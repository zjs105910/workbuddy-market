# -*- coding: utf-8 -*-
"""通用工具：时间戳、原子写、体积统计、子进程、事件输出。

v4 的重点在这一层里：**遍历只做一次**。

v3.2 的 estimate_install_bytes() 会
    ① find_skill_dirs()      rglob("*.md")   ← 第一遍
    ② path_size_bytes(root)  rglob("*")      ← 第二遍
    ③ 每个 skill 子目录各 rglob("*")          ← 第 N 遍
同一批文件被反复 stat。skill 目录本来就在 root 里面，所以这不是 O(root ×
skill_count) 那种爆炸，但实测（2100 文件 / 100 个 skill）仍是 3 遍左右，
且随仓库变大线性放大。v4 用 scan_tree() 一次遍历同时产出「总量」与
「各 skill 子目录的量」，find_skill_dirs 也并进同一次遍历（见 discovery）。
"""
from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .models import TreeStats

MIB = config.MIB
DISK_SAFETY_BYTES = config.DISK_SAFETY_BYTES


# ---------- 时间 ----------

def now() -> str:
    """统一时间戳：UTC ISO 8601。

    v3.1 用 time.strftime("%Y-%m-%d %H:%M:%S")，既没有时区也无法跨机器比较，
    夏令时切换附近还会产生歧义。清单里存 UTC，展示层再转本地时间（见 fmt_ts）。
    """
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fmt_ts(value: str) -> str:
    """把清单里的时间戳转成本地时间展示。

    兼容两种输入：v3.2 的 ISO 8601（带时区）和 v3.1 之前的无时区本地时间串。
    认不出来就原样返回，不让一个坏时间戳把整个 list 输出搞崩。
    """
    s = (value or "").strip()
    if not s:
        return "-"
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        try:                       # 老格式，视为本地时间
            dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return s
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _new_token() -> str:
    """锁 / 备份目录名用的随机串。pid 会被回收复用，光看 pid 会误判归属。"""
    return os.urandom(8).hex()


def safe_key(s: str) -> str:
    """目录名用的安全片段：owner/repo → owner__repo。
    只用仓库名的话，owner1/utils 和 owner2/utils 的备份目录会撞车，remove 可能误删。"""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", (s or "").replace("/", "__"))


# ---------- 结构化事件输出 ----------

def emit(phase: str, label: str, percent: int | None = None, code: str | None = None,
         detail: str | None = None, hint: str | None = None, backup: str | None = None,
         ok: bool | None = None, data=None, **extra) -> None:
    """字段全部显式列出（hint/backup/ok/data 是宿主常读的），**extra 只留作前向兼容。"""
    payload = {"phase": phase, "label": label, "ts": now()}
    if percent is not None:
        payload["percent"] = percent
    if code:
        payload["code"] = code
    if detail:
        payload["detail"] = detail
    if hint:
        payload["hint"] = hint
    if backup:
        payload["backup"] = backup
    if ok is not None:
        payload["ok"] = ok
    if data is not None:
        payload["data"] = data
    payload.update(extra)
    print("__GHPM__ " + json.dumps(payload, ensure_ascii=False), flush=True)


# ---------- 子进程 ----------

def run(cmd, **kw):
    """subprocess 包装：curl 不存在时给明确提示，别被外层 except 吞成泛化错误。"""
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", **kw)
    except FileNotFoundError:
        raise RuntimeError(
            "未找到可执行文件 %s。请安装后重试（Windows: winget install curl；"
            "macOS/Linux: 一般自带，或用包管理器安装），并确保它在 PATH 里。" % cmd[0])
    except PermissionError:
        raise RuntimeError("没有执行 %s 的权限：%s" % (cmd[0], cmd))


# ---------- 原子写 ----------

