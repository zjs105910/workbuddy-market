# -*- coding: utf-8 -*-
"""launcher —— 本机插件市场的一键入口。

双击「一键启动.cmd」等价于：

    python launcher.py

默认按顺序做五件事：

    0. 向导    首次启动检查：环境预检；配置缺失时从模板自动初始化
               （绝不覆盖已有配置，损坏的原样保留并给出修复建议）
    1. 打包    把 ~/.workbuddy/skills 里配置好的 skill 打包成标准插件
    2. 自检    校验市场索引、source 目录、WorkBuddy 目录是否就位
    3. 注册    写进 WorkBuddy 的 known_marketplaces.json（自动备份、幂等）
    4. 开界面  起本地服务并打开浏览器

**第 0 步**是 v2.22 新增：全新 clone 不再需要手工复制配置文件。
首次创建配置时，交互式终端会问一次「只浏览市场（默认，回车）/ 注册到
WorkBuddy」—— 回车永远是只浏览；非交互环境不等待输入，直接纯浏览模式。
无论怎么选，真正的注册都仍要过 should_register() 的原有前置检查。
不想跑向导（比如脚本里要输出干净）加 `--no-wizard`。

**第 1 步或第 2 步没过，第 3 步会被跳过**（但界面照常打开）。
注册会写 WorkBuddy 的配置文件，属于有外部副作用的动作 —— 前置检查没过就不该
动它，否则 WorkBuddy 会看到一个「根本没更新成功的旧市场」，而你还以为启动成功了。
想强行注册加 `--force-register`。

    python launcher.py --help     看全部参数
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import market_core as core  # noqa: E402

DEFAULT_PORT = 8777

ACTION_FLAGS = ("sync", "register", "unregister", "status", "recover", "purge_trash")

QUIET = False                     # --quiet：过程信息一律不打印

BANNER = r"""
  ┌──────────────────────────────────────────────┐
  │   WorkBuddy 本机插件市场                      │
  └──────────────────────────────────────────────┘
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="launcher.py",
        description="WorkBuddy 本机插件市场：把本机 skill 打包成插件，"
                    "注册进 WorkBuddy 插件面板，并打开本地网页界面。",
        epilog="不带任何参数 = 「一键启动.cmd」：打包 → 自检 → 注册 → 开界面。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    act = p.add_argument_group("只做一件事（彼此互斥）")
    act.add_argument("--sync", action="store_true", help="只重新打包本机 skill")
    act.add_argument("--register", action="store_true", help="只注册进 WorkBuddy")
    act.add_argument("--unregister", action="store_true", help="撤销注册")
    act.add_argument("--status", action="store_true", help="打印状态 + 深度自检 + 回收站")
    act.add_argument("--recover", action="store_true",
                     help="只做事务恢复（补记上一次没记完的所有权）")
    act.add_argument("--purge-trash", action="store_true", help="清空回收站")

    opt = p.add_argument_group("选项")
    opt.add_argument("--no-wizard", action="store_true",
                     help="跳过 v2.22 首次启动检查（配置缺失也不再自动初始化）")
    opt.add_argument("--serve", action="store_true", help="只起本地网页服务")
    opt.add_argument("--port", type=int, default=DEFAULT_PORT, metavar="N",
                     help=f"网页服务端口（默认 {DEFAULT_PORT}；被占用会自动往后找 20 个）")
    opt.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    opt.add_argument("--no-register", action="store_true",
                     help="开界面但不注册（完全不碰 WorkBuddy 配置）")
    opt.add_argument("--force-register", action="store_true",
                     help="打包 / 自检失败也照样注册（不推荐）")
    opt.add_argument("--discard-conflicts", action="store_true",
                     help="配合 --recover：放弃那些「内容已被你改过」的补账")
    opt.add_argument("--json", action="store_true",
                     help="以 JSON 输出结果（方便 CI / Harness 调用）")
    opt.add_argument("--quiet", action="store_true",
                     help="不打印过程信息，只输出最终结果")
    return p


