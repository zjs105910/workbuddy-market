# -*- coding: utf-8 -*-
"""market_server 的三处收口（回归钉子）—— 全部不碰网络，不碰真实状态。

  1. `_send` 对端断开：end_headers() 本身就写 socket，必须和 body 一起兜住。
     v2.41 及之前它在 try 外，连 BrokenPipe 都会冒出去：GET 多记一条
     「未捕获异常」的 error 事件，POST 更把异常抛给标准库打 traceback。
  2. `_start_job`：后台任务派发的统一出口（抢闸门 → 建任务 → 起线程）。
     并发满员回 None；令牌归还只在这里；任务体漏出来的异常以「失败」收尾，
     不让任务永远停在「运行中」。
  3. `registry.find_entry`：按 repo 取条目只留一处口径。

Handler 一律用 __new__ 造壳子再喂假 socket —— 不绑定端口。
"""
from __future__ import annotations

import time
import types

import pytest

import market_server as srv
from workbuddy_market.registry import find_entry


class _DeadSocket:
    """对端已经断开：一写就 ConnectionResetError（Windows WinError 10054）。"""

    def __init__(self, exc=ConnectionResetError):
        self._exc = exc

    def write(self, b):
        raise self._exc(10054, "远程主机强迫关闭了一个现有的连接。")

    def flush(self):
        pass


class _LiveSocket:
    def __init__(self):
        self.chunks = []

    def write(self, b):
        self.chunks.append(bytes(b))

    def flush(self):
        pass


def _handler(wfile, path="/nope", command="GET", headers=None):
    h = srv.Handler.__new__(srv.Handler)
    h.wfile = wfile
    h.rfile = None
    h.server = types.SimpleNamespace(server_address=("127.0.0.1", 8777))
    h.path, h.command = path, command
    h.headers = headers or {}
    h.request_version, h.requestline = "HTTP/1.1", f"{command} {path} HTTP/1.1"
    h.close_connection = False
    return h


@pytest.fixture
def logged(monkeypatch):
    """拦住事件流写盘，同时收集（level, detail）供断言。"""
    events = []
    monkeypatch.setattr(srv.core, "log",
                        lambda level, event, detail="", op_id="": events.append((level, detail)))
    return events


class TestSendOnClientDisconnect:
    @pytest.mark.parametrize("exc", [ConnectionResetError, ConnectionAbortedError,
                                    BrokenPipeError, TimeoutError])
    def test_write_failure_is_swallowed_and_connection_closed(self, exc):
        h = _handler(_DeadSocket(exc))
        srv.Handler._send(h, 200, b"{}", "application/json")   # 不抛
        assert h.close_connection is True                     # 让 handle() 别再读它

    def test_healthy_connection_unaffected(self):
        sock = _LiveSocket()
        h = _handler(sock)
        srv.Handler._send(h, 200, b'{"ok":true}', "application/json")
        raw = b"".join(sock.chunks)
        assert h.close_connection is False
        assert raw.startswith(b"HTTP/1.0 200 OK\r\n") and raw.endswith(b"\r\n\r\n" + b'{"ok":true}')
        for header in (b"Cache-Control: no-store", b"X-Frame-Options: DENY",
                       b"Content-Security-Policy:", b"Content-Length: 11"):
            assert header in raw

    def test_get_leaves_no_error_event(self, logged):
        """以前：一次普通的断开会往事件流里记一条 error「未捕获异常」。"""
        srv.Handler.do_GET(_handler(_DeadSocket(), path="/nothing"))
        assert logged == []

    def test_post_returns_normally(self, logged):
        """以前：异常冒出 do_POST，标准库向 stderr 打印 traceback。"""
        h = _handler(_DeadSocket(), path="/api/job/nope/cancel", command="POST",
                     headers={"X-Local-Market-Token": srv.init_token("t-test"),
                              "Origin": "http://127.0.0.1:8777", "Content-Length": "0"})
        srv.Handler.do_POST(h)                                 # 不抛
        assert logged == []


class _FakeLimiter:
    def __init__(self, ok=True):
        self.ok, self.acquired, self.released = ok, 0, 0

    def acquire(self):
        self.acquired += 1
        return self.ok

    def release(self):
        self.released += 1

    def running(self):
        return self.acquired - self.released


@pytest.fixture
def jobs(monkeypatch):
    """隔离任务表与并发闸门，跑完清干净。"""
    limiter = _FakeLimiter()
    monkeypatch.setattr(srv, "_RUNNER", limiter)
    with srv._jobs_lock:
        srv._jobs.clear()
    yield limiter
    with srv._jobs_lock:
        srv._jobs.clear()


