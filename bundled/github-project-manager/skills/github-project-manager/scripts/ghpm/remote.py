# -*- coding: utf-8 -*-
"""远程信息：仓库元信息、目录索引、ZIP 下载，以及三层回退。

v3.2 把 api.github.com / ungh.cc / atom feed 的 try/except 全塞在
``_repo_info_remote`` 一个函数里，分支随每加一个源而膨胀。v4 拆成：

    GitHubApiProvider  ── api.github.com（可配 GITHUB_TOKEN，能拿 branch/stars/sha）
    UnghProvider       ── ungh.cc（只读代理，不消耗本机额度，**没有 sha**）
    AtomProvider       ── commits/<branch>.atom（不要额度，只能拿最新 sha）

由 ``RemoteResolver`` 负责顺序与合并。以后加 Gitee / GitLab / 企业 GitHub
只要再写一个 Provider，不用动这里的回退逻辑。

**回退顺序是踩过坑的，不能改**：ungh 必须在 atom 之前。限流场景下 API 直接
403，branch 还停在默认值 main，此时先拉 atom 会去请求 ``commits/main.atom`` ——
默认分支不是 main 的仓库必然失败，而后面 ungh 修正了 branch 也不会重拉。
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

from . import config
from .errors import (E_NETWORK, E_NOT_FOUND, E_TIMEOUT, BadArchiveError,  # noqa: F401
                     HttpError)
from .models import RepoInfo
from .util import atomic_write_bytes, run, safe_key

TIMEOUT = config.TIMEOUT
MIB = config.MIB


# ---------- 低层 HTTP（统一走 curl） ----------

def _http_code(out: str) -> str:
    """从 curl -w 的输出尾部取状态码"""
    if "__HTTP__" in (out or ""):
        return out.rsplit("__HTTP__", 1)[1].strip()
    return ""


def _looks_like_bad_flag(stderr: str) -> bool:
    s = (stderr or "").lower()
    return ("retry-all-errors" in s or "unrecognized" in s
            or "unknown option" in s or "is not recognized" in s)


def _proxy_args(url: str) -> list:
    """给 curl 的显式代理参数（无需代理时返回 []）。

    · 环境变量已给代理 → curl 自己会认，不加（避免双重指定）；
    · 仅主源 / GitHub API（*.github.com）注入 Windows 系统代理 ——
      国内镜像本来就是给无代理链路准备的，走代理反而可能更慢；
    · 环境变量 GHPM_NO_SYS_PROXY=1 可整体关闭注入（诊断用）。
    """
    if any(os.environ.get(v) for v in
           ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "all_proxy")):
        return []
    if os.environ.get("GHPM_NO_SYS_PROXY"):
        return []
    if "github.com" not in urlparse(url).netloc:
        return []
    px = config.win_system_proxy()
    return ["-x", px] if px else []


def curl_json(url: str):
    """带状态码的 GET。GitHub 的 404 会返回合法 JSON，只看 returncode 会漏判。
    未鉴权只有 60 次/小时，配了 GITHUB_TOKEN 是 5000 次/小时。"""
    cmd = ["curl", "-sSL", "--max-time", "60", "-w", "\n__HTTP__%{http_code}",
           "-H", "Accept: application/vnd.github+json"]
    if config.GH_TOKEN and "api.github.com" in url:
        cmd += ["-H", "Authorization: Bearer %s" % config.GH_TOKEN]
    cmd += _proxy_args(url)
    cmd.append(url)
    r = run(cmd)
    out, code = r.stdout, ""
    if "__HTTP__" in out:
        out, code = out.rsplit("__HTTP__", 1)
        code = code.strip()
    if r.returncode != 0 or not out.strip():
        raise RuntimeError("请求失败 %s (http=%s): %s" % (url, code or "?", r.stderr.strip()[:160]))
    if code.isdigit() and int(code) >= 400:
        raise HttpError(int(code), out.strip(), url)
    try:
        return json.loads(out)
    except Exception:
        raise RuntimeError("响应不是合法 JSON（http=%s）: %s" % (code or "?", out[:120]))


def classify_net_error(e) -> tuple:
    """把网络异常归因成 (错误码, 人话提示)，仿 DSH 的错误归因"""
    s = str(e)
    low = s.lower()
    if isinstance(e, HttpError):
        if e.status == 404:
            return E_NOT_FOUND, "仓库不存在或已私有化。检查 owner/repo 拼写。"
        if e.status == 403 and ("rate limit" in low or "rate limit" in e.body.lower()):
            return E_NETWORK, "GitHub API 限流了（未鉴权 60 次/小时）。等一会儿再试，或配 GITHUB_TOKEN。"
        if e.status == 401:
            return E_NETWORK, "鉴权失败。检查 token。"
        if e.status >= 500:
            return E_NETWORK, "GitHub 服务端出错，稍后重试即可。"
        return E_NETWORK, "请求被拒绝（HTTP %d）。" % e.status
    if "timed out" in low or "timeout" in low:
        return E_TIMEOUT, "网络超时。代理可能不稳定，重试通常能过。"
    if "could not resolve" in low or "couldn't connect" in low or "proxy" in low:
        return E_NETWORK, "连不上网络。检查代理设置（本机需走 http_proxy/https_proxy）。"
    return E_NETWORK, "网络请求失败，可稍后重试。"


def curl_download(url: str, dest: Path) -> None:
    """下载到 dest。必须看 HTTP 状态码：curl -sSL 对 404 页面也返回 0，
    只看 returncode 会把「下到一张错误页」当成成功，最后抛个莫名其妙的
    「不是有效的 zip 包」。

    v4.1 下载提速（2026-10-22 用户实测「下载太慢」）：
    · 主源（codeload.github.com）用更快的失败参数 —— connect-timeout 5
      + retry 1。直连必挂的网络上别干等 30 秒，反正后面有镜像兜底；
      注入 Windows 系统代理后主源多半直接就通了（见 _proxy_args）。
    · 镜像保持 connect-timeout 10 + retry 2（镜像本身可达，慢点没关系）。
    """
    main_source = "github.com" in urlparse(url).netloc
    base = ["curl", "-sSL", "--max-time", TIMEOUT,
            "--connect-timeout", "5" if main_source else "10",
            "-w", "\n__HTTP__%{http_code}", "-o", str(dest)]
    base += _proxy_args(url)
    r = run(base + ["--retry", "1" if main_source else "2",
                    "--retry-all-errors", url])
    if r.returncode != 0 and _looks_like_bad_flag(r.stderr):
        # 老版本 curl（< 7.71）不认 --retry-all-errors，降级重跑
        r = run(base + ["--retry", "1" if main_source else "2", url])
    code = _http_code(r.stdout)
    if r.returncode != 0:
        raise RuntimeError("下载失败 %s (http=%s): %s"
                           % (url, code or "?", r.stderr.strip()[:200]))
    if code.isdigit() and not (200 <= int(code) < 300):
        raise HttpError(int(code), "", url)
    if not dest.exists() or dest.stat().st_size == 0:
        raise RuntimeError("下载为空 %s (http=%s)" % (url, code or "?"))


# ---------- 仓库地址解析 ----------

def parse_repo(text: str) -> str:
    """把用户输入解析成 owner/repo。

    v3.1 用一条正则 search，`https://github.com/foo/bar/xxxx` 会被截成 foo/bar、
    `?query` / `#frag` 会被一起吞进去。CLI 行为不确定，用户输错却装上了别的仓库
    是很难排查的问题。这里改成 urlparse 严格校验：https + github.com + 恰好两段路径。
    """
    raw = (text or "").strip()
    if not raw:
        raise ValueError("仓库地址为空")

    # 裸的 owner/repo（也可以是 git@github.com:owner/repo）
    if raw.startswith("git@github.com:"):
        rest = raw.split(":", 1)[1]
        raw = re.sub(r"\.git$", "", rest.strip())
        m = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9_.-]*)/([A-Za-z0-9][A-Za-z0-9_.-]*)", raw)
        if m:
            return "%s/%s" % (m.group(1), m.group(2))
        raise ValueError("无法解析 SSH 形式的仓库地址: %s" % text)
    raw = re.sub(r"\.git$", "", raw)
    raw = raw.rstrip("/")

    m = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9_.-]*)/([A-Za-z0-9][A-Za-z0-9_.-]*)", raw)
    if m:
        return "%s/%s" % (m.group(1), m.group(2))

    if "://" not in raw:
        raise ValueError("无法解析仓库地址: %s（应为 owner/repo 或 https://github.com/owner/repo）"
                         % text)

    u = urlparse(raw)
    if u.scheme != "https":
        raise ValueError("只支持 https 地址: %s" % text)
    host = (u.hostname or "").lower()
    if host not in ("github.com", "www.github.com"):
        raise ValueError("只支持 github.com 的仓库: %s" % text)
    if u.query or u.fragment:
        raise ValueError("仓库地址不应带查询参数或锚点: %s" % text)
    parts = [p for p in u.path.split("/") if p]
    if len(parts) != 2:
        raise ValueError("仓库地址必须是 https://github.com/<owner>/<repo>: %s" % text)
    owner, name = parts
    if not (config.OWNER_RE.match(owner) and config.OWNER_RE.match(name)):
        raise ValueError("owner/repo 含非法字符: %s" % text)
    return "%s/%s" % (owner, name)


# ---------- Provider ----------

class RemoteProvider:
    """远程信息源的统一接口。

    只实现自己支持的子集：UnghProvider 没有 sha、AtomProvider 只能拿 sha，
    所以 ``info()`` 允许返回 None / 空字段，由 Resolver 合并。
    """

    name = "provider"

    def info(self, repo: str) -> RepoInfo | None:
        """仓库元信息。抛异常表示这个源不可用。"""
        raise NotImplementedError

    def tree(self, repo: str, branch: str):
        """目录索引，返回 (paths, truncated) 或 None。"""
        return None


def ungh_meta(repo: str):
    """ungh.cc 的元信息（GitHub 只读代理，不消耗本机 API 额度）。失败返回 None。"""
    try:
        d = curl_json("https://ungh.cc/repos/%s" % repo)
    except Exception:
        return None
    if not isinstance(d, dict) or d.get("error"):
        return None
    r = d.get("repo") or {}
    return {
        "branch": r.get("defaultBranch") or "main",
        "stars": r.get("stars", 0),
        "desc": (r.get("description") or "")[:100],
        "pushed_at": r.get("pushedAt", ""),
    }


def atom_latest(repo: str, branch: str):
    """commits atom feed。不需要 API 额度，能拿到最新 commit 的 sha。
    GitHub API 限流时靠它仍能判断「有没有更新」。"""
    r = run(["curl", "-sSL", "--max-time", "60",
             "https://github.com/%s/commits/%s.atom" % (repo, branch)])
    if r.returncode != 0 or not r.stdout:
        return None
    m = re.search(r"Grit::Commit/([0-9a-f]{7,40})", r.stdout)
    if not m:
        return None
    t = re.search(r"<entry>.*?<title>(.*?)</title>", r.stdout, re.S)
    msg = ""
    if t:
        msg = re.sub(r"<!\[CDATA\[|\]\]>", "", t.group(1)).strip().split("\n")[0][:70]
    return m.group(1), msg


def ungh_files(repo: str, branch: str):
    """ungh.cc 的文件列表（不消耗本机 API 额度）"""
    try:
        d = curl_json("https://ungh.cc/repos/%s/files/%s" % (repo, branch))
    except Exception:
        return None
    if not isinstance(d, dict) or d.get("error"):
        return None
    return [f.get("path", "") for f in (d.get("files") or [])]


class GitHubApiProvider(RemoteProvider):
    """api.github.com。唯一能一次拿到 branch/stars/desc/sha/最新提交信息的源。"""

    name = "api.github.com"

    def info(self, repo: str) -> RepoInfo:
        info = RepoInfo(repo=repo)
        meta = curl_json("https://api.github.com/repos/%s" % repo)
        info.branch = meta.get("default_branch") or "main"
        info.stars = meta.get("stargazers_count", 0)
        info.desc = (meta.get("description") or "")[:100]
        info.pushed_at = meta.get("pushed_at", "")
        try:
            c = curl_json("https://api.github.com/repos/%s/commits?per_page=1&sha=%s"
                          % (repo, info.branch))
            if c:
                info.sha = c[0]["sha"]
                info.msg = (c[0].get("commit", {}).get("message", "") or "").split("\n")[0][:70]
        except Exception:
            pass          # 拿不到 sha 不算主源失败，后面还有 atom 兜底
        return info

    def tree(self, repo: str, branch: str):
        tree = curl_json("https://api.github.com/repos/%s/git/trees/%s?recursive=1"
                         % (repo, branch))
        paths = [it.get("path", "") for it in tree.get("tree", [])]
        return paths, bool(tree.get("truncated"))


class UnghProvider(RemoteProvider):
    """ungh.cc：备用元信息源。**没有 sha**，只用来补 branch/stars/desc。"""

    name = "ungh.cc"

    def info(self, repo: str) -> RepoInfo | None:
        u = ungh_meta(repo)
        if not u:
            return None
        info = RepoInfo(repo=repo)
        info.branch = u.get("branch") or "main"
        info.stars = u.get("stars", 0)
        info.desc = u.get("desc", "")
        info.pushed_at = u.get("pushed_at", "")
        return info

    def tree(self, repo: str, branch: str):
        paths = ungh_files(repo, branch)
        return (paths, False) if paths is not None else None


class AtomProvider:
    """commits atom feed：只提供最新 sha，不需要 API 额度。

    不是完整的 RemoteProvider（不能拿元信息），所以单列一类，
    由 Resolver 在「元信息有了但没有 sha」时调用 —— 限流时全靠它。
    """

    name = "commits.atom"

    def latest(self, repo: str, branch: str):
        return atom_latest(repo, branch)


class RemoteResolver:
    """按顺序回退的远程解析器。

    providers    —— 元信息源，按顺序试到第一个成功的；后续源只补空字段
    sha_fallback —— 元信息里没有 sha 时的兜底（atom feed）
    """

    def __init__(self, providers=None, sha_fallback=None):
        self.providers = list(providers) if providers is not None else [
            GitHubApiProvider(), UnghProvider()]
        self.sha_fallback = sha_fallback or AtomProvider()
        self.tree_providers = list(providers) if providers is not None else [
            GitHubApiProvider(), UnghProvider()]

    def info(self, repo: str) -> RepoInfo:
        """主源失败时不抛，而是尽量用备用源拼出能用的信息；全都拿不到 sha 才抛。

        只在**前一个源失败**时才去打扰下一个源：GitHub API 成功时（哪怕 stars=0）
        不再多打一次 ungh，否则每个仓库都会白白多一个 HTTP 请求。
        """
        info = RepoInfo(repo=repo)
        err = None
        for provider in self.providers:
            try:
                got = provider.info(repo)
            except Exception as e:
                err = err or e
                continue
            if got is None:
                continue
            info.merge_fallback(got.to_dict())
            break
        if not info.sha:
            info.sha, info.msg = self._sha_from_feed(repo, info.branch) or ("", "")
        info.fill_short_sha()
        if err is not None and not info.sha:
            raise err
        return info

    def _sha_from_feed(self, repo: str, branch: str):
        """atom 兜底。branch 不对时再试 master / main —— 备用源没能修正 branch 时
        （限流场景很常见），只有把几种默认分支都试一遍才拿得到 sha。"""
        for b in (branch, "master", "main"):
            if not b:
                continue
            a = self.sha_fallback.latest(repo, b)
            if a:
                return a
        return None

    def tree(self, repo: str, branch: str):
        """目录索引。Git Trees 标记 truncated 时不把「不完整目录树」当完整事实，
        优先回退 ungh；两者都失败才退回到那份被截断的（并标 complete=False）。"""
        partial: list | None = None
        mode = "tree"
        complete = True
        tree_size = 0
        providers = self.tree_providers
        if providers:
            try:
                got = providers[0].tree(repo, branch)
            except Exception:
                got = None
                mode = "ungh"
            if got:
                paths, truncated = got
                tree_size = len(paths)
                if not truncated:
                    return paths, tree_size, "tree", True
                partial = paths
                complete = False
                mode = "tree-truncated"
        for provider in providers[1:]:
            try:
                got = provider.tree(repo, branch)
            except Exception:
                continue
            if got:
                paths, _ = got
                return paths, len(paths), "ungh", True
        if partial is not None:
            return partial, tree_size, mode, complete
        return None, 0, "unavailable", False


DEFAULT_RESOLVER = RemoteResolver()


# ---------- 缓存 ----------

def _cache_file(repo: str) -> Path:
    return config.CACHE / ("repo-%s.json" % safe_key(repo))


_cache_pruned_at = 0.0
_cache_prune_lock = threading.Lock()


def _cache_get(repo: str, ttl: float):
    """命中且未过期才用。只缓存「确实拿到了 sha」的结果，
    免得把一次限流后的残缺信息当成事实。"""
    if ttl <= 0:
        return None
    f = _cache_file(repo)
    try:
        if not f.exists():
            return None
        if time.time() - f.stat().st_mtime > ttl:
            return None
        d = json.loads(f.read_text(encoding="utf-8"))
        if isinstance(d, dict) and str(d.get("repo", "")).lower() == repo.lower() and d.get("sha"):
            return RepoInfo.from_dict(d)
    except Exception:
        pass
    return None


def _cache_put(repo: str, info: RepoInfo) -> None:
    """写入缓存。

    容量清理从 v3.1 的「每次写都 glob+sort 全目录」改成低频触发：
    每次 put 都遍历一遍，在 check --all 并发拉取时会互相踩，也白费 IO。
    现在按「文件数超阈值」或「距上次清理超过 5 分钟」才扫。
    """
    global _cache_pruned_at
    try:
        config.CACHE.mkdir(parents=True, exist_ok=True)
        payload = info.to_dict()
        payload["repo"] = repo
        payload["fetched_at"] = time.time()
        atomic_write_bytes(_cache_file(repo), json.dumps(payload, ensure_ascii=False))
        now_t = time.time()
        # 并发时只让一个线程去清，其余直接跳过
        if _cache_prune_lock.acquire(blocking=False):
            try:
                if len(os.listdir(config.CACHE)) <= config.CACHE_MAX_FILES and \
                        now_t - _cache_pruned_at < 300:
                    return
                files = sorted(config.CACHE.glob("repo-*.json"),
                               key=lambda p: p.stat().st_mtime)
                for old in files[:-config.CACHE_MAX_FILES]:
                    try:
                        old.unlink()
                    except Exception:
                        pass
                # 顺手清掉异常退出留下的临时文件（唯一命名，不会误删别人的）
                for junk in config.CACHE.glob("*.tmp"):
                    try:
                        if now_t - junk.stat().st_mtime > 3600:
                            junk.unlink()
                    except Exception:
                        pass
                _cache_pruned_at = now_t
            finally:
                _cache_prune_lock.release()
    except Exception:
        pass


def cache_clear() -> int:
    """清空远程信息缓存，返回删掉的文件数。doctor / 排障用。"""
    n = 0
    try:
        for f in config.CACHE.glob("repo-*.json"):
            try:
                f.unlink()
                n += 1
            except Exception:
                pass
    except Exception:
        pass
    return n


# ---------- 对外入口 ----------

def repo_info(repo: str, ttl: float = 0) -> RepoInfo:
    """拿仓库元信息。主源 api.github.com，失败时回退 ungh.cc / atom feed。

    ttl>0 时先读本地缓存（只读命令用，默认 60 秒）；装/更新必须 ttl=0 拿最新 sha。
    回退拿不到 stars 时返回 0（调用方应沿用旧值，别把 ★7277 抹成 0）。
    """
    cached = _cache_get(repo, ttl)
    if cached:
        return cached
    info = DEFAULT_RESOLVER.info(repo)
    if info.sha:
        _cache_put(repo, info)
    return info


def repo_skill_index(repo: str, branch: str) -> dict | None:
    """读取远端目录索引并返回 skill 与检查元数据。"""
    paths, tree_size, mode, complete = DEFAULT_RESOLVER.tree(repo, branch)
    if paths is None:
        return None
    from .discovery import match_skill_path
    out = {}
    top_skill = False
    for path in paths:
        if path == "SKILL.md":
            top_skill = True
        name = match_skill_path(path.split("/"))
        if name and name not in out:
            out[name] = path
    if not out and top_skill:
        out[repo.split("/")[-1]] = "SKILL.md"
    return {"skills": out, "tree_size": tree_size, "inspection_mode": mode,
            "complete": complete}


def repo_skill_names(repo: str, branch: str):
    """兼容旧调用：只返回 {skill名: 仓库内路径}。"""
    result = repo_skill_index(repo, branch)
    return result["skills"] if result is not None else None


def fetch_repo_infos(repos, ttl: float = 0, label: str = "检查",
                     progress=None) -> tuple:
    """并发拉多个仓库的元信息。返回 ({repo_lower: RepoInfo}, {repo_lower: 异常})。

    v3.1 是纯串行 for 循环：100 个仓库 × 每个 0.5~2 秒 = 50~200 秒，
    而这些 GitHub 查询彼此完全独立。并发之后基本等于最慢的那一个。

    worker 数封顶 16（FETCH_WORKERS）：目标是把串行等待压下去，
    不是把 GitHub API 打爆 —— 匿名额度只有 60 次/小时，
    32~64 并发只会更快触发限流，然后整批变成 E_NETWORK。
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    repos = [r for r in dict.fromkeys(repos) if r]
    if not repos:
        return {}, {}
    results: dict = {}
    errors: dict = {}
    if len(repos) == 1:
        r = repos[0]
        try:
            results[r.lower()] = repo_info(r, ttl=ttl)
        except Exception as e:
            errors[r.lower()] = e
        if progress:
            progress(1, 1, repos[0])
        return results, errors

    workers = min(config.fetch_workers(), len(repos))
    done = 0
    total = len(repos)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(repo_info, r, ttl): r for r in repos}
        # 按完成顺序收割，进度才准确（一个慢请求不该卡住整批的进度显示）
        for fut in as_completed(futures):
            r = futures[fut]
            try:
                results[r.lower()] = fut.result()
            except Exception as e:
                errors[r.lower()] = e
            done += 1
            if progress:
                progress(done, total, r)
    return results, errors


