"""跨平台可重入文件锁（v2.8 自 market_core.py 逐字迁入，只搬不改）。"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from .errors import FileLockTimeout
from .paths import LOCK_PATH

# 线程级的「本线程当前是否持有市场锁」计数。
# FileLock._depth 是**实例**属性，没法跨实例识别重入，所以单独放一份模块级状态。
_HELD = threading.local()


class FileLock:
    """跨平台排他文件锁，**可重入**（同进程同线程重复获取不会自锁）。

    Windows 用 msvcrt.locking，POSIX 用 fcntl.flock。都没有时退化成
    O_EXCL 哨兵文件。

    注意：这把锁只能串行化**本工具自己**的多个进程。WorkBuddy 自身
    不会来抢这把锁，所以对 known_marketplaces.json 仍然保留
    「写回校验」，两者互补。
    """

    _depth = threading.local()

    def __init__(self, path: Path = LOCK_PATH, timeout: float = 15.0):
        self.path = Path(path)
        # v2.7：锁文件可能落在全新 STATE_HOME/locks/ 下，父目录必须先建好
        # （os.open(O_CREAT) 不会建父目录）。
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        self.timeout = timeout
        self._fd = None

    # ---- 平台原语
    def _try_lock(self) -> bool:
        fd = os.open(str(self.path), os.O_RDWR | os.O_CREAT, 0o644)
        try:
            if os.fstat(fd).st_size == 0:
                os.write(fd, b"\0")
            if os.name == "nt":
                import msvcrt

                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            return False
        self._fd = fd
        return True

    def _unlock(self) -> None:
        if self._fd is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                os.lseek(self._fd, 0, os.SEEK_SET)
                msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._fd, fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

    # ---- 可重入包装
    def __enter__(self):
        depth = getattr(self._depth, "n", 0)
        if depth > 0:
            self._depth.n = depth + 1
            return self
        deadline = time.monotonic() + self.timeout
        delay = 0.02
        while True:
            if self._try_lock():
                self._depth.n = 1
                _HELD.n = getattr(_HELD, "n", 0) + 1
                return self
            if time.monotonic() >= deadline:
                raise FileLockTimeout(
                    f"等锁超时（{self.timeout:.0f}s）：{self.path}\n"
                    "可能另一次安装/同步正在跑。若确认没有，删掉这个文件再试。"
                )
            time.sleep(delay)
            delay = min(delay * 1.6, 0.25)

    def __exit__(self, *exc):
        depth = getattr(self._depth, "n", 0)
        if depth > 1:
            self._depth.n = depth - 1
            return False
        self._depth.n = 0
        _HELD.n = max(0, getattr(_HELD, "n", 0) - 1)
        self._unlock()
        return False


def locked(timeout: float = 15.0):
    """取市场锁。**同线程可重入** —— 已持锁时直接返回空锁。

    为什么需要这一层：`locked()` 每次调用都会 new 一个 FileLock 实例，
    而 `FileLock._depth` 是**实例**属性。同一个线程在已持锁的状态下再
    `with locked():` 会拿着**另一个 fd** 去抢同一段区域，Windows 的
    msvcrt.locking / POSIX 的 flock 都会立刻失败 —— 结果是等锁超时，
    也就是自己把自己锁死。用一个线程级计数器绕开它。
    """
    if getattr(_HELD, "n", 0) > 0:
        return _NullLock()
    return FileLock(LOCK_PATH, timeout=timeout)


class _NullLock:
    """已经持锁时的占位上下文。"""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False
