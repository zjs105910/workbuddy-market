# -*- coding: utf-8 -*-
"""FileLock 的重入口径（日志锁不再被跳过的回归钉子）。

v2.41 及之前 FileLock 的嵌套深度是「每线程一份、所有实例共享」：持有市场锁
期间调 log()，日志锁的实例会被当成市场锁的重入，**根本不去拿日志锁**
（探针：持市场锁时 log() 获取日志锁 0 次，无锁时 1 次）。而安装 / 卸载 /
打包 / 恢复恰恰最爱写日志 —— 它们写日志的时段反而没有锁保护。

现在深度按 (线程, 锁文件) 各记一份。这里钉住：
  · 不同锁文件互不算重入（各拿各的锁）；
  · 同一把锁的重入照旧成立（同实例嵌套、跨实例同文件）；
  · 跨线程独占与 _HELD 计数不被破坏。

全部用临时目录里的锁文件，不碰市场锁与真实状态目录。
"""
from __future__ import annotations

import threading
import time

import pytest

from workbuddy_market import locking
from workbuddy_market.locking import FileLock, FileLockTimeout


@pytest.fixture
def tried(monkeypatch):
    """记录每次真实抢锁的锁文件名。"""
    calls = []
    real = FileLock._try_lock

    def spy(self):
        calls.append(self.path.name)
        return real(self)

    monkeypatch.setattr(FileLock, "_try_lock", spy)
    return calls


class TestReentrancyIsPerLockFile:
    def test_same_instance_reentrant(self, tried, tmp_path):
        lk = FileLock(tmp_path / "a.lock", timeout=1)
        with lk:
            with lk:
                assert tried == ["a.lock"]        # 第二层没有再抢
        assert tried == ["a.lock"]

    def test_same_file_other_instance_still_reentrant(self, tried, tmp_path):
        # 跨实例、同一个锁文件：旧版本就按重入处理（Windows 上第二个 fd 抢同一段
        # 必然失败），这个口径不能被这次改动弄坏。
        with FileLock(tmp_path / "a.lock", timeout=1):
            with FileLock(tmp_path / "a.lock", timeout=0.5):
                assert tried == ["a.lock"]
        assert tried == ["a.lock"]

    def test_other_lock_file_is_really_taken(self, tried, tmp_path):
        """持 A 期间取 B：B 是另一把锁，必须真的去抢 —— 这正是日志锁被跳过的修复点。"""
        with FileLock(tmp_path / "market.lock", timeout=1):
            with FileLock(tmp_path / "log.lock", timeout=1):
                pass
        assert tried == ["market.lock", "log.lock"]

    def test_nested_then_sibling_does_not_lose_track(self, tried, tmp_path):
        with FileLock(tmp_path / "market.lock", timeout=1):
            for _ in range(2):
                with FileLock(tmp_path / "log.lock", timeout=1):
                    pass
            with FileLock(tmp_path / "market.lock", timeout=0.5):   # 仍是重入
                assert tried == ["market.lock", "log.lock", "log.lock"]
        assert tried == ["market.lock", "log.lock", "log.lock"]


class TestHeldAccounting:
    def test_held_survives_a_nested_other_lock(self, tmp_path):
        """取过一把别的锁之后，本线程「持有市场锁」的事实不能被抹掉。"""
        with FileLock(tmp_path / "market.lock", timeout=1):
            assert getattr(locking._HELD, "n", 0) == 1
            with FileLock(tmp_path / "log.lock", timeout=1):
                assert getattr(locking._HELD, "n", 0) == 2
            assert getattr(locking._HELD, "n", 0) == 1
            assert isinstance(locking.locked(), locking._NullLock)   # locked() 仍认
        assert getattr(locking._HELD, "n", 0) == 0


class TestExclusionUnchanged:
    def test_other_thread_is_blocked(self, tmp_path):
        held, release = threading.Event(), threading.Event()

        def hold():
            with FileLock(tmp_path / "a.lock", timeout=5):
                held.set()
                release.wait(5)

        t = threading.Thread(target=hold, daemon=True)
        t.start()
        assert held.wait(3)
        try:
            t0 = time.monotonic()
            with pytest.raises(FileLockTimeout):
                with FileLock(tmp_path / "a.lock", timeout=0.4):
                    pass
            assert time.monotonic() - t0 < 3
        finally:
            release.set()
            t.join(5)
        with FileLock(tmp_path / "a.lock", timeout=2):    # 释放后能重新拿到
            pass
