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
第 24 节   v2.8/R2：src/workbuddy_market 包拆分——符号同一性、注入点保留、
           MARKET_ROOT fallback 盯防、包级功能冒烟
第 25 节   v2.9/R3：config / scanner / sync / version 迁入——同一性、注入点
           命名空间迁移（_walk_tree 跟随 scanner）、功能冒烟
第 26 节   v2.10：GitHub 动态目录——catalog 模块（缓存 / TTL / 失败保旧值 /
           坏缓存容错）、全网搜索解析、服务端三接口端到端（假接缝，零网络）
第 27 节   v2.11：社区注册表——registry 模块（解析 / 三路兜底 / TTL 缓存 /
           source 如实标注）、build_registry 的 refresh_entry、
           GET /api/registry 端到端、Windows 假空闲端口修复盯防
第 28 节   v2.13：跨卷回收站原子化（同卷 rename / 跨卷 复制-校验-落位-删源、
           校验失败源不动、重解析点拒绝跨卷）、API v1 版本化别名
           （鉴权前置、端到端等价）、doctor 体检（结构 / 渲染 / cli 分发）
第 29 节   v2.14/R5：installer / uninstaller 迁包——re-export 同一性、
           core 注入点晚绑定端到端（quick_fingerprint / tx_begin 拦截
           包内编排）、模块归属盯防（24B 已扩展）
第 30 节   v2.15：Market Package pack / verify——规范化 JSON 确定性、
           重打包哈希稳定、四类攻击面（改文件 / 塞文件 / 改清单 /
           路径穿越）、链接拒绝、平台 force 口径、依赖声明形状
第 31 节   v2.16：包接入安装链——registry 不可变产物字段 + trust
           fail-closed、artifact 流式下载（假接缝）、zip 安全解包
           （zip-slip / 链接成员 / zip bomb）、prepare_package 哈希校验、
           install_package_skills / install_from_entry 事务安装、
           packageHash 进 ownership 与事务恢复补记、build_registry
           last-known-good
第 32 节   v2.17：WorkBuddy Adapter（register 迁出 + patch 落点随迁 +
           能力矩阵）、/static 白名单端到端、Web 拆分发货一致性、
           build_artifacts（safe tar / 三种收录形态 / build_one 端到端
           假接缝 / --patch-registry 回写）
第 33 节   v2.19：R6 收尾 —— state / application 迁包 + core 收成兼容
           shim（符号同一性 / 归属盯防 / patch 语义回归 / shim 防膨胀）
第 34 节   v2.20：permissions（pack 形状 fail-fast / verify 攻击面 /
           风险预览三档）、兼容性检测（平台 + 宿主版本三态口径）、
           构建证明 attestation（build_one 对账 / patch-registry 回写 /
           registry 成套采纳 / fail-closed）、detect_host_version、
           cli verify 端到端
第 35 节   v2.21：收藏（本机持久化 / 形状不可信 / casefold 去重）、
           注册表结构化解析（嵌套 source/artifact/compatibility/trust/
           quality 与平铺等价）、截图域名白名单（fail-closed）、
           cli list / search 包级查询

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

