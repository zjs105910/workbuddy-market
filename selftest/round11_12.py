# -*- coding: utf-8 -*-
"""第 26-27 节（v2.10 / v2.11）：GitHub 动态目录 catalog / 社区注册表 registry。"""
from __future__ import annotations

import http.client
import json
import os
import threading
import time
from . import REPO_ROOT, _TMP, ck, core, section


def round11():
    """v2.10：GitHub 动态目录。

    三条盯防线：
    1. catalog 是**不可信状态文件**：形状不对当不存在，绝不让坏 JSON 炸掉状态页；
    2. 「失败不算刷新过」：整轮全败时 refreshedAt 必须沿用旧值，
       否则自动循环会误以为数据新鲜、傻等 24 小时；
    3. 服务端三个新接口全走 _guard（约定 15），网络接缝只有 _gh_request
       一处 —— 全部用假接缝离线测，自检零网络依赖。
    """
    section("26. v2.10：GitHub 动态目录（catalog 模块 + 全网搜索 + 服务接口）")

    import workbuddy_market.catalog as cat

    # --- 26A. 符号同一性（re-export 必须就是包里的同一对象）
    ck("★ catalog 符号同一性",
       core.refresh_catalog is cat.refresh_catalog
       and core.search_repos is cat.search_repos
       and core.load_catalog is cat.load_catalog
       and core.is_stale is cat.is_stale
       and core.validate_query is cat.validate_query
       and core.fetch_meta is cat.fetch_meta)
    ck("catalog 路径常量与内核一致",
       cat.CATALOG_PATH == core.CATALOG_PATH
       and core.catalog_path() == core.CATALOG_PATH,
       str(core.CATALOG_PATH))

    # --- 26B. 输入校验（约定 14：边界只留一处）
    for bad_q, why in [("", "空"), (None, "非字符串"), ("x" * 201, "超长")]:
        try:
            core.validate_query(bad_q)
            ck(f"validate_query 拒绝{why}", False)
        except core.ConfigError:
            ck(f"validate_query 拒绝{why}", True)
    ck("validate_query 正常去空白", core.validate_query("  skills for agents  ")
       == "skills for agents")
    for bad_repo in ("", "justname", "a/b/c", "o r/p"):
        try:
            core.fetch_meta(bad_repo)
            ck(f"fetch_meta 拒绝坏 repo（{bad_repo!r}）", False)
        except core.ConfigError:
            ck(f"fetch_meta 拒绝坏 repo（{bad_repo!r}）", True)

    # --- 26C. normalize：统一字段，坏 payload 尽量早死
    n = core.normalize_repo_payload({
        "full_name": "o/r", "stargazers_count": "12", "pushed_at": "2026-10-07T01:02:03Z",
        "description": None, "language": "Python", "homepage": "",
        "archived": 0, "html_url": "https://github.com/o/r", "topics": "bad"})
    ck("normalize 字段与类型",
       n["repo"] == "o/r" and n["stars"] == 12 and n["pushedAt"] == "2026-10-07"
       and n["description"] == "" and n["archived"] is False and n["topics"] == [],
       str(n))
    try:
        core.normalize_repo_payload({"id": 1})
        ck("normalize 缺 full_name 报错", False)
    except core.ConfigError:
        ck("normalize 缺 full_name 报错", True)

    # --- 26D. refresh 全流程（假接缝，零网络）
    calls = []

    def fake_gh(path, params=None, timeout=None):
        calls.append((path, params))
        if path.startswith("/repos/"):
            repo = path[len("/repos/"):]
            return {"full_name": repo, "stargazers_count": 7,
                    "pushed_at": "2026-10-07T01:02:03Z",
                    "description": "fake", "language": "Python",
                    "html_url": "https://github.com/" + repo}
        if path == "/search/repositories":
            q = (params or {}).get("q", "")
            items = [{"full_name": f"o/{q}{i}", "stargazers_count": 100 - i,
                      "pushed_at": "2026-10-06T00:00:00Z", "description": f"item{i}",
                      "html_url": f"https://github.com/o/{q}{i}"} for i in range(3)]
            items.append("not-a-dict")           # 单条畸形不能拖垮整页
            return {"items": items}
        raise AssertionError(f"假接缝收到意外路径：{path}")

    real_gh = cat._gh_request
    catlog = core.CATALOG_PATH
    catlog.unlink(missing_ok=True)
    try:
        cat._gh_request = fake_gh

        rep = core.refresh_catalog(repos=["owner/repo", "another/one"], force=True, now=1000.0)
        ck("force 刷新全部拉取", rep["fetched"] == 2 and rep["failed"] == 0
           and len(calls) == 2, f"fetched={rep['fetched']} calls={len(calls)}")
        disk = core.load_catalog()
        ck("缓存落盘且可读回", disk["repos"]["owner/repo"]["stars"] == 7
           and disk["schema"] == 1 and disk["refreshedAtEpoch"] == 1000.0, str(disk)[:120])
        ck("is_stale 判新鲜", not core.is_stale(disk, now=2000.0, max_age=24 * 3600.0))
        ck("is_stale 过期判定", core.is_stale(disk, now=2000.0, max_age=1.0))

        before_text = catlog.read_text(encoding="utf-8")
        calls.clear()
        rep2 = core.refresh_catalog(repos=["owner/repo", "another/one"],
                                    force=False, now=2000.0)
        ck("新鲜缓存零请求零写盘", rep2.get("noop") is True and calls == []
           and catlog.read_text(encoding="utf-8") == before_text)
        ck("noop 沿用旧 refreshedAt", rep2["refreshedAt"] == disk["refreshedAt"])

        calls.clear()
        rep3 = core.refresh_catalog(repos=["OWNER/REPO"], force=False, now=2000.0)
        ck("大小写变体命中同一条缓存", rep3["skipped"] == 1 and calls == [])

        calls.clear()
        rep4 = core.refresh_catalog(repos=["owner/repo"], force=False,
                                    max_age=-1.0, now=3000.0)
        ck("过期条目重新拉取", rep4["fetched"] == 1 and len(calls) == 1)

        def boom(path, params=None, timeout=None):
            raise OSError("模拟网络故障")

        cat._gh_request = boom
        old_epoch = core.load_catalog()["refreshedAtEpoch"]
        rep5 = core.refresh_catalog(repos=["owner/repo"], force=True, now=4000.0)
        ck("失败保留旧值", rep5["failed"] == 1 and rep5["fetched"] == 0
           and core.load_catalog()["repos"]["owner/repo"]["stars"] == 7)
        ck("失败记入 errors", "模拟网络故障" in rep5["catalog"]["errors"]["owner/repo"])
        ck("★ 全部失败不算刷新过（refreshedAt 沿用旧值）",
           rep5["catalog"]["refreshedAtEpoch"] == old_epoch)
        ck("失败条目按旧数据判龄（不因失败变「新鲜」）",
           core.is_stale(core.load_catalog(), now=old_epoch + 24 * 3600.0 + 1.0,
                         max_age=24 * 3600.0))

        cat._gh_request = fake_gh          # 恢复接缝，验证自动重试路径
        calls.clear()
        rep5b = core.refresh_catalog(repos=["owner/repo"], force=False,
                                     now=old_epoch + 24 * 3600.0 + 1.0)
        ck("★ TTL 过期后按条目重试成功并清掉错误",
           rep5b["fetched"] == 1 and len(calls) == 1
           and rep5b["catalog"]["errors"] == {},
           f"fetched={rep5b['fetched']} calls={len(calls)}")

        catlog.write_text("{这不是 json", encoding="utf-8")
        ck("坏缓存当不存在", core.load_catalog() == {})
        rep6 = core.refresh_catalog(repos=["owner/repo"], force=True, now=6000.0)
        ck("坏缓存也能刷新回来", rep6["fetched"] == 1
           and core.load_catalog()["repos"]["owner/repo"]["stars"] == 7)

        # --- 26E. 搜索解析：limit 截断 + 单条畸形跳过
        items = core.search_repos("skills", limit=2)
        ck("搜索解析与 limit 截断",
           len(items) == 2 and items[0]["repo"] == "o/skills0" and items[0]["stars"] == 100,
           str(items)[:120])
        try:
            core.search_repos("   ")
            ck("搜索拒绝空词", False)
        except core.ConfigError:
            ck("搜索拒绝空词", True)

        # --- 26E-2. 搜索翻页（v2.35 NEXT_STEPS 任务5）：page 透传 /
        #      坏值回退 / 上限截断（前端「加载更多」依赖）
        calls.clear()
        core.search_repos("skills", limit=20, page=3)
        ck("★ 搜索翻页：page 透传上游（per_page 上限纪律不变）",
           calls[-1][1].get("page") == 3 and calls[-1][1].get("per_page") == 20,
           str(calls[-1][1]))
        core.search_repos("skills", limit=20, page=0)
        ck("搜索翻页：0 / 负页号回退第 1 页",
           calls[-1][1].get("page") == 1)
        core.search_repos("skills", limit=20, page=99999)
        ck("搜索翻页：超上限截到 SEARCH_PAGE_MAX",
           calls[-1][1].get("page") == core.SEARCH_PAGE_MAX,
           str(core.SEARCH_PAGE_MAX))
        core.search_repos("skills", limit=20, page="abc")
        ck("搜索翻页：非数字页号回退第 1 页（不透传异常）",
           calls[-1][1].get("page") == 1)
    finally:
        cat._gh_request = real_gh
        catlog.unlink(missing_ok=True)      # 给后面的用例留干净环境

    # --- 26F. 服务端三接口端到端（真起服务，假接缝）
    import market_server as srv  # noqa: E402

    TOKC = "selftest-catalog-token"
    httpd2 = srv.make_server(0, token=TOKC)
    PORT2 = httpd2.server_address[1]
    threading.Thread(target=httpd2.serve_forever, daemon=True).start()

    def hit2(path, body=None, headers=None, method=None):
        c = http.client.HTTPConnection("127.0.0.1", PORT2, timeout=10)
        m = method or ("POST" if body is not None else "GET")
        data = json.dumps(body).encode() if body is not None else None
        c.request(m, path, body=data, headers=headers or {})
        r = c.getresponse()
        raw = r.read()
        c.close()
        try:
            return r.status, json.loads(raw)
        except Exception:
            return r.status, raw.decode("utf-8", "replace")

    AUTHC = {"X-Local-Market-Token": TOKC, "Content-Type": "application/json"}
    try:
        st, js = hit2("/api/catalog", headers=AUTHC)
        ck("GET /api/catalog 形状", st == 200 and js.get("ok")
           and "stale" in js and "catalog" in js, f"{st} {str(js)[:80]}")

        st, _ = hit2("/api/gh/search?q=x")
        ck("★ 搜索无口令 → 403", st == 403, str(st))
        st, _ = hit2("/api/gh/search?q=x", headers={"X-Local-Market-Token": TOKC,
                                                    "Origin": "http://evil.example"})
        ck("★ 搜索跨源 → 403", st == 403, str(st))
        st, js = hit2("/api/gh/search?q=%20", headers=AUTHC)
        ck("空搜索词 → 400", st == 400, f"{st} {str(js)[:60]}")

        cat._gh_request = fake_gh        # 端到端也用假接缝，保持零网络
        try:
            st, js = hit2("/api/gh/search?q=agent", headers=AUTHC)
            ck("搜索接口返回条目（畸形条目被跳过）",
               st == 200 and js.get("ok") and len(js.get("items", [])) == 3,
               f"{st} {str(js)[:80]}")
            # v2.35 任务5：page 参数端到端（「加载更多」翻页）
            st, js = hit2("/api/gh/search?q=agent&page=2", headers=AUTHC)
            ck("★ 搜索接口接受 page 翻页参数",
               st == 200 and js.get("ok") and len(js.get("items", [])) == 3,
               f"{st} {str(js)[:80]}")
            srv._search_cache.clear()   # v2.37 LRU：别把缓存漏进下一用例

            st, js = hit2("/api/catalog/refresh", {}, AUTHC)
            ck("POST /api/catalog/refresh 起任务", st == 200 and js.get("ok")
               and js.get("jobId"), f"{st} {str(js)[:60]}")
            jid = js["jobId"]
            done, view = 0, {}
            # 预算 30s：基线实测过「任务线程被宿主机负载饿到 >10s 才被调度」
            # 的偶发（刷新本身成功，只是轮询放弃了）——预算放宽到 600 轮。
            while done < 600:
                _, view = hit2(f"/api/job/{jid}", headers=AUTHC)
                if view.get("status") == "done":
                    break
                done += 1
                time.sleep(0.05)
            ck("刷新任务真完成且成功", view.get("ok") is True,
               str(view.get("label"))[:80])
            ck("刷新后目录落盘", core.load_catalog().get("repos", {}).get("owner/repo", {})
               .get("stars") == 7)
        finally:
            cat._gh_request = real_gh
            srv._search_cache.clear()
    finally:
        httpd2.shutdown()
        httpd2.server_close()

    core.CATALOG_PATH.unlink(missing_ok=True)     # 收尾：留干净环境
    ck("收尾：目录缓存已清理", not core.CATALOG_PATH.exists())


