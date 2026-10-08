# -*- coding: utf-8 -*-
"""trash —— 回收站（v2.12 R4 自 market_core.py 逐字迁入）。

职责：把「删除」统一变成「搬进 .trash/ + 记账」，并按配置清理。
纪律与原状完全一致：

  · `.trash/.index.json` 是**不可信状态文件**：一切路径必须过 `_trash_entry()`
    （单层 basename + ensure_child），绝不 `TRASH_DIR / name` 后删（约定 3）；
  · `move_to_trash()` 的 rename 成功即事实，索引写失败只降级告警（约定 4）；
  · `prune_trash` 的统计只算真删成功的（约定 5）。

注入点接缝（v2.12 R4）：
  · `_measure()` 用的 `_scan` 仍在 core（selftest 崩溃注入点，第 24B 节盯防），
    因此在调用点晚绑定 ``import market_core`` —— patch ``core._scan`` 对
    回收站侧的调用依然有效，与 v2.11 前「core 侧直接调用」的语义一致；
  · `prune_trash()` 的 `say()` 同理（core 的 CLI 输出小工具）。
  包内互调（TrashIndex→_save_trash_index 等）走本模块命名空间，
  patch 这些名字请 patch ``workbuddy_market.trash``（selftest 已按此调整）。
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import time
from pathlib import Path

from .errors import ConfigError
from .fsutil import atomic_write_text, read_json
from .paths import TRASH_DIR
from .config import ensure_child, load_config
from .logging import log
from .scanner import _is_reparse

TRASH_INDEX_PATH = TRASH_DIR / ".index.json"

# 索引里不允许出现的字符：路径分隔符、盘符、以及 Windows 的非法字符
_TRASH_NAME_BAD = ("/", "\\", ":", "\x00")


def _load_trash_index() -> dict:
    d = read_json(TRASH_INDEX_PATH, None)
    if not isinstance(d, dict) or not isinstance(d.get("items"), dict):
        return {"version": 1, "items": {}}
    return d


def _save_trash_index(idx: dict) -> None:
    idx["version"] = 1
    atomic_write_text(TRASH_INDEX_PATH, json.dumps(idx, ensure_ascii=False, indent=2) + "\n")


def _trash_entry(name) -> Path | None:
    """把索引里的一个名字解析成 .trash 内的真实路径；不合法一律返回 None。

    .index.json 是普通 JSON 文件，手工能改、也可能被投毒的包写坏 ——
    所以这里**按不可信状态文件处理**，读的时候就把恶意输入挡住：

      · 必须是字符串、非空、无 NUL
      · 不能是 "." / ".." / 索引自己
      · 必须是单层 basename：含 / \\ : 的一律拒绝
      · 最后再过 ensure_child()，把结果钉死在 TRASH_DIR 之内

    v2 是直接 `TRASH_DIR / name` 然后 rmtree —— 索引里写一条 "../../X"
    就能删掉市场根之外的真实目录。
    """
    if not isinstance(name, str) or not name:
        return None
    if name in (".", "..") or name == TRASH_INDEX_PATH.name:
        return None
    if any(ch in name for ch in _TRASH_NAME_BAD):
        return None
    if Path(name).name != name:            # 兜底：任何形式的路径成分
        return None
    try:
        return ensure_child(TRASH_DIR, TRASH_DIR / name)
    except ConfigError:
        return None


def _measure(path: Path) -> tuple:
    """(字节数, 文件数)。只用于回收站记账，所以走一次 _scan 就够。

    `_scan` 走 core 晚绑定：它是 selftest 的崩溃/计数注入点（core._scan），
    搬进包之后也必须保持「patch core._scan 能拦到回收站的这次扫描」。
    """
    import market_core as _core          # noqa: PLC0415 —— 注入点晚绑定，见模块 docstring
    try:
        if path.is_dir():
            files, _links = _core._scan(path)
            return sum(v[0] for v in files.values()), len(files)
        return path.stat().st_size, 1
    except OSError:
        return 0, 0


class TrashIndex:
    """回收站索引的内存视图 —— 批量操作只落一次盘。

    `move_to_trash()` 原来是「搬一个 → 读索引 → 改 → 原子写」。批量卸载 12 个
    skill 就是 12 次读 + 12 次原子写（每次都带 fsync），纯属把同一份 JSON 反复
    重写。把索引提到内存里，整批做完 flush 一次。

    安全性上不比原来差：万一中途崩掉，那些目录只是「没登记」，
    `trash_stats()` 的未登记补录会把它们收进来。
    """

    def __init__(self):
        self._idx = _load_trash_index()
        self._dirty = False

    @property
    def items(self) -> dict:
        return self._idx["items"]

    def record(self, name: str, entry: dict) -> None:
        self.items[name] = entry
        self._dirty = True

    def forget(self, name: str) -> None:
        if self.items.pop(name, None) is not None:
            self._dirty = True

    @property
    def dirty(self) -> bool:
        return self._dirty

    def flush(self) -> bool:
        if not self._dirty:
            return False
        try:
            _save_trash_index(self._idx)
        except (OSError, ConfigError) as exc:
            log("warn", "trash", f"回收站索引回写失败（{exc}），下次刷新状态会自动补录")
            return False
        self._dirty = False
        return True


def move_to_trash(path: Path, reason: str = "", index: "TrashIndex | None" = None) -> Path | None:
    """统一入口：把一个目录/文件整个 rename 进回收站，并记账。

    刻意用 rename 而不是 rmtree：O(1)、不遍历几百个文件，
    也不会触发宿主/沙箱的「批量删除」保护。
    体积在搬之前就算好写进索引 —— 否则每次刷新状态都要重新 rglob 整个回收站。

    **事务语义**：rename 成功之后，磁盘状态就已经变了。索引只是缓存，
    写索引失败**不能**让整个调用方判成失败 —— 否则会出现「旧版本已经被搬进
    回收站，调用方却以为操作没发生」。所以这里降级为记一条 warn 并照常返回，
    索引由 trash_stats() 的「未登记项自动补录」自愈。

    index: 传一个 `TrashIndex` 就只在内存里记账，由调用方在整批做完后 flush；
           不传就当场读写索引（单次操作的默认行为）。
    """
    path = Path(path)
    if not path.exists():
        return None
    TRASH_DIR.mkdir(parents=True, exist_ok=True)

    size, nfiles = _measure(path)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    tag = f"{stamp}__{path.name}"
    if reason:
        tag += f"__{reason}"
    dst = TRASH_DIR / tag
    n = 1
    while dst.exists():
        dst = TRASH_DIR / f"{tag}.{n}"
        n += 1
    try:
        shutil.move(str(path), str(dst))
    except OSError as exc:
        log("error", "trash", f"回收 {path} 失败：{exc}")
        return None

    entry = {"bytes": size, "files": nfiles, "at": time.time(),
             "reason": reason or "unknown", "origin": str(path)}
    if index is not None:
        index.record(dst.name, entry)
    else:
        own_idx = TrashIndex()
        own_idx.record(dst.name, entry)
        own_idx.flush()
    return dst


def trash_config() -> dict:
    """回收站清理策略，来自 market.config.json 的 trash 段。"""
    try:
        cfg = load_config()
    except ConfigError:
        cfg = {}
    t = cfg.get("trash") or {}
    return {
        "max_age_days": float(t.get("maxAgeDays", 30) or 0),
        "max_bytes": int(t.get("maxSizeBytes", 2 * 1024 ** 3) or 0),
        "protect_modified": bool(t.get("protectModified", True)),
    }


def trash_stats() -> dict:
    """回收站清单。

    v2 是每次都对整个 .trash 做 rglob，回收站一大（配置允许到 2GB）状态页就明显变慢。
    现在优先读索引；只有「磁盘上有、索引里没有」的情况（比如你手工往里拖了东西）
    才重新扫一遍，并顺手补进索引。

    索引里的非法条目名（路径穿越之类）会被剔除并记警告，绝不按它去访问磁盘。
    """
    if not TRASH_DIR.is_dir():
        return {"count": 0, "bytes": 0, "items": []}

    idx = _load_trash_index()
    recorded = idx["items"]
    items, total = [], 0
    seen = set()
    dirty = False

    for name, rec in list(recorded.items()):
        target = _trash_entry(name)
        if target is None:
            log("warn", "trash", f"索引里的条目名非法，已剔除：{name!r}")
            del recorded[name]
            dirty = True
            continue
        if not target.exists():
            continue                       # 已被手工删掉 → 稍后从索引里剔除
        seen.add(name)
        if not isinstance(rec, dict):
            rec = {}
        size = int(rec.get("bytes", 0) or 0)
        at = float(rec.get("at", 0) or 0) or _safe_mtime(target)
        items.append({"name": name, "size": size, "mtime": at,
                      "reason": rec.get("reason", "")})
        total += size

    # 磁盘上有、索引里没有的（手工拖进去的 / 索引丢了）
    try:
        children = list(TRASH_DIR.iterdir())
    except OSError:
        children = []
    for child in children:
        if child.name == TRASH_INDEX_PATH.name or child.name in seen:
            continue
        size, nfiles = _measure(child)
        at = _safe_mtime(child)
        items.append({"name": child.name, "size": size, "mtime": at, "reason": "未登记"})
        recorded[child.name] = {"bytes": size, "files": nfiles, "at": at,
                                "reason": "未登记", "origin": ""}
        total += size
        seen.add(child.name)
        dirty = True

    # 索引里有、磁盘上没了 → 剔除
    for name in [n for n in list(recorded) if n not in seen]:
        del recorded[name]
        dirty = True

    if dirty:
        try:
            _save_trash_index(idx)
        except (OSError, ConfigError) as exc:
            log("warn", "trash", f"回收站索引回写失败（{exc}），本次只在内存里修正")

    items.sort(key=lambda x: x["mtime"])
    return {"count": len(items), "bytes": total, "items": items}


def _safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def prune_trash(force: bool = False, quiet: bool = False) -> dict:
    """按配置清理回收站：先按保留天数，再按容量上限（从最旧的开始）。

    这是本工具唯一的「真删除」，只作用于 .trash/ 内部，
    而且只在超过阈值时才动 —— 不配阈值就等于永不清理。

    统计口径：**removed 只数真正删成功的**，freed 只累加这些项的字节，
    删失败的进 failed。v2 用 `except OSError: continue` 后照原计划累加，
    计划删 10 个、实际成功 8 个也会报 removed=10 / freed=500MB —— 说谎的统计
    比崩溃更麻烦。

    force=True 表示「用户明确要求清空」，此时不受保护项与阈值约束。
    """
    import market_core as _core          # noqa: PLC0415 —— say() 是 core 的 CLI 输出小工具
    conf = trash_config()
    st = trash_stats()
    idx = _load_trash_index()
    candidates = []                       # [(item, why)]
    protected = []                        # 受保护、本轮放过的
    now = time.time()

    def _is_protected(item) -> bool:
        return conf["protect_modified"] and "modified" in str(item.get("reason", ""))

    keep = list(st["items"])

    # 1) 超过保留天数（force 时不必判断：最后一步会全清）
    if conf["max_age_days"] > 0 and not force:
        cutoff = now - conf["max_age_days"] * 86400
        rest = []
        for it in keep:
            if it["mtime"] >= cutoff:
                rest.append(it)
            elif _is_protected(it):
                protected.append(it)
                rest.append(it)
            else:
                candidates.append((it, "超过保留天数"))
        keep = rest

    # 2) 超过容量上限（从最旧的开始丢）
    if conf["max_bytes"] > 0 and not force:
        total = sum(i["size"] for i in keep)
        rest = []
        for it in keep:
            if total > conf["max_bytes"] and not _is_protected(it):
                total -= it["size"]
                candidates.append((it, "超过容量上限"))
            else:
                if total > conf["max_bytes"]:
                    protected.append(it)
                rest.append(it)
        keep = rest

    # 3) force：剩下的全清
    if force:
        candidates += [(i, "手动清理") for i in keep]
        keep = []

    removed_ok, removed_failed = [], []
    for item, _why in candidates:
        target = _trash_entry(item["name"])
        if target is None:
            removed_failed.append({"name": item["name"], "error": "条目名非法，拒绝删除"})
            log("error", "trash", f"拒绝删除非法条目名：{item['name']!r}")
            continue
        try:
            stt = target.lstat()
            if stat.S_ISDIR(stt.st_mode) and not target.is_symlink() and not _is_reparse(stt):
                shutil.rmtree(target)
            elif stat.S_ISDIR(stt.st_mode):
                # 重解析点（软链 / junction）：只摘掉链接本身，绝不跟进目标
                os.rmdir(str(target))
            else:
                target.unlink()
        except OSError as exc:
            removed_failed.append({"name": item["name"], "error": str(exc)})
            log("error", "trash", f"删除 {item['name']} 失败：{exc}")
            continue
        removed_ok.append(item)
        idx["items"].pop(item["name"], None)

    if removed_ok:
        try:
            _save_trash_index(idx)
        except (OSError, ConfigError) as exc:
            log("warn", "trash", f"回收站索引回写失败（{exc}）")

    freed = sum(i["size"] for i in removed_ok)
    if removed_ok and not quiet:
        _core.say(f"  回收站清理：移除 {len(removed_ok)} 项")
    if removed_ok or removed_failed:
        log("info" if not removed_failed else "warn", "trash",
            f"清理成功 {len(removed_ok)} 项（{freed} 字节）"
            + (f"，失败 {len(removed_failed)} 项" if removed_failed else ""))
    if protected:
        log("info", "trash", f"{len(protected)} 项受保护（安装后被改过），本轮不清理")

    return {"removed": len(removed_ok), "failed": len(removed_failed),
            "failedItems": removed_failed,
            "freed": freed, "kept": len(keep),
            "bytes": sum(i["size"] for i in keep),
            "protected": len(protected)}
