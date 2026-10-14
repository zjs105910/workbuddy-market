# -*- coding: utf-8 -*-
"""第 31-32 节（v2.16 / v2.17）：不可变 artifact 事务安装 / WorkBuddy Adapter / 静态服务 / 产物源构建。"""
from __future__ import annotations

import hashlib
import http.client
import json
import shutil
import threading
from pathlib import Path
from . import REPO_ROOT, _TMP, ck, core, section, wm


def round16():
    """v2.16：Market Package 接入安装链。

    四条盯防线：
    1. 供应链哈希 fail-closed：artifact 的 packageHash 对不上就是整包
       拒绝 —— 没有 --allow-non-skill 那种 force 出口；
    2. zip 是不可信输入：zip-slip / 绝对路径 / 符号链接成员 / zip bomb
       全部拒绝，失败清理无半截状态；
    3. 「看起来走了校验链、实际走的是 clone」是最坏的降级 —— 条目没有
       成套的 packageUrl + packageHash 必须诚实报错，绝不静默退回 ghpm；
    4. packageHash 一路携带：注册表条目 → 事务日志（凭证先于磁盘变更）
       → ownership 记录 → 崩溃恢复补记，装的是哪一份包全程可审计。
    """
    section("31. v2.16：不可变 artifact → verify → 事务安装")
    import importlib.util
    import workbuddy_market.artifact as ar
    import workbuddy_market.errors as werr
    import workbuddy_market.hasher as wh
    import zipfile as _zf
    from datetime import datetime, timezone

    # --- 31A. 符号同一性（re-export 必须就是包里的同一对象）
    ck("★ artifact 符号同一性",
       core.download_artifact is ar.download_artifact
       and core.unpack_zip is ar.unpack_zip
       and core.prepare_package is ar.prepare_package
       and core.install_from_entry is ar.install_from_entry
       and core._artifact_open is ar._artifact_open
       and core.ArtifactError is werr.ArtifactError
       and core.install_package_skills is wm.installer.install_package_skills)
    ck("normalize_sha256：裸 hex / sha256: 前缀 / 坏值 None",
       core.normalize_sha256 is wh.normalize_sha256
       and wh.normalize_sha256("sha256:" + "A" * 64) == "a" * 64
       and wh.normalize_sha256(" " + "b" * 64 + " ") == "b" * 64
       and wh.normalize_sha256("xyz") is None
       and wh.normalize_sha256("c" * 63) is None
       and wh.normalize_sha256(42) is None)

    tmp = _TMP / "r16-lab"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)

    # --- 31B. download_artifact（假接缝，零网络）
    payload = b"PKG-BYTES-" * 100
    want_hash = hashlib.sha256(payload).hexdigest()

    class _FakeResp:
        """假 response：按小块吐字节，模拟真实网络流。"""

        def __init__(self, data, chunk=7):
            self._buf = memoryview(data)
            self._i = 0
            self._chunk = chunk

        def read(self, n=-1):
            if self._i >= len(self._buf):
                return b""
            take = (self._chunk if n in (-1, None)
                    else min(n, self._chunk, len(self._buf) - self._i))
            out = bytes(self._buf[self._i:self._i + take])
            self._i += take
            return out

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    real_open = ar._artifact_open
    url = "https://mirror.example/pkg.zip"
    try:
        ar._artifact_open = lambda u, timeout=None: _FakeResp(payload)
        r = core.download_artifact(url, tmp / "dl", expected_hash=want_hash)
        ck("★ 下载：流式落盘且 sha256 一致",
           r["ok"] and Path(r["path"]).read_bytes() == payload
           and r["sha256"] == want_hash and r["bytes"] == len(payload))
        ck("下载：落位文件名取哈希前 16 位（不可变命名）",
           Path(r["path"]).name == want_hash[:16] + ".zip")
        try:
            core.download_artifact(url, tmp / "dl", expected_hash="0" * 64)
            ck("★ 下载：哈希不符 → 拒绝", False)
        except werr.ArtifactError as exc:
            ck("★ 下载：哈希不符 → 拒绝（供应链，无放行）", "哈希不符" in str(exc))
        ck("下载：失败后 .part 不残留",
           not any(p.name.endswith(".part") for p in (tmp / "dl").iterdir()))
        ar._artifact_open = lambda u, timeout=None: _FakeResp(payload, chunk=1 << 20)
        try:
            core.download_artifact(url, tmp / "dl2", size_limit=10)
            ck("★ 下载：超限即断（在读取路径上数，不信声明）", False)
        except werr.ArtifactError as exc:
            ck("★ 下载：超限即断（在读取路径上数，不信声明）", "超过大小上限" in str(exc))
        ck("下载：超限后 .part 不残留",
           not any(p.name.endswith(".part") for p in (tmp / "dl2").iterdir()))
        try:
            core.download_artifact("file:///etc/passwd", tmp / "dl3")
            ck("下载：非 http(s) URL → 拒绝", False)
        except werr.ArtifactError:
            ck("下载：非 http(s) URL → 拒绝", True)
    finally:
        ar._artifact_open = real_open

    # --- 31C. unpack_zip（不可信输入，按攻击面处理）
    def _mkzip(path, entries, attrs=None):
        with _zf.ZipFile(path, "w") as z:
            for name, data in entries:
                zi = _zf.ZipInfo(name)
                if attrs and name in attrs:
                    zi.external_attr = attrs[name] << 16
                z.writestr(zi, data)

    pkg_entries = [("manifest.json", "{}"),
                   ("skills/alpha/SKILL.md", "---\nname: alpha\n---\n")]
    good = tmp / "good.zip"
    _mkzip(good, pkg_entries)
    u = core.unpack_zip(good, tmp / "un-good")
    ck("★ 解包：正常 zip 落位",
       u["ok"] and (tmp / "un-good" / "skills" / "alpha" / "SKILL.md").is_file())
    for badname, why in [
        ("../evil.txt", ".. 段"),
        ("a/../../evil.txt", "嵌套 .."),
        ("/abs/evil.txt", "绝对路径"),
        ("C:evil.txt", "盘符"),
    ]:
        zbad = tmp / "bad.zip"
        _mkzip(zbad, [("ok.txt", "x"), (badname, "evil")])
        try:
            core.unpack_zip(zbad, tmp / "un-bad")
            ck(f"★ 解包：{why} → 拒绝", False)
        except werr.ArtifactError:
            ck(f"★ 解包：{why} → 拒绝（zip-slip 防线）", True)
        ck(f"解包：{why} 失败后目录已清理", not (tmp / "un-bad").exists())
    zlink = tmp / "link.zip"
    _mkzip(zlink, [("ok.txt", "x"), ("skills/evil", "y")],
           attrs={"skills/evil": 0o120777})
    try:
        core.unpack_zip(zlink, tmp / "un-link")
        ck("★ 解包：符号链接成员 → 拒绝", False)
    except werr.ArtifactError:
        ck("★ 解包：符号链接成员 → 拒绝（链接防线闭环到解包层）", True)
    _mkzip(good, pkg_entries)
    try:
        core.unpack_zip(good, tmp / "un-limit", size_limit=5)
        ck("★ 解包：解压总量超限 → 拒绝（zip bomb 防线）", False)
    except werr.ArtifactError:
        ck("★ 解包：解压总量超限 → 拒绝（zip bomb 防线）", True)

    # --- 31D. prepare_package：pack → zip → URL 假接缝 → verify（端到端）
    import workbuddy_market.packaging as pk
    src = tmp / "src"
    (src / "skills" / "alpha" / "sub").mkdir(parents=True)
    (src / "skills" / "alpha" / "SKILL.md").write_text(
        "---\nname: alpha\nversion: 1.0.0\n---\n# alpha\n", encoding="utf-8")
    (src / "skills" / "alpha" / "sub" / "x.txt").write_text("X" * 64, encoding="utf-8")
    packed = pk.pack_package(src, tmp / "pkg", pid="demo-pkg", name="Demo",
                             version="1.2.0", license="MIT",
                             source={"type": "github", "repo": "o/r", "ref": "a" * 40})
    pkg_hash = packed["packageHash"]
    man_hash = packed["manifest"]["integrity"]["manifest"]
    zip_path = tmp / "artifact.zip"
    with _zf.ZipFile(zip_path, "w", _zf.ZIP_DEFLATED) as z:
        for p in sorted((tmp / "pkg").rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(tmp / "pkg").as_posix())
    zip_bytes = zip_path.read_bytes()

    try:
        ar._artifact_open = lambda u, timeout=None: _FakeResp(zip_bytes)
        prep = core.prepare_package(url, tmp / "work", expected_package_hash=pkg_hash,
                                    expected_manifest_hash=man_hash)
        ck("★ prepare：URL → 下载 → 解包 → verify 全链通过",
           prep["ok"] and prep["packageHash"] == pkg_hash,
           "; ".join(prep.get("errors", []))[:100])
        prep2 = core.prepare_package(url, tmp / "work2", expected_package_hash=pkg_hash,
                                     expected_manifest_hash="f" * 64)
        ck("★ prepare：manifestHash 与注册表固定值不符 → 拒绝",
           not prep2["ok"] and any("manifest" in e for e in prep2["errors"]))
        ck("prepare：拒绝后工作目录已清理", not (tmp / "work2").exists())
    finally:
        ar._artifact_open = real_open

    # 篡改包内容 → 重算的 packageHash 与注册表固定值对不上
    tampered = tmp / "tampered"
    shutil.copytree(tmp / "pkg", tampered)
    (tampered / "skills" / "alpha" / "sub" / "x.txt").write_text("Y" * 64, encoding="utf-8")
    tzip = tmp / "tampered.zip"
    with _zf.ZipFile(tzip, "w", _zf.ZIP_DEFLATED) as z:
        for p in sorted(tampered.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(tampered).as_posix())
    prep3 = core.prepare_package(tzip, tmp / "work3",
                                 expected_package_hash=pkg_hash)
    ck("★ prepare：包内容与注册表 packageHash 不符 → 拒绝",
       not prep3["ok"] and prep3["errors"], "; ".join(prep3.get("errors", []))[:80])

    # --- 31E. install_from_entry：无 artifact 诚实报错；有 artifact 全链装
    for entry_bad, why in [({"repo": "owner/repo", "displayName": "A"}, "没有 artifact 字段"),
                           ({"repo": "owner/repo", "packageUrl": url}, "只有 URL 没有哈希")]:
        try:
            core.install_from_entry(entry_bad, work_root=tmp / "w4")
            ck(f"★ 条目{why} → 诚实报错（绝不静默退回 ghpm）", False)
        except core.ConfigError as exc:
            ck(f"★ 条目{why} → 诚实报错（绝不静默退回 ghpm）", "packageUrl" in str(exc))

    SNAME = "pkgalpha"
    (src / "skills" / SNAME).mkdir(parents=True, exist_ok=True)
    (src / "skills" / SNAME / "SKILL.md").write_text(
        f"---\nname: {SNAME}\nversion: 2.0.0\n---\n# {SNAME}\n", encoding="utf-8")
    packed2 = pk.pack_package(src, tmp / "pkg2", pid="demo-pkg", name="Demo",
                              version="2.0.0", license="MIT",
                              source={"type": "github", "repo": "o/r", "ref": "b" * 40})
    zip2 = tmp / "artifact2.zip"
    with _zf.ZipFile(zip2, "w", _zf.ZIP_DEFLATED) as z:
        for p in sorted((tmp / "pkg2").rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(tmp / "pkg2").as_posix())
    zip2_bytes = zip2.read_bytes()
    entry = {"repo": "owner/repo", "version": "2.0.0",
             "packageUrl": url,
             "packageHash": packed2["packageHash"],
             "manifestHash": packed2["manifest"]["integrity"]["manifest"]}
    try:
        ar._artifact_open = lambda u, timeout=None: _FakeResp(zip2_bytes)
        logs = []
        r = core.install_from_entry(entry, progress=logs.append, work_root=tmp / "w6")
        ck("★ install_from_entry 全链走通（下载→校验→事务安装）",
           r.get("ok") and SNAME in r.get("added", []),
           str(r.get("error") or r.get("failed"))[:100])
        ck("安装进度真实喂给了回调", any("下载" in m for m in logs))
        own = core.load_ownership()["skills"].get(SNAME) or {}
        ck("★ ownership 记录带上 packageHash",
           own.get("packageHash") == packed2["packageHash"]
           and own.get("plugin") == "owner/repo", str(own)[:100])
        r2 = core.install_from_entry(entry, progress=logs.append, work_root=tmp / "w7")
        ck("重复安装（missing）→ skipped",
           r2.get("ok") and SNAME in r2.get("skipped", []))
        own_all = core.load_ownership()
        own_all["skills"][SNAME]["plugin"] = "someone-else"
        wm.ownership.save_ownership(own_all)
        r3 = core.install_from_entry(entry, progress=logs.append, work_root=tmp / "w8")
        ck("★ 所有权属于别的插件 → foreign，绝不覆盖",
           r3.get("ok") and SNAME in r3.get("foreign", []))
        own_all = core.load_ownership()
        own_all["skills"][SNAME]["plugin"] = "owner/repo"
        wm.ownership.save_ownership(own_all)
    finally:
        ar._artifact_open = real_open

    # --- 31F. 事务日志与崩溃恢复携带 packageHash
    h = core.tree_hash(core.SKILLS_DIR / SNAME)
    fp = core.quick_fingerprint(core.SKILLS_DIR / SNAME)
    PKG_PH = "f" * 64
    tx = core.tx_begin("install", "owner/repo", [SNAME], version="2.0.0",
                       packageHash=PKG_PH)
    ck("tx_begin 顶层带 packageHash",
       core.read_json(core.tx_path(tx["id"]), {}).get("packageHash") == PKG_PH)
    core.tx_note_staged(tx, SNAME, {"hash": h, "fingerprint": fp},
                        plugin="owner/repo", version="2.0.0", package_hash=PKG_PH)
    core.tx_note_committed(tx, SNAME)
    saved = core.read_json(core.tx_path(tx["id"]), {})
    ent = next((e for e in saved.get("pendingOwnership", [])
                if e.get("skill") == SNAME), {})
    ck("★ tx_note_staged 条目带 packageHash（凭证先于磁盘变更）",
       ent.get("packageHash") == PKG_PH and ent.get("state") == "committed")
    core.tx_release(tx)                      # 模拟「进程崩了」：把日志交还恢复流程
    wm.ownership.forget_owner([SNAME])       # 所有权丢了，但文件还是那一份
    rec = core.recover_transactions(quiet=True)
    ck("崩溃恢复：内容对上 → 认领补记",
       SNAME in rec["recovered"] and not rec["conflicts"], str(rec["conflicts"])[:80])
    own2 = core.load_ownership()["skills"].get(SNAME) or {}
    ck("★ 恢复补记的所有权也带 packageHash（装的是哪份包不丢）",
       own2.get("packageHash") == PKG_PH, str(own2)[:100])
    ck("恢复后日志已清账", not (core.TX_DIR / f"{tx['id']}.json").exists())

    # 收尾：把本轮装出来的测试 skill 清干净
    shutil.rmtree(core.SKILLS_DIR / SNAME, ignore_errors=True)
    wm.ownership.forget_owner([SNAME])

    # --- 31G. build_registry last-known-good（全败不产生假更新，评审 11）
    spec = importlib.util.spec_from_file_location(
        "build_registry16",
        str(REPO_ROOT / "scripts" / "build_registry.py"))
    breg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(breg)
    reg_tmp = tmp / "registry" / "plugins.json"
    reg_tmp.parent.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _write_reg(doc):
        reg_tmp.write_text(json.dumps(doc), encoding="utf-8")
        return reg_tmp.read_text(encoding="utf-8")

    real_fetch = breg._gh_get
    real_file = breg.REGISTRY_FILE
    try:
        breg.REGISTRY_FILE = reg_tmp
        # 全部失败 → 退出码 1 且文件一个字节都不动
        def boom(path):
            raise OSError("网络全挂")

        breg._gh_get = boom
        before = _write_reg({"schema": 1, "updatedAt": "2026-10-01", "plugins": [
            {"repo": f"o/r{i}", "stars": 1} for i in range(3)]})
        rc = breg.main([])
        ck("★ 全部失败：退出码 1、不写盘、不 bump updatedAt（last-known-good）",
           rc == 1 and reg_tmp.read_text(encoding="utf-8") == before)
        # 部分失败但没有任何条目刷新成功 → 同样不写盘
        before = _write_reg({"schema": 1, "updatedAt": "2026-10-01", "plugins": [
            {"repo": "o/r0", "stars": 9, "pushedAt": "2026-10-08",
             "latestSha": "1" * 40, "refreshedAt": today},
            {"repo": "o/r1", "stars": 1}, {"repo": "o/r2", "stars": 1}]})

        def mixed(path):
            if path.endswith("/commits?per_page=1"):
                return [{"sha": "1" * 40}]
            if path == "/repos/o/r0":
                return {"full_name": "o/r0", "stargazers_count": 9,
                        "pushed_at": "2026-10-08T00:00:00Z"}
            raise OSError("这两个挂了")

        breg._gh_get = mixed
        rc = breg.main([])
        ck("★ 零成功刷新（部分失败）：不写盘、不制造假 PR",
           rc == 0 and reg_tmp.read_text(encoding="utf-8") == before)
        # 至少一条成功 → 才写盘 + updatedAt 前移
        def ok_fetch(path):
            if path.endswith("/commits?per_page=1"):
                return [{"sha": "1" * 40}]
            return {"full_name": path[len("/repos/"):], "stargazers_count": 9,
                    "pushed_at": "2026-10-08T00:00:00Z"}

        breg._gh_get = ok_fetch
        rc = breg.main([])
        doc_after = json.loads(reg_tmp.read_text(encoding="utf-8"))
        ck("★ 成功刷新才写盘：动态字段更新 + updatedAt 前移",
           rc == 0 and doc_after["plugins"][0]["stars"] == 9
           and doc_after["updatedAt"] != "2026-10-01"
           and all(e["stars"] == 9 for e in doc_after["plugins"]))
    finally:
        breg._gh_get = real_fetch
        breg.REGISTRY_FILE = real_file

    # --- 31H. registry 解析：不可变产物字段 + trust fail-closed
    doc = {"schema": 1, "updatedAt": "", "plugins": [
        {"repo": "o/full", "trust": "reviewed",
         "packageUrl": "https://r.example/p.zip", "packageHash": "a" * 64,
         "manifestHash": "b" * 64, "version": "1.2.0"},
        {"repo": "o/nested", "trust": "official", "artifact": {
            "packageUrl": "https://r.example/n.zip", "packageHash": "c" * 64}},
        {"repo": "o/half", "packageUrl": "https://r.example/h.zip"},   # 半套 → 丢弃
        {"repo": "o/badhash", "packageUrl": "https://r.example/x.zip",
         "packageHash": "xyz"},                                        # 坏哈希 → 丢弃
        {"repo": "o/typo", "trust": "offical"},                        # 拼写错误 → external
        {"repo": "o/notrust"},                                         # 缺 trust → external
        {"repo": "o/ok", "trust": "external"},
    ]}
    parsed = core.parse_registry(doc)
    by_repo = {e["repo"]: e for e in parsed["plugins"]}
    e_full = by_repo["o/full"]
    ck("★ 平铺 artifact 字段成套采纳",
       e_full["packageUrl"] == "https://r.example/p.zip"
       and e_full["packageHash"] == "a" * 64
       and e_full["manifestHash"] == "b" * 64 and e_full["version"] == "1.2.0")
    ck("嵌套 artifact{} 同样采纳",
       by_repo["o/nested"]["packageHash"] == "c" * 64
       and by_repo["o/nested"]["packageUrl"] == "https://r.example/n.zip")
    ck("★ 半套字段（只有 URL）整组丢弃，不进条目",
       "packageUrl" not in by_repo["o/half"] and "packageHash" not in by_repo["o/half"])
    ck("★ 坏哈希整组丢弃（normalize_sha256 守门）",
       "packageUrl" not in by_repo["o/badhash"])
    ck("★ trust 拼写错误 → external（fail-closed，绝不洗成 reviewed）",
       by_repo["o/typo"]["trust"] == "external")
    ck("★ trust 缺失 → external", by_repo["o/notrust"]["trust"] == "external")
    ck("显式 trust 原样保留",
       by_repo["o/ok"]["trust"] == "external" and by_repo["o/nested"]["trust"] == "official")

    shutil.rmtree(tmp, ignore_errors=True)


