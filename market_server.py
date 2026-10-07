# -*- coding: utf-8 -*-
"""market_server —— 本机市场的网页后端。

只监听 127.0.0.1，只读写本市场目录与 ~/.workbuddy，不对外暴露。

**localhost ≠ 只有你的网页能调用。** 任何本机浏览器里打开的网页都能往
127.0.0.1:8777 发请求 —— 只要它猜得到路由，就能替我们点「安装 / 卸载 /
清空回收站 / 注册」。所以从 v2.3 起：

  · 启动时生成一次性 token，注入到 index.html 的 <meta> 里
  · 所有 /api/* 都要带 `X-Local-Market-Token` 头
  · 再校验 `Origin`（带 Origin 时必须是本机同端口）
  · 第三方网页即使拿到了地址，也读不到那个 token —— 跨源读响应被浏览器挡住

接口：
  GET  /                      网页界面（注入 token）
  GET  /api/state             市场全量状态（插件 / GitHub 源 / 已装情况）
                              ?exact=1 用精确判定重算卸载分级
  GET  /api/log               最近事件（ndjson 尾部）
  GET  /api/job/<id>          长任务进度（安装/更新走这里）
  POST /api/sync              重新打包本机 skill
  POST /api/register          注册进 WorkBuddy 原生插件面板
  POST /api/unregister        撤销注册
  POST /api/install           {id, mode} 本机插件 → 装到 ~/.workbuddy/skills
                              mode: missing(默认) / update / force
  POST /api/uninstall         {id, force, dryRun} 卸载；dryRun 只返回分级计划
  POST /api/trash/purge       清空回收站
  POST /api/remote/add        {repo} ghpm add（后台任务）
  POST /api/remote/update     {repo} ghpm update（后台任务）
  POST /api/job/<id>/cancel   终止一个后台任务
  POST /api/open/path         {target, id?} 在资源管理器中打开市场内的目录

v2.10 GitHub 动态目录：
  GET  /api/catalog           收录源的实时元数据缓存（.catalog.json + 陈旧标记）
  GET  /api/gh/search?q=      GitHub 全网搜索（实时，服务端短缓存 120s）
  POST /api/catalog/refresh   手动刷新目录（后台任务，可取消）
  · serve() 另起 daemon 线程：每 15 分钟检查一次，条目过期（默认 24h）
    就自动刷新（按条目 TTL 逐个判断，全新鲜时零网络）；失败保旧值、
    下个检查点重试。WBM_CATALOG_OFF=1 可关。
  · make_server() **不**起这个线程 —— 自检的端到端测试必须零网络依赖。

v2.11 社区注册表 + 端口修复：
  GET  /api/registry          社区注册表（本仓库 registry/plugins.json，
                              每日 CI 重建动态字段；600s 内存缓存 + single-flight，
                              ?force=1 强制在线拉取）。响应带 installedRepos
                              （本机 ghpm 已装的 repo → 摘要）。
  · POST /api/catalog/refresh 现在同时刷新 catalog 与 registry。
  · _find_port 的探测 socket 在 Windows 改用 SO_EXCLUSIVEADDRUSE：
    原来的 SO_REUSEADDR 允许绑定「别的进程正监听着」的端口，同机多个
    市场进程同时绑 8777、请求随机打到旧进程（2026-10-07 实测复现）。
"""
from __future__ import annotations

import collections
import json
import os
import secrets
import signal
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

import market_core as core  # noqa: E402

HOST = "127.0.0.1"
DEFAULT_PORT = 8777

MAX_BODY = 1024 * 1024            # 单个请求体上限 1 MiB
JOB_TTL = 30 * 60                 # 已完成任务保留 30 分钟
MAX_JOBS = 100                    # 任务表上限（只淘汰**已完成**的）
MAX_RUNNING_JOBS = 4              # 同时在跑的后台任务上限（每个都会拉起 ghpm 子进程）
WBM_TIMEOUT = int(os.environ.get("WBM_TIMEOUT")
                  or os.environ.get("GHPM_TIMEOUT")        # deprecated，v2.7 兼容
                  or 15 * 60)                              # 单次远端任务上限
STATE_TTL = 1.0                   # /api/state 短缓存（秒）
SOCKET_TIMEOUT = 15               # 单连接读写超时（秒）
MAX_PARALLEL = 32                 # 接受队列长度

TOKEN = ""                        # 启动时生成；也可用 WBM_MARKET_TOKEN 固定

_jobs: "collections.OrderedDict[str, dict]" = collections.OrderedDict()
_jobs_lock = threading.RLock()
_job_seq = 0

