# -*- coding: utf-8 -*-
"""doctor —— ``workbuddy-market doctor``（v2.13 新增）。

定位：把散落在深度自检 / 状态页 / 事务恢复里的健康信号收敛成一份
**不依赖 clone 布局也能跑**的体检报告。与 ``launcher.py --status``
的区别：launcher 的深度自检假设你就是这个市场的作者（要配置、要打包），
doctor 面向「装好之后出问题了」的用户 —— 每一项检查独立捕获异常，
坏了就如实标 ✗ 并给出下一步动作，绝不让一项故障拖垮整份报告。

每一项检查都是只读的；唯一有副作用的路径是 ``--fix``，它只做
``recover_transactions()``（补记所有权 + 清理安装暂存）—— 与
``python launcher.py --recover`` 完全同一套入口，不新增第二种恢复语义。

路径解析说明：本模块信任 ``workbuddy_market.paths`` 的解析结果
（WBM_MARKET_ROOT 环境变量 > 仓库根 fallback）。通过 pipx 安装后在
clone 目录里运行时，cli 入口会先把仓库根写进环境变量；在 clone 外
运行时 MARKET_ROOT 落在 site-packages 一侧，「市场根」一项会如实
标 ✗ —— 这是预期行为，提示用户在 clone 内运行或设置环境变量。
"""
from __future__ import annotations

import sys
from pathlib import Path

from .config import ConfigError, load_config, validate_config
from .ownership import load_ownership
from .paths import (
    GHPM_PY, KNOWN_PATH, MANIFEST_PATH, MARKET_ROOT, SKILLS_DIR,
    STATE_HOME, TRASH_DIR,
)
from .registry import REGISTRY_FILENAME, load_registry_cache
from .transactions import tx_list
from .trash import _TRASH_NAME_BAD, _load_trash_index, trash_stats


def _check(name: str, ok: bool, detail: str = "", warn: bool = False) -> dict:
    return {"name": name, "ok": ok, "warn": warn and ok, "detail": detail}