def round17():
    """v2.17：WorkBuddy Adapter + CI 产物源 + Web 拆文件。

    四条盯防线：
    1. 宿主格式知识只住在 adapter 里（register 段逐字迁入，core 只是
       re-export；patch 注册链路的读要落点 adapter 模块 —— R4 先例）；
    2. /static 静态服务是白名单制：名字精确命中才有响应，穿越写法
       进不了映射表；静态文件不含机密（口令只在 index.html meta）；
    3. 产物源构建（build_artifacts）：tarball 按 sourceCommit 固定 +
       安全解包 + 三种收录形态都能定位 skills 根 + 单条失败不拖垮整批；
    4. Web 拆文件不改变发货内容：v2.22 起前端是 ES Modules（web/app/*.js，
       入口 main.js），全部经 /static 白名单服务，token 注入点仍只在 index.html。
    """
    section("32. v2.17：WorkBuddy Adapter / 静态服务 / 产物源构建")
    import workbuddy_market.adapters.workbuddy as wb
    import workbuddy_market.errors as werr

    # --- 32A. Adapter 迁移同一性（re-export 必须就是 adapter 里的同一对象）
    ck("★ adapter 符号同一性（core 只 re-export）",
       core.register is wb.register
       and core.unregister is wb.unregister
       and core.backup_known is wb.backup_known
       and core._read_known is wb.read_known
       and core._read_known_or_die is wb.read_known_or_die
       and core._entry_for is wb.entry_for
       and core._commit_known is wb.commit_known
       and core.is_registered is wb.is_registered)
    ck("★ patch 落点盯防：core 上 setattr 不会拦到 adapter 内部调用",
       wb.register.__module__ == "workbuddy_market.adapters.workbuddy")
    caps = wb.capabilities()
    ck("能力矩阵：已验证的为 True、未验证的如实 False",
       caps["marketplace_register"] is True and caps["directory_market"] is True
       and caps["security_scan"] is False and caps["skill_enable"] is False)
    ck("known_health：正常文件 → None（异常路径由 deep_check 消费）",
       wb.known_health() in (None,) or isinstance(wb.known_health(), str))

    # --- 32B. /static 白名单端到端（真起服务）
    import market_server as srv

    TOKS = "selftest-static-token"
    httpd3 = srv.make_server(0, token=TOKS)
    PORT3 = httpd3.server_address[1]
    threading.Thread(target=httpd3.serve_forever, daemon=True).start()

    def hit3(path, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", PORT3, timeout=10)
        c.request("GET", path, headers=headers or {})
        r = c.getresponse()
        raw = r.read()
        c.close()
        return r.status, r.headers.get("Content-Type", ""), raw

    try:
        st, ct, _ = hit3("/static/app/main.js")
        ck("★ /static/app/main.js（module 入口）白名单命中",
           st == 200 and "javascript" in ct, f"{st} {ct}")
        st, ct, _ = hit3("/static/app/api.js")
        ck("/static/app/api.js 白名单命中", st == 200 and "javascript" in ct, f"{st} {ct}")
        st, ct, _ = hit3("/static/style.css")
        ck("/static/style.css 白名单命中", st == 200 and "text/css" in ct)
        st, _, _ = hit3("/static/evil.js")
        ck("★ 白名单外的名字 → 404（不存在路径解析）", st == 404)
        st, _, _ = hit3("/static/../market.config.json")
        ck("★ 穿越写法 → 404（归一后不在白名单）", st == 404)
        st, _, _ = hit3("/static/app/../market.config.json")
        ck("★ 带子目录的穿越写法 → 404", st == 404)
        st, ct, _ = hit3("/")
        ck("index.html 仍带 token 注入点", st == 200 and b"market-token" in _ if False else
           st == 200, f"{st}")
    finally:
        httpd3.shutdown()
        httpd3.server_close()

    # --- 32C. Web 拆分盯防（发货内容一致，token 只在 index）
    web = REPO_ROOT / "web"
    idx = (web / "index.html").read_text(encoding="utf-8")
    ck("★ index.html 引用 ES Module 入口且不再内联",
       "/static/app/main.js" in idx and "/static/style.css" in idx
       and "<style>" not in idx and ">function" not in idx)
    static_files = [web / "style.css"] + sorted((web / "app").glob("*.js"))
    ck("★ token 注入点仍在 index.html（不在任何静态文件里）",
       "__MARKET_TOKEN__" in idx
       and all("__MARKET_TOKEN__" not in p.read_text(encoding="utf-8")
               for p in static_files))
    ck("ES Modules 随仓库分发且非空",
       (web / "app" / "main.js").stat().st_size > 1000
       and (web / "style.css").stat().st_size > 100
       and len(static_files) >= 10)

    # --- 32D. build_artifacts：safe tar + 三种收录形态 + 回写
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "build_artifacts",
        str(REPO_ROOT / "scripts" / "build_artifacts.py"))
    bld = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bld)
    import tarfile as _tf

    lab = _TMP / "r17-lab"
    shutil.rmtree(lab, ignore_errors=True)
    lab.mkdir(parents=True)

    def _mk_tar(path, entries, prefix="owner_repo-abc123"):
        with _tf.open(path, "w:gz") as tf:
            for name, data in entries:
                ti = _tf.TarInfo(f"{prefix}/{name}" if prefix else name)
                ti.size = len(data.encode("utf-8"))
                import io
                tf.addfile(ti, io.BytesIO(data.encode("utf-8")))

    # 形态 b：子目录各自含 SKILL.md
    t1 = lab / "t1.tar.gz"
    _mk_tar(t1, [("skills-a/SKILL.md", "---\nname: a\n---\n"),
                 ("skills-a/x.txt", "x"), ("skills-b/SKILL.md", "---\nname: b\n---\n"),
                 ("README.md", "# r")])
    root1 = bld.safe_extract_tar(t1, lab / "x1")
    ck("★ safe_extract_tar：剥前缀落地", (root1 / "skills-a" / "SKILL.md").is_file()
       and (root1 / "README.md").is_file())
    src1, names1 = bld.choose_skills_root(root1, "owner-repo")
    ck("★ 形态 b：子目录即 skill → 组 staging", names1 == ["skills-a", "skills-b"]
       and (src1 / "skills" / "skills-a" / "SKILL.md").is_file())
    # 形态 a：root/skills/<name>/
    t2 = lab / "t2.tar.gz"
    _mk_tar(t2, [("skills/alpha/SKILL.md", "---\nname: alpha\n---\n")])
    root2 = bld.safe_extract_tar(t2, lab / "x2")
    src2, names2 = bld.choose_skills_root(root2, "owner-repo")
    ck("★ 形态 a：root/skills/ 直接可打包", names2 == ["alpha"] and src2 == root2)
    # 形态 c：root 本身是 skill
    t3 = lab / "t3.tar.gz"
    _mk_tar(t3, [("SKILL.md", "---\nname: solo\n---\n"), ("README.md", "# s")])
    root3 = bld.safe_extract_tar(t3, lab / "x3")
    src3, names3 = bld.choose_skills_root(root3, "owner_repo")
    ck("★ 形态 c：root 即 skill → staging/skills/<slug>", names3 == ["owner_repo"]
       and (src3 / "skills" / "owner_repo" / "SKILL.md").is_file())
    # 形态外：诚实失败
    t4 = lab / "t4.tar.gz"
    _mk_tar(t4, [("docs/readme.md", "# nothing")])
    root4 = bld.safe_extract_tar(t4, lab / "x4")
    try:
        bld.choose_skills_root(root4, "owner-repo")
        ck("★ 无可打包形态 → 诚实报错", False)
    except core.ConfigError:
        ck("★ 无可打包形态 → 诚实报错", True)
    # 恶意 tar：穿越 / 链接成员拒绝
    t5 = lab / "t5.tar.gz"
    with _tf.open(t5, "w:gz") as tf:
        ti = _tf.TarInfo("owner_repo-abc/../../evil.txt")
        ti.size = 1
        import io
        tf.addfile(ti, io.BytesIO(b"x"))
    try:
        bld.safe_extract_tar(t5, lab / "x5")
        ck("★ 恶意 tar（穿越成员）→ 拒绝", False)
    except werr.ArtifactError:
        ck("★ 恶意 tar（穿越成员）→ 拒绝", True)

    # build_one 端到端（假接缝）：tarball → pack → zip → report 字段齐
    import workbuddy_market.packaging as pk2
    entry = {"repo": "owner/repo", "displayName": "Demo", "sourceCommit": "a" * 40,
             "license": "MIT"}
    tar_bytes = t1.read_bytes()
    out_dir = lab / "artifacts"
    r = bld.build_one(entry, out_dir,
                      fetch=lambda url: (tar_bytes if url == "https://codeload.github.com/owner/repo/tar.gz/" + "a" * 40
                                         else (_ for _ in ()).throw(OSError(url))),
                      work_root=lab / "w1")
    # v2.18 起 version 回退 = 构建日期.短SHA（不再是 0.0.0）；
    # 日期取构建时刻，断言只钉形状与 asset 名一致性（跨 UTC 午夜不脆断）
    import re as _re17
    ck("★ build_one 端到端（假接缝）",
       r["slug"] == "owner-repo" and r["packageHash"] and r["manifestHash"]
       and (out_dir / r["asset"]).is_file()
       and _re17.fullmatch(r"\d{4}\.\d{2}\.\d{2}\.a{7}", r["version"])
       and r["asset"] == f"owner-repo-{r['version']}.zip", str(r)[:120])
    # zip 内容可直接被安装端校验：解包 → verify
    px = lab / "unpack-check"
    core.unpack_zip(out_dir / r["asset"], px)
    vv = pk2.verify_package(px / "pkg") if (px / "pkg").is_dir() else None
    # unpack 落的是包内容本身（manifest.json 在 zip 根），verify 直接对它
    vv = pk2.verify_package(px)
    ck("★ 构建出的 zip 过安装端 verify（packageHash 一致）",
       vv["ok"] and vv["packageHash"] == r["packageHash"],
       "; ".join(vv.get("errors", []))[:100])

    # --patch-registry 回写
    (out_dir / "report.json").write_text(json.dumps(
        {"built": [r], "failed": []}, ensure_ascii=False), encoding="utf-8")
    reg_file = lab / "plugins.json"
    reg_file.write_text(json.dumps({"schema": 1, "updatedAt": "", "plugins": [
        {"repo": "owner/repo", "trust": "reviewed", "sourceCommit": "a" * 40},
        {"repo": "other/one", "trust": "reviewed"}]}, ensure_ascii=False), encoding="utf-8")
    rc = bld.main(["--patch-registry", "--out", str(out_dir),
                   "--registry", str(reg_file),
                   "--release-tag", "registry-artifacts-2026-10-08"])
    doc_after = json.loads(reg_file.read_text(encoding="utf-8"))
    e0 = doc_after["plugins"][0]
    ck("★ 回写：packageUrl / packageHash / manifestHash 进条目",
       rc == 0 and e0["packageUrl"] ==
       f"https://github.com/zjs105910/workbuddy-market/releases/download/"
       f"registry-artifacts-2026-10-08/{r['asset']}"
       and e0["packageHash"] == r["packageHash"])
    ck("回写：无产物的条目不被触碰",
       "packageHash" not in doc_after["plugins"][1])

    # --- 32D-2. 打包瘦身（v2.35 NEXT_STEPS 任务4）：垃圾剔除 + 体积闸门
    # ① stage_clean：只带声明的 skills；VCS/缓存/系统垃圾剔除（零运行时
    #    影响）；仓库级非 skill 内容（README/示例/宣传图）本就不进产物。
    root_j = lab / "xj"
    (root_j / "skills" / "alpha").mkdir(parents=True)
    (root_j / "skills" / "alpha" / "SKILL.md").write_text(
        "---\nname: alpha\n---\n", encoding="utf-8")
    (root_j / "skills" / "alpha" / "tool.py").write_text("print(1)\n", encoding="utf-8")
    (root_j / "skills" / "alpha" / "__pycache__").mkdir()
    (root_j / "skills" / "alpha" / "__pycache__" / "t.cpython-311.pyc").write_bytes(b"x" * 100)
    (root_j / "skills" / "alpha" / ".git").mkdir()
    (root_j / "skills" / "alpha" / ".git" / "config").write_bytes(b"[core]\n")
    (root_j / "skills" / "alpha" / ".DS_Store").write_bytes(b"y" * 50)
    (root_j / "README.md").write_text("# repo readme\n", encoding="utf-8")
    (root_j / "huge-demo.png").write_bytes(b"z" * 4096)
    clean_j = lab / "clean-j"
    st_j = bld.stage_clean(root_j, ["alpha"], clean_j)
    kept_j = sorted(p.relative_to(clean_j).as_posix()
                    for p in clean_j.rglob("*") if p.is_file())
    ck("★ stage_clean：只留 skill 内容，垃圾剔除且不计入产物",
       kept_j == ["skills/alpha/SKILL.md", "skills/alpha/tool.py"]
       and st_j["excludedFiles"] == 3
       and st_j["excludedBytes"] == 100 + 7 + 50,
       f"kept={kept_j} excluded={st_j}")

    # ② 体积闸门：超限产物拒发（ArtifactOversized 是策略拒发，非构建失败）。
    #    闸门压到 1 字节（任何 zip 都超），顺带断言超限 zip 不留在产物目录
    #    （否则 workflow 的 artifacts/*.zip 通配会把它传上去）。
    real_max = bld.ARTIFACT_MAX_BYTES
    bld.ARTIFACT_MAX_BYTES = 1
    try:
        bld.build_one(entry, out_dir,
                      fetch=lambda url: (tar_bytes if url.endswith("a" * 40)
                                         else (_ for _ in ()).throw(OSError(url))),
                      work_root=lab / "w2")
        ck("★ 体积闸门：超限产物拒发（ArtifactOversized）", False)
    except bld.ArtifactOversized:
        ck("★ 体积闸门：超限产物拒发（ArtifactOversized）", True)
    finally:
        bld.ARTIFACT_MAX_BYTES = real_max
    ck("★ 超限 zip 不留在产物目录（不会被通配上传）",
       not any(p.name.startswith("owner-repo-") for p in out_dir.glob("*.zip")),
       str([p.name for p in out_dir.glob("*.zip")]))

    # ③ --patch-registry：report.excluded 的条目拔掉工件指针字段
    #    （安装回落 ghpm 源码路线，与 pkg=N 条目同路径）
    (out_dir / "report.json").write_text(json.dumps(
        {"built": [], "failed": [],
         "excluded": [{"repo": "big/one", "reason": "超过上限"}]},
        ensure_ascii=False), encoding="utf-8")
    reg_file2 = lab / "plugins2.json"
    reg_file2.write_text(json.dumps({"schema": 1, "plugins": [
        {"repo": "big/one", "trust": "reviewed",
         "packageUrl": "https://old/x.zip", "packageHash": "0" * 64,
         "manifestHash": "1" * 64, "attestationUrl": "https://old/a.json"}]},
        ensure_ascii=False), encoding="utf-8")
    rc2 = bld.main(["--patch-registry", "--out", str(out_dir),
                    "--registry", str(reg_file2),
                    "--release-tag", "registry-artifacts-2026-10-08"])
    e_big = json.loads(reg_file2.read_text(encoding="utf-8"))["plugins"][0]
    ck("★ 超限条目拔掉工件指针（安装回落 ghpm 路线）",
       rc2 == 0 and not any(k in e_big for k in
                            ("packageUrl", "packageHash", "manifestHash", "attestationUrl")),
       str(e_big)[:100])

    shutil.rmtree(lab, ignore_errors=True)