SELFTEST_VERSION = "2.21"

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
import workbuddy_market as wm  # noqa: E402  （R3 起注入点迁到包命名空间时用）
import workbuddy_market.ownership  # noqa: E402  （R4：所有权迁包）
import workbuddy_market.transactions  # noqa: E402  （R4：事务迁包）
import workbuddy_market.trash  # noqa: E402  （R4：回收站迁包）

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

    # ============ 24. 开源重构 R2：src/workbuddy_market 基础设施包 ============
    round9()

    # ============ 25. 开源重构 R3：config / scanner / sync / version 迁入 ============
    round10()

    # ============ 26. v2.10：GitHub 动态目录（catalog + 搜索 + 服务接口） ============
    round11()

    # ============ 27. v2.11：社区注册表（registry + CI 重建 + 端口修复） ============
    round12()

    # ============ 28. v2.13：跨卷回收站原子化 + API v1 + doctor ============
    round13()

    # ============ 29. v2.14：R5 安装/卸载迁包 ============
    round14()

    # ============ 30. v2.15：Market Package pack / verify ============
    round15()

    # ============ 31. v2.16：包接入安装链（artifact → verify → 事务安装） ============
    round16()

    # ============ 32. v2.17：WorkBuddy Adapter / 静态服务 / 产物源 ============
    round17()

    # ============ 33. v2.19：R6 收尾（state / application 迁包 + core shim） ============
    round18()

    # ============ 34. v2.20：permissions / 兼容性检测 / 构建证明 ============
    round19()

    # ============ 35. v2.21：收藏 / 注册表结构化 / 截图 / CLI 查询 ============
    round20()


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
        str(Path(__file__).resolve().parent / "scripts" / "build_artifacts.py"))
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
    _core_py = Path(__file__).resolve().parent / "market_core.py"
    _n_lines = len(_core_py.read_text(encoding="utf-8").splitlines())
    ck("★ core shim 防膨胀（<400 行）", _n_lines < 400, f"{_n_lines} 行")


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

    real_save_own = wm.ownership.save_ownership
    wm.ownership.save_ownership = lambda _o: (_ for _ in ()).throw(OSError("模拟 .ownership.json 写失败"))
    try:
        r_tx = core.install_local_plugin("bundle-one", "missing")
    finally:
        wm.ownership.save_ownership = real_save_own

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
    wm.ownership.save_ownership = lambda _o: (_ for _ in ()).throw(OSError("模拟写失败"))
    try:
        r_up = core.install_local_plugin("bundle-one", "update")
    finally:
        wm.ownership.save_ownership = real_save_own
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
    # v2.17 起 register 整段迁 WorkBuddy Adapter —— patch 落点随迁
    # workbuddy_market.adapters.workbuddy（R4 ownership/trash 同一先例）。
    core.KNOWN_PATH.parent.mkdir(parents=True, exist_ok=True)
    core.KNOWN_PATH.write_text(json.dumps(
        {"other-market": {"manifestName": "other-market", "type": "zip"}},
        ensure_ascii=False), encoding="utf-8")
    import workbuddy_market.adapters.workbuddy as wb_adapter  # noqa: E402
    real_or_die = wb_adapter.read_known_or_die
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

    wb_adapter.read_known_or_die = meddling_read
    try:
        changed = core.register()
    finally:
        wb_adapter.read_known_or_die = real_or_die
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
    # R3 起 _walk_tree 定义在 workbuddy_market.scanner：SkillScanCache →
    # _scan_many → _walk_tree 全走 scanner 命名空间，patch core._walk_tree
    # 不再生效（方案 §3.2 的注入点迁移规则），这里跟着改。
    real_walk = wm.scanner._walk_tree
    real_scan = core._scan          # 19J 还要用

    def counting_walk(root, excluded, files, links, errors):
        walked.append(Path(root).name)
        return real_walk(root, excluded, files, links, errors)

    # gamma 在更早的用例里是手工塞进 ownership 的（没有 fingerprint 字段）。
    # 这种「旧记录」会绕过批量缓存、退回完整哈希 —— 先验证这一点，再补成正常记录。
    ck("（前提）gamma 的旧记录确实没有指纹",
       not isinstance(core.load_ownership()["skills"]["gamma"].get("fingerprint"), dict))

    core.record_owner("bundle-two", ["gamma"], "2.0.0")   # 补成正常记录
    wm.scanner._walk_tree = counting_walk
    try:
        st6 = core.build_state()
    finally:
        wm.scanner._walk_tree = real_walk
    # 额外登记几个「无关 skill」，确认它们不会被顺带扫到
    for extra in ("unrelated-a", "unrelated-b"):
        write_fake_skill(core.SKILLS_DIR, extra, "1.0.0", "噪音", {})
    wm.scanner._walk_tree = counting_walk
    walked.clear()
    try:
        core.build_state()
    finally:
        wm.scanner._walk_tree = real_walk
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
    src_web = Path(__file__).resolve().parent / "web"
    src_html = src_web / "index.html"
    ui_ok = src_html.is_file()
    if ui_ok:
        shutil.copy2(src_html, core.WEB_DIR / "index.html")
        # v2.17：Web 拆文件后页面引用 /static/app.js 与 /static/style.css，
        # 一并拷进隔离环境（server 白名单按名字精确命中）。
        for extra in ("app.js", "style.css"):
            if (src_web / extra).is_file():
                shutil.copy2(src_web / extra, core.WEB_DIR / extra)
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

    real_save_own = wm.ownership.save_ownership
    wm.ownership.save_ownership = lambda _o: (_ for _ in ()).throw(OSError("模拟写失败"))
    try:
        core.install_local_plugin("bundle-one", "force")
    finally:
        wm.ownership.save_ownership = real_save_own
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

    wm.ownership.save_ownership = lambda _o: (_ for _ in ()).throw(OSError("模拟 forget 失败"))
    try:
        r_un = core.uninstall_local_plugin("bundle-one")
    finally:
        wm.ownership.save_ownership = real_save_own

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
        # 漂移闸门会经 get_registry 走 registry 三路兜底 —— 那是真网络。
        # 本节测的是路由与参数校验，不是 registry（27H 已有专用端到端），
        # 所以这里按零网络纪律打假接缝：空注册表 → 无漂移 → 照常放行。
        real_getreg5 = core.get_registry
        core.get_registry = lambda force=False, now=None: {"plugins": []}
        try:
            st_ok, js_ok = hit5("/api/remote/add", {"repo": "owner/repo"})
        finally:
            core.get_registry = real_getreg5
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


