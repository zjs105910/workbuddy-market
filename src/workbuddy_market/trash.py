# -*- coding: utf-8 -*-
"""trash —— 回收站（v2.12 R4 自 market_core.py 逐字迁入）。

职责：把「删除」统一变成「搬进 .trash/ + 记账」，并按配置清理。
纪律与原状完全一致：

  · `.trash/.index.json` 是**不可信状态文件**：一切路径必须过 `_trash_entry()`
    （单层 basename + ensure_child），绝不 `TRASH_DIR / name` 后删（约定 3）；
  · `move_to_trash()` 的 rename 成功即事实，索引写失败只降级告警（约定 4）；
  · `prune_trash` 的统计只算真删成功的（约定 5）。

v2.13（跨卷原子化）：`WBM_HOME` 与 `WBM_STATE_HOME` 允许配置到**不同磁盘**，
`shutil.move()` 跨卷会退化成 copy + delete —— 中途崩掉两边都不完整，
不再是文档声称的「近似原子搬移」。现在显式分两条路：

  · 同卷 → `os.rename()`（原子，与原行为等价）；
  · 跨卷 → staging 复制（.trash 内 `.partial`）→ 结构校验（相对路径集合 +
    每文件大小）→ 同卷原子 rename 落位 → **最后才删源**。
    任何一步失败：清掉 .partial、源目录原样保留、返回 None。

注入点接缝（v2.12 R4）：
  · `_measure()` / 跨卷校验用的 `_scan` 仍在 core（selftest 崩溃注入点，
    第 24B 节盯防），因此在调用点晚绑定 ``import market_core`` ——
    patch ``core._scan`` 对回收站侧的调用依然有效，与 v2.11 前
    「core 侧直接调用」的语义一致；
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


def _same_volume(a: Path, b: Path) -> bool:
    """两个路径是否在同一文件系统卷上。

    Windows 按盘符比（splitdrive；UNC 路径取 \\server\\share 整段），
    POSIX 按 st_dev 比。stat 失败时**保守按跨卷处理** —— 宁可走慢的
    校验搬移，也不赌一次静默退化成 copy+delete 的「假原子」。
    """
    if os.name == "nt":
        da = os.path.splitdrive(str(a))[0].casefold()
        db = os.path.splitdrive(str(b))[0].casefold()
        return bool(da) and da == db
    try:
        return os.stat(str(a)).st_dev == os.stat(str(b)).st_dev
    except OSError:
        return False


def _is_dir_entry(path: Path) -> bool:
    """目录判定看 lstat，不看 is_dir()（约定 18：is_dir() 会跟随链接）。"""
    try:
        stt = path.lstat()
    except OSError:
        return False
    return stat.S_ISDIR(stt.st_mode) and not path.is_symlink() and not _is_reparse(stt)


def _verify_tree_copy(src: Path, staging: Path) -> None:
    """跨卷搬移的校验：相对路径集合一致 + 每个文件大小一致。

    刻意**不比内容哈希**：回收站允许到 2GB，全量哈希的代价与「搬个家」
    不成比例；而且 staging → dst 是同卷原子 rename，校验通过后内容
    不会再变。安全语义（能不能覆盖 / 卸载）依旧由 needs_exact 的
    tree_hash 负责，跟这里的完整性校验是两回事。
    抛 OSError 即校验不过（staging 会被调用方清掉，源不受影响）。
    """
    import market_core as _core          # noqa: PLC0415 —— 注入点晚绑定，见模块 docstring
    si, _ = _core._scan(src, on_error="raise")
    ti, _ = _core._scan(staging, on_error="raise")
    if set(si) != set(ti):
        miss = sorted(set(si) - set(ti))[:3]
        raise OSError(f"跨卷搬移校验失败：目标缺少 {miss}")
    for rel, (sz, _mt) in si.items():
        if ti[rel][0] != sz:
            raise OSError(f"跨卷搬移校验失败：大小不一致 {rel}")


def _move_cross_volume(path: Path, dst: Path) -> None:
    """跨卷搬移：shutil.move 会退化成 copy + delete —— 中途崩掉两边都不完整。

    显式走「staging 复制 → 结构校验 → 同卷原子 rename → 删源」：

      1. 复制到 .trash 内的 `<目标名>.partial`（与 dst 同卷，rename 是原子的）；
      2. 目录：copytree(symlinks=True) + 结构校验；文件：copy2 + 大小校验；
      3. rename(.partial → dst) 原子落位；
      4. **最后才删源** —— 前面任何一步失败，源目录原样保留。

    边界：目录树里或条目本身含重解析点（symlink / junction）时拒绝跨卷
    搬移 —— copytree 无法保真复制 junction，宁可让调用方拿到失败
    （同卷 rename 路径不受影响）。删源失败同样按失败上报：此刻旧内容
    已完整躺在回收站里，调用方中止操作不会丢任何东西。
    """
    staging = dst.with_name(dst.name + ".partial")
    is_dir = _is_dir_entry(path)
    if path.is_symlink() or _is_reparse(path.lstat()):
        raise OSError("条目是符号链接 / junction，跨卷搬移无法保真复制，拒绝")
    try:
        shutil.rmtree(staging, ignore_errors=True)   # 上次中断的残留
        if is_dir:
            _files, links = _core_scan_links(path)   # 事前拦截树内重解析点
            if links:
                raise OSError(
                    f"目录含 {len(links)} 个符号链接 / junction，"
                    f"跨卷搬移无法保真复制，拒绝：{links[:3]}")
            shutil.copytree(str(path), str(staging), symlinks=True)
            _verify_tree_copy(path, staging)
        else:
            shutil.copy2(str(path), str(staging))
            if staging.stat().st_size != path.stat().st_size:
                raise OSError("跨卷搬移校验失败：文件大小不一致")
        try:
            os.rename(str(staging), str(dst))        # 同卷，原子
        except OSError:
            shutil.move(str(staging), str(dst))      # 兜底（理论上不该触发）
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    # 内容已确认完整落在 dst，最后才删源
    try:
        if is_dir:
            shutil.rmtree(str(path))
        else:
            path.unlink()
    except OSError as exc:
        raise OSError(f"跨卷搬移已落位但删源失败（旧内容在 {dst.name}）：{exc}") from exc


def _core_scan_links(path: Path):
    import market_core as _core          # noqa: PLC0415 —— 注入点晚绑定，见模块 docstring
    return _core._scan(path, on_error="raise")


def move_to_trash(path: Path, reason: str = "", index: "TrashIndex | None" = None) -> Path | None:
    """统一入口：把一个目录/文件整个搬进回收站，并记账。

    同卷走 `os.rename()`（原子）；跨卷走 `_move_cross_volume()` 的
    「复制 → 校验 → 原子落位 → 删源」（v2.13）。两条路的失败都如实
    返回 None —— 此时**源目录原样未动**，调用方可以放心中止。

    刻意用 rename 而不是 rmtree：O(1)、不遍历几百个文件，
    也不会触发宿主/沙箱的「批量删除」保护。
    体积在搬之前就算好写进索引 —— 否则每次刷新状态都要重新 rglob 整个回收站。

    **事务语义**：搬移成功之后，磁盘状态就已经变了。索引只是缓存，
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
        if _same_volume(path, TRASH_DIR):
            os.rename(str(path), str(dst))           # 同卷：原子搬移
        else:
            _move_cross_volume(path, dst)            # 跨卷：复制-校验-落位-删源
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
