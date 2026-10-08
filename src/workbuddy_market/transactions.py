# -*- coding: utf-8 -*-
"""transactions —— 安装/卸载事务日志与崩溃恢复（v2.12 R4 自 market_core.py 逐字迁入）。

v2.2 只保证「文件」这一步是事务的：

    PREPARE → COPY → VERIFY → COMMIT

而 record_owner() 在 COMMIT **之后**才跑。一旦写 .ownership.json 失败，
有两种坏结果（都已用探针复现）：

  · 全新安装 —— 文件在盘上、所有权缺失 → classify_skill 判成 foreign，
    这个 skill 永久不再受本市场管辖（既不能更新也不能卸载）。
  · 更新安装 —— 文件已经被换掉，调用方却看到异常；所有权停在旧 hash。

现在把「记所有权」纳入同一份日志，从「文件事务」升级成「文件 + 状态事务」：

    BEGIN → COPY → VERIFY → COMMIT → WRITE_OWNERSHIP → FINALIZE

每个 skill 换位成功就立刻登记进 pendingOwnership；收尾时一次性写所有权，
写成功才清账。中途任何一步崩掉，下次启动 / 下次装改卸之前会自动补记。

v2.3 → v2.4 又补了两条硬约束（第四轮评审，均已用探针复现）：

  ① **凭证必须先于磁盘变更。** 日志要在任何可能改变正式 skill 目录的动作
     *之前* 落盘，并且带上恢复时用来比对的 expected hash。
     v2.3 是 commit 之后才 tx_begin() —— 进程恰好死在那两步之间，磁盘已经
     换成新版本，却没有留下任何恢复凭证。

  ② **恢复要校验内容，不能「看到文件在就认领」。** 崩溃之后、恢复之前，
     用户完全可能自己改过那个 skill。只看「目录还在」就补记所有权，等于把
     用户的改动**洗白**成「市场装的、没改过」—— 之后一键卸载就会搬走它。
     只有当前内容仍等于 commit 那一份才允许认领；不一致就是 conflict，
     保留日志并报出来。

卸载走同一套模型：pendingForget 记「已搬进回收站、所有权还没清」的 skill，
同样在动磁盘之前就有凭证。

注入点接缝（v2.12 R4）：
  · `recover_transactions()` 用的 `tree_hash`（认领比对）与 `_sweep_staging`
    （清暂存）仍在 core（selftest 注入点 / 安装器职责，R4 不迁），调用点
    晚绑定 ``import market_core``，patch 语义与 v2.11 前一致；
  · `say()` 同理（core 的 CLI 输出小工具）；
  · 事务内部互调（tx_begin→tx_save、tx_close→tx_release 等）走本模块
    命名空间；`tx_begin` 的 patch 点仍是 ``core.tx_begin``（调用方
    install/uninstall 在 core，经 re-export 解析）。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .errors import ConfigError, ScanError
from .fsutil import atomic_write_text, read_json
from .paths import TX_DIR, SKILLS_DIR
from .version import TX_SCHEMA
from .logging import now_iso, log
from .locking import locked
from .config import ensure_child
from .ownership import forget_owner, record_owner

_TX_ACTIVE: set = set()        # 本进程正在写的事务 id —— tx_list() 要跳过它们


def tx_path(tx_id: str) -> Path:
    """事务日志路径。tx_id 是我们自己生成的，但仍然过一遍 basename 校验 ——
    将来若有人把外部值传进来，这里就是最后一道闸。"""
    if (not isinstance(tx_id, str) or not tx_id or Path(tx_id).name != tx_id
            or any(ch in tx_id for ch in ("/", "\\", ":", "\x00"))):
        raise ConfigError(f"非法事务 id：{tx_id!r}")
    return TX_DIR / f"{tx_id}.json"


def tx_save(tx: dict) -> None:
    tx["updatedAt"] = now_iso()
    atomic_write_text(tx_path(tx["id"]),
                      json.dumps(tx, ensure_ascii=False, indent=2) + "\n",
                      durable=True)


def tx_begin(operation: str, plugin: str, skills: list, **extra) -> dict:
    """开一份事务日志。**必须在动磁盘之前调用。**

    调用点的标准不是「看着顺眼」，而是：从这里到 tx_close() 之间，无论进程
    在哪一行消失，恢复流程都能仅凭这份日志把状态推回一致。
    """
    TX_DIR.mkdir(parents=True, exist_ok=True)
    tx = {
        "schema": TX_SCHEMA,
        "id": f"{operation}-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
              f"-{time.time_ns() % 1_000_000:06d}",
        "operation": operation,
        "plugin": plugin,
        "skills": sorted(str(s) for s in skills),
        "pid": os.getpid(),
        "pendingOwnership": [],         # [{skill, hash, fingerprint, plugin, version, state}]
        "pendingForget": [],            # 已搬进回收站、所有权还没清的 skill
        "startedAt": now_iso(),
    }
    tx.update(extra)
    tx_save(tx)
    _TX_ACTIVE.add(tx["id"])
    return tx


def _tx_put(tx: dict, sname: str, **fields) -> None:
    pend = [e for e in (tx.get("pendingOwnership") or [])
            if not (isinstance(e, dict) and e.get("skill") == sname)]
    entry = {"skill": sname, "plugin": tx.get("plugin") or "",
             "version": tx.get("version") or ""}
    entry.update({k: v for k, v in fields.items() if v is not None})
    pend.append(entry)
    tx["pendingOwnership"] = sorted(pend, key=lambda e: e.get("skill", ""))


def tx_note_staged(tx: dict, sname: str, expected: dict | None = None,
                   plugin: str | None = None, version: str | None = None) -> None:
    """**换位之前**落盘：记下这次 commit 完成之后应该长什么样。

    为什么要提前记：如果只记「已交付」，那么「os.replace 成功 → 写日志」这个
    窗口里崩掉，磁盘已经是新版本、日志却什么都没写 —— 恢复流程两眼一抹黑。
    提前记下的 expected hash 就是那个窗口的凭证。

    state="staged" 表示「我打算换，但还没确认换成功」。恢复时：
      · 磁盘内容 == expected  → 其实换成功了（崩在 replace 之后）→ 认领
      · 磁盘内容 != expected  → 没换，或已被改动 → **不认领**（也不报冲突，
        因为这次交付本来就没完成）
    """
    _tx_put(tx, sname, state="staged",
            hash=(expected or {}).get("hash"),
            fingerprint=(expected or {}).get("fingerprint"),
            plugin=plugin, version=version)
    tx_save(tx)


def tx_note_committed(tx: dict, sname: str) -> None:
    """换位成功 —— 把该条目升级成 committed。

    升级之后就"交付确认"了：此后磁盘内容只要和 expected 不一致，一定是有人
    在崩溃之后改过它，恢复流程必须拒绝认领并报冲突。
    """
    for e in (tx.get("pendingOwnership") or []):
        if isinstance(e, dict) and e.get("skill") == sname and e.get("state") != "committed":
            e["state"] = "committed"
            tx_save(tx)
            return


def tx_note_removed(tx: dict, sname: str) -> None:
    """某个 skill 已经搬进回收站 —— 登记「待清所有权」。"""
    fg = set(tx.get("pendingForget") or ())
    fg.add(sname)
    tx["pendingForget"] = sorted(fg)
    tx_save(tx)


def tx_drop(tx: dict, sname: str) -> None:
    """把某条待办从日志里摘掉（收尾时用）。只改内存，由调用方决定何时 tx_save。"""
    tx["pendingOwnership"] = [
        e for e in (tx.get("pendingOwnership") or [])
        if not (isinstance(e, dict) and e.get("skill") == sname)]


def tx_settled(tx: dict) -> bool:
    """这份日志还有没有未了结的事。"""
    return not (tx.get("pendingOwnership") or tx.get("pendingForget"))


def tx_release(tx: dict) -> None:
    """操作结束了，但账还没清 —— 把日志交还给恢复流程。

    必须显式释放：`_TX_ACTIVE` 是「本进程正在改这份日志」的意思，
    如果一次安装带着未了结的条目就结束了，还把它留在 _TX_ACTIVE 里，
    同一进程里的 recover_transactions() 就永远看不到它。
    """
    _TX_ACTIVE.discard(tx["id"])


def tx_close(tx: dict) -> None:
    tx_release(tx)
    try:
        tx_path(tx["id"]).unlink()
    except OSError:
        pass


def tx_list() -> list:
    """列出还挂着的日志。**本进程正在写的不算**（按 id 认，不靠 pid 猜）。"""
    if not TX_DIR.is_dir():
        return []
    out = []
    for p in sorted(TX_DIR.glob("*.json")):
        rec = read_json(p, None)
        if not isinstance(rec, dict):
            try:
                p.unlink()
            except OSError:
                pass
            continue
        if rec.get("id") in _TX_ACTIVE:
            continue                    # 本进程正在跑的事务，别碰
        out.append(rec)
    return out


def recover_transactions(quiet: bool = True, discard_conflicts: bool = False) -> dict:
    """补账：把上一次没走完的事务收尾。

    在每次打包 / 安装 / 卸载之前，以及服务启动时调用。
    持市场锁运行 —— 同一时刻只会有一次操作，所以这里看到的日志要么属于
    已经结束的操作，要么属于已经崩掉的进程。

    **认领的条件是「内容还是当初那一份」，不是「目录还在」：**

      pendingOwnership，state="staged"    → 还没确认交付；内容对上才认领，对不上静默放过
      pendingOwnership，state="committed" → 已确认交付；内容对不上 = 有人改过 → conflict
      pendingForget                       → 目录确实不在了才清所有权；还在说明当时没搬成

    conflict 会**保留日志**并报出来：要么用户重装覆盖（内容对上了自然消解），
    要么显式 discard_conflicts=True 表示「这次的账不要了」。默认绝不替用户决定。
    """
    import market_core as _core          # noqa: PLC0415 —— tree_hash/_sweep_staging/say 晚绑定
    recovered, finished, failed, conflicts = [], [], [], []
    with locked():
        stale = _core._sweep_staging()
        for tx in tx_list():
            txid = tx.get("id", "?")

            # --- 认领：必须内容对得上 ---
            claim, snapshots, versions = [], {}, {}
            for entry in (tx.get("pendingOwnership") or []):
                if not isinstance(entry, dict):
                    continue
                s = entry.get("skill")
                if not isinstance(s, str):
                    continue
                d = SKILLS_DIR / s
                try:
                    ensure_child(SKILLS_DIR, d)
                except ConfigError:
                    continue
                if not (d / "SKILL.md").is_file():
                    continue            # 落位后又被人删了 → 没什么可认领
                want = entry.get("hash")
                try:
                    got = _core.tree_hash(d)
                except ScanError as exc:
                    log("warn", "tx", f"跳过 {s}：内容读不全（{exc}），不认领")
                    conflicts.append({"tx": txid, "skill": s,
                                      "expected": want, "actual": None,
                                      "reason": "unreadable"})
                    continue
                if want and got != want:
                    if entry.get("state") == "committed":
                        # 交付确认过，现在内容却不对 —— 一定是崩溃之后有人改了它。
                        # 认领 = 把用户的改动洗白成「市场装的、没改过」。
                        conflicts.append({"tx": txid, "skill": s,
                                          "expected": want, "actual": got})
                        log("error", "tx",
                            f"拒绝认领 {s}：内容与当时 commit 的不一致"
                            f"（期望 {str(want)[:12]}…，实际 {str(got)[:12]}…）"
                            "—— 这是你的改动，本工具不会把它当成市场版本")
                    else:
                        # 还没确认交付（崩在 replace 前后）→ 这次交付本来就没完成，
                        # 不认领，也不用报警
                        log("warn", "tx",
                            f"跳过未确认交付的 {s}（内容与预期不符，本次事务未完成）")
                    continue
                claim.append(s)
                snapshots[s] = {"hash": got, "fingerprint": entry.get("fingerprint")}
                versions[s] = entry.get("version") or tx.get("version") or ""

            if claim:
                full = all(v.get("fingerprint") for v in snapshots.values())
                by_version = {}
                for s in claim:
                    by_version.setdefault(versions.get(s) or "", []).append(s)
                failed_here = False
                for ver, group in by_version.items():
                    snaps = {s: (snapshots[s] if full else {"hash": snapshots[s]["hash"]})
                             for s in group}
                    try:
                        # 按版本分组写：不能把不同版本号的 skill 混成一条记录
                        record_owner(tx.get("plugin") or "", group, ver, snapshots=snaps)
                    except (OSError, ConfigError) as exc:
                        failed.append((txid, str(exc)))
                        log("error", "tx", f"补记所有权失败（保留日志下次再试）：{txid} — {exc}")
                        failed_here = True
                        break
                    recovered.extend(group)
                    log("warn", "tx",
                        f"补记了上一次未完成的所有权记录：{', '.join(group)}")
                if failed_here:
                    continue

            # --- 清账：已搬进回收站、所有权还留着的 ---
            forgotten = [s for s in (tx.get("pendingForget") or [])
                         if isinstance(s, str) and not (SKILLS_DIR / s).exists()]
            if forgotten:
                try:
                    forget_owner(forgotten)
                    log("warn", "tx", f"补清了上一次未完成的所有权移除：{', '.join(forgotten)}")
                except (OSError, ConfigError) as exc:
                    failed.append((txid, str(exc)))
                    log("error", "tx", f"补清所有权失败（保留日志下次再试）：{txid} — {exc}")
                    continue

            # --- 收尾：了结的条目摘掉，被挡下的（冲突 / 没搬成）留着 ---
            conflict_skills = {c["skill"] for c in conflicts if c["tx"] == txid}
            if discard_conflicts:
                conflict_skills = set()
            tx["pendingOwnership"] = [
                e for e in (tx.get("pendingOwnership") or [])
                if isinstance(e, dict) and e.get("skill") in conflict_skills]
            tx["pendingForget"] = [
                s for s in (tx.get("pendingForget") or [])
                if isinstance(s, str) and (SKILLS_DIR / s).exists()]
            if tx_settled(tx):
                tx_close(tx)
                finished.append(txid)
            else:
                tx_save(tx)             # 保留日志：让人知道有笔账被挡下了

    if recovered or finished or stale or conflicts:
        log("info", "tx",
            f"事务恢复：补记 {len(recovered)} / 清账 {len(finished)}"
            f" / 冲突 {len(conflicts)} / 清暂存 {stale}")
    if not quiet and (recovered or finished or conflicts):
        _core.say(f"  事务恢复：补记所有权 {len(recovered)} 项，清理残留日志 {len(finished)} 份")
        for c in conflicts:
            _core.say(f"  ! 拒绝认领 {c['skill']}：内容已被改动，未记为本市场版本")
    return {"recovered": recovered, "finished": finished, "failed": failed,
            "conflicts": conflicts, "stagingSwept": stale}
