"""GitHub 动态目录（v2.10 新增）—— 收录源的实时元数据 + 全网搜索。

参考 DSH 市场的分层：**精选目录给静态身份，动态数据由定时任务刷新**。
区别在于 DSH 用远端 CI 每天重建 plugins.json，本市场是本机服务，直接用
一个后台线程把这件事做了，不需要任何外部基础设施：

  · ``market.config.json`` 的 ``remoteSources`` 继续只承担**静态身份**
    （repo / 分类 / 描述 / 关键词）。stars / verifiedAt 从此只是
    「上次手工填写的快照」，展示层优先用本模块的实时值；
  · 动态元数据缓存在 ``STATE_HOME/catalog.json``（TTL 默认 24 小时），
    与 state / ownership 一样属于运行状态，不进 Git 仓库；
    按 provider-api.md 设计稿的口径：**易变数据永不写回配置文件**；
  · 全网搜索（/search/repositories）是实时的，只在服务进程内存里
    短缓存（120 秒），不落盘。

容错口径（本项目的老规矩：统计要诚实）：

  · 单个仓库拉取失败 → **保留旧值**，错误记进 ``errors``，下次再试；
  · 整轮全部失败 → **不更新 refreshedAt**（失败不算「刷新过」），
    自动刷新循环才会按 TTL 继续重试，而不是傻等 24 小时；
  · 缓存文件损坏 → 当作不存在（read_json 容错路径），不影响任何功能。

网络接缝只有一个：``_gh_request()``。自检通过 monkeypatch 这个名字，
离线测完全部逻辑（与 _scan 注入点同一套纪律）。
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from .config import load_config, validate_repo
from .errors import ConfigError
from .fsutil import atomic_write_text, read_json
from .logging import now_iso
from .paths import CATALOG_PATH
from .version import MARKET_VERSION

GH_API = "https://api.github.com"
GH_TIMEOUT = 10.0                   # 单次请求超时（秒）
CATALOG_TTL = 24 * 3600.0           # 目录元数据的保鲜期（秒）
SEARCH_LIMIT_DEFAULT = 8
SEARCH_LIMIT_MAX = 20
MAX_QUERY = 200                     # 搜索词长度上限
CATALOG_SCHEMA = 1


# ---------------------------------------------------------------- 接缝

def _gh_request(path: str, params: dict | None = None,
                timeout: float = GH_TIMEOUT):
    """GitHub API GET 的唯一入口。测试 monkeypatch 这个名字。

    urllib 默认走系统代理（Windows 注册表 / 环境变量都在覆盖范围内），
    对本机常见的「只在代理里能上 GitHub」的场景刚好是对的。
    """
    url = GH_API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "User-Agent": f"workbuddy-market/{MARKET_VERSION}",
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------- 校验

def validate_query(value, field: str = "q") -> str:
    """搜索词校验：非空字符串、去首尾空白、长度有限。API 层与内核共用。"""
    if not isinstance(value, str):
        raise ConfigError(f"{field} 必须是字符串，实际是 {type(value).__name__}。")
    q = value.strip()
    if not q:
        raise ConfigError(f"{field} 不能为空。")
    if len(q) > MAX_QUERY:
        raise ConfigError(f"{field} 过长（>{MAX_QUERY} 字符）。")
    return q


def normalize_repo_payload(payload: dict) -> dict:
    """GitHub /repos 或 /search items → 统一字段。坏 payload 尽量取到什么算什么。"""
    if not isinstance(payload, dict):
        raise ConfigError("GitHub 返回的仓库数据不是对象。")
    full = payload.get("full_name") or ""
    if not isinstance(full, str) or "/" not in full:
        raise ConfigError(f"GitHub 返回缺 full_name：{payload.get('id')!r}")
    topics = payload.get("topics")
    return {
        "repo": full,
        "stars": int(payload.get("stargazers_count") or 0),
        "pushedAt": (payload.get("pushed_at") or "")[:10],
        "description": payload.get("description") or "",
        "language": payload.get("language") or "",
        "homepage": payload.get("homepage") or "",
        "archived": bool(payload.get("archived")),
        "htmlUrl": payload.get("html_url") or "",
        "topics": topics if isinstance(topics, list) else [],
    }


# ---------------------------------------------------------------- 拉取

def fetch_meta(repo: str) -> dict:
    """单个仓库的实时元数据。网络错误原样上抛，由 refresh_catalog 兜。"""
    return normalize_repo_payload(_gh_request(f"/repos/{validate_repo(repo)}"))


def search_repos(query: str, limit: int = SEARCH_LIMIT_DEFAULT) -> list:
    """GitHub 全网搜索。只做展示与「一键安装」入口，安装仍走 ghpm 老路。"""
    q = validate_query(query)
    lim = max(1, min(int(limit), SEARCH_LIMIT_MAX))
    data = _gh_request("/search/repositories",
                       {"q": q, "per_page": lim, "order": "desc"})
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise ConfigError("GitHub 搜索返回缺 items 数组。")
    out = []
    for it in data["items"]:              # 先归一再截断：畸形条目不能占用名额
        if len(out) >= lim:
            break
        try:
            out.append(normalize_repo_payload(it))
        except ConfigError:
            continue                      # 单条畸形不拖垮整页结果
    return out


# ---------------------------------------------------------------- 缓存

def catalog_path():
    return CATALOG_PATH


def load_catalog() -> dict:
    """读目录缓存。**不可信状态文件**：形状不对就当不存在。"""
    data = read_json(CATALOG_PATH, {}) or {}
    if not isinstance(data, dict) or data.get("schema") != CATALOG_SCHEMA:
        return {}
    if not isinstance(data.get("repos"), dict):
        data["repos"] = {}
    if not isinstance(data.get("errors"), dict):
        data["errors"] = {}
    return data


def save_catalog(cat: dict) -> None:
    atomic_write_text(CATALOG_PATH,
                      json.dumps(cat, ensure_ascii=False, indent=2))


def _entry_fresh(entry: dict, now: float, max_age: float) -> bool:
    ts = entry.get("fetchedAtEpoch")
    return isinstance(ts, (int, float)) and (now - float(ts)) < max_age


def is_stale(cat: dict | None = None, now: float | None = None,
             max_age: float | None = None) -> bool:
    """整份目录是否过期（或根本没有）。自动刷新循环按它决定要不要动手。"""
    cat = load_catalog() if cat is None else cat
    max_age = CATALOG_TTL if max_age is None else float(max_age)
    now = time.time() if now is None else float(now)
    ts = cat.get("refreshedAtEpoch")
    if not isinstance(ts, (int, float)):
        return True
    return (now - float(ts)) >= max_age


def refresh_catalog(repos: list | None = None, force: bool = False,
                    max_age: float | None = None, now: float | None = None) -> dict:
    """刷新目录元数据。

    repos 缺省 = 配置里的全部 remoteSources。force=True 无视单条 TTL
    （手动刷新按钮用）；force=False 只拉过期的（自动循环用）。

    返回 ``{refreshedAt, fetched, skipped, failed, catalog}``。
    全部失败时 refreshedAt 沿用旧值 —— 「一单都没成」不能假装刷新过。
    """
    if repos is None:
        repos = [spec.get("repo")
                 for spec in load_config().get("remoteSources", [])
                 if isinstance(spec, dict) and spec.get("repo")]
    validated = []
    seen = set()
    for r in repos:
        v = validate_repo(r)
        if v.casefold() not in seen:      # 配置层已查重，这里只兜大小写变体
            seen.add(v.casefold())
            validated.append(v)

    cat = load_catalog()
    now = time.time() if now is None else float(now)
    max_age = CATALOG_TTL if max_age is None else float(max_age)
    out_repos = dict(cat.get("repos") or {})
    errors = dict(cat.get("errors") or {})
    fetched = failed = skipped = 0

    for repo in validated:
        old = out_repos.get(repo)
        if old is None:                   # 大小写不同的旧条目也算同一家
            old = next((e for k, e in out_repos.items()
                        if k.casefold() == repo.casefold()), None)
        if not force and old is not None and _entry_fresh(old, now, max_age):
            skipped += 1
            continue
        try:
            entry = fetch_meta(repo)
            entry["fetchedAtEpoch"] = now
            for k in [k for k in out_repos if k.casefold() == repo.casefold()]:
                del out_repos[k]
            for k in [k for k in errors if k.casefold() == repo.casefold()]:
                del errors[k]
            out_repos[repo] = entry
            fetched += 1
        except Exception as exc:          # noqa: BLE001 —— 网络/HTTP 什么都有可能
            failed += 1
            errors[repo] = f"{type(exc).__name__}: {exc}"[:300]

    all_failed = fetched == 0 and failed > 0
    if not fetched and not failed:
        # 全部跳过（缓存都还新鲜）：不动盘，也不假装刷新过 —— 原样返回现有目录
        return {"refreshedAt": cat.get("refreshedAt", ""),
                "fetched": 0, "skipped": skipped, "failed": 0,
                "catalog": cat, "noop": True}
    new_cat = {
        "schema": CATALOG_SCHEMA,
        # 一单未成不算刷新过：保住旧的时间戳，自动循环才会在下个检查点重试
        "refreshedAt": (cat.get("refreshedAt") or "") if all_failed else now_iso(),
        "refreshedAtEpoch": (cat.get("refreshedAtEpoch") or 0) if all_failed else now,
        "repos": out_repos,
        "errors": errors,
    }
    save_catalog(new_cat)
    return {
        "refreshedAt": new_cat["refreshedAt"],
        "fetched": fetched,
        "skipped": skipped,
        "failed": failed,
        "catalog": new_cat,
    }
