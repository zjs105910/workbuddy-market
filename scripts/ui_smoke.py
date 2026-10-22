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

            # ---- v2.35 NEXT_STEPS 任务5：GitHub 全网搜索「加载更多」翻页。
            # 页面内桩掉 fetch（只拦 /api/gh/search，其余透传）——不依赖
            # 真实 GitHub（匿名 API 限流 + 代理抖动会让这检查变flake）。
            page.click("#tab-explore")
            page.fill("#q", "zzz-不存在的词-zzz")   # 收录源零命中 → 触发全网搜索
            page.evaluate("""
(() => {
  const real = window.fetch;
  window.__realFetch = real;
  window.fetch = (path, opt) => {
    if (String(path).indexOf('/api/gh/search') === 0) {
      const page = Number(new URLSearchParams(String(path).split('?')[1])
                            .get('page') || 1);
      const items = [];
      for (let i = 0; i < 20; i++) {
        items.push({repo: 'fake/repo-p' + page + '-' + i, description: 'stub',
                    htmlUrl: 'https://github.com/fake/repo', stars: 1,
                    pushedAt: '2026-10-01', language: 'Python', archived: false});
      }
      return Promise.resolve({ok: true, status: 200,
        json: () => Promise.resolve({ok: true, items})});
    }
    return real(path, opt);
  };
})()
""")
            page.wait_for_timeout(1200)   # 防抖 550ms + 渲染
            n1 = page.locator("#ghGrid .card").count()
            more_n = page.locator("[data-ghmore]").count()
            ck("★ 全网搜索渲染 + 满页出现「加载更多」（任务5）",
               n1 == 20 and more_n == 1, f"cards={n1} more={more_n}")
            if more_n:
                page.locator("[data-ghmore]").click()
                page.wait_for_timeout(800)
                n2 = page.locator("#ghGrid .card").count()
                ck("★ 「加载更多」翻页追加（20 → 40，任务5）",
                   n2 == 40, f"cards={n2}")
            # 恢复 fetch。**表达式不能返回 fetch 函数本身** —— Playwright 的
            # evaluate 结果序列化会调用它（传 null），产生一个 fetch(null)
            # → GET /null 404，污染「同源请求全通过」门禁（实锤：最小复现
            # page.evaluate("window.fetch = window.fetch") 即触发）。
            # void 掉，返回值 undefined，安全。
            page.evaluate("void (window.fetch = window.__realFetch)")
            page.fill("#q", "")
            page.wait_for_timeout(400)
            page.click("#tab-local")
            page.wait_for_timeout(300)

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

            # ---- v2.35 NEXT_STEPS 任务6：筛选 chip aria-pressed 同步
            page.locator('[data-f="todo"]').click()
            page.wait_for_timeout(250)
            ap_todo = page.locator('[data-f="todo"]').get_attribute("aria-pressed")
            ap_all = page.locator('[data-f="all"]').get_attribute("aria-pressed")
            ck("★ 筛选 chip aria-pressed 同步（任务6）",
               ap_todo == "true" and ap_all == "false",
               f"todo={ap_todo} all={ap_all}")
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
                page.wait_for_function(
                    "!document.querySelector('#cfm').classList.contains('show')",
                    timeout=5000)
                # v2.35 NEXT_STEPS 任务3：工件构建日期显式化。精选列表
                # 前几张可能是不带工件的 ghpm-only 条目，遍历前 6 张找到
                # 带固定产物的再断言（100 条收录里 ghpm-only 不足半数，
                # 前 6 张必中；隔离区 registry 是仓库副本，数据确定性）。
                date_seen = False
                n_detail = page.locator("[data-regdetail]").count()
                for i in range(min(6, n_detail)):
                    page.locator("[data-regdetail]").nth(i).click()
                    page.wait_for_selector("#cfm.show", timeout=5000)
                    body = page.locator("#cfmBody").inner_text()
                    if "工件构建日期" in body:
                        date_seen = True
                    page.locator("#cfmYes").click()
                    page.wait_for_function(
                        "!document.querySelector('#cfm').classList.contains('show')",
                        timeout=5000)
                    if date_seen:
                        break
                ck("★ 详情弹窗展示工件构建日期（任务3，零协议变更）", date_seen)
                # 循环每轮结束都已关窗（wait_for_function 保证），这里不能再点
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

            # ==== 2026-10-14 用户实测 P0 回归：data-radd 安装链路三连坑 ====
            # ① const note +=：点「一键安装」即 TypeError，确认弹窗都不出现；
            # ② usePkg 块级作用域：确认后 ReferenceError，被 try/catch 吞掉；
            # ③ errorBox 不 add("show")：错误弹窗从不显示，await 它的调用方
            #    全部静默挂起（v2.24 结构化错误自此形同虚设）。
            # 回归口径：确认弹窗必须出现且含路由说明；取消后不得起任务；
            # errorBox 必须真的进入 .show。三项任一静默即 FAIL。
            page.click("#tab-curated")
            page.wait_for_timeout(500)
            radd_btn = page.locator("[data-radd]").first
            if radd_btn.count():
                radd_btn.click()
                try:
                    page.wait_for_selector("#cfm.show", timeout=5000)
                    rtitle = page.locator("#cfmTitle").inner_text()
                    rbody = page.locator("#cfmBody").inner_text()
                    ck("★ 一键安装确认弹窗（radd 链路不再静默死亡）",
                       ("安装" in rtitle) and ("不可变产物" in rbody or "ghpm" in rbody),
                       rtitle[:60])
                    # ---- v2.35 NEXT_STEPS 任务6：弹窗 ARIA + 焦点管理
                    dia_role = page.locator("#cfm").get_attribute("role")
                    dia_modal = page.locator("#cfm").get_attribute("aria-modal")
                    focus_in = page.evaluate(
                        "document.activeElement ? document.activeElement.id : ''")
                    ck("★ 弹窗 ARIA 语义 + 焦点进主按钮（任务6）",
                       dia_role == "dialog" and dia_modal == "true"
                       and focus_in == "cfmYes",
                       f"role={dia_role} modal={dia_modal} focus={focus_in}")
                    page.keyboard.press("Tab")
                    tab_in = page.evaluate(
                        "!!(document.activeElement && document.activeElement.closest('#cfm'))")
                    ck("★ Tab 焦点锁在弹窗内（任务6）", tab_in)
                    page.locator("#cfmNo").click()      # 取消，不真装
                    page.wait_for_function(
                        "!document.querySelector('#cfm').classList.contains('show')",
                        timeout=5000)
                    ck("★ 取消安装不起任务（veil 不出现）",
                       "show" not in (page.locator("#veil").get_attribute("class") or ""))
                    focus_back = page.evaluate(
                        "document.activeElement ? (document.activeElement.dataset"
                        ".radd || document.activeElement.dataset.rupdate || '') : ''")
                    ck("★ 关闭后焦点归还触发者（任务6）", focus_back != "", focus_back)
                except Exception as exc:  # noqa: BLE001 —— 弹窗不出现本身就是失败
                    ck("★ 一键安装确认弹窗（radd 链路不再静默死亡）", False, str(exc)[:80])
            else:
                ck("★ 一键安装确认弹窗（隔离区无 radd 入口）", False, "注册表卡片未渲染")
            # errorBox 可见性：直接调模块函数（静态白名单可达），断言 #cfm 真的显示。
            # 修复前这个函数从不 add("show")——所有错误弹窗路径静默挂起。
            page.evaluate(
                "(async () => { const m = await import('/static/app/utils.js');"
                " window.__eb = m.errorBox; return typeof window.__eb; })()")
            page.evaluate("void window.__eb('errorBox 可见性回归', new Error('boom'))")
            try:
                page.wait_for_selector("#cfm.show", timeout=5000)
                eb_title = page.locator("#cfmTitle").inner_text()
                ck("★ errorBox 真的可见（结构化错误弹窗回归）",
                   "errorBox" in eb_title, eb_title[:60])
                page.locator("#cfmYes").click()         # 关闭
                page.wait_for_timeout(300)
            except Exception as exc:  # noqa: BLE001
                ck("★ errorBox 真的可见（结构化错误弹窗回归）", False, str(exc)[:80])
            page.click("#tab-local")
            page.wait_for_timeout(300)

            # ==== 2026-10-14 用户实测 P1 回归（审计 D1）：工件安装全旅程 ====
            # 用户实测原话：「安装完成之后看不到它安装在了哪里，在本机技能和
            # 已安装里都没有显示」。验收：UI 点安装 → 完成 toast 说清装去哪 →
            # 社区安装分区可见 → 市场内卸载 → 回收站 → 磁盘落账。
            # 走真实点击流（不裸 fetch）：watchJob 的完成回调才会刷新 STATE。
            # v2.35 修正：obra 的安装入口位置取决于隔离配置——**收录源配置**
            # （本机 market.config.json）在探索页；**fresh-clone 配置**
            # （example 无收录源，CI 就是这样）在精选页的注册表卡片上。
            # 两处都试 —— CI 首跑实锤：把「配置形态」误判成「链路坏了」。
            page.click("#tab-explore")
            page.wait_for_timeout(500)
            art_btn = page.locator('[data-radd="obra/superpowers"]')
            on_explore = art_btn.count() > 0
            if not on_explore:
                page.click("#tab-curated")
                page.wait_for_timeout(400)
                art_btn = page.locator('[data-radd="obra/superpowers"]')
            if art_btn.count():
                art_btn.click()
                page.wait_for_selector("#cfm.show", timeout=5000)
                route_txt = page.locator("#cfmBody").inner_text()
                ck("★ 工件安装确认框说明固定产物链路（哈希校验先行）",
                   ("产物" in route_txt) and ("SHA" in route_txt or "哈希" in route_txt),
                   route_txt[:60])
                page.locator("#cfmYes").click()
                # 任务弹窗起来 → 等完成 toast（artifact 下载+校验+事务安装）。
                # 轮询口径：toast 正在显示且文本含「已装入」——不看「从隐藏到
                # 显示」的边沿（旧 toast 的 3.4s 自动隐藏会制造假竞争），
                # toast 元素的 textContent 在隐藏后仍残留旧文本，必须同时判可见。
                done_toast = ""
                canceled_fallback = False
                try:
                    for i in range(180):
                        page.wait_for_timeout(1000)
                        showing = page.evaluate(
                            "document.querySelector('#toast')"
                            ".classList.contains('show')")
                        if showing:
                            done_toast = page.locator("#toast").inner_text()
                            if "已装入" in done_toast:
                                break
                        # v2.36.1 兜底：网络差时工件下载能拖几分钟 —— 2 分钟
                        # 仍无完成迹象（✓/✗）就点新加的「取消任务」按钮收尾
                        # （真实旅程：/api/job/<id>/cancel 终止整棵进程树），
                        # 保证 smoke 不会被单个卡住的任务拖崩。
                        label = page.locator("#jobLabel").inner_text()
                        if label.startswith(("✓", "✗")):
                            break
                        if i == 120:
                            try:
                                page.locator("#jobCancel").click(timeout=3000)
                                canceled_fallback = True
                            except Exception:  # noqa: BLE001
                                pass
                    ck("★ 工件安装完成 toast 说明落盘位置（修复「看不到装在哪」）",
                       "已装入" in done_toast,
                       done_toast[:80] +
                       ("；2 分钟无完成迹象，已走取消兜底" if canceled_fallback else ""))
                except Exception as exc:  # noqa: BLE001
                    ck("★ 工件安装完成 toast 说明落盘位置（修复「看不到装在哪」）",
                       False, str(exc)[:80])
                # 任务弹窗完成后仍开着（watchJob 语义：后台继续），
                # 先关掉否则 #veil 会挡住后续所有点击。取消兜底刚把任务
                # 终结时 jobClose 才从 disabled 变 enabled，放宽等待。
                try:
                    page.locator("#jobClose").click(timeout=30000)
                except Exception:  # noqa: BLE001 —— 弹窗已关就不必再关
                    pass
                page.wait_for_timeout(300)
                # 社区安装分区 + 卡片可见（修复前：装完哪里都看不到）。
                # 断言口径 = 卡片真实渲染文案：工件链描述是「通过精选市场安装：
                # 不可变工件 …」（state.py build_state）。此前写的是
                # 「精选市场工件安装」——UI 里不存在这个字符串，断言恒假
                # （下面对应的「卸载后消失」则恒真），属于测试自身缺陷。
                page.click("#tab-local")
                page.wait_for_timeout(600)
                sec_seen = page.evaluate(
                    "document.body.innerText.indexOf('通过精选市场安装') >= 0")
                card_seen = page.locator(
                    '[data-uninstall="obra/superpowers"]').count() > 0
                ck("★ 安装后「社区安装」分区与卡片可见（本机技能页）",
                   bool(sec_seen) and bool(card_seen), "obra/superpowers")
                inv_seen = page.evaluate(
                    "document.body.innerText.indexOf('本机 WorkBuddy 技能一览') >= 0")
                ck("★ 本机技能只读清单渲染（全部本机技能 + 来源标注）", bool(inv_seen))
                # v2.35 用户实测三修回归：顶部统计如实纳入社区安装
                # （去空白比对：innerText 可能带回不换行空格等不可见变体）
                metric_txt = page.locator("#metrics").inner_text()
                metric_norm = "".join(metric_txt.split())
                ck("★ 顶部统计纳入社区安装（社区安装 N 个 · 已装 X/Y skill）",
                   ("社区安装1个" in metric_norm) and ("15/15" in metric_norm),
                   ascii(metric_txt)[:120])
                # v2.35 用户实测三修回归：已装收录源移出探索页（提示 + 跳转）。
                # 只在「obra 是收录源」的配置形态下断言；fresh-clone 形态
                # （无收录源）改看精选页的入口翻转（radd → 本机技能页查看）。
                if on_explore:
                    page.click("#tab-explore")
                    page.wait_for_timeout(400)
                    exp_gone = page.locator(
                        '[data-rupdate="obra/superpowers"]').count() == 0
                    hint_seen = page.evaluate(
                        "document.body.innerText.indexOf('社区安装分区统一管理') >= 0")
                    ck("★ 探索页已装收录源移管（卡片消失 + 提示出现）",
                       bool(exp_gone) and bool(hint_seen),
                       f"卡片隐藏={exp_gone} 提示={hint_seen}")
                    # v2.35 四修回归：「已装好」筛选在探索页也不显示已装源
                    # （用户实测：选已装好又看到它们，不符合「只在社区安装页」预期）
                    page.locator('[data-f="done"]').click()
                    page.wait_for_timeout(400)
                    done_gone = page.locator(
                        '[data-rupdate="obra/superpowers"]').count() == 0
                    done_hint = page.evaluate(
                        "document.body.innerText.indexOf('社区安装分区统一管理') >= 0")
                    ck("★ 探索页「已装好」筛选也不再显示已装源（四修，只留提示）",
                       bool(done_gone) and bool(done_hint),
                       f"卡片隐藏={done_gone} 提示={done_hint}")
                    page.locator('[data-f="all"]').click()
                    page.wait_for_timeout(200)
                else:
                    page.click("#tab-curated")
                    page.wait_for_timeout(400)
                    cur_gone = page.locator(
                        '[data-radd="obra/superpowers"]').count() == 0
                    cur_seen = page.locator(
                        '[data-regdetail="obra/superpowers"]').count() > 0
                    ck("★ 安装后精选页入口翻转（工件 → 本机技能页查看，任务5 口径）",
                       bool(cur_gone) and bool(cur_seen),
                       f"入口消失={cur_gone} 卡片在={cur_seen}")
                page.click("#tab-local")
                page.wait_for_timeout(300)
                # 市场内卸载：确认弹窗列出将移除的 skill → 回收站。
                # 卸载是同步 POST（响应回来即 toast），同样用「可见 + 关键词」
                # 轮询，避开 toast 元素残留旧文本与 3.4s 自动隐藏的竞争。
                un = page.locator('[data-uninstall="obra/superpowers"]')
                if un.count():
                    un.click()
                    page.wait_for_selector("#cfm.show", timeout=5000)
                    plan_txt = page.locator("#cfmBody").inner_text()
                    page.locator("#cfmYes").click()
                    un_toast = ""
                    try:
                        for _ in range(60):
                            page.wait_for_timeout(500)
                            showing = page.evaluate(
                                "document.querySelector('#toast')"
                                ".classList.contains('show')")
                            if showing:
                                un_toast = page.locator("#toast").inner_text()
                                if "回收站" in un_toast or "移除" in un_toast:
                                    break
                        ck("★ 市场内卸载工件安装（确认 → 回收站 toast）",
                           ("回收站" in un_toast or "移除" in un_toast)
                           and ("将移入回收站" in plan_txt), un_toast[:60])
                    except Exception as exc:  # noqa: BLE001
                        ck("★ 市场内卸载工件安装（确认 → 回收站 toast）",
                           False, str(exc)[:80])
                    wb_skills = tmp / "wb-home" / "skills"
                    ck("★ 卸载后磁盘落账（隔离 WBM_HOME 技能已移走）",
                       wb_skills.is_dir() and not (wb_skills / "brainstorming").exists())
                    page.click("#tab-local")
                    page.wait_for_timeout(500)
                    gone = page.evaluate(
                        "document.body.innerText.indexOf('通过精选市场安装') < 0")
                    ck("★ 卸载后社区分区消失（状态闭环）", bool(gone))
                    # v2.35 用户实测三修回归：卸载后安装入口恢复（状态闭环）。
                    # 收录源形态在探索页恢复；fresh-clone 形态在精选页恢复。
                    page.click("#tab-explore")
                    page.wait_for_timeout(400)
                    back = page.locator(
                        '[data-radd="obra/superpowers"]').count() > 0
                    if not back:
                        page.click("#tab-curated")
                        page.wait_for_timeout(400)
                        back = page.locator(
                            '[data-radd="obra/superpowers"]').count() > 0
                    ck("★ 卸载后安装入口恢复（探索页或精选页，状态闭环）",
                       bool(back))
                else:
                    CI_GATE["skipped_core"].append("市场内卸载工件安装")
                    ck("★ 市场内卸载工件安装（社区卡片无卸载按钮）", False,
                       "安装成功但卡片没有卸载入口")
            else:
                CI_GATE["skipped_core"].append("工件安装全旅程")
                ck("★ 工件安装全旅程（精选页无 obra/superpowers 安装入口）", False,
                   "隔离区注册表没有该条目或已被收录源去重")

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
            errs2 = []
            pg2.on("pageerror", lambda e: errs2.append(str(e)))
            pg2.goto(base, wait_until="domcontentloaded")
            try:
                pg2.wait_for_selector("#tab-local", timeout=10000)
                pg2.wait_for_timeout(1200)
                ck("★ 空市场状态：界面骨架正常（tab 就位、无 pageerror）",
                   not errs2 and pg2.locator("#tab-curated").count() == 1,
                   "; ".join(errs2[:2]))
                # v2.35 任务2：空态明示「未收录 ≠ 已删除」+ 两步引导
                t2 = pg2.locator("#content").inner_text()
                ck("★ 空本机插件态：「未收录 ≠ 已删除」+ 两步引导（任务2）",
                   ("未收录" in t2) and ("重新打包" in t2), t2[:80])
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
                # v2.35 任务2：未初始化态 doctor 报 △ 待初始化（不是 ✗）
                pg4.click("#btnDoctor")
                pg4.wait_for_selector("#cfm.show", timeout=10000)
                body4 = pg4.locator("#cfmBody").inner_text()
                ck("★ 未初始化 doctor：△ 待初始化而非 ✗（任务2）",
                   ("△" in body4) and ("待初始化" in body4), body4[:80])
                pg4.locator("#cfmYes").click()
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
