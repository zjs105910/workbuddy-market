# -*- coding: utf-8 -*-
"""第 20-21 节（第五、六轮）：事务模型闭环 + 真 tail + 鉴权加固 / 并发压力 + 崩溃点矩阵。"""
from __future__ import annotations

import http.client
import json
import os
import shutil
import threading
import time
from pathlib import Path
from . import SELFTEST_VERSION, ck, core, section, sk, wm, _make_link, _drop_link


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


