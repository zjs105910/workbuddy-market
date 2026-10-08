# -*- coding: utf-8 -*-
"""installer —— 两阶段安装（v2.14 R5 自 market_core.py 逐字迁入）。

职责：PREPARE → COPY → VERIFY → COMMIT → RECORD 的完整安装生命周期，
含暂存目录管理（_stage_dir / _sweep_staging / _stage_skill）、
原子换位（_commit_staged）与插件级编排（install_local_plugin）。
纪律与原状完全一致：

  · 任何一步失败，本机原来的那份**原样还在**（先备好新的、再动旧的）；
  · 凭证先于磁盘变更：tx_begin 早于一切，expected hash 在 os.replace
    之前写进日志（约定 12）；
  · 链接防线三道闭环：源拒绝 → symlinks=True 复制 → 暂存副本再拒。

注入点接缝（v2.14 R5，与 R4 同一纪律 —— 对 core 注入点**调用点晚绑定
``import market_core``**，patch ``core.X`` 对安装链路的拦截语义与迁移前
完全一致；selftest 崩溃矩阵第 805 行起、第 1652 行 tx_begin 注入都依赖它）：

  · ``_scan``（第 19 节 / 第 22 节崩溃注入：core._scan）；
  · ``quick_fingerprint`` / ``tree_hash`` / ``tree_hash_from_index``
    （第 24B 节盯防的 core 注入点；tree_hash* 留 core 是既定纪律）；
  · ``tx_begin / tx_note_staged / tx_note_committed / tx_drop /
    tx_settled / tx_release / tx_close / recover_transactions``
    （第 20 节 core.tx_begin 注入：连日志都开不了就不许动磁盘）；
  · ``_sync_packaging``（core 侧组合函数，R6 前不迁）。

包内互调（TrashIndex / move_to_trash / ownership / config / locking /
logging / paths）直接走包命名空间，patch 这些名字请 patch
``workbuddy_market.<模块>``。
"""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from .config import ConfigError, ensure_child, load_config
from .hasher import fingerprint_from_index
from .locking import locked
from .logging import log
from .ownership import load_ownership
from .paths import PLUGINS_DIR, SKILLS_DIR
from .trash import TrashIndex, move_to_trash

INSTALL_MODES = ("missing", "update", "force")


def _stage_dir(sname: str) -> Path:
    return SKILLS_DIR / f".{sname}.installing-{os.getpid()}"


def _sweep_staging() -> int:
    """清掉上次崩在中途留下的暂存目录。"""
    n = 0
    try:
        for d in SKILLS_DIR.glob(".*.installing-*"):
            if d.is_dir():
                shutil.rmtree(d, ignore_errors=True)
                n += 1
    except OSError:
        pass
    return n


