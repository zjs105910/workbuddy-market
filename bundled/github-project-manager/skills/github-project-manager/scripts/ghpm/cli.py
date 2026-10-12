# -*- coding: utf-8 -*-
"""CLI：argparse 定义与分发。

这一层只做三件事：定义参数、把参数交给命令函数、把异常翻译成退出码。
业务逻辑一行都不在这里 —— v3.2 的 cmd_update 同时干着参数解析、找项目、
批量查询、判断 sha、错误处理、调用 install、统计、输出、emit 九件事，
想加个参数就得读完整段。
"""
from __future__ import annotations

import argparse
import sys

from . import __version__
from .commands.add import cmd_add
from .commands.basic import cmd_doctor, cmd_list, cmd_rollback, cmd_unlock
from .commands.inspect import cmd_inspect
from .commands.remove import cmd_remove
from .commands.scan import cmd_scan
from .commands.update import cmd_update
from .commands.verify import cmd_verify


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="ghpm", description="GitHub 开源项目管理 v%s" % __version__)
    ap.add_argument("--version", action="version", version="ghpm %s" % __version__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    l = sub.add_parser("list", help="列出已登记项目")
    l.add_argument("--json", action="store_true", help="输出 JSON")
    l.set_defaults(func=cmd_list)

    sc = sub.add_parser("scan", help="扫描本机未登记的 GitHub 项目")
    sc.add_argument("--fresh", action="store_true", help="忽略本地缓存，直接问 GitHub")
    sc.set_defaults(func=cmd_scan)

    i = sub.add_parser("inspect", help="安装前预检（不写入任何文件）")
    i.add_argument("repo", help="GitHub 仓库，如 owner/repo 或完整 URL")
    i.add_argument("--force", action="store_true", help="即使已安装也继续预检")
    i.add_argument("--fresh", action="store_true", help="忽略本地缓存，直接问 GitHub")
    i.set_defaults(func=cmd_inspect)

    a = sub.add_parser("add", help="添加/安装项目")
    a.add_argument("repo", help="GitHub 仓库，如 owner/repo 或完整 URL")
    a.add_argument("--branch", help="指定分支，默认用 default_branch")
    a.add_argument("--allow-non-skill", dest="allow_non_skill", action="store_true",
                   help="没有 skill 也照装源码")
    a.add_argument("--force", action="store_true",
                   help="即使 skill 已被其他项目占用也强制覆盖")
    a.set_defaults(func=cmd_add)

    c = sub.add_parser("check", help="检查更新")
    c.add_argument("name", nargs="?")
    c.add_argument("--fresh", action="store_true", help="忽略本地缓存，直接问 GitHub")
    c.set_defaults(func=cmd_check)

    u = sub.add_parser("update", help="更新项目")
    u.add_argument("name", nargs="?")
    u.add_argument("--all", action="store_true", help="更新清单里所有项目")
    u.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="只报告有没有更新，不下载不写盘")
    u.add_argument("--force", action="store_true",
                   help="已是最新也重新下载覆盖，并强制覆盖他人已装的 skill")
    u.add_argument("--fresh", action="store_true",
                   help="忽略本地缓存（update 本身总是查最新 sha，此项只影响 --dry-run）")
    u.set_defaults(func=cmd_update)

    r = sub.add_parser("remove", help="移除项目（自动备份）")
    r.add_argument("name")
    r.set_defaults(func=cmd_remove)

    rb = sub.add_parser("rollback", help="把某次备份恢复到原位")
    rb.add_argument("backup", help="备份目录路径")
    rb.set_defaults(func=cmd_rollback)

    v = sub.add_parser("verify", help="校验清单 ↔ 磁盘（↔ 远端）是否一致")
    v.add_argument("name", nargs="?", help="只校验某个项目")
    v.add_argument("--remote", action="store_true", help="额外比对远端 sha（需要网络）")
    v.add_argument("--fresh", action="store_true", help="远端比对时忽略本地缓存")
    v.add_argument("--json", action="store_true", help="输出 JSON")
    v.set_defaults(func=cmd_verify)

    doc = sub.add_parser("doctor", help="诊断环境、网络、清单、锁、备份与磁盘")
    doc.add_argument("--json", action="store_true", help="输出 JSON")
    doc.add_argument("--no-network", dest="no_network", action="store_true",
                     help="跳过 GitHub API 网络探测")
    doc.set_defaults(func=cmd_doctor)

    un = sub.add_parser("unlock", help="清除写锁（持有者仍在运行则拒绝）")
    un.add_argument("--force", action="store_true", help="即使持有者仍在运行也强制清除")
    un.set_defaults(func=cmd_unlock)

    return ap


