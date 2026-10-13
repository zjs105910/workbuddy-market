# -*- coding: utf-8 -*-
"""第 33-35 节（v2.19-v2.21）：R6 收尾 core shim / permissions·兼容性·构建证明 / 收藏·注册表结构化·CLI。"""
from __future__ import annotations

import json
import os
import shutil
from . import REPO_ROOT, _TMP, _raises, ck, core, section


def round18():
    """v2.19：R6 收尾 —— state / application 迁包，market_core 收成兼容 shim。

    三条盯防线：
    1. 符号同一性：core 只是 re-export，`import market_core` 旧脚本不坏；
    2. 归属盯防（R4/R5 同款）：state / application 各符号的 __module__
       钉死，搬错位置直接 FAIL；
    3. patch 语义不变：core.plugin_uninstall_plan 拦到 build_state
       （R5 编排晚绑定纪律）；core.build_state 拦 server 链路（19M 依赖，
       server 经 core 命名空间调用）；core._scan 拦 sync 链路
       （第 18 节端到端覆盖，此处不重复）。外加 shim 防膨胀盯防。
    """
    section("33. v2.19：R6 收尾（state / application 迁包 + core shim）")
    import workbuddy_market.state as wstate
    import workbuddy_market.application as wapp

    # --- 33A. 符号同一性
    ck("★ state 符号同一性（core 只 re-export）",
       core.build_state is wstate.build_state
       and core.installed_skill_names is wstate.installed_skill_names
       and core.installed_repos is wstate.installed_repos)
    ck("★ application 符号同一性（core 只 re-export）",
       core.sync_packaging is wapp.sync_packaging
       and core._sync_packaging is wapp._sync_packaging
       and core.build_plugin_json is wapp.build_plugin_json
       and core.resolve_open_request is wapp.resolve_open_request
       and core.deep_check is wapp.deep_check
       and core.selfcheck is wapp.selfcheck
       and core.main is wapp.main)

    # --- 33B. 归属盯防（R4/R5 同款循环）
    for _name, _want in (
            ("installed_skill_names", "workbuddy_market.state"),
            ("installed_repos", "workbuddy_market.state"),
            ("build_state", "workbuddy_market.state"),
            ("sync_packaging", "workbuddy_market.application"),
            ("_sync_packaging", "workbuddy_market.application"),
            ("build_plugin_json", "workbuddy_market.application"),
            ("resolve_open_request", "workbuddy_market.application"),
            ("deep_check", "workbuddy_market.application"),
            ("selfcheck", "workbuddy_market.application"),
            ("main", "workbuddy_market.application")):
        _mod = getattr(getattr(core, _name), "__module__", "?")
        ck(f"注入点已迁包（R6）：{_name}", _mod == _want, _mod)

    # --- 33C. patch 语义回归 + shim 防膨胀
    # core.plugin_uninstall_plan 必须仍能拦到 build_state 的卸载分级
    # （state.build_state 函数体内经 core 晚绑定调用 —— R5 编排纪律）。
    real_plan = core.plugin_uninstall_plan
    hits = {"n": 0}

    def counting_plan(*a, **k):
        hits["n"] += 1
        return real_plan(*a, **k)

    core.plugin_uninstall_plan = counting_plan
    try:
        st_p = core.build_state()
    finally:
        core.plugin_uninstall_plan = real_plan
    ck("★ patch core.plugin_uninstall_plan 拦到 build_state（编排晚绑定）",
       hits["n"] == len(st_p["plugins"]),
       f"{hits['n']} vs 插件数 {len(st_p['plugins'])}")

    # shim 防膨胀：core 收成兼容层后不许再往里塞实现（评审 1 的收敛目标）
    _core_py = REPO_ROOT / "market_core.py"
    _n_lines = len(_core_py.read_text(encoding="utf-8").splitlines())
    ck("★ core shim 防膨胀（<400 行）", _n_lines < 400, f"{_n_lines} 行")


