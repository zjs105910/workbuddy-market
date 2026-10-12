# -*- coding: utf-8 -*-
"""remove：移除项目（备份后删除，可回滚）。"""
from __future__ import annotations

import sys
from pathlib import Path

from .. import config
from ..errors import E_LOCKED, E_NOT_FOUND, E_UNSAFE_PATH, E_WRITE, UnsafePathError
from ..lock import LockSession
from ..pathguard import remove_managed_path, validate_managed_path, validate_skill_name
from ..registry import drop_project, find_project, load, save, skill_owner_map
from ..transaction import Transaction, report_rollback
from ..util import classify_write_error, emit


def cmd_remove(args):
    data = load()
    hit = find_project(data, args.name)
    if not hit:
        emit("failed", "未找到项目", percent=100, code=E_NOT_FOUND, detail=args.name)
        print("未找到项目：%s" % args.name)
        return
    ident = hit.get("repo") or hit["name"]

    def on_busy(holder):
        emit("failed", "有另一个任务正在修改，请稍后再试", percent=100, code=E_LOCKED,
             detail="占用者：%s" % holder.get("op", "?"))

    with LockSession("remove %s" % ident, on_busy=on_busy):
        # 路径全部先过 containment：清单里的 source_dir / skill_names 未必可信
        # （手工编辑、旧版本写坏、别的程序污染）。越界就整条拒绝，
        # 不能「跳过不认识的路径然后把剩下的删了」—— 那是半吊子安全。
        try:
            paths = []
            for n in hit.get("skill_names", []):
                paths.append(config.SKILLS / validate_skill_name(n))
            if hit.get("source_dir"):
                paths.append(validate_managed_path(hit["source_dir"], config.WB, "source_dir"))
            for p in paths:
                validate_managed_path(p, config.WB, "待删除路径")
        except UnsafePathError as e:
            emit("failed", "清单里的路径不合法，已拒绝删除", percent=100,
                 code=E_UNSAFE_PATH, detail=str(e),
                 hint="这通常意味着 %s 被手工改坏了。先把它改回 %s 之内的路径，"
                      "或直接手动删除。" % (config.REGISTRY, config.WB),
                 data={"repo": ident})
            raise
        paths = [Path(p) for p in paths]
        owners = skill_owner_map(data)
        for n in hit.get("skill_names", []):
            other = owners.get(n)
            if other and other.lower() != str(ident).lower():
                print("  [警告] skill %s 同时被登记在 %s 名下，本次只按本项目的记录删除。"
                      % (n, other), file=sys.stderr)

        tx = Transaction(ident, hit.get("name", ident), "remove")
        tx.track(paths)
        try:
            bd = tx.begin()
        except Exception as e:
            emit("failed", "备份失败，未删除任何文件", percent=100, code=E_WRITE,
                 detail=str(e)[:160], hint=classify_write_error(e))
            raise
        emit("backing-up", "备份待删除内容", percent=30)
        emit("applying", "删除文件", percent=60, backup=str(bd))
        try:
            for d in paths:
                remove_managed_path(d, "待删除路径")
            drop_project(data, ident)
            save(data)      # 原子提交；失败则连同删除的文件一起回滚
        except Exception as e:
            emit("rollback", "移除失败，正在回滚…", percent=90, backup=str(bd))
            restored = tx.rollback()
            report_rollback(bd, restored, e)
            raise
        # 移除成功后**保留**备份：这是唯一的撤销手段
        # （rename 模式下备份目录本身就是被删掉的那份内容，回滚是 O(1) rename）
        tx.commit(purge=False)
        print("已移除 %s，备份保留在 %s" % (hit.get("name", ident), bd))
        print("要撤销：`ghpm rollback %s`" % bd)
        emit("done", "已移除 · %s" % hit.get("name", ident), percent=100, backup=str(bd),
             data={"removed": [str(p) for p in paths], "backup": str(bd)})
