# -*- coding: utf-8 -*-
"""事务：文件系统 + 清单的原子提交与回滚。

v3 的 manifest 同时记录「操作前存在」与「不存在」的目标：
存在的还原内容，不存在的删除新建出来的目录。v2 只备份已存在的路径，
全新安装失败时 expected==0，回滚形同虚设、还会误判成功并删掉备份。

v4 增加第三种备份介质 ``GHPM_BACKUP_MODE=rename``（默认仍是 link）：

    link   同卷内建硬链接树。几乎不占空间，但**仍然要遍历整棵目录**。
    rename 把目标目录整个 rename 到备份目录，回滚时 rename 回来。
           同卷 O(1)、零遍历 —— 代价是写入期间原目录**暂时不在原位**。
    copy   整目录复制，行为与 v3.1 一致。

为什么默认不换成 rename：它更快，但会改变「写入期间原目录还在不在」这个
可观察行为（编辑器和别的进程会看不到目录）。收益（大规模目录省一次遍历）
换来一个行为变化，不值得默认开启，交给需要的人用环境变量打开。

无论哪种模式，apply 阶段都必须是**整目录替换**（rmtree + 写入），
不能原地改写 —— 硬链接备份会顺着 inode 把备份一起改掉。
"""
from __future__ import annotations

import errno
import json
import os
import shutil
import sys
import time
from pathlib import Path

from . import config
from .errors import E_WRITE, UnsafePathError
from .pathguard import validate_managed_path
from .util import (atomic_copy, atomic_write_bytes, classify_write_error, emit, now,
                   remove_path, safe_key, _new_token)