def _stage_skill(src: Path, sname: str) -> Path:
    """PREPARE + COPY + VERIFY：把 skill 完整复制到暂存目录并校验。

    失败时清掉暂存并原样抛出 —— 此时**正式目录一点没动**。

    链接防线（defense-in-depth）：打包阶段已经不跟随 symlink / junction，
    但「正常流程不会产生」不等于「不可能发生」—— 手工往市场目录塞一个
    重解析点就够了。而 `copytree(..., symlinks=False)` 会**跟随**链接，
    把技能目录之外的内容复制进 ~/.workbuddy。所以这里三道：

      1. 源目录里有任何重解析点 → 直接拒绝安装
      2. copytree 用 symlinks=True（复制链接本身，绝不跟随）
      3. 暂存副本里若出现重解析点 → 同样拒绝

    和打包阶段连起来就是完整闭环：源 → 打包禁止 → 市场产物禁止 → 安装再禁一次。

    返回 dict：`{"tmp", "index", "links", "bytes"}`。把暂存副本的索引一并交出去，
    是因为落位后的内容与暂存**完全一致**（rename 不改内容也不改 mtime），
    后续算所有权指纹 / 内容哈希可以直接用它，不必再扫一遍新版本。

    `_scan` 走 core 晚绑定：它是 selftest 的崩溃/计数注入点（core._scan），
    搬进包之后也必须保持「patch core._scan 能拦到安装的这次扫描」。
    """
    import market_core as _core          # noqa: PLC0415 —— 注入点晚绑定，见模块 docstring
    tmp = _stage_dir(sname)
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    try:
        si, s_links = _core._scan(src, on_error="raise")   # 看不见源内容就别谈"校验通过"
        if s_links:
            raise OSError(
                f"源目录含 {len(s_links)} 个符号链接 / junction，拒绝安装：{s_links[:3]}"
            )
        shutil.copytree(src, tmp, symlinks=True)
        if not (tmp / "SKILL.md").is_file():
            raise OSError("暂存目录里没有 SKILL.md")
        ti, t_links = _core._scan(tmp, on_error="raise")
        if t_links:
            raise OSError(
                f"暂存副本里出现 {len(t_links)} 个符号链接 / junction，拒绝安装：{t_links[:3]}"
            )
        if set(si) != set(ti):
            miss = sorted(set(si) - set(ti))[:3]
            raise OSError(f"暂存内容不完整，缺少 {miss}")
        for rel, (sz, _mt) in si.items():
            if ti[rel][0] != sz:
                raise OSError(f"暂存文件大小与源不符：{rel}")
        return {"tmp": tmp, "index": ti, "links": t_links,
                "bytes": sum(v[0] for v in ti.values())}
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def _commit_staged(tmp: Path, dst: Path, sname: str,
                   index: "TrashIndex | None" = None) -> None:
    """COMMIT：把暂存目录原子换到正式位置；换失败就把旧版本放回去。

    顺序很重要 —— **先复制好、校验过，再动旧版本**。
    v2 是反过来的（先把旧的搬走再复制新的），所以复制一旦失败，
    旧版本躺在回收站、新版本没写上，本机 skill 直接消失。
    """
    trashed = None
    if dst.exists():
        trashed = move_to_trash(dst, "reinstall", index=index)
        if trashed is None:
            raise OSError("旧目录无法移入回收站，未改动")
    try:
        os.replace(str(tmp), str(dst))
    except OSError:
        if trashed is not None:
            try:
                shutil.move(str(trashed), str(dst))
                log("warn", "install", f"{sname} 落位失败，已把旧版本放回原位")
            except OSError as exc:
                log("error", "install",
                    f"{sname} 落位失败且回滚也失败：{exc}；旧版本仍在 {trashed}")
        raise