def round12():
    """v2.11：社区注册表 + Windows 假空闲端口修复。

    三条盯防线：
    1. registry 是**不可信状态文件**：坏 JSON / 坏 schema 当不存在，
       坏条目跳过，绝不让社区数据炸掉状态页（与 catalog 同一口径）；
    2. 「source 必须如实标注」：在线三路（env / raw / api）→ 缓存 →
       本地副本，逐级兜底时 source 跟着变 —— 绝不把兜底数据假装成
       「刚从 GitHub 拉的」；
    3. **Windows 假空闲端口**：探测 socket 设 SO_REUSEADDR 时，Windows
       允许绑定别的进程正监听的端口（同机多进程同绑 8777，2026-10-07
       实测复现）。真起服务后 _find_port(p) 绝不允许再返回 p。
    """
    section("27. v2.11：社区注册表（registry 模块 + CI 重建 + 端口修复）")

    import workbuddy_market.registry as reg

    # --- 27A. 符号同一性（re-export 必须就是包里的同一对象）
    ck("★ registry 符号同一性",
       core.get_registry is reg.get_registry
       and core.parse_registry is reg.parse_registry
       and core.load_registry_cache is reg.load_registry_cache
       and core.registry_routes is reg.registry_routes
       and core._registry_http_get is reg._registry_http_get)
    ck("registry 路径常量与内核一致",
       reg.REGISTRY_PATH == core.REGISTRY_PATH
       and core.registry_path() == core.REGISTRY_PATH,
       str(core.REGISTRY_PATH))
    ck("本地副本路径在仓库根 registry/ 下",
       core.local_registry_file() == core.MARKET_ROOT / "registry" / "plugins.json",
       str(core.local_registry_file()))

    # --- 27B. parse_registry：边界只留一处，坏条目跳过不拖垮整份
    doc = {"schema": 1, "updatedAt": "2026-10-07", "plugins": [
        {"repo": "owner/repo", "displayName": "A", "category": "官方",
         "description": "d", "keywords": ["k1", "  ", 3],
         "stars": 12, "pushedAt": "2026-10-06", "latestSha": "abc"},
        {"repo": "OWNER/REPO"},                      # 大小写重复 → 跳过
        {"repo": "bad-repo"},                        # 非法 repo → 跳过
        {"repo": 42},                                # 非字符串 → 跳过
        "not-a-dict",                                # 畸形条目 → 跳过
        {"repo": "another/one", "stars": "bad",      # 坏动态字段当没有
         "keywords": "not-a-list"},
    ]}
    parsed = core.parse_registry(doc)
    ck("★ parse_registry 跳过坏条目并去重",
       [e["repo"] for e in parsed["plugins"]] == ["owner/repo", "another/one"]
       and parsed["skipped"] == 4, f"skipped={parsed['skipped']}")
    e0 = parsed["plugins"][0]
    ck("动态字段类型守卫 + 关键词清洗",
       e0["stars"] == 12 and e0["pushedAt"] == "2026-10-06"
       and e0["keywords"] == ["k1"], str(e0)[:120])
    ck("坏动态字段 / 坏 keywords 不进条目",
       parsed["plugins"][1].get("stars") is None
       and parsed["plugins"][1]["keywords"] == []
       and parsed["plugins"][1]["category"] == "未分类")
    for bad_doc, why in [({"schema": 2, "plugins": []}, "schema 不认识"),
                         ({"schema": 1}, "缺 plugins"),
                         ({"schema": 1, "plugins": {}}, "plugins 非数组"),
                         ([1, 2], "顶层非对象"),
                         ("{这不是 json", "非 JSON 文本")]:
        try:
            core.parse_registry(bad_doc)
            ck(f"parse_registry 拒绝{why}", False)
        except core.ConfigError:
            ck(f"parse_registry 拒绝{why}", True)

    # --- 27B-2. artifact_build_date（v2.35 NEXT_STEPS 任务3）：
    # 从 packageUrl 的发布 tag 解析工件构建日期；没有/解析不出一律
    # 空串——没有日期绝不用 pushedAt 冒充。
    from workbuddy_market.registry import artifact_build_date   # noqa: E402
    ck("★ artifact_build_date：发布 tag 内日期解析",
       artifact_build_date({"packageUrl":
           "https://github.com/o/r/releases/download/registry-artifacts-2026-10-11/x.tar.gz"})
       == "2026-10-11")
    ck("artifact_build_date：无 packageUrl → 空串（不冒充）",
       artifact_build_date({"pushedAt": "2026-10-09"}) == ""
       and artifact_build_date({}) == "")
    ck("artifact_build_date：tag 不含日期 → 空串",
       artifact_build_date({"packageUrl":
           "https://github.com/o/r/releases/download/latest/x.tar.gz"}) == "")

    # --- 27C. 拉取路线与三级兜底（假接缝，零网络）
    good_doc = {"schema": 1, "updatedAt": "2026-10-07",
                "plugins": [{"repo": "owner/repo", "displayName": "A"}]}
    good_bytes = json.dumps(good_doc).encode("utf-8")
    real_get = reg._registry_http_get
    core.REGISTRY_PATH.unlink(missing_ok=True)
    try:
        # 27C-1: 首选路线（raw）成功 → source 如实、缓存落盘
        def ok_raw(url, headers=None, timeout=None):
            if "raw.githubusercontent.com" in url:
                return good_bytes
            raise OSError("这条路线不该被走到")

        reg._registry_http_get = ok_raw
        r1 = core.get_registry(force=True, now=1000.0)
        ck("首选路线成功 → source=raw 且 fetched",
           r1["fetched"] is True and r1["source"] == "raw.githubusercontent.com"
           and len(r1["plugins"]) == 1, str(r1.get("source")))
        ck("注册表缓存落盘且可读回",
           core.load_registry_cache()["plugins"][0]["repo"] == "owner/repo")

        # 27C-2: raw 挂 → api 路线接住（且必须带 raw accept 头，否则拿到的是
        # contents 接口的 base64 JSON 信封，解析必炸）
        seen_headers = []

        def raw_down(url, headers=None, timeout=None):
            if "raw.githubusercontent.com" in url:
                raise OSError("raw 超时（国内常态）")
            if "api.github.com" in url:
                seen_headers.append(dict(headers or {}))
            return good_bytes

        reg._registry_http_get = raw_down
        r2 = core.get_registry(force=True, now=2000.0)
        ck("★ raw 挂 → api.github.com 接住且带 raw 头",
           r2["source"] == "api.github.com" and r2["fetched"] is True
           and seen_headers and seen_headers[0].get("Accept")
           == "application/vnd.github.raw",
           f"{r2.get('source')} headers={seen_headers[:1]}")

        # 27C-3: 全挂 + 缓存还在 → 退缓存（stale 与否按 TTL 如实）
        def all_down(url, headers=None, timeout=None):
            raise OSError(f"网络全挂：{url}")

        reg._registry_http_get = all_down
        r3 = core.get_registry(force=True, now=3000.0)   # force 拉不动 → 退缓存
        ck("★ 在线全挂 → 退回缓存且 source 如实",
           r3["source"] == "cache" and r3["fetched"] is False
           and r3["stale"] is False and len(r3["plugins"]) == 1,
           f"{r3.get('source')} stale={r3.get('stale')}")
        r3b = core.get_registry(force=True, now=3000.0 + core.REGISTRY_TTL + 1)
        ck("过期缓存的 stale 标记如实",
           r3b["stale"] is True and r3b["source"] == "cache")

        # 27C-4: 全挂 + 无缓存 → 本地副本兜底
        core.REGISTRY_PATH.unlink(missing_ok=True)
        local_f = core.local_registry_file()
        local_f.parent.mkdir(parents=True, exist_ok=True)
        local_f.write_text(json.dumps(good_doc), encoding="utf-8")
        try:
            r4 = core.get_registry(force=True, now=4000.0)
            ck("★ 缓存也没有 → 本地副本兜底",
               r4["source"] == "local-repo" and r4["stale"] is True
               and len(r4["plugins"]) == 1, str(r4.get("source")))
        finally:
            import shutil as _sh
            _sh.rmtree(local_f.parent, ignore_errors=True)

        # 27C-5: WBM_REGISTRY_URL 环境变量成为第一优先路线
        os.environ["WBM_REGISTRY_URL"] = "https://mirror.example/reg.json"
        try:
            routes = core.registry_routes()
            ck("env 覆盖插入为第一路线",
               routes[0][0] == "env-override"
               and routes[0][1] == "https://mirror.example/reg.json",
               str(routes[0][:2]))

            def only_env(url, headers=None, timeout=None):
                if url == "https://mirror.example/reg.json":
                    return good_bytes
                raise OSError("env 之后的路线不应被走到")

            reg._registry_http_get = only_env
            r5 = core.get_registry(force=True, now=5000.0)
            ck("★ env 路线命中 → source 如实标注",
               r5["source"] == "env-override" and r5["fetched"] is True,
               str(r5.get("source")))
        finally:
            os.environ.pop("WBM_REGISTRY_URL", None)
    finally:
        reg._registry_http_get = real_get
        core.REGISTRY_PATH.unlink(missing_ok=True)

    # --- 27D. 缓存 TTL 语义：force=False 全新鲜时零联网
    calls = {"n": 0}

    def count_get(url, headers=None, timeout=None):
        calls["n"] += 1
        return good_bytes

    reg._registry_http_get = count_get
    try:
        core.get_registry(force=True, now=6000.0)          # 先填缓存
        calls["n"] = 0
        r6 = core.get_registry(force=False, now=6100.0)
        ck("新鲜缓存内零联网（force=False）",
           r6["fetched"] is False and r6["source"] == "cache" and calls["n"] == 0,
           f"calls={calls['n']}")
        r7 = core.get_registry(force=True, now=6200.0)
        ck("force=True 无视 TTL 重新拉取", r7["fetched"] is True and calls["n"] == 1)
    finally:
        reg._registry_http_get = real_get
        core.REGISTRY_PATH.unlink(missing_ok=True)

    # --- 27E. build_registry.refresh_entry（CI 与本机共用的纯函数）
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "build_registry", str(REPO_ROOT / "scripts" / "build_registry.py"))
    breg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(breg)
    entry = {"repo": "owner/repo", "displayName": "A", "stars": 1,
             "pushedAt": "", "latestSha": "", "refreshedAt": ""}
    def fake_fetch(repo):
        return {"full_name": repo, "stargazers_count": 99,
                "pushed_at": "2026-10-07T08:09:10Z"}
    def fake_ref(repo):
        return [{"sha": "0123456789abcdef" * 2 + "0123"}]
    new_e = breg.refresh_entry(entry, fake_fetch, ref_fetch=fake_ref)
    ck("refresh_entry 更新动态字段且不改原对象",
       new_e["stars"] == 99 and new_e["pushedAt"] == "2026-10-07"
       and new_e["latestSha"] == "0123456789abcdef" * 2 + "0123"
       and entry["stars"] == 1 and entry["latestSha"] == "")
    ck("refresh_entry 不覆盖静态字段",
       new_e["displayName"] == "A" and new_e["repo"] == "owner/repo")
    def bad_fetch(repo):
        return {"id": 1}
    try:
        breg.refresh_entry(entry, bad_fetch)
        ck("refresh_entry 拒绝缺 full_name 的 payload", False)
    except ValueError:
        ck("refresh_entry 拒绝缺 full_name 的 payload", True)

    # --- 27E-2. ★ main() 的 fetch 契约回归（2026-10-07 真实 bug）：
    # main 直接把 _gh_get（收 API 路径）当 fetch（收 repo 名）传进
    # refresh_entry，拼出 api.github.comanthropics/skills 坏主机名，
    # 代理只报「Tunnel 502」，排查极难。这里用假接缝记录实际请求的
    # 路径，必须全部以 /repos/ 开头。
    seen_paths = []
    real_bgh = breg._gh_get
    tmp_reg = _TMP / "registry-test" / "plugins.json"
    tmp_reg.parent.mkdir(parents=True, exist_ok=True)
    tmp_doc = {"schema": 1, "updatedAt": "", "plugins": [
        {"repo": "owner/repo", "displayName": "A"}]}
    tmp_reg.write_text(json.dumps(tmp_doc), encoding="utf-8")
    real_bfile = breg.REGISTRY_FILE
    try:
        breg._gh_get = lambda path: (seen_paths.append(path),
                                     {"full_name": path[len("/repos/"):],
                                      "stargazers_count": 5,
                                      "pushed_at": "2026-10-07T00:00:00Z"})[1]
        breg.REGISTRY_FILE = tmp_reg
        breg.main(["--dry-run"])
        ck("★ main 的 fetch 契约：实际请求都是 /repos/... 路径",
           seen_paths and all(p.startswith("/repos/") for p in seen_paths)
           and any(p.endswith("/commits?per_page=1") for p in seen_paths),
           str(seen_paths[:3]))
    finally:
        breg._gh_get = real_bgh
        breg.REGISTRY_FILE = real_bfile

    # --- 27F. GET /api/registry 端到端（真起服务，假接缝）
    import market_server as srv  # noqa: E402

    TOKR = "selftest-registry-token"
    httpd3 = srv.make_server(0, token=TOKR)
    PORT3 = httpd3.server_address[1]
    threading.Thread(target=httpd3.serve_forever, daemon=True).start()

    def hit3(path, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", PORT3, timeout=10)
        c.request("GET", path, headers=headers or {})
        r = c.getresponse()
        raw = r.read()
        c.close()
        try:
            return r.status, json.loads(raw)
        except Exception:
            return r.status, raw.decode("utf-8", "replace")

    AUTHR = {"X-Local-Market-Token": TOKR}
    try:
        st, _ = hit3("/api/registry")
        ck("GET /api/registry 无口令 → 403", st == 403, str(st))
        st, _ = hit3("/api/registry", {"X-Local-Market-Token": TOKR,
                                       "Origin": "http://evil.example"})
        ck("GET /api/registry 跨源 → 403", st == 403, str(st))

        reg._registry_http_get = count_get      # 端到端也用假接缝，保持零网络
        core.REGISTRY_PATH.unlink(missing_ok=True)
        try:
            st, js = hit3("/api/registry", AUTHR)
            ck("GET /api/registry 形状（plugins/installedRepos/ttlHours）",
               st == 200 and js.get("ok") is True
               and isinstance(js.get("plugins"), list) and len(js["plugins"]) == 1
               and "installedRepos" in js and js.get("ttlHours") == 6,
               f"{st} {str(js)[:90]}")
            ck("★ 接口如实标注拉取来源",
               js.get("source") == "raw.githubusercontent.com"
               and js.get("stale") is False, str(js.get("source")))
            srv._registry_mem.update(at=0.0, force=None, data=None)

            st, js = hit3("/api/registry?force=1", AUTHR)
            ck("?force=1 强制在线拉取", st == 200 and js.get("ok")
               and js.get("source") == "raw.githubusercontent.com",
               str(js.get("source")))
        finally:
            reg._registry_http_get = real_get
            srv._registry_mem.update(at=0.0, force=None, data=None)
            core.REGISTRY_PATH.unlink(missing_ok=True)
    finally:
        httpd3.shutdown()
        httpd3.server_close()

    # --- 27G. ★ Windows 假空闲端口修复盯防（本轮的起点 bug）
    httpd4 = srv.make_server(0)                     # 真起监听（随机端口）
    busy = httpd4.server_address[1]
    try:
        threading.Thread(target=httpd4.serve_forever, daemon=True).start()
        time.sleep(0.05)
        picked = srv._find_port(busy)
        ck("★ 已被监听的端口绝不允许再被探测选中（v2.10 同绑 8777 复现点）",
           picked != busy and busy < picked <= busy + 20,
           f"busy={busy} picked={picked}")
    finally:
        httpd4.shutdown()
        httpd4.server_close()

    # --- 27H. 供应链固定校验（v2.12）：/api/remote/add 的上游漂移闸门
    # 收录时固定的 sourceCommit ≠ CI 刷出的 latestSha → 默认 409 拦下，
    # force=True 才放行；注册表不可用时不锁死安装（闸门守的是「收录过的」）。
    httpd5 = srv.make_server(0, token=TOKR)
    PORT5 = httpd5.server_address[1]
    threading.Thread(target=httpd5.serve_forever, daemon=True).start()

    def post5(path, obj, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", PORT5, timeout=10)
        c.request("POST", path, body=json.dumps(obj).encode(),
                  headers={"Content-Type": "application/json", **(headers or {})})
        r = c.getresponse()
        raw = r.read()
        c.close()
        try:
            return r.status, json.loads(raw)
        except Exception:
            return r.status, raw.decode("utf-8", "replace")

    SHA_A, SHA_B = "a" * 40, "b" * 40
    fake_reg = {"plugins": [
        {"repo": "owner/drift", "sourceCommit": SHA_A, "latestSha": SHA_B},
        {"repo": "owner/fresh", "sourceCommit": SHA_B, "latestSha": SHA_B},
        {"repo": "owner/nosha", "sourceCommit": SHA_A},
    ]}
    real_getreg = core.get_registry
    core.get_registry = lambda force=False, now=None: fake_reg
    captured = {}
    real_rjob5 = srv._remote_job

    def fake_rjob(repo, action, allow_non_skill=False):
        captured.update(repo=repo, action=action, allow_non_skill=allow_non_skill)
        return "fake-jid"

    srv._remote_job = fake_rjob
    try:
        st, js = post5("/api/remote/add", {"repo": "owner/drift"}, AUTHR)
        ck("★ 上游漂移 → 409 拦截并带凭证",
           st == 409 and js.get("drift", {}).get("sourceCommit") == SHA_A
           and js.get("drift", {}).get("latestSha") == SHA_B,
           f"{st} {str(js)[:80]}")
        st, js = post5("/api/remote/add", {"repo": "owner/drift", "force": True}, AUTHR)
        ck("★ force=True 显式放行", st == 200 and js.get("jobId") == "fake-jid", str(st))
        st, js = post5("/api/remote/add", {"repo": "owner/fresh"}, AUTHR)
        ck("★ 未漂移照常放行", st == 200 and js.get("ok") is True, str(st))
        st, js = post5("/api/remote/add", {"repo": "owner/nosha"}, AUTHR)
        ck("★ 缺 latestSha 不误拦（无法判定 ≠ 判定漂移）", st == 200, str(st))
        st, js = post5("/api/remote/add",
                       {"repo": "owner/fresh", "allowNonSkill": True}, AUTHR)
        ck("★ 兼容模式必须显式传入才开启",
           st == 200 and captured.get("allow_non_skill") is True, str(captured))
        st, js = post5("/api/remote/add", {"repo": "owner/fresh"}, AUTHR)
        ck("★ 默认关闭兼容模式",
           st == 200 and captured.get("allow_non_skill") is False, str(captured))

        def reg_boom(force=False, now=None):
            raise RuntimeError("离线")
        core.get_registry = reg_boom
        st, js = post5("/api/remote/add", {"repo": "owner/anything"}, AUTHR)
        ck("★ 注册表不可用时跳过校验、不锁死安装", st == 200, f"{st} {str(js)[:60]}")
    finally:
        srv._remote_job = real_rjob5
        core.get_registry = real_getreg
        httpd5.shutdown()
        httpd5.server_close()

    core.REGISTRY_PATH.unlink(missing_ok=True)      # 收尾：留干净环境
    ck("收尾：注册表缓存已清理", not core.REGISTRY_PATH.exists())