def atomic_write_bytes(dest: Path, payload: str) -> None:
    """写文件走原子替换：唯一临时文件 → fsync → os.replace。

    临时名用 mkstemp 而不是「dest + .tmp」：固定名在两个进程同时写同一目标时
    会互相覆盖对方的临时文件（A 写完被 B 截断，replace 后内容是 B 的半截），
    而且进程被 kill -9 会在目录里留下同名 .tmp 垃圾。唯一名 + 同目录 rename
    既避开竞争，也让残留文件互不干扰（后缀 .tmp-* 便于识别与清理）。
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=dest.name + ".", suffix=".tmp",
                                    dir=str(dest.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, str(dest))
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def atomic_copy(src: Path, dest: Path) -> None:
    """单文件恢复：也走唯一临时文件 + os.replace，避免回滚中途被杀把目标写成半截。"""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=dest.name + ".", suffix=".ghpm-restore.tmp",
                                    dir=str(dest.parent))
    os.close(fd)
    try:
        shutil.copy2(src, tmp_name)
        os.replace(tmp_name, str(dest))
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def remove_path(p: Path) -> None:
    """删除目录或文件；不存在不算错。

    删除失败**必须抛错**：apply 阶段靠它触发整事务回滚，回滚阶段靠它把
    失败项记进 failed 并保住备份。这里用 ignore_errors 会静默吞掉半截删除，
    让「回滚成功」变成假话。
    """
    p = Path(p)
    if not p.exists() and not p.is_symlink():
        return
    if p.is_dir() and not p.is_symlink():
        shutil.rmtree(p)
    else:
        try:
            p.unlink()
        except FileNotFoundError:
            pass


# ---------- 遍历与体积 ----------

def iter_tree(root: Path):
    """深度优先遍历 root，**不跟随符号链接**，yield (所在目录, DirEntry)。

    os.scandir 的 DirEntry 自带 is_dir/is_file/stat 缓存，比
    ``Path.rglob("*") + f.stat()`` 少一次 stat 系统调用 / 项，
    目录不可读时跳过而不是让整个扫描炸掉。
    """
    root = Path(root)
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                entries = list(it)
        except OSError:
            continue
        for e in entries:
            yield d, e
            try:
                is_dir = e.is_dir(follow_symlinks=False)
            except OSError:
                is_dir = False
            if is_dir:
                stack.append(Path(e.path))


def scan_tree(root: Path, watch=()) -> tuple:
    """一次遍历同时算出「整棵树」和「watch 里各子目录」的字节数。

    返回 ``(TreeStats, {watch路径: bytes})``。

    watch 里的目录如果本来就在 root 之内（正常安装流程就是：
    [[skills/<name>]] 全部位于解压根之下），它们的体积在**同一次遍历**里
    按前缀归属累加，不再各自 rglob 一遍 —— 这就是 v4 相对 v3.2 的主要收益。

    不在 root 之内的 watch 目标（外部直接喂 plan 的场景）单独扫一遍，
    宁可多花一点，也不能少算导致磁盘预检放行。
    """
    root = Path(root)
    try:
        root_res = root.resolve()
    except Exception:
        root_res = root

    watch_rel: dict = {}
    outside: list = []
    for w in watch:
        w = Path(w)
        try:
            rel = w.resolve().relative_to(root_res)
        except Exception:
            outside.append(w)
            continue
        if rel.parts:
            watch_rel[rel.parts] = w

    sub = {w: 0 for w in watch_rel.values()}
    stats = TreeStats()
    stack = [(root, (), None)]
    while stack:
        d, rel, bucket = stack.pop()
        try:
            with os.scandir(d) as it:
                entries = list(it)
        except OSError:
            continue
        for e in entries:
            try:
                if e.is_dir(follow_symlinks=False):
                    stats.dirs += 1
                    nrel = rel + (e.name,)
                    # 命中 watch 就开一个新桶，桶会沿子树继承下去
                    nb = bucket if bucket is not None else watch_rel.get(nrel)
                    stack.append((Path(e.path), nrel, nb))
                    continue
                if not e.is_file(follow_symlinks=True):
                    continue          # 断链、FIFO、symlink 到目录：与 rglob 行为一致地忽略
                size = e.stat(follow_symlinks=True).st_size
            except OSError:
                continue
            stats.files += 1
            stats.bytes += size
            if bucket is not None:
                sub[bucket] = sub.get(bucket, 0) + size

    for w in outside:
        st, _ = scan_tree(w)
        sub[w] = st.bytes
    return stats, sub


def path_size_bytes(p: Path) -> int:
    """文件或目录体积；读取失败按 0 处理，供展示与保守预检使用。"""
    try:
        p = Path(p)
        if p.is_file():
            return p.stat().st_size
        if p.is_dir():
            stats, _ = scan_tree(p)
            return stats.bytes
    except Exception:
        pass
    return 0


def dir_size_mb(p: Path) -> float:
    """目录体积（MB）。命令行用户靠它判断源码副本要不要留着。"""
    return path_size_bytes(Path(p)) / MIB


def format_bytes(n: int) -> str:
    n = max(0, int(n))
    if n >= 1024 * MIB:
        return "%.1f GB" % (n / (1024 * MIB))
    if n >= MIB:
        return "%.1f MB" % (n / MIB)
    return "%.1f KB" % (n / 1024)


def estimate_install_bytes(root: Path, pairs, targets, index=None) -> int:
    """估算备份 + 新源码 + skill 副本的峰值写入，并加安全余量。

    备份那一份在 link 模式下几乎不占数据块（只增目录项），所以按 2% 计；
    copy 模式下仍按全量算，宁可估高也不能在写到一半时才 ENOSPC。

    index 传入 SourceIndex 时直接复用它的扫描结果，**不再重复遍历**。
    """
    if index is not None:
        stats = index.stats
        sub = {d: index.skill_bytes.get(n, 0) for n, d in pairs}
    else:
        stats, sub = scan_tree(root, watch=[d for _, d in pairs])
    target_bytes = sum(path_size_bytes(Path(p)) for p in targets)
    if config.backup_mode() == "link":
        backup_bytes = int(target_bytes * 0.02) + 8 * MIB
    else:
        backup_bytes = target_bytes
    new_bytes = stats.bytes + sum(sub.values())
    registry_bytes = path_size_bytes(config.REGISTRY)
    payload = backup_bytes + new_bytes + registry_bytes
    return payload + max(DISK_SAFETY_BYTES, int(payload * 0.10))


# ---------- 内容指纹 ----------

def tree_fingerprint(root: Path, content: bool = False) -> tuple:
    """目录指纹，用于 verify 判断本地是否被改过。返回 ``(digest, TreeStats)``。

    指纹 = 排序后的「相对路径 + 大小」行；``content=True`` 时对小文件
    （<= FP_CONTENT_MAX）再拼上内容哈希 —— 改一个字符也能发现，
    代价是要把小文件读一遍。

    调用方必须成对一致：安装时用什么模式记录，verify 就用什么模式校验，
    所以摘要前缀里写死了模式标记，避免两种模式互相比较得出假结论。
    """
    root = Path(root)
    h = hashlib.sha256()
    stats = TreeStats()
    if not root.exists():
        return "", stats
    h.update(b"c" if content else b"s")
    rows = []
    for d, e in iter_tree(root):
        try:
            if e.is_dir(follow_symlinks=False):
                stats.dirs += 1
                continue
            if not e.is_file(follow_symlinks=True):
                continue
            size = e.stat(follow_symlinks=True).st_size
        except OSError:
            continue
        stats.files += 1
        stats.bytes += size
        try:
            rel = os.path.relpath(e.path, root).replace(os.sep, "/")
        except Exception:
            rel = e.name
        row = "%s\x00%d" % (rel, size)
        if content and 0 < size <= config.FP_CONTENT_MAX:
            try:
                with open(e.path, "rb") as f:
                    row += "\x00" + hashlib.sha256(f.read()).hexdigest()[:16]
            except OSError:
                pass
        rows.append(row)
    rows.sort()
    for row in rows:
        h.update(row.encode("utf-8", "replace"))
        h.update(b"\n")
    return h.hexdigest(), stats


# ---------- 磁盘 ----------

def disk_free_bytes(path: Path) -> int:
    """取 path 所在卷的可用空间；path 尚不存在时向上找最近的已存在父目录。"""
    p = Path(path)
    while not p.exists() and p.parent != p:
        p = p.parent
    return shutil.disk_usage(p).free


def ensure_disk_space(path: Path, required: int, purpose: str) -> int:
    free = disk_free_bytes(path)
    if free < required:
        raise OSError(errno.ENOSPC,
                      "%s磁盘空间不足：预计还需约 %s，当前可用 %s"
                      % (purpose, format_bytes(required), format_bytes(free)))
    return free


def classify_write_error(e) -> str:
    """本地写入失败的人话提示（DSH 会单独区分「磁盘满」，这里也分开）"""
    s = str(e).lower()
    if "no space" in s or "空间" in s or "disk full" in s or "not enough" in s:
        return "磁盘可能满了。清理空间后重试。"
    if ("permission" in s or "errno 13" in s or "access is denied" in s
            or "拒绝访问" in s or "being used" in s or "占用" in s):
        return "文件被占用或没有权限。关掉正在用它的程序（编辑器/终端）再试。"
    return "本地写入失败。检查磁盘空间、权限，以及文件是否被其他程序占用。"