def _wait_done(jid, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with srv._jobs_lock:
            job = srv._jobs.get(jid)
        if job and job["status"] == "done":
            return job
        time.sleep(0.015)
    raise AssertionError(f"任务 {jid} 没有结束")


def _wait_released(jobs, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and jobs.released == 0:
        time.sleep(0.015)
    assert jobs.released >= 1, "任务结束后令牌没有归还"


class TestStartJob:
    def test_full_capacity_returns_none_without_creating_job(self, jobs, logged):
        jobs.ok = False
        assert srv._catalog_refresh_job() is None
        assert jobs.acquired == 1 and jobs.released == 0
        with srv._jobs_lock:
            assert srv._jobs == {}                            # 被拒不进任务表
        assert any("后台任务已达上限" in d and "刷新目录" in d for _, d in logged)

    def test_token_returned_once_on_success(self, jobs):
        seen = []
        jid = srv._start_job("t", lambda j: seen.append(j), "t")
        _wait_released(jobs)
        assert seen == [jid] and jobs.released == 1 and jobs.running() == 0
        with srv._jobs_lock:
            # 「收尾」是任务体的责任（_job_finish 由它调）：派发层只保证
            # 线程跑完、令牌归还，不会替任务体把状态改成 done。
            assert srv._jobs[jid]["status"] == "running"

    def test_token_returned_when_job_creation_fails(self, jobs, monkeypatch):
        def boom(_title):
            raise RuntimeError("建任务失败")
        monkeypatch.setattr(srv, "_new_job", boom)
        with pytest.raises(RuntimeError):
            srv._start_job("t", lambda j: None, "t")
        assert jobs.released == 1                              # 令牌必须还回去

    def test_exception_in_body_fails_the_job(self, jobs, logged):
        """以前 _remote_job 的任务体漏出异常 → 任务永远停在「运行中」。"""
        def body(jid):
            raise RuntimeError("没料到的异常")
        jid = srv._start_job("探针", body, "探针")
        job = _wait_done(jid)
        assert job["ok"] is False and job["label"] == "失败"
        assert any("异常终止" in ln for ln in job["lines"])
        assert jobs.released == 1 and jobs.running() == 0
        assert any(lvl == "error" and "异常终止" in d for lvl, d in logged)


class TestJobFunctionsUseStartJob:
    def test_remote_job_crash_no_longer_hangs(self, jobs, monkeypatch, logged):
        def boom(args, jid):
            raise RuntimeError("ghpm 解析炸了")
        monkeypatch.setattr(srv, "_run_ghpm", boom)
        jid = srv._remote_job("owner/repo", "add")
        job = _wait_done(jid)
        assert job["ok"] is False and jobs.released == 1

    def test_remote_job_success_label(self, jobs, monkeypatch, logged):
        monkeypatch.setattr(srv, "_run_ghpm", lambda args, jid: True)
        monkeypatch.setattr(srv.core, "installed_repos", lambda: {})
        jid = srv._remote_job("owner/repo", "add")
        job = _wait_done(jid)
        assert job["ok"] is True and "未含 skill" in job["label"]
        assert jobs.released == 1

    def test_registry_install_missing_entry(self, jobs, monkeypatch, logged):
        monkeypatch.setattr(srv.core, "get_registry", lambda *a, **k: {"plugins": []})
        jid = srv._registry_install_job("owner/absent")
        job = _wait_done(jid)
        assert job["ok"] is False and job["label"] == "失败 · 社区注册表"
        assert any("注册表里没有" in ln for ln in job["lines"])
        assert jobs.released == 1


_REG = {"plugins": [
    {"repo": "Owner/Repo", "packageHash": "a" * 64},
    {"repo": "other/one", "packageHash": "b" * 64},
]}


class TestFindEntry:
    def test_case_insensitive(self):
        assert find_entry(_REG, "owner/repo")["packageHash"] == "a" * 64
        assert find_entry(_REG, "OWNER/REPO") is _REG["plugins"][0]
        assert find_entry(_REG, "other/one")["packageHash"] == "b" * 64

    def test_not_found_and_bad_shapes(self):
        assert find_entry(_REG, "nope/nope") is None
        assert find_entry({}, "owner/repo") is None
        assert find_entry({"plugins": None}, "owner/repo") is None
        assert find_entry(None, "owner/repo") is None
        assert find_entry(_REG, "") is None
        assert find_entry({"plugins": ["junk", None, {"repo": "x/y"}]}, "x/y") == {"repo": "x/y"}
