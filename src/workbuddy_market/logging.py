"""事件流日志（v2.8 自 market_core.py 逐字迁入，只搬不改）。

模块名与标准库 logging 同名是刻意的（方案 §3.1 命名）：
Python 3 绝对导入下包内模块不会遮蔽 stdlib logging；
本包与调用方都不 import stdlib 的 logging，无实际冲突。
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .errors import FileLockTimeout
from .locking import FileLock
from .paths import LOG_KEEP, LOG_LOCK_PATH, LOG_MAX_BYTES, LOG_PATH


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _rotate_log() -> None:
    """日志超过阈值就轮转：.ndjson → .1.ndjson → .2.ndjson（最旧的丢弃）。"""
    try:
        if not LOG_PATH.is_file() or LOG_PATH.stat().st_size < LOG_MAX_BYTES:
            return
    except OSError:
        return
    for i in range(LOG_KEEP, 0, -1):
        older = LOG_PATH.with_name(f"{LOG_PATH.stem}.{i}{LOG_PATH.suffix}")
        newer = LOG_PATH if i == 1 else LOG_PATH.with_name(f"{LOG_PATH.stem}.{i - 1}{LOG_PATH.suffix}")
        try:
            if newer.is_file():
                os.replace(newer, older)
        except OSError:
            pass


def log(level: str, event: str, detail: str = "", op_id: str = "") -> None:
    """DSH 风格的事件流：一行一条 ndjson，追加写，超限自动轮转。

    「轮转 + 追加」整体放在**独立的日志锁**里 —— 两个进程同时轮转会出现
    A 把 .1 挪成 .2、B 又把 .1 挪成 .2 的竞态。不共用主锁是为了避免
    记日志和业务操作互相等待；也刻意不参与事务（日志不该成为失败点），
    所以拿不到锁时退化成无锁追加，宁可顺序乱一点，也不让记日志把业务打断。
    """
    rec = {"at": now_iso(), "level": level, "event": event, "detail": detail}
    if op_id:
        rec["op"] = op_id
    line = json.dumps(rec, ensure_ascii=False) + "\n"

    def _append() -> None:
        try:
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)  # v2.7：logs/ 可能尚未创建
        except OSError:
            pass
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line)

    try:
        with FileLock(LOG_LOCK_PATH, timeout=2.0):
            _rotate_log()
            _append()
    except (FileLockTimeout, OSError):
        try:
            _append()
        except OSError:
            pass


def _tail_lines(path: Path, want: int, block: int = 64 * 1024) -> tuple:
    """从文件**尾部**反向分块读，凑够 want 行就停。

    返回 (行列表[按时间正序, bytes], 是否读到了文件开头)。
    没读到开头时，返回的第一行可能是被截断的半行 —— 调用方靠第二个返回值判断。

    为什么不直接 `deque(fh, maxlen=N)`：那样内存是 O(N)，但**磁盘 I/O 仍然是
    整个文件**。实测 3 份日志合计 28.6 MB 时，取最后 60 行要读满 28.6 MB、
    耗时 1.4 秒。反向读只碰最后 64 KB，成本与日志历史长度无关。
    """
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            pos = fh.tell()
            chunks, newlines = [], 0
            while pos > 0 and newlines <= want:
                step = min(block, pos)
                pos -= step
                fh.seek(pos)
                chunk = fh.read(step)
                chunks.append(chunk)
                newlines += chunk.count(b"\n")
            at_start = pos == 0
    except OSError:
        return [], True
    data = b"".join(reversed(chunks))
    lines = data.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()                     # 文件以换行结尾
    if not at_start and lines:
        lines.pop(0)                    # 最前面那条是被截断的半行
    if len(lines) > want:
        lines = lines[-want:]
    return lines, at_start


def tail_log(limit: int = 60) -> list:
    """最近 limit 条事件（最新在前）。

    **真 tail**：从每个文件的尾部反向读，凑够就停。
    多份轮转日志按「新 → 旧」补足，所以日志越大，读的量也不会跟着涨。

    （v2.3 的实现是 `deque.extend(fh)` —— 内存省了，I/O 没省：
    每次仍要把整份日志从头扫一遍。README 里写的「反向读」名不副实。）
    """
    want = max(1, int(limit))
    files = [LOG_PATH]                  # 最新的一份
    for i in range(1, LOG_KEEP + 1):    # 越往后越旧
        files.append(LOG_PATH.with_name(f"{LOG_PATH.stem}.{i}{LOG_PATH.suffix}"))

    buf: list = []                      # 按时间正序累积
    for p in files:
        if not p.is_file():
            continue
        need = want - len(buf)
        if need <= 0:
            break
        lines, at_start = _tail_lines(p, need)
        buf = lines + buf
        if not at_start:
            break                       # 这一份还没读到头，就说明已经凑够了

    out = []
    for raw in buf[-want:]:
        text = raw.decode("utf-8", "replace").strip()
        if not text:
            continue
        try:
            out.append(json.loads(text))
        except ValueError:
            continue
    return list(reversed(out))
