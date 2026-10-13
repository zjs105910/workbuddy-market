# -*- coding: utf-8 -*-
"""第 16-18 节：故障注入（出错时数据必须还在）/ 异常状态安全 / 打包扫描次数。"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from . import _drop_link, _make_link, ck, core, section, wm


def faults():
    """故障注入：出错时数据必须还在。"""
    section("16. 故障注入：出错时数据必须还在")

    # --- A. 两阶段安装：复制中途失败，旧版本必须原样还在
    core.sync_packaging(quiet=True)
    core.install_local_plugin("bundle-one", "force")        # 确保归本市场并刷新记录
    (core.SKILLS_DIR / "alpha" / "notes.md").write_text("# edited by user\n", encoding="utf-8")
    core.sync_packaging(quiet=True)
    d_alpha = core.SKILLS_DIR / "alpha"
    before_hash = core.tree_hash(d_alpha)
    before_files = sorted(core._scan(d_alpha)[0])

    real_copytree = shutil.copytree

    def boom(*a, **k):
        raise OSError("模拟磁盘写失败")

    shutil.copytree = boom
    try:
        r = core.install_local_plugin("bundle-one", "update")
    finally:
        shutil.copytree = real_copytree

    ck("复制失败被记进 failed", bool(r["failed"]) and "alpha" in r["failed"][0],
       str(r["failed"])[:80])
    ck("★ 失败后本机 skill 仍在", d_alpha.is_dir() and (d_alpha / "SKILL.md").is_file())
    ck("★ 旧版本内容一字未改", core.tree_hash(d_alpha) == before_hash)
    ck("★ 旧版本文件清单未变", sorted(core._scan(d_alpha)[0]) == before_files)
    ck("★ 没留下暂存目录", not list(core.SKILLS_DIR.glob(".*.installing-*")))

    # 恢复后 update 要能正常成功
    r2 = core.install_local_plugin("bundle-one", "update")
    ck("恢复后 update 正常成功", "alpha" in r2["updated"], str(r2["updated"]))

    # --- B. known_marketplaces.json 损坏：必须拒绝写，原文件分毫不动
    core.KNOWN_PATH.parent.mkdir(parents=True, exist_ok=True)
    core.KNOWN_PATH.write_text('{"aaa-market": {"manifestName"', encoding="utf-8")
    snapshot = core.KNOWN_PATH.read_bytes()
    try:
        core.register()
        ck("★ known 损坏时 register 必须失败", False, "居然成功了")
    except RuntimeError as exc:
        ck("★ known 损坏时 register 拒绝覆盖", "拒绝覆盖" in str(exc), str(exc)[:46])
    ck("★ 损坏文件被原样保留，没被覆盖", core.KNOWN_PATH.read_bytes() == snapshot)
    try:
        core.unregister()
        ck("★ known 损坏时 unregister 也必须失败", False, "居然成功了")
    except RuntimeError:
        ck("★ known 损坏时 unregister 拒绝覆盖", True)
    ck("★ unregister 也没动那个坏文件", core.KNOWN_PATH.read_bytes() == snapshot)

    # 修好之后一切照旧，且别的市场不能丢
    core.KNOWN_PATH.write_text(json.dumps(
        {"aaa-market": {"manifestName": "aaa-market", "type": "zip"}}, ensure_ascii=False),
        encoding="utf-8")
    ck("修好后 register 恢复正常", core.register() is True)
    after = json.loads(core.KNOWN_PATH.read_text(encoding="utf-8"))
    ck("★ 原有的 aaa-market 还在", "aaa-market" in after, str(list(after)))

    # --- C. 路径穿越：非法 id 与越界配置一律拒绝
    bad_ids = ["../evil", "../../evil", "foo/../bar", "a/b", "a\\b", "..", ".",
               "", "  x", "C:evil", "/abs", "NUL", "con.txt", "x" * 200, "a\tb"]
    rejected = 0
    for v in bad_ids:
        try:
            core.validate_id(v, "t")
        except core.ConfigError:
            rejected += 1
    ck("★ 非法 id 全部被拒", rejected == len(bad_ids), f"{rejected}/{len(bad_ids)}")
    try:
        for v in ["alpha", "story-long-write", "a.b_c-d", "A1", "x" * 128]:
            core.validate_id(v, "t")
        ck("合法 id 全部通过", True)
    except core.ConfigError as exc:
        ck("合法 id 全部通过", False, str(exc))

    good_cfg = core.CONFIG_PATH.read_text(encoding="utf-8")

    def try_cfg(mutate, label):
        c = json.loads(good_cfg)
        mutate(c)
        core.CONFIG_PATH.write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
        try:
            core.load_config()
            ck(f"★ 拒绝：{label}", False, "居然加载成功了")
        except core.ConfigError:
            ck(f"★ 拒绝：{label}", True)

    try_cfg(lambda c: c["localPlugins"][0].update({"skills": ["../escape-skill"]}),
            "配置里的越界 skill 名")
    try_cfg(lambda c: c["localPlugins"][0].update({"name": "../escape"}),
            "配置里的越界插件名")
    try_cfg(lambda c: c["localPlugins"][1].update({"name": c["localPlugins"][0]["name"]}),
            "插件重名")
    try_cfg(lambda c: c["localPlugins"][1]["skills"].append(c["localPlugins"][0]["skills"][0]),
            "同一个 skill 被两个插件声明")
    try_cfg(lambda c: c["remoteSources"][0].update({"repo": "not-a-repo"}), "repo 不是 owner/repo")
    try_cfg(lambda c: c.update({"marketId": "../m"}), "marketId 越界")
    try_cfg(lambda c: c["localPlugins"][0].update({"version": ""}), "版本号非法")
    try_cfg(lambda c: c["marketId"] and c.pop("marketId"), "缺少 marketId")
    try_cfg(lambda c: c["localPlugins"][0].update({"skills": []}), "skills 为空")
    try_cfg(lambda c: c.update({"trash": {"maxAgeDays": -1}}), "trash 阈值是负数")

    # --- C2. 大小写碰撞：Windows 文件系统不区分大小写，全平台统一拒绝
    try_cfg(lambda c: c["localPlugins"][0].update({"skills": ["alpha", "Alpha"]}),
            "同一插件内 skill 名只差大小写")
    try_cfg(lambda c: c["localPlugins"].append(
        {"name": "BUNDLE-ONE", "version": "1.0.0", "description": "d", "skills": ["delta"]}),
        "插件名只差大小写")
    try_cfg(lambda c: c["localPlugins"][1]["skills"].append("ALPHA"),
            "skill 跨插件只差大小写")
    try_cfg(lambda c: c["remoteSources"].append({"repo": "Owner/Repo"}),
            "远端源只差大小写")

    try_cfg(lambda c: c.update({"packaging": {"verify": "sometimes"}}),
            "packaging.verify 取值非法")
    try_cfg(lambda c: c.update({"packaging": {"hashChunkBytes": 12}}),
            "hashChunkBytes 太小")
    try_cfg(lambda c: c.update({"trash": {"protectModified": "yes"}}),
            "protectModified 不是布尔")

    core.CONFIG_PATH.write_text(good_cfg, encoding="utf-8")
    ck("配置已还原", core.load_config()["marketId"] == "test-market")

    # --- D. 软链 / junction：绝不跟随
    outside = core.MARKET_ROOT.parent / "OUTSIDE-SECRET"
    outside.mkdir(parents=True, exist_ok=True)
    (outside / "secret.txt").write_text("TOPSECRET", encoding="utf-8")
    sk = core.SKILLS_DIR / "gamma"          # gamma 归 bundle-two
    link = sk / "leak"
    kind = _make_link(outside, link)
    if kind:
        links_seen = core._scan(sk)[1]
        ck(f"★ _scan 能报出重解析点（{kind}）", len(links_seen) >= 1, str(links_seen)[:70])
        core.sync_packaging(quiet=True)
        leaked = core.PLUGINS_DIR / "bundle-two" / "skills" / "gamma" / "leak"
        ck(f"★ {kind} 未被跟随（外部内容没进市场）", not leaked.exists(), str(leaked))
        ck("★ 市场里也搜不到那个外部文件名",
           not any(p.name == "secret.txt" for p in core.PLUGINS_DIR.rglob("*")))
        _drop_link(link)
    else:
        ck("软链/junction 测试：本环境建不出重解析点，已跳过（不是通过）", True,
           "os.symlink 被宿主拦成普通文件")
    shutil.rmtree(outside, ignore_errors=True)

    # --- E. fast / strict 两级一致性
    def set_verify(mode):
        c = json.loads(core.CONFIG_PATH.read_text(encoding="utf-8"))
        c["packaging"] = {"excludeNames": ["__pycache__"], "excludeGlobs": ["*.bak"],
                          "verify": mode}
        core.CONFIG_PATH.write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")

    set_verify("fast")
    core.sync_packaging(quiet=True)
    s_file = core.SKILLS_DIR / "alpha" / "notes.md"
    d_file = core.PLUGINS_DIR / "bundle-one" / "skills" / "alpha" / "notes.md"

    # E1 内容一样、只是时间戳不同
    d_file.write_bytes(s_file.read_bytes())
    old = time.time() - 500
    os.utime(d_file, (old, old))
    rf = core.sync_packaging(quiet=True)
    ck("fast：时间戳变了就重拷", rf["copiedFiles"] >= 1, str(rf["copiedFiles"]))
    ck("report 标明 verify=fast", rf.get("verify") == "fast")

    set_verify("strict")
    d_file.write_bytes(s_file.read_bytes())
    os.utime(d_file, (old, old))
    rs = core.sync_packaging(quiet=True)
    ck("★ strict：内容一样就不重拷", rs["copiedFiles"] == 0, str(rs["copiedFiles"]))
    ck("report 标明 verify=strict", rs.get("verify") == "strict")

    # E2 大小与时间戳都被对齐，但内容不同
    # 注意：os.utime 传浮点秒会丢亚秒精度，必须用 ns= 才能把 st_mtime_ns 对齐
    st = s_file.stat()
    d_file.write_bytes(b"X" * st.st_size)
    os.utime(d_file, ns=(st.st_atime_ns, st.st_mtime_ns))
    ck("（构造）两边大小与时间戳完全一致", d_file.stat().st_size == st.st_size
       and d_file.stat().st_mtime_ns == st.st_mtime_ns)
    set_verify("fast")
    rf2 = core.sync_packaging(quiet=True)
    ck("（对照）fast 会漏检这种内容差异", rf2["copiedFiles"] == 0, str(rf2["copiedFiles"]))
    set_verify("strict")
    d_file.write_bytes(b"X" * st.st_size)
    os.utime(d_file, ns=(st.st_atime_ns, st.st_mtime_ns))
    rs2 = core.sync_packaging(quiet=True)
    ck("★ strict 检出「时间戳一样但内容不同」", rs2["copiedFiles"] >= 1, str(rs2["copiedFiles"]))
    ck("内容已修正", d_file.read_bytes() == s_file.read_bytes())
    set_verify("fast")

    # --- F. 回收站索引：不再每次遍历回收站
    probe = core.SKILLS_DIR / "trash-probe"
    probe.mkdir(parents=True, exist_ok=True)
    for i in range(50):
        (probe / f"f{i}.txt").write_text("z" * 50, encoding="utf-8")
    core.move_to_trash(probe, "probe")
    stp = core.trash_stats()
    ck("★ 回收站索引记下了体积",
       any(i["name"].endswith("trash-probe__probe") and i["size"] > 0 for i in stp["items"]),
       str([i["name"] for i in stp["items"]])[:80])
    ck("★ 索引文件本身不出现在列表里",
       all(i["name"] != ".index.json" for i in stp["items"]))

    stat_calls = {"n": 0}
    real_stat = Path.stat

    def counting_stat(self, *a, **k):
        stat_calls["n"] += 1
        return real_stat(self, *a, **k)

    Path.stat = counting_stat
    try:
        t0 = time.time()
        core.trash_stats()
        el = time.time() - t0
    finally:
        Path.stat = real_stat
    ck("★ 读过索引后不再递归回收站", stat_calls["n"] < 200,
       f"{stat_calls['n']} 次 stat / {el * 1000:.1f}ms")

    # 手工往回收站塞东西 → 应被自动补录
    manual = core.TRASH_DIR / "manual-thing"
    manual.mkdir(parents=True, exist_ok=True)
    (manual / "x.txt").write_text("m", encoding="utf-8")
    stp2 = core.trash_stats()
    ck("★ 手工放进回收站的东西会被补录",
       any(i["name"] == "manual-thing" for i in stp2["items"]))
    ck("补录后落盘进索引",
       "manual-thing" in json.loads(core.TRASH_INDEX_PATH.read_text(encoding="utf-8"))["items"])

    # --- G. 所有权快速指纹：状态检查不再全量读文件
    core.install_local_plugin("bundle-one", "force")
    own = core.load_ownership()["skills"]
    tracked = [s for s in ("alpha", "beta") if s in own]
    ck("★ 所有权记录带快速指纹",
       bool(tracked) and all(isinstance(own[s].get("fingerprint"), dict) for s in tracked),
       str(tracked))

    reads = {"n": 0}
    real_rb = Path.read_bytes

    def counting_read(self):
        reads["n"] += 1
        return real_rb(self)

    Path.read_bytes = counting_read
    try:
        core.plugin_uninstall_plan("bundle-one")
    finally:
        Path.read_bytes = real_rb
    ck("★ 未改动时不再读文件算 SHA-256（走指纹快路径）", reads["n"] == 0,
       f"{reads['n']} 次 read_bytes")

    # 改了内容之后，指纹对不上，必须回到完整哈希并判为 modified
    (core.SKILLS_DIR / "alpha" / "notes.md").write_text("# tampered\n", encoding="utf-8")
    plan = core.plugin_uninstall_plan("bundle-one", purpose="uninstall")
    ck("★ 内容被改后仍能判为 modified", plan["modified"] == ["alpha"], str(plan["modified"]))

    # ================================================================
    section("17. 第三轮评审：故意构造异常状态也必须是安全的")

    # --- 17A. 快速指纹：从「理论上安全」推进到「构造也安全」
    core.sync_packaging(quiet=True)
    core.install_local_plugin("bundle-one", "force")
    d_alpha = core.SKILLS_DIR / "alpha"
    sk = d_alpha / "SKILL.md"
    victim = d_alpha / "old-note.md"

    # 造一个「很旧的」文件，让它的 mtime 永远不是最大值
    old_t = time.time() - 5000
    victim.write_text("AAAAAAAA", encoding="utf-8")
    os.utime(victim, (old_t, old_t))
    # 让另一个文件坐稳「最大 mtime」的位置（真实场景里通常是最近改过的文件）
    os.utime(sk, (time.time() + 100, time.time() + 100))
    core.record_owner("bundle-one", ["alpha"], "1.0.0")

    fp0 = core.load_ownership()["skills"]["alpha"]["fingerprint"]
    hash0 = core.load_ownership()["skills"]["alpha"]["hash"]
    ck("★ 指纹含 mtime_ns 聚合维度", "mtime_ns_sum" in fp0, str(sorted(fp0)))

    # 常见情况：改 victim（等长），mtime 跟着变，但最大值仍由 SKILL.md 贡献
    victim.write_text("BBBBBBBB", encoding="utf-8")
    fp1 = core.quick_fingerprint(d_alpha)
    ck("（构造）文件数 / 总字节 / 最大 mtime 三者全都没变",
       fp1["files"] == fp0["files"] and fp1["bytes"] == fp0["bytes"]
       and fp1["mtime_ns_max"] == fp0["mtime_ns_max"],
       f"{fp1['files']}/{fp1['bytes']}/{fp1['mtime_ns_max']}")
    ck("★ mtime_ns_sum 变了 → 新指纹当场抓到（v2 只看 max，抓不到）",
       fp1["mtime_ns_sum"] != fp0["mtime_ns_sum"])
    plan_ui = core.plugin_uninstall_plan("bundle-one", purpose="ui")
    ck("★ 网页判定：改了但最大值没变，也判 modified",
       plan_ui["modified"] == ["alpha"], str(plan_ui["modified"]))

    # 极端情况：连 mtime 都压回原值 —— 指纹被完全伪造
    os.utime(victim, (old_t, old_t))
    fp2 = core.quick_fingerprint(d_alpha)
    ck("（构造）指纹被完全伪造：连聚合维度都一致", fp2 == fp0, str(fp2))
    ck("（对照）但内容确实已经不同", core.tree_hash(d_alpha) != hash0)
    ck("★ install 用途仍判 modified（读内容，不看指纹）",
       core.classify_skill("bundle-one", "alpha", core.load_config(),
                           purpose="install")["kind"] == "modified")
    ck("★ uninstall 用途仍判 modified（读内容，不看指纹）",
       core.classify_skill("bundle-one", "alpha", core.load_config(),
                           purpose="uninstall")["kind"] == "modified")
    ck("★ ui 用途允许走指纹（快，误差可容忍）",
       core.classify_skill("bundle-one", "alpha", core.load_config(),
                           purpose="ui")["checked"] == "fingerprint")

    # 真正跑一次 update：v2 会因为指纹相同而跳过，v2.1 必须覆盖
    r_up = core.install_local_plugin("bundle-one", "update")
    ck("★ update 真的覆盖了「被改过但指纹被伪造」的 skill",
       "alpha" in r_up["updated"], str({k: r_up[k] for k in ("updated", "skipped")}))
    ck("★ 覆盖后回到 safe",
       core.classify_skill("bundle-one", "alpha", core.load_config(),
                           purpose="uninstall")["kind"] == "safe")

    # --- 17B. 回收站索引：路径穿越
    victim_in = core.MARKET_ROOT / "TRAVERSAL-VICTIM"
    victim_out = core.MARKET_ROOT.parent / "TRAVERSAL-VICTIM2"
    for v in (victim_in, victim_out):
        v.mkdir(parents=True, exist_ok=True)
        (v / "keep.txt").write_text("keep me", encoding="utf-8")

    ck("★ _trash_entry 拒绝一切带路径成分的名字",
       all(core._trash_entry(v) is None for v in
           ["../TRAVERSAL-VICTIM", "../../TRAVERSAL-VICTIM2", "..", ".", "a/b",
            "..\\win", "C:evil", "", None, 5, ".index.json"]))
    ck("★ _trash_entry 接受合法 basename",
       core._trash_entry("20260101-000000__alpha__uninstall") is not None)

    core.TRASH_DIR.mkdir(parents=True, exist_ok=True)
    evil_index = {
        "version": 1,
        "items": {
            "../TRAVERSAL-VICTIM": {"bytes": 7, "at": time.time(), "reason": "evil"},
            "../../TRAVERSAL-VICTIM2": {"bytes": 7, "at": time.time(), "reason": "evil"},
            "..": {"bytes": 1, "at": time.time(), "reason": "evil"},
            "a/b": {"bytes": 1, "at": time.time(), "reason": "evil"},
        },
    }
    core.TRASH_INDEX_PATH.write_text(json.dumps(evil_index), encoding="utf-8")

    st_evil = core.trash_stats()
    ck("★ 非法条目名不进状态列表",
       all(i["name"] not in evil_index["items"] for i in st_evil["items"]),
       str([i["name"] for i in st_evil["items"]])[:80])
    ck("★ 非法条目被剔出索引",
       not any(n in core._load_trash_index()["items"] for n in evil_index["items"]))

    # 再来一次，这次不走 trash_stats 的清洗，直接让 prune 面对脏索引
    core.TRASH_INDEX_PATH.write_text(json.dumps(evil_index), encoding="utf-8")
    core.prune_trash(force=True, quiet=True)
    ck("★ ★ prune_trash 没删到 .trash 之外的一级目录",
       victim_in.exists() and (victim_in / "keep.txt").is_file(), str(victim_in))
    ck("★ ★ prune_trash 也没删到市场根之外",
       victim_out.exists() and (victim_out / "keep.txt").is_file(), str(victim_out))

    # --- 17C. 配置大小写碰撞已在上面的 try_cfg 覆盖，这里验证运行时口径
    ck("★ collision_key 归一大小写",
       core.collision_key("Story") == core.collision_key("story") == "story")

    # --- 17D. 删除失败时统计必须诚实
    core.prune_trash(force=True, quiet=True)
    d_ok = core.TRASH_DIR / "20260101-000000__deletable"
    d_bad = core.TRASH_DIR / "20260101-000001__undeletable"
    for p in (d_ok, d_bad):
        p.mkdir(parents=True, exist_ok=True)
        (p / "f.bin").write_bytes(b"x" * 100)
    core.trash_stats()                       # 补录进索引

    real_rmtree = shutil.rmtree

    def rmtree_fail_on_bad(path, *a, **k):
        if "undeletable" in str(path):
            raise OSError("模拟删除失败")
        return real_rmtree(path, *a, **k)

    shutil.rmtree = rmtree_fail_on_bad
    try:
        r_del = core.prune_trash(force=True, quiet=True)
    finally:
        shutil.rmtree = real_rmtree

    ck("★ 删除失败不虚报：removed 只数真删掉的", r_del["removed"] == 1, str(r_del))
    ck("★ 失败项进 failed 且带原因",
       r_del["failed"] == 1 and "undeletable" in str(r_del["failedItems"]),
       str(r_del["failedItems"])[:90])
    ck("★ freed 只累加真删掉的（100 字节，不是 200）",
       r_del["freed"] == 100, str(r_del["freed"]))
    ck("★ 删失败的目录原样还在", d_bad.exists() and (d_bad / "f.bin").is_file())
    real_rmtree(d_bad, ignore_errors=True)

    # --- 17E. 索引写失败：磁盘状态如实上报，后续自愈
    core.prune_trash(force=True, quiet=True)
    core.sync_packaging(quiet=True)
    core.install_local_plugin("bundle-one", "force")
    # 先把索引写成一张空表，这样「索引是否过期」可以直接读文件验证
    core.TRASH_DIR.mkdir(parents=True, exist_ok=True)
    core.TRASH_INDEX_PATH.write_text(
        json.dumps({"version": 1, "items": {}}), encoding="utf-8")

    real_save = wm.trash._save_trash_index

    def save_boom(_idx):
        raise OSError("模拟 .index.json 写入失败")

    wm.trash._save_trash_index = save_boom
    try:
        t = core.move_to_trash(core.SKILLS_DIR / "alpha", "reinstall")
    finally:
        wm.trash._save_trash_index = real_save

    ck("★ ★ 索引写失败时不再把整体判为失败（rename 已生效）",
       t is not None and Path(t).exists(), str(t))
    ck("★ 旧版本确实已经搬进回收站，内容完好",
       not (core.SKILLS_DIR / "alpha").exists() and (Path(t) / "SKILL.md").is_file())
    ck("★ 索引文件仍然停在旧内容（dirty，但数据没丢）",
       "alpha" not in json.loads(core.TRASH_INDEX_PATH.read_text(encoding="utf-8"))["items"])

    st_heal = core.trash_stats()
    healed = [i["name"] for i in st_heal["items"] if "alpha" in i["name"]]
    ck("★ ★ 下次状态刷新自动补录（自愈）", bool(healed), str(healed))
    ck("★ 补录结果落盘进索引",
       all(n in json.loads(core.TRASH_INDEX_PATH.read_text(encoding="utf-8"))["items"]
           for n in healed))

    # 整条安装流程同样不能被索引写失败带崩
    core.install_local_plugin("bundle-one", "force")     # 先把 alpha 装回来
    wm.trash._save_trash_index = save_boom
    try:
        r_fs = core.install_local_plugin("bundle-one", "force")
    finally:
        wm.trash._save_trash_index = real_save
    ck("★ 索引写失败时安装仍报告成功",
       r_fs["ok"] and "alpha" in (r_fs["added"] + r_fs["updated"]), str(r_fs.get("added")))
    ck("★ 且新版本已正确落位",
       (core.SKILLS_DIR / "alpha" / "SKILL.md").is_file())

    # --- 17F. 安装阶段拒绝重解析点（defense-in-depth）
    core.sync_packaging(quiet=True)
    outside2 = core.MARKET_ROOT.parent / "OUTSIDE-INSTALL"
    outside2.mkdir(parents=True, exist_ok=True)
    (outside2 / "secret.txt").write_text("TOPSECRET", encoding="utf-8")
    pkg_alpha = core.PLUGINS_DIR / "bundle-one" / "skills" / "alpha"
    link = pkg_alpha / "leak"
    kind = _make_link(outside2, link)
    if kind:
        r_ln = core.install_local_plugin("bundle-one", "force")
        ck(f"★ 市场产物里的 {kind} 导致该 skill 安装被拒",
           any("alpha" in f and "链接" in f for f in r_ln["failed"]), str(r_ln["failed"])[:100])
        ck("★ 外部内容没有被复制进 skills 目录",
           not any(p.name == "secret.txt" for p in core.SKILLS_DIR.rglob("*")))
        _drop_link(link)
    else:
        ck("安装期链接测试：本环境建不出重解析点，已跳过（不是通过）", True,
           "os.symlink 被宿主拦成普通文件")
    shutil.rmtree(outside2, ignore_errors=True)
    shutil.rmtree(victim_in, ignore_errors=True)
    shutil.rmtree(victim_out, ignore_errors=True)
    core.sync_packaging(quiet=True)

    # --- 17G. 流式 SHA-256：结果不变，内存不再随文件大小
    probe_dir = core.SKILLS_DIR / "hash-probe"
    probe_dir.mkdir(parents=True, exist_ok=True)
    blob = probe_dir / "a.bin"
    blob.write_bytes(bytes(range(256)) * 4000)          # ≈ 1 MB

    h_read = hashlib.sha256(blob.read_bytes()).digest()
    ck("★ sha256_file 与整体读的结果一致", core.sha256_file(blob) == h_read)
    ck("★ 分块大小不影响哈希结果",
       core.sha256_file(blob, 4096) == core.sha256_file(blob, 1 << 20) == h_read)
    ck("★ tree_hash 默认块大小来自配置", core.hash_chunk_bytes() == 1 << 20,
       str(core.hash_chunk_bytes()))

    reads_hash = {"n": 0}
    real_read_bytes = Path.read_bytes

    def counting_read_bytes(self):
        reads_hash["n"] += 1
        return real_read_bytes(self)

    Path.read_bytes = counting_read_bytes
    try:
        th = core.tree_hash(probe_dir)
        core.sha256_file(blob)
    finally:
        Path.read_bytes = real_read_bytes
    ck("★ ★ 哈希全程不调用 read_bytes（内存 O(块) 而非 O(文件)）",
       reads_hash["n"] == 0, f"{reads_hash['n']} 次 read_bytes")
    ck("★ tree_hash 结果与内容相关",
       th != core.tree_hash(core.SKILLS_DIR / "beta"))
    shutil.rmtree(probe_dir, ignore_errors=True)

    # ================================================================
    section("18. 打包扫描次数：destination 每插件只扫一次")

    core.sync_packaging(quiet=True)
    calls = {"n": 0}
    real_scan = core._scan

    def counting_scan(root, excluded=None, **kw):
        calls["n"] += 1
        return real_scan(root, excluded, **kw)

    # 注意：树哈希也走 _scan，所以这里只统计「内容没变」的稳态同步 ——
    # 稳态下不该有任何 tree_hash 调用，计数就纯粹反映目录遍历次数。
    core._scan = counting_scan
    try:
        rep_scan = core.sync_packaging(quiet=True)
    finally:
        core._scan = real_scan

    n_skills = rep_scan["totalSkills"]
    naive = 2 * n_skills                   # v2：每个 skill 各扫源 + 各扫目标
    ck(f"★ 扫描次数低于「每 skill 两次」({calls['n']} < {naive})",
       calls["n"] < naive, f"{calls['n']} 次 / {n_skills} skill")
    ck("★ 目标目录按插件整树扫（源 N 次 + 目标 1 次/插件）",
       calls["n"] <= n_skills + len(rep_scan["plugins"]),
       f"{calls['n']} <= {n_skills} + {len(rep_scan['plugins'])}")


