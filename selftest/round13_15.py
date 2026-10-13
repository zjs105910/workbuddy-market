# -*- coding: utf-8 -*-
"""第 28-30 节（v2.13-v2.15）：跨卷回收站 / API v1 / doctor / installer·uninstaller 迁包 / package pack·verify。"""
from __future__ import annotations

import http.client
import json
import os
import shutil
import tempfile
import threading
from pathlib import Path
from . import _ISOLATED, _raises, _TMP, ck, core, section, sk, wm, write_fake_skill, _make_link, _drop_link


def round13():
    """v2.13：跨卷回收站原子化 + API v1 版本化 + doctor 体检。

    背景（评审 P0）：WBM_HOME 与 WBM_STATE_HOME 允许在不同磁盘 ——
    shutil.move() 跨卷退化成 copy+delete，中途崩掉两边都不完整，
    不再是文档声称的「近似原子搬移」。本轮显式分两条路：
    同卷 os.rename（原子）；跨卷「staging 复制 → 结构校验 → 同卷原子
    rename 落位 → 最后才删源」，任何一步失败源目录原样保留。

    测试策略：真造跨卷（不同盘符）不可移植也不可控，所以同 selftest
    的惯例用**假接缝** —— monkeypatch ``wm.trash._same_volume`` 强制
    走跨卷路径，磁盘动作仍然是真实的（copy / 校验 / rename / 删源）。
    """
    section("28. v2.13：跨卷回收站原子化 / API v1 版本化 / doctor")
    trash = wm.trash

    # --- 28A. _same_volume 语义
    ck("同卷判定：.trash 与自身恒为同卷",
       trash._same_volume(trash.TRASH_DIR, trash.TRASH_DIR) is True)
    if os.name == "nt":
        drive = os.path.splitdrive(str(trash.TRASH_DIR))[0].casefold()
        other = "Z:" if drive != "z:" else "Y:"
        ck("跨卷判定：不同盘符必判 False（Windows splitdrive）",
           trash._same_volume(trash.TRASH_DIR,
                              Path(other + "\\wbm-selftest-nowhere")) is False)
    else:
        r = trash._same_volume(trash.TRASH_DIR, Path(tempfile.gettempdir()))
        ck("同卷判定（POSIX st_dev）：返回 bool 且不抛异常", isinstance(r, bool))

    # --- 28B. 跨卷搬移端到端（假接缝强制走跨卷路径，磁盘动作真实）
    src = core.SKILLS_DIR / "cx-vol-skill"
    write_fake_skill(core.SKILLS_DIR, "cx-vol-skill", "1.0.0", "跨卷",
                     {"a.txt": "A" * 100, "sub/b.txt": "B" * 50})
    real_same = trash._same_volume
    trash._same_volume = lambda a, b: False
    dst = None
    try:
        dst = trash.move_to_trash(src, "selftest-cross")
        ck("★ 跨卷搬移：目标落位且内容完整（含子目录）",
           dst is not None and (dst / "SKILL.md").is_file()
           and (dst / "a.txt").read_text(encoding="utf-8") == "A" * 100
           and (dst / "sub" / "b.txt").read_text(encoding="utf-8") == "B" * 50,
           str(dst))
        ck("★ 跨卷搬移：源已删除", not src.exists())
        ck("★ 跨卷搬移：无 .partial 残留",
           dst is not None
           and not dst.with_name(dst.name + ".partial").exists())
        ck("★ 跨卷搬移：已如实登记进回收站索引",
           dst is not None and dst.name in trash._load_trash_index()["items"])
    finally:
        trash._same_volume = real_same
        if dst is not None:                          # 收尾：不留垃圾
            shutil.rmtree(dst, ignore_errors=True)
            idx = trash._load_trash_index()
            idx["items"].pop(dst.name, None)
            trash._save_trash_index(idx)

    # --- 28C. 跨卷校验失败 → 源不动、无残留、如实返回 None
    write_fake_skill(core.SKILLS_DIR, "cx-vol-skill", "1.0.0", "跨卷",
                     {"a.txt": "A" * 100})
    real_verify = trash._verify_tree_copy

    def _verify_boom(a, b):
        raise OSError("selftest 注入：结构校验失败")

    trash._same_volume = lambda a, b: False
    trash._verify_tree_copy = _verify_boom
    try:
        dst2 = trash.move_to_trash(src, "selftest-xfail")
        ck("★ 跨卷校验失败 → 返回 None（调用方知道没搬成）", dst2 is None)
        ck("★ 源目录原样保留", (src / "SKILL.md").is_file()
           and (src / "a.txt").read_text(encoding="utf-8") == "A" * 100)
        ck("★ .partial 暂存已清理",
           not any(p.name.endswith(".partial") for p in trash.TRASH_DIR.iterdir()))
    finally:
        trash._verify_tree_copy = real_verify
        trash._same_volume = real_same
        shutil.rmtree(src, ignore_errors=True)       # 收尾

    # --- 28D. 重解析点拒绝跨卷搬移（copytree 无法保真复制 junction）
    if _make_link(core.SKILLS_DIR / "alpha", core.SKILLS_DIR / "cx-vol-link"):
        trash._same_volume = lambda a, b: False
        try:
            dst3 = trash.move_to_trash(core.SKILLS_DIR / "cx-vol-link", "selftest-link")
            ck("★ 重解析点条目跨卷搬移被拒绝（源保留）",
               dst3 is None and (core.SKILLS_DIR / "cx-vol-link").exists())
        finally:
            trash._same_volume = real_same
            _drop_link(core.SKILLS_DIR / "cx-vol-link")
    else:
        sk("重解析点条目跨卷搬移被拒绝",
           "本环境建不出 junction / symlink（无管理员或宿主拦截）")

    # --- 28E. API v1 版本化：归一化语义 + 端到端等价
    import market_server as srv                      # noqa: E402

    ck("归一化：/api/v1/state → /api/state",
       srv._normalize_api_path("/api/v1/state") == "/api/state")
    ck("归一化：带参数路由 /api/v1/job/<id>/cancel",
       srv._normalize_api_path("/api/v1/job/j1/cancel") == "/api/job/j1/cancel")
    ck("归一化：裸 /api/* 不受影响",
       srv._normalize_api_path("/api/state") == "/api/state"
       and srv._normalize_api_path("/api/v1") == "/api/v1")
    ck("归一化：不误伤相似前缀（/apiv1）",
       srv._normalize_api_path("/apiv1/state") == "/apiv1/state")

    TOK6 = "selftest-v1-token"
    httpd6 = srv.make_server(0, token=TOK6)
    PORT6 = httpd6.server_address[1]
    threading.Thread(target=httpd6.serve_forever, daemon=True).start()

    def hit6(path, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", PORT6, timeout=10)
        c.request("GET", path, headers=headers or {})
        r = c.getresponse()
        raw = r.read()
        c.close()
        try:
            return r.status, json.loads(raw)
        except Exception:
            return r.status, raw.decode("utf-8", "replace")

    AUTH6 = {"X-Local-Market-Token": TOK6}
    try:
        st, _ = hit6("/api/v1/state")
        ck("★ /api/v1/state 无口令 → 403（版本前缀不绕过鉴权闸门）", st == 403, str(st))
        st, _ = hit6("/api/v1/state", {"X-Local-Market-Token": TOK6,
                                       "Origin": "http://evil.example"})
        ck("★ /api/v1/state 跨源 → 403（Origin 校验同样生效）", st == 403, str(st))
        st1, js1 = hit6("/api/v1/state", AUTH6)
        st2, js2 = hit6("/api/state", AUTH6)
        ck("★ /api/v1/state 与 /api/state 返回等价数据",
           st1 == 200 and st2 == 200
           and js1.get("marketId") == js2.get("marketId")
           and js1.get("marketVersion") == js2.get("marketVersion")
           and list(js1) == list(js2), f"{st1}/{st2}")
        st, _ = hit6("/api/v1/definitely-not-a-route", AUTH6)
        ck("/api/v1 未知路由 → 404", st == 404, str(st))
    finally:
        httpd6.shutdown()
        httpd6.server_close()

    # --- 28F. doctor：结构 / 渲染 / cli 分发
    import contextlib                                # noqa: E402
    import io                                        # noqa: E402
    import workbuddy_market.doctor as doc            # noqa: E402
    import workbuddy_market.cli as wmcli             # noqa: E402

    # 隔离环境里 GHPM_PY 不存在（round7 的 fake ghpm 已还原），doctor 按
    # 实情报 ✗ 本没有错 —— 但本节测的是 doctor 的结构与分发，不是环境，
    # 所以按假接缝惯例补一个真实存在的 ghpm.py，只影响 doctor 自己的绑定。
    fake_ghpm = _TMP / "wb" / "skills" / "github-project-manager" / "scripts" / "ghpm.py"
    fake_ghpm.parent.mkdir(parents=True, exist_ok=True)
    fake_ghpm.write_text("# selftest fake ghpm\n", encoding="utf-8")
    real_doc_ghpm = doc.GHPM_PY
    doc.GHPM_PY = fake_ghpm
    try:
        r = doc.run_doctor()
        ck("doctor：逐项字段齐全（name/ok/detail）",
           isinstance(r.get("checks"), list) and r["checks"]
           and all({"name", "ok", "detail"} <= set(c) for c in r["checks"]))
        ck("doctor：隔离环境健康时 ok=True", r["ok"] is True,
           "; ".join(f"{c['name']}: {c['detail'][:40]}"
                     for c in r["checks"] if not c["ok"])[:200])
        text = doc.render(r)
        ck("doctor：渲染含标题与逐项标记",
           "WorkBuddy Market Doctor" in text and "✓" in text)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = wmcli.main(["doctor"])
        ck("doctor：cli 分发可用且健康时退出码 0", rc == 0, buf.getvalue()[-120:])
    finally:
        doc.GHPM_PY = real_doc_ghpm
    # cli 分发会按 repo 根写 WBM_MARKET_ROOT —— 恢复隔离环境变量，防影响后续用例
    if _ISOLATED:
        os.environ["GHPM_MARKET_ROOT"] = str(_TMP / "market")
        os.environ.pop("WBM_MARKET_ROOT", None)


def round14():
    """v2.14 / R5：installer / uninstaller 迁包（逐字搬迁，行为零变化）。

    重点盯防（与 R2~R4 同一纪律）：
    1. re-export 同一性（is）—— core.X 必须就是包里那个对象；
    2. core 注入点**晚绑定**端到端：安装/卸载编排已进包，但对
       core.quick_fingerprint / core.tx_begin 等的调用必须经
       ``market_core`` 命名空间 —— patch core.X 仍要拦得到包内编排
       （第 21/20 节的崩溃矩阵已在真实流水线上验证，这里补直达断言）；
    3. 模块归属盯防见 24B（本轮已扩展 installer / uninstaller 八项）。
    """
    section("29. v2.14/R5：installer / uninstaller 迁包")
    import workbuddy_market.installer as wmi
    import workbuddy_market.uninstaller as wmu

    # --- 29A. re-export 同一性
    ck("安装符号同一性（R5）",
       core.install_local_plugin is wmi.install_local_plugin
       and core._stage_skill is wmi._stage_skill
       and core._commit_staged is wmi._commit_staged
       and core._sweep_staging is wmi._sweep_staging
       and core._stage_dir is wmi._stage_dir
       and core.INSTALL_MODES is wmi.INSTALL_MODES)
    ck("卸载符号同一性（R5）",
       core.classify_skill is wmu.classify_skill
       and core.inspect_skill is wmu.inspect_skill
       and core.plugin_uninstall_plan is wmu.plugin_uninstall_plan
       and core.uninstall_local_plugin is wmu.uninstall_local_plugin
       and core.dropped is wmu.dropped)
    ck("INSTALL_MODES 取值不变", core.INSTALL_MODES == ("missing", "update", "force"),
       str(core.INSTALL_MODES))

    # --- 29B. core 注入点晚绑定端到端：patch core.X 必须拦到包内编排
    # （1）classify 的指纹快路径经 core.quick_fingerprint —— 注入崩溃后
    #      ui 判定必须炸出来（证明走的是 core 命名空间，不是包内直连）
    real_fp = core.quick_fingerprint

    def _fp_boom(*a, **k):
        raise RuntimeError("注入：quick_fingerprint 处崩溃")

    core.quick_fingerprint = _fp_boom
    intercepted = False
    try:
        # bundle-one/alpha 此刻归本市场（第 28 节之后环境仍在）；
        # ui 用途 + 无缓存 → 走指纹快路径 → 命中注入
        wmu.classify_skill("bundle-one", "alpha", core.load_config(), purpose="ui")
    except RuntimeError as exc:
        intercepted = "quick_fingerprint" in str(exc)
    except Exception:
        intercepted = False
    finally:
        core.quick_fingerprint = real_fp
    ck("★ patch core.quick_fingerprint 拦得到包内 classify_skill（晚绑定）",
       intercepted)

    # （2）安装编排经 core.tx_begin —— 连日志都开不了就不许动磁盘
    #     （与 20B 同一契约：tx_begin 失败直接抛 OSError 硬失败，磁盘零改动。
    #      这里断言同一语义对 wm.installer 命名空间同样成立 —— 编排虽已
    #      迁包，注入点仍走 core 晚绑定）
    core.install_local_plugin("bundle-one", "force")      # 先归零
    before_tx = core.tree_hash(core.SKILLS_DIR / "alpha")
    real_begin = core.tx_begin
    core.tx_begin = lambda *a, **k: (_ for _ in ()).throw(
        OSError("模拟：连日志都开不了"))
    tx_failed = False
    try:
        wmi.install_local_plugin("bundle-one", "missing")
    except OSError:
        tx_failed = True
    finally:
        core.tx_begin = real_begin
    ck("★ tx_begin 注入 → 包内安装编排直接失败（不碰磁盘）", tx_failed)
    ck("★ tx_begin 注入期间本机 alpha 未被改动",
       core.tree_hash(core.SKILLS_DIR / "alpha") == before_tx
       and not list(core.SKILLS_DIR.glob(".*.installing-*")))

    # --- 29C. 行为不变：迁移后安装/卸载全流程仍走通（端到端一遍）
    r_i = core.install_local_plugin("bundle-one", "force")
    ck("★ 迁移后安装流程正常", r_i.get("ok") is True and not r_i.get("failed"),
       str(r_i.get("failed"))[:80])
    r_u = core.uninstall_local_plugin("bundle-one")
    ck("★ 迁移后卸载流程正常（safe 全部移除）",
       r_u.get("ok") is True and r_u["plan"]["counts"].get("safe", 0) >= 1,
       str(r_u.get("plan", {}).get("counts"))[:80])
    r_back = core.install_local_plugin("bundle-one", "missing")
    ck("★ 装回（环境归零，后续轮次不受影响）", r_back.get("ok") is True)


def round15():
    """v2.15：Market Package pack / verify（docs/plugin-spec.md v0.2）。

    本轮冻结了协议的 6 项开放问题并实现纯函数层：pack（本地插件目录 →
    带 manifest 的包）与 verify（不可信输入，按攻击面处理）。安装链路
    的接入是下一步，不在本轮。

    攻击面用例（spec §7.3 点名的三类 + 双向一致）：
    改文件内容 / 塞未列出文件 / 改清单字段 / 路径穿越 / 链接 / 平台。
    """
    section("30. v2.15：Market Package pack / verify")
    import workbuddy_market.packaging as pk

    tmp = _TMP / "pkg-lab"
    shutil.rmtree(tmp, ignore_errors=True)
    src = tmp / "src"
    (src / "skills" / "alpha" / "sub").mkdir(parents=True)
    (src / "skills" / "alpha" / "SKILL.md").write_text(
        "---\nname: alpha\nversion: 1.0.0\n---\n# alpha\n", encoding="utf-8")
    (src / "skills" / "alpha" / "sub" / "x.txt").write_text("X" * 64, encoding="utf-8")
    (src / "README.md").write_text("# demo\n", encoding="utf-8")

    # --- 30A. 规范化 JSON：键序无关 + 中文原样（冻结决定 #2 的可复现口径）
    a = pk.canonical_json({"b": 1, "a": 2})
    b = pk.canonical_json({"a": 2, "b": 1})
    ck("规范化 JSON：键序无关且紧凑", a == b and a == b'{"a":2,"b":1}')
    ck("规范化 JSON：非 ASCII 按原样编码（ensure_ascii=False）",
       pk.canonical_json({"k": "中"}) == '{"k":"中"}'.encode("utf-8"))

    # --- 30B. pack happy path + 重打包确定性
    r1 = pk.pack_package(src, tmp / "pkg1", pid="demo-pkg", name="Demo",
                         version="1.0.0", license="MIT",
                         source={"type": "github", "repo": "o/r", "ref": "a" * 40})
    ck("★ pack：包落位且 manifest 齐全",
       r1.get("ok") and (tmp / "pkg1" / "manifest.json").is_file()
       and r1["files"] == 3, str(r1.get("files")))
    r2 = pk.pack_package(src, tmp / "pkg2", pid="demo-pkg", name="Demo",
                         version="1.0.0", license="MIT",
                         source={"type": "github", "repo": "o/r", "ref": "a" * 40})
    ck("★ 重打包整包哈希稳定（immutable 口径）",
       r2["packageHash"] == r1["packageHash"],
       f"{r1['packageHash'][:12]} vs {r2['packageHash'][:12]}")
    ck("pack：id/version 复用配置层校验（坏 id 拒绝）",
       _raises(pk.pack_package, core.ConfigError,
               src, tmp / "pkgX", pid="../evil", name="X", version="1.0.0"))

    # --- 30C. verify happy path
    v = pk.verify_package(tmp / "pkg1")
    ck("★ verify：合法包通过且零告警",
       v["ok"] and not v["errors"] and not v["warnings"],
       "; ".join(v["errors"])[:100])
    ck("★ verify：packageHash 与 pack 一致",
       v["packageHash"] == r1["packageHash"])

    def _fresh():
        """从 pkg2 复制一份干净的包（pk2 本轮永不改动）。"""
        d = tmp / "pkg-t"
        shutil.rmtree(d, ignore_errors=True)
        shutil.copytree(tmp / "pkg2", d)
        return d

    def _rewrite(d: Path, mutate):
        m = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        mutate(m)
        (d / "manifest.json").write_text(json.dumps(m), encoding="utf-8")

    # --- 30D. 攻击面：改文件 / 塞文件 / 改清单 / 穿越
    d = _fresh()
    (d / "skills" / "alpha" / "sub" / "x.txt").write_text("Y" * 64, encoding="utf-8")
    ck("★ 攻击：篡改文件内容 → 拒绝", not pk.verify_package(d)["ok"])
    d = _fresh()
    (d / "extra.txt").write_text("evil", encoding="utf-8")
    ck("★ 攻击：塞未列出文件（双向一致）→ 拒绝", not pk.verify_package(d)["ok"])
    d = _fresh()
    (d / "skills" / "alpha" / "sub" / "x.txt").unlink()
    ck("★ 攻击：删清单内文件 → 拒绝", not pk.verify_package(d)["ok"])
    d = _fresh()
    _rewrite(d, lambda m: m.update(version="9.9.9"))
    ck("★ 攻击：改清单字段（自哈希不符）→ 拒绝", not pk.verify_package(d)["ok"])
    d = _fresh()
    _rewrite(d, lambda m: m.update(skills=["skills/../../.."]))
    ck("★ 攻击：skills 路径穿越 → 拒绝（ensure_child 闸）",
       not pk.verify_package(d)["ok"])
    d = _fresh()
    _rewrite(d, lambda m: m.update(id="../evil"))
    ck("★ 攻击：坏 id → 拒绝（validate_id 复用）", not pk.verify_package(d)["ok"])
    d = _fresh()
    _rewrite(d, lambda m: m.update(dependencies={"skills": [{"id": 1}]}))
    ck("攻击：依赖声明形状非法 → 拒绝（声明不解析，形状必须对）",
       not pk.verify_package(d)["ok"])
    d = _fresh()
    (d / "manifest.json").write_text("{broken", encoding="utf-8")
    ck("攻击：manifest 不是 JSON → 拒绝且不抛", not pk.verify_package(d)["ok"])

    # --- 30E. 链接防线
    link_type = _make_link(src, src / "skills" / "alpha" / "sub" / "link-dir")
    if link_type:
        try:
            refused = False
            try:
                pk.pack_package(src, tmp / "pkg-link", pid="demo-pkg",
                                name="Demo", version="1.0.0")
            except OSError as exc:
                refused = "链接" in str(exc) or "junction" in str(exc)
            ck("★ pack：源含重解析点 → 拒绝打包", refused)
        finally:
            _drop_link(src / "skills" / "alpha" / "sub" / "link-dir")
    else:
        sk("pack：源含重解析点 → 拒绝打包",
           "本环境建不出 junction / symlink（无管理员或宿主拦截）")

    # --- 30F. 平台口径（冻结决定 #4：默认拒绝，force 放行并记 warning）
    alien = "linux" if os.name == "nt" else "windows"
    rp = pk.pack_package(src, tmp / "pkg-plat", pid="demo-pkg", name="Demo",
                         version="1.0.0", platforms=[alien])
    ck("pack：platforms 写进 manifest 且自哈希含它",
       rp["manifest"]["platforms"] == [alien])
    v = pk.verify_package(tmp / "pkg-plat")
    ck("★ 平台不匹配 → 默认拒绝",
       not v["ok"] and any("平台不匹配" in e for e in v["errors"]),
       "; ".join(v["errors"])[:80])
    v = pk.verify_package(tmp / "pkg-plat", force=True)
    ck("★ force=True → 放行并如实记 warning",
       v["ok"] and v["warnings"] and "平台不匹配" in v["warnings"][0],
       "; ".join(v["warnings"])[:80])

    # 收尾
    shutil.rmtree(tmp, ignore_errors=True)