# 真正限制「同时在跑的后台任务」的闸门。
#
# MAX_JOBS 只淘汰**已完成**的任务（运行中的一个都不动），所以它是「历史任务
# 表上限」，不是并发上限 —— 连开 140 个全 running 的任务，表里就真的留着 140 个，
# 每个都带一条线程 + 一个 ghpm 子进程（已用探针复现）。资源保护必须靠这个闸门。
class JobLimiter:
    """并发闸门 + 运行计数，二者由同一把锁保证一致。

    不直接读 `BoundedSemaphore._value`（私有字段，v2.5 的 running_jobs()
    靠 # noqa 压警告，长期维护不漂亮）。以后想把「超限直接拒绝」升级成
    「排队等待」，只需要改这一个类。
    """

    def __init__(self, limit: int):
        self.limit = limit
        self._sem = threading.BoundedSemaphore(limit)
        self._lock = threading.Lock()
        self._running = 0

    def acquire(self) -> bool:
        """抢一个并发槽。抢不到返回 False（调用方回 429），不阻塞。"""
        if not self._sem.acquire(blocking=False):
            return False
        with self._lock:
            self._running += 1
        return True

    def release(self) -> None:
        with self._lock:
            self._running -= 1
        self._sem.release()

    def running(self) -> int:
        with self._lock:
            return self._running


_RUNNER = JobLimiter(MAX_RUNNING_JOBS)

_state_lock = threading.RLock()
_state_cache: dict = {"at": 0.0, "key": None, "data": None}


# ---------------------------------------------------------------- 鉴权

def init_token(token: str | None = None) -> str:
    """生成/固定本机口令。环境变量 WBM_MARKET_TOKEN 可覆盖（测试用）。"""
    global TOKEN
    TOKEN = (token
             or os.environ.get("WBM_MARKET_TOKEN")
             or os.environ.get("GHPM_MARKET_TOKEN")     # deprecated，v2.7 兼容
             or secrets.token_urlsafe(32))
    return TOKEN


def origin_allowed(origin: str | None, port: int) -> bool:
    """Origin 校验。没带 Origin（curl / 脚本）时不在这里拦 —— 交给 token。

    浏览器对**同源 POST** 也会带 Origin，所以自己页面的请求能正常通过；
    带 `http://evil.example` 的跨源请求会被这里挡掉。
    """
    if origin is None or origin == "":
        return True
    if origin == "null":
        return False                  # sandbox iframe / data: 页面
    try:
        u = urlparse(origin)
    except ValueError:
        return False
    if u.scheme != "http":
        return False
    host = (u.hostname or "").lower()
    if host not in ("127.0.0.1", "localhost", "::1"):
        return False
    return u.port in (None, port)


# ---------------------------------------------------------------- 状态缓存

