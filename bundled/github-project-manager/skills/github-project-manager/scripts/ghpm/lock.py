# -*- coding: utf-8 -*-
"""并发写锁（profile 锁）。

skills 目录 + 清单一次只允许一个写操作，仿 DSH 的 profile 写锁。
宿主强杀进程时 finally 不会执行，故下个写操作会检查持有者并清理陈旧锁。

v4 的两处加固：
1. **心跳租约**：长任务（下载几百 MB）期间周期性 touch 锁文件，
   让「这把锁是活的」有独立于 pid 的证据。
2. **pid 判断允许失败**：v3.2 的 pid_alive 直接 ``run(["tasklist", ...])``，
   tasklist 不可用时 run() 会抛 RuntimeError 并一路穿透 acquire_lock ——
   整个加锁流程被一个可选工具搞挂。现在 pid_alive 返回三态
   （活着 / 已退出 / 判断不了），判断不了时退回租约判断，
   拿不准就**当成有人在跑**（宁可报 E_LOCKED，也不并发写盘）。
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

from . import config
from .util import _new_token, now, run


def _lock_path() -> Path:
    """锁文件路径在调用时读，测试换 GHPM_HOME 后仍然正确。"""
    return config.LOCK


def pid_alive(pid) -> bool | None:
    """锁的持有者还活着吗？返回三态：True 活着 / False 确认已退出 / None 判断不了。

    pid 可能被复用（Windows 上尤其），所以真正的归属判定靠 token，
    这里只用于「能不能忽略这把锁」。判断不了时返回 None，由调用方退回租约判断 ——
    绝不能在判断不了的时候当作「已退出」去抢锁。
    """
    try:
        pid = int(pid)
    except Exception:
        return None
    if pid <= 0:
        return None
    if os.name == "nt":
        try:
            r = run(["tasklist", "/FI", "PID eq %d" % pid, "/NH"])
        except Exception:
            return None                      # tasklist 不在 PATH / 无权限
        if r.returncode != 0:
            return None
        return str(pid) in (r.stdout or "")
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True                          # 存在但不属于我们
    except Exception:
        return None


def read_lock() -> dict:
    """读当前锁内容；锁文件不存在或坏了都返回 {}。"""
    try:
        st = json.loads(_lock_path().read_text(encoding="utf-8"))
        return st if isinstance(st, dict) else {}
    except Exception:
        return {}


def try_create_lock(payload: dict) -> None:
    """用 O_EXCL 排他创建锁；只有创建成功的进程才拥有锁。"""
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    lock = _lock_path()
    lock.parent.mkdir(parents=True, exist_ok=True)
    fd = None
    try:
        fd = os.open(str(lock), flags, 0o600)
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        view = memoryview(raw)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("写锁文件失败")
            view = view[written:]
        os.fsync(fd)
    except Exception:
        created = fd is not None
        if fd is not None:
            try:
                os.close(fd)
            except Exception:
                pass
            fd = None
        # 只有本次 O_EXCL 创建成功后才清理半写锁；不能删掉竞争者的现有锁。
        if created:
            try:
                lock.unlink()
            except Exception:
                pass
        raise
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except Exception:
                pass


def lock_heartbeat_age(st: dict, stat_mtime: float | None = None) -> float:
    """距最后一次「持有者还活着」的证据过去多久（秒）。

    取 mtime / heartbeat / epoch 三者里最新的那个：老版本写的锁没有 heartbeat
    字段，用 epoch 兜底；被人手工 touch 过则以 mtime 为准。
    """
    stamps = []
    for v in (st.get("heartbeat"), st.get("epoch")):
        try:
            stamps.append(float(v))
        except Exception:
            pass
    if stat_mtime:
        stamps.append(float(stat_mtime))
    if not stamps:
        return float("inf")
    return max(0.0, time.time() - max(stamps))


def lock_is_stale(st: dict, stat_mtime: float | None = None) -> bool:
    """这把锁能不能当陈旧锁清掉。

    进程存活是权威证据；查不到进程（None）时退回租约：
    心跳还在 LOCK_LEASE_SEC 之内就当作有人在跑，不抢。
    """
    alive = pid_alive(st.get("pid"))
    if alive is True:
        return False
    if alive is False:
        return True
    return lock_heartbeat_age(st, stat_mtime) > config.LOCK_LEASE_SEC


def _stat_mtime(p: Path) -> float | None:
    try:
        return p.stat().st_mtime
    except OSError:
        return None


def acquire_lock(op: str = "") -> tuple[Path | None, dict]:
    """获取写锁。

    O_EXCL 保证多个进程竞争时只有一个能创建锁。若发现旧锁，只在确认持有者
    已退出（或租约过期、或锁内容损坏）后删除，再重新竞争；不会覆盖另一进程刚创建的锁。
    """
    lock = _lock_path()
    lock.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(4):
        payload = {"pid": os.getpid(), "epoch": time.time(), "at": now(),
                   "op": op, "token": _new_token(), "heartbeat": time.time()}
        try:
            try_create_lock(payload)
            return lock, payload
        except FileExistsError:
            st = read_lock()
            if st and not lock_is_stale(st, _stat_mtime(lock)):
                return None, st

            # 陈旧锁只能按读到的 token 清理。若期间内容变化，重新竞争而不是误删。
            current = read_lock()
            if st and current.get("token") != st.get("token"):
                continue
            try:
                lock.unlink()
            except FileNotFoundError:
                continue
            except Exception:
                return None, current or st
            age = lock_heartbeat_age(st, None) if st else 0
            print("  [提示] 已清理陈旧锁（持有者 %s，%.0f 秒前有活动）"
                  % (st.get("pid", "?") if st else "?", age), file=sys.stderr)
            continue
        except Exception:
            return None, read_lock() or {}
    return None, read_lock() or {}


def release_lock(token: str | None = None) -> None:
    """只删「自己加的锁」。宿主强杀 → B 覆盖锁 → A 的 finally 晚到时，
    若无条件 unlink 会把 B 的锁删掉造成双写。"""
    lock = _lock_path()
    try:
        if not lock.exists():
            return
        st = read_lock()
        if not st:                       # 坏锁文件：内容都解析不了，直接清掉
            lock.unlink()
            return
        if token and st.get("token") != token:
            return
        if st.get("pid") != os.getpid():
            return
        lock.unlink()
    except Exception:
        pass


class Heartbeat:
    """持有写锁期间周期性续租（只 touch mtime，不重写内容）。

    为什么只 touch：重写内容需要「临时文件 + os.replace」，而排他性建立在
    O_EXCL 创建出的**那个**文件上，replace 会让竞争者观察到不一致的中间状态。
    utime 是原子的，且不改变 inode 归属，最安全。

    为什么每次都要重新读 token：锁有可能被 `ghpm unlock --force` 摘掉后
    被另一个进程拿走，这时继续 touch 等于替别人续租，会把活锁伪装成新锁。
    """

    def __init__(self, token: str | None, interval: float | None = None):
        self.token = token
        self.interval = float(interval or config.LOCK_HEARTBEAT_SEC)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> "Heartbeat":
        if not self.token:
            return self
        self._thread = threading.Thread(target=self._loop, name="ghpm-lock-hb",
                                        daemon=True)
        self._thread.start()
        return self

    def _loop(self) -> None:
        lock = _lock_path()
        while not self._stop.wait(self.interval):
            try:
                st = read_lock()
                if not st or st.get("token") != self.token:
                    return               # 锁已经不是我们的了，立即停手
                if not lock.exists():
                    return
                os.utime(lock, None)
            except Exception:
                return

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def __enter__(self) -> "Heartbeat":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()


class LockSession:
    """``with LockSession("install foo") as holder:`` —— 拿不到锁就抛 E_LOCKED。

    把「加锁 → 起心跳 → 干活 → 解锁」收敛成一个上下文，
    命令层不用再各写一遍 try/finally（v3.2 里 install / remove / scan /
    rollback 各写了一遍，漏一处就是并发写的口子）。
    """

    def __init__(self, op: str, on_busy=None):
        self.op = op
        self.holder: dict = {}
        self.lock: Path | None = None
        self._hb: Heartbeat | None = None
        self.on_busy = on_busy

    def __enter__(self) -> "LockSession":
        from .errors import E_LOCKED
        self.lock, self.holder = acquire_lock(self.op)
        if not self.lock:
            if self.on_busy:
                self.on_busy(self.holder)
            raise RuntimeError("%s 有另一个任务正在修改（占用者：%s）"
                               % (E_LOCKED, self.holder.get("op", "?")))
        self._hb = Heartbeat(self.holder.get("token")).start()
        return self

    def __exit__(self, *exc) -> None:
        if self._hb is not None:
            self._hb.stop()
            self._hb = None
        release_lock(self.holder.get("token"))
