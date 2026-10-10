"""采集 README 演示截图（dev-only，可选依赖；v2.25 新增）。

定位：README 的演示截图必须来自**真实运行的界面**（评审纪律：不得使用
伪造 UI 图，也不得包含个人隐私）。本脚本在与 ui_smoke 相同纪律的隔离区里
用**合成的确定性数据**起真实服务 + 真浏览器截图：

  · 技能内容 = 现场生成的 demo skill（非任何真实用户内容）；
  · 社区目录 = 仓库自带的 registry/plugins.json（公开注册表数据）；
  · WBM_MARKET_ROOT / WBM_STATE_HOME / WBM_HOME 全部指进临时区，
    真实环境零接触；截图只保留 UI 结构，不含任何本机路径与口令。

用法：
  python scripts/capture-screenshots.py [输出目录，默认 docs/screenshots]

依赖 playwright + chromium（未安装时打印 SKIP 退出 0，与 ui_smoke 同口径）。
"""

import shutil
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "screenshots"

_COPY_ITEMS = ("web", "registry", ".codebuddy-plugin")


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP：未安装 playwright（pip install playwright && "
              "python -m playwright install chromium）")
        return 0

    demo_skills = {
        "pdf-tools": "PDF 工具箱：合并、拆分、提取文本",
        "notes-export": "笔记导出：把本地笔记打包成 Markdown",
    }
    tmp = Path(tempfile.mkdtemp(prefix="wbm-shots-"))
    root = tmp / "market"
    root.mkdir(parents=True)
    for item in _COPY_ITEMS:
        src = ROOT / item
        if src.exists():
            if src.is_dir():
                shutil.copytree(src, root / item,
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else:
                shutil.copy2(src, root / item)
    # 合成的 demo skills + 对应配置（绝不携带真实用户的 skill 内容）
    plugins = []
    for i, (name, desc) in enumerate(demo_skills.items(), 1):
        d = root / "plugins" / f"demo-bundle-{i}" / "skills" / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            f"---\nname: {name}\nversion: 1.0.0\ndescription: \"{desc}\"\n---\n\n# {name}\n"
            "演示截图用的合成 skill（capture-screenshots.py 现场生成）。\n",
            encoding="utf-8")
        plugins.append({
            "name": f"demo-bundle-{i}", "version": "1.0.0",
            "displayName": name, "category": "演示",
            "description": desc, "keywords": [], "skills": [name],
        })
    cfg = __import__("json").loads(
        (ROOT / "market.config.example.json").read_text(encoding="utf-8"))
    cfg["localPlugins"] = plugins
    (root / "market.config.json").write_text(
        __import__("json").dumps(cfg, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    import os
    os.environ["WBM_MARKET_ROOT"] = str(root)
    os.environ["WBM_STATE_HOME"] = str(tmp / "state")
    os.environ["WBM_HOME"] = str(tmp / "wb")
    (tmp / "wb").mkdir()
    os.environ["WBM_CATALOG_OFF"] = "1"

    sys.path.insert(0, str(ROOT))
    import market_server as srv

    httpd = srv.make_server(0, token="shots-token")
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"

    OUT.mkdir(parents=True, exist_ok=True)
    ok = 0
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(base, wait_until="domcontentloaded")
            page.wait_for_selector("#content .card", timeout=30000)
            page.wait_for_timeout(800)
            page.screenshot(path=str(OUT / "home-local.png"), full_page=False)
            ok += 1
            page.click("#tab-curated")
            page.wait_for_timeout(900)
            page.screenshot(path=str(OUT / "home-curated.png"), full_page=False)
            ok += 1
            d = page.locator("[data-regdetail]").first
            if d.count():
                d.click()
                page.wait_for_selector("#cfm.show", timeout=5000)
                page.wait_for_timeout(300)
                page.screenshot(path=str(OUT / "detail-four-questions.png"))
                page.keyboard.press("Escape")
                ok += 1
            browser.close()
    finally:
        httpd.shutdown()
        httpd.server_close()
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"OK：{ok} 张截图已写入 {OUT}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