def should_register(sync_ok: bool, check_ok: bool, forced: bool = False) -> tuple:
    """前置检查失败时，还允不允许注册？返回 (允许?, 原因)。

    `register()` 会往 WorkBuddy 的 known_marketplaces.json 写一条记录 ——
    这是**有外部副作用**的步骤。而打包或自检失败时，plugins/ 里还是上一次的
    旧内容；这时候注册上去，只会让 WorkBuddy 看到一个「根本没更新成功的旧市场」，
    用户却以为启动成功了。

    v2.1 之前的设计是「一步失败也继续后面的步骤」。展示型工具这样没问题，
    但这条链路带着外部副作用，所以改成：**失败可以继续开网页，但不能继续注册。**
    """
    if forced:
        return True, ""
    if not sync_ok:
        return False, "打包没有成功"
    if not check_ok:
        return False, "深度自检没有通过"
    return True, ""


def _emit(args, payload: dict, human: str) -> int:
    """统一出口：--json 打 JSON，否则打人类可读的一行（--quiet 时什么都不打）。"""
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload.get("ok", True) else 1
    if human and not args.quiet:
        _line(human)
    return 0 if payload.get("ok", True) else 1


def _status_payload() -> dict:
    st = core.build_state()
    ok, errors, warns = core.deep_check()
    return {
        "ok": ok,
        "marketVersion": core.MARKET_VERSION,
        "marketId": st["marketId"],
        "registered": st["registered"],
        "localPlugins": st["stats"]["localPlugins"],
        "remoteSources": st["stats"]["remoteSources"],
        "verify": st["stats"]["verify"],
        "verifyEffective": st["stats"]["verifyEffective"],
        "trash": {"count": st["trash"]["count"], "bytes": st["trash"]["bytes"]},
        "check": {"ok": ok, "errors": errors, "warnings": warns},
    }


def run_action(args) -> int | None:
    """互斥的「只做一件事」模式。没选任何一个就返回 None（走默认全流程）。"""
    chosen = [a for a in ACTION_FLAGS if getattr(args, a)]
    if args.serve:
        if chosen:
            raise SystemExit(
                f"launcher.py：--serve 不能和 --{chosen[0].replace('_', '-')} 一起用。")
        return _serve(args)
    if not chosen:
        return None
    if len(chosen) > 1:
        names = "、".join("--" + c.replace("_", "-") for c in chosen)
        raise SystemExit(f"launcher.py：这些动作只能选一个，你给了 {len(chosen)} 个：{names}")

    what = chosen[0]
    if what == "status":
        # v2.24：配置缺失/损坏不再裸抛 traceback —— 给人话 + 下一步指引。
        try:
            p = _status_payload()
        except core.ConfigError as exc:
            if args.json:
                print(json.dumps({"ok": False, "error": str(exc)},
                                 ensure_ascii=False, indent=2))
            else:
                _line("状态读取失败：配置文件有问题 ——")
                _line("  " + str(exc).replace("\n", "\n  "))
                _line("  首次使用：直接重跑 python launcher.py（会从模板自动初始化配置，")
                _line("  绝不覆盖已有文件）；损坏文件会被原样保留，按提示修复即可。")
            return 1
        human = (f"市场：{p['marketId']} v{p['marketVersion']}｜"
                 f"{'已注册' if p['registered'] else '未注册'}｜"
                 f"插件 {p['localPlugins']} / 源 {p['remoteSources']}｜"
                 f"回收站 {p['trash']['count']} 项｜"
                 f"自检 {'通过' if p['check']['ok'] else '未通过'}")
        rc = _emit(args, p, human)
        if not args.json and p["check"]["errors"]:
            for e in p["check"]["errors"]:
                _line("  ✗ " + e)
        if not args.json:
            for w in p["check"]["warnings"][:6]:
                _line("  ! " + w)
        return rc
    if what == "sync":
        rep = core.sync_packaging(quiet=QUIET)
        p = {"ok": True, "plugins": len(rep["plugins"]), "skills": rep["totalSkills"],
             "copiedFiles": rep.get("copiedFiles", 0),
             "removedFiles": rep.get("removedFiles", 0),
             "recovered": rep.get("recovered", []), "missing": rep["missing"]}
        return _emit(args, p, f"打包完成：{p['plugins']} 个插件，{p['skills']} 个 skill")
    if what == "recover":
        r = core.recover_transactions(quiet=QUIET and not args.json,
                                      discard_conflicts=args.discard_conflicts)
        p = {"ok": not r["failed"], "recovered": r["recovered"],
             "finished": r["finished"], "conflicts": r["conflicts"],
             "failed": r["failed"], "stagingSwept": r["stagingSwept"]}
        return _emit(args, p,
                     f"事务恢复：补记所有权 {len(r['recovered'])} 项，"
                     f"清理日志 {len(r['finished'])} 份，清理暂存 {r['stagingSwept']} 个")
    if what == "unregister":
        changed = core.unregister()
        return _emit(args, {"ok": True, "changed": changed},
                     "已撤销注册。" if changed else "本来就没注册。")
    if what == "register":
        changed = core.register()
        return _emit(args, {"ok": True, "changed": changed},
                     "已注册（写入了 known_marketplaces.json）。" if changed
                     else "已是注册状态，无需改动。")
    if what == "purge_trash":
        r = core.prune_trash(force=True)
        p = {"ok": True, "removed": r["removed"], "failed": r["failed"],
             "freed": r["freed"]}
        return _emit(args, p,
                     f"回收站已清空：移除 {r['removed']} 项，"
                     f"释放 {r['freed'] / 1048576:.1f} MB")
    return None


