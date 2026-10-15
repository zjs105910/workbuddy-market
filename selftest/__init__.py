# -*- coding: utf-8 -*-
"""selftest 共享基础设施（v2.34 从 selftest.py 单体拆出）。

本模块被 import 时即完成隔离环境准备（环境变量必须在 import market_core
之前设置——路径常量是 import 期求值的），因此任何 ``selftest.*`` 子模块
的导入都会先触发这里。各评审轮次在 runner.py 按序调度。"""
from __future__ import annotations


import json
import os
import stat
import sys
import tempfile
from pathlib import Path

SELFTEST_VERSION = "2.36"

# ---------------------------------------------------------------- 隔离环境
# 必须在 import market_core 之前设置：路径常量是 import 期求值的。

_ISOLATED = "--real" not in sys.argv
_TMP = None

if _ISOLATED:
    # .resolve() 必须加：GitHub Windows runner 的 TEMP 是 8.3 短路径
    # （RUNNER~1 形态，见 GitHub runner 镜像文档），而路径常量在 import 期
    # 经 Path.resolve() 展开成长路径，后续用 str(_TMP) 做前缀比较会对不上
    # （v2.21 CI 唯一 FAIL；本机 TEMP 已是长路径，从未暴露）。
    _TMP = Path(tempfile.mkdtemp(prefix="wbm-selftest-")).resolve()
    os.environ["GHPM_MARKET_ROOT"] = str(_TMP / "market")
    os.environ["GHPM_HOME"] = str(_TMP / "wb")
    (_TMP / "market").mkdir(parents=True, exist_ok=True)
    (_TMP / "wb" / "skills").mkdir(parents=True, exist_ok=True)
    (_TMP / "wb" / "plugins").mkdir(parents=True, exist_ok=True)

REPO_ROOT = Path(__file__).resolve().parents[1]   # 本文件在 selftest/ 下，上两级才是仓库根
sys.path.insert(0, str(REPO_ROOT))
import market_core as core  # noqa: E402
import workbuddy_market as wm  # noqa: E402,F401  （再导出：各轮次经 kit 用同一实例）  （R3 起注入点迁到包命名空间时用）
import workbuddy_market.ownership  # noqa: E402  （R4：所有权迁包）
import workbuddy_market.transactions  # noqa: E402  （R4：事务迁包）
import workbuddy_market.trash  # noqa: E402,F401  （副作用导入：patch 落点注册）  （R4：回收站迁包）

PASS, FAIL, SKIP = [], [], []

def ck(name: str, cond: bool, extra: str = ""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  —— {extra}" if extra else ""))


def sk(name: str, why: str = ""):
    """明确跳过 —— 不算通过，也不算失败，但必须让人看见。

    「环境缺个文件就整条挂死」会让人以为代码坏了；「静默当通过」更糟。
    """
    SKIP.append(name)
    print(f"  SKIP  {name}" + (f"  —— {why}" if why else ""))


def section(t: str):
    print(f"\n--- {t} ---")

FAKE_SKILLS = {
    "alpha": ("1.0.0", "Alpha 技能",
              {"notes.md": "# notes\n", "sub/deep.txt": "deep\n"}),
    "beta": ("2.1.0", "Beta 技能", {"data.bin": "x" * 200}),
    "gamma": ("0.9.0", "Gamma 技能", {}),
}


def write_fake_skill(root: Path, name: str, version: str, desc: str, files: dict) -> Path:
    d = Path(root) / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\nversion: {version}\ndescription: \"{desc}\"\n---\n\n# {name}\n",
        encoding="utf-8",
    )
    for rel, content in files.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return d


def prepare_fixture():
    for name, (ver, desc, files) in FAKE_SKILLS.items():
        write_fake_skill(core.SKILLS_DIR, name, ver, desc, files)

    cfg = {
        "marketId": "test-market",
        "name": "测试市场",
        "description": "selftest 用",
        "owner": {"name": "Test"},
        "localPlugins": [
            {"name": "bundle-one", "displayName": "第一包", "category": "测试",
             "version": "1.0.0", "description": "含 alpha 与 beta", "keywords": ["t"],
             "skills": ["alpha", "beta"]},
            {"name": "bundle-two", "displayName": "第二包", "category": "测试",
             "version": "2.0.0", "description": "含 gamma", "skills": ["gamma"]},
        ],
        "remoteSources": [{"repo": "owner/repo", "displayName": "远端的", "category": "远端"}],
        "packaging": {"excludeNames": ["__pycache__"], "excludeGlobs": ["*.bak", "*.tmp"]},
        "trash": {"maxAgeDays": 30, "maxSizeBytes": 1024 * 1024},
    }
    core.CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

