# -*- coding: utf-8 -*-
"""posix-smoke —— POSIX 语义冒烟（v2.17 新增，CI Ubuntu 槽位跑）。

现状：完整 selftest 的硬门槛仅在 Windows（README 第七/十节如实标注），
Ubuntu 槽位此前只做 py_compile + 隐私审计。本脚本把「POSIX 分支是否
真的存在且行为正确」变成最小可执行证据 —— v3-roadmap §5 认可的
「独立 POSIX 语义冒烟」路线。它**不是**完整 selftest 的替代，只盯防
跨平台历史上踩过坑的分支：

  1. fcntl 文件锁：独占语义 + 重入计数（约定 16 的跨实例重入）；
  2. 符号链接防线：skills 目录里的 symlink 被 _scan 如实报出；
  3. os.replace 原子换位 + atomic_write_text durable；
  4. 路径穿越闸门 ensure_child 与平台无关地拒绝 ``..``；
  5. artifact.unpack_zip 的 zip-slip 防线在 POSIX 上同样成立。

在 Windows 上运行时明确 SKIP（exit 0）—— 它的存在不是为了在 Windows
上模拟 POSIX，而是让 Ubuntu CI 槽位有真实语义可验。
"""
from __future__ import annotations

import os
import stat
import sys
import tempfile
import zipfile
from pathlib import Path

PASS, FAIL, SKIP = [], [], []


def ck(name: str, cond: bool, extra: str = ""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  —— {extra}" if extra else ""))


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if os.name != "posix":
        print("posix-smoke：非 POSIX 平台，跳过（本脚本只验 POSIX 分支）。")
        return 0

    root = Path(tempfile.mkdtemp(prefix="wbm-posix-smoke-"))
    os.environ.setdefault("WBM_MARKET_ROOT", str(root / "market"))
    os.environ.setdefault("WBM_HOME", str(root / "wb"))
    (root / "market").mkdir(parents=True, exist_ok=True)
    (root / "wb" / "skills").mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import market_core as core
    import workbuddy_market as wm
    import workbuddy_market.artifact as ar
    import workbuddy_market.errors as werr

    # --- 1. fcntl 文件锁：独占 + 跨实例重入计数
    lock_a = core.FileLock(core.LOCK_PATH)
    lock_b = core.FileLock(core.LOCK_PATH)
    with lock_a:
        try:
            with lock_b.acquire(timeout=0.2):
                ck("fcntl 锁独占语义（另一实例 0.2s 内拿不到）", False)
        except core.FileLockTimeout:
            ck("fcntl 锁独占语义（另一实例 0.2s 内拿不到）", True)
        # 同一线程嵌套取锁走 _HELD 重入计数，不该自锁死
        with core.locked():
            ck("锁重入计数（同线程嵌套不死锁）", True)
    try:
        with lock_b.acquire(timeout=0.5):
            ck("锁释放后另一实例可得", True)
    except core.FileLockTimeout:
        ck("锁释放后另一实例可得", False)

    # --- 2. symlink 防线：_scan 如实报出重解析点
    skill = root / "wb" / "skills" / "smoke"
    (skill / "sub").mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text("---\nname: smoke\n---\n# x\n", encoding="utf-8")
    link = skill / "sub" / "link"
    try:
        os.symlink(root / "market", link)
        made = os.path.islink(link)
    except OSError:
        made = False
    if made:
        try:
            _idx, links = core._scan(skill, on_error="raise")
            ck("★ symlink 被 _scan 如实报出（不跟随）", bool(links), str(links[:1]))
        except Exception as exc:  # noqa: BLE001
            ck("★ symlink 被 _scan 如实报出（不跟随）", False, str(exc))
        finally:
            link.unlink()
    else:
        print("  SKIP  symlink 防线（宿主环境不允许 os.symlink）")

    # --- 3. os.replace 原子换位 + durable 原子写
    f1, f2 = root / "a.txt", root / "b.txt"
    f1.write_text("v1", encoding="utf-8")
    wm.fsutil.atomic_write_text(f2, "v2", durable=True)
    os.replace(f2, f1)
    ck("os.replace 原子换位 + atomic_write_text(durable)",
       f1.read_text(encoding="utf-8") == "v2" and not f2.exists())

    # --- 4. ensure_child 穿越闸门（平台无关，POSIX 上再证一次）
    try:
        core.ensure_child(root, root / ".." / "escape")
        ck("★ ensure_child 拒绝 .. 穿越", False)
    except core.ConfigError:
        ck("★ ensure_child 拒绝 .. 穿越", True)

    # --- 5. artifact.unpack_zip zip-slip 防线（POSIX 复证）
    zbad = root / "bad.zip"
    with zipfile.ZipFile(zbad, "w") as z:
        z.writestr(zipfile.ZipInfo("../evil.txt"), "x")
    try:
        core.unpack_zip(zbad, root / "un")
        ck("★ unpack_zip 拒绝 zip-slip", False)
    except werr.ArtifactError:
        ck("★ unpack_zip 拒绝 zip-slip", True)
    ck("解包失败目录已清理", not (root / "un").exists())

    import shutil
    shutil.rmtree(root, ignore_errors=True)
    print(f"\nposix-smoke: {len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        for f in FAIL:
            print("  - " + f)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