def install_local_plugin(plugin_id: str, mode: str = "missing") -> dict:
    """把插件的 skill 装到 ~/.workbuddy/skills/。

    mode:
      missing（默认）只补缺，已有的一律不碰
      update      补缺 + 覆盖「本市场装的且内容已变」的
      force       补缺 + 覆盖全部同名目录

    每个 skill 都走「暂存 → 校验 → 换位」两阶段：任何一步失败，
    本机原来的那份**原样还在**。三种模式都绝不静默覆盖非本市场安装的 skill。

    core 注入点（classify_skill / _stage_skill / _commit_staged /
    tree_hash* / tx_* / _sync_packaging）一律经 ``market_core`` 晚绑定：
    安装编排是这些注入点最重要的消费方，patch core.X 的语义不能变。
    classify_skill 与 _stage_skill / _commit_staged 虽已同包（R5），
    但它们的内部依赖（quick_fingerprint / tree_hash / _scan）是 core
    注入点，经由 core 命名空间调用才能让一次 patch 拦到全链路。
    """
    import market_core as _core          # noqa: PLC0415 —— 注入点晚绑定，见模块 docstring
    if mode not in INSTALL_MODES:
        return {"ok": False, "error": f"未知安装模式 {mode}（可选：{', '.join(INSTALL_MODES)}）"}

    with locked():
        op = f"install-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
        try:
            cfg = load_config()
        except ConfigError as exc:
            return {"ok": False, "error": f"配置不可用：{exc}"}
        spec = next((p for p in cfg.get("localPlugins", []) if p["name"] == plugin_id), None)
        if not spec:
            return {"ok": False, "error": f"市场里没有插件 {plugin_id}"}

        # 先把上一次未完成的事务补上（比如上次正好卡在
        # 「文件已落位、所有权还没写」那一步）
        rec = _core.recover_transactions(quiet=True)
        recovered = rec["recovered"]

        src_root = PLUGINS_DIR / plugin_id / "skills"
        if not src_root.is_dir():
            _core._sync_packaging(quiet=True)
        if not src_root.is_dir():
            return {"ok": False, "error": f"插件 {plugin_id} 尚未打包，请先运行同步"}

        SKILLS_DIR.mkdir(parents=True, exist_ok=True)

        version = spec.get("version", "1.0.0")
        own = load_ownership()
        added, updated, skipped, foreign, failed, warnings = [], [], [], [], [], []
        expected_by_skill = {}          # 换位前算好的「期望状态」，收尾直接复用
        trash_index = TrashIndex()      # 整批只落一次回收站索引

        # 事务日志**必须早于任何磁盘变更**。哪怕后面一个 skill 都不用装，
        # 也只是一份空日志，收尾时会被删掉 —— 代价是一次原子写，
        # 换来的是「从这里起无论死在哪一行都有凭证」。
        tx = _core.tx_begin("install", plugin_id, spec.get("skills", []),
                            version=version, mode=mode)

        try:
            for sname in spec.get("skills", []):
                src = src_root / sname
                if not (src / "SKILL.md").is_file():
                    continue
                dst = SKILLS_DIR / sname
                try:
                    ensure_child(SKILLS_DIR, dst)
                except ConfigError as exc:
                    failed.append(f"{sname}: {exc}")
                    continue

                # 安装决策必须精确：指纹只服务网页显示，绝不用来决定要不要覆盖
                kind = _core.classify_skill(plugin_id, sname, cfg, own,
                                            purpose="install")["kind"]

                if kind == "foreign" or kind == "other_plugin":
                    foreign.append(sname)
                    continue
                if kind == "absent":
                    action = "add"
                elif mode == "missing" or (mode == "update" and kind == "safe"):
                    skipped.append(sname)
                    continue
                else:
                    action = "update"

                # 两阶段：先备好新的，再动旧的
                try:
                    st = _core._stage_skill(src, sname)
                except (OSError, shutil.Error) as exc:
                    failed.append(f"{sname}: 暂存失败（本机版本未改动）：{exc}")
                    continue

                # 先算出「换位之后应该长什么样」，**在动正式目录之前落盘**。
                # 中间那一步 os.replace 成功但进程随即死掉，靠的就是这份 expected。
                expected = {
                    "hash": _core.tree_hash_from_index(st["tmp"], st["index"]),
                    "fingerprint": fingerprint_from_index(st["index"], st["links"]),
                }
                _core.tx_note_staged(tx, sname, expected,
                                     plugin=plugin_id, version=version)

                try:
                    _core._commit_staged(st["tmp"], dst, sname, index=trash_index)
                except OSError as exc:
                    shutil.rmtree(st["tmp"], ignore_errors=True)
                    failed.append(f"{sname}: 落位失败：{exc}")
                    continue

                _core.tx_note_committed(tx, sname)     # 交付确认
                expected_by_skill[sname] = expected

                (added if action == "add" else updated).append(sname)
                log("info", "install", f"{sname} {'新增' if action == 'add' else '更新'}完成",
                    op_id=op)

            done = added + updated
            if done:
                try:
                    # 这些 hash / 指纹就是上面刚算过的，不用再读一遍新版本
                    _core.record_owner(plugin_id, done, version,
                                       snapshots={s: expected_by_skill[s]
                                                  for s in done if s in expected_by_skill})
                    for s in done:
                        _core.tx_drop(tx, s)
                except (OSError, ConfigError) as exc:
                    # 文件已经装好了，只是账没记上。如实报告，但**不能**谎称成功
                    # 之后什么都没发生 —— 日志会保留，下次启动自动补记。
                    warnings.append(
                        f"所有权记录写入失败：{exc}（已记入事务日志，"
                        "下次启动/下次安装会自动补记）")
                    log("error", "install", warnings[-1], op_id=op)

            msg = (f"{plugin_id}[{mode}]: 新增 {len(added)} 更新 {len(updated)} "
                   f"跳过 {len(skipped)} 非本市场 {len(foreign)} 失败 {len(failed)}")
            log("warn" if (failed or warnings) else "info", "install", msg, op_id=op)
            return {"ok": True, "mode": mode, "op": op, "added": added, "updated": updated,
                    "skipped": skipped, "foreign": foreign, "failed": failed,
                    "warnings": warnings, "recovered": recovered,
                    "tx": tx["id"]}
        finally:
            # 账清干净了就删日志；还有没结的，就把日志交还给恢复流程 ——
            # 必须显式释放，否则这个 id 会一直挂在 _TX_ACTIVE 里，同进程的
            # recover_transactions() 反而看不见它。
            if _core.tx_settled(tx):
                _core.tx_close(tx)
            else:
                _core.tx_release(tx)
            trash_index.flush()         # 整批搬移只写一次索引
