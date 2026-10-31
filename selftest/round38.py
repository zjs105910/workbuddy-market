# -*- coding: utf-8 -*-
"""第 43 节（v2.38）：离线安装 —— 本地 zip 走同一条哈希校验链。

背景（用户实测）：国内移动网络连不上 GitHub，精选市场的「安装固定产物」
第一步下载就挂了。v2.38 给这条链开了离线通道：install_from_entry 新增
package_path，用别处下载好的产物 zip 从本地导入。

四条盯防线（与在线链路同一纪律，离线 ≠ 免检）：
1. 供应链哈希一分不减：离线包仍必须与注册表钉死的 packageHash 比对，
   对不上整包拒绝 —— 篡改过的 zip 在本地照样进不来；
2. 条目没有固定哈希 → 诚实报错：没有 packageHash 就无法证明本地 zip
   是审核过的那一份，绝不给「免校验」的后门；
3. 离线条目不要求 packageUrl：能离线装的判据是 packageHash 在不在，
   不是 URL 在不在（URL 本来就连不上）；
4. 服务端闸门：/api/registry/install-offline 对 zipPath 做形状预检
   （绝对路径 + 存在 + .zip），内容安全交给与在线同一条 unpack/verify
   管线；端到端真起服务验证 400 与安装闭环。
"""
from __future__ import annotations

import http.client
import json
import shutil
import threading
import time
from pathlib import Path
from . import _TMP, ck, core, section, wm