def round19():
    """v2.20：permissions / 兼容性检测 / 构建证明（协议 v0.3，第 34 节）。

    四条盯防线：
    1. permissions：pack 写入前形状校验（fail-fast）、verify 查形状、
       manifest 自哈希覆盖它（改一个字都过不了）；
    2. 风险预览 / 兼容性报告（纯函数）：level 三档、ok 三态 ——
       「宿主版本未知」必须如实标 △，绝不冒充满足或不满足；
    3. 宿主版本门槛：minWorkBuddyVersion 与平台同口径（默认拒绝、
       force 放行并记 warning）；探测不到 → 跳过，不算失败；
    4. 构建证明：build_one 产出 attestation 且与包对账一致，篡改
       packageHash / sourceCommit 立即现形；--patch-registry 回写
       attestationUrl / permissions，registry 解析层成套采纳 + fail-closed。
    """
    section("34. v2.20：permissions / 兼容性检测 / 构建证明（协议 v0.3）")
    import workbuddy_market.packaging as pk
    import workbuddy_market.registry as wr

    from workbuddy_market.adapters.workbuddy import detect_host_version

    lab = _TMP / "r19-lab"
    shutil.rmtree(lab, ignore_errors=True)
    lab.mkdir(parents=True)

    src = lab / "src"
    (src / "skills" / "alpha").mkdir(parents=True)
    (src / "skills" / "alpha" / "SKILL.md").write_text(
        "---\nname: alpha\nversion: 1.0.0\n---\n# alpha\n", encoding="utf-8")

    PERMS = {"network": ["github.com", "api.github.com"],
             "shell": ["python"], "credentials": False}

    # --- 34A. permissions：pack 固化 + verify 形状闸
    r = pk.pack_package(src, lab / "pkg-perm", pid="demo-pkg", name="Demo",
                        version="1.0.0", permissions=PERMS)
    ck("★ pack：permissions 写进 manifest 且自哈希覆盖它",
       r["manifest"]["permissions"] == PERMS
       and pk.verify_package(lab / "pkg-perm")["ok"])
    ck("pack：未知能力键 → 打包期拒绝（fail-fast）",
       _raises(pk.pack_package, core.ConfigError,
               src, lab / "pkg-bad1", pid="demo-pkg", name="Demo", version="1.0.0",
               permissions={"gpu": True}))
    ck("pack：空数组范围 → 打包期拒绝",
       _raises(pk.pack_package, core.ConfigError,
               src, lab / "pkg-bad2", pid="demo-pkg", name="Demo", version="1.0.0",
               permissions={"shell": []}))

    d = lab / "pkg-t"
    shutil.rmtree(d, ignore_errors=True)
    shutil.copytree(lab / "pkg-perm", d)
    m = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    m["permissions"] = {"mystery": True}
    (d / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
    v = pk.verify_package(d)
    ck("★ 攻击：manifest 里的 permissions 形状非法 → 拒绝（形状独立于自哈希）",
       not v["ok"] and any(e.startswith("permissions") for e in v["errors"]),
       "; ".join(v["errors"])[:90])

    # --- 34B. risk_summary：三档 level + 归一化
    ck("★ risk_summary：布尔 true → broad（未限定范围的全量授权）",
       pk.risk_summary({"permissions": {"shell": True}})["level"] == "broad")
    ck("★ risk_summary：数组范围 → scoped 且 scope 转人话",
       (lambda s: s["level"] == "scoped" and s["items"][0]["scope"] == "github.com")(
           pk.risk_summary({"permissions": {"network": ["github.com"]}})))
    ck("★ risk_summary：false 也是声明（declared=True、granted=False、level=none）",
       (lambda s: s["declared"] and s["level"] == "none"
        and s["items"][0]["granted"] is False)(
           pk.risk_summary({"permissions": {"credentials": False}})))
    ck("risk_summary：未声明 → declared=False；非 dict manifest 不炸",
       not pk.risk_summary({})["declared"] and not pk.risk_summary(None)["declared"])

    # --- 34C. compatibility_report：ok 三态（True / False / None=未知）
    ck("★ 兼容性：无声明 → 平台默认全平台（ok=True）",
       pk.compatibility_report({})["ok"] is True)
    ck("★ 兼容性：平台不匹配 → ok=False",
       pk.compatibility_report({"platforms": ["linux"]},
                               platform="windows")["ok"] is False)
    ck("★ 兼容性：宿主版本低于要求 → ok=False（数字段比较：5.10 > 5.9）",
       pk.compatibility_report({"minWorkBuddyVersion": "5.8"},
                               host_version="5.7.6")["ok"] is False
       and pk.semver_gte("5.10", "5.9"))
    ck("★ 兼容性：宿主版本未知 → ok=None（△ 未知），整体不算失败",
       (lambda c: c["checks"][-1]["ok"] is None and c["ok"] is True)(
           pk.compatibility_report({"minWorkBuddyVersion": "5.8"}, host_version=None)))
    ck("semver_gte 口径：补零等值 / 预发布视为相等 / v 前缀 / 低位反例",
       pk.semver_gte("5.7", "5.7.0") and pk.semver_gte("5.7.6-beta", "5.7.6")
       and pk.semver_gte("v5.8.1", "5.8") and not pk.semver_gte("5.6.9", "5.7"))

    # --- 34D. verify 的宿主版本门槛（与平台同口径：默认拒绝 / force 放行）
    pk.pack_package(src, lab / "pkg-min", pid="demo-pkg", name="Demo",
                    version="1.0.0", min_workbuddy_version="999.0.0")
    ck("★ 宿主版本不满足 → 默认拒绝",
       not pk.verify_package(lab / "pkg-min", host_version="5.7.6")["ok"])
    v = pk.verify_package(lab / "pkg-min", host_version="5.7.6", force=True)
    ck("★ force=True → 放行并如实记 warning",
       v["ok"] and any("宿主版本" in w for w in v["warnings"]),
       "; ".join(v["warnings"])[:80])
    ck("★ 宿主版本未知 → 跳过（不算失败，诚实口径）",
       pk.verify_package(lab / "pkg-min", host_version=None)["ok"])

    # --- 34E. 构建证明：build_one → attestation → 对账 → 回写
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "build_artifacts_r19",
        str(REPO_ROOT / "scripts" / "build_artifacts.py"))
    bld = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bld)
    import io as _io19
    import tarfile as _tf19

    lab2 = _TMP / "r19-lab2"
    shutil.rmtree(lab2, ignore_errors=True)
    lab2.mkdir(parents=True)

    def _mk_tar19(path, entries, prefix="owner_repo-abc123"):
        with _tf19.open(path, "w:gz") as tf:
            for name, data in entries:
                ti = _tf19.TarInfo(f"{prefix}/{name}" if prefix else name)
                ti.size = len(data.encode("utf-8"))
                tf.addfile(ti, _io19.BytesIO(data.encode("utf-8")))

    _mk_tar19(lab2 / "t.tar.gz", [("SKILL.md", "---\nname: solo\n---\n")])
    tar_bytes = (lab2 / "t.tar.gz").read_bytes()
    ref19 = "b" * 40
    out_dir = lab2 / "artifacts"
    entry19 = {"repo": "owner/repo", "displayName": "Demo", "sourceCommit": ref19,
               "permissions": {"network": ["github.com"]}}
    rr = bld.build_one(entry19, out_dir,
                       fetch=lambda url: (tar_bytes
                                          if url == "https://codeload.github.com/owner/repo/tar.gz/" + ref19
                                          else (_ for _ in ()).throw(OSError(url))),
                       work_root=lab2 / "w")
    att = json.loads((out_dir / rr["attestationFile"]).read_text(encoding="utf-8"))
    ck("★ build_one：attestation 落盘且与包对账一致",
       (out_dir / rr["attestationFile"]).is_file()
       and not pk.verify_attestation(att, package_hash=rr["packageHash"],
                                     manifest_hash=rr["manifestHash"],
                                     source_commit=ref19),
       str(pk.verify_attestation(att, package_hash=rr["packageHash"]))[:90])
    ck("★ 收录条目的静态 permissions 被 CI 固化进 manifest（从此受 manifestHash 保护）",
       rr["permissions"] == {"network": ["github.com"]}
       and rr["minWorkBuddyVersion"] == "")
    ck("★ 对账：attestation 的 packageHash 被篡改 → 立即现形",
       (lambda a, errs: errs and any("packageHash" in e for e in errs))(
           {**att, "packageHash": "0" * 64},
           pk.verify_attestation({**att, "packageHash": "0" * 64},
                                 package_hash=rr["packageHash"])))
    ck("对账：sourceCommit 不符 / attestation 形状坏 → 都拦",
       pk.verify_attestation(att, package_hash=rr["packageHash"],
                             source_commit="c" * 40) != []
       and pk.verify_attestation(["nope"], package_hash=rr["packageHash"])
       == ["attestation 必须是 JSON 对象"])

    (out_dir / "report.json").write_text(json.dumps(
        {"built": [rr], "failed": []}, ensure_ascii=False), encoding="utf-8")
    reg_file = lab2 / "plugins.json"
    reg_file.write_text(json.dumps({"schema": 1, "updatedAt": "", "plugins": [
        {"repo": "owner/repo", "trust": "reviewed", "sourceCommit": ref19},
        {"repo": "other/one", "trust": "reviewed"}]}, ensure_ascii=False),
        encoding="utf-8")
    rc = bld.main(["--patch-registry", "--out", str(out_dir),
                   "--registry", str(reg_file),
                   "--release-tag", "registry-artifacts-2026-10-08"])
    doc_after = json.loads(reg_file.read_text(encoding="utf-8"))
    e0 = doc_after["plugins"][0]
    ck("★ 回写：attestationUrl + permissions 进条目（无产物条目不被触碰）",
       rc == 0
       and e0["attestationUrl"] ==
       ("https://github.com/zjs105910/workbuddy-market/releases/download/"
        f"registry-artifacts-2026-10-08/{rr['attestationFile']}")
       and e0["permissions"] == {"network": ["github.com"]}
       and "attestationUrl" not in doc_after["plugins"][1])

    # --- 34F. registry 解析层：新字段白名单采纳 + fail-closed
    good = {"schema": 1, "updatedAt": "", "plugins": [{
        "repo": "o/k", "trust": "reviewed",
        "packageUrl": "https://github.com/z/releases/download/t/x.zip",
        "packageHash": "a" * 64,
        "attestationUrl": "https://github.com/z/releases/download/t/x.zip.attestation.json",
        "permissions": {"network": ["github.com"]},
        "platforms": ["windows", "solaris"],
        "minWorkBuddyVersion": "5.7"}]}
    parsed = wr.parse_registry(json.dumps(good))["plugins"][0]
    ck("★ 解析层：attestationUrl / permissions / platforms / minWorkBuddyVersion 采纳（platforms 过白名单）",
       parsed.get("attestationUrl", "").endswith(".attestation.json")
       and parsed.get("permissions") == {"network": ["github.com"]}
       and parsed.get("platforms") == ["windows"]
       and parsed.get("minWorkBuddyVersion") == "5.7",
       str(parsed)[:140])
    noart = {"schema": 1, "updatedAt": "", "plugins": [{
        "repo": "o/k", "trust": "reviewed",
        "attestationUrl": "https://github.com/z/releases/download/t/x.zip.attestation.json"}]}
    ck("★ 解析层：没有成套产物字段 → attestationUrl 不采纳（没有包的证明没有意义）",
       "attestationUrl" not in wr.parse_registry(json.dumps(noart))["plugins"][0])
    badperm = {"schema": 1, "updatedAt": "", "plugins": [{
        "repo": "o/k", "trust": "reviewed",
        "packageUrl": "https://github.com/z/releases/download/t/x.zip",
        "packageHash": "a" * 64,
        "permissions": {"shell": {"oops": 1}}}]}
    ck("★ 解析层：permissions 形状非法 → 整个字段当没有（fail-closed）",
       "permissions" not in wr.parse_registry(json.dumps(badperm))["plugins"][0])

    # --- 34G. detect_host_version：显式来源 + 不可信状态文件口径
    _old_env = os.environ.get("WORKBUDDY_VERSION")
    os.environ["WORKBUDDY_VERSION"] = "5.9.9"
    try:
        ck("★ 宿主版本：WORKBUDDY_VERSION 显式注入优先",
           detect_host_version() == "5.9.9")
    finally:
        if _old_env is None:
            os.environ.pop("WORKBUDDY_VERSION", None)
        else:
            os.environ["WORKBUDDY_VERSION"] = _old_env
    hd = lab / "host"
    hd.mkdir(parents=True, exist_ok=True)
    (hd / "last-launch.json").write_text(
        '{"version": "5.7.6", "build": "x", "timestamp": "t"}', encoding="utf-8")
    ck("★ 宿主版本：last-launch.json 是可靠来源（WorkBuddy 自己写的启动记录）",
       detect_host_version(host_dir=hd) == "5.7.6")
    (hd / "last-launch.json").write_text('{"version": 576}', encoding="utf-8")
    ck("宿主版本：形状不对（非字符串）→ 当没有",
       detect_host_version(host_dir=hd) is None)
    ck("宿主版本：文件不存在 → None（绝不猜安装目录 / 注册表）",
       detect_host_version(host_dir=lab / "nope") is None)

    # --- 34H. cli verify：包级子命令端到端
    import contextlib
    import io as _ioh
    from workbuddy_market import cli as wcli
    with contextlib.redirect_stdout(_ioh.StringIO()) as buf:
        rc_ok = wcli.main(["verify", str(lab / "pkg-perm")])
    ck("★ cli verify：合法包 → 退出码 0 且输出风险预览",
       rc_ok == 0 and "风险预览" in buf.getvalue(), buf.getvalue()[-90:])
    with contextlib.redirect_stdout(_ioh.StringIO()) as bufj:
        rc_json = wcli.main(["verify", str(lab / "pkg-perm"), "--json"])
    ck("cli verify：--json 可解析且 level=scoped",
       rc_json == 0 and json.loads(bufj.getvalue())["risk"]["level"] == "scoped")
    bad_pkg = lab / "pkg-badfile"
    shutil.copytree(lab / "pkg-perm", bad_pkg)
    (bad_pkg / "skills" / "alpha" / "SKILL.md").write_text(
        "---\nname: alpha\nversion: 9.9.9\n---\n# evil\n", encoding="utf-8")
    with contextlib.redirect_stdout(_ioh.StringIO()):
        rc_bad = wcli.main(["verify", str(bad_pkg)])
    ck("★ cli verify：被篡改的包 → 退出码 1", rc_bad == 1)

    shutil.rmtree(lab, ignore_errors=True)
    shutil.rmtree(lab2, ignore_errors=True)


