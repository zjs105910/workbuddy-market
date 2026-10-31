# -*- coding: utf-8 -*-
"""第 44 节（v2.39）：离线导入 —— 任意 skill 安装包：上传→预览→确认→事务安装。

v2.38 的离线安装只认「收录条目 + 钉死 packageHash」。用户实测需求再进
一步：手上有一个任意来源的 skill 安装包（GitHub Download ZIP、Release
产物、别人发来的 zip），在市场点按钮、选文件、直接装。v2.39 补齐：

四条盯防线：
1. 上传内容是不可信输入：zip 防线全在 unpack_zip / prepare_package /
   pack_package 同一套管线上，本模块不自己解 zip；暂存在系统临时目录
   （绝不进 SKILLS_DIR），TTL 清扫；
2. commit 必须 confirmed=True：未经收录审核的包，风险确认不可跳过；
   暂存 id 形状校验（16 位 hex），路径拼不进任何东西；
3. 收录上下文的严格链不回退：repo 给了且注册表条目有 packageHash →
   对不上整包拒绝（离线导入不是洗白通道）；
4. 装过的东西看得见、卸得掉：imports.json 记录显示名，state 社区分组
   出 via=import 卡片，卸载经 plugin_uninstall_plan 所有权回退。
"""
from __future__ import annotations

import http.client
import json
import shutil
import threading
import zipfile as _zf
from pathlib import Path
from . import _TMP, ck, core, section, wm


def _reader(data: bytes):
    """把 bytes 包成 read(chunk) 口（模拟 rfile.read 的分块语义）。"""
    buf = memoryview(data)
    state = {"i": 0}

    def read(n: int) -> bytes:
        i = state["i"]
        if i >= len(buf):
            return b""
        take = buf[i:i + n]
        state["i"] += len(take)
        return bytes(take)
    return read


def _mkzip(path, entries):
    with _zf.ZipFile(path, "w") as z:
        for name, data in entries:
            z.writestr(name, data)


