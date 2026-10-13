"""同内容多份拷贝的一致性门禁（stdlib，零第三方依赖）。

管两组「故意重复」的拷贝——协议约束下的必然，不是疏漏：

  A. bundled 插件内的共享助手脚本。插件安装粒度是 **per-skill**
     （skills/<name>/ 整个目录进本机 skills 目录），SKILL.md 里写的
     都是「本 skill 自带的 scripts/xxx.py」——跨技能共享目录在协议内
     不可行（源技能没装，引用就断）。所以同一助手在每个子技能各存
     一份，必须逐字节一致。白名单见 SHARED_HELPERS：新增共享助手要
     往里加。不能按「重名即同内容」一刀切——ghpm 的两个 __init__.py
     内容 legitimately 不同（包结构使然），一刀切会误报。
  B. plugins/ ↔ bundled/ 的三个自有插件。plugins/ 是个人编辑面
     （gitignored，不随仓库分发），bundled/ 是分发副本，两边必须逐
     字节一致。plugins/ 不存在时（CI 干净 clone，或本机没同步过
     个人数据）跳过并明说——这一组只在本机开发流里有效，CI 跑不到。

用法：
  python scripts/check_dup_sync.py
退出码：0 = 一致（或 B 组跳过）；1 = 有漂移（逐文件列出）。
"""

import hashlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# A 组白名单：跨子技能共享、必须逐字节一致的助手脚本（basename）
SHARED_HELPERS = ("tracking_commit.py", "author_memory_commit.py", "wordcount_core.py")

# B 组对象：bundled/ 里入库分发的三个自有插件（与 plugins/ 手工同步）
OWN_PLUGINS = ("browser-cdp", "github-project-manager", "novel-writing-suite")


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _tree(root: Path) -> dict:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            out[p.relative_to(root).as_posix()] = _sha(p)
    return out


def check_shared_helpers() -> list:
    """A 组：bundled 各插件内，同名共享助手必须内容一致。"""
    problems = []
    for plugin in OWN_PLUGINS:
        skills_dir = REPO / "bundled" / plugin / "skills"
        if not skills_dir.is_dir():
            continue
        for helper in SHARED_HELPERS:
            copies = sorted(skills_dir.rglob(helper))
            if len(copies) < 2:
                continue          # 没被多个子技能用到的助手不归本组管
            hashes = {}
            for c in copies:
                hashes.setdefault(_sha(c), []).append(c)
            if len(hashes) > 1:
                problems.append(
                    f"bundled/{plugin}: {helper} 有 {len(copies)} 份拷贝但内容不一致——"
                    f"它们是 per-skill 安装协议下的共享助手，改一份必须同步其余副本")
                for h, paths in hashes.items():
                    problems.append("    " + h[:12] + "  " +
                                    "\n    ".join(p.as_posix() for p in paths))
    return problems


def check_plugins_mirror() -> tuple:
    """B 组：plugins/（个人编辑面）与 bundled/（分发副本）逐字节一致。

    返回 (problems, skipped)。plugins/ 不存在 → skipped=True。
    """
    plugins_dir = REPO / "plugins"
    if not plugins_dir.is_dir():
        return [], True
    problems = []
    for plugin in OWN_PLUGINS:
        src, dst = plugins_dir / plugin, REPO / "bundled" / plugin
        if not src.is_dir():
            continue
        t_src, t_dst = _tree(src), _tree(dst)
        for rel in sorted(set(t_src) | set(t_dst)):
            h1, h2 = t_src.get(rel), t_dst.get(rel)
            if h1 is None:
                problems.append(f"{plugin}/{rel}: 只在 bundled/ 有（plugins/ 缺）")
            elif h2 is None:
                problems.append(f"{plugin}/{rel}: 只在 plugins/ 有（bundled/ 缺）")
            elif h1 != h2:
                problems.append(
                    f"{plugin}/{rel}: 两边内容不一致——plugins/ 是编辑面、"
                    f"bundled/ 是分发副本，改完记得同步（bundled/ 侧需要保留 "
                    f"pa:allow 等仓库特有调整）")
    return problems, False


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    a = check_shared_helpers()
    b, skipped = check_plugins_mirror()

    if a:
        print("[dup-sync] A 组（bundled 共享助手）漂移：")
        for p in a:
            print("  " + p)
    if skipped:
        print("[dup-sync] B 组（plugins/ ↔ bundled/）跳过：本机无 plugins/ 目录"
              "（CI 干净 clone 或个人数据未就位），该组只在本机开发流有效")
    elif b:
        print("[dup-sync] B 组（plugins/ ↔ bundled/）漂移：")
        for p in b:
            print("  " + p)

    if a or b:
        print(f"\n[dup-sync] 失败：A 组 {len(a)} 项、B 组 {len(b)} 项漂移")
        return 1
    print("[dup-sync] 一致：共享助手副本逐字节相同"
          + ("；plugins/ 组跳过" if skipped else "；plugins/ ↔ bundled/ 一致"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