def round20():
    """v2.21：收藏 / 注册表结构化解析 / 截图域名白名单 / CLI list·search。

    评审 #9/#12/#13/#22（dsh-market 对比走查）的当轮落地：
    1. 收藏（favorites）：本机持久化、形状不可信当空、原子写、casefold 去重；
    2. 注册表结构化：嵌套 source/artifact/compatibility/trust/quality
       与平铺等价解析，回写平铺零迁移；
    3. 截图：只收 https 且 GitHub 系域名（fail-closed，防外链追踪）；
    4. CLI list / search：包级能力，不依赖 clone 布局。
    """
    section("35. v2.21：收藏 / 注册表结构化 / 截图 / CLI 查询")
    import contextlib
    import io as _io20
    import workbuddy_market.favorites as fav
    import workbuddy_market.registry as wr

    # --- 35A. 收藏：本机持久化 + 形状不可信 + casefold 去重
    fav_path = fav.FAVORITES_PATH
    ck("★ 收藏落盘在 STATE_HOME（Local-first，不进 Git）",
       ".workbuddy-market" in str(fav_path) or str(fav_path).startswith(str(_TMP)))
    ck("★ 符号同一性：core 只 re-export favorites",
       core.load_favorites is fav.load_favorites
       and core.set_favorite is fav.set_favorite
       and core.is_favorite is fav.is_favorite)
    ck("收藏：初始为空（坏文件 / 不存在都当空）",
       fav.load_favorites() == [])
    r = fav.set_favorite("Anthropics/Skills", True)
    ck("★ 收藏：加一条 → 大小写归一，重加不重复",
       r == ["Anthropics/Skills"] and fav.is_favorite("anthropics/skills"))
    r = fav.set_favorite("anthropics/skills", True)
    ck("收藏：同 repo 不同大小写重复收藏 → 仍只一条",
       len(r) == 1)
    r = fav.set_favorite("Anthropics/Skills", False)
    ck("★ 收藏：取消 → 列表清空", r == [] and not fav.is_favorite("anthropics/skills"))

    # --- 35B. 注册表结构化：嵌套与平铺等价
    nested = {"schema": 1, "plugins": [{
        "repo": "owner/repo", "displayName": "Nested", "category": "工具",
        "source": {"type": "github", "repo": "owner/repo", "commit": "abc123"},
        "artifact": {"url": "https://x/y.zip", "sha256": "a" * 64,
                     "size": 123, "version": "1.2.0"},
        "compatibility": {"workbuddy": ">=5.7",
                          "platforms": ["windows", "linux"]},
        "trustObj": {"level": "reviewed"},
        "quality": {"score": 93, "tests": True, "lastVerified": "2026-10-08"},
        "screenshots": ["https://user-images.githubusercontent.com/a.png",
                        "https://evil.com/b.png", "http://github.com/c.png"],
    }]}
    e = wr.parse_registry(nested)["plugins"][0]
    ck("★ 注册表结构化：source.commit → sourceCommit",
       e.get("sourceCommit") == "abc123")
    ck("★ 注册表结构化：artifact.url/sha256/size/version 成套采纳",
       e.get("packageUrl") == "https://x/y.zip" and e.get("packageHash") == "a" * 64
       and e.get("packageSize") == 123 and e.get("version") == "1.2.0")
    ck("★ 注册表结构化：compatibility → platforms/minWorkBuddyVersion",
       e.get("platforms") == ["windows", "linux"]
       and e.get("minWorkBuddyVersion") == ">=5.7")
    ck("★ 注册表结构化：trustObj.level → trust；quality 三字段",
       e.get("trust") == "reviewed" and e.get("qualityScore") == 93
       and e.get("qualityTests") is True
       and e.get("qualityLastVerified") == "2026-10-08")

    # --- 35C. 截图域名白名单（fail-closed）
    ck("★ 截图：GitHub 系 https 放行",
       wr._github_image_url("https://user-images.githubusercontent.com/x/a.png")
       and wr._github_image_url("https://raw.githubusercontent.com/o/r/main/a.png"))
    ck("★ 截图：非 GitHub 域名 / http / 伪装域名全部拒绝",
       not wr._github_image_url("https://evil.com/a.png")
       and not wr._github_image_url("http://github.com/a.png")
       and not wr._github_image_url("https://github.com.evil.com/a.png")
       and not wr._github_image_url("https://github.io/a.png"))
    ck("★ 截图：解析后只保留 GitHub 系（fail-closed 过滤）",
       e.get("screenshots") == ["https://user-images.githubusercontent.com/a.png"])

    # --- 35D. CLI list / search：包级能力，不依赖 clone 布局
    from workbuddy_market import cli as wcli
    with contextlib.redirect_stdout(_io20.StringIO()) as buf:
        rc = wcli.main(["list", "--json"])
    ck("★ cli list：退出码 0 且 JSON 可解析",
       rc == 0 and json.loads(buf.getvalue()).get("source") is not None)
    with contextlib.redirect_stdout(_io20.StringIO()) as buf2:
        rc2 = wcli.main(["search", "pdf"])
    ck("★ cli search：退出码 0 且命中输出",
       rc2 == 0 and "pdf" in buf2.getvalue().lower())

    # --- 36. Registry 收录契约（registry-schema.json v2 + validate_registry.py）
    # 三条盯防线：
    # 1. 真实注册表永远能过契约 —— 收录质量基线，坏了这里直接 FAIL；
    # 2. 契约真的会咬人 —— 常见坏形态（查重/枚举/哈希/截图域名/成套产物）
    #    必须各报对 error；缺 license / 缺兼容性只警告不拦（早期收录不阻塞）；
    # 3. 契约文件与校验器版本互锁 —— 防契约文档和执行者漂移。
    import importlib.util as _ilv36
    _spec36 = _ilv36.spec_from_file_location(
        "validate_registry",
        str(REPO_ROOT / "scripts" / "validate_registry.py"))
    vreg = _ilv36.module_from_spec(_spec36)
    _spec36.loader.exec_module(vreg)

    real_doc = json.loads(
        (REPO_ROOT / "registry" / "plugins.json")
        .read_text(encoding="utf-8"))
    errs36, _ = vreg.validate_registry(real_doc)
    ck("★ 真实 registry/plugins.json 通过收录契约（0 error）", not errs36,
       "; ".join(errs36[:2]))
    schema_doc36 = json.loads(
        (REPO_ROOT / "registry" / "registry-schema.json")
        .read_text(encoding="utf-8"))
    ck("★ 契约 version 与校验器 CONTRACT_VERSION 互锁",
       schema_doc36.get("version") == vreg.CONTRACT_VERSION
       and schema_doc36.get("$schema", "").startswith("https://json-schema.org/draft/"))

    def _errs36(doc):
        return vreg.validate_registry(doc)[0]

    base36 = {"repo": "owner/repo", "displayName": "X", "category": "开发工具",
              "description": "一条足够长的描述文本。", "keywords": ["k"],
              "addedAt": "2026-10-08", "trust": "reviewed",
              "review": {"status": "reviewed", "reviewedAt": "2026-10-08",
                         "method": "manual"},
              "sourceCommit": "a" * 40}
    doc36 = lambda *es: {"schema": 1, "updatedAt": "2026-10-08", "plugins": list(es)}  # noqa: E731
    ck("★ 合法最小条目 → 0 error", not _errs36(doc36(base36)))
    dup36 = dict(base36, repo="Owner/REPO")
    ck("★ repo 大小写重复 → error（casefold 查重）",
       any("大小写重复" in x for x in _errs36(doc36(base36, dup36))))
    ck("★ trust 越枚举 → error",
       any("trust" in x for x in _errs36(doc36(dict(base36, trust="super")))))
    ck("★ sourceCommit 非 40 位 → error",
       any("sourceCommit" in x for x in _errs36(doc36(dict(base36, sourceCommit="abc")))))
    ck("★ official 未过审 → error（一致性）",
       any("official" in x for x in _errs36(doc36(dict(
           base36, trust="official",
           review={"status": "pending", "reviewedAt": "2026-10-08",
                   "method": "manual"})))))
    ck("★ 截图域名不在白名单 → error（与 registry.py 同口径）",
       any("截图域名" in x for x in _errs36(
           doc36(dict(base36, screenshots=["https://evil.com/a.png"])))))
    ck("★ packageUrl / packageHash 不成对 → error",
       any("成对" in x for x in _errs36(
           doc36(dict(base36, packageUrl="https://x/y.zip")))))
    ck("★ 未知字段 → error（additionalProperties=false）",
       any("未知字段" in x for x in _errs36(doc36(dict(base36, starring=1)))))
    _pair = dict(base36, packageUrl="https://x/y.zip", packageHash="a" * 64)
    errs_p, warns_p = vreg.validate_registry(doc36(_pair))
    ck("★ 缺 license / 缺兼容性只警告不拦（早期收录不阻塞）",
       not errs_p and any("license" in w for w in warns_p)
       and any("兼容性" in w for w in warns_p))