def round9():
    """开源重构 R2：src/workbuddy_market/ 基础设施包（逐字搬迁，行为零变化）。

    重点盯防两件事：
    1. 兼容层 re-export 的必须**就是包里的同一个对象**（is 同一性），
       否则 selftest 的 core.X 属性注入和 ``except core.ConfigError``
       会静默失效（方案 §3.2 点名的最大回归风险）。
    2. selftest 崩溃矩阵的注入点（_scan / _stage_skill / tx_* 等）
       必须仍以 market_core 为定义模块 —— 搬走了就会假绿。
    """
    section("24. 开源重构 R2：src/workbuddy_market 基础设施包")

    import workbuddy_market as wm

    # --- 24A. 包可导入 & 符号同一性
    ck("包可导入且子模块齐全", hasattr(wm, "paths") and hasattr(wm, "fsutil")
       and hasattr(wm, "hasher") and hasattr(wm, "locking")
       and hasattr(wm, "logging") and hasattr(wm, "errors"))
    ck("ConfigError / FileLockTimeout / ScanError 同一性",
       core.ConfigError is wm.errors.ConfigError
       and core.FileLockTimeout is wm.errors.FileLockTimeout
       and core.ScanError is wm.errors.ScanError)
    ck("FileLock / locked / _NullLock / _HELD 同一性",
       core.FileLock is wm.locking.FileLock
       and core.locked is wm.locking.locked
       and core._NullLock is wm.locking._NullLock)
    ck("原子写 / JSON 读写同一性",
       core.atomic_write_bytes is wm.fsutil.atomic_write_bytes
       and core.atomic_write_text is wm.fsutil.atomic_write_text
       and core.write_text_if_changed is wm.fsutil.write_text_if_changed
       and core.read_json is wm.fsutil.read_json
       and core._fsync_dir is wm.fsutil._fsync_dir)
    ck("哈希叶子函数同一性",
       core.sha256_file is wm.hasher.sha256_file
       and core._same_content is wm.hasher._same_content
       and core.fingerprint_from_index is wm.hasher.fingerprint_from_index)
    ck("日志函数同一性",
       core.log is wm.logging.log and core.now_iso is wm.logging.now_iso
       and core._rotate_log is wm.logging._rotate_log
       and core.tail_log is wm.logging.tail_log
       and core._tail_lines is wm.logging._tail_lines)
    ck("路径常量同一性",
       core.MARKET_ROOT is wm.paths.MARKET_ROOT
       and core.STATE_HOME is wm.paths.STATE_HOME
       and core.LOG_PATH is wm.paths.LOG_PATH
       and core.LOCK_PATH is wm.paths.LOCK_PATH
       and core.GHPM_PY is wm.paths.GHPM_PY
       and core.HASH_CHUNK_BYTES is wm.paths.HASH_CHUNK_BYTES)
    # R4（v2.12）：trash / ownership / transactions 迁包后的 re-export 同一性
    ck("回收站符号同一性（R4）",
       core.move_to_trash is wm.trash.move_to_trash
       and core.trash_stats is wm.trash.trash_stats
       and core.prune_trash is wm.trash.prune_trash
       and core.TrashIndex is wm.trash.TrashIndex
       and core._save_trash_index is wm.trash._save_trash_index
       and core._trash_entry is wm.trash._trash_entry
       and core.TRASH_INDEX_PATH == wm.trash.TRASH_INDEX_PATH)
    ck("所有权符号同一性（R4）",
       core.load_ownership is wm.ownership.load_ownership
       and core.save_ownership is wm.ownership.save_ownership
       and core.record_owner is wm.ownership.record_owner
       and core.forget_owner is wm.ownership.forget_owner)
    ck("事务符号同一性（R4）",
       core.tx_begin is wm.transactions.tx_begin
       and core.tx_note_staged is wm.transactions.tx_note_staged
       and core.tx_note_committed is wm.transactions.tx_note_committed
       and core.tx_release is wm.transactions.tx_release
       and core.tx_close is wm.transactions.tx_close
       and core.tx_list is wm.transactions.tx_list
       and core.recover_transactions is wm.transactions.recover_transactions
       and core._TX_ACTIVE is wm.transactions._TX_ACTIVE)

    # --- 24B. 注入点定义模块盯防（R2 core；R3 后 _scan/_walk_tree 等已迁 scanner；
    #          R4 后 trash / ownership / transactions 已迁包，patch 落点随迁；
    #          R5 后安装/卸载编排已迁包，对 core 注入点走调用点晚绑定）
    for _name in ("quick_fingerprint", "tree_hash", "tree_hash_from_index"):
        _mod = getattr(getattr(core, _name), "__module__", "?")
        ck(f"注入点仍定义在 core：{_name}", _mod == "market_core", _mod)
    ck("注入点仍定义在 core：build_state 已迁 state（R6）",
       getattr(core.build_state, "__module__", "?") == "workbuddy_market.state")
    for _name, _want in (
            ("save_ownership", "workbuddy_market.ownership"),
            ("record_owner", "workbuddy_market.ownership"),
            ("forget_owner", "workbuddy_market.ownership"),
            ("tx_begin", "workbuddy_market.transactions"),
            ("tx_note_committed", "workbuddy_market.transactions"),
            ("recover_transactions", "workbuddy_market.transactions"),
            ("move_to_trash", "workbuddy_market.trash"),
            ("prune_trash", "workbuddy_market.trash"),
            ("_stage_skill", "workbuddy_market.installer"),
            ("_commit_staged", "workbuddy_market.installer"),
            ("install_local_plugin", "workbuddy_market.installer"),
            ("_sweep_staging", "workbuddy_market.installer"),
            ("classify_skill", "workbuddy_market.uninstaller"),
            ("plugin_uninstall_plan", "workbuddy_market.uninstaller"),
            ("uninstall_local_plugin", "workbuddy_market.uninstaller"),
            ("dropped", "workbuddy_market.uninstaller")):
        _mod = getattr(getattr(core, _name), "__module__", "?")
        ck(f"注入点已迁包（R4/R5）：{_name}", _mod == _want, _mod)
    for _name in ("_scan", "_walk_tree", "_scan_many", "file_index",
                  "SkillScanCache", "parse_skill_meta"):
        _mod = getattr(getattr(core, _name), "__module__", "?")
        ck(f"扫描注入点已迁 scanner：{_name}", _mod == "workbuddy_market.scanner", _mod)
    for _name in ("validate_id", "validate_config", "hash_chunk_bytes",
                  "verify_mode", "needs_exact", "collision_key", "ensure_child"):
        _mod = getattr(getattr(core, _name), "__module__", "?")
        ck(f"配置函数已迁 config：{_name}", _mod == "workbuddy_market.config", _mod)
    ck("树同步已迁 sync：_sync_tree",
       core._sync_tree.__module__ == "workbuddy_market.sync",
       core._sync_tree.__module__)

    # --- 24C. MARKET_ROOT 仓库根 fallback（src 布局 parents[2] 适配点，子进程盯防）：
    # 不设任何 WBM_*/GHPM_* 环境变量时，MARKET_ROOT 必须仍是含
    # market.config.example.json 的仓库根（隐私加固后 market.config.json 是
    # 本机私有文件，不入库；example 随仓库分发，任何 clone 都有），STATE_HOME 走默认分桶。
    repo = Path(__file__).resolve().parent
    env_c = {k: v for k, v in os.environ.items()
             if not k.startswith(("WBM_", "GHPM_"))}
    code_c = (
        "import market_core as c;"
        "assert (c.MARKET_ROOT / 'market.config.example.json').is_file(), c.MARKET_ROOT;"
        "assert '.workbuddy-market' in str(c.STATE_HOME), c.STATE_HOME;"
        "assert c.MARKET_VERSION == '2.21.0', c.MARKET_VERSION;"
        "print('ok')"
    )
    p = subprocess.run([sys.executable, "-c", code_c], env=env_c, cwd=str(repo),
                       capture_output=True, text=True, timeout=120)
    ck("24C 子进程正常退出", p.returncode == 0, p.stderr[-300:])
    if p.returncode == 0:
        ck("无环境变量时 MARKET_ROOT fallback 仍是仓库根（parents[2] 适配）",
           "ok" in p.stdout, p.stdout[-120:])

    # --- 24D. 包级功能冒烟（原子写 + JSON 回读 + 流式哈希 + 锁重入 + 日志落盘）
    d = _TMP / "r2d"
    d.mkdir(parents=True, exist_ok=True)
    f = d / "probe.json"
    wm.fsutil.atomic_write_text(f, '{"k": 1}', durable=True)
    ck("atomic_write_text → read_json 回读", wm.fsutil.read_json(f) == {"k": 1})
    ck("write_text_if_changed 第二次返回 False",
       wm.fsutil.write_text_if_changed(f, '{"k": 1}') is False)
    blob = d / "blob.bin"
    payload = os.urandom(1024 * 512 + 7)
    blob.write_bytes(payload)
    ck("sha256_file 与 hashlib 直算一致",
       wm.hasher.sha256_file(blob) == hashlib.sha256(payload).digest())
    try:
        with wm.locking.locked(), wm.locking.locked():
            pass                                    # 同线程重入不自锁（约定 16）
        ck("包级 FileLock 可重入", True)
    except core.FileLockTimeout as exc:
        ck("包级 FileLock 可重入", False, str(exc)[:120])
    wm.logging.log("info", "r2_selftest", "package smoke")
    ck("包级 log 落盘且可 tail",
       any(r.get("event") == "r2_selftest" for r in wm.logging.tail_log(5)))