def check_real() -> int:
    print("只读模式：检查现网市场状态（不写任何东西）\n")
    st = core.build_state()
    ck("市场可枚举", st["stats"]["localPlugins"] > 0,
       f"{st['stats']['localPlugins']} 插件 / {st['stats']['localSkills']} skill")
    ck("地图与索引一致", st["manifestOk"])
    ok, errors, warns = core.deep_check()
    ck("深度自检无 error", ok, "; ".join(errors[:3]))
    if warns:
        print(f"  （{len(warns)} 条 warning）")
        for w in warns[:6]:
            print("     ! " + w)

    # 关键安全检查：每个插件的卸载分级必须覆盖它声明的所有 skill，
    # 且在没有所有权记录时，一律不得判为「可卸载」。
    own = core.load_ownership()["skills"]
    for p in st["plugins"]:
        u = p["uninstall"]
        acc = sum(u["counts"].values())
        ck(f"插件 {p['id']} 卸载分级覆盖全部 skill", acc == len(p["skills"]),
           f"{acc}/{len(p['skills'])}")
        claimed = [s for s in u["removable"] if s not in own]
        ck(f"插件 {p['id']} 没把无主的 skill 判成可卸载", not claimed, str(claimed))
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    return 1 if FAIL else 0

# ---------------------------------------------------------------- 共享小工具
# 跨轮次复用的助手集中放这里：链接构造（faults / round5 / round6 用）、
# 配置快照恢复（round4 / round19 用）。
def _restore_config(snapshot: str) -> None:
    core.CONFIG_PATH.write_text(snapshot, encoding="utf-8")


def _make_link(target: Path, link: Path) -> str:
    """尽力造一个重解析点，返回造出来的类型名或空串。

    先试 junction（不需要管理员），再试符号链接。
    注意 Windows 上 `os.symlink` 可能被宿主环境拦成普通空文件 ——
    这时 is_symlink() 是 False，说明没造成，必须如实报告而不是假装通过。
    """
    try:
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
        return "junction"
    except Exception:
        pass
    try:
        os.symlink(target, link, target_is_directory=True)
        if os.path.islink(link) or (getattr(os.path, "isjunction", None) and os.path.isjunction(link)):
            return "symlink"
        # 宿主把 symlink 拦成了普通目录/文件 → 清掉，别留下垃圾
        _drop_link(link)
    except Exception:
        pass
    return ""


def _is_dir_link(path: Path) -> bool:
    """这个是「目录形态的重解析点」吗？**看 lstat，不要看 is_dir()**。"""
    try:
        st = path.lstat()
    except OSError:
        return False
    return stat.S_ISDIR(st.st_mode)


def _drop_link(link: Path) -> None:
    """摘掉重解析点。必须用 lstat 判断类型，**不能用 Path.is_dir()** ——
    它会跟随链接：指向目录的 symlink 让 is_dir() 返回 True，于是走到
    `os.rmdir(symlink)`，而 POSIX 上 rmdir 对 symlink 是 ENOTDIR，
    链接根本摘不掉，异常还被 except 吞掉。

    Windows 的 junction 恰好能 rmdir 成功，所以在 Windows 上这个 bug 不会暴露 ——
    但它会污染后续用例（残留的链接让"链接安全检查"拒绝本该成功的安装）。
    同样，**绝不能 rmtree**：那会顺着链接递归进去删掉目标里的真东西。
    """
    try:
        if _is_dir_link(link):
            os.rmdir(str(link))     # 目录 / junction
        else:
            link.unlink()           # 文件 / 符号链接
    except OSError:
        pass


def _raises(fn, exc_type, *args, **kwargs) -> bool:
    try:
        fn(*args, **kwargs)
        return False
    except exc_type:
        return True