def read_manifest(bd: Path) -> dict:
    bd = Path(bd)
    mf = bd / "_manifest.json"
    if not mf.exists():
        return {}
    try:
        d = json.loads(mf.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def backup_mode() -> str:
    return config.backup_mode()


def _backup_copy(src, dst) -> str:
    """copytree 的 copy_function：优先 os.link，失败退回 copy2。

    硬链接失败很常见（跨 EXDEV、目录软链、FAT/exFAT），这些都必须静默降级 ——
    备份慢只是慢，备份失败会让整个事务直接拒绝写入。
    """
    if backup_mode() == "link":
        try:
            os.link(src, dst)
            return dst
        except (OSError, NotImplementedError, AttributeError):
            pass
    return shutil.copy2(src, dst)


def _same_volume(a: Path, b: Path) -> bool:
    """a 与 b 是否在同一卷。rename 只同卷可用（跨卷会 EXDEV）。"""
    try:
        return os.stat(a).st_dev == os.stat(b).st_dev
    except OSError:
        return False


class Transaction:
    """文件系统 + 清单的原子事务。

    用法：
        tx = Transaction(repo, name, "install")
        tx.track([...目标路径...])     # 必须在实际改动之前
        tx.begin()                     # 备份已存在的 + 记录不存在的 + 快照清单
        try:
            ...写盘...; save(data)
        except Exception:
            tx.rollback(); raise
        tx.commit()
    """

    def __init__(self, key: str, name: str = "", op: str = ""):
        self.key = key or name or "ghpm"
        self.name = name or self.key
        self.op = op
        self.bd: Path | None = None
        self.paths: list = []
        self.done = False

    def track(self, paths) -> None:
        for p in paths:
            p = Path(p)
            if p not in self.paths:
                self.paths.append(p)

    # ---- 备份 ----

    def _save_item(self, bd: Path, p: Path, i: int, used: set) -> dict:
        bn = p.name or ("item-%d" % i)
        if bn in used:
            bn = "%s-%d" % (p.name or "item", i)
        used.add(bn)
        existed = p.exists()
        entry = {"existed": existed, "backup": None,
                 "kind": ("dir" if (existed and p.is_dir()) else "file")}
        if not existed:
            return entry
        mode = backup_mode()
        try:
            if mode == "rename" and p.is_dir() and not p.is_symlink() \
                    and _same_volume(p, bd):
                # 同卷整目录 rename：O(1)，不遍历。回滚时再 rename 回来。
                os.replace(str(p), str(bd / bn))
                entry["mode"] = "rename"
            elif p.is_dir():
                shutil.copytree(p, bd / bn, dirs_exist_ok=True, copy_function=_backup_copy)
                entry["mode"] = "link" if backup_mode() == "link" else "copy"
            else:
                _backup_copy(p, bd / bn)
                entry["mode"] = "link" if backup_mode() == "link" else "copy"
            entry["backup"] = bn
        except Exception as e:
            # 备份失败的项在回滚时会被记为「没恢复」，从而保住备份不删
            print("  [警告] 备份 %s 失败: %s" % (p, e), file=sys.stderr)
            entry["error"] = str(e)[:120]
        return entry

    def begin(self) -> Path:
        """建备份目录、拷走已存在的目标、快照清单文件，写 manifest。"""
        bd = config.WB / (".ghpm-backup-%s-%s-%s" % (
            safe_key(self.key), time.strftime("%Y%m%d-%H%M%S"), _new_token()[:6]))
        bd.mkdir(parents=True, exist_ok=True)
        items: dict = {}
        used: set = set()

        for i, p in enumerate(self.paths):
            items[str(p)] = self._save_item(bd, p, i, used)
        # 清单文件也是事务的一部分：写盘成功但 save() 失败时，
        # 靠这份快照把 github-projects.json 还原回去。
        # 它是普通文件，rename 分支只对目录生效，所以天然走 link/copy，
        # 不会在事务期间从磁盘上消失。
        items[str(config.REGISTRY)] = self._save_item(
            bd, config.REGISTRY, len(self.paths), used)

        manifest = {"version": 5, "name": self.name, "repo": self.key,
                    "op": self.op, "at": now(), "backup_mode": backup_mode(),
                    "items": items}
        atomic_write_bytes(bd / "_manifest.json",
                           json.dumps(manifest, ensure_ascii=False, indent=2))
        self.bd = bd
        failed = [p for p, entry in items.items() if entry.get("error")]
        if failed:
            # 只在完整备份后才允许进入 applying；此时原目标尚未改动，可直接清理备份。
            # 若已经用 rename 搬走了部分目录，必须先搬回来再清理备份目录。
            self._undo_renames(items, bd)
            shutil.rmtree(bd, ignore_errors=True)
            self.bd = None
            raise OSError(errno.EIO, "备份失败，未开始写入：%s" % "、".join(failed[:5]))
        return bd

    @staticmethod
    def _undo_renames(items: dict, bd: Path) -> None:
        """备份中途失败时，把已经 rename 走的目录搬回原位。"""
        for dest, entry in items.items():
            if entry.get("mode") != "rename" or not entry.get("backup"):
                continue
            src = bd / entry["backup"]
            try:
                if src.exists() and not Path(dest).exists():
                    os.replace(str(src), str(dest))
            except Exception:
                pass

    def rollback(self) -> dict:
        return restore_backup(self.bd) if self.bd else {
            "restored": [], "failed": [{"path": "", "error": "事务没有备份目录"}]
        }

    def commit(self, purge: bool = True) -> None:
        """事务成功。默认清掉备份；remove 传 purge=False 保留备份当撤销手段。"""
        self.done = True
        if purge and self.bd:
            shutil.rmtree(self.bd, ignore_errors=True)
            self.bd = None


def restore_backup(bd, strict: bool = True) -> dict:
    """按 manifest 恢复事务，返回逐项成功/失败明细。

    existed=true  → 从备份还原（当前是半截写入就先删掉再放回）
    existed=false → 删除事务新建出来的目录/文件（v2 漏掉的那一半）
    兼容 v2 manifest（值是备份目录名的字符串，一律视为 existed=true）。

    strict=True（默认）时每个还原目标都要通过 containment 校验：
    manifest 里的路径是历史写入的，不能假定它一定落在 WB 内。越界项记 failed
    而不是照着删 —— 宁可回滚不完整，也不能让一个坏 manifest 删掉工作区之外的东西。
    """
    bd = Path(bd)
    result = {"restored": [], "failed": [], "skipped": []}
    if not bd.exists():
        result["failed"].append({"path": str(bd), "error": "备份目录不存在"})
        return result
    manifest = read_manifest(bd)
    items = manifest.get("items", {}) if isinstance(manifest, dict) else {}
    if not isinstance(items, dict) or not items:
        result["failed"].append({"path": str(bd / "_manifest.json"),
                                 "error": "manifest 缺失、损坏或没有恢复项"})
        return result
    for dest, entry in items.items():
        if isinstance(entry, str):          # v2 老备份
            entry = {"existed": True, "backup": entry}
        if not isinstance(entry, dict):
            result["failed"].append({"path": str(dest), "error": "manifest 项格式无效"})
            continue
        dest_p = Path(dest)
        if strict:
            try:
                validate_managed_path(dest_p, config.WB, "回滚目标")
            except UnsafePathError as e:
                print("  [警告] %s" % e, file=sys.stderr)
                result["skipped"].append({"path": str(dest_p), "error": str(e)})
                result["failed"].append({"path": str(dest_p), "error": str(e)})
                continue
        bn = entry.get("backup")
        src = (bd / bn) if bn else None
        try:
            if entry.get("existed"):
                if not src or not src.exists():
                    reason = entry.get("error") or "备份文件缺失"
                    print("  [警告] 回滚 %s 失败：%s" % (dest_p, reason), file=sys.stderr)
                    result["failed"].append({"path": str(dest_p), "error": str(reason)})
                    continue
                remove_path(dest_p)
                if entry.get("mode") == "rename" and src.is_dir():
                    # 备份就是原目录本身，直接搬回去（同卷 rename）
                    try:
                        os.replace(str(src), str(dest_p))
                    except OSError:
                        shutil.move(str(src), str(dest_p))
                elif src.is_dir():
                    shutil.copytree(src, dest_p)
                else:
                    atomic_copy(src, dest_p)
            else:
                # 事务新建出来的：删除即恢复到"原先不存在"的状态。
                remove_path(dest_p)
            result["restored"].append(str(dest_p))
        except Exception as e:
            print("  [警告] 回滚 %s 失败: %s" % (dest_p, e), file=sys.stderr)
            result["failed"].append({"path": str(dest_p), "error": str(e)[:200]})
    return result


def report_rollback(bd: Path, result: dict, e: Exception, code: str = E_WRITE) -> None:
    """统一输出回滚结果；只要 failed 非空就保留备份。"""
    restored = result.get("restored", [])
    failed = result.get("failed", [])
    expected = len(restored) + len(failed)
    hint = classify_write_error(e)
    if not failed:
        shutil.rmtree(bd, ignore_errors=True)
        emit("failed", "写入失败，已回滚 %d 项（恢复到操作前状态）" % len(restored),
             percent=100, code=code, detail=str(e)[:160], hint=hint,
             data={"rollback": result})
    else:
        failed_names = "、".join(Path(x.get("path", "?")).name or x.get("path", "?")
                                 for x in failed[:5])
        emit("failed", "写入失败，且回滚不完整（%d/%d）" % (len(restored), expected),
             percent=100, code=code, detail=str(e)[:160], backup=str(bd),
             hint="%s 未恢复：%s。原状态备份仍保留在 %s，可用 `ghpm rollback %s` 手动恢复"
                  % (hint, failed_names, bd, bd), data={"rollback": result})


def move_or_copy_tree(src: Path, dst: Path) -> str:
    """把 src 整棵树搬到 dst，优先 rename，跨卷再退回 copytree。

    为什么重要：v3.2 的 apply 流程是
        ZIP → 解压到 tmp → copytree 到 source_dir → copytree 每个 skill
    同一份源码被完整写了**两遍**（解压一遍、拷进 source 一遍）。
    解压根本来就是这次下载的产物，之后没人再用，直接 rename 进 source_dir
    即可 —— 同卷 O(1)，跨卷时 shutil.move 自己会退回「复制 + 删除」，
    行为与 v3.2 等价而不再多留一份临时数据。

    返回实际使用的方式：``"rename"`` 或 ``"copy"``（便于日志与测试断言）。
    """
    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists() and _same_volume(src, dst.parent):
        try:
            os.replace(str(src), str(dst))
            return "rename"
        except OSError:
            pass
    shutil.copytree(src, dst, dirs_exist_ok=True)
    return "copy"
