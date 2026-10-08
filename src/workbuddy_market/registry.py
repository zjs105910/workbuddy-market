"""社区注册表（v2.11 新增）—— DSH 市场那层「registry 仓库」的本机实现。

DSH 市场的分层是：**精选目录 = 一个静态 GitHub 仓库（plugins.json），
CI 每天重建动态字段，市场端在线拉取、点了就装**。本市场 v2.10 已经有
「按条目 TTL 的动态目录」（catalog.py，本机线程自己刷），这一轮补上另一半：

  · 注册表本体就是本仓库里的 ``registry/plugins.json``（静态提交，人工
    审核收录；stars / pushedAt / latestSha 由 CI 每天重建——见
    ``scripts/build_registry.py`` 与 ``.github/workflows/registry.yml``）；
  · 市场端按 TTL 在线拉取它，网页多出一个「社区目录」区块，展示的是
    **别人仓库里收录的 WorkBuddy 插件**，与本机 market.config.json 的
    remoteSources 完全解耦——装/不装都不写配置文件。

拉取路线（对国内网络诚实：raw 域名经常超时，所以留了三条路 + 本地兜底）：

  1. ``WBM_REGISTRY_URL`` 环境变量（测试与镜像加速用，整条 URL）；
  2. raw.githubusercontent.com（首选，无额外开销）；
  3. api.github.com 的 contents 接口（``Accept: application/vnd.github.raw``，
     返回的响应体就是文件原文，不走 base64）；
  4. 本仓库自带的 ``registry/plugins.json``（离线 / 断网兜底 —— 本仓库
     本身就是注册表，clone 下来就有一份）。

缓存与容错口径与 catalog.py 完全一致（老规矩）：

  · 缓存在 ``STATE_HOME/registry.json``（TTL 6 小时），属运行状态，不进 Git；
  · **不可信状态文件**：形状不对当不存在；
  · 在线三条路全挂 → 退回缓存（哪怕过期）；连缓存都没有 → 退回本地副本；
    每一级的 ``source`` 字段都会如实标注数据从哪来，网页据此显示
    「离线副本」之类的角标 —— 绝不把兜底数据假装成最新拉取。

网络接缝只有一个：``_registry_http_get(url, headers, timeout)``。自检
monkeypatch 这个名字离线测完全部逻辑（与 _gh_request 同一套纪律）。
"""
from __future__ import annotations

import json
import os
import time
import urllib.request

from .config import validate_repo
from .errors import ConfigError
from .fsutil import atomic_write_text, read_json
from .logging import now_iso
from .paths import MARKET_ROOT, REGISTRY_PATH
from .version import MARKET_VERSION

REGISTRY_REPO = "zjs105910/workbuddy-market"
REGISTRY_BRANCH = "main"
REGISTRY_FILENAME = "registry/plugins.json"
REGISTRY_TTL = 6 * 3600.0           # 注册表缓存保鲜期（秒）
REGISTRY_TIMEOUT = 10.0             # 单次请求超时（秒）
REGISTRY_SCHEMA = 1
MAX_REGISTRY_ENTRIES = 500          # 注册表条目数上限（防一个坏文件撑爆内存）

REGISTRY_RAW_URL = ("https://raw.githubusercontent.com/"
                    f"{REGISTRY_REPO}/{REGISTRY_BRANCH}/{REGISTRY_FILENAME}")
REGISTRY_API_URL = (f"https://api.github.com/repos/{REGISTRY_REPO}"
                    f"/contents/{REGISTRY_FILENAME}?ref={REGISTRY_BRANCH}")
ENV_REGISTRY_URL = "WBM_REGISTRY_URL"


# ---------------------------------------------------------------- 接缝

