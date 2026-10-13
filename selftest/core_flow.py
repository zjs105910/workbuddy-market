# -*- coding: utf-8 -*-
"""第 1-15 节：打包 / 增量同步 / 安装 / 卸载 / 文件锁 / 日志 / 回收站 / 注册。

原 selftest.py ``run()`` 的内联主体，v2.34 拆出为独立函数（逐字搬迁）。
"""
from __future__ import annotations

import json
import os
import shutil
import threading
import time
from pathlib import Path
from . import ck, core, prepare_fixture, section, wm, write_fake_skill


def core_flow() -> None:
    prepare_fixture()

    # ============ 1. 打包 ============
    section("1. 打包与索引")
    rep = core.sync_packaging(quiet=True)
    ck("打包出 2 个插件", len([p for p in rep["plugins"] if not p.get("skipped")]) == 2,
       str([p["name"] for p in rep["plugins"]]))
    ck("打包了 3 个 skill", rep["copiedSkills"] == 3, str(rep["copiedSkills"]))

    man = json.loads(core.MANIFEST_PATH.read_text(encoding="utf-8"))
    ck("索引 name == marketId", man["name"] == "test-market")
    ck("索引含 owner 与 plugins", "owner" in man and isinstance(man["plugins"], list))
    ck("source 都是 ./ 相对路径",
       all(str(p["source"]).startswith("./") for p in man["plugins"]))
    ck("每条插件必备字段齐全",
       all(p.get(f) for p in man["plugins"] for f in ("name", "description", "version", "source")))

    pj = json.loads((core.PLUGINS_DIR / "bundle-one" / ".codebuddy-plugin" / "plugin.json")
                    .read_text(encoding="utf-8"))
    ck("plugin.json name 与目录一致", pj["name"] == "bundle-one")
    ck("plugin.json 有 description_zh/en", "description_zh" in pj and "description_en" in pj)

    # ============ 2. 增量同步 ============
    section("2. 增量同步")
    r2 = core.sync_packaging(quiet=True)
    ck("重复同步零拷贝", r2["copiedFiles"] == 0 and r2["removedFiles"] == 0,
       f"copied={r2['copiedFiles']} removed={r2['removedFiles']}")

    (core.SKILLS_DIR / "alpha" / "new.md").write_text("new\n", encoding="utf-8")
    r3 = core.sync_packaging(quiet=True)
    ck("新增 1 个文件 → 只拷 1 个", r3["copiedFiles"] == 1, str(r3["copiedFiles"]))
    ck("文件已同步到插件",
       (core.PLUGINS_DIR / "bundle-one" / "skills" / "alpha" / "new.md").is_file())

    (core.SKILLS_DIR / "alpha" / "new.md").unlink()
    r4 = core.sync_packaging(quiet=True)
    ck("删掉 1 个文件 → 只删 1 个", r4["removedFiles"] == 1 and r4["copiedFiles"] == 0,
       f"copied={r4['copiedFiles']} removed={r4['removedFiles']}")

    # ============ 3. mtime 精度（v1 的真实 bug）============
    section("3. mtime_ns：同秒内 + 同大小的修改必须被检出")
    srcf = core.SKILLS_DIR / "gamma" / "SKILL.md"
    dstf = core.PLUGINS_DIR / "bundle-two" / "skills" / "gamma" / "SKILL.md"
    ck("初始两边内容一致", srcf.read_bytes() == dstf.read_bytes())

    body = srcf.read_text(encoding="utf-8")
    # 从整秒 +0.1 起算，保证 t0 与 t0+0.2 落在同一秒内（否则这个断言会随
    # 真实时间抖动而 flaky —— 踩到秒边界就失败）
    t0 = int(time.time()) + 0.1
    srcf.write_text(body.replace("0.9.0", "0.9.1"), encoding="utf-8")   # 等长改写
    os.utime(srcf, (t0, t0))
    dstf.write_text(body.replace("0.9.0", "0.9.2"), encoding="utf-8")
    time.sleep(0.25)
    os.utime(dstf, (t0 + 0.2, t0 + 0.2))          # 同一秒内、晚 0.2 秒

    ss, ds = srcf.stat(), dstf.stat()
    ck("两边大小相同", ss.st_size == ds.st_size, str(ss.st_size))
    ck("int(st_mtime) 判定确实会漏检（复现 v1 bug）",
       int(ds.st_mtime) == int(ss.st_mtime),
       f"int {int(ds.st_mtime)} == {int(ss.st_mtime)}")
    ck("mtime_ns 判定能分出来", ds.st_mtime_ns != ss.st_mtime_ns)

    r5 = core.sync_packaging(quiet=True)
    ck("★ 同秒同大小的修改被同步了", r5["copiedFiles"] >= 1, f"copied={r5['copiedFiles']}")
    ck("内容确实更新了", dstf.read_bytes() == srcf.read_bytes())

    # ============ 4. 排除规则 ============
    section("4. 打包排除")
    (core.SKILLS_DIR / "alpha" / "junk.bak").write_text("junk", encoding="utf-8")
    (core.SKILLS_DIR / "alpha" / "junk.tmp").write_text("junk", encoding="utf-8")
    core.sync_packaging(quiet=True)
    ck("*.bak 未被打包",
       not (core.PLUGINS_DIR / "bundle-one" / "skills" / "alpha" / "junk.bak").exists())
    ck("*.tmp 未被打包",
       not (core.PLUGINS_DIR / "bundle-one" / "skills" / "alpha" / "junk.tmp").exists())
    (core.SKILLS_DIR / "alpha" / "junk.bak").unlink()
    (core.SKILLS_DIR / "alpha" / "junk.tmp").unlink()

    # ============ 5. 安装 + 所有权 ============
    section("5. 安装与所有权记录")
    ck("初始无所有权记录", len(core.load_ownership()["skills"]) == 0)
    ck("卸载前 alpha 判为 foreign",
       core.classify_skill("bundle-one", "alpha", core.load_config())["kind"] == "foreign")

    for s in ("alpha", "beta"):          # 模拟「全新安装」
        shutil.rmtree(core.SKILLS_DIR / s)
    r = core.install_local_plugin("bundle-one", "missing")
    ck("安装补齐 2 个 skill", sorted(r["added"]) == ["alpha", "beta"], str(r["added"]))
    ck("★ 安装后记下了所有权", set(core.load_ownership()["skills"]) >= {"alpha", "beta"})
    ck("已装 skill 判为 safe",
       core.classify_skill("bundle-one", "alpha", core.load_config())["kind"] == "safe")

    # ============ 6. 安装模式 ============
    section("6. 安装模式 missing / update / force")
    r = core.install_local_plugin("bundle-one", "missing")
    ck("missing 模式：已存在则跳过",
       sorted(r["skipped"]) == ["alpha", "beta"] and not r["updated"], str(r["skipped"]))

    (core.SKILLS_DIR / "alpha" / "notes.md").write_text("# changed\n", encoding="utf-8")
    core.sync_packaging(quiet=True)
    ck("本机改动后判为 modified",
       core.classify_skill("bundle-one", "alpha", core.load_config())["kind"] == "modified")

    r = core.install_local_plugin("bundle-one", "missing")
    ck("missing 模式不动 modified", not r["updated"] and "alpha" in r["skipped"], str(r["skipped"]))

    r = core.install_local_plugin("bundle-one", "update")
    ck("update 模式覆盖 modified", r["updated"] == ["alpha"], str(r["updated"]))
    ck("覆盖后回到 safe",
       core.classify_skill("bundle-one", "alpha", core.load_config())["kind"] == "safe")

    r = core.install_local_plugin("bundle-one", "bogus")
    ck("非法模式被拒绝", r["ok"] is False and "未知安装模式" in r["error"])

    # ============ 7. 卸载安全分级（v1 最危险的地方）============
    section("7. 卸载：绝不碰别人的 skill")
    write_fake_skill(core.SKILLS_DIR, "mine", "1.0.0", "用户自己的", {})   # 用户自己的
    own = core.load_ownership()                                          # 别的插件装的
    own["skills"]["gamma"] = {"owner": "test-market", "plugin": "bundle-two",
                              "version": "2.0.0", "installedAt": core.now_iso(),
                              "hash": core.tree_hash(core.SKILLS_DIR / "gamma")}
    wm.ownership.save_ownership(own)

    plan = core.plugin_uninstall_plan("bundle-one")
    ck("alpha/beta 可安全卸载", sorted(plan["removable"]) == ["alpha", "beta"], str(plan["removable"]))
    ck("计划里不含别的插件的 skill", "gamma" not in plan["removable"] + plan["modified"])
    ck("计划里不含用户自己的 skill", "mine" not in plan["removable"] + plan["modified"])

    (core.SKILLS_DIR / "beta" / "data.bin").write_text("hand-edited", encoding="utf-8")
    plan2 = core.plugin_uninstall_plan("bundle-one")
    ck("被改过的 beta 判为 modified", plan2["modified"] == ["beta"], str(plan2["modified"]))

    res = core.uninstall_local_plugin("bundle-one")
    ck("卸载移走了 safe 的 alpha", res["moved"] == ["alpha"], str(res["moved"]))
    ck("★ 被改过的 beta 被保留", [k["skill"] for k in res["kept"]] == ["beta"], str(res["kept"]))
    ck("★ 用户自己的 mine 毫发无损", (core.SKILLS_DIR / "mine" / "SKILL.md").is_file())
    ck("★ 别的插件的 gamma 毫发无损", (core.SKILLS_DIR / "gamma" / "SKILL.md").is_file())
    ck("alpha 进了回收站而非被删",
       not (core.SKILLS_DIR / "alpha").exists()
       and any("alpha" in p.name for p in core.TRASH_DIR.iterdir()))

    res2 = core.uninstall_local_plugin("bundle-one", force=True)
    ck("force 才移走 modified 的 beta", res2["moved"] == ["beta"], str(res2["moved"]))
    ck("force 仍然不碰 mine / gamma",
       (core.SKILLS_DIR / "mine").exists() and (core.SKILLS_DIR / "gamma").exists())

    # 卸载之后市场里必须还留着货 —— 否则「装回来」这条路根本不成立
    r_sync = core.sync_packaging(quiet=True)
    names = [p["name"] for p in
             json.loads(core.MANIFEST_PATH.read_text(encoding="utf-8"))["plugins"]]
    ck("★ 卸载后市场仍保留该插件（是仓库不是镜像）", "bundle-one" in names, str(names))
    ck("★ 保留的是历史副本",
       (core.PLUGINS_DIR / "bundle-one" / "skills" / "alpha" / "SKILL.md").is_file())
    ck("★ 源已消失的 skill 被记为 cached", len(r_sync["cachedSkills"]) >= 2,
       str(r_sync["cachedSkills"]))
    r_back = core.install_local_plugin("bundle-one", "missing")
    ck("★ 能从市场把 alpha 装回来", "alpha" in r_back["added"], str(r_back["added"]))
    ck("装回来之后重新记了所有权",
       "alpha" in core.load_ownership()["skills"])

    # ============ 8. 文件锁 ============
    section("8. 文件锁")
    lk = core.FileLock(core.LOCK_PATH, timeout=1.0)
    with lk:
        with lk:
            ck("同线程可重入", True)

    holder_ready = threading.Event()
    holder_release = threading.Event()

    def hold():
        with core.FileLock(core.LOCK_PATH, timeout=5.0):
            holder_ready.set()
            holder_release.wait(5)

    th = threading.Thread(target=hold, daemon=True)
    th.start()
    holder_ready.wait(3)
    t_start = time.time()
    try:
        with core.FileLock(core.LOCK_PATH, timeout=0.8):
            ck("★ 他人持锁时应该等锁超时", False, "居然拿到了锁")
    except core.FileLockTimeout:
        ck("★ 他人持锁时等锁超时", True, f"{time.time() - t_start:.2f}s")
    holder_release.set()
    th.join(5)

    t_start = time.time()
    with core.FileLock(core.LOCK_PATH, timeout=0.8):
        pass
    ck("释放后能立刻拿到", time.time() - t_start < 0.5)

    # ============ 9. 日志：真 tail + 轮转 ============
    section("9. 日志 tail 与轮转")
    for i in range(500):
        core.log("info", "bulk", f"line-{i}")
    items = core.tail_log(20)
    ck("tail_log 只取最后 N 条", len(items) == 20, str(len(items)))
    ck("tail_log 取到的是最新的", items[0]["detail"] == "line-499", items[0]["detail"])
    ck("tail_log 是倒序（最新在前）", items[0]["detail"] > items[-1]["detail"])

    core.LOG_PATH.write_text(
        "\n".join(json.dumps({"at": "x", "level": "info", "event": "e", "detail": str(i)})
                  for i in range(200_000)) + "\n", encoding="utf-8")
    t_start = time.time()
    core.tail_log(10)
    ck("20 万行日志 tail 仍然很快", time.time() - t_start < 0.5, f"{time.time() - t_start:.3f}s")

    core.LOG_PATH.write_text("x" * (core.LOG_MAX_BYTES + 1024), encoding="utf-8")
    core.log("info", "rotate", "should trigger")
    rotated = core.LOG_PATH.with_name(f"{core.LOG_PATH.stem}.1{core.LOG_PATH.suffix}")
    ck("★ 超限自动轮转为 .1", rotated.is_file())
    ck("轮转后当前日志变小", core.LOG_PATH.stat().st_size < core.LOG_MAX_BYTES)

    # ============ 10. 回收站生命周期 ============
    section("10. 回收站清理")
    ck("回收站里有前面卸载留下的东西", core.trash_stats()["count"] >= 2,
       str(core.trash_stats()["count"]))
    r = core.prune_trash()
    ck("按策略清理不动未过期项", r["removed"] == 0, str(r))
    r = core.prune_trash(force=True)
    ck("★ --purge-trash 清空回收站",
       r["removed"] >= 2 and core.trash_stats()["count"] == 0, str(r))

    d = core.TRASH_DIR / "20300101-000000__old__probe"
    d.mkdir(parents=True, exist_ok=True)
    (d / "f.txt").write_text("old", encoding="utf-8")
    long_ago = time.time() - 99 * 86400
    os.utime(d, (long_ago, long_ago))
    r = core.prune_trash()
    ck("超保留天数的会被清掉", r["removed"] == 1, str(r))

    # ============ 11. strict JSON ============
    section("11. 配置损坏时的可诊断性")
    good = core.CONFIG_PATH.read_text(encoding="utf-8")
    core.CONFIG_PATH.write_text('{"marketId": "x",,}', encoding="utf-8")
    try:
        core.load_config()
        ck("坏配置应该抛错", False, "居然没抛")
    except core.ConfigError as exc:
        ck("★ 坏配置抛出 ConfigError 且带定位", "合法 JSON" in str(exc), str(exc)[:70])
    ck("容错读仍返回默认值",
       core.read_json(core.CONFIG_PATH, {"fallback": 1}) == {"fallback": 1})
    core.CONFIG_PATH.write_text(good, encoding="utf-8")
    ck("配置已还原", core.load_config()["marketId"] == "test-market")

    # ============ 12. 深度自检的发现能力 ============
    section("12. 深度自检的发现能力")
    core.sync_packaging(quiet=True)
    ok, errs, _w = core.deep_check()
    ck("干净状态下无 error", ok, "; ".join(errs[:3]))

    pj_path = core.PLUGINS_DIR / "bundle-one" / ".codebuddy-plugin" / "plugin.json"
    pj_data = json.loads(pj_path.read_text(encoding="utf-8"))
    pj_data["version"] = "9.9.9"
    pj_path.write_text(json.dumps(pj_data, ensure_ascii=False), encoding="utf-8")
    ok, errs, _w = core.deep_check()
    ck("★ 检出 plugin.json 版本不一致", not ok and any("版本不一致" in e for e in errs),
       "; ".join(errs[:2]))

    core.sync_packaging(quiet=True)
    shutil.rmtree(core.PLUGINS_DIR / "bundle-two" / "skills" / "gamma")
    ok, errs, _w = core.deep_check()
    ck("★ 检出「配置声明但未打包」", not ok and any("gamma" in e for e in errs),
       "; ".join(errs[:2]))

    core.sync_packaging(quiet=True)
    m = json.loads(core.MANIFEST_PATH.read_text(encoding="utf-8"))
    m["plugins"].append({"name": "ghost", "version": "1.0.0",
                         "source": "./plugins/ghost", "description": "d"})
    core.MANIFEST_PATH.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    ok, errs, warns = core.deep_check()
    ck("索引里多余的插件只报警告", any("ghost" in w for w in warns), "; ".join(warns[:2]))
    core.sync_packaging(quiet=True)

    # ============ 13. 注册/撤销 ============
    section("13. 注册与撤销")
    core.KNOWN_PATH.parent.mkdir(parents=True, exist_ok=True)
    core.KNOWN_PATH.write_text(json.dumps(
        {"other-market": {"manifestName": "other-market", "type": "zip", "lastUpdated": "T0"}},
        ensure_ascii=False), encoding="utf-8")

    ck("注册成功", core.register() is True)
    ck("重复注册幂等（返回 False）", core.register() is False)
    known = json.loads(core.KNOWN_PATH.read_text(encoding="utf-8"))
    ck("本市场条目类型为 directory", known["test-market"]["type"] == "directory")
    ck("installLocation 指向市场根",
       Path(known["test-market"]["installLocation"]).resolve() == core.MARKET_ROOT)

    n0 = len(list(core.BACKUP_DIR.glob("known_marketplaces.*.json")))
    core.backup_known()
    core.backup_known()
    n1 = len(list(core.BACKUP_DIR.glob("known_marketplaces.*.json")))
    ck("★ 同一秒两次备份都留下（纳秒戳）", n1 == n0 + 2, f"{n0} → {n1}")

    others_before = {k: v for k, v in known.items() if k != "test-market"}
    core.unregister()
    after = json.loads(core.KNOWN_PATH.read_text(encoding="utf-8"))
    ck("撤销只删自己那一条", set(after) == set(others_before))
    ck("撤销未改动别的市场", after == others_before)
    core.register()
    after2 = json.loads(core.KNOWN_PATH.read_text(encoding="utf-8"))
    ck("再注册后别的市场仍原样",
       {k: v for k, v in after2.items() if k != "test-market"} == others_before)

    # ============ 14. 状态与界面数据 ============
    section("14. 状态结构")
    st = core.build_state()
    for f in ("marketId", "registered", "plugins", "remotes", "stats", "trash", "categories"):
        ck(f"state 含 {f}", f in st)
    u = st["plugins"][0]["uninstall"]
    ck("state 带卸载分级", set(u) >= {"counts", "removable", "modified", "untouched"})
    ck("state 带回收站信息", "policy" in st["trash"] and "count" in st["trash"])
    ck("skillDetail 覆盖全部 skill",
       all(len(p["skillDetail"]) == len(p["skills"]) for p in st["plugins"]))

    # ============ 15. 其他 ============
    section("15. 其他")
    iso = core.now_iso()
    ck("now_iso 带时区", "T" in iso and ("+" in iso or iso.endswith("Z")), iso)
    probe = write_fake_skill(core.SKILLS_DIR, "meta-probe", "3.4.5", "探针", {})
    ck("parse_skill_meta 读到版本", core.parse_skill_meta(probe)["version"] == "3.4.5",
       core.parse_skill_meta(probe)["version"])
    ck("tree_hash 与内容相关",
       core.tree_hash(core.SKILLS_DIR / "beta") != core.tree_hash(core.SKILLS_DIR / "gamma"))
    ck("插件目录确实在市场根之下",
       core.MARKET_ROOT in (core.PLUGINS_DIR / "bundle-one").resolve().parents)

