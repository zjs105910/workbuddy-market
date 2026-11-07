# -*- coding: utf-8 -*-
"""第 45 节：回收站 restore —— 内容指纹 / 事务 / 所有权闭环 / 评审修复。

背景：v2.39 之前回收站「能进、能清、能自愈索引，唯独不能出」，网页甚至
写着「位置 <市场根>\\.trash」这个 v2.7 起就失效的旧路径。本轮补齐恢复。

五条盯防线：
1. 搬入时留 treeHash（内容 SHA-256）+ 卸载者带来的所有权快照；旧条目、
   手工放入、sync 退役 / reinstall 旧版本一律缺指纹 → 诚实拒绝，绝不洗白；
2. 恢复前复算 treeHash，不符 / 读不全 → conflict，条目、日志、所有权全保留；
   目标只由内核构造，已存在绝不覆盖，网页传不进任何路径；
3. tx_begin / staged 凭证先于磁盘变更，成功后重建所有权 —— 恢复完还卸得掉；
4. state 暴露条目摘要与真实回收站目录，网页逐项两段式确认；服务端端到端
   验证 400 / 200 / 二次恢复 400；
5. 顺带盯住同轮评审修复：卸载失败进 failed、.partial 不补录、写侧 dst
   校验、doctor 口径统一、prune 持锁、二进制上传异常不裸断；
6. 第二轮加固：写接口缺/跨源 Origin → 403、只读 GET 无 Origin 仍放行、
   4 线程真并发收藏无丢失更新、4 线程真并发索引 flush 不互相覆盖。
"""
from __future__ import annotations

import http.client
import json
import shutil
import threading

from . import _TMP, ck, core, section, wm


