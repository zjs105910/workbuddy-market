"""增量树同步（v2.9 自 market_core.py 逐字迁入，只搬不改）。

纯树同步，无打包语义（方案 §3.1）；打包编排（_sync_packaging）留在 core。
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from .config import hash_chunk_bytes
from .hasher import _same_content
from .logging import log
from .paths import HASH_CHUNK_BYTES
from .scanner import _scan


def _sync_tree(src: Path, dst: Path, excluded=None, strict: bool = False,
               dst_index: dict | None = None) -> tuple:
    """把 src **增量**同步到 dst，返回 (拷贝数, 删除数, 源端总字节, 跳过的软链数)。

    判定用 size + **mtime_ns**（v1 的 int(st_mtime) 会把精度砍到秒，
    同秒内大小不变的修改会被漏掉）。
    strict=True 时，对「大小和时间戳都一样」的文件再比一遍内容 ——
    代价是要读文件，但能堵住「改完再把时间戳改回去」这种情况。

    dst_index 可由调用方预先算好（插件级整树扫描 + _sub_index 切片），
    避免每个 skill 都把目标目录重扫一遍。

    **两侧都 fail-closed**：源端少看见一个文件，目标端那份就会被判成「多余」
    而被删掉 —— 一次读取抖动就能把市场里的内容删掉（已用探针复现）。
    所以这里任何一处扫描失败都直接抛 ScanError，宁可整次同步失败。
    """
    src_index, src_links = _scan(src, excluded, on_error="raise")
    if dst_index is None:
        dst_index, _ = _scan(dst, excluded, on_error="raise")
    # strict 下每个变动文件都要比内容 —— 块大小在这里解析一次，别在循环里反复读配置
    chunk = hash_chunk_bytes() if strict else HASH_CHUNK_BYTES
    copied = removed = 0

    for rel, (ssize, smtime) in src_index.items():
        dfull = dst / rel
        cur = dst_index.get(rel)
        skip = False
        if cur is not None:
            if strict:
                # strict：以内容为准 —— 内容一样就不重写，哪怕时间戳不同
                skip = (cur[0] == ssize) and _same_content(src / rel, dfull, chunk)
            else:
                # fast：只看 size + mtime_ns
                skip = (cur[0] == ssize and cur[1] == smtime)
        if skip:
            continue
        dfull.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(src / rel, dfull)
            copied += 1
        except OSError as exc:
            log("error", "sync", f"拷贝 {rel} 失败：{exc}")

    # 删掉目标端多出来的（通常个位数），并记下受影响的目录
    prune_dirs = set()
    for rel in dst_index:
        if rel in src_index:
            continue
        p = dst / rel
        try:
            p.unlink()
            removed += 1
            prune_dirs.add(str(p.parent))
        except OSError:
            pass

    # 只收「确实删过文件的那些目录」及其祖先。
    # 不对全树目录试 rmdir —— 宿主/沙箱会给每次 os.rmdir 套一层路径校验，
    # 几百次空转 rmdir 能占掉整个同步一半的耗时（实测 0.32s/156 次）。
    tried = set()
    for d in sorted(prune_dirs, key=len, reverse=True):
        cur = Path(d)
        while cur not in tried and cur != dst and dst in cur.parents:
            tried.add(cur)
            try:
                os.rmdir(cur)
            except OSError:
                break
            cur = cur.parent

    if src_links:
        log("warn", "sync", f"{len(src_links)} 个符号链接被跳过，未打包：{src_links[:3]}")

    total = sum(v[0] for v in src_index.values())
    return copied, removed, total, len(src_links)