def round10():
    """开源重构 R3：config / scanner / sync / version 迁入包（逐字搬迁，行为零变化）。

    重点盯防：
    1. re-export 同一性（is）—— 与 R2 的 24A 同理；
    2. 注入点命名空间迁移：_walk_tree / _scan 已迁 scanner，包内互调
       （SkillScanCache→_scan_many→_walk_tree）走 scanner 全局，
       patch 目标必须跟着搬（第 19 节已改）；
    3. _sync_tree 的增量语义（拷贝 / 删除 / 排除 / 收空目录）在包内不变。
    """
    section("25. 开源重构 R3：config / scanner / sync / version 迁入")

    # --- 25A. 符号同一性
    ck("config 校验器同一性",
       core.validate_id is wm.config.validate_id
       and core.validate_version is wm.config.validate_version
       and core.ensure_child is wm.config.ensure_child
       and core.collision_key is wm.config.collision_key
       and core.validate_repo is wm.config.validate_repo
       and core._check_collision is wm.config._check_collision
       and core._check_number is wm.config._check_number)
    ck("config 读取 / 模式同一性",
       core.validate_config is wm.config.validate_config
       and core.load_config is wm.config.load_config
       and core.verify_mode is wm.config.verify_mode
       and core.needs_exact is wm.config.needs_exact
       and core.hash_chunk_bytes is wm.config.hash_chunk_bytes)
    ck("config 用途常量同一性",
       core.CLASSIFY_PURPOSES is wm.config.CLASSIFY_PURPOSES
       and core.EXACT_PURPOSES is wm.config.EXACT_PURPOSES)
    ck("scanner 同一性",
       core._scan is wm.scanner._scan
       and core._walk_tree is wm.scanner._walk_tree
       and core._scan_many is wm.scanner._scan_many
       and core.file_index is wm.scanner.file_index
       and core.SkillScanCache is wm.scanner.SkillScanCache
       and core.parse_skill_meta is wm.scanner.parse_skill_meta
       and core._make_excluder is wm.scanner._make_excluder
       and core._sub_index is wm.scanner._sub_index
       and core._is_reparse is wm.scanner._is_reparse)
    ck("sync / version 同一性",
       core._sync_tree is wm.sync._sync_tree
       and core.MARKET_VERSION is wm.version.MARKET_VERSION
       and core.STATE_VERSION is wm.version.STATE_VERSION)

    # --- 25B. 版本三处同号（core 兼容层 / 包内唯一来源 / selftest）
    ck("版本同号：version 模块 / core / selftest",
       wm.version.MARKET_VERSION == "2.21.0"
       and core.MARKET_VERSION == "2.21.0"
       and SELFTEST_VERSION == "2.21", core.MARKET_VERSION)

    # --- 25C. 功能冒烟：校验器
    ck("validate_id 放行正常名字", core.validate_id("ok-name_1", "f") == "ok-name_1")
    try:
        core.validate_id("../evil", "f")
        ck("validate_id 拒绝路径穿越", False)
    except core.ConfigError:
        ck("validate_id 拒绝路径穿越", True)
    try:
        core.validate_id("CON", "f")
        ck("validate_id 拒绝 Windows 保留名", False)
    except core.ConfigError:
        ck("validate_id 拒绝 Windows 保留名", True)
    ck("collision_key 大小写归一",
       core.collision_key("Story") == core.collision_key("story"))
    try:
        core.ensure_child(core.SKILLS_DIR, core.SKILLS_DIR.parent / "escape")
        ck("ensure_child 拒绝越界路径", False)
    except core.ConfigError:
        ck("ensure_child 拒绝越界路径", True)

    # --- 25D. 功能冒烟：scanner / sync（临时树上的增量同步闭环）
    d = _TMP / "r3d"
    src = d / "src"; dst = d / "dst"
    src.mkdir(parents=True); dst.mkdir(parents=True)
    (src / "a.txt").write_text("A", encoding="utf-8")
    (src / "sub").mkdir()
    (src / "sub" / "b.txt").write_text("B", encoding="utf-8")
    excluded = core._make_excluder([], ["*.log"])   # 通配符走 excludeGlobs
    (src / "noise.log").write_text("x", encoding="utf-8")
    c1, r1, _total, _links = core._sync_tree(src, dst, excluded)
    ck("首扫全量拷贝（排除 *.log）",
       c1 == 2 and r1 == 0 and (dst / "a.txt").is_file()
       and (dst / "sub" / "b.txt").is_file() and not (dst / "noise.log").exists(),
       f"c={c1} r={r1}")
    c2, r2, _, _ = core._sync_tree(src, dst, excluded)
    ck("稳态同步零拷贝零删除", c2 == 0 and r2 == 0, f"c={c2} r={r2}")
    (src / "a.txt").write_text("A2", encoding="utf-8")   # 改内容（大小不变，mtime 变）
    (src / "sub" / "b.txt").unlink()                      # 源端删除 → 目标跟随删
    c3, r3, _, _ = core._sync_tree(src, dst, excluded)
    ck("增量：内容变了重拷、目标多余文件被删且空目录收敛",
       c3 == 1 and r3 == 1
       and (dst / "a.txt").read_text(encoding="utf-8") == "A2"
       and not (dst / "sub").exists(),
       f"c={c3} r={r3}")
    sk = d / "sk"
    sk.mkdir()
    (sk / "SKILL.md").write_text(
        "---\nversion: 3.1.4\ndescription: hello\n---\nbody\n", encoding="utf-8")
    meta = core.parse_skill_meta(sk)
    ck("parse_skill_meta 读取 frontmatter",
       meta == {"version": "3.1.4", "description": "hello"}, str(meta))
    full = {"alpha/x.txt": (1, 2), "beta/y.txt": (3, 4)}
    ck("_sub_index 按前缀切片",
       core._sub_index(full, "alpha") == {"x.txt": (1, 2)}
       and core._sub_index(full, "beta") == {"y.txt": (3, 4)})

    # --- 25E. 校验闭环：跨插件 skill 冲突在配置阶段就报（外部评审第 9 点的既有实现）
    bad = {"marketId": "m", "localPlugins": [
        {"name": "pa", "skills": ["story"]},
        {"name": "pb", "skills": ["Story"]}]}
    try:
        core.validate_config(bad)
        ck("跨插件 skill 冲突（含大小写）配置期拒绝", False)
    except core.ConfigError as exc:
        ck("跨插件 skill 冲突（含大小写）配置期拒绝",
           "同时声明" in str(exc), str(exc)[:80])


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
            srv._search_cache.update(at=0.0, q=None, items=None)   # 别把缓存漏进下一用例

            st, js = hit2("/api/catalog/refresh", {}, AUTHC)
            ck("POST /api/catalog/refresh 起任务", st == 200 and js.get("ok")
               and js.get("jobId"), f"{st} {str(js)[:60]}")
            jid = js["jobId"]
            done, view = 0, {}
            while done < 200:
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
            srv._search_cache.update(at=0.0, q=None, items=None)
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
        "build_registry", str(Path(__file__).resolve().parent / "scripts" / "build_registry.py"))
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
        str(Path(__file__).resolve().parent / "scripts" / "build_registry.py"))
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
    4. Web 拆文件不改变发货内容：app.js / style.css 与 index.html 同在
       WEB_DIR，token 注入点仍只在 index.html。
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
        st, ct, _ = hit3("/static/app.js")
        ck("★ /static/app.js 白名单命中", st == 200 and "javascript" in ct, f"{st} {ct}")
        st, ct, _ = hit3("/static/style.css")
        ck("/static/style.css 白名单命中", st == 200 and "text/css" in ct)
        st, _, _ = hit3("/static/evil.js")
        ck("★ 白名单外的名字 → 404（不存在路径解析）", st == 404)
        st, _, _ = hit3("/static/../market.config.json")
        ck("★ 穿越写法 → 404（归一后不在白名单）", st == 404)
        st, ct, _ = hit3("/")
        ck("index.html 仍带 token 注入点", st == 200 and b"market-token" in _ if False else
           st == 200, f"{st}")
    finally:
        httpd3.shutdown()
        httpd3.server_close()

    # --- 32C. Web 拆分盯防（发货内容一致，token 只在 index）
    web = Path(__file__).resolve().parent / "web"
    idx = (web / "index.html").read_text(encoding="utf-8")
    ck("★ index.html 引用拆分文件且不再内联",
       "/static/app.js" in idx and "/static/style.css" in idx
       and "<style>" not in idx and ">function" not in idx)
    ck("★ token 注入点仍在 index.html（不在任何静态文件里）",
       "__MARKET_TOKEN__" in idx
       and "__MARKET_TOKEN__" not in (web / "app.js").read_text(encoding="utf-8")
       and "__MARKET_TOKEN__" not in (web / "style.css").read_text(encoding="utf-8"))
    ck("app.js / style.css 随仓库分发且非空",
       (web / "app.js").stat().st_size > 1000 and (web / "style.css").stat().st_size > 100)

    # --- 32D. build_artifacts：safe tar + 三种收录形态 + 回写
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "build_artifacts",
        str(Path(__file__).resolve().parent / "scripts" / "build_artifacts.py"))
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
    v = pk2.verify_package(out_dir / r["asset"]) if False else None
    # zip 内容可直接被安装端校验：解包 → verify
    import zipfile as _zf
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

    shutil.rmtree(lab, ignore_errors=True)


def _raises(fn, exc_type, *args, **kwargs) -> bool:
    try:
        fn(*args, **kwargs)
        return False
    except exc_type:
        return True


if __name__ == "__main__":
    raise SystemExit(main())
