# -*- coding: utf-8 -*-
"""workbuddy_market.favorites —— 本机收藏（v2.21 新增，评审 #13）。

评审 #13（dsh-market 对比）：收藏是「安装之前先了解插件、安装之后还要
管理」的产品闭环里的一环。本市场的收藏**纯本机**（Local-first）：

  · 存 ``STATE_HOME/favorites.json``，不进 Git、不上传 —— 与 ownership /
    事务日志 / 回收站同一运行状态分桶纪律；
  · 收藏的是**注册表条目的 repo 标识**（社区目录里的插件），不是本机
    plugin id —— 收藏的是「我想装 / 我常用的那个上游」，语义与 installed
    解耦（收藏了不代表装过，装过也不自动收藏）；
  · 形状不可信：坏了当空集合，绝不带病进前端（fail-closed）。

为什么不是「收藏本机插件」：本机插件来自你自己的 market.config.json，
要不要装是你自己写配置决定的，不存在「发现 → 收藏 → 稍后装」的链路；
社区目录才是发现型场景，收藏挂在 repo 上才对。
"""
from __future__ import annotations

import json

from .fsutil import atomic_write_text, read_json
from .paths import STATE_HOME

FAVORITES_PATH = STATE_HOME / "favorites.json"
MAX_FAVORITES = 1000          # 上限（防坏文件撑爆内存，与注册表同纪律）


def load_favorites() -> list:
    """读收藏列表。**不可信状态文件**：形状不对当空集合。

    返回按加入顺序排列的 repo 列表（去重、casefold 归一）。"""
    data = read_json(FAVORITES_PATH, {}) or {}
    if not isinstance(data, dict):
        return []
    items = data.get("repos")
    if not isinstance(items, list):
        return []
    seen, out = set(), []
    for r in items:
        if not isinstance(r, str):
            continue
        key = r.strip().casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(r.strip())
        if len(out) >= MAX_FAVORITES:
            break
    return out


def is_favorite(repo: str) -> bool:
    key = (repo or "").strip().casefold()
    return bool(key) and key in {r.casefold() for r in load_favorites()}


def set_favorite(repo: str, on: bool) -> bool:
    """加 / 删一个收藏。返回变更后的完整列表。

    repo 合法性由调用方保证（注册表条目已经过 validate_repo），这里只做
    非空与大小写归一；写盘走原子写（半截 JSON 绝不落盘）。"""
    key = (repo or "").strip()
    if not key:
        return load_favorites()
    cur = load_favorites()
    cur_keys = [r.casefold() for r in cur]
    k = key.casefold()
    changed = False
    if on and k not in cur_keys:
        cur.append(key)
        changed = True
    if not on and k in cur_keys:
        cur = [r for r in cur if r.casefold() != k]
        changed = True
    if changed:
        atomic_write_text(FAVORITES_PATH,
                          json.dumps({"repos": cur}, ensure_ascii=False, indent=2))
    return cur
