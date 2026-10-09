# -*- coding: utf-8 -*-
"""onboard —— 首次启动向导（v2.22 新增）。

定位：把「全新克隆 → 能用的网页市场」之间剩下的手工步骤收进启动流程。
README 的产品承诺是「双击 一键启动.cmd」，但 v2.21 之前用户仍要先
``cp market.config.example.json market.config.json`` —— 这一步漏掉时
打包/自检会失败，与「一键」的承诺有落差。本模块负责：

  1. 环境预检：Python 版本、仓库布局、配置状态、WorkBuddy 目录、
     本机 skills、服务端口 —— 每一项独立捕获异常，坏了如实标，
     绝不让一项故障拖垮整份报告（与 doctor 同一纪律）；
  2. 配置初始化：配置缺失时从 market.config.example.json 安全创建。
     独占创建（O_CREAT|O_EXCL）+ 单次写入 + fsync + 失败清理 ——
     并发启动不会互相覆盖，也不会留下半截 JSON；
  3. 启动选择：首次创建配置后，交互式终端给「只浏览（默认）/ 注册」
     两个选项；**回车 = 只浏览**。非交互环境不等待输入，直接纯浏览。

安全边界（全部有自检盯防）：
  · 已存在的配置（包括损坏的）绝不改写、绝不移动 —— 损坏时只报告
    错误位置与恢复建议，修复由用户手工完成；
  · 新配置不自动收录发现的 skills（localPlugins 保持空），
    也不自动添加远程收录源 —— 「加入市场内容」必须由用户明确决定；
  · 向导本身永远不写 known_marketplaces.json —— 注册意图只作为
    返回值交给 launcher，真正的注册仍走 should_register() 原有闸门。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .config import validate_config
from .errors import ConfigError
from .paths import CONFIG_PATH, KNOWN_PATH, MARKET_ROOT, SKILLS_DIR

TEMPLATE_NAME = "market.config.example.json"

# 可注入的 os 接缝：selftest 用它们模拟「写到一半失败」，
# 产品代码永远走真实现。
_os_open = os.open
_os_write = os.write
_os_close = os.close
_os_unlink = os.unlink


# ---------------------------------------------------------------- 状态判定

def classify_config() -> tuple:
    """配置文件现状 → (status, detail)。status ∈ missing / ok / corrupt。

    读取与校验都是只读的；损坏的文件在这里只被描述，绝不被修改。
    """
    if not CONFIG_PATH.exists():
        return "missing", "还没有 market.config.json"
    try:
        raw = CONFIG_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        return "corrupt", f"配置文件读不出来（不动它）：{exc}"
    except UnicodeDecodeError as exc:
        return "corrupt", f"配置文件不是合法 UTF-8（不动它）：{exc}"
    try:
        data = json.loads(raw)
    except ValueError as exc:
        return "corrupt", (
            f"JSON 解析失败：{exc}\n"
            f"        文件原样保留在 {CONFIG_PATH}\n"
            "        建议：修好这一处语法错误，或把文件改名备份后"
            "删除，下次启动会从模板重新初始化")
    if not isinstance(data, dict):
        return "corrupt", (f"配置顶层必须是 JSON 对象（实际是 "
                           f"{type(data).__name__}），文件原样保留")
    try:
        validate_config(data)
    except ConfigError as exc:
        where = str(exc).splitlines()[0]
        return "corrupt", (
            f"配置校验失败：{where}\n"
            f"        文件原样保留在 {CONFIG_PATH}，未做任何改动\n"
            "        建议：按上面指出的字段修正，或把文件改名备份后"
            "删除，下次启动会从模板重新初始化")
    return "ok", ""


def discover_skills() -> list:
    """枚举 ~/.workbuddy/skills 下的 skill 目录（顶层含 SKILL.md）。

    这是给用户看的「发现了什么」摘要 —— 不写进任何配置。
    重解析点（符号链接 / junction）不跟随，与 scanner 同一边界。
    """
    import stat as _stat
    if not SKILLS_DIR.is_dir():
        return []
    names = []
    try:
        entries = sorted(os.scandir(SKILLS_DIR), key=lambda e: e.name)
    except OSError:
        return []
    for e in entries:
        try:
            st = e.stat(follow_symlinks=False)
            attr = getattr(st, "st_file_attributes", 0)
            if e.is_symlink() or (attr & getattr(
                    _stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)):
                continue
            if not _stat.S_ISDIR(st.st_mode):
                continue
        except OSError:
            continue
        if (Path(e.path) / "SKILL.md").is_file():
            names.append(e.name)
    return names


# ---------------------------------------------------------------- 配置初始化

def init_config(template_path=None) -> dict:
    """配置缺失时从模板安全初始化。

    返回 {"action": "created"|"exists"|"error", "detail": str}。
    · 已存在（含损坏）→ "exists"，一字节都不动；
    · 模板缺失 / 模板坏 → "error"，诚实失败，不生成猜测配置；
    · 创建 → 独占打开（O_EXCL）+ 写入 + fsync；任何一步失败都
      删掉半成品再抛出，磁盘上不会留下半截 JSON。
    """
    if CONFIG_PATH.exists():
        return {"action": "exists",
                "detail": "配置已存在，未做任何改动（包括损坏的也原样保留）"}
    template = Path(template_path) if template_path else MARKET_ROOT / TEMPLATE_NAME
    if not template.is_file():
        return {"action": "error",
                "detail": (f"找不到配置模板 {template}。\n"
                           "        请从仓库重新获取 market.config.example.json"
                           "（或手动复制一份），本工具不会凭空生成猜测配置。")}
    try:
        raw = template.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return {"action": "error",
                "detail": f"模板 {template.name} 读不出来或不是合法 JSON：{exc}"}
    try:
        validate_config(data)
    except ConfigError as exc:
        return {"action": "error",
                "detail": f"模板本身校验失败（这是模板的问题，请报告）：{exc}"}
    blob = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    try:
        _write_exclusive(CONFIG_PATH, blob)
    except FileExistsError:
        return {"action": "exists",
                "detail": "并发启动：另一个进程刚刚创建了配置，沿用现成文件"}
    except OSError as exc:
        return {"action": "error", "detail": f"配置创建失败（已清理半成品）：{exc}"}
    return {"action": "created", "detail": str(CONFIG_PATH)}


def _write_exclusive(path: Path, text: str) -> None:
    """独占创建 + 写入 + fsync。已存在 → FileExistsError；中途失败 → 清理。"""
    fd = _os_open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        view = memoryview(text.encode("utf-8"))
        while view:
            n = _os_write(fd, view)
            view = view[n:]
        try:
            os.fsync(fd)
        except OSError:
            pass                      # 个别平台 / 文件系统不支持，尽力即可
        _os_close(fd)
    except BaseException:
        try:
            _os_close(fd)
        except OSError:
            pass
        try:
            _os_unlink(str(path))
        except OSError:
            pass
        raise


# ---------------------------------------------------------------- 预检与向导

def _check(name: str, ok: bool, detail: str = "", warn: bool = False) -> dict:
    return {"name": name, "ok": ok, "warn": warn and ok, "detail": detail}


def precheck(port_probe=None, port: int = 0) -> list:
    """环境预检。每项独立捕获异常；WorkBuddy 目录缺失只警告不挡浏览。"""
    checks = []
    vi = sys.version_info
    checks.append(_check(
        "Python 版本", vi >= (3, 10),
        f"{vi.major}.{vi.minor}.{vi.micro}"
        + ("" if vi >= (3, 10) else "（需要 ≥ 3.10，请升级 Python）")))

    layout_ok = (MARKET_ROOT / "web" / "index.html").is_file() \
        and (MARKET_ROOT / TEMPLATE_NAME).is_file()
    checks.append(_check(
        "市场目录（仓库布局）", layout_ok, str(MARKET_ROOT)
        + ("" if layout_ok else "（缺 web/ 或配置模板 —— 请在完整 clone 内运行）")))

    status, detail = classify_config()
    if status == "ok":
        checks.append(_check("配置文件", True, str(CONFIG_PATH)))
    elif status == "missing":
        checks.append(_check("配置文件", True,
                             "缺失 —— 将从模板自动初始化（绝不覆盖已有配置）",
                             warn=True))
    else:
        checks.append(_check("配置文件", False, detail))

    try:
        skills = discover_skills()
        if skills:
            checks.append(_check(
                "本机 skills", True,
                f"发现 {len(skills)} 个：{'、'.join(skills[:6])}"
                + ("…等" if len(skills) > 6 else "")
                + "（仅摘要，不自动收录进市场内容）"))
        else:
            checks.append(_check("本机 skills", True,
                                 f"{SKILLS_DIR} 下没有发现带 SKILL.md 的技能目录",
                                 warn=True))
    except Exception as exc:                          # pragma: no cover
        checks.append(_check("本机 skills", False, f"扫描失败：{exc}"))

    checks.append(_check(
        "WorkBuddy 家目录", KNOWN_PATH.parent.is_dir(), str(KNOWN_PATH.parent)
        + ("" if KNOWN_PATH.parent.is_dir()
           else "（不存在 —— 只影响注册，不影响浏览市场）"),
        warn=not KNOWN_PATH.parent.is_dir()))

    if port_probe is not None and port:
        try:
            got = int(port_probe(port))
            if got == port:
                checks.append(_check("服务端口", True, f"{port} 空闲"))
            else:
                checks.append(_check("服务端口", True,
                                     f"{port} 被占用，将自动改用 {got}",
                                     warn=True))
        except SystemExit as exc:
            checks.append(_check("服务端口", False, str(exc)))
        except Exception as exc:
            checks.append(_check("服务端口", False, f"探测失败：{exc}"))
    return checks


def _is_interactive() -> bool:
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        return False


def run_wizard(port_probe=None, port: int = 0, interactive: bool | None = None,
               input_func=None) -> dict:
    """跑一遍首次启动向导，返回结构化报告。**本函数零外部副作用**
    （唯一可能的写动作是「配置缺失时的 init_config」），不注册、不打包。

    choice 只在「本次启动创建了新配置」时才询问/生效 —— 老用户的启动
    行为与 v2.21 完全一致。
    """
    if interactive is None:
        interactive = _is_interactive()
    report = {
        "checks": precheck(port_probe=port_probe, port=port),
        "configStatus": None, "configAction": None, "configDetail": "",
        "created": False, "interactive": bool(interactive),
        "choice": None, "choiceReason": "", "skills": [],
    }

    status, _ = classify_config()
    report["configStatus"] = status
    report["skills"] = discover_skills()

    if status == "missing":
        r = init_config()
        report["configAction"] = r["action"]
        report["configDetail"] = r["detail"]
        report["created"] = r["action"] == "created"
        status = "ok" if report["created"] else status
        report["configStatus"] = status
    else:
        report["configAction"] = "none"

    if report["created"]:
        if interactive:
            choice = None
            if input_func is None:
                input_func = input
            try:
                raw = input_func(
                    "\n  首次启动：选择本次的启动方式\n"
                    "    1) 只浏览市场（默认；回车即选这个，不改动 WorkBuddy 配置）\n"
                    "    2) 注册到 WorkBuddy（写 known_marketplaces.json，"
                    "仍需通过打包/自检前置检查）\n"
                    "  请输入 1 或 2 后回车：").strip()
            except (EOFError, KeyboardInterrupt):
                raw = ""
            choice = "register" if raw == "2" else "browse"
            report["choice"] = choice
            report["choiceReason"] = (
                "你选择了注册（实际注册仍会经过打包 / 自检前置检查）"
                if choice == "register" else
                "使用默认的只浏览模式（回车 / 其他输入都算只浏览）")
        else:
            report["choice"] = "browse"
            report["choiceReason"] = (
                "非交互环境（无终端输入），不等待、不猜测 —— "
                "本次按纯浏览模式启动，不碰注册；"
                "想注册可运行 python launcher.py --register")
    return report


def render(report: dict) -> list:
    """把向导报告渲染成人话行（调用方负责缩进与打印）。"""
    lines = []
    for c in report["checks"]:
        mark = "✓" if c["ok"] and not c["warn"] else ("!" if c["ok"] else "✗")
        if c["detail"]:
            lines.append(f"{mark} {c['name']}：{c['detail']}")
        else:
            lines.append(f"{mark} {c['name']}")
    act = report.get("configAction")
    if act == "created":
        lines.append("已从模板初始化 market.config.json（localPlugins 留空，"
                     "发现的 skills 只在上方做摘要 —— 把哪些收进市场由你决定："
                     "编辑 market.config.json 后点「重新打包」即可）。")
    elif act == "exists":
        lines.append("配置已存在，原样保留。")
    elif act == "error":
        lines.append("初始化失败：" + (report.get("configDetail") or "未知原因"))
    if report.get("choiceReason"):
        lines.append(report["choiceReason"])
    return lines