# ---------- ZIP 下载（多镜像回退） ----------

def _load_last_good_source() -> str:
    """上次成功用过的镜像前缀（"" = 没有 / 主源成功 / 读失败）。"""
    try:
        return Path(config.LAST_SOURCE_PATH).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _save_last_good_source(prefix: str) -> None:
    from .util import atomic_write_bytes
    try:
        atomic_write_bytes(Path(config.LAST_SOURCE_PATH), prefix)
    except Exception:
        pass      # 记忆写失败不影响安装，下次最多多试一个慢镜像


def download_repo_zip(repo: str, branch: str, dest: Path, on_attempt=None,
                      validate=None) -> None:
    """按 MIRROR_PREFIXES 依次尝试下载 codeload ZIP 到 dest。

    主源永远排第一；每个源都要看 HTTP 状态码（见 curl_download）。
    v4.1 记忆重排：主源失败时，**上次成功过的镜像**提到其余镜像前面
    （主源安全设计不变——成功记录只影响镜像之间的先后）。

    validate(dest) 用来判断「下到的是不是真 ZIP」：镜像回源失败时经常
    返回 HTTP 200 + 一张 HTML 错误页，只看状态码会把错误页当成下载成功，
    最后抛个莫名其妙的「不是有效的 zip 包」。校验不过就换下一个镜像。

    全部失败时抛 RuntimeError(E_NETWORK)。
    """
    tried, last_err = [], ""
    prefixes = list(config.MIRROR_PREFIXES)
    last_good = _load_last_good_source()
    if last_good and last_good in prefixes and last_good != prefixes[0]:
        prefixes.remove(last_good)
        prefixes.insert(1, last_good)
    for i, prefix in enumerate(prefixes):
        url = prefix + (config.CODELOAD % (repo, branch))
        label = "主源 codeload" if prefix == "" else ("镜像 " + urlparse(prefix).netloc)
        if on_attempt:
            on_attempt(i, label, url)
        try:
            Path(dest).unlink(missing_ok=True)
            curl_download(url, Path(dest))
            if validate:
                validate(dest)
            if prefix != "":
                _save_last_good_source(prefix)
            return
        except HttpError as e:
            last_err = str(e)[:120]
            if e.status == 404 and i == 0:
                # 主源 404 说明仓库/分支真的不存在，换镜像也一样；直接失败，
                # 别把「仓库不存在」伪装成「所有镜像都挂了」。
                raise
        except Exception as e:
            last_err = str(e)[:120]
        tried.append(label)
    raise RuntimeError("%s 所有下载源都不可用（已尝试 %s）；最后错误：%s"
                       % (E_NETWORK, "、".join(tried), last_err))