def cmd_check(args):
    """check：比对本地记录与远端 sha。只读，不写盘（除 checked_at）。"""
    from .registry import find_project, load, persist_checked_at
    from .remote import classify_net_error, fetch_repo_infos
    from .config import CACHE_TTL
    from .errors import E_NETWORK
    from .util import emit

    data = load()
    targets = data["projects"]
    if args.name:
        hit = find_project(data, args.name)
        targets = [hit] if hit else []
        if not targets:
            print("未找到项目：%s" % args.name)
            return
    if not targets:
        emit("done", "清单为空，没有可检查的项目", percent=100, ok=True,
             data={"outdated": 0, "total": 0, "results": []})
        print("清单为空。用 `ghpm add <repo>` 添加，或 `ghpm scan` 自动发现。")
        return
    ttl = 0 if getattr(args, "fresh", False) else CACHE_TTL
    total = len(targets)
    print("检查 %d 个项目...\n" % total)

    # 并发拉取；网络等待不再线性累加。进度按完成数走，宿主看不出差别。
    fetched, fetch_errors = fetch_repo_infos(
        [p.get("repo") or p.get("name") for p in targets], ttl=ttl,
        progress=lambda d, t, r: emit(
            "checking", "检查 %d/%d · %s" % (d, t, r), percent=int(90 * d / max(1, t))))

    outdated, results, errors, checked = [], [], [], []
    # 按清单顺序输出，避免并发导致每次结果排列都不同（对 diff/CI 不友好）
    for p in targets:
        repo = (p.get("repo") or p.get("name") or "").lower()
        name = p.get("name", "?")
        if repo in fetch_errors:
            e = fetch_errors[repo]
            # 单个项目失败不 emit failed：那会让宿主误以为整个任务失败（后面还有别的要查）
            code, hint = classify_net_error(e)
            print("  %-24s 检查失败: %s" % (name, str(e)[:60]))
            results.append({"repo": p.get("repo", ""), "name": name,
                            "status": "error", "code": code, "error": str(e)[:120],
                            "hint": hint})
            errors.append(name)
            continue
        info = fetched.get(repo)
        if info is None:
            print("  %-24s 未取得信息" % name)
            results.append({"repo": p.get("repo", ""), "name": name, "status": "error",
                            "code": E_NETWORK, "error": "未取得仓库信息",
                            "hint": "稍后重试，或用 --fresh 绕过本地缓存。"})
            errors.append(name)
            continue
        local = p.get("sha", "")
        checked.append(p.get("repo", ""))
        if not local or info.get("sha") != local:
            print("  [有更新] %-22s %s -> %s" % (name, p.get("sha_short", "-"),
                                                info.get("sha_short")))
            print("            %s" % info.get("msg"))
            outdated.append((p, info))
            results.append({"repo": p.get("repo", ""), "name": name,
                            "status": "outdated",
                            "from": p.get("sha_short", ""), "to": info.get("sha_short"),
                            "stars": info.get("stars"), "msg": info.get("msg")})
        else:
            print("  [最新]   %-22s %s  ★%s"
                  % (name, info.get("sha_short"), info.get("stars")))
            results.append({"repo": p.get("repo", ""), "name": name,
                            "status": "latest",
                            "sha": info.get("sha_short"), "stars": info.get("stars")})
    persist_checked_at(checked)
    print()
    if outdated:
        print("%d 个项目可更新。运行 `ghpm update %s` 或 `ghpm update --all`"
              % (len(outdated), outdated[0][0].get("name", "?")))
    else:
        print("全部已是最新。")
    label = "%d 个可更新" % len(outdated)
    if errors:
        label += "（%d 个没查到）" % len(errors)
    # 结果形状恒定：宿主只需看顶层 ok，逐项归因一律去 data.results[].hint 取。
    # 之前单项目失败才带 hint、多项目失败只带 detail，宿主得写两套解析分支。
    emit("done", label, percent=100, ok=not errors,
         detail=(("没查到：%s" % "、".join(errors)) if errors else None),
         hint=("部分项目没查到，多为网络波动或 API 限流，可稍后重试；"
               "每个项目的具体归因见 data.results[].hint" if errors else None),
         data={"total": len(results), "outdated": len(outdated), "errors": len(errors),
               "results": results})


def main(argv=None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    try:
        rc = args.func(args)
    except KeyboardInterrupt:
        print("已取消", file=sys.stderr)
        return 130
    except SystemExit:
        raise
    except Exception as e:
        print("错误: %s" % e, file=sys.stderr)
        return 1
    return rc if isinstance(rc, int) else 0