def round40():
    section("45. 回收站 restore（内容指纹 → 冲突 → 恢复 → 所有权闭环）")
    import workbuddy_market.trash as tr
    import workbuddy_market.uninstaller as un
    import workbuddy_market.doctor as doc

    tmp = _TMP / "r40-lab"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    SNAME, PID, VER = "r40skill", "r40-demo", "1.2.3"
    PKG_HASH = "a" * 64
    d = core.SKILLS_DIR / SNAME
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {SNAME}\nversion: {VER}\n---\n# {SNAME}\n", encoding="utf-8")
    (d / "notes.md").write_text("original\n", encoding="utf-8")
    core.record_owner(PID, [SNAME], VER, package_hash=PKG_HASH)
    want_hash = core.tree_hash(d)

    # --- 45A. 卸载 → 条目带可恢复凭据
    r_un = core.uninstall_local_plugin(PID)
    ck("卸载成功（虚拟插件经所有权回退）",
       r_un.get("ok") is True and r_un.get("moved") == [SNAME], str(r_un)[:140])
    idx = tr._load_trash_index()["items"]
    name = next((n for n, e in idx.items() if e.get("skill") == SNAME), "")
    entry = idx.get(name, {})
    ck("★ 条目记下搬入时的 treeHash（恢复的唯一凭据）",
       bool(name) and entry.get("treeHash") == want_hash, str(entry.get("treeHash"))[:80])
    ck("★ 条目封存 owner 快照（plugin / version / packageHash）",
       entry.get("owner", {}).get("plugin") == PID
       and entry.get("owner", {}).get("version") == VER
       and entry.get("owner", {}).get("packageHash") == PKG_HASH,
       str(entry.get("owner"))[:120])
    ck("卸载后所有权已清", SNAME not in core.load_ownership()["skills"])
    target = tr._trash_entry(name)

    # --- 45B. 入口防线：确认 / 名字 / 存在性
    r0 = tr.restore_from_trash(name)
    ck("★ 未经确认 → 拒绝，条目与本机目录都不动",
       not r0.get("ok") and target.is_dir() and not d.exists(), str(r0)[:120])
    ck("★ 非法条目名（路径穿越）→ 拒绝",
       not tr.restore_from_trash("../evil", confirmed=True).get("ok"))
    ck("★ 不存在的条目 → 诚实报错",
       not tr.restore_from_trash("nope__uninstall", confirmed=True).get("ok"))

    # --- 45C. 内容被改动 → conflict，绝不洗白
    (target / "notes.md").write_text("tampered\n", encoding="utf-8")
    r1 = tr.restore_from_trash(name, confirmed=True)
    ck("★ 内容被改动 → conflict（条目 / 文件 / 所有权全保留）",
       not r1.get("ok") and "改动" in str(r1.get("conflict", {}).get("reason", ""))
       and target.is_dir() and not d.exists()
       and SNAME not in core.load_ownership()["skills"], str(r1)[:160])
    (target / "notes.md").write_text("original\n", encoding="utf-8")

    # --- 45D. 目标已存在 → 拒绝覆盖
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("someone else\n", encoding="utf-8")
    r2 = tr.restore_from_trash(name, confirmed=True)
    ck("★ 同名目标已存在 → 拒绝覆盖（不动别人的文件）",
       not r2.get("ok") and "已存在" in str(r2.get("conflict", {}).get("reason", ""))
       and (d / "SKILL.md").read_text(encoding="utf-8") == "someone else\n"
       and target.is_dir(), str(r2)[:140])
    shutil.rmtree(d, ignore_errors=True)

    # --- 45E/F. 不可信索引字段：缺指纹 / skill 名投毒
    dirty = tr._load_trash_index()
    dirty["items"][name]["treeHash"] = ""
    tr._save_trash_index(dirty)
    r3 = tr.restore_from_trash(name, confirmed=True)
    ck("★ 旧条目缺 treeHash → 诚实拒绝（升级前 / 手工放入不洗白）",
       not r3.get("ok") and "指纹" in str(r3.get("conflict", {}).get("reason", ""))
       and not d.exists(), str(r3)[:140])
    dirty = tr._load_trash_index()
    dirty["items"][name]["treeHash"] = want_hash
    dirty["items"][name]["skill"] = "../../evil"
    tr._save_trash_index(dirty)
    r4 = tr.restore_from_trash(name, confirmed=True)
    ck("★ 索引里 skill 名投毒 → 拒绝（origin 不参与路径构造）",
       not r4.get("ok") and not (core.SKILLS_DIR / "evil").exists()
       and target.is_dir(), str(r4)[:140])
    dirty = tr._load_trash_index()
    dirty["items"][name]["skill"] = SNAME
    tr._save_trash_index(dirty)

    # --- 45G. 正常恢复：文件 / 哈希 / 所有权 / 索引 / 事务日志
    r5 = tr.restore_from_trash(name, confirmed=True)
    ck("★ 确认恢复成功（treeHash 校验通过）",
       r5.get("ok") is True and r5.get("restored") == SNAME
       and r5.get("treeHashVerified") is True, str(r5)[:160])
    ck("★ 文件真的回到 SKILLS_DIR 且内容哈希一致",
       (d / "SKILL.md").is_file() and core.tree_hash(d) == want_hash)
    rec = core.load_ownership()["skills"].get(SNAME, {})
    ck("★ 所有权重建（恢复完还归市场管）",
       rec.get("plugin") == PID and rec.get("version") == VER
       and rec.get("hash") == want_hash and rec.get("packageHash") == PKG_HASH,
       str(rec)[:150])
    ck("★ 索引移除已恢复条目 / 回收站条目目录消失",
       name not in tr._load_trash_index()["items"] and not target.exists())
    ck("★ restore 事务日志已结清（不留未结条目）",
       not any(t.get("operation") == "restore" for t in core.tx_list()))
    plan = core.plugin_uninstall_plan(PID, purpose="uninstall")
    ck("★ 恢复后仍判 safe（卸得掉，闭环）",
       SNAME in plan.get("removable", []), str(plan.get("removable"))[:100])

    # --- 45H. state 摘要：网页看得见条目与真实位置
    st = core.build_state()
    ck("★ state 给出真实回收站位置（不再是写死的仓库根 .trash）",
       st["trash"].get("dir") == str(core.TRASH_DIR), str(st["trash"].get("dir"))[:100])
    ck("★ state 条目摘要带 restorable / occupied / skill",
       isinstance(st["trash"].get("items"), list)
       and all({"restorable", "occupied", "skill"} <= set(i) for i in st["trash"]["items"]))

    # --- 45I. 同轮评审修复：卸载失败诚实计入 failed
    real_mtt = un.move_to_trash
    un.move_to_trash = lambda *a, **k: None
    try:
        r_fail = core.uninstall_local_plugin(PID)
    finally:
        un.move_to_trash = real_mtt
    ck("★ 搬入回收站失败进 failed 且不再谎报 ok（本机文件未动）",
       r_fail.get("ok") is False and r_fail.get("failed") == [SNAME]
       and (d / "SKILL.md").is_file(), str(r_fail)[:140])

    # --- 45J. 同轮评审修复：脏条目补录 / 写侧校验 / doctor 口径 / prune 持锁
    partial = core.TRASH_DIR / "20260101-000000__x.partial"
    partial.mkdir(parents=True, exist_ok=True)
    ts = tr.trash_stats()
    ck("★ 跨卷残留 .partial 不被补录成正式条目",
       partial.name not in {i["name"] for i in ts["items"]}
       and partial.name not in tr._load_trash_index()["items"])
    shutil.rmtree(partial, ignore_errors=True)
    junk = tmp / "junk"
    junk.mkdir(parents=True)
    (junk / "SKILL.md").write_text("x\n", encoding="utf-8")
    ck("★ 写侧拒绝带路径分隔符的 reason（源目录原样保留）",
       tr.move_to_trash(junk, "../escape") is None and junk.is_dir())
    ck("★ doctor 非法名口径与 _trash_entry 一致",
       doc._bad_entry_name("..") and doc._bad_entry_name(".index.json")
       and not doc._bad_entry_name("20260101-000000__x__uninstall"))
    calls = {"n": 0}
    real_locked, real_impl = tr.locked, tr._prune_trash_impl

    def counting_locked(*a, **k):
        calls["n"] += 1
        return real_locked(*a, **k)

    tr.locked, tr._prune_trash_impl = counting_locked, lambda f, q: {"removed": 0}
    try:
        tr.prune_trash(force=False, quiet=True)
    finally:
        tr.locked, tr._prune_trash_impl = real_locked, real_impl
    ck("★ prune_trash 整段纳入全局锁（与卸载 / 状态轮询串行）",
       calls["n"] == 1, str(calls))

    # --- 45K. 服务端端到端：再卸载一次造出可恢复条目
    r_un2 = core.uninstall_local_plugin(PID)
    idx2 = tr._load_trash_index()["items"]
    name2 = next((n for n, e in idx2.items()
                  if e.get("skill") == SNAME and e.get("treeHash")), "")
    ck("再卸载造出可恢复条目", bool(name2) and r_un2.get("ok") is True,
       str(r_un2)[:120])

    import market_server as srv
    TOK = "selftest-restore-token"
    httpd = srv.make_server(0, token=TOK)
    PORT = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def post_json(path, body, headers=None):
        h = {"Content-Type": "application/json",
             "X-Local-Market-Token": TOK,
             "Origin": f"http://127.0.0.1:{PORT}"}
        # headers 里值为 None 表示「删掉这个头」，用于测缺 Origin 的分支
        for k, v in (headers or {}).items():
            if v is None:
                h.pop(k, None)
            else:
                h[k] = v
        c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=15)
        c.request("POST", path, body=json.dumps(body).encode("utf-8"), headers=h)
        resp = c.getresponse()
        raw = resp.read()
        c.close()
        try:
            return resp.status, json.loads(raw)
        except ValueError:
            return resp.status, {}

    try:
        s1, p1 = post_json("/api/trash/restore", {"name": name2})
        ck("★ 服务端：未经确认 → 400", s1 == 400 and not p1.get("ok"),
           f"{s1} {str(p1)[:100]}")
        s2, p2 = post_json("/api/trash/restore", {"name": name2, "confirmed": True})
        ck("★ 服务端：确认后 200 且技能落位", s2 == 200 and p2.get("ok")
           and (d / "SKILL.md").is_file(), f"{s2} {str(p2)[:120]}")
        s3, p3 = post_json("/api/trash/restore",
                           {"name": "../evil", "confirmed": True})
        ck("★ 服务端：非法条目名 → 400", s3 == 400 and not p3.get("ok"))
        s4, p4 = post_json("/api/trash/restore", {"name": name2, "confirmed": True})
        ck("★ 服务端：同一条目二次恢复 → 400（不会重复认领）",
           s4 == 400 and not p4.get("ok"))
        ck("★ 新接口登记 _STAGE_NAMES",
           srv._STAGE_NAMES.get("/api/trash/restore") == "恢复回收站条目"
           and srv._STAGE_NAMES.get("/api/import/upload") == "离线导入上传")
        # 二进制上传分流异常：必须回结构化 JSON，不能让连接裸断
        real_upload = srv.Handler._import_upload
        srv.Handler._import_upload = lambda self: (_ for _ in ()).throw(
            OSError("模拟上传崩溃"))
        try:
            s5, p5 = post_json("/api/import/upload", {})
        finally:
            srv.Handler._import_upload = real_upload
        ck("★ 上传异常回结构化 JSON（stage 中文，连接不裸断）",
           s5 == 500 and p5.get("ok") is False
           and p5.get("stage") == "离线导入上传", f"{s5} {str(p5)[:120]}")

        # --- 45L. 写接口 Origin 纵深防御（评审第二条：不能只压在 token 上）
        s6, p6 = post_json("/api/trash/restore", {"name": "x"},
                           {"Origin": None})
        ck("★ 写接口缺 Origin → 403（不再放行无来源的修改）",
           s6 == 403 and "Origin" in str(p6.get("error", "")), f"{s6} {str(p6)[:100]}")
        s7, p7 = post_json("/api/trash/restore", {"name": "x"},
                           {"Origin": "http://evil.example"})
        ck("★ 写接口跨源 Origin → 403", s7 == 403 and not p7.get("ok"))
        ck("★ origin_allowed 只读 / 写两种口径",
           srv.origin_allowed(None, PORT) is True
           and srv.origin_allowed(None, PORT, write=True) is False
           and srv.origin_allowed(f"http://127.0.0.1:{PORT}", PORT, write=True) is True
           and srv.origin_allowed("null", PORT, write=True) is False)
        cg = http.client.HTTPConnection("127.0.0.1", PORT, timeout=15)
        cg.request("GET", "/api/state",
                   headers={"X-Local-Market-Token": TOK})   # 故意不带 Origin
        rg = cg.getresponse()
        rg.read()
        gstatus = rg.status
        cg.close()
        ck("★ 只读 GET 无 Origin 仍放行（curl / 脚本可用性不变）", gstatus == 200,
           str(gstatus))
    finally:
        httpd.shutdown()
        httpd.server_close()

    # --- 45M. 真并发：同步写锁 + 回收站索引合并不丢数据
    import workbuddy_market.favorites as fav
    repos = [f"owner/concurrent{i}" for i in range(4)]
    err_f, bar_f = [], threading.Barrier(4)

    def add_fav(r):
        try:
            bar_f.wait(timeout=10)
            fav.set_favorite(r, True)
        except Exception as exc:      # noqa: BLE001 —— 并发异常要如实收集
            err_f.append(f"{r}: {exc!r}")

    th_f = [threading.Thread(target=add_fav, args=(r,)) for r in repos]
    for t in th_f:
        t.start()
    for t in th_f:
        t.join(timeout=20)
    saved = fav.load_favorites()
    ck("★ 4 线程真并发收藏：无异常、无丢失更新（同步写纳入市场锁）",
       not err_f and not any(t.is_alive() for t in th_f)
       and all(r in saved for r in repos), f"err={err_f[:2]} saved={saved[-6:]}")

    names = [f"20261107-00000{i}__concurrent{i}__uninstall" for i in range(4)]
    err_i, bar_i = [], threading.Barrier(4)

    def add_entry(n):
        try:
            idx = tr.TrashIndex()        # 各自读一份旧索引
            bar_i.wait(timeout=10)       # 真并发：同一时刻一起 flush
            idx.record(n, {"bytes": 1, "files": 1, "at": 0, "reason": "concurrent",
                           "origin": "", "treeHash": "", "skill": ""})
            idx.flush()
        except Exception as exc:        # noqa: BLE001
            err_i.append(f"{n}: {exc!r}")

    th_i = [threading.Thread(target=add_entry, args=(n,)) for n in names]
    for t in th_i:
        t.start()
    for t in th_i:
        t.join(timeout=20)
    final_idx = tr._load_trash_index()
    ck("★ 4 线程真并发写回收站索引：合并式 flush 不覆盖别人的条目",
       not err_i and not any(t.is_alive() for t in th_i)
       and all(n in final_idx["items"] for n in names),
       f"err={err_i[:2]} got={[n for n in names if n in final_idx['items']]}")
    for n in names:
        final_idx["items"].pop(n, None)
    tr._save_trash_index(final_idx)
    for r in repos:
        fav.set_favorite(r, False)

    # 收尾：隔离环境随 _TMP 消失，但别把本轮 skill 留给后续只读检查
    shutil.rmtree(d, ignore_errors=True)
    wm.ownership.forget_owner([SNAME])
    shutil.rmtree(tmp, ignore_errors=True)
