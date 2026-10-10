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
    """fresh clone 没有 market.config.json 也没有 plugins/（两者都不入库）
    —— run #3 / run #4 双实锤。合成一份确定性配置：
      · plugins/ 里扫得到 SKILL.md → 全量收编为单个 localPlugin；
      · 扫不到（CI）→ 现场生成一个最小 dummy skill，保证 --ci 门禁的
        「本机安装端到端」必然有可交互项。
    已有配置绝不覆盖（幂等）。"""
    cfg_path = root / "market.config.json"
    if cfg_path.exists():
        return
    example = json.loads(
        (ROOT / "market.config.example.json").read_text(encoding="utf-8"))
    skills = sorted(
        d.name for d in (root / "plugins").glob("*/skills/*")
        if d.is_dir() and (d / "SKILL.md").is_file())
    if not skills:
        dummy = root / "plugins" / "ci-smoke-suite" / "skills" / "ci-smoke-dummy"
        dummy.mkdir(parents=True, exist_ok=True)
        (dummy / "SKILL.md").write_text(
            "---\nname: ci-smoke-dummy\n"
            "description: ui-smoke --ci 门禁用的确定性最小 skill（运行时生成，非真实内容）\n---\n\n"
            "# CI Smoke Dummy\n\n"
            "本 skill 由 scripts/ui_smoke.py 在隔离区现场生成，用于验收\n"
            "「补齐 → 事务安装 → toast」端到端链路，不代表任何真实插件。\n",
            encoding="utf-8")
        skills = ["ci-smoke-dummy"]
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

            # ---- v2.23：筛选 chip 是原生 button → 键盘 Enter 可激活
            fchip = page.locator("#filters .chip").first
            fchip.focus()
            fchip.press("Enter")
            page.wait_for_timeout(300)
            ck("★ 筛选 chip 为原生 button（键盘 Enter 可激活）",
               fchip.evaluate("el => el.tagName === 'BUTTON'"))
            page.locator('[data-f="all"]').click()
            page.wait_for_timeout(200)

            # ---- v2.23 三入口 tab：本机技能 / 精选市场 / 探索 GitHub
            page.click("#tab-curated")
            page.wait_for_timeout(400)
            t1 = page.locator("#content").inner_text()
            ck("★ tab 精选市场：区块标题出现", ("精选市场" in t1) or ("社区目录" in t1))
            page.click("#tab-explore")
            page.wait_for_timeout(400)
            t2 = page.locator("#content").inner_text()
            ck("★ tab 探索 GitHub：收录源区块出现", "GitHub 收录源" in t2)
            page.click("#tab-local")
            page.wait_for_timeout(400)
            ck("★ tab 本机技能：卡片恢复", page.locator("#content .card").count() >= 1)

            # ---- 注册表详情弹窗（社区目录有收录时）：v2.23 四问结构
            page.click("#tab-curated")
            page.wait_for_timeout(300)
            detail_btn = page.locator("[data-regdetail]").first
            if detail_btn.count():
                detail_btn.click()
                page.wait_for_selector("#cfm.show", timeout=5000)
                body = page.locator("#cfmBody").inner_text()
                ck("★ 注册表详情弹窗：安装前四问（来自哪里/是否可信/能做什么/能否安装）",
                   all(k in body for k in ("来自哪里", "是否可信", "能做什么", "能否安装")),
                   body[:80])
                page.locator("#cfmYes").click()
                page.wait_for_timeout(200)
            else:
                CI_GATE["skipped_core"].append("注册表详情弹窗")
                ck("注册表详情弹窗（社区目录为空，跳过）", True)
            page.click("#tab-local")
            page.wait_for_timeout(300)

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
            # v2.23 起 Homepage 分三个 tab，收藏按钮只在「精选市场」渲染 ——
            # 检查前必须切过去（v2.25 实锤：停在「本机技能」tab 找不到
            # data-fav 被静默跳过，--ci 门禁即 FAIL）。
            page.click("#tab-curated")
            page.wait_for_timeout(300)
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
            page.click("#tab-local")
            page.wait_for_timeout(300)

            # ==== v2.24 扩展：卸载旅程 / Escape / 响应式 ====
            # 等安装 toast 收起（3.4s 自动隐藏），避免把安装的 toast 误读成卸载结果
            page.wait_for_function(
                "!!document.querySelector('#toast') && "+
                "!document.querySelector('#toast').classList.contains('show')",
                timeout=10000)
            # 卸载 → 回收站（安装端到端之后，第一张本机卡片必有「卸载…」）
            uns = page.locator("[data-uninstall]").first
            if uns.count():
                uns.click()
                page.wait_for_selector("#cfm.show", timeout=5000)
                page.locator("#cfmYes").click()          # 确认「卸载」
                page.wait_for_function(
                    "document.querySelector('#toast').classList.contains('show')",
                    timeout=30000)
                toast_txt = page.locator("#toast").inner_text()
                ck("★ 卸载旅程（确认 → 移入回收站 → toast）",
                   ("回收站" in toast_txt) or ("移除" in toast_txt), toast_txt)
                ck("★ 卸载后磁盘落账：隔离区回收站非空",
                   any((tmp / "state" / "trash").rglob("*")) if (tmp / "state" / "trash").exists()
                   else False)
            else:
                ck("卸载旅程（无可卸载项，跳过）", True)

            # Escape 关弹窗（可访问性）
            page.click("#tab-curated")
            page.wait_for_timeout(300)
            d2 = page.locator("[data-regdetail]").first
            if d2.count():
                d2.click()
                page.wait_for_selector("#cfm.show", timeout=5000)
                page.keyboard.press("Escape")
                page.wait_for_timeout(300)
                ck("★ Escape 关闭弹窗",
                   "show" not in (page.locator("#cfm").get_attribute("class") or ""))
            else:
                ck("Escape 关闭弹窗（无详情入口，跳过）", True)
            page.click("#tab-local")
            page.wait_for_timeout(300)

            # 响应式三档：核心入口可见 + 无意外横向溢出
            overflow_ok, tabs_ok = True, True
            for w in (360, 768, 1280):
                page.set_viewport_size({"width": w, "height": 900})
                page.wait_for_timeout(250)
                sw = page.evaluate(
                    "document.documentElement.scrollWidth")
                cw = page.evaluate(
                    "document.documentElement.clientWidth")
                if sw > cw + 2:
                    overflow_ok = False
                if not page.locator("#tabs").is_visible():
                    tabs_ok = False
            ck("★ 响应式 360/768/1280：无横向溢出", overflow_ok)
            ck("★ 响应式 360/768/1280：三入口 tab 始终可见", tabs_ok)
            page.set_viewport_size({"width": 1280, "height": 900})
            page.wait_for_timeout(250)

            page.screenshot(path=str(shots / "main.png"), full_page=True)

            # ==== v2.24 扩展：配置损坏 / 缺失 / 空市场的界面状态 ====
            # 同一隔离区、同一服务进程：config 是每请求从磁盘读的，
            # 改磁盘即改状态（确定性，无注入魔法）。
            cfg_path = market_root / "market.config.json"
            cfg_backup = cfg_path.read_bytes()

            # --- 空市场：合法但没有任何插件与收录源
            empty_cfg = json.loads(cfg_backup.decode("utf-8"))
            empty_cfg["localPlugins"] = []
            empty_cfg["remoteSources"] = []
            cfg_path.write_text(json.dumps(empty_cfg, ensure_ascii=False),
                                encoding="utf-8")
            pg2 = browser.new_page()
            errs2, toasts2 = [], []
            pg2.on("pageerror", lambda e: errs2.append(str(e)))
            pg2.goto(base, wait_until="domcontentloaded")
            try:
                pg2.wait_for_selector("#tab-local", timeout=10000)
                pg2.wait_for_timeout(1200)
                ck("★ 空市场状态：界面骨架正常（tab 就位、无 pageerror）",
                   not errs2 and pg2.locator("#tab-curated").count() == 1,
                   "; ".join(errs2[:2]))
            finally:
                pg2.close()

            # --- 配置损坏：结构化错误 + 界面不白屏
            cfg_path.write_bytes(b"{broken,,,")
            pg3 = browser.new_page()
            errs3 = []
            pg3.on("pageerror", lambda e: errs3.append(str(e)))
            pg3.goto(base, wait_until="domcontentloaded")
            try:
                pg3.wait_for_function(
                    "document.querySelector('#toast').classList.contains('show')",
                    timeout=15000)
                t3 = pg3.locator("#toast").inner_text()
                ck("★ 配置损坏状态：结构化人话报错（无裸异常、无 pageerror）",
                   not errs3 and ("配置" in t3) and ("Traceback" not in t3), t3[:80])
            finally:
                pg3.close()

            # --- 配置缺失：同样结构化、不白屏
            cfg_path.unlink()
            pg4 = browser.new_page()
            errs4 = []
            pg4.on("pageerror", lambda e: errs4.append(str(e)))
            pg4.goto(base, wait_until="domcontentloaded")
            try:
                pg4.wait_for_function(
                    "document.querySelector('#toast').classList.contains('show')",
                    timeout=15000)
                t4 = pg4.locator("#toast").inner_text()
                ck("★ 配置缺失状态：结构化人话报错（界面照常可打开）",
                   not errs4 and ("配置" in t4), t4[:80])
            finally:
                pg4.close()
            cfg_path.write_bytes(cfg_backup)   # 还原，别污染后续

            # --- doctor 体检入口（v2.24，只读）
            pg5 = browser.new_page()
            errs5 = []
            pg5.on("pageerror", lambda e: errs5.append(str(e)))
            pg5.goto(base, wait_until="domcontentloaded")
            try:
                pg5.wait_for_selector("#tab-local", timeout=10000)
                pg5.click("#btnDoctor")
                pg5.wait_for_selector("#cfm.show", timeout=10000)
                body5 = pg5.locator("#cfmBody").inner_text()
                ck("★ doctor 体检弹窗（检查项 + 脱敏说明）",
                   not errs5 and ("体检" in body5 or "✓" in body5 or "✗" in body5)
                   and "脱敏" in body5, body5[:60])
            finally:
                pg5.close()

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