def run_doctor(fix: bool = False) -> dict:
    """逐项体检。返回 {"ok", "checks", "fix", "warnings"}，ok = 无 error 项。"""
    checks: list[dict] = []

    # --- Python 版本
    vi = sys.version_info
    checks.append(_check(
        "Python",
        vi >= (3, 10),
        f"{vi.major}.{vi.minor}.{vi.micro}"
        + ("" if vi >= (3, 10) else "（需要 ≥ 3.10）")))

    # --- 市场根
    config_ok = False
    cfg = None
    has_config = (MARKET_ROOT / "market.config.json").is_file()
    checks.append(_check(
        "市场根（MARKET_ROOT）",
        has_config,
        f"{MARKET_ROOT}"
        + ("" if has_config else
           "（没有 market.config.json —— 请在仓库 clone 内运行，"
           "或设置 WBM_MARKET_ROOT 指向市场根）")))

    # --- 配置
    if has_config:
        try:
            cfg = load_config()
            config_ok = True
            warns = validate_config(cfg)
            for w in warns:
                checks.append(_check(f"配置警告：{w[:60]}", True, "", warn=True))
        except ConfigError as exc:
            checks.append(_check("配置（market.config.json）", False, str(exc)))
        if config_ok:
            n_local = len(cfg.get("localPlugins", []))
            n_remote = len(cfg.get("remoteSources", []))
            checks.append(_check("配置", True,
                                 f"本机插件 {n_local} 个 / GitHub 源 {n_remote} 个"))
    else:
        checks.append(_check("配置（market.config.json）", False, "市场根里没有配置文件"))

    # --- WorkBuddy 家目录 / skills
    checks.append(_check(
        "WorkBuddy 家目录", KNOWN_PATH.parent.is_dir(), str(KNOWN_PATH.parent)))
    checks.append(_check(
        "本机 skills 目录", SKILLS_DIR.is_dir(), str(SKILLS_DIR)))

    # --- 打包索引
    checks.append(_check(
        "市场索引（打包产物）", MANIFEST_PATH.is_file(),
        str(MANIFEST_PATH) + ("" if MANIFEST_PATH.is_file()
                              else "（还没打包 —— 在市场根运行一次同步）"),
        warn=not MANIFEST_PATH.is_file()))

    # --- ghpm
    checks.append(_check(
        "ghpm 安装器", GHPM_PY.is_file(),
        str(GHPM_PY) + ("" if GHPM_PY.is_file() else "（缺失 —— GitHub 源安装不可用）")))

    # --- 所有权
    try:
        own = load_ownership()
        checks.append(_check("所有权记录", True, f"{len(own['skills'])} 个 skill"))
    except Exception as exc:      # ownership 是状态文件，坏了必须报出来
        checks.append(_check("所有权记录", False, f"读取失败：{exc}"))

    # --- 事务日志（未结的账）
    try:
        pending = []
        for tx in tx_list():
            pend = tx.get("pendingOwnership") or []
            forget = tx.get("pendingForget") or []
            if pend or forget:
                pending.append(tx.get("id", "?"))
        if pending:
            checks.append(_check(
                "事务日志", False,
                f"{len(pending)} 份未结（{pending[:3]}）—— 运行 workbuddy-market doctor --fix"))
        else:
            checks.append(_check("事务日志", True, "无未结事务"))
    except Exception as exc:
        checks.append(_check("事务日志", False, f"读取失败：{exc}"))

    # --- 回收站（含索引安全）
    try:
        ts = trash_stats()
        checks.append(_check(
            "回收站", True,
            f"{ts['count']} 项，{ts['bytes'] / 1048576:.1f} MB（{TRASH_DIR}）"))
        bad = []
        if (TRASH_DIR / ".index.json").is_file():
            tidx = _load_trash_index()
            bad = [n for n in tidx.get("items", {}) if _bad_entry_name(n)]
        if bad:
            checks.append(_check(
                "回收站索引", False,
                f"{len(bad)} 个非法条目名 {bad[:3]}（越界删除风险，"
                f"可删掉 {TRASH_DIR / '.index.json'} 让它重建）"))
    except Exception as exc:
        checks.append(_check("回收站", False, f"统计失败：{exc}"))

    # --- 注册表缓存（只读本地缓存，绝不联网）
    try:
        cache = load_registry_cache()
        if cache:
            src = cache.get("source", "?")
            n_reg = len(cache.get("plugins", []))
            checks.append(_check("社区注册表缓存", True,
                                 f"{n_reg} 条（来源 {src}）"))
        else:
            checks.append(_check(
                "社区注册表缓存", True,
                "无缓存（首次刷新后生成；离线兜底见仓库内 "
                f"{REGISTRY_FILENAME}）", warn=True))
    except Exception as exc:
        checks.append(_check("社区注册表缓存", False, f"读取失败：{exc}"))

    # --- 运行状态目录
    checks.append(_check("运行状态目录（STATE_HOME）", STATE_HOME.is_dir(),
                         str(STATE_HOME)))

    # ok 只看 error 项；warn（如「索引还没打包」「注册表无缓存」）不算失败，
    # 与 deep_check「warnings 不挡门」的口径一致。
    ok = all(c["ok"] for c in checks)

    fix_result = None
    if fix:
        from .transactions import recover_transactions      # noqa: PLC0415 —— 仅 --fix 时才需要
        fix_result = recover_transactions(quiet=False)
        # 恢复之后重查一次事务
        still = [tx.get("id", "?") for tx in tx_list()
                 if (tx.get("pendingOwnership") or []) or (tx.get("pendingForget") or [])]
        checks.append(_check(
            "--fix 恢复", not still,
            "无残留未结事务" if not still else
            f"仍有 {len(still)} 份未结（{still[:3]}）—— 内容已被改动的事务会"
            "一直保留（见 docs：恢复只认「内容还是当初那一份」）"))

    return {"ok": ok, "checks": checks, "fix": fix_result}


def _bad_entry_name(name) -> bool:
    """与 trash._trash_entry 的边界一致，但不做 ensure_child（doctor 不碰磁盘）。"""
    if not isinstance(name, str) or not name:
        return True
    if any(ch in name for ch in _TRASH_NAME_BAD):
        return True
    return Path(name).name != name


def render(result: dict) -> str:
    """把 run_doctor 的结果渲染成终端友好的文本。"""
    lines = ["WorkBuddy Market Doctor", "─" * 40]
    for c in result["checks"]:
        mark = "✓" if c["ok"] and not c["warn"] else ("!" if c["ok"] else "✗")
        detail = f" — {c['detail']}" if c["detail"] else ""
        lines.append(f"{mark} {c['name']}{detail}")
    if not result["ok"]:
        lines.append("")
        lines.append("存在错误项；提示：市场根内的常规入口是 一键启动.cmd / python launcher.py")
    return "\n".join(lines)


def main(argv: list | None = None) -> int:
    argv = list(argv or [])
    fix = "--fix" in argv
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    result = run_doctor(fix=fix)
    print(render(result))
    return 0 if result["ok"] else 1
