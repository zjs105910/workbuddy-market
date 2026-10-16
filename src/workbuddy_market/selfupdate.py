# -*- coding: utf-8 -*-
"""selfupdate —— 市场本体更新检查（v2.36 新增）。

检查「WorkBuddy Market 自己」是否有新版本：把运行中的 ``MARKET_VERSION``
与 GitHub Releases 的最新正式 tag 比对。**只读不装** —— 升级动作永远由
用户自己执行，这里只给出两条人话升级路径：

  · 一键安装渠道：重跑 install.cmd 更新 CLI 并检查市场本体；确认后运行
    ``install.cmd --update-root`` 才会替换市场根；
  · pipx / 源码渠道：``pipx upgrade workbuddy-market``，再用
    ``workbuddy-market root-update --market-root <市场根目录>`` 更新本体；Git
    工作区一律用 ``git pull``，不做自动目录替换。

设计约束（与全项目同口径）：
  · 网络接缝只有一处（``_release_fetch``），自检 / pytest 可整体替换；
  · 网络失败**如实返回**（``updateAvailable: None`` + 人话 error），
    绝不假装「已是最新」，也绝不抛异常让 UI 白屏；
  · 比较是纯的（X.Y.Z 逐段比），tag 形态不对（非 ``vX.Y.Z``）时如实
    报告拿不到，不猜。
"""
from __future__ import annotations

import re
import urllib.request
from datetime import datetime, timezone

LATEST_RELEASE_URL = (
    "https://api.github.com/repos/zjs105910/workbuddy-market/releases/latest")
SELFUPDATE_TIMEOUT = 10.0

_TAG_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
_UPGRADE_HINT = [
    "一键安装渠道：重新运行 install.cmd 更新 CLI 并检查本体；确认后运行 "
    "install.cmd --update-root 才会替换市场根。",
    "pipx 渠道：pipx upgrade workbuddy-market；再运行 "
    "workbuddy-market root-update --market-root <市场根目录>。Git 工作区请用 git pull。",
]


def _release_fetch(url: str = LATEST_RELEASE_URL, timeout: float = SELFUPDATE_TIMEOUT) -> dict:
    """最新 Release 的唯一网络接缝。测试整体替换本函数。

    返回 GitHub /releases/latest 的 JSON（含 tag_name）；HTTP/网络错误
    原样上抛，由 check_for_update 统一翻译成人话。
    """
    req = urllib.request.Request(url, headers={
        "User-Agent": f"workbuddy-market/{_current_version()}",
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return _loads(resp.read())


def _current_version() -> str:
    from .version import MARKET_VERSION          # noqa: PLC0415 —— 晚绑定防环
    return MARKET_VERSION


def _loads(raw: bytes) -> dict:
    import json                                   # noqa: PLC0415
    return json.loads(raw.decode("utf-8"))


def parse_tag(tag: str) -> tuple | None:
    """``v2.36.0`` / ``2.36.0`` → (2, 36, 0)；形态不对 → None（不猜）。"""
    m = _TAG_RE.match(str(tag or "").strip())
    if not m:
        return None
    return tuple(int(x) for x in m.groups())


def compare_versions(a: str, b: str) -> int:
    """X.Y.Z 逐段比较：a>b → 1，a<b → -1，相等 → 0。

    段数不齐按缺省 0 补齐（2.36 == 2.36.0）；任一段非数字抛 ValueError
    （调用方保证来自 parse_tag，形态已验）。
    """
    pa = [int(x) for x in str(a).strip().split(".")]
    pb = [int(x) for x in str(b).strip().split(".")]
    n = max(len(pa), len(pb))
    pa += [0] * (n - len(pa))
    pb += [0] * (n - len(pb))
    return (pa > pb) - (pa < pb)


def check_for_update(current: str | None = None, fetch=_release_fetch) -> dict:
    """市场本体更新检查（自检 / API 共用入口）。

    返回 dict：
      · 正常：{current, latest, latestTag, updateAvailable, howToUpdate, checkedAt}
      · tag 形态不对：updateAvailable=None + error（如实说明拿到的是什么）
      · 网络失败：updateAvailable=None + error（人话 + 重试建议）
    绝不抛异常 —— 调用方（API / CLI）直接渲染。
    """
    cur = current if current is not None else _current_version()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        data = fetch()
    except Exception as exc:                      # noqa: BLE001 —— 统一人话出口
        return {"current": cur, "latest": None, "updateAvailable": None,
                "error": f"检查更新失败：连不上 GitHub（{exc}）。"
                         "这是网络问题 —— 请确认能访问 github.com"
                         "（需要代理时先开系统代理）后重试。",
                "howToUpdate": [], "checkedAt": now}
    tag = str((data or {}).get("tag_name") or "")
    latest = parse_tag(tag)
    if latest is None:
        return {"current": cur, "latest": None, "updateAvailable": None,
                "error": f"检查更新失败：最新 Release 的 tag 形态不对（{tag[:40]!r}，"
                         "期望 vX.Y.Z）。不猜 —— 请到 Releases 页人工确认。",
                "howToUpdate": [], "checkedAt": now}
    latest_str = ".".join(str(x) for x in latest)
    return {"current": cur, "latest": latest_str, "latestTag": tag,
            "updateAvailable": compare_versions(latest_str, cur) > 0,
            "howToUpdate": _UPGRADE_HINT, "checkedAt": now}