def round38():
    section("43. v2.38：离线安装（本地 zip → 同一条哈希校验链）")
    import workbuddy_market.errors as werr
    import workbuddy_market.packaging as pk
    import zipfile as _zf

    tmp = _TMP / "r38-lab"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)

    # --- 43A. 造一个可离线安装的 Market Package（与 round16 同套路）
    SNAME = "off38"
    src = tmp / "src"
    (src / "skills" / SNAME).mkdir(parents=True)
    (src / "skills" / SNAME / "SKILL.md").write_text(
        f"---\nname: {SNAME}\nversion: 3.0.0\n---\n# {SNAME}\n", encoding="utf-8")
    packed = pk.pack_package(src, tmp / "pkg", pid="demo-off", name="Demo",
                             version="3.0.0", license="MIT",
                             source={"type": "github", "repo": "o/r", "ref": "c" * 40})
    pkg_hash = packed["packageHash"]
    man_hash = packed["manifest"]["integrity"]["manifest"]
    zip_path = tmp / "offline.zip"
    with _zf.ZipFile(zip_path, "w", _zf.ZIP_DEFLATED) as z:
        for p in sorted((tmp / "pkg").rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(tmp / "pkg").as_posix())

    # 离线条目：故意**没有 packageUrl** —— 能不能离线装看的是哈希，不是 URL
    entry_off = {"repo": "owner/off", "displayName": "Offline Demo",
                 "version": "3.0.0",
                 "packageHash": pkg_hash, "manifestHash": man_hash}

    # --- 43B. 没有固定哈希 → 诚实报错（没有「免校验」的离线通道）
    for bad, why in [({"repo": "owner/off"}, "条目没有 packageHash"),
                     (dict(entry_off, packageHash="xyz"), "packageHash 是坏值")]:
        try:
            core.install_from_entry(bad, package_path=str(zip_path),
                                    work_root=tmp / "w-bad")
            ck(f"★ 离线{why} → 诚实报错", False)
        except core.ConfigError as exc:
            ck(f"★ 离线{why} → 诚实报错（离线 ≠ 免检）", "packageHash" in str(exc))
    try:
        core.install_from_entry(entry_off, package_path="   ",
                                work_root=tmp / "w-bad2")
        ck("★ 离线空路径 → 诚实报错", False)
    except core.ConfigError as exc:
        ck("★ 离线空路径 → 诚实报错", "空路径" in str(exc))

    # --- 43C. 离线全链走通：本地 zip → verify → 事务安装（零网络）
    logs = []
    r = core.install_from_entry(entry_off, package_path=str(zip_path),
                                progress=logs.append, work_root=tmp / "w-ok")
    ck("★ 离线安装全链走通（本地 zip → 校验 → 事务安装）",
       r.get("ok") and SNAME in r.get("added", []),
       str(r.get("error") or r.get("failed"))[:120])
    ck("进度如实说明「离线 / 不联网」，且没有「下载」字样",
       any("离线" in m and "不联网" in m for m in logs)
       and not any("下载" in m for m in logs),
       " | ".join(logs)[:120])
    own = core.load_ownership()["skills"].get(SNAME) or {}
    ck("★ 离线安装的 ownership 同样带上 packageHash（装的是哪份包可审计）",
       own.get("packageHash") == pkg_hash and own.get("plugin") == "owner/off",
       str(own)[:120])

    # --- 43D. 篡改过的本地 zip → 整包拒绝（离线不豁免供应链校验）
    tam = tmp / "tampered"
    shutil.copytree(tmp / "pkg", tam)
    (tam / "skills" / SNAME / "SKILL.md").write_text(
        f"---\nname: {SNAME}\nversion: 9.9.9\n---\n# evil\n", encoding="utf-8")
    tzip = tmp / "tampered.zip"
    with _zf.ZipFile(tzip, "w", _zf.ZIP_DEFLATED) as z:
        for p in sorted(tam.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(tam).as_posix())
    r2 = core.install_from_entry(entry_off, package_path=str(tzip),
                                 progress=logs.append, work_root=tmp / "w-tam")
    ck("★ 离线包哈希不符 → 整包拒绝（无放行）",
       not r2.get("ok") and any("packageHash" in e or "哈希" in e
                                for e in r2.get("errors", [])),
       "; ".join(r2.get("errors", []))[:120])

    # --- 43E. 本地路径不存在 / 不是 zip → 人话报错（prepare_package 抛
    #          ArtifactError，与在线链路的坏 zip 同一套 fail-closed）
    try:
        core.install_from_entry(entry_off, package_path=str(tmp / "nope.zip"),
                                progress=logs.append, work_root=tmp / "w-nope")
        ck("★ 离线包路径不存在 → 诚实报错", False)
    except werr.ArtifactError as exc:
        ck("★ 离线包路径不存在 → 诚实报错（不假装装好）", "解包失败" in str(exc))
    txt = tmp / "not-a-zip.txt"
    txt.write_text("hello", encoding="utf-8")
    try:
        core.install_from_entry(entry_off, package_path=str(txt),
                                progress=logs.append, work_root=tmp / "w-txt")
        ck("★ 离线包不是 zip → 诚实报错", False)
    except werr.ArtifactError:
        ck("★ 离线包不是 zip → 诚实报错", True)

    # --- 43F. 在线语义不回归：无 packageUrl 也无 package_path → 原样报错
    try:
        core.install_from_entry(entry_off, work_root=tmp / "w-url")
        ck("★ 在线链路仍要求 packageUrl（不静默降级）", False)
    except core.ConfigError as exc:
        ck("★ 在线链路仍要求 packageUrl（不静默降级）", "packageUrl" in str(exc))

    # --- 43G. 服务端端到端：/api/registry/install-offline 闸门 + 安装闭环
    import market_server as srv
    TOKS = "selftest-offline-token"
    httpd = srv.make_server(0, token=TOKS)
    PORT = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def hit(method, path, body=None):
        c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=10)
        c.request(method, path,
                  body=json.dumps(body) if body is not None else None,
                  headers={"X-Local-Market-Token": TOKS,
                           "Content-Type": "application/json"})
        resp = c.getresponse()
        raw = resp.read()
        c.close()
        try:
            return resp.status, json.loads(raw)
        except ValueError:
            return resp.status, {}

    try:
        # 形状预检：缺 zipPath / 相对路径 / 不是 zip / 不存在 → 全部 400
        st, _ = hit("POST", "/api/registry/install-offline", {"repo": "owner/off"})
        ck("★ 离线安装：缺 zipPath → 400", st == 400, str(st))
        st, body = hit("POST", "/api/registry/install-offline",
                       {"repo": "owner/off", "zipPath": "offline.zip"})
        ck("★ 离线安装：相对路径 → 400（提示要绝对路径）",
           st == 400 and "绝对路径" in str(body.get("error", "")), str(body)[:120])
        st, body = hit("POST", "/api/registry/install-offline",
                       {"repo": "owner/off", "zipPath": str(txt)})
        ck("★ 离线安装：不是 .zip → 400", st == 400, str(body)[:120])
        st, _ = hit("POST", "/api/registry/install-offline",
                    {"repo": "owner/off", "zipPath": str(tmp / "nope.zip")})
        ck("★ 离线安装：zip 不存在 → 400", st == 400, str(st))

        # 闭环：把注册表指到我们的离线条目 → 走任务线程真装进 SKILLS_DIR
        real_get_registry = core.get_registry
        try:
            core.get_registry = lambda *a, **k: {
                "schema": 1, "plugins": [entry_off], "stale": True,
                "source": "local-repo"}
            st, body = hit("POST", "/api/registry/install-offline",
                           {"repo": "owner/off", "zipPath": str(zip_path)})
            jid = body.get("jobId") if st == 200 else None
            ck("★ 离线安装：服务端受理（200 + jobId）",
               st == 200 and bool(jid), f"{st} {str(body)[:120]}")
            job = {}
            deadline = time.time() + 60
            while time.time() < deadline:
                _, job = hit("GET", f"/api/job/{jid}")
                if job.get("status") != "running":
                    break
                time.sleep(0.2)
            ck("★ 离线安装：任务完成且成功",
               job.get("ok") is True and job.get("status") == "done",
               " | ".join(job.get("lines", []))[-200:])
            ck("离线安装：任务日志有「离线」且无「下载」",
               any("离线" in ln for ln in job.get("lines", []))
               and not any("下载" in ln for ln in job.get("lines", [])))
            ck("★ 端到端：skill 真的装进了 SKILLS_DIR",
               (core.SKILLS_DIR / SNAME / "SKILL.md").is_file())
            own2 = core.load_ownership()["skills"].get(SNAME) or {}
            ck("端到端：ownership packageHash 与注册表固定值一致",
               own2.get("packageHash") == pkg_hash)
        finally:
            core.get_registry = real_get_registry
    finally:
        httpd.shutdown()
        httpd.server_close()

    # 收尾：把本轮装出来的测试 skill 清干净（round16 同款）
    shutil.rmtree(core.SKILLS_DIR / SNAME, ignore_errors=True)
    wm.ownership.forget_owner([SNAME])
    shutil.rmtree(tmp, ignore_errors=True)
