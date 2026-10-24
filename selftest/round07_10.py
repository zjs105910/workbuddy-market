# -*- coding: utf-8 -*-
"""第 22-25 节（第七至十轮）：ghpm 事件解析 / R1 运行时分离 / R2 基础设施包 / R3 模块迁入。"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from . import REPO_ROOT, SELFTEST_VERSION, _TMP, ck, core, section, wm


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
       any("✗" in ln and "ghpm 执行失败" in ln for ln in lines7), str(lines7))
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
    ck("★ ★ 优先展示 ghpm 给出的 error 原文", ok is False and any("✗ boom" in ln for ln in lines7),
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
       ok is False and not any(ln.startswith("$ ") for ln in lines7)
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
    m8a = _TMP / "r1a" / "market"
    wb8a = _TMP / "r1a" / "wb"
    m8a.mkdir(parents=True)
    wb8a.mkdir(parents=True)
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
    m8b = _TMP / "r1b" / "market"
    s8b = _TMP / "r1b" / "state"
    m8b.mkdir(parents=True)
    s8b.mkdir(parents=True)
    p = _run({"WBM_MARKET_ROOT": str(m8b), "WBM_STATE_HOME": str(s8b)}, _CODE_PATHS)
    ck("23B 子进程正常退出", p.returncode == 0, p.stderr[-300:])
    if p.returncode == 0:
        d = json.loads(p.stdout.strip().splitlines()[-1])
        ck("显式 WBM_STATE_HOME 直接生效（不分桶）",
           Path(d["STATE_HOME"]) == s8b.resolve(), d["STATE_HOME"])

    # --- 23C. 旧变量：完全复刻 v2.6 布局（legacy 模式）
    m8c = _TMP / "r1c" / "market"
    wb8c = _TMP / "r1c" / "wb"
    m8c.mkdir(parents=True)
    wb8c.mkdir(parents=True)
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
    m8d = _TMP / "r1d" / "market"
    s8d = _TMP / "r1d" / "state"
    wb8d = _TMP / "r1d" / "wb"
    m8d.mkdir(parents=True)
    s8d.mkdir(parents=True)
    wb8d.mkdir(parents=True)
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
    m8e = _TMP / "r1e" / "market"
    s8e = _TMP / "r1e" / "state"
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
    m8f = _TMP / "r1f" / "market"
    s8f = _TMP / "r1f" / "state"
    m8f.mkdir(parents=True)
    s8f.mkdir(parents=True)
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
    m8g = _TMP / "r1g" / "market"
    s8g = _TMP / "r1g" / "state"
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
    repo = REPO_ROOT
    env_c = {k: v for k, v in os.environ.items()
             if not k.startswith(("WBM_", "GHPM_"))}
    code_c = (
        "import market_core as c;"
        "assert (c.MARKET_ROOT / 'market.config.example.json').is_file(), c.MARKET_ROOT;"
        "assert '.workbuddy-market' in str(c.STATE_HOME), c.STATE_HOME;"
        "assert c.MARKET_VERSION == '2.37.0', c.MARKET_VERSION;"
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
       wm.version.MARKET_VERSION == "2.37.0"
       and core.MARKET_VERSION == "2.37.0"
       and SELFTEST_VERSION == "2.37", core.MARKET_VERSION)

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
    src = d / "src"
    dst = d / "dst"
    src.mkdir(parents=True)
    dst.mkdir(parents=True)
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


