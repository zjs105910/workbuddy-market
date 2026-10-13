# -*- coding: utf-8 -*-
"""第 19 节（第四轮评审）：事务边界、本地 API 鉴权、任务生命周期、扫描复用。"""
from __future__ import annotations

import http.client
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from . import REPO_ROOT, _restore_config, ck, core, section, sk, wm, write_fake_skill


def round4():
    """第四轮评审：事务边界、本地 API 鉴权、任务生命周期、扫描复用。"""
    section("19. 第四轮：故意构造异常状态也必须是安全的")

    # --- 19A. launcher：前置失败时禁止 register
    import launcher  # noqa: E402

    ck("★ 打包失败 → 不注册", launcher.should_register(False, True)[0] is False)
    ck("★ 自检失败 → 不注册", launcher.should_register(True, False)[0] is False)
    ck("★ 都成功 → 才注册", launcher.should_register(True, True)[0] is True)
    ck("★ --force-register 才允许强行注册",
       launcher.should_register(False, False, True)[0] is True)
    ck("跳过原因可读", "打包" in launcher.should_register(False, True)[1],
       launcher.should_register(False, True)[1])

    # 端到端：真跑一遍 launcher 的编排，确认坏配置下不会调用 register
    good_cfg = core.CONFIG_PATH.read_text(encoding="utf-8")
    core.CONFIG_PATH.write_text('{"marketId": "x",,}', encoding="utf-8")
    import types

    stub = types.ModuleType("market_server")
    stub.serve = lambda **k: 0
    sys.modules["market_server"] = stub
    registered = []
    real_register = core.register
    core.register = lambda *a, **k: (registered.append(1), True)[1]
    try:
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            launcher.main(["--no-open"])
        out = buf.getvalue()
    finally:
        core.register = real_register
        _restore_config(good_cfg)
        sys.modules.pop("market_server", None)
    ck("★ ★ 坏配置下 launcher 真的没有调用 register", not registered, str(registered))
    ck("★ 并且如实告诉用户跳过了注册", "已跳过" in out, out.strip().splitlines()[-1][:60])

    # --- 19B. 事务日志：全新安装时所有权写失败
    core.sync_packaging(quiet=True)
    for s in ("alpha", "beta"):
        shutil.rmtree(core.SKILLS_DIR / s, ignore_errors=True)
    shutil.rmtree(core.TX_DIR, ignore_errors=True)
    own_before = dict(core.load_ownership()["skills"])

    real_save_own = wm.ownership.save_ownership
    wm.ownership.save_ownership = lambda _o: (_ for _ in ()).throw(OSError("模拟 .ownership.json 写失败"))
    try:
        r_tx = core.install_local_plugin("bundle-one", "missing")
    finally:
        wm.ownership.save_ownership = real_save_own

    ck("★ 文件确实装上了", (core.SKILLS_DIR / "alpha" / "SKILL.md").is_file()
       and (core.SKILLS_DIR / "beta" / "SKILL.md").is_file())
    ck("★ 安装整体仍报成功（不谎称什么都没发生）", r_tx["ok"] is True, str(r_tx["ok"]))
    ck("★ 并且给出了明确的告警", any("所有权" in w for w in r_tx["warnings"]),
       str(r_tx["warnings"])[:70])
    ck("★ ★ 留下了事务日志（v2.2 什么都没留）",
       any(True for _ in core.TX_DIR.glob("*.json")))
    tx = core.tx_list()[0]
    ck("★ 日志里记着待补账的 skill（含 expected hash）",
       sorted(e["skill"] for e in tx["pendingOwnership"]) == ["alpha", "beta"]
       and all(e.get("hash") and e.get("state") == "committed"
               for e in tx["pendingOwnership"]),
       str([(e["skill"], e.get("state")) for e in tx["pendingOwnership"]]))
    ck("★ 此刻所有权还是安装前那一份（没被这次安装更新）",
       json.dumps(core.load_ownership()["skills"], sort_keys=True)
       == json.dumps(own_before, sort_keys=True))
    ok_dc, errs_dc, _w = core.deep_check()
    ck("★ 深度自检能报出这个未完成事务",
       not ok_dc and any("未完成的事务" in e for e in errs_dc), "; ".join(errs_dc[:1])[:80])

    # 恢复：下一次同步就该把账补上
    rec = core.recover_transactions(quiet=True)
    ck("★ ★ 恢复流程补记了所有权", sorted(rec["recovered"]) == ["alpha", "beta"],
       str(rec["recovered"]))
    ck("★ 补记后日志已清账", not list(core.TX_DIR.glob("*.json")))
    ck("★ ★ 恢复后 alpha 不再是 foreign",
       core.classify_skill("bundle-one", "alpha", core.load_config(),
                           purpose="uninstall")["kind"] == "safe")
    ck("★ 自检重新变干净", core.deep_check()[0])
    ck("★ 补记后的记录与磁盘内容对得上",
       core.load_ownership()["skills"]["alpha"]["hash"]
       == core.tree_hash(core.SKILLS_DIR / "alpha"))

    # --- 19C. 事务日志：更新安装时所有权写失败
    (core.SKILLS_DIR / "alpha" / "notes.md").write_text("# user edited\n", encoding="utf-8")
    core.sync_packaging(quiet=True)
    old_hash = core.load_ownership()["skills"]["alpha"]["hash"]
    wm.ownership.save_ownership = lambda _o: (_ for _ in ()).throw(OSError("模拟写失败"))
    try:
        core.install_local_plugin("bundle-one", "update")
    finally:
        wm.ownership.save_ownership = real_save_own
    ck("★ 更新后本地内容已等于市场版本",
       core.tree_hash(core.SKILLS_DIR / "alpha")
       == core.tree_hash(core.PLUGINS_DIR / "bundle-one" / "skills" / "alpha"))
    ck("★ 所有权仍停在旧 hash（这就是要补的账）",
       core.load_ownership()["skills"]["alpha"]["hash"] == old_hash)
    rec2 = core.recover_transactions(quiet=True)
    ck("★ 恢复后所有权 hash 跟上了新内容",
       core.load_ownership()["skills"]["alpha"]["hash"] != old_hash,
       str(rec2["recovered"]))
    ck("★ 恢复后判为 safe",
       core.classify_skill("bundle-one", "alpha", core.load_config(),
                           purpose="uninstall")["kind"] == "safe")

    # --- 19D. 一次没走完的事务被交还给恢复流程（不是留在进程里）
    core.TX_DIR.mkdir(parents=True, exist_ok=True)
    stale = core.tx_begin("install", "bundle-one", ["alpha"], version="1.0.0")
    core.tx_note_staged(stale, "alpha", {"hash": "x" * 64})
    core.tx_release(stale)                  # 操作结束、账没清 → 交给恢复流程
    own_snapshot = json.dumps(core.load_ownership(), sort_keys=True)
    rec3 = core.recover_transactions(quiet=True)
    ck("★ 未确认交付的条目不会被认领（内容对不上）",
       rec3["recovered"] == [] and not list(core.TX_DIR.glob("*.json")),
       str(rec3))
    ck("★ 也没动所有权记录",
       json.dumps(core.load_ownership(), sort_keys=True) == own_snapshot)

    # --- 19E. 配置数值校验
    cfg_now = core.CONFIG_PATH.read_text(encoding="utf-8")

    def try_bad(mutate, label):
        c = json.loads(cfg_now)
        mutate(c)
        core.CONFIG_PATH.write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
        try:
            core.load_config()
            ck(f"★ 拒绝：{label}", False, "居然通过了")
        except core.ConfigError:
            ck(f"★ 拒绝：{label}", True)
        finally:
            _restore_config(cfg_now)

    try_bad(lambda c: c.update({"trash": {"maxSizeBytes": 1.9}}), "maxSizeBytes 是小数 1.9")
    try_bad(lambda c: c.update({"trash": {"maxSizeBytes": float("nan")}}), "maxSizeBytes = NaN")
    try_bad(lambda c: c.update({"trash": {"maxAgeDays": float("inf")}}), "maxAgeDays = Infinity")
    try_bad(lambda c: c.update({"packaging": {"hashChunkBytes": 1.5}}), "hashChunkBytes 是小数")

    # --- 19F. 注册：乐观合并，别覆盖 WorkBuddy 中途写入的内容
    # v2.17 起 register 整段迁 WorkBuddy Adapter —— patch 落点随迁
    # workbuddy_market.adapters.workbuddy（R4 ownership/trash 同一先例）。
    core.KNOWN_PATH.parent.mkdir(parents=True, exist_ok=True)
    core.KNOWN_PATH.write_text(json.dumps(
        {"other-market": {"manifestName": "other-market", "type": "zip"}},
        ensure_ascii=False), encoding="utf-8")
    import workbuddy_market.adapters.workbuddy as wb_adapter  # noqa: E402
    real_or_die = wb_adapter.read_known_or_die
    reads = {"n": 0}

    def meddling_read():
        data = real_or_die()
        reads["n"] += 1
        if reads["n"] == 1:
            # 模拟 WorkBuddy 恰好在我们「读完、还没写」的窗口里改了同一个文件
            cur = json.loads(core.KNOWN_PATH.read_text(encoding="utf-8"))
            cur["workbuddy-added"] = {"manifestName": "workbuddy-added", "type": "zip"}
            core.KNOWN_PATH.write_text(json.dumps(cur, ensure_ascii=False), encoding="utf-8")
        return data

    wb_adapter.read_known_or_die = meddling_read
    try:
        changed = core.register()
    finally:
        wb_adapter.read_known_or_die = real_or_die
    known = json.loads(core.KNOWN_PATH.read_text(encoding="utf-8"))
    ck("★ 注册成功", changed is True)
    ck("★ ★ 中途被写进来的 workbuddy-added 没被覆盖掉", "workbuddy-added" in known,
       str(sorted(known)))
    ck("★ 原有的 other-market 也还在", "other-market" in known)
    ck("★ 本市场也注册上了", "test-market" in known)
    ck("★ 确实重试了（读了两轮以上）", reads["n"] >= 3, f"{reads['n']} 次读")

    # --- 19G. durable 原子写
    probe_file = core.MARKET_ROOT / "durable-probe.txt"
    core.atomic_write_text(probe_file, "hello\n", durable=True)
    ck("★ durable 原子写内容正确", probe_file.read_text(encoding="utf-8") == "hello\n")
    ck("★ 不留下 .tmp- 残渣", not list(core.MARKET_ROOT.glob(".tmp-*")))
    ck("★ Windows 上没有不需要的目录 fsync",
       (os.name != "nt") or (core._fsync_dir(core.MARKET_ROOT) is None))
    probe_file.unlink()

    # --- 19H. 批量指纹扫描
    cache = core.SkillScanCache(["alpha", "beta", "gamma"])
    ck("★ 批量指纹 == 单独扫出来的指纹",
       cache.fingerprint("beta") == core.quick_fingerprint(core.SKILLS_DIR / "beta"))
    cache.fingerprint("alpha")
    cache.fingerprint("gamma")
    ck("★ 三次取指纹只扫了一遍", cache.scans == 1, f"{cache.scans} 次")
    ck("★ 没被声明的 skill 不会被扫到（桶是空的）",
       cache.fingerprint("not-declared")["files"] == 0)

    # --- 19I. build_state 的扫描次数
    cfg_before_19i = core.CONFIG_PATH.read_text(encoding="utf-8")
    core.prune_trash(force=True, quiet=True)
    cfg_six = json.loads(cfg_before_19i)
    for n in ("gen1", "gen2", "gen3"):
        write_fake_skill(core.SKILLS_DIR, n, "1.0.0", "gen", {})
    cfg_six["localPlugins"].append({"name": "gen-bundle", "version": "1.0.0",
                                    "description": "d", "skills": ["gen1", "gen2", "gen3"]})
    cfg_six["packaging"] = {"excludeNames": ["__pycache__"], "excludeGlobs": ["*.bak"],
                            "verify": "fast"}
    core.CONFIG_PATH.write_text(json.dumps(cfg_six, ensure_ascii=False, indent=2),
                                encoding="utf-8")
    core.sync_packaging(quiet=True)
    core.install_local_plugin("gen-bundle", "missing")

    declared_names = sorted(s for p in core.load_config()["localPlugins"]
                            for s in p["skills"])
    walked = []
    # R3 起 _walk_tree 定义在 workbuddy_market.scanner：SkillScanCache →
    # _scan_many → _walk_tree 全走 scanner 命名空间，patch core._walk_tree
    # 不再生效（方案 §3.2 的注入点迁移规则），这里跟着改。
    real_walk = wm.scanner._walk_tree
    real_scan = core._scan          # 19J 还要用

    def counting_walk(root, excluded, files, links, errors):
        walked.append(Path(root).name)
        return real_walk(root, excluded, files, links, errors)

    # gamma 在更早的用例里是手工塞进 ownership 的（没有 fingerprint 字段）。
    # 这种「旧记录」会绕过批量缓存、退回完整哈希 —— 先验证这一点，再补成正常记录。
    ck("（前提）gamma 的旧记录确实没有指纹",
       not isinstance(core.load_ownership()["skills"]["gamma"].get("fingerprint"), dict))

    core.record_owner("bundle-two", ["gamma"], "2.0.0")   # 补成正常记录
    wm.scanner._walk_tree = counting_walk
    try:
        st6 = core.build_state()
    finally:
        wm.scanner._walk_tree = real_walk
    # 额外登记几个「无关 skill」，确认它们不会被顺带扫到
    for extra in ("unrelated-a", "unrelated-b"):
        write_fake_skill(core.SKILLS_DIR, extra, "1.0.0", "噪音", {})
    wm.scanner._walk_tree = counting_walk
    walked.clear()
    try:
        core.build_state()
    finally:
        wm.scanner._walk_tree = real_walk
    ck(f"★ ★ 只走声明的 {len(declared_names)} 个 skill，不碰无关目录",
       sorted(walked) == declared_names, f"走了 {sorted(walked)}")
    ck("★ ★ 不再整树扫 skills 根", "skills" not in walked, str(sorted(walked)[:4]))
    ck("批量路径下状态依然正确",
       all(len(p["skillDetail"]) == len(p["skills"]) for p in st6["plugins"]))

    _restore_config(cfg_before_19i)
    core.sync_packaging(quiet=True)

    # --- 19J. 一次 update 的磁盘 I/O + 暂存索引复用
    core.install_local_plugin("bundle-one", "force")
    io_stats = {"scan": 0, "hash": 0, "fp": 0}
    real_th, real_fp = core.tree_hash, core.quick_fingerprint

    def c_scan2(root, excluded=None, **kw):
        io_stats["scan"] += 1
        return real_scan(root, excluded, **kw)

    def c_th2(*a, **k):
        io_stats["hash"] += 1
        return real_th(*a, **k)

    def c_fp2(*a, **k):
        io_stats["fp"] += 1
        return real_fp(*a, **k)

    (core.SKILLS_DIR / "alpha" / "notes.md").write_text("# changed again\n", encoding="utf-8")
    core._scan, core.tree_hash, core.quick_fingerprint = c_scan2, c_th2, c_fp2
    try:
        r_io = core.install_local_plugin("bundle-one", "update")
    finally:
        core._scan, core.tree_hash, core.quick_fingerprint = real_scan, real_th, real_fp
    ck("update 确实覆盖了 alpha", "alpha" in r_io["updated"], str(r_io["updated"]))
    ck("★ ★ 一次 update 不再额外算指纹（v2.2 会多一次 quick_fingerprint）",
       io_stats["fp"] == 0, f"scan={io_stats['scan']} hash={io_stats['hash']} fp={io_stats['fp']}")
    ck("★ 扫描/哈希次数都压在合理区间",
       io_stats["scan"] <= 6 and io_stats["hash"] <= 2,
       f"scan={io_stats['scan']} hash={io_stats['hash']} fp={io_stats['fp']}")

    # 直接证明复用：带 snapshots 的 record_owner 完全不碰磁盘
    io_stats.update(scan=0, hash=0, fp=0)
    core._scan, core.tree_hash, core.quick_fingerprint = c_scan2, c_th2, c_fp2
    try:
        core.record_owner("bundle-one", ["alpha"], "1.0.0",
                          snapshots={"alpha": {"hash": "deadbeef",
                                               "fingerprint": core.quick_fingerprint(
                                                   core.SKILLS_DIR / "alpha")}})
    finally:
        core._scan, core.tree_hash, core.quick_fingerprint = real_scan, real_th, real_fp
    # 上面的 fingerprint 是显式算的，减掉它自己
    ck("★ ★ 带 snapshots 的 record_owner 不再重扫新版本（复用暂存索引）",
       io_stats["hash"] == 0 and io_stats["scan"] == 1,
       f"scan={io_stats['scan']} hash={io_stats['hash']}（那 1 次是构造 snapshots 用的）")
    core.install_local_plugin("bundle-one", "force")

    # --- 19K. 本机 API 鉴权（真起一个服务做端到端）
    import market_server as srv  # noqa: E402

    # 隔离环境里的假市场没有 web/ 目录，把真实前端拷过来 ——
    # 这样测的是真正会发货的那个 index.html（含 token 注入点）。
    # 缺文件时**明确 SKIP**，而不是让整条测试挂死。
    core.WEB_DIR.mkdir(parents=True, exist_ok=True)
    src_web = REPO_ROOT / "web"
    src_html = src_web / "index.html"
    ui_ok = src_html.is_file()
    if ui_ok:
        shutil.copy2(src_html, core.WEB_DIR / "index.html")
        # v2.17：Web 拆文件后页面引用 /static/style.css；
        # v2.22：前端再拆 ES Modules，/static/app/*.js 也要进隔离环境
        #（server 白名单按相对路径精确命中）。
        src_css = src_web / "style.css"
        if src_css.is_file():
            shutil.copy2(src_css, core.WEB_DIR / "style.css")
        src_app = src_web / "app"
        if src_app.is_dir():
            (core.WEB_DIR / "app").mkdir(exist_ok=True)
            for js in sorted(src_app.glob("*.js")):
                shutil.copy2(js, core.WEB_DIR / "app" / js.name)
    else:
        sk("前端页面相关的断言（token 注入）",
           f"缺少 {src_html}；API 层鉴权仍会照常测试")

    TOK = "selftest-token-abc123"
    httpd = srv.make_server(0, token=TOK)
    PORT = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def hit(path, body=None, headers=None, method=None):
        c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=10)
        m = method or ("POST" if body is not None else "GET")
        data = None
        if body is not None:
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
        c.request(m, path, body=data, headers=headers or {})
        r = c.getresponse()
        raw = r.read()
        c.close()
        try:
            return r.status, json.loads(raw)
        except Exception:
            return r.status, raw.decode("utf-8", "replace")

    AUTH = {"X-Local-Market-Token": TOK, "Content-Type": "application/json"}
    try:
        st_home, html = hit("/")
        if ui_ok:
            ck("首页可访问", st_home == 200, str(st_home))
            ck("★ ★ 页面里注入的是真口令，不是占位符",
               TOK in html and "__MARKET_TOKEN__" not in html)
        else:
            sk("首页可访问 / 口令注入")

        st1, _ = hit("/api/state")
        ck("★ ★ 没口令的 GET /api/state → 403", st1 == 403, str(st1))
        st2, _ = hit("/api/state", headers={"X-Local-Market-Token": "wrong"})
        ck("★ ★ 错误口令 → 403", st2 == 403, str(st2))
        st3, js3 = hit("/api/state", headers=AUTH)
        ck("★ 正确口令 → 200", st3 == 200 and js3.get("marketId") == "test-market", str(st3))

        for p, b, label in [
            ("/api/install", {"id": "bundle-one", "mode": "missing"}, "install"),
            ("/api/register", {}, "register"),
            ("/api/trash/purge", {}, "purge"),
        ]:
            stx, _ = hit(p, b, {"X-Local-Market-Token": TOK,
                                "Content-Type": "application/json",
                                "Origin": "http://evil.example"})
            ck(f"★ ★ 跨源 {label} → 403", stx == 403, str(stx))
            sty, _ = hit(p, b, dict(AUTH))
            ck(f"同源 {label} 正常放行", sty == 200, str(sty))

        st_o, _ = hit("/api/install", {"id": "bundle-one"},
                      {"X-Local-Market-Token": TOK, "Content-Type": "application/json",
                       "Origin": f"http://127.0.0.1:{PORT}"})
        ck("★ 同端口 Origin 放行", st_o == 200, str(st_o))

        # body 上限与坏 JSON
        # 超限请求体的合法结局有两种：服务端读完头部就回 413 并关连接，
        # 而客户端可能还在写 body——Linux/Darwin 的 TCP 栈对「带未读数据
        # 关闭」直接 RST，写一半就 BrokenPipe（Windows 上是读响应时
        # 10053）。两种结局都证明服务端没有接受超限 body，断言要同时认，
        # 否则同一用例在 Windows 上靠时序侥幸过、在 POSIX 上必挂。
        try:
            st_big, js_big = hit("/api/install", b"x" * (srv.MAX_BODY + 1024), AUTH)
        except (BrokenPipeError, ConnectionError, http.client.RemoteDisconnected) as exc:
            st_big, js_big = "RESET", f"{type(exc).__name__}: {exc}"
        ck("★ ★ 超限请求体 → 413", st_big == 413 or st_big == "RESET",
           f"{st_big} {str(js_big)[:50]}")
        st_bad, js_bad = hit("/api/install", b"{not json", AUTH)
        ck("★ ★ 坏 JSON → 400 且说明原因",
           st_bad == 400 and "JSON" in str(js_bad), f"{st_bad} {str(js_bad)[:60]}")

        # open/path 白名单
        opened = []
        real_popen = srv.subprocess.Popen
        srv.subprocess.Popen = lambda args, *a, **k: opened.append(list(args))
        try:
            outside_dir = core.MARKET_ROOT.parent / "OUTSIDE-OPEN"
            outside_dir.mkdir(parents=True, exist_ok=True)
            st_p1, _ = hit("/api/open/path", {"path": str(outside_dir)}, AUTH)
            ck("★ ★ 市场之外的路径被拒", st_p1 == 400 and not opened, f"{st_p1} opened={opened}")
            st_p2, _ = hit("/api/open/path", {"path": "C:\\Windows"}, AUTH)
            ck("★ ★ C:\\Windows 被拒", st_p2 == 400 and not opened, f"{st_p2} opened={opened}")
            st_p3, _ = hit("/api/open/path", {"target": "nope"}, AUTH)
            ck("未知 target 被拒", st_p3 == 400, str(st_p3))
            st_p4, js_p4 = hit("/api/open/path", {"target": "plugin", "id": "bundle-one"}, AUTH)
            want = core.PLUGINS_DIR / "bundle-one"
            got = Path(opened[-1][1]).resolve() if opened else None
            ck("★ target=plugin 打开市场内的插件目录",
               st_p4 == 200 and got == want.resolve(), f"{st_p4} {got}")
            st_p5, _ = hit("/api/open/path", {"target": "root"}, AUTH)
            ck("★ target=root 打开市场根", st_p5 == 200, str(st_p5))
            st_p6, _ = hit("/api/open/path", {"target": "plugin", "id": "../escape"}, AUTH)
            ck("★ 越界插件 id 被拒", st_p6 == 400, str(st_p6))
            shutil.rmtree(outside_dir, ignore_errors=True)
        finally:
            srv.subprocess.Popen = real_popen

        # --- 19L. 任务生命周期
        with srv._jobs_lock:
            srv._jobs.clear()
        run_ids = [srv._new_job(f"run{i}") for i in range(3)]
        for i in range(srv.MAX_JOBS + 15):
            jid = srv._new_job(f"done{i}")
            srv._job_finish(jid, True)
        with srv._jobs_lock:
            alive = set(srv._jobs)
        ck("★ 任务表不超过上限", len(alive) <= srv.MAX_JOBS, str(len(alive)))
        ck("★ ★ 运行中的任务一个都没被淘汰", all(r in alive for r in run_ids))

        with srv._jobs_lock:
            for j in srv._jobs.values():
                if j["status"] == "done":
                    j["finishedAt"] = time.time() - srv.JOB_TTL - 5
        dead = srv.reap_jobs()
        with srv._jobs_lock:
            alive2 = set(srv._jobs)
        ck("★ ★ 过期任务被回收", dead >= 1 and not (alive2 - set(run_ids)),
           f"回收 {dead} 个，剩 {len(alive2)}")

        # 取消：真起一个长睡的进程
        jid_cancel = srv._new_job("cancel-test")
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        with srv._jobs_lock:
            srv._jobs[jid_cancel]["proc"] = proc
        ck("取消运行中的任务返回 True", srv.cancel_job(jid_cancel) is True)
        t_end = time.time() + 15
        while proc.poll() is None and time.time() < t_end:
            time.sleep(0.1)
        ck("★ ★ 取消真的把子进程杀掉了", proc.poll() is not None, str(proc.poll()))
        ck("取消不存在的任务返回 False", srv.cancel_job("no-such-job") is False)

        # --- 19M. /api/state 短 TTL 缓存
        calls = {"n": 0}
        real_build = core.build_state

        def counting_build(*a, **k):
            calls["n"] += 1
            return real_build(*a, **k)

        core.build_state = counting_build
        try:
            srv.invalidate_state()
            srv.get_state()
            srv.get_state()
            srv.get_state()
        finally:
            core.build_state = real_build
        ck("★ ★ 1 秒内的重复 /api/state 复用缓存", calls["n"] == 1, f"重建 {calls['n']} 次")

        srv.invalidate_state()
        core.build_state = counting_build
        try:
            srv.get_state()
            srv.invalidate_state()      # 有写操作 → 必须失效
            srv.get_state()
        finally:
            core.build_state = real_build
        ck("★ 写操作之后缓存立即失效", calls["n"] == 3, f"累计 {calls['n']} 次")

        # 端到端确认缓存不会让界面看到过期数据
        st_c1, js_c1 = hit("/api/state", headers=AUTH)
        ck("/api/state 端到端可用", st_c1 == 200 and "stats" in js_c1, str(st_c1))
    finally:
        httpd.shutdown()
        httpd.server_close()


