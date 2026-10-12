# -*- coding: utf-8 -*-
"""verify：清单 ↔ 磁盘 ↔ 远端 的三方一致性检查（只读）。"""
from __future__ import annotations

import json

from .. import config
from ..registry import find_project, load
from ..remote import fetch_repo_infos
from ..util import emit
from ..verifier import verify_all

_ICON = {"ok": "✓", "warn": "!", "fail": "✗"}


def cmd_verify(args):
    """不写盘、不删文件。发现 FAIL 时返回非零退出码（由 cli 判断）。"""
    data = load()
    targets = data.get("projects", [])
    if getattr(args, "name", None):
        hit = find_project(data, args.name)
        if not hit:
            emit("failed", "未找到项目", percent=100, code="E_NOT_FOUND",
                 detail=args.name, hint="用 `ghpm list` 看看已登记的项目名")
            print("未找到项目：%s" % args.name)
            return 1
        targets = [hit]

    remote_infos = None
    if getattr(args, "remote", False) and targets:
        ttl = 0 if getattr(args, "fresh", False) else config.CACHE_TTL
        remote_infos, _errors = fetch_repo_infos(
            [p.get("repo") or p.get("name") for p in targets], ttl=ttl,
            progress=lambda d, t, r: emit(
                "checking", "核对远端 %d/%d · %s" % (d, t, r),
                percent=int(80 * d / max(1, t))))
        remote_infos = remote_infos or {}

    scoped = dict(data)
    scoped["projects"] = targets
    result = verify_all(scoped, remote_infos=remote_infos)

    if getattr(args, "json", False):
        print(json.dumps(result, ensure_ascii=False))
    else:
        _render(result, remote=bool(getattr(args, "remote", False)))

    summary = result["summary"]
    emit("done", "%d 个项目：%d 正常，%d 警告，%d 失败"
         % (result["checked"], summary["ok"], summary["warn"], summary["fail"]),
         percent=100, ok=result["ok"],
         hint=None if result["ok"] else "有项目数据不一致，逐项见 data.projects[].findings",
         data=result)
    return 0 if result["ok"] else 1


def _render(result: dict, remote: bool = False) -> None:
    print("GHPM Verify%s\n" % ("（含远端比对）" if remote else "（仅本地）"))
    if not result["projects"]:
        print("清单为空，没有可校验的项目。")
    for proj in result["projects"]:
        print("%s %s  [%s]" % (_ICON.get(proj["status"], "?"), proj["repo"],
                               proj["status"].upper()))
        for f in proj["findings"]:
            if f["level"] == "ok":
                continue                      # 正常项不刷屏，只看问题
            print("     %s %-20s %s" % (_ICON.get(f["level"], "?"), f["code"], f["message"]))
            if f.get("path"):
                print("       %s" % f["path"])
    if result["orphans"]:
        print("\n未被任何项目认领的 skill 目录（可能是手动放的，也可能是孤儿）：")
        for o in result["orphans"]:
            print("  ? %s" % o)
    s = result["summary"]
    print("\n汇总：%d 正常，%d 警告，%d 失败" % (s["ok"], s["warn"], s["fail"]))
    if s["fail"]:
        print("有 FAIL 项：清单与磁盘已经不一致，建议 `ghpm remove` 后重装，"
              "或用 `ghpm rollback <备份目录>` 恢复。")
    else:
        print("清单与磁盘一致。")