def _serve(args) -> int:
    import market_server

    return market_server.serve(port=args.port, open_browser=not args.no_open)


def _line(t=""):
    # 必须 flush：双击运行走控制台还好，但被重定向到管道/日志时
    # 不 flush 就会一直攒着，用户以为卡住了。
    if QUIET:
        return
    print("  " + t if t else "", flush=True)


def main(argv=None) -> int:
    global QUIET
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    parser = build_parser()
    args = parser.parse_args(argv)
    QUIET = bool(args.quiet) or bool(args.json)      # --json 时人话一律别混进 stdout

    early = run_action(args)
    if early is not None:
        return early

    # ---- 默认：一键全流程
    if not QUIET:
        print(BANNER)

    # ---- [0/4] 首次启动检查（v2.22）：环境预检 + 配置缺失自动初始化。
    #      向导零副作用（唯一可能的写是「配置缺失时的模板初始化」），
    #      注册只产生「意图」，真正注册仍在 [3/4] 过 should_register 闸门。
    wizard_browse = False
    if not args.json and not args.no_wizard:
        _line("[0/4] 首次启动检查")
        try:
            import workbuddy_market.onboard as onboard
        except Exception as exc:
            onboard = None
            _line(f"      向导模块不可用，跳过（主流程不受影响）：{exc}")
        if onboard is not None:
            probe = None
            try:
                import market_server as _ms
                probe = _ms._find_port        # 复用同一套端口探测（含 Windows 修复）
            except Exception:
                probe = None
            try:
                rep = onboard.run_wizard(port_probe=probe, port=args.port,
                                         interactive=False if QUIET else None)
                for ln in onboard.render(rep):
                    _line("      " + ln)
                if rep.get("created") and rep.get("choice") == "browse":
                    wizard_browse = True
            except Exception as exc:
                _line(f"      首次启动检查本身出错（不阻断后续步骤）：{exc}")
                core.log("warn", "onboard", f"向导异常：{exc}")

    _line()
    _line("[1/4] 打包本机 skill → 插件（增量同步）")
    sync_ok = False
    try:
        rep = core.sync_packaging(quiet=False)
        sync_ok = True
        _line(f"      完成：{len(rep['plugins'])} 个插件，{rep['totalSkills']} 个 skill，"
              f"{rep['bytes'] / 1048576:.1f} MB")
        if rep.get("recovered"):
            _line(f"      顺带补记了上次未完成的所有权：{'、'.join(rep['recovered'])}")
        if rep.get("copiedFiles"):
            _line(f"      本次更新 {rep['copiedFiles']} 个文件"
                  + (f"，清理 {rep['removedFiles']} 个" if rep.get("removedFiles") else "")
                  + f"（校验档位 {rep.get('verify', 'auto')}，没变的不重拷）")
        else:
            _line(f"      内容与上次一致，无需拷贝（校验档位 {rep.get('verify', 'auto')}）")
        if rep.get("skippedLinks"):
            _line(f"      ! 跳过了 {rep['skippedLinks']} 个符号链接 / junction"
                  "（不跟随，避免带出技能目录外的内容）")
        if rep.get("cachedSkills"):
            _line(f"      沿用历史副本 {len(rep['cachedSkills'])} 个"
                  "（这些 skill 本机已不存在，市场里还留着，可随时装回来）")
        if rep["missing"]:
            _line(f"      注意：{len(rep['missing'])} 个配置里的 skill 在本机不存在")
            for m in rep["missing"][:6]:
                _line(f"        · {m}")
    except Exception as exc:
        _line(f"      失败：{exc}")
        core.log("error", "launch", f"打包失败：{exc}")

    _line()
    _line("[2/4] 自检")
    check_ok = False
    try:
        ok, errors, warns = core.deep_check()
        check_ok = ok
        if ok:
            _line("      通过：配置 ↔ 索引 ↔ 插件清单 ↔ 实际文件 四层一致")
        else:
            for e in errors:
                _line(f"      ✗ {e}")
        for w in warns[:4]:
            _line(f"      ! {w}")
    except Exception as exc:
        _line(f"      自检本身出错了：{exc}")

    # 回收站按策略自动清理（只在超过阈值时才真删）
    try:
        pr = core.prune_trash()
        if pr["removed"]:
            _line(f"      回收站自动清理：移除 {pr['removed']} 项，"
                  f"释放 {pr['freed'] / 1048576:.1f} MB")
        if pr.get("failed"):
            _line(f"      ! 有 {pr['failed']} 项没能删掉（多半是被占用），保留在回收站里")
        if pr.get("protected"):
            _line(f"      有 {pr['protected']} 项因为「安装后被改过」受保护，未自动清理")
    except Exception:
        pass

    _line()
    registered_now = None
    register_skipped = None
    if args.no_register:
        _line("[3/4] 跳过注册（--no-register，纯网页模式）")
        register_skipped = "no-register"
    elif wizard_browse:
        _line("[3/4] 跳过注册（首次启动选择了「只浏览市场」，纯网页模式）")
        register_skipped = "wizard-browse"
        _line("      想注册随时可以：python launcher.py --register，"
              "或打开网页点「注册到 WorkBuddy」。")
    else:
        allow, why = should_register(sync_ok, check_ok, args.force_register)
        _line("[3/4] 注册到 WorkBuddy 插件面板")
        if not allow:
            # 注册会写 WorkBuddy 的配置文件 —— 前置检查没过就不该动它
            register_skipped = why
            _line(f"      已跳过：{why}")
            if not args.force_register:
                _line("      市场内容可能不是最新的。先修好上面的报错，再重跑一次；")
                _line("      确实想强行注册可以加 --force-register。")
            _line("      网页服务照常启动（只读展示，页面上能看到具体问题）。")
        else:
            try:
                registered_now = core.register()
                if registered_now:
                    _line(f"      已写入 {core.KNOWN_PATH}")
                    _line("      备份放在 " + str(core.BACKUP_DIR))
                else:
                    _line("      已是注册状态，无需改动")
            except Exception as exc:
                _line(f"      失败：{exc}")
                core.log("error", "launch", f"注册失败：{exc}")

    _line()
    _line("[4/4] 打开市场界面")
    if sync_ok and check_ok:
        _line("      注册完成后，WorkBuddy 自带的插件面板里也能看到本市场")
    _line()

    if args.json:
        # CI / Harness 用：只吐一份结果，不混人话
        print(json.dumps({
            "ok": sync_ok and check_ok,
            "marketVersion": core.MARKET_VERSION,
            "syncOk": sync_ok,
            "checkOk": check_ok,
            "registered": registered_now,
            "registerSkipped": register_skipped,
            "port": args.port,
        }, ensure_ascii=False, indent=2))

    try:
        return _serve(args)
    except SystemExit as exc:
        _line(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
