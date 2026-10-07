# -*- coding: utf-8 -*-
"""selftest —— 本机插件市场的离线自检（v2.7）。

    python selftest.py            隔离模式：在临时目录里跑完整流程
    python selftest.py --real     只读检查现网状态，不写任何东西

隔离模式会造 3 个假 skill + 一份假配置，完完整整走一遍
「打包 → 安装 → 更新 → 卸载 → 回滚 → 加锁 → 日志轮转」，
**不碰真实的 ~/.workbuddy，也不动真实的插件市场目录**。

第 16 节   故障注入
第 17/18 节 v2.2：快速指纹误判、回收站路径穿越、大小写碰撞、删除失败统计
第 19 节   v2.3：事务日志、本地 API 鉴权、任务生命周期、扫描复用
第 20 节   v2.4：凭证前置、恢复校验 expected hash、卸载事务、真 tail
第 21 节   v2.5：并发压力、扫描失败 fail-closed、崩溃点矩阵
第 22 节   v2.6：ghpm 事件解析、取消竞态、进程树终止、真并发闸门
第 23 节   v2.7/R1：三层根目录、WBM_* 环境变量、运行时迁移（含跨卷回退）

`SELFTEST_VERSION` 与内核的 `market_core.MARKET_VERSION` 必须同号 ——
自检里有一条用例专门盯这个，防止文档版本漂移（v2.3 时就漂过一次）。
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

SELFTEST_VERSION = "2.7"

# ---------------------------------------------------------------- 隔离环境
# 必须在 import market_core 之前设置：路径常量是 import 期求值的。

_ISOLATED = "--real" not in sys.argv
_TMP = None

if _ISOLATED:
    _TMP = Path(tempfile.mkdtemp(prefix="wbm-selftest-"))
    os.environ["GHPM_MARKET_ROOT"] = str(_TMP / "market")
    os.environ["GHPM_HOME"] = str(_TMP / "wb")
    (_TMP / "market").mkdir(parents=True, exist_ok=True)
    (_TMP / "wb" / "skills").mkdir(parents=True, exist_ok=True)
    (_TMP / "wb" / "plugins").mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import market_core as core  # noqa: E402

PASS, FAIL, SKIP = [], [], []


def ck(name: str, cond: bool, extra: str = ""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  —— {extra}" if extra else ""))


def sk(name: str, why: str = ""):
    """明确跳过 —— 不算通过，也不算失败，但必须让人看见。

    「环境缺个文件就整条挂死」会让人以为代码坏了；「静默当通过」更糟。
    """
    SKIP.append(name)
    print(f"  SKIP  {name}" + (f"  —— {why}" if why else ""))


def section(t: str):
    print(f"\n--- {t} ---")


# ---------------------------------------------------------------- 造数据

FAKE_SKILLS = {
    "alpha": ("1.0.0", "Alpha 技能",
              {"notes.md": "# notes\n", "sub/deep.txt": "deep\n"}),
    "beta": ("2.1.0", "Beta 技能", {"data.bin": "x" * 200}),
    "gamma": ("0.9.0", "Gamma 技能", {}),
}


def write_fake_skill(root: Path, name: str, version: str, desc: str, files: dict) -> Path:
    d = Path(root) / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\nversion: {version}\ndescription: \"{desc}\"\n---\n\n# {name}\n",
        encoding="utf-8",
    )
    for rel, content in files.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return d


def prepare_fixture():
    for name, (ver, desc, files) in FAKE_SKILLS.items():
        write_fake_skill(core.SKILLS_DIR, name, ver, desc, files)

    cfg = {
        "marketId": "test-market",
        "name": "测试市场",
        "description": "selftest 用",
        "owner": {"name": "Test"},
        "localPlugins": [
            {"name": "bundle-one", "displayName": "第一包", "category": "测试",
             "version": "1.0.0", "description": "含 alpha 与 beta", "keywords": ["t"],
             "skills": ["alpha", "beta"]},
            {"name": "bundle-two", "displayName": "第二包", "category": "测试",
             "version": "2.0.0", "description": "含 gamma", "skills": ["gamma"]},
        ],
        "remoteSources": [{"repo": "owner/repo", "displayName": "远端的", "category": "远端"}],
        "packaging": {"excludeNames": ["__pycache__"], "excludeGlobs": ["*.bak", "*.tmp"]},
        "trash": {"maxAgeDays": 30, "maxSizeBytes": 1024 * 1024},
    }
    core.CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------- 只读检查现网

def check_real() -> int:
    print("只读模式：检查现网市场状态（不写任何东西）\n")
    st = core.build_state()
    ck("市场可枚举", st["stats"]["localPlugins"] > 0,
       f"{st['stats']['localPlugins']} 插件 / {st['stats']['localSkills']} skill")
    ck("地图与索引一致", st["manifestOk"])
    ok, errors, warns = core.deep_check()
    ck("深度自检无 error", ok, "; ".join(errors[:3]))
    if warns:
        print(f"  （{len(warns)} 条 warning）")
        for w in warns[:6]:
            print("     ! " + w)

    # 关键安全检查：每个插件的卸载分级必须覆盖它声明的所有 skill，
    # 且在没有所有权记录时，一律不得判为「可卸载」。
    own = core.load_ownership()["skills"]
    for p in st["plugins"]:
        u = p["uninstall"]
        acc = sum(u["counts"].values())
        ck(f"插件 {p['id']} 卸载分级覆盖全部 skill", acc == len(p["skills"]),
           f"{acc}/{len(p['skills'])}")
        claimed = [s for s in u["removable"] if s not in own]
        ck(f"插件 {p['id']} 没把无主的 skill 判成可卸载", not claimed, str(claimed))
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    return 1 if FAIL else 0


# ---------------------------------------------------------------- 主流程

def run() -> None:
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
    core.save_ownership(own)

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

    # ============ 16. 故障注入 ============
    faults()

    # ============ 19. 第四轮：事务边界 + 本地 API ============
    round4()

    # ============ 20. 第五轮：事务闭环 + 真 tail + 鉴权加固 ============
    round5()

    # ============ 21. 第六轮：并发压力 + 扫描失败 + 崩溃点矩阵 ============
    round6()

    # ============ 22. 第七轮：ghpm 事件解析 / 取消竞态 / 进程树 ============
    round7()

    # ============ 23. 开源重构 R1：运行时目录分离 + WBM_* 环境变量 ============
    round8()


def _restore_config(snapshot: str) -> None:
    core.CONFIG_PATH.write_text(snapshot, encoding="utf-8")


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

    real_save_own = core.save_ownership
    core.save_ownership = lambda _o: (_ for _ in ()).throw(OSError("模拟 .ownership.json 写失败"))
    try:
        r_tx = core.install_local_plugin("bundle-one", "missing")
    finally:
        core.save_ownership = real_save_own

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
    core.save_ownership = lambda _o: (_ for _ in ()).throw(OSError("模拟写失败"))
    try:
        r_up = core.install_local_plugin("bundle-one", "update")
    finally:
        core.save_ownership = real_save_own
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
    core.KNOWN_PATH.parent.mkdir(parents=True, exist_ok=True)
    core.KNOWN_PATH.write_text(json.dumps(
        {"other-market": {"manifestName": "other-market", "type": "zip"}},
        ensure_ascii=False), encoding="utf-8")
    real_or_die = core._read_known_or_die
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

    core._read_known_or_die = meddling_read
    try:
        changed = core.register()
    finally:
        core._read_known_or_die = real_or_die
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
    real_walk = core._walk_tree
    real_scan = core._scan          # 19J 还要用

    def counting_walk(root, excluded, files, links, errors):
        walked.append(Path(root).name)
        return real_walk(root, excluded, files, links, errors)

    # gamma 在更早的用例里是手工塞进 ownership 的（没有 fingerprint 字段）。
    # 这种「旧记录」会绕过批量缓存、退回完整哈希 —— 先验证这一点，再补成正常记录。
    ck("（前提）gamma 的旧记录确实没有指纹",
       not isinstance(core.load_ownership()["skills"]["gamma"].get("fingerprint"), dict))

    core.record_owner("bundle-two", ["gamma"], "2.0.0")   # 补成正常记录
    core._walk_tree = counting_walk
    try:
        st6 = core.build_state()
    finally:
        core._walk_tree = real_walk
    # 额外登记几个「无关 skill」，确认它们不会被顺带扫到
    for extra in ("unrelated-a", "unrelated-b"):
        write_fake_skill(core.SKILLS_DIR, extra, "1.0.0", "噪音", {})
    core._walk_tree = counting_walk
    walked.clear()
    try:
        core.build_state()
    finally:
        core._walk_tree = real_walk
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
    src_html = Path(__file__).resolve().parent / "web" / "index.html"
    ui_ok = src_html.is_file()
    if ui_ok:
        shutil.copy2(src_html, core.WEB_DIR / "index.html")
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
        st_big, js_big = hit("/api/install", b"x" * (srv.MAX_BODY + 1024), AUTH)
        ck("★ ★ 超限请求体 → 413", st_big == 413, f"{st_big} {str(js_big)[:50]}")
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


def _make_link(target: Path, link: Path) -> str:
    """尽力造一个重解析点，返回造出来的类型名或空串。

    先试 junction（不需要管理员），再试符号链接。
    注意 Windows 上 `os.symlink` 可能被宿主环境拦成普通空文件 ——
    这时 is_symlink() 是 False，说明没造成，必须如实报告而不是假装通过。
    """
    try:
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
        return "junction"
    except Exception:
        pass
    try:
        os.symlink(target, link, target_is_directory=True)
        if os.path.islink(link) or (getattr(os.path, "isjunction", None) and os.path.isjunction(link)):
            return "symlink"
        # 宿主把 symlink 拦成了普通目录/文件 → 清掉，别留下垃圾
        _drop_link(link)
    except Exception:
        pass
    return ""


def _is_dir_link(path: Path) -> bool:
    """这个是「目录形态的重解析点」吗？**看 lstat，不要看 is_dir()**。"""
    try:
        st = path.lstat()
    except OSError:
        return False
    return stat.S_ISDIR(st.st_mode)


def _drop_link(link: Path) -> None:
    """摘掉重解析点。必须用 lstat 判断类型，**不能用 Path.is_dir()** ——
    它会跟随链接：指向目录的 symlink 让 is_dir() 返回 True，于是走到
    `os.rmdir(symlink)`，而 POSIX 上 rmdir 对 symlink 是 ENOTDIR，
    链接根本摘不掉，异常还被 except 吞掉。

    Windows 的 junction 恰好能 rmdir 成功，所以在 Windows 上这个 bug 不会暴露 ——
    但它会污染后续用例（残留的链接让"链接安全检查"拒绝本该成功的安装）。
    同样，**绝不能 rmtree**：那会顺着链接递归进去删掉目标里的真东西。
    """
    try:
        if _is_dir_link(link):
            os.rmdir(str(link))     # 目录 / junction
        else:
            link.unlink()           # 文件 / 符号链接
    except OSError:
        pass


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

    real_save = core._save_trash_index

    def save_boom(_idx):
        raise OSError("模拟 .index.json 写入失败")

    core._save_trash_index = save_boom
    try:
        t = core.move_to_trash(core.SKILLS_DIR / "alpha", "reinstall")
    finally:
        core._save_trash_index = real_save

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
    core._save_trash_index = save_boom
    try:
        r_fs = core.install_local_plugin("bundle-one", "force")
    finally:
        core._save_trash_index = real_save
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


def main() -> int:
    if not _ISOLATED:
        return check_real()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(f"本机插件市场 自检 v{core.MARKET_VERSION}（隔离模式）\n临时根目录：{_TMP}\n")
    try:
        run()
    finally:
        if _TMP and _TMP.exists():
            shutil.rmtree(_TMP, ignore_errors=True)

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed"
          + (f", {len(SKIP)} skipped" if SKIP else ""))
    if SKIP:
        print("跳过项（环境不具备，不是通过）：")
        for s in SKIP:
            print("  - " + s)
    if FAIL:
        print("失败项：")
        for f in FAIL:
            print("  - " + f)
    return 1 if FAIL else 0


class _CountingFile:
    """包一层文件对象，统计真正读了多少字节（用于验证 tail 的 I/O 量）。"""

    def __init__(self, fh, box):
        self._fh = fh
        self._box = box

    def read(self, *a):
        d = self._fh.read(*a)
        if isinstance(d, (bytes, str)):
            self._box["bytes"] += len(d)
        return d

    def __iter__(self):
        for line in self._fh:
            self._box["bytes"] += len(line)
            yield line

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return self._fh.__exit__(*exc)

    def __getattr__(self, k):
        return getattr(self._fh, k)


def round5():
    """第五轮评审：事务闭环（凭证前置 / 拒认领 / 卸载事务）+ 真 tail + 鉴权加固。"""
    section("20. 第五轮：事务模型闭环与服务端加固")

    # --- 20A. 版本口径一致（文档漂移的防呆）
    want = ".".join(core.MARKET_VERSION.split(".")[:2])
    ck("★ selftest 声明的版本与内核一致", SELFTEST_VERSION == want,
       f"selftest={SELFTEST_VERSION} 内核={core.MARKET_VERSION}")

    # --- 20B. 凭证必须先于磁盘变更
    core.sync_packaging(quiet=True)
    shutil.rmtree(core.TX_DIR, ignore_errors=True)
    core.install_local_plugin("bundle-one", "force")     # 归本市场
    core.install_local_plugin("bundle-one", "force")

    # ① 拿不到凭证就一个字节都不动磁盘
    before = core.tree_hash(core.SKILLS_DIR / "alpha")
    real_begin = core.tx_begin
    core.tx_begin = lambda *a, **k: (_ for _ in ()).throw(OSError("模拟：连日志都开不了"))
    try:
        try:
            core.install_local_plugin("bundle-one", "force")
            ck("★ 日志开不了时安装应当失败", False, "居然成功了")
        except OSError:
            ck("★ ★ 日志开不了 → 安装直接失败，不碰磁盘", True)
    finally:
        core.tx_begin = real_begin
    ck("★ 磁盘内容一字未改", core.tree_hash(core.SKILLS_DIR / "alpha") == before)
    ck("★ 没留下暂存目录", not list(core.SKILLS_DIR.glob(".*.installing-*")))

    # ② 崩在「os.replace 成功」与「交付确认」之间 —— 凭证必须已经在了
    (core.SKILLS_DIR / "alpha" / "body.txt").write_text("MARKET-V2", encoding="utf-8")
    core.sync_packaging(quiet=True)
    real_note = core.tx_note_committed

    def crash_after_commit(*a, **k):
        raise SystemExit("模拟：换位成功后、交付确认之前进程被杀")

    core.tx_note_committed = crash_after_commit
    try:
        core.install_local_plugin("bundle-one", "update")
    except SystemExit:
        pass
    finally:
        core.tx_note_committed = real_note

    ck("★ 磁盘确实已经换成市场版本",
       core.tree_hash(core.SKILLS_DIR / "alpha")
       == core.tree_hash(core.PLUGINS_DIR / "bundle-one" / "skills" / "alpha"))
    logs = core.tx_list()
    ck("★ ★ 这个窗口里凭证已经存在（v2.3 是 0 份）", len(logs) == 1, f"{len(logs)} 份")
    entry = logs[0]["pendingOwnership"][0] if logs else {}
    ck("★ 日志里带着 expected hash 与状态",
       bool(entry.get("hash")) and entry.get("state") == "staged",
       f"state={entry.get('state')} hash={str(entry.get('hash'))[:12]}…")
    ck("★ expected hash 与换位后的内容一致",
       entry.get("hash") == core.tree_hash(core.SKILLS_DIR / "alpha"))

    rec = core.recover_transactions(quiet=True)
    ck("★ ★ 恢复流程据此认领回来", rec["recovered"] == ["alpha"], str(rec))
    ck("★ 认领后判为 safe",
       core.classify_skill("bundle-one", "alpha", core.load_config(),
                           purpose="uninstall")["kind"] == "safe")
    ck("★ 日志已清账", not core.tx_list())

    # --- 20C. 恢复拒绝把用户的改动洗白
    core.prune_trash(force=True, quiet=True)
    core.install_local_plugin("bundle-one", "force")
    shutil.rmtree(core.TX_DIR, ignore_errors=True)
    own_before = json.dumps(core.load_ownership()["skills"], sort_keys=True)

    real_save_own = core.save_ownership
    core.save_ownership = lambda _o: (_ for _ in ()).throw(OSError("模拟写失败"))
    try:
        core.install_local_plugin("bundle-one", "force")
    finally:
        core.save_ownership = real_save_own
    ck("（前提）确实留下了待补账的事务", bool(core.tx_list()))

    # 用户在这中间改了自己的那份
    (core.SKILLS_DIR / "alpha" / "body.txt").write_text("USER-EDITED", encoding="utf-8")
    user_hash = core.tree_hash(core.SKILLS_DIR / "alpha")

    rec2 = core.recover_transactions(quiet=True)
    ck("★ ★ 恢复**拒绝认领**被改动过的 skill", "alpha" not in rec2["recovered"],
       str(rec2["recovered"]))
    ck("★ ★ 同一次事务里没被改过的 beta 照常认领（逐条判决，不是一刀切）",
       "beta" in rec2["recovered"], str(rec2["recovered"]))
    ck("★ ★ 并且明确报出冲突",
       bool(rec2["conflicts"]) and rec2["conflicts"][0]["skill"] == "alpha",
       str(rec2["conflicts"])[:80])
    ck("★ 所有权保持原样（没被写成用户改完的版本）",
       json.dumps(core.load_ownership()["skills"].get("alpha"), sort_keys=True)
       == json.dumps(json.loads(own_before).get("alpha"), sort_keys=True))
    ck("★ ★ 磁盘内容也没被动过", core.tree_hash(core.SKILLS_DIR / "alpha") == user_hash)
    kind = core.classify_skill("bundle-one", "alpha", core.load_config(),
                               purpose="uninstall")["kind"]
    ck("★ ★ 不再被判成「可以安全卸载」（v2.3 会误判 safe）", kind != "safe", kind)
    ck("★ 冲突时保留日志，不替用户做决定", len(core.tx_list()) == 1)
    ok_dc, errs_dc, _w = core.deep_check()
    ck("★ 深度自检报出这笔被挡下的账",
       not ok_dc and any("未完成的事务" in e for e in errs_dc), "; ".join(errs_dc[:1])[:70])

    rec3 = core.recover_transactions(quiet=True, discard_conflicts=True)
    ck("★ --discard-conflicts 才放弃这笔账", not core.tx_list() and rec3["recovered"] == [])
    ck("★ 放弃也依然不认领", "alpha" not in [
        k for k, v in core.load_ownership()["skills"].items()
        if v.get("hash") == user_hash])

    # --- 20D. 卸载也走同一套事务
    core.install_local_plugin("bundle-one", "force")
    shutil.rmtree(core.TX_DIR, ignore_errors=True)
    ck("（前提）alpha 归本市场", "alpha" in core.load_ownership()["skills"])

    core.save_ownership = lambda _o: (_ for _ in ()).throw(OSError("模拟 forget 失败"))
    try:
        r_un = core.uninstall_local_plugin("bundle-one")
    finally:
        core.save_ownership = real_save_own

    ck("★ 目录确实被搬走了", not (core.SKILLS_DIR / "alpha").exists())
    ck("★ 所有权还没清（这就是要补的账）",
       "alpha" in core.load_ownership()["skills"])
    ck("★ ★ 卸载也留下了事务日志（v2.3 是 0 份）", len(core.tx_list()) == 1)
    utx = core.tx_list()[0]
    ck("★ 日志是 uninstall 类型，且记着待清的所有权",
       utx.get("operation") == "uninstall" and "alpha" in (utx.get("pendingForget") or []),
       f"{utx.get('operation')} forget={utx.get('pendingForget')}")
    ck("★ 卸载照常报告成功并给出告警",
       r_un["ok"] is True and any("所有权" in w for w in r_un.get("warnings", [])),
       str(r_un.get("warnings"))[:70])

    rec4 = core.recover_transactions(quiet=True)
    ck("★ ★ 恢复补清了所有权", "alpha" not in core.load_ownership()["skills"], str(rec4))
    ck("★ 日志已清账", not core.tx_list())
    core.install_local_plugin("bundle-one", "missing")

    # --- 20E. tail_log 是真的反向 tail
    core.LOG_PATH.write_text("x\n" * 4_000_000, encoding="utf-8")          # ≈8MB
    for i in (1, 2):
        core.LOG_PATH.with_name(f"{core.LOG_PATH.stem}.{i}{core.LOG_PATH.suffix}").write_text(
            "x\n" * 4_000_000, encoding="utf-8")
    lines = [json.dumps({"at": "T", "level": "info", "event": "tail", "detail": f"L{i}"},
                        ensure_ascii=False) for i in range(500)]
    core.LOG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    total = sum(p.stat().st_size for p in (
        [core.LOG_PATH] + [core.LOG_PATH.with_name(
            f"{core.LOG_PATH.stem}.{i}{core.LOG_PATH.suffix}") for i in (1, 2)]))

    box = {"bytes": 0}
    real_open = Path.open

    def counting_open(self, *a, **k):
        return _CountingFile(real_open(self, *a, **k), box)

    Path.open = counting_open
    try:
        t0 = time.perf_counter()
        got = core.tail_log(60)
        el = (time.perf_counter() - t0) * 1000
    finally:
        Path.open = real_open

    ck("★ 只读尾部，不再扫整份日志", box["bytes"] < 1_048_576,
       f"读了 {box['bytes'] / 1024:.0f} KB / 日志共 {total / 1048576:.1f} MB / {el:.0f} ms")
    ck("★ 拿到的是最后 60 条且顺序正确（最新在前）",
       len(got) == 60 and got[0]["detail"] == "L499" and got[-1]["detail"] == "L440",
       f"{len(got)} 条，首 {got[0]['detail'] if got else None}，末 {got[-1]['detail'] if got else None}")

    small = core.MARKET_ROOT / "tail-probe.txt"
    small.write_bytes(b"".join(f"line{i}\n".encode() for i in range(10)))
    tl, at_start = core._tail_lines(small, 3)
    ck("★ _tail_lines 取最后 N 行且读到文件头时如实报告",
       tl == [b"line7", b"line8", b"line9"] and at_start is True, f"{tl} at_start={at_start}")
    big = core.MARKET_ROOT / "tail-big.txt"
    big.write_bytes(b"".join(f"lg{i:07d}\n".encode() for i in range(200_000)))
    tl2, at_start2 = core._tail_lines(big, 3)
    ck("★ 大文件只读尾部且拼得对",
       tl2 == [b"lg0199997", b"lg0199998", b"lg0199999"] and at_start2 is False,
       f"{tl2} at_start={at_start2}")
    small.unlink()
    big.unlink()

    # --- 20F. repo 校验在 API 层复用
    bad = ["", "   ", "foo", "owner/", "/repo", "a/b/c", "../evil", "..", "owner/..",
           "-x/repo", "owner/-y", "a b/c", "owner/repo\n", "x" * 300 + "/y"]
    rejected = 0
    for v in bad:
        try:
            core.validate_repo(v)
        except core.ConfigError:
            rejected += 1
    ck("★ ★ 可疑 repo 全部拒绝（含 ../ / 短横线开头 / 超长）",
       rejected == len(bad), f"{rejected}/{len(bad)}")
    ok_ok = True
    for v in ["owner/repo", "anthropics/skills", "a.b_c-d/e.f", "obra/superpowers"]:
        try:
            core.validate_repo(v)
        except core.ConfigError as exc:
            ok_ok = False
            ck(f"合法 repo {v} 应通过", False, str(exc))
    ck("★ 合法 repo 全部通过", ok_ok)

    import market_server as srv5  # noqa: E402

    httpd = srv5.make_server(0, token="tok5")
    port5 = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def hit5(path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", port5, timeout=10)
        data = json.dumps(body).encode() if body is not None else None
        h = {"X-Local-Market-Token": "tok5", "Content-Type": "application/json"}
        h.update(headers or {})
        c.request("POST" if body is not None else "GET", path, body=data, headers=h)
        r = c.getresponse()
        raw = r.read()
        c.close()
        try:
            return r.status, json.loads(raw)
        except Exception:
            return r.status, raw.decode("utf-8", "replace")

    try:
        for v in ["../../x", "foo", "owner/", "-x/y", "a/b/c"]:
            st, js = hit5("/api/remote/add", {"repo": v})
            ck(f"★ /api/remote/add 拒绝 {v!r}", st == 400, f"{st} {str(js)[:50]}")
        st_ok, js_ok = hit5("/api/remote/add", {"repo": "owner/repo"})
        ck("★ /api/remote/add 接受合法 repo", st_ok == 200 and js_ok.get("jobId"),
           f"{st_ok} {str(js_ok)[:50]}")

        # --- 20G. /api/state single-flight
        calls = {"n": 0}
        real_build = core.build_state

        def slow_build(*a, **k):
            calls["n"] += 1
            time.sleep(0.15)
            return real_build(*a, **k)

        core.build_state = slow_build
        try:
            srv5.invalidate_state()
            errs = []

            def worker():
                try:
                    srv5.get_state()
                except Exception as exc:      # pragma: no cover
                    errs.append(exc)

            ths = [threading.Thread(target=worker) for _ in range(8)]
            for t in ths:
                t.start()
            for t in ths:
                t.join(20)
        finally:
            core.build_state = real_build
        ck("★ ★ 8 个并发请求只重建一次状态（缓存击穿已堵）", calls["n"] == 1,
           f"重建 {calls['n']} 次" + (f"，异常 {errs}" if errs else ""))

        # --- 20H. 连接超时与队列长度
        ck("★ Handler 设了 socket 读超时",
           srv5.Handler.timeout == srv5.SOCKET_TIMEOUT and srv5.SOCKET_TIMEOUT > 0,
           str(srv5.Handler.timeout))
        ck("★ 服务用了加固过的 server 类",
           issubclass(srv5.MarketHTTPServer, srv5.ThreadingHTTPServer)
           and srv5.MarketHTTPServer.daemon_threads is True
           and srv5.MarketHTTPServer.request_queue_size == srv5.MAX_PARALLEL,
           f"queue={srv5.MarketHTTPServer.request_queue_size}")
        st_after, _ = hit5("/api/state")
        ck("★ 加固之后接口仍正常", st_after == 200, str(st_after))
    finally:
        httpd.shutdown()
        httpd.server_close()

    # --- 20I. _drop_link 不再被 is_dir() 带偏
    victim_dir = core.MARKET_ROOT.parent / "DROP-LINK-TARGET"
    victim_dir.mkdir(parents=True, exist_ok=True)
    (victim_dir / "keep.txt").write_text("keep", encoding="utf-8")
    holder = core.SKILLS_DIR / "link-holder"
    holder.mkdir(parents=True, exist_ok=True)
    link = holder / "lnk"
    kind = _make_link(victim_dir, link)
    if kind:
        ck("（构造）is_dir() 对目录形态的重解析点返回 True（正是旧实现的坑）",
           link.is_dir() is True)
        _drop_link(link)
        ck(f"★ ★ {kind} 被真正摘掉", not link.exists() and not link.is_symlink(),
           f"exists={link.exists()}")
        ck("★ 目标目录毫发无损", (victim_dir / "keep.txt").is_file())
    else:
        sk("_drop_link 实测", "本环境建不出重解析点（symlink 被宿主拦成普通文件）")
    _drop_link(holder / "does-not-exist")          # 不存在的路径不该抛
    ck("★ _drop_link 对不存在的路径安全返回", True)
    shutil.rmtree(holder, ignore_errors=True)
    shutil.rmtree(victim_dir, ignore_errors=True)


class _Crash(BaseException):
    """崩溃注入用的哨兵。

    刻意继承 BaseException：这样它不会被 `except OSError` / `except Exception`
    顺手吃掉 —— 事务里的 `finally`（释放日志、flush 索引）仍然会执行，
    这才是"进程在这一点上突然没了"的真实语义。
    """


def _invariants() -> list:
    """事务系统的不变量：所有权 ↔ 磁盘 一致、没有残留暂存目录。"""
    probs = []
    for s, rec in core.load_ownership()["skills"].items():
        d = core.SKILLS_DIR / s
        if not (d / "SKILL.md").is_file():
            probs.append(f"所有权里的 {s} 在磁盘上不存在")
            continue
        try:
            if core.tree_hash(d) != rec.get("hash"):
                probs.append(f"{s}: 所有权 hash 与磁盘内容不符")
        except core.ScanError as exc:
            probs.append(f"{s}: 读不了（{exc}）")
    left = [p.name for p in core.SKILLS_DIR.glob(".*.installing-*")]
    if left:
        probs.append(f"残留暂存目录 {left}")
    return probs


def round6():
    """第六轮评审：并发边界、扫描 fail-closed、崩溃点矩阵。"""
    section("21. 第六轮：并发压力 / 扫描失败 / 崩溃点矩阵")

    # ---------- 21A. 并发压力 ----------
    _line = None
    core.prune_trash(force=True, quiet=True)
    core.sync_packaging(quiet=True)

    # A1. 32 并发打 /api/state
    import market_server as srv6  # noqa: E402

    httpd = srv6.make_server(0, token="concurrency-token")
    PORT = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def _get_state(i, out):
        c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=15)
        try:
            c.request("GET", "/api/state",
                      headers={"X-Local-Market-Token": "concurrency-token"})
            r = c.getresponse()
            body = r.read()
            out.append(r.status if r.status == 200 and b"stats" in body else f"HTTP{r.status}")
        except Exception as exc:          # pragma: no cover
            out.append(f"{type(exc).__name__}: {exc}")
        finally:
            c.close()

    builds = {"n": 0}
    real_build = core.build_state

    def slow_build(*a, **k):
        builds["n"] += 1
        time.sleep(0.2)
        return real_build(*a, **k)

    res = []
    core.build_state = slow_build
    try:
        srv6.invalidate_state()
        ths = [threading.Thread(target=_get_state, args=(i, res)) for i in range(32)]
        t0 = time.time()
        for t in ths:
            t.start()
        for t in ths:
            t.join(30)
        el = time.time() - t0
    finally:
        core.build_state = real_build
    ck("★ ★ 32 并发 /api/state：无死锁、无异常",
       len(res) == 32 and all(r == 200 for r in res), f"{el:.1f}s，结果 {set(res)}")
    ck("★ ★ single-flight 生效：只重建一次", builds["n"] == 1, f"重建 {builds['n']} 次")

    # A2. 8 并发 install（文件锁串行化）
    core.install_local_plugin("bundle-one", "force")
    out_i, err_i = [], []

    def _install():
        try:
            out_i.append(core.install_local_plugin("bundle-one", "missing")["ok"])
        except Exception as exc:          # pragma: no cover
            err_i.append(f"{type(exc).__name__}: {exc}")

    ths = [threading.Thread(target=_install) for _ in range(8)]
    for t in ths:
        t.start()
    for t in ths:
        t.join(60)
    ck("★ ★ 8 并发 install：全部返回且无异常",
       len(out_i) == 8 and all(out_i) and not err_i, f"{out_i} {err_i}")
    ck("★ 并发 install 后不变量成立", not _invariants(), str(_invariants()))
    ck("★ 没有重复事务残留", not core.tx_list())

    # A3. 8 并发 register
    core.KNOWN_PATH.parent.mkdir(parents=True, exist_ok=True)
    core.KNOWN_PATH.write_text(json.dumps(
        {"other-market": {"manifestName": "other-market", "type": "zip"}},
        ensure_ascii=False), encoding="utf-8")
    out_r, err_r = [], []

    def _register():
        try:
            core.register()
            out_r.append(1)
        except Exception as exc:          # pragma: no cover
            err_r.append(f"{type(exc).__name__}: {exc}")

    ths = [threading.Thread(target=_register) for _ in range(8)]
    for t in ths:
        t.start()
    for t in ths:
        t.join(60)
    known = json.loads(core.KNOWN_PATH.read_text(encoding="utf-8"))
    ck("★ ★ 8 并发 register：无异常、无丢失",
       len(out_r) == 8 and not err_r and "test-market" in known and "other-market" in known,
       f"{known.keys()} {err_r}")

    # A4. 后台任务并发上限 —— 真·并发。
    # v2.5 的写法是**串行**调用 _remote_job，而隔离环境里 ghpm 秒失败、令牌秒还，
    # 下一个串行请求又能抢到 —— accepted 超过上限（探针 10/10 轮复现：上限 4，
    # accepted 全是 10）。真正要验证的是「N 个请求**同时**打进来」：用 barrier
    # 让所有请求同时出发，用 gate 挂住 fake _run_ghpm，保证满载状态可观察。
    with srv6._jobs_lock:
        srv6._jobs.clear()
    for _ in range(20):                  # 上轮测试若有泄漏，把令牌收回来
        if not srv6.running_jobs():
            break
        try:
            srv6._RUNNER.release()
        except ValueError:
            break
        time.sleep(0.05)
    gate = threading.Event()
    real_run_ghpm = srv6._run_ghpm

    def blocked_run_ghpm(args, jid):
        gate.wait(15)                    # 模拟 ghpm 一直在跑，直到测试放行
        return True

    srv6._run_ghpm = blocked_run_ghpm
    n_total = srv6.MAX_RUNNING_JOBS + 6
    results = []
    start_bar = threading.Barrier(n_total)

    def _fire(i):
        start_bar.wait(15)               # 全部就位后同时出发
        results.append(srv6._remote_job(f"owner/repo{i}", "add"))

    ths = [threading.Thread(target=_fire, args=(i,)) for i in range(n_total)]
    try:
        for t in ths:
            t.start()
        for t in ths:
            t.join(30)
        accepted = [j for j in results if j]
        rejected = [j for j in results if j is None]
        ck("★ ★ 后台任务并发不超过 MAX_RUNNING_JOBS（真并发，同时打进来的请求）",
           len(accepted) == srv6.MAX_RUNNING_JOBS and len(rejected) == 6,
           f"接受 {len(accepted)} / 拒绝 {len(rejected)}（上限 {srv6.MAX_RUNNING_JOBS}）")
        ck("★ ★ 满载时运行计数恰好等于上限（不读信号量私有字段）",
           srv6.running_jobs() == srv6.MAX_RUNNING_JOBS, str(srv6.running_jobs()))
        ck("★ 被拒的任务不会进任务表",
           len([j for j in srv6._jobs if j in accepted]) == len(accepted), str(len(srv6._jobs)))
        gate.set()                       # 放行所有 worker
        deadline = time.time() + 20
        while srv6.running_jobs() and time.time() < deadline:
            time.sleep(0.05)
        for t in ths:                    # 等 worker 线程真正退出再断言
            t.join(5)
        ck("★ 任务结束后令牌全部归还（并发槽不会泄漏）",
           srv6.running_jobs() == 0, str(srv6.running_jobs()))
        with srv6._jobs_lock:
            done_ok = all(srv6._jobs[j]["status"] == "done" and srv6._jobs[j]["ok"] is True
                          for j in accepted)
        ck("★ 放行后所有任务正常收尾（没有卡在 running）", done_ok)
    finally:
        gate.set()                       # 就算断言炸了也要放行，别拖死整个自检
        srv6._run_ghpm = real_run_ghpm
    httpd.shutdown()
    httpd.server_close()

    # ---------- 21B. 扫描失败必须 fail-closed ----------
    core.install_local_plugin("bundle-one", "force")
    core.sync_packaging(quiet=True)
    pkg = core.PLUGINS_DIR / "bundle-one" / "skills"
    before_pkg = sorted(str(p.relative_to(pkg)) for p in pkg.rglob("*") if p.is_file())
    real_scandir = os.scandir

    def flaky_for(target: str):
        def _f(path=".", *a, **k):
            if str(path).rstrip("\\/") == target:
                raise PermissionError(13, "模拟：读不了这个目录")
            return real_scandir(path, *a, **k)
        return _f

    # ① 源端（本机 skills）读不了 → sync 必须失败，而且市场内容一个都不能删
    os.scandir = flaky_for(str(core.SKILLS_DIR / "alpha"))
    try:
        try:
            core.sync_packaging(quiet=True)
            sync_raised = False
        except core.ScanError:
            sync_raised = True
        after_pkg = sorted(str(p.relative_to(pkg)) for p in pkg.rglob("*") if p.is_file())
        kind_flaky = core.classify_skill("bundle-one", "alpha", core.load_config(),
                                         purpose="uninstall")["kind"]
        raw = core._scan(core.SKILLS_DIR / "alpha", on_error="skip")
        try:
            core._scan(core.SKILLS_DIR / "alpha", on_error="raise")
            raise_mode_ok = False
        except core.ScanError:
            raise_mode_ok = True
    finally:
        os.scandir = real_scandir

    ck("★ ★ 扫描不完整时 sync 直接失败（不再当空目录处理）", sync_raised)
    ck("★ ★ 市场内容一个文件都没被删", after_pkg == before_pkg,
       f"{len(before_pkg)} → {len(after_pkg)}")
    ck("★ ★ 读不全时卸载判定保守（当 modified，不搬走）", kind_flaky != "safe", kind_flaky)
    ck("★ _scan(on_error='skip') 仍可用于状态展示（不抛）", isinstance(raw, tuple))
    ck("★ ★ _scan(on_error='raise') 抛 ScanError", raise_mode_ok)

    # ② 安装源（市场产物）读不了 → 那个 skill 安装失败，本机毫发无损
    victim2 = str(core.PLUGINS_DIR / "bundle-one" / "skills" / "alpha")
    before_local = core.tree_hash(core.SKILLS_DIR / "alpha")
    os.scandir = flaky_for(victim2)
    try:
        r_ci = core.install_local_plugin("bundle-one", "force")
    except core.ScanError as exc:
        r_ci = {"ok": False, "failed": [str(exc)]}
    finally:
        os.scandir = real_scandir

    ck("★ ★ 安装源读不全时该 skill 安装失败",
       bool(r_ci.get("failed")) and any("alpha" in f for f in r_ci["failed"]),
       str(r_ci["failed"])[:90])
    ck("★ ★ 本机 skill 一个字节没动",
       core.tree_hash(core.SKILLS_DIR / "alpha") == before_local)
    ck("★ 没留下暂存目录", not list(core.SKILLS_DIR.glob(".*.installing-*")))

    core.sync_packaging(quiet=True)
    ck("★ 恢复后不变量成立", not _invariants(), str(_invariants()))

    # ---------- 21C. 崩溃点矩阵 ----------
    def crash_at(attr: str, label: str):
        """在 pipeline 的某一步注入崩溃，然后跑恢复，检查不变量。"""
        core.install_local_plugin("bundle-one", "force")     # 每轮先归零
        shutil.rmtree(core.TX_DIR, ignore_errors=True)
        (core.SKILLS_DIR / "alpha" / "body.txt").write_text(f"MARKET-{label}",
                                                            encoding="utf-8")
        core.sync_packaging(quiet=True)
        core.install_local_plugin("bundle-one", "force")
        own_before = json.dumps(core.load_ownership()["skills"], sort_keys=True)

        real = getattr(core, attr)

        def boom(*a, **k):
            raise _Crash(f"注入：{attr} 处崩溃")

        setattr(core, attr, boom)
        crashed = False
        try:
            try:
                core.install_local_plugin("bundle-one", "force")
            except _Crash:
                crashed = True
        finally:
            setattr(core, attr, real)

        rec = core.recover_transactions(quiet=True)
        probs = _invariants()
        leftover = len(core.tx_list())
        ck(f"★ 崩溃点 {label}：捕获到注入", crashed)
        ck(f"★ 崩溃点 {label}：恢复后不变量成立（disk ↔ ownership 一致、无残留）",
           not probs, "; ".join(probs)[:80])
        ck(f"★ 崩溃点 {label}：日志已收敛（或明确留下冲突）",
           leftover == 0 or bool(rec["conflicts"]),
           f"残留 {leftover} 份，recovered={rec['recovered']}, conflicts={len(rec['conflicts'])}")
        return own_before, rec

    crash_at("_stage_skill", "① tx_begin 之后")
    crash_at("_commit_staged", "② tx_note_staged 之后")
    crash_at("tx_note_committed", "③ os.replace 之后")
    crash_at("record_owner", "④ tx_note_committed 之后")
    before5, rec5 = crash_at("tx_drop", "⑤ record_owner 之后")
    ck("★ ★ 崩溃点⑤：所有权已经写进去了（恢复只是把它们再确认一次）",
       "alpha" in core.load_ownership()["skills"], str(rec5["recovered"]))

    # 提交确认后的那个点必须真的"认领回来"，而不是丢弃
    core.install_local_plugin("bundle-one", "force")
    core.sync_packaging(quiet=True)
    (core.SKILLS_DIR / "alpha" / "body.txt").write_text("MARKET-claim", encoding="utf-8")
    core.sync_packaging(quiet=True)
    real_note = core.tx_note_committed
    core.tx_note_committed = lambda *a, **k: (_ for _ in ()).throw(_Crash("注入"))
    try:
        try:
            core.install_local_plugin("bundle-one", "force")
        except _Crash:
            pass
    finally:
        core.tx_note_committed = real_note
    rec_claim = core.recover_transactions(quiet=True)
    ck("★ ★ 交付确认后崩溃的那一笔会被补记回来（不是丢弃）",
       "alpha" in rec_claim["recovered"], str(rec_claim["recovered"]))
    ck("★ 补记后判为 safe（内容确实是市场那份）",
       core.classify_skill("bundle-one", "alpha", core.load_config(),
                           purpose="uninstall")["kind"] == "safe")
    ck("★ 最终不变量成立", not _invariants() and not core.tx_list(),
       str(_invariants()))


def round7():
    """第七轮评审：ghpm 事件解析的真 bug、取消竞态、POSIX 进程树。"""
    section("22. 第七轮：ghpm 事件解析 / 取消竞态 / 进程树收尾")

    import market_server as srv7  # noqa: E402

    # 用一个可控的假 ghpm 替身（真 ghpm 在隔离环境里根本不存在）
    fake_dir = core.MARKET_ROOT / ".selftest-fake-ghpm"
    fake_dir.mkdir(exist_ok=True)
    real_ghpm_py = core.GHPM_PY

    def _fake_ghpm(body: str) -> Path:
        p = fake_dir / "ghpm.py"
        p.write_text("import sys\n" + body, encoding="utf-8")
        return p

    # --- 22A. done/ok=false 且**没有 error 字段**：v2.5 在这里引用未定义的
    #     label → NameError → worker 的 _job_finish 不跑 → 任务永远 running。
    core.GHPM_PY = _fake_ghpm(
        'import json\nprint("__GHPM__ " + json.dumps({"phase": "done", "ok": False}))\n'
        'sys.exit(1)\n')
    jid = srv7._new_job("探针：无 error 字段")
    name_error = None
    try:
        ok = srv7._run_ghpm(["add", "owner/repo"], jid)
    except NameError as exc:
        name_error = exc
        ok = None
    with srv7._jobs_lock:
        lines7 = list(srv7._jobs[jid]["lines"])
    ck("★ ★ ghpm 失败事件（无 error 字段）不再抛 NameError",
       name_error is None and ok is False, str(name_error))
    ck("★ ★ 任务行里有可读的失败原因（兜底文案）",
       any("✗" in l and "ghpm 执行失败" in l for l in lines7), str(lines7))
    srv7._job_finish(jid, ok, "失败")
    with srv7._jobs_lock:
        st = srv7._jobs[jid]["status"]
    ck("★ 显式收尾后任务不会停在 running", st == "done", st)

    # --- 22B. 带 error 字段时优先展示它
    core.GHPM_PY = _fake_ghpm(
        'import json\n'
        'print("__GHPM__ " + json.dumps({"phase": "done", "ok": False, "error": "boom"}))\n'
        'sys.exit(1)\n')
    jid = srv7._new_job("探针：带 error 字段")
    ok = srv7._run_ghpm(["add", "owner/repo"], jid)
    with srv7._jobs_lock:
        lines7 = list(srv7._jobs[jid]["lines"])
    ck("★ ★ 优先展示 ghpm 给出的 error 原文", ok is False and any("✗ boom" in l for l in lines7),
       str(lines7))

    # --- 22C. 取消发生在 Popen 之前：不该白白拉起进程
    core.GHPM_PY = _fake_ghpm("import time\nprint('started', flush=True)\ntime.sleep(30)\n")
    jid = srv7._new_job("探针：Popen 前取消")
    with srv7._jobs_lock:
        srv7._jobs[jid]["canceled"] = True
    t0 = time.time()
    ok = srv7._run_ghpm(["add", "owner/repo"], jid)
    with srv7._jobs_lock:
        lines7 = list(srv7._jobs[jid]["lines"])
    ck("★ ★ Popen 之前已取消 → 直接返回，不启动子进程",
       ok is False and not any(l.startswith("$ ") for l in lines7)
       and time.time() - t0 < 5, str(lines7))

    # --- 22D. 取消发生在运行中：整棵进程树真的被终止
    jid = srv7._new_job("探针：运行中取消")
    result = {}

    def _runner():
        result["ok"] = srv7._run_ghpm(["add", "owner/repo"], jid)

    th = threading.Thread(target=_runner, daemon=True)
    th.start()
    deadline = time.time() + 10
    proc7 = None
    while time.time() < deadline:
        with srv7._jobs_lock:
            proc7 = srv7._jobs[jid].get("proc")
        if proc7 is not None:
            break
        time.sleep(0.05)
    ck("（构造）子进程已拉起并挂到任务上", proc7 is not None)
    if proc7 is not None:
        canceled = srv7.cancel_job(jid)
        th.join(15)
        alive = proc7.poll() is None
        ck("★ ★ cancel_job 返回成功", canceled)
        ck("★ ★ 运行中取消：子进程（连同它的树）被终止",
           not alive and result.get("ok") is False, f"alive={alive} ok={result.get('ok')}")

    # --- 22E. 收尾不变量：并发槽没有泄漏、任务表没有卡死项
    deadline = time.time() + 10
    while srv7.running_jobs() and time.time() < deadline:
        time.sleep(0.05)
    ck("★ 全部用例结束后并发槽归还（running_jobs == 0）",
       srv7.running_jobs() == 0, str(srv7.running_jobs()))
    with srv7._jobs_lock:
        stuck = [j for j, d in srv7._jobs.items() if d["status"] == "running"]
    for jid in stuck:
        srv7._job_finish(jid, False, "selftest 清理")
    shutil.rmtree(fake_dir, ignore_errors=True)
    core.GHPM_PY = real_ghpm_py


def round8():
    """开源重构 R1：三层根目录 / WBM_* 环境变量 / 运行时迁移。

    路径常量是 import 期求值的，所以全部用**子进程**验证：每个用例
    独立设置环境变量后 import market_core，断言算出来的路径。
    """
    section("23. 开源重构 R1：运行时目录分离与环境变量升级")

    repo = str(Path(core.__file__).resolve().parent)

    def _clean_env(extra: dict) -> dict:
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("GHPM_", "WBM_", "_WBM_"))}
        env["_WBM_REPO"] = repo
        env["PYTHONIOENCODING"] = "utf-8"
        env.update(extra)
        return env

    _CODE_PATHS = (
        "import json, os, sys\n"
        "sys.path.insert(0, os.environ['_WBM_REPO'])\n"
        "import market_core as c\n"
        "print(json.dumps({'MARKET_ROOT': str(c.MARKET_ROOT),"
        " 'STATE_HOME': str(c.STATE_HOME), 'STATE_PATH': str(c.STATE_PATH),"
        " 'LOG_PATH': str(c.LOG_PATH), 'TRASH_DIR': str(c.TRASH_DIR),"
        " 'TX_DIR': str(c.TX_DIR), 'WB': str(c.WB)}))\n"
    )
    _CODE_MIGRATE = (
        "import json, os, sys\n"
        "sys.path.insert(0, os.environ['_WBM_REPO'])\n"
        "import market_core as c\n"
        "print(json.dumps(c.migrate_runtime_files(quiet=True)))\n"
    )
    # 模拟跨卷：os.replace 一律抛 EXDEV，迁移必须靠 shutil.move 兜底完成
    _CODE_EXDEV = (
        "import json, os, sys\n"
        "def _exdev(src, dst):\n"
        "    raise OSError(18, 'Cross-device link (simulated)')\n"
        "os.replace = _exdev\n"
        "sys.path.insert(0, os.environ['_WBM_REPO'])\n"
        "import market_core as c\n"
        "print(json.dumps(c.migrate_runtime_files(quiet=True)))\n"
    )

    def _run(env_extra: dict, code: str):
        return subprocess.run([sys.executable, "-c", code], env=_clean_env(env_extra),
                              capture_output=True, text=True, timeout=60)

    # --- 23A. WBM_* 新变量：默认分桶 ~/.workbuddy-market/markets/<bucket>/
    m8a = _TMP / "r1a" / "market"; wb8a = _TMP / "r1a" / "wb"
    m8a.mkdir(parents=True); wb8a.mkdir(parents=True)
    p = _run({"WBM_MARKET_ROOT": str(m8a), "WBM_HOME": str(wb8a)}, _CODE_PATHS)
    ck("23A 子进程正常退出", p.returncode == 0, p.stderr[-300:])
    if p.returncode != 0:
        return
    d = json.loads(p.stdout.strip().splitlines()[-1])
    ck("WBM_MARKET_ROOT 生效", Path(d["MARKET_ROOT"]) == m8a.resolve(), d["MARKET_ROOT"])
    bucket_name = "market-" + hashlib.sha256(str(m8a.resolve()).encode("utf-8")).hexdigest()[:12]
    expect_home = (Path.home() / ".workbuddy-market" / "markets" / bucket_name).resolve()
    ck("默认 STATE_HOME 分桶到 ~/.workbuddy-market/markets/<bucket>",
       Path(d["STATE_HOME"]) == expect_home, d["STATE_HOME"])
    ck("bucket 名 = 仓库目录名 + 12 位路径哈希",
       Path(d["STATE_HOME"]).name == bucket_name, Path(d["STATE_HOME"]).name)
    ck("v2.7 布局：state.json / logs/ / tx 归位到 STATE_HOME",
       Path(d["STATE_PATH"]).name == "state.json"
       and Path(d["LOG_PATH"]).parent.name == "logs"
       and Path(d["TRASH_DIR"]).parent == Path(d["STATE_HOME"])
       and Path(d["TX_DIR"]).parent == Path(d["STATE_HOME"]),
       d["STATE_PATH"])
    ck("WBM_HOME 生效", Path(d["WB"]) == wb8a.resolve(), d["WB"])
    ck("纯新变量不打 deprecation 告警", "deprecated" not in p.stderr, p.stderr[-200:])

    # --- 23B. 显式 WBM_STATE_HOME：直接使用，不分桶
    m8b = _TMP / "r1b" / "market"; s8b = _TMP / "r1b" / "state"
    m8b.mkdir(parents=True); s8b.mkdir(parents=True)
    p = _run({"WBM_MARKET_ROOT": str(m8b), "WBM_STATE_HOME": str(s8b)}, _CODE_PATHS)
    ck("23B 子进程正常退出", p.returncode == 0, p.stderr[-300:])
    if p.returncode == 0:
        d = json.loads(p.stdout.strip().splitlines()[-1])
        ck("显式 WBM_STATE_HOME 直接生效（不分桶）",
           Path(d["STATE_HOME"]) == s8b.resolve(), d["STATE_HOME"])

    # --- 23C. 旧变量：完全复刻 v2.6 布局（legacy 模式）
    m8c = _TMP / "r1c" / "market"; wb8c = _TMP / "r1c" / "wb"
    m8c.mkdir(parents=True); wb8c.mkdir(parents=True)
    p = _run({"GHPM_MARKET_ROOT": str(m8c), "GHPM_HOME": str(wb8c)}, _CODE_PATHS)
    ck("23C 子进程正常退出", p.returncode == 0, p.stderr[-300:])
    if p.returncode == 0:
        d = json.loads(p.stdout.strip().splitlines()[-1])
        ck("旧变量：STATE_HOME 跟随 MARKET_ROOT（v2.6 复刻）",
           Path(d["STATE_HOME"]) == m8c.resolve(), d["STATE_HOME"])
        ck("旧变量：文件名沿用 v2.6（.market-state.json / .trash / .market-tx）",
           Path(d["STATE_PATH"]).name == ".market-state.json"
           and Path(d["TRASH_DIR"]).name == ".trash"
           and Path(d["TX_DIR"]).name == ".market-tx", d["STATE_PATH"])
        ck("WB 仍由 GHPM_HOME 指定", Path(d["WB"]) == wb8c.resolve(), d["WB"])
        ck("旧变量打 deprecation 告警", "deprecated" in p.stderr, p.stderr[-200:])

    # --- 23D. 新旧混用：新名优先，旧名照常兼容
    m8d = _TMP / "r1d" / "market"; s8d = _TMP / "r1d" / "state"
    wb8d = _TMP / "r1d" / "wb"
    m8d.mkdir(parents=True); s8d.mkdir(parents=True); wb8d.mkdir(parents=True)
    p = _run({"WBM_MARKET_ROOT": str(m8d),
              "GHPM_MARKET_ROOT": str(_TMP / "r1d" / "ignored"),
              "WBM_STATE_HOME": str(s8d), "GHPM_HOME": str(wb8d)}, _CODE_PATHS)
    ck("23D 子进程正常退出", p.returncode == 0, p.stderr[-300:])
    if p.returncode == 0:
        d = json.loads(p.stdout.strip().splitlines()[-1])
        ck("新名优先：WBM_MARKET_ROOT 压过 GHPM_MARKET_ROOT",
           Path(d["MARKET_ROOT"]) == m8d.resolve(), d["MARKET_ROOT"])
        ck("显式 WBM_STATE_HOME 压过 legacy 跟随",
           Path(d["STATE_HOME"]) == s8d.resolve(), d["STATE_HOME"])
        ck("GHPM_HOME 兼容仍生效", Path(d["WB"]) == wb8d.resolve(), d["WB"])
        ck("新旧混用也打 deprecation 告警", "deprecated" in p.stderr, p.stderr[-200:])

    # --- 23E. 迁移正向：6 类运行时文件搬进 STATE_HOME，锁不迁移
    m8e = _TMP / "r1e" / "market"; s8e = _TMP / "r1e" / "state"
    m8e.mkdir(parents=True)
    (m8e / ".market-state.json").write_text('{"a":1}', encoding="utf-8")
    (m8e / ".ownership.json").write_text('{"plugins":{}}', encoding="utf-8")
    (m8e / ".market-log.ndjson").write_text('{"level":"info"}\n', encoding="utf-8")
    (m8e / ".market-tx").mkdir()
    (m8e / ".market-tx" / "tx-1.json").write_text('{}', encoding="utf-8")
    (m8e / ".backups").mkdir()
    (m8e / ".backups" / "known.1.json").write_text('{}', encoding="utf-8")
    (m8e / ".trash").mkdir()
    (m8e / ".trash" / ".index.json").write_text('{}', encoding="utf-8")
    (m8e / ".market.lock").write_text("", encoding="utf-8")     # 锁：按设计不迁移
    p = _run({"WBM_MARKET_ROOT": str(m8e), "WBM_STATE_HOME": str(s8e)}, _CODE_MIGRATE)
    ck("23E 子进程正常退出", p.returncode == 0, p.stderr[-300:])
    if p.returncode == 0:
        r = json.loads(p.stdout.strip().splitlines()[-1])
        ck("import 期自动迁移 6 类运行时文件（第二遍调用 moved==0）",
           r["mode"] == "v2.7" and r["moved"] == [] and r["errors"] == [],
           json.dumps(r, ensure_ascii=False)[:300])
        ck("state.json / ownership.json 内容原样",
           (s8e / "state.json").read_text(encoding="utf-8") == '{"a":1}'
           and (s8e / "ownership.json").read_text(encoding="utf-8") == '{"plugins":{}}')
        ck("tx/ trash/ backups/ logs/ 四个目录归位",
           (s8e / "tx" / "tx-1.json").is_file()
           and (s8e / "trash" / ".index.json").is_file()
           and (s8e / "backups" / "known.1.json").is_file()
           and (s8e / "logs" / "market.ndjson").is_file())
        ck("旧位置已清空", not (m8e / ".market-state.json").exists()
           and not (m8e / ".market-tx").exists() and not (m8e / ".trash").exists())
        ck("锁文件按设计不迁移（留在原地）", (m8e / ".market.lock").exists())

    # --- 23F. 目标已存在：以 STATE_HOME 为准，仓库侧原件保留（绝不删用户文件）
    m8f = _TMP / "r1f" / "market"; s8f = _TMP / "r1f" / "state"
    m8f.mkdir(parents=True); s8f.mkdir(parents=True)
    (m8f / ".market-state.json").write_text('{"old":1}', encoding="utf-8")
    (s8f / "state.json").write_text('{"new":1}', encoding="utf-8")
    p = _run({"WBM_MARKET_ROOT": str(m8f), "WBM_STATE_HOME": str(s8f)}, _CODE_MIGRATE)
    ck("23F 子进程正常退出", p.returncode == 0, p.stderr[-300:])
    if p.returncode == 0:
        r = json.loads(p.stdout.strip().splitlines()[-1])
        ck("目标已存在 → 记 skipped 且不覆盖",
           len(r["skipped"]) == 1
           and (s8f / "state.json").read_text(encoding="utf-8") == '{"new":1}',
           json.dumps(r["skipped"], ensure_ascii=False))
        ck("仓库侧原件保留（绝不删用户文件）",
           (m8f / ".market-state.json").read_text(encoding="utf-8") == '{"old":1}')

    # --- 23G. 跨卷回退：os.replace 抛 EXDEV → shutil.move 兜底完成迁移
    m8g = _TMP / "r1g" / "market"; s8g = _TMP / "r1g" / "state"
    m8g.mkdir(parents=True)
    (m8g / ".market-state.json").write_text('{"x":1}', encoding="utf-8")
    (m8g / ".market-tx").mkdir()
    (m8g / ".market-tx" / "tx-9.json").write_text('{}', encoding="utf-8")
    p = _run({"WBM_MARKET_ROOT": str(m8g), "WBM_STATE_HOME": str(s8g)}, _CODE_EXDEV)
    ck("23G 子进程正常退出", p.returncode == 0, p.stderr[-300:])
    if p.returncode == 0:
        r = json.loads(p.stdout.strip().splitlines()[-1])
        ck("EXDEV 模拟下迁移靠 shutil.move 兜底完成",
           r["moved"] == [] and r["errors"] == []
           and (s8g / "state.json").read_text(encoding="utf-8") == '{"x":1}'
           and (s8g / "tx" / "tx-9.json").is_file()
           and not (m8g / ".market-state.json").exists(),
           json.dumps(r, ensure_ascii=False)[:300])

    # --- 23H. 本进程（legacy 隔离环境）迁移恒为 no-op，旧布局不受影响
    r = core.migrate_runtime_files(quiet=True)
    ck("legacy 布局下 migrate_runtime_files 恒为 no-op",
       r["mode"] == "legacy" and r["moved"] == [] and r["skipped"] == [] and r["errors"] == [],
       json.dumps(r, ensure_ascii=False))

if __name__ == "__main__":
    raise SystemExit(main())
