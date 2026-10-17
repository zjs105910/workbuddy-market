# -*- coding: utf-8 -*-
"""uninstall_market —— 全盘精准卸载 WorkBuddy 本机插件市场。

设计目标（2026-10-17 事故后重做）：**不依赖脚本放在哪个盘、哪个目录**——
它从两个来源精准定位本机所有市场安装：

  1. 权威来源：~/.workbuddy/plugins/known_marketplaces.json 的注册条目
     （installLocation / source.path）；
  2. 兜底扫描：所有本地磁盘根目录 + %USERPROFILE% 下名为
     workbuddy-market 的文件夹（覆盖未注册的默认安装位）；
  3. 便利项：脚本自己所在目录（如果你恰好把它放进了市场根目录）。

安全纪律（fail-closed，接 2026-10-17「放错位置删掉文档夹」事故）：

  · 每个候选必须通过**市场根签名校验**——目录里同时有 launcher.py 和
    market_core.py 才算市场本体；签名不过的路径一律不碰，只如实报告；
  · 撤销注册走每个市场自己的 launcher.py --unregister（自动备份、
    乐观合并，是项目已验证的路径），不手工裸改 JSON；
  · 已注册但目录消失的残留条目：仅当 manifestName 以 wb-local-market
    开头（本项目的命名约定）才直接清条目，清理前先备份 JSON；
  · 目录删除走 Windows 回收站（SHFileOperation FOF_ALLOWUNDO），
    可恢复；回收失败就保留目录并如实报告，绝不强删。

刻意不碰：~/.workbuddy/skills（已装技能，走网页卸载）、
~/.workbuddy-market（状态与回收站，除非显式 --with-state）。

用法：
    python uninstall_market.py [--dry-run] [--yes] [--with-state]
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

MARKET_DIR_NAME = "workbuddy-market"
NAME_PREFIX = "wb-local-market"          # 本项目注册条目的命名约定
SIGNATURE = ("launcher.py", "market_core.py")


# ---------------------------------------------------------------- 定位

def known_json_path() -> Path:
    return Path.home() / ".workbuddy" / "plugins" / "known_marketplaces.json"


def load_known() -> dict:
    p = known_json_path()
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError) as exc:
        print(f"  △ known_marketplaces.json 读取失败（按无注册处理）：{exc}")
        return {}


def iter_fixed_drives() -> list[Path]:
    drives = []
    for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
        p = Path(f"{letter}:\\")
        if p.is_dir():
            drives.append(p)
    return drives


def discover_candidates() -> dict[str, list[str]]:
    """返回 候选根目录 -> 发现来源列表。只收集，不判定。"""
    found: dict[str, list[str]] = {}

    def add(path: Path, why: str) -> None:
        try:
            key = str(path.resolve()).lower()
        except OSError:
            return
        found.setdefault(key, [])
        if why not in found[key]:
            found[key].append(why)

    for key, entry in load_known().items():
        if not isinstance(entry, dict):
            continue
        src = entry.get("source") or {}
        for field in ("installLocation", "source"):
            raw = entry.get(field) or src.get(field)
            if isinstance(raw, str) and raw.strip():
                add(Path(raw), f"注册表条目 {key}")

    home_default = Path.home() / MARKET_DIR_NAME
    if home_default.is_dir():
        add(home_default, "默认安装位 %USERPROFILE%")

    for drive in iter_fixed_drives():
        probe = drive / MARKET_DIR_NAME
        if probe.is_dir():
            add(probe, f"{drive} 盘根目录扫描")

    # 刻意不含「脚本所在目录」：签名齐全的开发仓库/复制错位置的目录
    # 都会被误当成目标（2026-10-17 事故镜像）。定位只认注册表与
    # 固定命名位置，宁可漏报让人手动补，不可误删。
    return found


def has_signature(root: Path) -> bool:
    return all((root / name).is_file() for name in SIGNATURE)


# ---------------------------------------------------------------- 删除

def send_to_recycle_bin(path: Path) -> tuple[bool, str]:
    """目录送回收站（可恢复）。返回 (成功, 说明)。仅支持 Windows。"""
    if sys.platform != "win32":
        return False, "非 Windows 平台，未执行删除"

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", ctypes.c_void_p), ("wFunc", ctypes.c_uint),
                    ("pFrom", ctypes.c_wchar_p), ("pTo", ctypes.c_wchar_p),
                    ("fFlags", ctypes.c_ushort),
                    ("fAnyOperationsAborted", ctypes.c_int),
                    ("hNameMappings", ctypes.c_void_p),
                    ("lpszProgressTitle", ctypes.c_wchar_p)]

    FO_DELETE = 3
    FOF_ALLOWUNDO = 0x40
    FOF_NOCONFIRMATION = 0x10
    FOF_SILENT = 0x04
    op = SHFILEOPSTRUCTW()
    op.hwnd = None
    op.wFunc = FO_DELETE
    op.pFrom = str(path.resolve()) + "\0"       # 需要双 null 结尾
    op.pTo = None
    op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT
    rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if rc == 0 and not op.fAnyOperationsAborted:
        return True, "已移入回收站（可恢复）"
    return False, f"回收站删除失败（code={rc}），目录已保留，可手动处理"


# ---------------------------------------------------------------- 执行

def unregister_via_launcher(root: Path) -> str:
    """用该市场自己的 launcher --unregister 撤销注册（自带备份与合并）。"""
    try:
        proc = subprocess.run(
            [sys.executable, str(root / "launcher.py"), "--unregister"],
            capture_output=True, text=True, timeout=120, cwd=str(root),
            encoding="utf-8", errors="replace")
        if proc.returncode == 0:
            return "已撤销注册"
        tail = (proc.stdout or proc.stderr or "").strip().splitlines()
        detail = tail[-1] if tail else f"exit={proc.returncode}"
        return f"撤销注册返回码 {proc.returncode}（{detail}）"
    except (OSError, subprocess.SubprocessError) as exc:
        return f"撤销注册执行失败：{exc}"


def cleanup_stale_entries(roots_lower: set[str]) -> list[str]:
    """清掉「指向已删除市场」的残留注册条目。先备份，只动本项目的条目。"""
    p = known_json_path()
    data = load_known()
    if not data:
        return []
    doomed = []
    for key, entry in data.items():
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("manifestName", ""))
        loc = str((entry.get("installLocation") or "")).lower()
        if not name.startswith(NAME_PREFIX):
            continue                              # 不是本项目的条目，绝不碰
        if loc and loc in roots_lower:
            doomed.append(key)                    # 指向我们刚删掉的市场
        elif loc and not Path(loc).exists():
            doomed.append(key)                    # 目录已消失的残留
    if not doomed:
        return []
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = p.with_name(f"known_marketplaces.json.pre-uninstall-{stamp}")
    try:
        backup.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
        for key in doomed:
            data.pop(key, None)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                     encoding="utf-8")
        return [f"{k}（备份：{backup.name}）" for k in doomed]
    except OSError as exc:
        return [f"清理失败（JSON 原样保留）：{exc}"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="uninstall_market",
        description="全盘精准卸载 WorkBuddy 本机插件市场（注册表 + 常见位置双定位，"
                    "签名校验 fail-closed，目录进回收站可恢复）")
    ap.add_argument("--dry-run", action="store_true", help="只列出将要做的事，不执行")
    ap.add_argument("--yes", action="store_true", help="跳过确认（脚本/无人值守用）")
    ap.add_argument("--with-state", action="store_true",
                    help="连状态目录 ~/.workbuddy-market 一起删（含回收站与事务日志）")
    args = ap.parse_args(argv)

    cands = discover_candidates()
    verified, missing, suspicious = [], [], []
    seen = set()
    for key, whys in cands.items():
        root = Path(key)
        if key in seen:
            continue
        seen.add(key)
        if not root.exists():
            missing.append((root, whys))
        elif has_signature(root):
            verified.append((root, whys))
        else:
            suspicious.append((root, whys))

    print()
    print("WorkBuddy 本机插件市场 —— 精准卸载")
    print("=" * 56)
    if not verified and not missing:
        print("没有找到任何市场安装（注册表与常见位置均已检查）。无事可做。")
        return 0
    for root, whys in verified:
        print(f"  目标  {root}")
        print(f"        来源：{'；'.join(whys)}（签名校验 ✓）")
    for root, whys in missing:
        print(f"  残留  {root}（目录已不存在，将只清注册条目）")
    for root, whys in suspicious:
        print(f"  跳过  {root} —— 存在但缺市场签名（launcher.py/market_core.py），不碰")
    print()
    print("  将执行：撤销注册 → pipx uninstall workbuddy-market → 目录进回收站")
    print("  不会碰：~/.workbuddy/skills 已装技能；状态目录（除非 --with-state）")
    print()

    if args.dry_run:
        print("--dry-run：以上仅为计划，未做任何改动。")
        return 0
    if not args.yes:
        try:
            ans = input("确认执行？输入 Y 继续，其他任意键取消：").strip().lower()
        except EOFError:
            ans = ""
        if ans != "y":
            print("已取消，未做任何改动。")
            return 1

    ok = True
    for root, _ in verified:
        print()
        print(f"── 处理 {root}")
        msg = unregister_via_launcher(root)
        print(f"  [1/3] 撤销注册：{msg}")
    pipx = shutil.which("pipx")
    print()
    print("  [2/3] 卸载命令行工具（pipx）")
    if pipx:
        proc = subprocess.run([pipx, "uninstall", "workbuddy-market"],
                              capture_output=True, text=True)
        out = (proc.stdout or proc.stderr or "").strip().splitlines()
        print("        " + (out[-1] if out else f"exit={proc.returncode}"))
    else:
        print("        未找到 pipx，跳过（CLI 可能本就未安装）")

    roots_lower = {str(root.resolve()).lower() for root, _ in verified}
    print("  [3/3] 删除市场目录（进回收站）")
    for root, _ in verified:
        done, why = send_to_recycle_bin(root)
        print(f"        {root} → {why}")
        ok = ok and done

    stale = cleanup_stale_entries(roots_lower)
    for line in stale:
        print(f"  残留条目清理：{line}")

    if args.with_state:
        state = Path.home() / ".workbuddy-market"
        if state.is_dir():
            done, why = send_to_recycle_bin(state)
            print(f"  状态目录 {state} → {why}")
            ok = ok and done
        else:
            print("  状态目录不存在，跳过。")
    else:
        state = Path.home() / ".workbuddy-market"
        if state.is_dir():
            print(f"  状态目录保留：{state}（含可恢复回收站；确认不要可加 --with-state 或手动删）")

    print()
    if ok:
        print("✅ 卸载完成。以上目录均可在回收站找回。")
    else:
        print("△ 部分目录未能删除（被占用？），已保留并在上方注明原因。")
        print("  提示：关闭正在运行的市场窗口后重跑本脚本。")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