def _registry_http_get(url: str, headers: dict | None = None,
                       timeout: float = REGISTRY_TIMEOUT) -> bytes:
    """注册表 HTTP GET 的唯一入口。测试 monkeypatch 这个名字。

    与 catalog._gh_request 分开：注册表首选 raw.githubusercontent.com，
    URL 不在 api.github.com 上，套同一个接缝反而别扭。urllib 默认走
    系统代理，对本机「只在代理里能上 GitHub」的场景刚好是对的。
    """
    req = urllib.request.Request(url, headers={
        "User-Agent": f"workbuddy-market/{MARKET_VERSION}",
        **(headers or {}),
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def registry_routes() -> list:
    """按优先级排列的拉取路线。每条是 ``(source, url, headers)``。

    headers 为 None 表示响应体直接是 JSON 原文；api 路线要带 raw accept
    头（否则 contents 返回的是 base64 包了一层的 JSON 信封）。
    """
    routes = []
    env_url = (os.environ.get(ENV_REGISTRY_URL) or "").strip()
    if env_url:
        routes.append(("env-override", env_url, None))
    routes.append(("raw.githubusercontent.com", REGISTRY_RAW_URL, None))
    routes.append(("api.github.com", REGISTRY_API_URL,
                   {"Accept": "application/vnd.github.raw"}))
    return routes


def local_registry_file():
    """本仓库自带的注册表副本（离线兜底）。clone 下来就有一份。"""
    return MARKET_ROOT / REGISTRY_FILENAME


# ---------------------------------------------------------------- 解析

def _clean_text(v, limit: int = 400) -> str:
    if not isinstance(v, str):
        return ""
    return v.strip()[:limit]


def parse_registry(data) -> dict:
    """注册表原文 → ``{"plugins": [...], "updatedAt": ...}``。

    **输入边界只留一处**（约定 14）：repo 逐条过 validate_repo()；
    单条畸形跳过（记数，不拖垮整份）；同 repo 大小写变体只留第一条；
    条目数超上限截断。schema 不对 / 顶层不是对象 → ConfigError（调用方
    换下一条路线）。
    """
    if isinstance(data, (bytes, bytearray)):
        data = bytes(data).decode("utf-8", "replace")
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except ValueError as exc:
            raise ConfigError(f"注册表不是合法 JSON：{exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError("注册表顶层必须是 JSON 对象。")
    if data.get("schema") != REGISTRY_SCHEMA:
        raise ConfigError(f"注册表 schema 不支持：{data.get('schema')!r}")
    items = data.get("plugins")
    if not isinstance(items, list):
        raise ConfigError("注册表缺 plugins 数组。")

    out, seen, skipped = [], set(), 0
    for it in items:
        if len(out) >= MAX_REGISTRY_ENTRIES:
            skipped += len(items) - len(out) - skipped
            break
        if not isinstance(it, dict):
            skipped += 1
            continue
        try:
            repo = validate_repo(it.get("repo"), "repo")
        except ConfigError:
            skipped += 1
            continue
        key = repo.casefold()
        if key in seen:
            skipped += 1
            continue
        seen.add(key)
        entry = {
            "repo": repo,
            "displayName": _clean_text(it.get("displayName")) or repo.split("/", 1)[1],
            "displayNameEn": _clean_text(it.get("displayNameEn")),
            "category": _clean_text(it.get("category"), 40) or "未分类",
            "description": _clean_text(it.get("description")),
            "descriptionEn": _clean_text(it.get("descriptionEn")),
            "keywords": [ _clean_text(k, 40) for k in it["keywords"]
                          if isinstance(k, str) and k.strip() ][:12]
                         if isinstance(it.get("keywords"), list) else [],
            "homepage": _clean_text(it.get("homepage"), 300),
            "addedAt": _clean_text(it.get("addedAt"), 10),
        }
        # 信任分级（v2.12）：official=官方收录 / reviewed=社区精选（人工审核）
        # / external=未审核。静态字段，只许人工维护；值不认识就降为 reviewed。
        trust = _clean_text(it.get("trust"), 16) or "reviewed"
        entry["trust"] = trust if trust in ("official", "reviewed", "external") else "reviewed"
        # 供应链字段（v2.12，可选增量，schema 保持 1）：审核时固定下来的来源
        # commit 与许可证。sourceCommit 是「审核时看的是哪一份」的凭证，
        # 安装端拿它和 CI 刷出来的 latestSha 比对，检测上游漂移。
        lic = _clean_text(it.get("license"), 64)
        if lic:
            entry["license"] = lic
        sc = _clean_text(it.get("sourceCommit"), 64)
        if sc:
            entry["sourceCommit"] = sc
        rv = it.get("review")
        if isinstance(rv, dict):
            review = {k: _clean_text(rv.get(k), 40)
                      for k in ("status", "reviewedAt", "method")}
            review = {k: v for k, v in review.items() if v}
            if review:
                entry["review"] = review
        # 动态字段：CI 每天重建；类型不对就当没有，绝不让坏数据进前端
        stars = it.get("stars")
        if isinstance(stars, int) and not isinstance(stars, bool) and stars >= 0:
            entry["stars"] = stars
        for f in ("pushedAt", "latestSha", "refreshedAt"):
            v = _clean_text(it.get(f), 64)
            if v:
                entry[f] = v
        out.append(entry)

    return {"plugins": out,
            "updatedAt": _clean_text(data.get("updatedAt"), 32),
            "skipped": skipped}


# ---------------------------------------------------------------- 缓存

def registry_path():
    return REGISTRY_PATH


def load_registry_cache() -> dict:
    """读注册表缓存。**不可信状态文件**：形状不对当不存在。"""
    data = read_json(REGISTRY_PATH, {}) or {}
    if not isinstance(data, dict) or data.get("schema") != REGISTRY_SCHEMA:
        return {}
    if not isinstance(data.get("plugins"), list):
        return {}
    return data


def save_registry_cache(cache: dict) -> None:
    atomic_write_text(REGISTRY_PATH,
                      json.dumps(cache, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------- 拉取

def _read_local() -> dict:
    """本地副本兜底。读不到 / 解析不了 → ConfigError（让调用方如实报错）。"""
    p = local_registry_file()
    try:
        raw = p.read_bytes()
    except OSError as exc:
        raise ConfigError(f"本地注册表副本读不到：{exc}") from exc
    return parse_registry(raw)


def get_registry(force: bool = False, now: float | None = None) -> dict:
    """取注册表：force=True 无视缓存 TTL；默认过期（6h）才联网。

    返回 ``{plugins, updatedAt, fetchedAt, fetchedAtEpoch, stale, source,
    skipped, fetched}``。``source`` 如实标注来源（env-override /
    raw.githubusercontent.com / api.github.com / local-repo / cache），
    「离线兜底」绝不能假装成「刚从 GitHub 拉的」。
    """
    now = time.time() if now is None else float(now)
    cache = load_registry_cache()
    cache_epoch = cache.get("fetchedAtEpoch")
    cache_fresh = (isinstance(cache_epoch, (int, float))
                   and (now - float(cache_epoch)) < REGISTRY_TTL)
    if not force and cache_fresh:
        return {"plugins": cache["plugins"],
                "updatedAt": cache.get("updatedAt", ""),
                "fetchedAt": cache.get("fetchedAt", ""),
                "fetchedAtEpoch": cache_epoch,
                "stale": False, "source": "cache",
                "skipped": cache.get("skipped", 0), "fetched": False}

    errors = []
    for source, url, headers in registry_routes():
        try:
            raw = _registry_http_get(url, headers=headers)
            parsed = parse_registry(raw)
            fresh = {"schema": REGISTRY_SCHEMA,
                     "fetchedAt": now_iso(),
                     "fetchedAtEpoch": now,
                     "source": source,
                     "updatedAt": parsed["updatedAt"],
                     "skipped": parsed["skipped"],
                     "plugins": parsed["plugins"]}
            save_registry_cache(fresh)
            fresh.update(stale=False, fetched=True)
            return fresh
        except Exception as exc:      # noqa: BLE001 —— 网络 / HTTP / 解析都换下一条路
            errors.append(f"{source}: {type(exc).__name__}: {exc}"[:200])

    # 在线全挂：退回缓存（哪怕过期）→ 再退本地副本。source 如实标注。
    if cache:
        return {"plugins": cache["plugins"],
                "updatedAt": cache.get("updatedAt", ""),
                "fetchedAt": cache.get("fetchedAt", ""),
                "fetchedAtEpoch": cache_epoch,
                "stale": not cache_fresh, "source": "cache",
                "skipped": cache.get("skipped", 0), "fetched": False,
                "errors": errors}
    local = _read_local()
    local.update(stale=True, source="local-repo", fetched=False,
                 fetchedAt="", fetchedAtEpoch=0, errors=errors)
    return local
