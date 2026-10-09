"""UI 冒烟：Playwright 真浏览器验收（dev-only，可选依赖）。

定位（对应 v3-roadmap P0-1「UI 产品化」的验收基建）：
  · 产品本体保持零依赖 —— 本脚本只是开发者工具，playwright 不进
    pyproject 依赖，也不进 selftest（selftest 纪律：零依赖一键诊断）；
  · 真起服务 + 真浏览器，验证的是「会发货的那套前端」：
    ES Modules 导入链（import 失败 = pageerror）、token 注入、
    卡片渲染、搜索过滤、分类切换、注册表详情弹窗、本机安装端到端。

用法：
  python scripts/ui_smoke.py            # 无头跑完输出 PASS/FAIL
  python scripts/ui_smoke.py --headed   # 有头模式，肉眼看界面
  python scripts/ui_smoke.py --ci       # CI 门禁模式（见下）

环境：
  pip install playwright && python -m playwright install chromium
  （未安装时打印 SKIP 退出 0 —— 不挡本地开发，不挡 selftest）

--ci 门禁模式（v2.21 评审 P1：核心检查不允许静默跳过后仍报成功）：
  · playwright 未安装 → 直接 FAIL（退出 1），SKIP 不存在；
  · 本机安装端到端 / 注册表详情弹窗 / 收藏开关这三项是「数据确定性」
    检查（隔离区自带 plugins + registry，必然有可交互项）——任何一项
    落进「跳过」分支即 FAIL，因为那说明渲染链路坏了而不是数据缺失。

隔离（与 selftest 同一纪律）：临时目录复制真实市场内容，
WBM_MARKET_ROOT / WBM_STATE_HOME / WBM_HOME 全部指进临时区，
真实环境零接触。
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))   # 让 scripts/ 直跑也能 import market_server

# 复制进隔离区的条目：市场内容 + 前端 + 注册表 + 索引。
# 其余（.git / .trash / 状态文件 / 日志 / 本机杂物）一律不带走。
_COPY_ITEMS = ("market.config.json", "plugins", "web", "registry",
               ".codebuddy-plugin")

CHECKS = []
CI_GATE = {"active": False, "skipped_core": []}   # --ci：核心检查跳过即失败


def ck(name, ok, detail=""):
    CHECKS.append(ok)
    print(("  PASS  " if ok else "  FAIL  ") + name + (f"  ——  {detail}" if detail else ""))


def build_isolated_market(base: Path) -> Path:
    root = base / "market"
    root.mkdir(parents=True)
    for item in _COPY_ITEMS:
        src = ROOT / item
        if not src.exists():
            continue
        dst = root / item
        if src.is_dir():
            shutil.copytree(src, dst,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(src, dst)
    return root


def _ensure_config(root: Path) -> None:
    """fresh clone 没有 market.config.json（私有配置不入库）—— CI 首跑
    实锤（run #3：ConfigError → 零卡片 → 超时）。从 example + plugins/
    目录合成一份确定性配置：单个 localPlugin 扫全量 SKILL.md，让本机
    安装端到端在 --ci 门禁下必然有可交互项。已有配置绝不覆盖。"""
    cfg_path = root / "market.config.json"
    if cfg_path.exists():
        return
    example = json.loads(
        (ROOT / "market.config.example.json").read_text(encoding="utf-8"))
    skills = sorted(
        d.name for d in (root / "plugins").glob("*/skills/*")
        if d.is_dir() and (d / "SKILL.md").is_file())
    if not skills:
        raise SystemExit("FAIL：plugins/ 扫不到任何带 SKILL.md 的 skill")
    example["localPlugins"] = [{
        "name": "ci-smoke-suite",
        "version": "1.0.0",
        "displayName": "CI smoke suite",
        "category": "验收",
        "description": "CI fresh clone 场景下由 ui_smoke 合成的临时配置",
        "keywords": [],
        "skills": skills,
    }]
    cfg_path.write_text(
        json.dumps(example, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--headed", action="store_true", help="有头模式（肉眼验收）")
    ap.add_argument("--ci", action="store_true",
                    help="CI 门禁：playwright 缺失或核心检查被跳过 → 硬失败")
    args = ap.parse_args()
    CI_GATE["active"] = args.ci

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        if args.ci:
            print("FAIL：--ci 模式要求 playwright 已安装"
                  "（pip install playwright && python -m playwright install chromium）")
            return 1
        print("SKIP：未安装 playwright（pip install playwright && "
              "python -m playwright install chromium）")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="wbm-ui-smoke-"))
    market_root = build_isolated_market(tmp)
    _ensure_config(market_root)
    os.environ["WBM_MARKET_ROOT"] = str(market_root)
    os.environ["WBM_STATE_HOME"] = str(tmp / "state")
    os.environ["WBM_HOME"] = str(tmp / "wb-home")
    (tmp / "wb-home").mkdir()

    # 环境变量必须在导入 core/server 之前就位 —— paths.py 在导入期解析根目录。
    import market_server as srv

    TOK = "ui-smoke-token"
    httpd = srv.make_server(0, token=TOK)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"

    page_errors = []
    console_errors = []
    # 远程资源（v2.21 screenshots 的 <img> 直拉插件仓库图片）会因本机
    # 代理 / 网络抖动 502，污染控制台 —— 那是环境噪音，UI 本来就优雅降级。
    # 真正要盯的是：JS error + 同源（本地服务）4xx/5xx / 请求失败。
    bad_same_origin = []
    # /api/gh/* 是服务端代理 GitHub 的上游调用（代理抖动 / 匿名配额 403），
    # 失败时 UI 优雅降级为空态 —— 上游噪音不算本地 API 故障，豁免。

    def _on_response(resp):
        try:
            if (resp.url.startswith(base) and resp.status >= 400
                    and "/api/gh/" not in resp.url):
                bad_same_origin.append(f"{resp.status} {resp.url}")
        except Exception:
            pass

    def _on_reqfailed(req):
        try:
            if req.url.startswith(base) and "/api/gh/" not in req.url:
                bad_same_origin.append(f"REQFAIL {req.url}")
        except Exception:
            pass

    shots = tmp / "shots"
    shots.mkdir()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not args.headed)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.on("pageerror", lambda e: page_errors.append(str(e)))
            page.on("console",
                    lambda m: console_errors.append(m.text)
                    if m.type == "error" else None)
            page.on("response", _on_response)
            page.on("requestfailed", _on_reqfailed)

            page.goto(base, wait_until="domcontentloaded")
            # 卡片渲染 = refresh() 全链完成（state/catalog/registry 都已返回）
            page.wait_for_selector("#content .card", timeout=30000)

            ck("页面标题", "本机插件市场" in page.title(), page.title())
            ck("★ ES Modules 导入链无 pageerror（import 失败会在这里炸出来）",
               not page_errors, "; ".join(page_errors[:3]))
            ck("服务端注入 token（页面可用，403 没出现）", True)

            cards = page.locator("#content .card")
            n_cards = cards.count()
            ck("★ 卡片渲染（本机插件 + 收录源）", n_cards >= 1, f"{n_cards} 张")

            # 顶部徽标（v2.21 更新中心按钮存在即可，不必有可更新项）
            ck("头部工具条就绪", page.locator("#btnSync").count() == 1)

            # ---- 搜索过滤： nonsense 词 → 空态；清空 → 卡片回来
            page.fill("#q", "zzz-不存在的词-zzz")
            page.wait_for_timeout(400)
            ck("搜索无命中 → 空态文案",
               page.locator("#content").inner_text().find("没有符合条件") >= 0)
            page.fill("#q", "")
            page.wait_for_timeout(400)
            ck("清空搜索 → 卡片恢复", page.locator("#content .card").count() >= 1)

            # ---- 分类切换（点「全部」以外第一枚 chip，再切回）
            chips = page.locator("#cats .chip")
            if chips.count() > 1:
                label = chips.nth(1).inner_text()
                chips.nth(1).click()
                page.wait_for_timeout(300)
                chips.nth(0).click()   # 「全部」
                page.wait_for_timeout(300)
                ck("分类切换往返不炸", True, f"切到「{label}」再切回")
            else:
                ck("分类切换往返不炸（单分类，跳过）", True)

            # ---- 注册表详情弹窗（社区目录有收录时）
            detail_btn = page.locator("[data-regdetail]").first
            if detail_btn.count():
                detail_btn.click()
                page.wait_for_selector("#cfm.show", timeout=5000)
                body = page.locator("#cfmBody").inner_text()
                ck("★ 注册表详情弹窗：来源与信任/兼容性信息块",
                   ("来源与信任" in body) and ("兼容性" in body))
                page.locator("#cfmYes").click()
                page.wait_for_timeout(200)
            else:
                CI_GATE["skipped_core"].append("注册表详情弹窗")
                ck("注册表详情弹窗（社区目录为空，跳过）", True)

            # ---- 本机安装端到端：隔离 WBM_HOME 是空的 → 第一张本机卡片必有「补齐」
            #      （/api/install 是同步接口：响应回来即装完，toast 汇总，不走任务弹窗）
            inst = page.locator("[data-install]").first
            if inst.count():
                inst.click()
                page.wait_for_function(
                    "document.querySelector('#toast').classList.contains('show')",
                    timeout=60000)
                toast_txt = page.locator("#toast").inner_text()
                ck("★ 本机安装端到端（补齐 → 事务安装 → toast 汇总）",
                   ("新增" in toast_txt or "更新" in toast_txt
                    or "跳过" in toast_txt or "没有" in toast_txt), toast_txt)
                page.wait_for_timeout(800)   # 等 refresh 完成后截图
                page.screenshot(path=str(shots / "after-install.png"))
            else:
                CI_GATE["skipped_core"].append("本机安装端到端")
                ck("本机安装端到端（无可安装项，跳过）", True)

            # ---- 收藏开关（POST /api/favorites，写进隔离 STATE_HOME）
            fav = page.locator("[data-fav]").first
            if fav.count():
                fav.click()
                page.wait_for_timeout(600)
                ck("收藏开关走通（隔离 STATE_HOME 持久化）",
                   (tmp / "state").exists() and
                   any((tmp / "state").rglob("favorites.json")))
            else:
                CI_GATE["skipped_core"].append("收藏开关")
                ck("收藏开关（无社区条目，跳过）", True)

            page.screenshot(path=str(shots / "main.png"), full_page=True)
            # JS 异常才是硬错误；纯资源加载失败（远程截图等）是环境噪音，
            # 同源 API 的失败已由 bad_same_origin 单独盯防，不放跑。
            js_errors = [e for e in console_errors
                         if not e.startswith("Failed to load resource")]
            ck("★ 控制台无 JS error", not js_errors, "; ".join(js_errors[:3]))
            ck("同源请求全通过（本地 API 无 4xx/5xx / 无失败请求）",
               not bad_same_origin, "; ".join(bad_same_origin[:3]))
            browser.close()
    finally:
        httpd.shutdown()
        httpd.server_close()

    n_fail = CHECKS.count(False)
    if CI_GATE["active"] and CI_GATE["skipped_core"]:
        print(f"\nFAIL（--ci）：核心检查被静默跳过：{CI_GATE['skipped_core']} —— "
              f"隔离区数据是确定性的，跳过说明渲染链路坏了，不是数据缺失")
        return 1
    print(f"\n{len(CHECKS) - n_fail} passed, {n_fail} failed")
    print(f"隔离区（含截图）保留在：{tmp}")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
