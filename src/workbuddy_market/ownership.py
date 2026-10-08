# -*- coding: utf-8 -*-
"""ownership —— 所有权账本（v2.12 R4 自 market_core.py 逐字迁入）。

`.ownership.json` 记「哪些 skill 是本市场装的、装的时候长什么样」：
每个 skill 一条 {owner, plugin, version, installedAt, hash, fingerprint}。

  · hash         内容 SHA-256（准，但要读全部文件）—— 判「能不能安全卸载」；
  · fingerprint  文件数 / 总字节 / mtime_ns 聚合（廉价，只 stat）—— 候选判定。

纪律与原状完全一致：分类判定走 classify_skill(..., purpose=...)，
cheap 指纹只影响性能语义，安全语义必须读内容（约定 2）。

注入点接缝（v2.12 R4）：
  `record_owner()` 用的 `tree_hash` / `quick_fingerprint` 仍定义在 core
  （selftest 崩溃/计数注入点，第 24B 节盯防），因此在调用点晚绑定
  ``import market_core`` —— patch ``core.tree_hash`` / ``core.quick_fingerprint``
  对所有权侧的调用依然有效，与 v2.11 前语义一致。
  本模块内部的 load/save/record/forget 互调走本模块命名空间，patch
  ``workbuddy_market.ownership.save_ownership`` 即可拦到（selftest 已按此调整）。
"""
from __future__ import annotations

import json
from pathlib import Path

from .errors import ConfigError
from .fsutil import atomic_write_text, read_json
from .paths import OWNERSHIP_PATH, SKILLS_DIR
from .version import OWNERSHIP_SCHEMA
from .logging import now_iso
from .config import load_config


def load_ownership() -> dict:
    data = read_json(OWNERSHIP_PATH, None)
    if not isinstance(data, dict) or "skills" not in data:
        return {"version": OWNERSHIP_SCHEMA, "skills": {}}
    data.setdefault("skills", {})
    return data


def save_ownership(own: dict) -> None:
    own["version"] = OWNERSHIP_SCHEMA
    atomic_write_text(OWNERSHIP_PATH,
                      json.dumps(own, ensure_ascii=False, indent=2) + "\n",
                      durable=True)


def record_owner(plugin_id: str, skills: list, version: str,
                 snapshots: dict | None = None) -> None:
    """记下「这些 skill 是本市场这个插件装的」，并留两层指纹。

    hash         内容 SHA-256（准，但要读全部文件）
    fingerprint  文件数 / 总字节 / mtime_ns 聚合（廉价，只 stat）

    snapshots: {skill: {"hash": ..., "fingerprint": ...}}。
    安装路径会把暂存阶段已经算好的结果传进来 —— 落位用的是同一批文件、
    内容一模一样，没必要在 commit 之后把新版本整个重扫一遍再算一次哈希。
    """
    import market_core as _core          # noqa: PLC0415 —— 注入点晚绑定，见模块 docstring
    own = load_ownership()
    mid = _market_id()
    snaps = snapshots or {}
    for s in skills:
        d = SKILLS_DIR / s
        if not (d / "SKILL.md").is_file():
            continue
        pre = snaps.get(s) if isinstance(snaps.get(s), dict) else {}
        own["skills"][s] = {
            "owner": mid,
            "plugin": plugin_id,
            "version": version,
            "installedAt": now_iso(),
            "hash": pre.get("hash") or _core.tree_hash(d),
            "fingerprint": pre.get("fingerprint") or _core.quick_fingerprint(d),
        }
    save_ownership(own)


def _market_id() -> str:
    try:
        return load_config().get("marketId", "wb-local-market")
    except ConfigError:
        return "wb-local-market"


def forget_owner(skills: list) -> None:
    own = load_ownership()
    changed = False
    for s in skills:
        if s in own["skills"]:
            del own["skills"][s]
            changed = True
    if changed:
        save_ownership(own)
