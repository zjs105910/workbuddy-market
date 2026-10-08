"""内容指纹与流式哈希（v2.8 自 market_core.py 逐字迁入）。

只迁「不依赖扫描器与配置」的叶子函数；quick_fingerprint / tree_hash /
tree_hash_from_index 依赖 core._scan（selftest 崩溃注入的属性注入点）与
hash_chunk_bytes()（读配置），留在 market_core，R3 拆 config/scanner 时再走。
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .paths import HASH_CHUNK_BYTES

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


def normalize_sha256(value) -> str | None:
    """把外部给的 sha256 值归一成裸小写 hex；不合法返回 None（v2.16 新增）。

    接受 ``"裸 hex"`` 与 ``"sha256:<hex>"`` 两种写法（manifest / 注册表 /
    命令行三种来源的口径不一，这里统一）。**返回 None 是刻意的**：让
    调用方自己决定「没给哈希」与「给了坏哈希」分别怎么 fail-closed，
    本函数不做策略。
    """
    if not isinstance(value, str):
        return None
    v = value.strip().lower()
    if v.startswith("sha256:"):
        v = v[len("sha256:"):]
    return v if _HEX64_RE.match(v) else None


def fingerprint_from_index(index: dict, links=()) -> dict:
    """从一份**已经扫好的**索引算指纹，不再碰磁盘。

    批量状态检查和安装暂存阶段都复用这个 —— 索引已经在那儿了，
    没必要为了算指纹再把同一棵树走一遍。
    """
    mtimes = [v[1] for v in index.values()]
    return {
        "files": len(index),
        "bytes": sum(v[0] for v in index.values()),
        "mtime_ns_max": max(mtimes, default=0),
        "mtime_ns_sum": sum(mtimes),
        "links": len(links),
    }


def sha256_file(path: Path, chunk_size: int | None = None) -> bytes:
    """流式 SHA-256：内存占用 O(chunk)，不是 O(文件大小)。

    strict 模式会对每个文件算哈希；某个 skill 里出现几百 MB 的大文件时，
    read_bytes() 会直接把文件整个读进内存。分块读则与文件大小无关。

    实测（64 MiB 文件）：read_bytes 峰值 64.0 MiB → 流式 2.01 MiB，
    耗时可忽略（44.9 ms vs 45.5 ms）。
    """
    cs = chunk_size or HASH_CHUNK_BYTES
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        while True:
            chunk = fh.read(cs)
            if not chunk:
                break
            h.update(chunk)
    return h.digest()


def _same_content(a: Path, b: Path, chunk_size: int | None = None) -> bool:
    """两个文件内容是否一致（strict 模式下用）。流式比对，不整读。"""
    cs = chunk_size or HASH_CHUNK_BYTES
    try:
        if a.stat().st_size != b.stat().st_size:
            return False
        return sha256_file(a, cs) == sha256_file(b, cs)
    except OSError:
        return False