def round39():
    section("44. v2.39：离线导入（任意 skill 安装包 → 预览 → 确认 → 事务安装）")
    import workbuddy_market.importer as imp
    import workbuddy_market.packaging as pk

    tmp = _TMP / "r39-lab"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)

    # --- 44A. find_skill_layout：三种收录形态 + 无 skill
    a = tmp / "lay-a"; (a / "skills" / "alpha").mkdir(parents=True)
    (a / "skills" / "alpha" / "SKILL.md").write_text("---\nname: alpha\n---\n", encoding="utf-8")
    (a / "skills" / "beta").mkdir()
    (a / "skills" / "beta" / "SKILL.md").write_text("---\nname: beta\n---\n", encoding="utf-8")
    root_a, names_a = imp.find_skill_layout(a)
    ck("★ 形态 a：root/skills/<name> 整包可装", root_a == a and names_a == ["alpha", "beta"])
    b = tmp / "lay-b"; (b / "one").mkdir(parents=True); (b / "two").mkdir()
    (b / "one" / "SKILL.md").write_text("---\nname: one\n---\n", encoding="utf-8")
    (b / "two" / "SKILL.md").write_text("---\nname: two\n---\n", encoding="utf-8")
    root_b, names_b = imp.find_skill_layout(b)
    ck("★ 形态 b：子目录各自带 SKILL.md → 重组清单", root_b is None and names_b == ["one", "two"])
    c = tmp / "lay-c"; c.mkdir()
    (c / "SKILL.md").write_text("---\nname: solo\n---\n", encoding="utf-8")
    root_c, names_c = imp.find_skill_layout(c)
    ck("★ 形态 c：root 本身是 skill", root_c == c and names_c == [])
    d = tmp / "lay-d"; d.mkdir()
    (d / "readme.md").write_text("# nothing\n", encoding="utf-8")
    ck("★ 无可识别 skill → 诚实 (None, [])", imp.find_skill_layout(d) == (None, []))

    # --- 44B. stage_upload：Market Package zip → kind=package
    SNAME = "imp39"
    src = tmp / "src"
    (src / "skills" / SNAME).mkdir(parents=True)
    (src / "skills" / SNAME / "SKILL.md").write_text(
        f"---\nname: {SNAME}\nversion: 1.0.0\n---\n# {SNAME}\n", encoding="utf-8")
    packed = pk.pack_package(src, tmp / "pkg", pid="demo-imp", name="Demo",
                             version="1.0.0", license="MIT",
                             source={"type": "github", "repo": "o/r", "ref": "d" * 40})
    pkg_zip = tmp / "pkg.zip"
    with _zf.ZipFile(pkg_zip, "w", _zf.ZIP_DEFLATED) as z:
        for p in sorted((tmp / "pkg").rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(tmp / "pkg").as_posix())
    blob = pkg_zip.read_bytes()
    pv = imp.stage_upload(_reader(blob), len(blob), name_hint="demo-imp.zip")
    ck("★ Market Package：识别为 kind=package 且预览齐",
       pv.get("ok") and pv.get("kind") == "package" and pv.get("skills") == [SNAME]
       and pv.get("packageHash") == packed["packageHash"],
       str(pv.get("error") or "")[:120])
    ck("预览带风险与兼容性报告（不装）",
       isinstance(pv.get("risk"), dict) and isinstance(pv.get("compatibility"), dict)
       and len(pv.get("stagingId") or "") == 16)

    # --- 44C. stage_upload：原始仓库 zip（形态 a）→ 就地打包 kind=import
    raw = tmp / "raw.zip"
    _mkzip(raw, [("skills/alpha/SKILL.md", "---\nname: alpha\n---\n"),
                 ("skills/alpha/tool.py", "print(1)\n"), ("README.md", "# r")])
    raw_blob = raw.read_bytes()
    pv2 = imp.stage_upload(_reader(raw_blob), len(raw_blob), name_hint="some-repo-main.zip")
    ck("★ 原始仓库 zip：自动打包为 kind=import，verify 通过",
       pv2.get("ok") and pv2.get("kind") == "import"
       and pv2.get("pid") == "import-some-repo-main" and pv2.get("skills") == ["alpha"],
       str(pv2.get("error") or "")[:120])

    # --- 44D. 无 skill 的 zip → 诚实报错
    junk = tmp / "junk.zip"
    _mkzip(junk, [("readme.md", "# hi\n")])
    junk_blob = junk.read_bytes()
    pv3 = imp.stage_upload(_reader(junk_blob), len(junk_blob), name_hint="junk.zip")
    ck("★ zip 里没有 skill → 诚实报错（不装垃圾）",
       not pv3.get("ok") and "SKILL.md" in str(pv3.get("error", "")))

    # --- 44E. zip-slip 成员 → 拒绝（防线在 unpack_zip，本层不放过）
    evil = tmp / "evil.zip"
    _mkzip(evil, [("skills/ok/SKILL.md", "---\nname: ok\n---\n"),
                  ("../evil.txt", "x")])
    evil_blob = evil.read_bytes()
    pv4 = imp.stage_upload(_reader(evil_blob), len(evil_blob), name_hint="evil.zip")
    ck("★ zip-slip 成员 → 整包拒绝", not pv4.get("ok"))

    # --- 44F. 超限 / 中断 → 诚实失败
    pv5 = imp.stage_upload(_reader(b""), imp.MAX_IMPORT_BYTES + 1, name_hint="big.zip")
    ck("★ 超过大小上限 → 直接拒绝", not pv5.get("ok"))
    pv6 = imp.stage_upload(_reader(b"short"), 1000, name_hint="cut.zip")
    ck("★ 接收中断（实收 < 声明）→ 诚实失败", not pv6.get("ok"))

    # --- 44G. commit：形状 / 未确认 / 确认安装 / 记录与可见性
    ck("★ stagingId 形状校验（非法 id 拒绝）",
       not imp.commit_import("../../evil", confirmed=True).get("ok"))
    ck("★ 不存在的暂存 id → 诚实报错",
       not imp.commit_import("0" * 16, confirmed=True).get("ok"))
    ck("★ 未经确认（confirmed=False）→ 拒绝安装",
       not imp.commit_import(pv["stagingId"], confirmed=False).get("ok"))
    r = imp.commit_import(pv["stagingId"], confirmed=True)
    ck("★ 确认后：两阶段事务安装成功",
       r.get("ok") and SNAME in r.get("added", []),
       str(r.get("error") or r.get("failed"))[:120])
    ck("skill 真的落位 SKILLS_DIR", (core.SKILLS_DIR / SNAME / "SKILL.md").is_file())
    own = core.load_ownership()["skills"].get(SNAME) or {}
    ck("★ ownership 带上导入包的 packageHash（装的是哪份可审计）",
       own.get("packageHash") == packed["packageHash"], str(own)[:100])
    meta = imp.list_imports().get(pv["pid"]) or {}
    ck("★ imports.json 记录显示名与来源 zip",
       meta.get("name") == "demo-imp" and meta.get("via") == "import", str(meta)[:120])
    plan = core.plugin_uninstall_plan(pv["pid"], purpose="ui")
    ck("★ 卸载通路：所有权回退覆盖导入包（removable 非空）",
       plan.get("removable") == [SNAME], str(plan)[:120])
    st = core.build_state()
    card = next((c for c in st.get("community", []) if c.get("rawName") == pv["pid"]), None)
    ck("★ build_state 社区分组出 via=import 卡片，显示名 = zip 名",
       card is not None and card.get("via") == "import"
       and card.get("name") == "demo-imp" and card.get("installed") is True,
       str(card)[:120] if card else "no-card")

    # --- 44H. 收录上下文：pinned 比对（严格链不回退）
    reg_ok = {"plugins": [{"repo": "owner/good", "packageHash": packed["packageHash"]}]}
    blob2 = pkg_zip.read_bytes()
    pv7 = imp.stage_upload(_reader(blob2), len(blob2), name_hint="demo-imp.zip",
                           repo="owner/good", registry_lookup=lambda: reg_ok)
    ck("★ 哈希与收录固定值一致 → pinned=True",
       pv7.get("ok") and pv7.get("pinned") is True, str(pv7.get("error") or "")[:120])
    reg_bad = {"plugins": [{"repo": "owner/good", "packageHash": "e" * 64}]}
    pv8 = imp.stage_upload(_reader(pkg_zip.read_bytes()), len(blob2), name_hint="demo-imp.zip",
                           repo="owner/good", registry_lookup=lambda: reg_bad)
    ck("★ 哈希与收录固定值不符 → 整包拒绝（导入不是洗白通道）",
       not pv8.get("ok") and "不是同一份" in str(pv8.get("error", "")))

    # --- 44I. 服务端端到端：上传（二进制）→ commit
    import market_server as srv
    TOKS = "selftest-import-token"
    httpd = srv.make_server(0, token=TOKS)
    PORT = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def post_raw(path, body: bytes, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=15)
        c.request("POST", path, body=body,
                  headers={"X-Local-Market-Token": TOKS, **(headers or {})})
        resp = c.getresponse()
        raw_out = resp.read()
        c.close()
        try:
            return resp.status, json.loads(raw_out)
        except ValueError:
            return resp.status, {}

    def post_json(path, body):
        return post_raw(path, json.dumps(body).encode("utf-8"),
                        {"Content-Type": "application/json"})

    try:
        raw_zip2 = tmp / "srv.zip"
        _mkzip(raw_zip2, [("skills/srv39/SKILL.md", "---\nname: srv39\n---\n")])
        up_blob = raw_zip2.read_bytes()
        stc, pvup = post_raw(
            "/api/import/upload", up_blob,
            {"Content-Type": "application/octet-stream",
             "X-Import-Name": "srv-repo-main.zip"})
        ck("★ 上传：受理并返回预览",
           stc == 200 and pvup.get("ok") and pvup.get("kind") == "import"
           and pvup.get("skills") == ["srv39"], f"{stc} {str(pvup)[:120]}")
        stc, r0 = post_json("/api/import/commit",
                            {"stagingId": pvup.get("stagingId"), "confirmed": False})
        ck("★ 提交：未经确认 → 400", stc == 400 and not r0.get("ok"))
        stc, r1 = post_json("/api/import/commit",
                            {"stagingId": pvup.get("stagingId"), "confirmed": True})
        ck("★ 提交：确认后 200 且装进 SKILLS_DIR",
           stc == 200 and r1.get("ok") and (core.SKILLS_DIR / "srv39" / "SKILL.md").is_file(),
           f"{stc} {str(r1)[:120]}")
        stc, _ = post_json("/api/import/commit",
                           {"stagingId": "zz", "confirmed": True})
        ck("★ 提交：stagingId 非法 → 400", stc == 400)
    finally:
        httpd.shutdown()
        httpd.server_close()

    # 收尾：清掉本轮装出来的 skill 与所有权（imports.json 在隔离 STATE_HOME，
    # 随 _TMP 一起消失，不影响其他轮）
    for sname, pid in [(SNAME, pv["pid"]), ("alpha", pv2.get("pid")), ("srv39", "import-srv-repo-main")]:
        shutil.rmtree(core.SKILLS_DIR / sname, ignore_errors=True)
        wm.ownership.forget_owner([sname])
    shutil.rmtree(tmp, ignore_errors=True)