class SingleFlight:
    """同一时刻只让一个线程去重建同一个 key，其余线程**共享它的结果**。

    只做 TTL 是不够的：TTL 刚过期的那一瞬间，10 个并发请求会同时发现
    「缓存没了」，然后一起跑 build_state()。前端是定时轮询的，这种
    「缓存击穿」在状态页上很容易撞到。

    v2.4 的实现是「leader 刷，其他线程 `ev.wait()` 后**自己再跑一次 fn()**」——
    正常路径没问题，但两条边路都会把击穿放回来：
      · leader 超过 60 秒 → 等待线程超时醒来，各自重跑 fn()
      · leader 抛异常 → 等待线程醒来照样自己重跑 fn()
    实测「leader 抛异常 + 6 并发」→ build_state 被调了 **6 次**。

    现在改成共享结果盒：value / error 都由 leader 填，等待线程直接取，
    一个字节的重算都不会发生。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._boxes: dict = {}

    def run(self, key, fn, timeout: float = 60.0):
        with self._lock:
            box = self._boxes.get(key)
            if box is None:
                box = {"event": threading.Event(), "value": None, "error": None}
                self._boxes[key] = box
                leader = True
            else:
                leader = False

        if leader:
            try:
                box["value"] = fn()
            except BaseException as exc:      # noqa: BLE001 —— 原样转给所有等待者
                box["error"] = exc
            finally:
                box["event"].set()
                with self._lock:
                    self._boxes.pop(key, None)
            if box["error"] is not None:
                raise box["error"]
            return box["value"]

        if not box["event"].wait(timeout):
            raise TimeoutError(f"等待 {key!r} 的批量刷新超时（{timeout:.0f}s）")
        if box["error"] is not None:
            raise box["error"]
        return box["value"]


_flight = SingleFlight()


def invalidate_state() -> None:
    with _state_lock:
        _state_cache["data"] = None
        _state_cache["at"] = 0.0


def _read_state_cache(key: bool):
    with _state_lock:
        if (_state_cache["data"] is not None and _state_cache["key"] == key
                and time.time() - _state_cache["at"] < STATE_TTL):
            return _state_cache["data"]
    return None


def get_state(exact: bool = False) -> dict:
    """/api/state：短 TTL 缓存 + single-flight。

    状态页会被前端定时轮询；每次都把全部 skill 重新判一遍（精确模式还要读
    文件）没必要。1 秒内的重复请求直接复用，并且并发请求只会触发一次重建。
    """
    key = bool(exact)
    hit = _read_state_cache(key)
    if hit is not None:
        return hit
    return _flight.run(key, lambda: _fresh_state(key))


def _fresh_state(key: bool) -> dict:
    hit = _read_state_cache(key)              # 可能已经被 leader 刷好了
    if hit is not None:
        return hit
    data = core.build_state(purpose="uninstall" if key else "ui")
    with _state_lock:
        _state_cache.update(at=time.time(), key=key, data=data)
    return data


# ---------------------------------------------------------------- 长任务

def _job_finished(job: dict) -> bool:
    return job.get("status") == "done"


def _enforce_cap_locked() -> int:
    """调用方必须已持有 _jobs_lock。只淘汰已完成的任务，运行中的绝不动。"""
    dropped = 0
    while len(_jobs) > MAX_JOBS:
        for jid, job in _jobs.items():
            if _job_finished(job):
                del _jobs[jid]
                dropped += 1
                break
        else:
            break                     # 全在跑，一个都不动
    return dropped


def reap_jobs(now: float | None = None) -> int:
    """清掉过期的已完成任务，并保证任务数不超过上限。

    v2.2 的 _jobs 只增不减：完成的任务永远留着，长期跑会持续吃内存。
    运行中的任务绝不淘汰。
    """
    now = now or time.time()
    dead = 0
    with _jobs_lock:
        for jid in list(_jobs):
            job = _jobs[jid]
            if _job_finished(job) and now - float(job.get("finishedAt") or now) > JOB_TTL:
                del _jobs[jid]
                dead += 1
        dead += _enforce_cap_locked()
    return dead


def _new_job(title: str) -> str:
    global _job_seq
    reap_jobs()
    with _jobs_lock:
        _job_seq += 1
        jid = f"job{_job_seq}-{uuid.uuid4().hex[:6]}"
        _jobs[jid] = {
            "id": jid,
            "title": title,
            "status": "running",
            "ok": None,
            "lines": [],
            "percent": 0,
            "label": "准备中",
            "startedAt": time.time(),
            "finishedAt": None,
            "canceled": False,
            "timeout": WBM_TIMEOUT,
            "proc": None,
        }
        # 插入之后再收一次 —— 否则「先清理再插入」会让上限被突破 1 个
        _enforce_cap_locked()
    return jid


def _job_push(jid: str, text: str, percent=None, label=None) -> None:
    with _jobs_lock:
        job = _jobs.get(jid)
        if not job:
            return
        if text:
            job["lines"].append(text)
            if len(job["lines"]) > 400:
                del job["lines"][:100]
        if percent is not None:
            job["percent"] = percent
        if label:
            job["label"] = label


def _job_finish(jid: str, ok: bool, label: str = "") -> None:
    with _jobs_lock:
        job = _jobs.get(jid)
        if job:
            job["status"] = "done"
            job["ok"] = ok
            job["percent"] = 100
            job["finishedAt"] = time.time()
            job["proc"] = None
            if label:
                job["label"] = label


def _job_public(job: dict) -> dict:
    """给前端看的视图 —— 别把 Popen 对象序列化出去。"""
    return {k: v for k, v in job.items() if k != "proc"}


def kill_process_tree(proc: subprocess.Popen, grace: float = 5.0) -> None:
    """尽力干掉一个子进程，Windows 和 POSIX 都连带整棵进程树。

    git / gh / 代理 / 凭证助手都可能留下子进程，只 terminate 父进程
    会让它们变成孤儿继续挂着。POSIX 上子进程用 start_new_session=True
    启动（见 _run_ghpm），所以 pgid == pid，killpg() 一次收掉整组；
    Windows 走 taskkill /T。
    """
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, timeout=15)
        else:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                proc.terminate()      # 不在独立进程组里（老条目）就退回单杀
    except Exception:
        pass
    try:
        proc.wait(timeout=grace)
        return
    except Exception:
        pass
    try:
        if os.name == "nt":
            proc.kill()
        else:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                proc.kill()
    except Exception:
        pass


def cancel_job(jid: str) -> bool:
    with _jobs_lock:
        job = _jobs.get(jid)
        if not job or job.get("status") != "running":
            return False
        job["canceled"] = True
        proc = job.get("proc")
    if proc is not None:
        kill_process_tree(proc)
    return True


def _run_ghpm(args: list, jid: str) -> bool:
    """跑 ghpm 并把 __GHPM__ 进度事件翻译成任务进度。

    带看门狗：超时或用户点取消都会终止整棵进程树 —— 否则 GitHub / DNS /
    代理任一环节卡住，任务就会永远停在 running。

    取消有两条路径，都必须把「进程还没起来」的窗口关掉：
      · Popen 之前先查一次 canceled —— 用户取消得早就不必白白拉起进程；
      · Popen 之后、把 proc 挂到 job 上时再查一次 —— 若 cancel_job 恰好
        落在中间（那时 job["proc"] 还是 None，它杀无可杀），由这里自己补杀。
    """
    with _jobs_lock:
        job = _jobs.get(jid)
        if not job or job.get("canceled"):
            return False
    if not core.GHPM_PY.is_file():
        _job_push(jid, f"找不到 ghpm：{core.GHPM_PY}")
        return False
    cmd = [sys.executable, str(core.GHPM_PY)] + args
    _job_push(jid, "$ " + " ".join(args))
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(core.GHPM_PY.parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            start_new_session=(os.name != "nt"),   # POSIX 独立进程组，killpg 才收得干净
        )
    except OSError as exc:
        _job_push(jid, f"启动失败：{exc}")
        return False

    canceled_after_spawn = False
    with _jobs_lock:
        job = _jobs.get(jid)
        if job:
            job["proc"] = proc
            canceled_after_spawn = bool(job.get("canceled"))
    if canceled_after_spawn:
        # cancel_job 已经走过了（那时 proc 还没挂上，它杀无可杀）——这里补杀
        kill_process_tree(proc)

    deadline = time.time() + WBM_TIMEOUT
    stop = threading.Event()

    def watchdog():
        while not stop.wait(0.5):
            with _jobs_lock:
                job = _jobs.get(jid)
                canceled = bool(job and job.get("canceled"))
            if canceled:
                _job_push(jid, "已取消，正在终止子进程…")
                kill_process_tree(proc)
                return
            if time.time() > deadline:
                _job_push(jid, f"超过 {WBM_TIMEOUT // 60} 分钟仍未完成，自动终止")
                kill_process_tree(proc)
                return

    threading.Thread(target=watchdog, daemon=True).start()

    assert proc.stdout is not None
    try:
        for raw in proc.stdout:
            line = raw.rstrip("\n")
            if line.startswith("__GHPM__ "):
                try:
                    ev = json.loads(line[len("__GHPM__ "):])
                except ValueError:
                    continue
                _job_push(jid, "", percent=ev.get("percent"), label=ev.get("label", ""))
                if ev.get("phase") == "done" and ev.get("ok") is False:
                    # v2.5 在这里引用了未定义的 label（NameError），异常一路
                    # 冒到 worker，_job_finish 没跑，任务永远停在 running。
                    _job_push(jid, "✗ " + str(ev.get("error")
                                     or ev.get("label") or "ghpm 执行失败"))
            elif line.strip():
                _job_push(jid, line)
        code = proc.wait()
    finally:
        stop.set()
        with _jobs_lock:
            job = _jobs.get(jid)
            if job:
                job["proc"] = None

    with _jobs_lock:
        job = _jobs.get(jid)
        canceled = bool(job and job.get("canceled"))
    if canceled:
        _job_push(jid, "任务已取消")
        return False
    return code == 0


def running_jobs() -> int:
    """当前在跑的后台任务数（由 JobLimiter 自己记账，不碰信号量私有字段）。"""
    return _RUNNER.running()


def _remote_job(repo: str, action: str):
    """起一个远端任务。**并发已满时返回 None**，由调用方回 429。

    闸门在创建任务之前就抢下，抢不到就直接拒绝 —— 不能先建任务再排队，
    那样任务表会被塞满，用户看到的是一串永远不动的"运行中"。
    """
    if not _RUNNER.acquire():
        core.log("warn", "job", f"后台任务已达上限 {MAX_RUNNING_JOBS}，拒绝 {action} {repo}")
        return None
    try:
        jid = _new_job(f"{'安装' if action == 'add' else '更新'} {repo}")
    except BaseException:
        _RUNNER.release()                 # 建任务都失败了，令牌必须还回去
        raise

    core.log("info", "job", f"{action} {repo} 开始")

    def work():
        try:
            ok = _run_ghpm([action, repo] + (["--allow-non-skill"] if action == "add" else []), jid)
            _job_finish(jid, ok, ("完成" if ok else "失败") + f" · {repo}")
            core.log("info" if ok else "error", "job",
                     f"{action} {repo} {'成功' if ok else '失败'}")
        finally:
            _RUNNER.release()             # 无论成功、失败还是异常，都要还令牌

    threading.Thread(target=work, daemon=True).start()
    return jid


# ---------------------------------------------------------------- GitHub 目录（v2.10）

SEARCH_TTL = 120.0                 # GitHub 搜索的进程内缓存（秒）
CATALOG_CHECK_INTERVAL = 15 * 60   # 自动刷新循环的检查间隔（秒）

_search_lock = threading.Lock()
_search_cache: dict = {"at": 0.0, "q": None, "items": None}


def gh_search(query: str, limit: int = core.SEARCH_LIMIT_DEFAULT) -> list:
    """GitHub 搜索：TTL 缓存 + single-flight。

    未登录的 search API 限流是 10 次/分钟；前端 600ms 防抖 + 这里的
    「同词 120 秒直返」足够把误触挡住。结果只进内存不落盘 —— 搜索是
    「现在 GitHub 上有什么」的问题，落盘就变成目录了。
    """
    with _search_lock:
        if (_search_cache["items"] is not None and _search_cache["q"] == query
                and time.time() - _search_cache["at"] < SEARCH_TTL):
            return _search_cache["items"]
    items = _flight.run(("ghsearch", query),
                        lambda: core.search_repos(query, limit))
    with _search_lock:
        _search_cache.update(at=time.time(), q=query, items=items)
    return items


def _catalog_refresh_job():
    """手动刷新目录 + 社区注册表。与 _remote_job 同一套闸门与任务表，并发满员返回 None。"""
    if not _RUNNER.acquire():
        core.log("warn", "job", f"后台任务已达上限 {MAX_RUNNING_JOBS}，拒绝刷新目录")
        return None
    try:
        jid = _new_job("刷新 GitHub 目录")
    except BaseException:
        _RUNNER.release()
        raise

    def work():
        try:
            rep = core.refresh_catalog(force=True)
            _job_push(jid, f"已刷新 {rep['fetched']} 个 · 失败 {rep['failed']} 个"
                           f" · 跳过 {rep['skipped']} 个（数据还新鲜）")
            for repo, err in (rep["catalog"].get("errors") or {}).items():
                _job_push(jid, f"! {repo}: {err}")
            # v2.11：目录顺手把社区注册表也刷了（同一个「联网取新数据」动作）
            reg_ok, reg_note = True, ""
            try:
                reg = core.get_registry(force=True)
                reg_note = (f"社区注册表 {len(reg['plugins'])} 条 · 来源 {reg['source']}")
                _job_push(jid, reg_note)
            except Exception as exc:  # noqa: BLE001 —— 注册表挂了不算目录刷新失败
                reg_ok, reg_note = False, ""
                _job_push(jid, f"! 社区注册表刷新失败：{exc}")
            ok = rep["failed"] == 0
            _job_finish(jid, ok, ("完成" if ok else "部分失败") + " · GitHub 目录")
            core.log("info" if ok else "warn", "catalog",
                     f"手动刷新：fetched={rep['fetched']} failed={rep['failed']}"
                     f" skipped={rep['skipped']} registry={reg_note}")
        except Exception as exc:  # noqa: BLE001 —— 任务里的一切都转成失败展示
            _job_push(jid, f"✗ 刷新失败：{exc}")
            _job_finish(jid, False, "失败 · GitHub 目录")
            core.log("error", "catalog", f"手动刷新失败：{exc}")
        finally:
            _RUNNER.release()

    threading.Thread(target=work, daemon=True).start()
    return jid


_catalog_stop = threading.Event()


def catalog_auto_loop(stop: threading.Event) -> None:
    """每日自动刷新：先等 20 秒让网页先出来，之后每 15 分钟看一眼 TTL。

    force=False：只拉过期的条目；整轮失败时 refreshedAt 不动，
    下个检查点自然重试。这个线程只在 serve() 里起 —— 自检走
    make_server()，永远不碰网络。
    """
    if stop.wait(20.0):
        return
    while not stop.is_set():
        try:
            # 无条件进 refresh：内部按**单条** TTL 决定拉谁，全新鲜时零网络
            # （noop 不写盘）。不能用 is_stale() 做闸门 —— 整份目录的新鲜度
            # 跟着「最后一次成功刷新」走，个别条目连续失败时它永远显示新鲜，
            # 那个条目就再也轮不到重试了。
            rep = core.refresh_catalog(force=False)
            if rep.get("fetched") or rep.get("failed"):
                core.log("info" if not rep.get("failed") else "warn",
                         "catalog",
                         f"自动刷新：fetched={rep['fetched']} "
                         f"failed={rep['failed']} skipped={rep['skipped']}")
        except Exception as exc:  # noqa: BLE001 —— 网络问题不该弄死常驻线程
            core.log("warn", "catalog", f"自动刷新失败（下个检查点重试）：{exc}")
        try:
            # v2.11：注册表同样按自己的 TTL（6h）走，过期才联网。
            reg = core.get_registry(force=False)
            if reg.get("fetched"):
                core.log("info", "registry",
                         f"社区注册表已更新：{len(reg['plugins'])} 条（{reg['source']}）")
        except Exception as exc:
            core.log("warn", "registry", f"社区注册表刷新失败（下个检查点重试）：{exc}")
        if stop.wait(CATALOG_CHECK_INTERVAL):
            return


# ---------------------------------------------------------------- 社区注册表（v2.11）

REGISTRY_MEM_TTL = 600.0           # /api/registry 的进程内缓存（秒）

_registry_mem_lock = threading.Lock()
_registry_mem: dict = {"at": 0.0, "force": None, "data": None}


def registry_data(force: bool = False) -> dict:
    """GET /api/registry 的数据层：内存缓存 + single-flight + 已装摘要。

    内存 600 秒；core.get_registry 自己还有 6 小时的盘上缓存，两层各管各的
    （内存层挡轮询，盘上层挡重启）。force=True 连内存缓存一起跳过，
    但 single-flight 仍然生效 —— 并发的 force 请求共享同一次在线拉取。
    """
    with _registry_mem_lock:
        if (not force and _registry_mem["data"] is not None
                and _registry_mem["force"] is False
                and time.time() - _registry_mem["at"] < REGISTRY_MEM_TTL):
            return _registry_mem["data"]
    data = _flight.run(("registry", force), lambda: _registry_fresh(force))
    with _registry_mem_lock:
        _registry_mem.update(at=time.time(), force=force, data=data)
    return data


def _registry_fresh(force: bool) -> dict:
    reg = core.get_registry(force=force)
    reg["installedRepos"] = core.installed_repos()
    reg["ttlHours"] = int(core.REGISTRY_TTL // 3600)
    reg["ok"] = True
    return reg


# ---------------------------------------------------------------- HTTP

def _repo_arg(body: dict) -> tuple:
    """repo 参数统一走内核的 `validate_repo()`。

    输入边界只该有一处。v2.3 的 API 只判断了「非空」就丢给后台，等于把
    market_core 里已有的 owner/repo 校验整个绕过去了。
    """
    raw = body.get("repo")
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return "", "缺少 repo"
    if isinstance(raw, str):
        raw = raw.strip()
    try:
        return core.validate_repo(raw, "repo"), ""
    except core.ConfigError as exc:
        return "", str(exc)


class MarketHTTPServer(ThreadingHTTPServer):
    daemon_threads = True                 # 线程随主进程退出，不拖住 Ctrl+C
    allow_reuse_address = True
    request_queue_size = MAX_PARALLEL     # 默认 5 太小，本地轮询也能撞满


class Handler(BaseHTTPRequestHandler):
    server_version = "WorkBuddyLocalMarket/1.1"
    # StreamRequestHandler 会把这个值设到 connection 上：连上来之后
    # 15 秒还没发完请求就断开。否则有人慢慢发 1 MB body 就能一直占着一个线程。
    timeout = SOCKET_TIMEOUT

    def log_message(self, fmt, *args):  # 静音默认日志
        return

    # ---- 工具

    def _port(self) -> int:
        try:
            return int(self.server.server_address[1])
        except Exception:
            return DEFAULT_PORT

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError):
            pass

    def _json(self, data, code: int = 200):
        self._send(code, json.dumps(data, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _guard(self) -> bool:
        """鉴权：Origin + token。任一不过就回 403 并返回 False。"""
        origin = self.headers.get("Origin")
        if not origin_allowed(origin, self._port()):
            core.log("warn", "api", f"拒绝跨源请求：Origin={origin!r} {self.path}")
            self._json({"ok": False, "error": "跨源请求被拒绝（本机服务只服务自己的页面）"}, 403)
            return False
        got = self.headers.get("X-Local-Market-Token")
        if not TOKEN or got != TOKEN:
            core.log("warn", "api", f"拒绝无口令的请求：{self.path}")
            self._json({"ok": False,
                        "error": "缺少或错误的 X-Local-Market-Token；"
                                 "请从 http://127.0.0.1:%d/ 打开界面" % self._port()}, 403)
            return False
        return True

    def _body(self):
        """返回 (payload, error)。请求体有上限，坏 JSON 明确报 400。

        v2.2 是「读多少算多少 + 坏 JSON 当 {}」，既没有内存上限，
        也会让「格式写错」表现成「缺少 id」，诊断信息很差。
        """
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None, "Content-Length 不是数字"
        if n < 0:
            return None, "Content-Length 非法"
        if n > MAX_BODY:
            return None, f"请求体过大（{n} 字节，上限 {MAX_BODY}）"
        if n == 0:
            return {}, None
        raw = self.rfile.read(n)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            return None, f"请求体不是合法 UTF-8：{exc}"
        try:
            data = json.loads(text)
        except ValueError as exc:
            return None, f"请求体不是合法 JSON：{exc}"
        if not isinstance(data, dict):
            return None, "请求体必须是一个 JSON 对象"
        return data, None

    # ---- 路由

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            f = core.WEB_DIR / "index.html"
            if not f.is_file():
                return self._send(500, b"web/index.html missing", "text/plain; charset=utf-8")
            try:
                html = f.read_text(encoding="utf-8")
            except OSError as exc:
                return self._send(500, f"读不到 index.html：{exc}".encode("utf-8"),
                                  "text/plain; charset=utf-8")
            # 把一次性口令注入页面 —— 只有真正从本服务拿到的页面才带着它
            return self._send(200, html.replace("__MARKET_TOKEN__", TOKEN).encode("utf-8"),
                              "text/html; charset=utf-8")
        if path.startswith("/api/"):
            if not self._guard():
                return
            if path == "/api/state":
                exact = "exact=1" in (urlparse(self.path).query or "")
                return self._json(get_state(exact))
            if path == "/api/log":
                return self._json({"items": core.tail_log(80)})
            if path == "/api/catalog":
                cat = core.load_catalog()
                return self._json({"ok": True, "stale": core.is_stale(cat),
                                   "ttlHours": int(core.CATALOG_TTL // 3600),
                                   "catalog": cat})
            if path == "/api/gh/search":
                qs = parse_qs(urlparse(self.path).query)
                raw = (qs.get("q") or [""])[0]
                try:
                    q = core.validate_query(raw)
                except core.ConfigError as exc:
                    return self._json({"ok": False, "error": str(exc)}, 400)
                try:
                    items = gh_search(q)
                except core.ConfigError as exc:
                    return self._json({"ok": False, "error": str(exc)}, 400)
                except Exception as exc:  # 网络 / 限流 / DNS 都算上游失败
                    core.log("warn", "api", f"GitHub 搜索失败：{exc}")
                    return self._json({"ok": False,
                                       "error": f"GitHub 搜索失败：{exc}"}, 502)
                return self._json({"ok": True, "query": q, "items": items})
            if path == "/api/registry":
                force = parse_qs(urlparse(self.path).query).get("force") == ["1"]
                try:
                    reg = registry_data(force=force)
                except Exception as exc:  # 注册表三路全挂且无兜底时给 502，不白屏
                    core.log("warn", "api", f"社区注册表拉取失败：{exc}")
                    return self._json({"ok": False,
                                       "error": f"社区注册表拉取失败：{exc}"}, 502)
                return self._json(reg)
            if path.startswith("/api/job/"):
                jid = path.rsplit("/", 1)[-1]
                reap_jobs()
                with _jobs_lock:
                    job = _jobs.get(jid)
                    view = _job_public(job) if job else None
                if not view:
                    return self._json({"error": "任务不存在"}, 404)
                return self._json(view)
            return self._json({"error": "not found", "path": path}, 404)
        return self._json({"error": "not found", "path": path}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        if not path.startswith("/api/"):
            return self._json({"error": "not found", "path": path}, 404)
        if not self._guard():
            return
        body, err = self._body()
        if err is not None:
            code = 413 if "过大" in err else 400
            return self._json({"ok": False, "error": err}, code)
        try:
            if path == "/api/sync":
                rep = core.sync_packaging(quiet=True)
                invalidate_state()
                return self._json({"ok": True, "report": {
                    "plugins": len(rep["plugins"]),
                    "skills": rep["totalSkills"],
                    "copiedSkills": rep["copiedSkills"],
                    "copiedFiles": rep.get("copiedFiles", 0),
                    "removedFiles": rep.get("removedFiles", 0),
                    "skippedLinks": rep.get("skippedLinks", 0),
                    "cachedSkills": len(rep.get("cachedSkills", [])),
                    "verify": rep.get("verify", "auto"),
                    "recovered": rep.get("recovered", []),
                    "missing": rep["missing"],
                }})
            if path == "/api/register":
                changed = core.register()
                invalidate_state()
                return self._json({"ok": True, "changed": changed})
            if path == "/api/unregister":
                changed = core.unregister()
                invalidate_state()
                return self._json({"ok": True, "changed": changed})
            if path == "/api/install":
                r = core.install_local_plugin(body.get("id", ""), body.get("mode") or "missing")
                invalidate_state()
                return self._json(r)
            if path == "/api/uninstall":
                # dryRun=true 只算不删，界面用它先给用户看分级结果。
                # 这里是「删除前的预览」，必须用精确判定 —— 不能拿指纹的
                # 乐观结论去骗用户说「这些都能安全卸载」。
                if body.get("dryRun"):
                    return self._json(core.plugin_uninstall_plan(
                        body.get("id", ""), purpose="uninstall"))
                r = core.uninstall_local_plugin(body.get("id", ""), force=bool(body.get("force")))
                invalidate_state()
                return self._json(r)
            if path == "/api/trash/purge":
                r = core.prune_trash(force=True, quiet=True)
                invalidate_state()
                return self._json({"ok": True, "result": r})
            if path == "/api/remote/add":
                repo, err2 = _repo_arg(body)
                if err2:
                    return self._json({"ok": False, "error": err2}, 400)
                jid = _remote_job(repo, "add")
                if jid is None:
                    return self._json({"ok": False, "error":
                                       f"后台任务已达上限（{MAX_RUNNING_JOBS} 个），"
                                       "请等当前任务完成或取消它"}, 429)
                return self._json({"ok": True, "jobId": jid})
            if path == "/api/remote/update":
                repo, err2 = _repo_arg(body)
                if err2:
                    return self._json({"ok": False, "error": err2}, 400)
                jid = _remote_job(repo, "update")
                if jid is None:
                    return self._json({"ok": False, "error":
                                       f"后台任务已达上限（{MAX_RUNNING_JOBS} 个），"
                                       "请等当前任务完成或取消它"}, 429)
                return self._json({"ok": True, "jobId": jid})
            if path == "/api/catalog/refresh":
                jid = _catalog_refresh_job()
                if jid is None:
                    return self._json({"ok": False, "error":
                                       f"后台任务已达上限（{MAX_RUNNING_JOBS} 个），"
                                       "请等当前任务完成或取消它"}, 429)
                return self._json({"ok": True, "jobId": jid})
            if path.startswith("/api/job/") and path.endswith("/cancel"):
                jid = path[len("/api/job/"):-len("/cancel")].strip("/")
                if not jid:
                    return self._json({"ok": False, "error": "缺少任务 id"}, 400)
                return self._json({"ok": True, "canceled": cancel_job(jid)})
            if path == "/api/open/path":
                # 白名单：只打开市场自己地盘里的目录。
                # v2.2 是 Path(body["path"]) 直接交给 explorer —— C:\Windows 都能开。
                target, err2 = core.resolve_open_request(body)
                if target is None:
                    return self._json({"ok": False, "error": err2}, 400)
                if not target.exists():
                    return self._json({"ok": False, "error": f"路径不存在：{target}"}, 400)
                opener = {"win32": "explorer", "darwin": "open"}.get(sys.platform, "xdg-open")
                try:
                    subprocess.Popen([opener, str(target)])
                except OSError as exc:
                    return self._json({"ok": False, "error": f"打不开：{exc}"}, 500)
                return self._json({"ok": True, "opened": str(target)})
        except Exception as exc:  # 任何异常都回成 JSON，别让界面白屏
            core.log("error", "api", f"{path} 出错：{exc}")
            return self._json({"ok": False, "error": str(exc)}, 500)
        return self._json({"error": "not found", "path": path}, 404)


# ---------------------------------------------------------------- 入口

def make_server(port: int = DEFAULT_PORT, host: str = HOST,
                token: str | None = None) -> ThreadingHTTPServer:
    """建好服务但不启动 —— 自检可以直接拿它在临时端口上跑端到端测试。"""
    init_token(token)
    core.recover_transactions(quiet=True)
    return MarketHTTPServer((host, port), Handler)


def serve(port: int = DEFAULT_PORT, open_browser: bool = True) -> int:
    port = _find_port(port)
    httpd = make_server(port)
    url = f"http://{HOST}:{port}/"
    core.log("info", "serve", f"市场服务已启动 {url}")
    print(f"  市场已启动： {url}", flush=True)
    print(f"  口令已注入页面（第三方网页无法调用本机 API）", flush=True)
    print("  按 Ctrl+C 停止\n", flush=True)
    if open_browser:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    catalog_off = os.environ.get("WBM_CATALOG_OFF") == "1"
    if not catalog_off:
        threading.Thread(target=catalog_auto_loop, args=(_catalog_stop,),
                         daemon=True, name="catalog-auto").start()
        print("  GitHub 目录自动刷新已开启（每 15 分钟检查，过期即拉取；"
              "WBM_CATALOG_OFF=1 可关闭）", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  已停止。")
    finally:
        _catalog_stop.set()
        httpd.server_close()
    return 0


def _find_port(start: int) -> int:
    """从 start 起找一个真正空闲的端口。

    v2.11 修复 Windows 假空闲端口：探测 socket 原来设 SO_REUSEADDR ——
    在 Windows 上它允许绑定「别的进程**正监听着**」的端口，于是旧市场
    进程还活着时新进程也「探测成功」，两个进程同时绑 8777，请求随机
    打到旧进程，网页就会随机 404（2026-10-07 三个进程同绑 8777 实测）。
    Windows 改用 SO_EXCLUSIVEADDRUSE：只要端口被任何人占着就 bind 失败，
    这才是「真的空闲」。POSIX 不需要换 —— Linux 上 SO_REUSEADDR 只放宽
    TIME_WAIT 复用，本就不允许两个监听 socket 共存。

    真正的服务 socket（MarketHTTPServer）保留 allow_reuse_address=True：
    Windows 上 Ctrl+C 重启后立刻重绑 8777 依赖它，去掉会引入重启回归；
    而 serve() 的入口永远先过本探测，双活场景已经被这里挡死。
    """
    import socket

    exclusive = hasattr(socket, "SO_EXCLUSIVEADDRUSE")   # Windows only
    for p in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if exclusive:
                # 注意 SO_REUSEADDR 与 SO_EXCLUSIVEADDRUSE 在 Windows 上互斥，
                # 同设是 WSEINVAL —— 要换就彻底换掉。
                s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            else:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((HOST, p))
                return p
            except OSError:
                continue
    raise SystemExit(f"{start}~{start + 19} 端口都被占用，起不了服务。")


if __name__ == "__main__":
    raise SystemExit(serve())
