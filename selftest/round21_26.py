# -*- coding: utf-8 -*-
"""第 36-41 节（v2.22-v2.28）：onboard 向导 / 安装四问 / 结构化错误 / 入门体验 / latestSha 回写 / zip 市场构建。"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from . import REPO_ROOT, _TMP, ck, core, section


def round21():
    """v2.22：onboard 首次启动向导 / 配置安全初始化（第 36 节）。

    八条盯防线（评审 P0「让普通用户一次用成功」的当轮落地）：
    1. 配置缺失 + 模板存在 → 初始化成功、产物合法、发现的 skills 绝不
       被自动收录（localPlugins 保持空，加入市场内容由用户决定）；
    2. 配置已存在（合法）→ 一字节不动（sha256 前后一致）；
    3. 配置损坏 → 原样保留 + 明确错误位置与恢复建议，绝不覆盖；
    4. 模板缺失 / 模板损坏 → 诚实报错，不生成猜测配置；
    5. 并发初始化（真并发线程）→ 恰好一个 created、其余 exists，
       产物完整；写入中途失败 → 半成品被清理，不留半截 JSON；
    6. 非交互环境 → 不等待输入，直接纯浏览并说明原因；
    7. 交互首次启动 → 回车 = 只浏览（默认安全）；显式选 2 = 注册意图，
       但向导本身绝不写 known_marketplaces.json；
    8. 全新克隆启动端到端（真子进程 + 真 HTTP）：源目录没有
       market.config.json、不靠任何预合成配置 —— 启动后配置被自动
       初始化、页面可达、纯浏览模式下 known_marketplaces.json 不存在。
    """
    section("36. v2.22：onboard 首次启动向导 / 配置安全初始化")
    import workbuddy_market.onboard as ob

    # --- 环境准备：隔离区市场根里补上 web/ 与模板（全新克隆的形状）
    web_min = core.MARKET_ROOT / "web"
    web_min.mkdir(exist_ok=True)
    (web_min / "index.html").write_text("<html><body>min</body></html>", encoding="utf-8")
    tpl = core.MARKET_ROOT / "market.config.example.json"
    tpl.write_text(json.dumps({
        "schemaVersion": 2, "marketId": "wb-local-market",
        "name": "本机插件市场", "owner": {"name": "WorkBuddy Local Market"},
        "localPlugins": [], "remoteSources": [],
        "packaging": {"verify": "auto", "hashAlgorithm": "sha256"},
        "trash": {"maxAgeDays": 30, "maxSizeBytes": 2147483648},
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    cfg_backup = core.CONFIG_PATH.read_bytes()   # 收尾恢复用
    # 前序轮次（第 13 节注册测试等）可能已经动过注册文件 —— 这里快照做「不被改动」断言
    known_before = (core.KNOWN_PATH.read_bytes()
                    if core.KNOWN_PATH.exists() else None)
    try:
        # --- 36A. 缺失 + 模板存在 → 初始化成功且能继续启动
        core.CONFIG_PATH.unlink()
        r = ob.init_config()
        ck("★ 配置缺失 + 模板存在 → 初始化成功", r["action"] == "created")
        created = json.loads(core.CONFIG_PATH.read_text(encoding="utf-8"))
        ck("★ 初始化产物是合法配置且可被 load_config 继续",
           created["marketId"] == ob.unique_market_id("wb-local-market")
           and created["marketId"] != "wb-local-market"
           and core.load_config()["marketId"] == created["marketId"])
        ck("★ 发现的 skills 不被自动收录（localPlugins 保持空）",
           created["localPlugins"] == [] and created["remoteSources"] == []
           and len(ob.discover_skills()) >= 3)   # 前序轮次可能造了更多 skill，只增不减

        # --- 36B. 已存在且合法 → 一字节不动
        before = hashlib.sha256(core.CONFIG_PATH.read_bytes()).hexdigest()
        r = ob.init_config()
        ck("★ 配置已存在 → exists 且 sha256 前后一致",
           r["action"] == "exists"
           and hashlib.sha256(core.CONFIG_PATH.read_bytes()).hexdigest() == before)

        # --- 36C. 损坏 → 原样保留 + 恢复建议
        bad = b'{"marketId": "x",,,,'
        core.CONFIG_PATH.write_bytes(bad)
        st, detail = ob.classify_config()
        ck("★ 损坏配置 → 如实标 corrupt 且给恢复建议",
           st == "corrupt" and "原样保留" in detail)
        r = ob.init_config()
        ck("★ 损坏配置 → 绝不覆盖（字节级一致）",
           r["action"] == "exists" and core.CONFIG_PATH.read_bytes() == bad)

        # --- 36D. 模板缺失 / 模板坏 → 诚实报错
        core.CONFIG_PATH.unlink()
        r = ob.init_config(template_path=core.MARKET_ROOT / "no-such-tpl.json")
        ck("★ 模板缺失 → 诚实报错、不生成猜测配置",
           r["action"] == "error" and "模板" in r["detail"]
           and not core.CONFIG_PATH.exists())
        badtpl = core.MARKET_ROOT / "bad-tpl.json"
        badtpl.write_text("{oops", encoding="utf-8")
        r = ob.init_config(template_path=badtpl)
        ck("★ 模板损坏 → 诚实报错",
           r["action"] == "error" and "JSON" in r["detail"]
           and not core.CONFIG_PATH.exists())
        badtpl.unlink()

        # --- 36E. 并发初始化：真并发 + 注入半途失败
        res = {}

        def _worker(i):
            res[i] = ob.init_config()

        threads = [threading.Thread(target=_worker, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        actions = sorted(v["action"] for v in res.values())
        ck("★ 4 线程并发初始化 → 恰好一个 created，其余沿用（绝不互相覆盖）",
           actions.count("created") == 1 and actions.count("exists") == 3,
           str(actions))
        ck("★ 并发产物是完整合法 JSON（没有半截文件）",
           isinstance(json.loads(core.CONFIG_PATH.read_text(encoding="utf-8")), dict))
        core.CONFIG_PATH.unlink()
        real_write = ob._os_write

        def _boom(fd, view):
            real_write(fd, memoryview(b"{"))
            raise OSError("注入：写到一半进程崩了")

        ob._os_write = _boom
        try:
            try:
                ob.init_config()
            except OSError:
                pass
            ck("★ 写入中途失败 → 半成品被清理（磁盘上没有半截 JSON）",
               not core.CONFIG_PATH.exists())
        finally:
            ob._os_write = real_write

        # --- 36F. 非交互环境：不等待输入
        def _poison(prompt=""):
            raise AssertionError("非交互环境不应等待输入")

        rep = ob.run_wizard(interactive=False, input_func=_poison)
        ck("★ 非交互环境 → 不等待输入，直接纯浏览并说明原因",
           rep["choice"] == "browse" and "非交互" in rep["choiceReason"])

        # --- 36G. 交互首次启动：回车 = 只浏览；显式 2 = 注册意图（仍不写注册文件）
        core.CONFIG_PATH.unlink()
        prompts = []
        rep = ob.run_wizard(interactive=True,
                            input_func=lambda p: (prompts.append(p), "")[1])
        ck("★ 首次启动交互：回车 = 只浏览（默认安全，其他输入也算只浏览）",
           rep["choice"] == "browse" and len(prompts) == 1)
        ck("★ 只浏览 → known_marketplaces.json 原样不动（零副作用）",
           (core.KNOWN_PATH.read_bytes() if core.KNOWN_PATH.exists() else None)
           == known_before)
        core.CONFIG_PATH.unlink()
        rep2 = ob.run_wizard(interactive=True, input_func=lambda p: "2")
        ck("★ 显式选 2 → 注册意图（实际注册仍要过 should_register 闸门）",
           rep2["choice"] == "register")
        ck("★ 注册意图 ≠ 注册行为：向导本身不写 known_marketplaces.json",
           (core.KNOWN_PATH.read_bytes() if core.KNOWN_PATH.exists() else None)
           == known_before)

        # --- 36H. 注册前置闸门（launcher 语义不变）
        import launcher as _L
        ck("★ should_register：打包失败 → 不允许注册",
           _L.should_register(False, True) == (False, "打包没有成功"))
        ck("★ should_register：自检失败 → 不允许注册",
           _L.should_register(True, False)[0] is False)
        ck("★ should_register：全部通过 → 允许注册",
           _L.should_register(True, True) == (True, ""))

        # --- 36I. 全新克隆启动端到端（真子进程 + 真 HTTP，无预合成配置）
        repo_root = REPO_ROOT
        fresh = _TMP / "fresh-clone"
        shutil.rmtree(fresh, ignore_errors=True)
        mk = fresh / "market"
        (mk / "web").mkdir(parents=True)
        shutil.copytree(repo_root / "web" / "app", mk / "web" / "app")
        shutil.copy2(repo_root / "web" / "index.html", mk / "web" / "index.html")
        shutil.copy2(repo_root / "web" / "style.css", mk / "web" / "style.css")
        shutil.copy2(repo_root / "market.config.example.json",
                     mk / "market.config.example.json")
        # 注意：不放 market.config.json —— 这就是全新克隆的形状
        wbhome = fresh / "wb"
        (wbhome / "skills").mkdir(parents=True)
        import socket as _s
        import urllib.request as _ur
        with _s.socket() as _sk:
            _sk.bind(("127.0.0.1", 0))
            eport = _sk.getsockname()[1]
        env = dict(os.environ)
        env.update({"WBM_MARKET_ROOT": str(mk), "WBM_STATE_HOME": str(fresh / "state"),
                    "WBM_HOME": str(wbhome), "WBM_CATALOG_OFF": "1"})
        env.pop("PYTHONPATH", None)          # 干净导入路径（跨平台写法）
        out_path = _TMP / "fresh-clone-stdout.txt"
        proc = None
        ok200 = False
        try:
            with open(out_path, "w", encoding="utf-8") as out_f:
                proc = subprocess.Popen(
                    [sys.executable, str(repo_root / "launcher.py"),
                     "--no-open", "--port", str(eport)],
                    stdout=out_f, stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL, env=env, cwd=str(repo_root))
                deadline = time.time() + 60
                while time.time() < deadline:
                    if proc.poll() is not None:
                        break
                    try:
                        with _ur.urlopen(f"http://127.0.0.1:{eport}/", timeout=3) as resp:
                            if resp.status == 200:
                                ok200 = True
                                break
                    except Exception:
                        time.sleep(0.3)
            ck("★ 全新克隆启动：HTTP 页面可达（真子进程）", ok200)
            cfg_new = mk / "market.config.json"
            ck("★ 全新克隆启动：配置被向导自动初始化（零手工步骤）",
               cfg_new.is_file()
               and json.loads(cfg_new.read_text(encoding="utf-8"))["marketId"]
               == ob.unique_market_id("wb-local-market", mk))
            ck("★ 全新克隆启动：纯浏览模式 → known_marketplaces.json 不存在",
               not (wbhome / "plugins" / "known_marketplaces.json").exists())
            out_text = out_path.read_text(encoding="utf-8", errors="replace")
            ck("★ 全新克隆启动：向导输出了三态检查（成功/警告/失败可见）",
               "首次启动检查" in out_text and "已从模板初始化" in out_text)
        finally:
            if proc is not None and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()

        # --- 36J. 预检覆盖与端口探测
        core.CONFIG_PATH.unlink()
        checks = ob.precheck(port_probe=lambda p: p, port=8777)
        names = [c["name"] for c in checks]
        ck("★ 预检覆盖：Python / 仓库布局 / 配置 / skills / WorkBuddy / 端口",
           all(n in names for n in ("Python 版本", "市场目录（仓库布局）",
                                    "配置文件", "本机 skills", "WorkBuddy 家目录",
                                    "服务端口")))
        cfgc = [c for c in checks if c["name"] == "配置文件"][0]
        ck("★ 预检：配置缺失 = 警告不挡路", cfgc["ok"] and cfgc["warn"])
        pc = [c for c in checks if c["name"] == "服务端口"][0]
        ck("★ 预检：端口空闲 → 成功", pc["ok"] and not pc["warn"])
        checks2 = ob.precheck(port_probe=lambda p: p + 3, port=8777)
        pc2 = [c for c in checks2 if c["name"] == "服务端口"][0]
        ck("★ 预检：端口被占 → 警告并给出替换端口",
           pc2["ok"] and pc2["warn"] and "8780" in pc2["detail"])

        # --- 老用户回归：已有配置 → 不询问、行为与 v2.21 一致
        core.CONFIG_PATH.write_bytes(cfg_backup)
        rep3 = ob.run_wizard(interactive=False, input_func=_poison)
        ck("★ 老用户（已有合法配置）→ 不询问、不创建、行为与 v2.21 一致",
           rep3["configAction"] == "none" and rep3["choice"] is None
           and not rep3["created"])
    finally:
        if core.CONFIG_PATH.exists() and core.CONFIG_PATH.read_bytes() != cfg_backup:
            core.CONFIG_PATH.write_bytes(cfg_backup)   # 保险恢复（幂等）
        shutil.rmtree(web_min, ignore_errors=True)
        tpl.unlink(missing_ok=True)


def round22():
    """v2.23：网页信息架构 + 安装前「四问」+ 信任 fail-closed（第 37 节）。

    评审 P1（界面可理解 / 安全信息人话化）的当轮落地，盯防三件事：
    1. 信任分级 fail-closed 不许退化：后端解析层缺失/未知 trust → external
       （v2.16 语义不变）；前端源码不许再出现 `e.trust || "reviewed"` 这种
       fail-open 默认值（v2.21 的真实漏洞，本轮修掉）；
    2. 详情四问结构存在：来自哪里 / 是否可信 / 能做什么 / 能否安装，
       审核范围缺失必须写「未提供」而不是推断；
    3. 三入口 tab（本机技能 / 精选市场 / 探索 GitHub）与「高级信息」折叠
       进入发货的 index.html；筛选/分类控件必须是原生 button（键盘可用）。
    """
    section("37. v2.23：信息架构 / 安装四问 / 信任 fail-closed")
    import workbuddy_market.registry as wr

    # --- 37A. 后端 trust fail-closed（语义不变，回归盯防）
    mk_e = lambda **kw: {"repo": "o/r", "displayName": "X", **kw}  # noqa: E731
    e = wr.parse_registry({"schema": 1, "plugins": [mk_e()]})["plugins"][0]
    ck("★ trust 缺失 → external（绝不默认已审核）", e.get("trust") == "external")
    e = wr.parse_registry({"schema": 1, "plugins": [mk_e(trust="guru")]})["plugins"][0]
    ck("★ trust 越枚举 → external", e.get("trust") == "external")
    e = wr.parse_registry({"schema": 1, "plugins": [
        mk_e(trustObj={"level": "official"})]})["plugins"][0]
    ck("★ trustObj.level=official → official（合法路径不受影响）",
       e.get("trust") == "official")

    # --- 37B. 前端 fail-closed 源码盯防（v2.21 的 fail-open 默认值必须消失）
    web_dir = REPO_ROOT / "web"
    plugins_js = (web_dir / "app" / "plugins.js").read_text(encoding="utf-8")
    registry_js = (web_dir / "app" / "registry.js").read_text(encoding="utf-8")
    ck("★ plugins.js 不再出现 `e.trust || \"reviewed\"`（fail-open 已修）",
       'e.trust || "reviewed"' not in plugins_js)
    ck("★ registry.js 不再出现 `(e.trust || \"reviewed\")` 兜底（fail-open 已修）",
       'e.trust || "reviewed"' not in registry_js)

    # --- 37C. 四问详情 + 三入口 tab 发货盯防
    details_js = (web_dir / "app" / "details.js").read_text(encoding="utf-8")
    ck("★ 详情四问结构（来自哪里/是否可信/能做什么/能否安装）",
       all(k in details_js for k in ("来自哪里", "是否可信", "能做什么", "能否安装")))
    ck("★ 审核范围缺失 → 明确写「未提供」（不推断）",
       "审核范围未提供" in details_js)
    ck("★ 权限声明 ≠ 运行时限制 / 审核 ≠ 绝对安全 的免责文案在场",
       "运行时沙箱" in details_js and "不等于绝对安全" in details_js)
    idx = (web_dir / "index.html").read_text(encoding="utf-8")
    ck("★ index.html 发货三入口 tab（role=tablist）+ 高级信息折叠",
       'role="tablist"' in idx and 'data-tab="local"' in idx
       and 'data-tab="curated"' in idx and 'data-tab="explore"' in idx
       and "<details" in idx and "高级信息" in idx)
    ck("★ 分类/筛选控件全部是原生 button（div.chip 已清零）",
       '<div class="chip"' not in idx and '<button class="chip' in idx)


def round23():
    """v2.24：结构化错误 / doctor Web 入口 / 路径脱敏（第 38 节）。

    评审 P1（「把报错变成可以执行的修复建议」）的当轮落地，盯防四件事：
    1. _api_error_payload 分类正确：config / concurrency / integrity /
       network / internal 各归各位，retryable 语义如实；
    2. **绝不泄密**：内部错误的原始异常文本不进响应载荷（只进本地日志）；
    3. **绝不撒谎**：拿不到「已完成什么」时如实写「无法确认」，
       不自动声称「数据未受影响」；
    4. /api/doctor 只读 + 路径脱敏（用户主目录 → ~）；launcher --status
       在配置缺失时给人话与下一步指引，不再裸抛 traceback。
    """
    section("38. v2.24：结构化错误 / doctor Web 入口 / 路径脱敏")
    import market_server as srv2
    from workbuddy_market.errors import ConfigError, FileLockTimeout

    # --- 38A. 错误映射分类
    p, code = srv2._api_error_payload("/api/install", ConfigError("bad id"))
    ck("★ ConfigError → config 类、不可重试、400",
       p["category"] == "config" and p["retryable"] is False and code == 400
       and p["code"] == "CONFIG_INVALID")
    p, code = srv2._api_error_payload("/api/install", FileLockTimeout("locked"))
    ck("★ FileLockTimeout → concurrency 类、可重试、503",
       p["category"] == "concurrency" and p["retryable"] is True and code == 503)
    p, _ = srv2._api_error_payload("/api/remote/add",
                                   OSError("connection timed out"))
    ck("★ 网络类关键词 → network、可重试",
       p["category"] == "network" and p["retryable"] is True)
    p, _ = srv2._api_error_payload("/api/install", RuntimeError("boom-xyz"))
    ck("★ 未知异常 → internal、不可重试", p["category"] == "internal"
       and p["retryable"] is False)

    # --- 38B. 绝不泄密 / 绝不撒谎
    p, _ = srv2._api_error_payload("/api/install", RuntimeError("boom-xyz"))
    ck("★ 内部错误：原始异常文本不进响应（只进本地日志）",
       "boom-xyz" not in json.dumps(p, ensure_ascii=False))
    ck("★ 内部错误：不谎称「数据未受影响」，如实写「无法确认」",
       "无法确认" in p.get("done", ""))
    ck("★ 每个载荷都带人话 error 与下一步 advice",
       all(p.get(k) for k in ("error", "advice", "stage")))

    # --- 38C. 路径脱敏
    home = str(Path.home())
    fake = home + "\\somewhere\\secret-name"
    ck("★ _sanitize_text：用户主目录 → ~（用户名不进诊断报告）",
       srv2._sanitize_text(fake).startswith("~")
       and Path.home().name not in srv2._sanitize_text(fake))

    # --- 38D. /api/doctor 端到端（真起服务，只读）
    TOKD = "selftest-doctor-token"
    httpd4 = srv2.make_server(0, token=TOKD)
    PORT4 = httpd4.server_address[1]
    threading.Thread(target=httpd4.serve_forever, daemon=True).start()

    def hit4(path, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", PORT4, timeout=10)
        c.request("GET", path, headers=headers or {})
        r = c.getresponse()
        raw = r.read()
        c.close()
        try:
            return r.status, json.loads(raw)
        except Exception:
            return r.status, raw.decode("utf-8", "replace")

    try:
        st, js = hit4("/api/doctor", {"X-Local-Market-Token": TOKD})
        ck("★ GET /api/doctor：200 + checks 列表", st == 200 and js.get("ok")
           and isinstance(js.get("doctor", {}).get("checks"), list)
           and len(js["doctor"]["checks"]) > 0, str(st))
        ck("★ /api/doctor 无口令 → 403（新接口同样过 _guard）",
           hit4("/api/doctor")[0] == 403)
        doc_txt = json.dumps(js, ensure_ascii=False)
        ck("★ /api/doctor 响应不含真实用户主目录（已脱敏为 ~）",
           home not in doc_txt and "~" in doc_txt)
    finally:
        httpd4.shutdown()
        httpd4.server_close()

    # --- 38E. launcher --status：配置缺失 → 人话 + 下一步（不再裸 traceback）
    repo_root = REPO_ROOT
    iso = _TMP / "status-iso"
    shutil.rmtree(iso, ignore_errors=True)
    mkc = iso / "market"
    (mkc / "web").mkdir(parents=True)
    shutil.copy2(repo_root / "market.config.example.json",
                 mkc / "market.config.example.json")
    env2 = dict(os.environ)
    env2.update({"WBM_MARKET_ROOT": str(mkc), "WBM_STATE_HOME": str(iso / "state"),
                 "WBM_HOME": str(iso / "wb")})
    env2.pop("PYTHONPATH", None)
    r = subprocess.run(
        [sys.executable, str(repo_root / "launcher.py"), "--status", "--json"],
        env=env2, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=120, cwd=str(repo_root))
    ck("★ --status 配置缺失 → 退出码 1 且 JSON 报错（人话）",
       r.returncode == 1 and json.loads(r.stdout or "{}").get("ok") is False
       and "market.config.json" in (json.loads(r.stdout or "{}").get("error") or ""))
    ck("★ --status 配置缺失 → stderr 无 Python traceback",
       "Traceback" not in (r.stderr or ""))


def round24():
    """v2.25：开源入门体验（第 39 节）。

    文档轮的盯防线（评审 P1「重构开源项目的入门体验」）：
    1. 演示截图真实存在且由可再生脚本采集（不是伪造图片、不是手工贴图）；
    2. README 快速上手 / 平台支持矩阵 / 参与入口在发货内容里；
    3. FAQ 有首次启动 / 配置初始化专节。
    """
    section("39. v2.25：开源入门体验（Quick Start / 平台矩阵 / 截图）")
    repo = REPO_ROOT
    shots = repo / "docs" / "screenshots"
    names = ("home-local.png", "home-curated.png", "detail-four-questions.png")
    ck("★ 演示截图随仓库分发且非空（真实界面采集）",
       all((shots / n).is_file() and (shots / n).stat().st_size > 20000
           for n in names),
       " ".join(f"{n}={((shots / n).stat().st_size // 1024) if (shots / n).is_file() else 0}KB"
                for n in names))
    ck("★ 截图采集脚本可再生（合成数据 + 隔离区纪律）",
       (repo / "scripts" / "capture-screenshots.py").is_file()
       and "WBM_MARKET_ROOT" in (repo / "scripts" / "capture-screenshots.py")
       .read_text(encoding="utf-8"))
    rd = (repo / "README.md").read_text(encoding="utf-8")
    ck("★ README 快速上手 / 平台支持矩阵 / 参与入口在发货内容里",
       "快速上手" in rd and "平台支持矩阵" in rd and "CONTRIBUTING.md" in rd
       and "docs/screenshots/home-local.png" in rd)
    ck("★ README 平台矩阵区分「CI 覆盖 ≠ 宿主集成已验证」",
       "WorkBuddy 宿主集成" in rd)
    faq = (repo / "docs" / "FAQ.md").read_text(encoding="utf-8")
    ck("★ FAQ 有首次启动 / 配置初始化专节（缺失/已有/损坏/回车/非交互）",
       "首次启动 / 配置相关" in faq and "原样保留" in faq and "只浏览" in faq)


def round25():
    """v2.27：更新后 latestSha 回写 / 漂移检查前缀口径（第 40 节）。

    用户实测：ghpm 更新报告「已是最新」，但「可更新 1」仍挂着 ——
    根因是 latestSha 是每日 CI 快照，上游在快照后推进、ghpm 已追平
    实时上游时误报。盯防四件事：
    1. ghpm 输出里的实测 sha（[跳过] / [更新] / 已是最新行）被回写进
       注册表缓存 latestSha；
    2. 无关仓库 / 无 sha 行 → 不动缓存（解析不出绝不猜）；
    3. 回写后 /api/registry 数据源（get_registry）立即可见新值；
    4. _registry_drift 用前 7 位比对 —— 7 位短 sha 回写不产生假 409。
    """
    section("40. v2.27：更新后 latestSha 回写 / 漂移前缀口径")
    import market_server as srv3

    base_cache = {"schema": core.REGISTRY_SCHEMA, "updatedAt": "2026-10-10",
                  "fetchedAt": "2026-10-10T00:00:00Z",
                  "fetchedAtEpoch": time.time() + 3600,   # 未来时间 = 缓存新鲜，不触网
                  "plugins": [{
                      "repo": "anthropics/skills", "displayName": "Skills",
                      "category": "测试", "trust": "official",
                      "sourceCommit": "dbd4588" + "a" * 33,
                      "latestSha": "aaa0000"}]}
    core.save_registry_cache(base_cache)

    # --- 40A. [跳过] 行的实测 sha 回写
    lines = ["$ update anthropics/skills",
             "  [跳过]  anthropics/skills      dbd4588 已是最新"]
    ck("★ ghpm「跳过/已是最新」行 → 实测 sha 回写缓存",
       srv3._sync_registry_sha_from_job("anthropics/skills", lines) is True
       and core.load_registry_cache()["plugins"][0]["latestSha"] == "dbd4588")

    # --- 40B. get_registry（/api/registry 数据源）立即可见
    reg = core.get_registry()
    e = next(x for x in reg["plugins"] if x["repo"] == "anthropics/skills")
    ck("★ 回写后 get_registry 立即可见（内存缓存已失效）",
       str(e.get("latestSha", "")).lower() == "dbd4588")

    # --- 40C. 无关仓库 / 无 sha 行 → 不动
    ck("★ 无关仓库的输出 → 不回写",
       srv3._sync_registry_sha_from_job("other/repo", lines) is False
       and core.load_registry_cache()["plugins"][0]["latestSha"] == "dbd4588")
    ck("★ 没有 sha 的行 → 解析不出，绝不猜",
       srv3._sync_registry_sha_from_job("anthropics/skills",
                                        ["$ update anthropics/skills"]) is False)

    # --- 40D. 漂移检查前缀口径：7 位回写不产生假 409
    ck("★ _registry_drift：sourceCommit 与 latestSha 前 7 位一致 → 无漂移",
       srv3._registry_drift("anthropics/skills") is None)
    cache2 = core.load_registry_cache()
    cache2["plugins"][0]["latestSha"] = "fff1234"
    core.save_registry_cache(cache2)
    d = srv3._registry_drift("anthropics/skills")
    ck("★ _registry_drift：真前移 → 照常报漂移",
       d is not None and d["latestSha"][:7] == "fff1234")

    # --- 收尾：清掉缓存，别污染其他检查
    core.REGISTRY_PATH.unlink(missing_ok=True)


def round26():
    """v2.28：审计修复轮（CLI 口径诚实化 / zip 市场构建清单）。

    使用与宣发审计的 4 个用户可见问题的盯防线：
    1. CLI list/search 头部改为「匹配 X / 共 Y 条」—— 命中数与总数同框，
       「search 4 条」不再被误读成数据源只有 4 条；
    2. 注册表自带 displayNameEn 时，CLI 顺手输出一行原文名（渐进 i18n）；
    3. zip 市场构建产物自带 included / excluded 清单 —— 用户能对上
       「注册表收录 N 条，zip 里怎么只有 M 个」；
    4. 单插件体积闸门：超限剔除并如实记录 reason，拒绝发布空市场，
       绝不静默裁剪内容。
    """
    section("41. v2.28：CLI 口径诚实化 / zip 市场构建清单")
    import contextlib as _ctx41
    import io as _io41
    import tarfile as _tf41
    import zipfile as _zf41
    import importlib.util as _ilu41
    import workbuddy_market.cli as wcli41

    # --- 41A/41B. CLI 头部口径 + 英文名行（缓存新鲜，不触网）
    core.save_registry_cache({
        "schema": core.REGISTRY_SCHEMA, "updatedAt": "2026-10-12",
        "fetchedAt": "2026-10-12T00:00:00Z",
        "fetchedAtEpoch": time.time() + 3600,
        "plugins": [
            {"repo": "owner/cn", "displayName": "中文技能",
             "displayNameEn": "Chinese Skill", "description": "一个示例",
             "category": "测试", "trust": "reviewed", "sourceCommit": "a" * 40},
            {"repo": "owner/plain", "displayName": "Plain",
             "description": "另一个示例", "category": "测试",
             "trust": "reviewed", "sourceCommit": "b" * 40}]})
    buf = _io41.StringIO()
    with _ctx41.redirect_stdout(buf):
        rc = wcli41._registry_list_main(["list"])
    out = buf.getvalue()
    ck("★ CLI list 头部：匹配数与总数同框",
       rc == 0 and "社区目录匹配 2 / 共 2 条" in out, out[:80])
    ck("★ 注册表带英文名 → 输出原文名行", "(Chinese Skill)" in out)
    buf2 = _io41.StringIO()
    with _ctx41.redirect_stdout(buf2):
        rc2 = wcli41._registry_list_main(["search", "chinese"])
    out2 = buf2.getvalue()
    ck("★ CLI search 头部：命中 1 / 共 2（英文关键词命中 displayNameEn）",
       rc2 == 0 and "社区目录匹配 1 / 共 2 条" in out2, out2[:80])
    core.REGISTRY_PATH.unlink(missing_ok=True)

    # --- 41C/41D. zip 市场构建：included/excluded 清单 + 体积闸门
    spec41 = _ilu41.spec_from_file_location(
        "build_marketplace_zip",
        str(REPO_ROOT / "scripts" /
            "build_marketplace_zip.py"))
    bz41 = _ilu41.module_from_spec(spec41)
    spec41.loader.exec_module(bz41)

    lab41 = _TMP / "r26-lab"
    shutil.rmtree(lab41, ignore_errors=True)
    lab41.mkdir(parents=True)

    tar_path = lab41 / "ok.tar.gz"
    with _tf41.open(tar_path, "w:gz") as tf41:
        data41 = "---\nname: alpha\n---\n"
        ti41 = _tf41.TarInfo("ok_repo-abc/skills/alpha/SKILL.md")
        ti41.size = len(data41.encode("utf-8"))
        tf41.addfile(ti41, _io41.BytesIO(data41.encode("utf-8")))
    ok_tar41 = tar_path.read_bytes()

    real_fetch41 = bz41._fetch_with_retry

    def fake_fetch41(url: str) -> bytes:
        if url.endswith("/" + "a" * 40 + ".tar.gz"):
            return ok_tar41
        raise RuntimeError("网络炸了")

    bz41._fetch_with_retry = fake_fetch41
    try:
        reg41 = lab41 / "reg.json"
        reg41.write_text(json.dumps({"schema": 1, "plugins": [
            {"repo": "owner/ok", "sourceCommit": "a" * 40,
             "displayName": "OK", "description": "d1"},
            {"repo": "owner/bad", "sourceCommit": "b" * 40,
             "displayName": "Bad", "description": "d2"}]},
            ensure_ascii=False), encoding="utf-8")
        out41 = lab41 / "mkt.zip"
        summary = bz41.build_marketplace(reg41, out41)
        ck("★ zip 构建：单条失败不拖垮整批，excluded 结构化（repo+reason）",
           summary["built"] == 1 and summary["failed"] == 1
           and summary["excluded"][0]["repo"] == "owner/bad"
           and "网络炸了" in summary["excluded"][0]["reason"],
           json.dumps(summary.get("excluded"), ensure_ascii=False)[:100])
        with _zf41.ZipFile(out41) as zf41:
            mp41 = json.loads(zf41.read(".codebuddy-plugin/marketplace.json"))
        ck("★ marketplace.json 自带 included/excluded",
           mp41["included"] == [mp41["plugins"][0]["name"]]
           and mp41["excluded"][0]["repo"] == "owner/bad")
        man41 = json.loads((out41.parent / "workbuddy-marketplace.manifest.json")
                           .read_text(encoding="utf-8"))
        ck("★ manifest 与 marketplace.json 清单一致",
           man41["included"] == mp41["included"] and len(man41["excluded"]) == 1)

        # --- 41D. 体积闸门：超限剔除 → 拒发空市场并说明原因
        reg42 = lab41 / "reg2.json"
        reg42.write_text(json.dumps({"schema": 1, "plugins": [
            {"repo": "owner/ok", "sourceCommit": "a" * 40,
             "displayName": "OK", "description": "d1"}]},
            ensure_ascii=False), encoding="utf-8")
        gated = None
        try:
            bz41.build_marketplace(reg42, lab41 / "mkt2.zip",
                                   max_plugin_bytes=1)
        except SystemExit as exc41:
            gated = str(exc41)
        ck("★ 体积闸门：超限剔除 → 拒发空市场并如实说明原因",
           gated is not None and "拒绝发布空市场" in gated and "体积" in gated,
           (gated or "")[:100])
        shutil.rmtree(lab41, ignore_errors=True)
    finally:
        bz41._fetch_with_retry = real_fetch41


