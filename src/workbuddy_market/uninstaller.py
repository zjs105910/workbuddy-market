# -*- coding: utf-8 -*-
"""uninstaller —— 卸载分级与执行（v2.14 R5 自 market_core.py 逐字迁入）。

职责：classify_skill 三档判定（absent / safe / modified / foreign /
other_plugin）、插件级卸载计划（plugin_uninstall_plan）与执行
（uninstall_local_plugin）。纪律与原状完全一致：

  · **只动本市场装的**，用户自己的和别的插件的绝不碰；
  · 分级准不准由 purpose 决定：ui 可用指纹（快，误差只是显示），
    install / uninstall 必须 READ 内容算 SHA-256（约定 2）；
  · 扫不全就 fail-closed 当「被改过」（约定 20 的删除侧镜像）；
  · 和安装共用同一套事务模型：搬走之前就有日志，搬走之后立刻登记
    pendingForget，forget_owner 成功才清账。

注入点接缝（v2.14 R5，与 R4 同一纪律 —— 对 core 注入点**调用点晚绑定
``import market_core``**，patch ``core.X`` 对卸载链路的拦截语义与迁移前
完全一致）：

  · ``quick_fingerprint`` / ``tree_hash``（第 22 节崩溃矩阵经
    core.quick_fingerprint / core.tree_hash 注入分类判定）；
  · ``tx_begin / tx_note_removed / tx_settled / tx_release / tx_close /
    recover_transactions``（事务凭证先于磁盘变更，约定 12）。

包内互调（ownership / config / trash / paths / locking / logging /
scanner 的 SkillScanCache）直接走包命名空间；
classify_skill ↔ plugin_uninstall_plan ↔ uninstall_local_plugin 的
包内互调走本模块命名空间，patch 请 patch ``workbuddy_market.uninstaller``。
"""
from __future__ import annotations

from pathlib import Path

from .config import (CLASSIFY_PURPOSES, ConfigError, ensure_child, load_config,
                     needs_exact)
from .errors import ScanError
from .locking import locked
from .logging import log
from .ownership import forget_owner, load_ownership
from .paths import SKILLS_DIR, TRASH_DIR
from .scanner import SkillScanCache
from .trash import TrashIndex, move_to_trash


def classify_skill(plugin_id: str, sname: str, cfg: dict, own: dict | None = None,
                   purpose: str = "ui", always_hash: bool | None = None,
                   scan_cache: "SkillScanCache | None" = None) -> dict:
    """判断一个 skill 当前该归哪一档。网页界面与卸载都靠它。

    返回 kind: absent / safe / modified / foreign / other_plugin

    **准不准由 purpose 决定**，而不是由调用方随手传一个开关：

      ui         网页状态。允许用廉价指纹，快；判错只是显示不准。
      install    决定要不要覆盖本机文件 → 必须 READ 内容。
      uninstall  决定要不要把用户目录搬进回收站 → 必须 READ 内容。

    真正的开关是 needs_exact(purpose)：strict 模式一律精确；auto/fast 下
    install / uninstall 精确、ui 走指纹。

    v2 的 bug 是让 update 也走指纹：只要「文件数 / 总字节 / 最大 mtime_ns」
    三者不变就判 safe —— 用户改了某个旧文件（内容变、大小不变、mtime 仍小于
    最大值）时会被误判成「没动过」，于是 update 静默跳过覆盖。已用探针复现。

    quick_fingerprint / tree_hash 走 core 晚绑定：它们是 selftest 崩溃
    矩阵的注入点（core.quick_fingerprint / core.tree_hash），搬进包之后
    也必须保持「patch core.X 能拦到分类判定」。
    """
    import market_core as _core          # noqa: PLC0415 —— 注入点晚绑定，见模块 docstring
    if purpose not in CLASSIFY_PURPOSES:
        raise ValueError(f"未知用途 {purpose!r}（可选：{', '.join(CLASSIFY_PURPOSES)}）")
    exact = needs_exact(purpose)
    if always_hash:                       # 兼容旧签名：只允许「更严」，不允许更松
        exact = True

    mid = cfg.get("marketId", "wb-local-market")
    d = SKILLS_DIR / sname
    try:
        ensure_child(SKILLS_DIR, d)
    except ConfigError:
        return {"skill": sname, "kind": "foreign", "label": "路径越界，拒绝处理"}

    if not (d / "SKILL.md").is_file():
        return {"skill": sname, "kind": "absent", "label": "未安装"}

    own = own if own is not None else load_ownership()
    rec = own["skills"].get(sname)
    if not rec:
        return {"skill": sname, "kind": "foreign", "label": "非本市场安装（不会动）"}
    if rec.get("plugin") != plugin_id:
        return {"skill": sname, "kind": "other_plugin",
                "label": f"由插件 {rec.get('plugin')} 安装"}
    if rec.get("owner") != mid:
        return {"skill": sname, "kind": "foreign", "label": "非本市场安装（不会动）"}

    # 快路径只服务「可以容忍误差」的用途
    if not exact:
        rec_fp = rec.get("fingerprint")
        if isinstance(rec_fp, dict):
            cur = (scan_cache.fingerprint(sname) if scan_cache is not None
                   else _core.quick_fingerprint(d))
            if cur == rec_fp:
                return {"skill": sname, "kind": "safe", "label": "可安全卸载",
                        "checked": "fingerprint", "purpose": purpose}

    try:
        same = _core.tree_hash(d) == rec.get("hash")
    except ScanError as exc:
        # 扫不全就没法证明「没被动过」。fail-closed：当作被改过 ——
        # 卸载会保留它，更新会覆盖它（市场那份是完整的，覆盖是安全方向）。
        return {"skill": sname, "kind": "modified",
                "label": f"内容读取失败，保守当成被改过：{exc}",
                "checked": "error", "purpose": purpose}
    if not same:
        return {"skill": sname, "kind": "modified", "label": "安装后被修改过",
                "checked": "hash", "purpose": purpose}
    return {"skill": sname, "kind": "safe", "label": "可安全卸载",
            "checked": "hash", "purpose": purpose}


# 兼容别名：语义就是「按用途判断」，旧名字保留给外部脚本
inspect_skill = classify_skill


def plugin_uninstall_plan(plugin_id: str, cfg: dict | None = None,
                          purpose: str = "ui", always_hash: bool | None = None,
                          scan_cache: "SkillScanCache | None" = None) -> dict:
    """插件的卸载分级计划。

    · 网页展示（purpose="ui"）用指纹，快
    · 真正执行卸载（purpose="uninstall"）必须精确 —— 否则可能把
      「其实已经被用户改过」的目录当 safe 搬进回收站
    """
    cfg = cfg or load_config()
    spec = next((p for p in cfg.get("localPlugins", []) if p["name"] == plugin_id), None)
    if not spec:
        return {"ok": False, "error": f"市场里没有插件 {plugin_id}"}
    own = load_ownership()          # 只读一次，别在循环里反复读文件
    items = [classify_skill(plugin_id, s, cfg, own, purpose=purpose,
                            always_hash=always_hash, scan_cache=scan_cache)
             for s in spec.get("skills", [])]
    counts = {}
    for it in items:
        counts[it["kind"]] = counts.get(it["kind"], 0) + 1
    return {
        "ok": True,
        "plugin": plugin_id,
        "purpose": purpose,
        "items": items,
        "counts": counts,
        "removable": [i["skill"] for i in items if i["kind"] == "safe"],
        "modified": [i["skill"] for i in items if i["kind"] == "modified"],
        "untouched": [i["skill"] for i in items if i["kind"] in ("foreign", "other_plugin")],
        "absent": [i["skill"] for i in items if i["kind"] == "absent"],
    }


def uninstall_local_plugin(plugin_id: str, force: bool = False) -> dict:
    """卸载。**只动本市场装的**，用户自己的和别的插件的绝不碰。

    分级：
      safe      本市场装的且没被改过  → 移入回收站
      modified  装过但被改过          → 默认保留，force=True 才移走
      foreign   不是本市场装的        → 永不移动

    和安装共用同一套事务模型：搬走之前就有日志，搬走之后立刻登记
    pendingForget，`forget_owner()` 成功才清账。崩在中间的话，下次恢复
    会看到「目录已不在 + 所有权还在」并把账补平 —— 而不是留下
    「文件没了、ownership 还认着它」这种半截状态。

    tx_* / recover_transactions 走 core 晚绑定（同 installer，见模块
    docstring）；分级计划走本模块命名空间（patch 落点随迁）。
    """
    import market_core as _core          # noqa: PLC0415 —— 注入点晚绑定，见模块 docstring
    with locked():
        try:
            cfg = load_config()
        except ConfigError as exc:
            return {"ok": False, "error": f"配置不可用：{exc}"}
        # 卸载前先把上一次没记完的账补上，否则分级会不准
        recovered = _core.recover_transactions(quiet=True)["recovered"]
        # 卸载是要真的把用户目录搬走，必须用精确判定，不看指纹
        plan = plugin_uninstall_plan(plugin_id, cfg, purpose="uninstall")
        if not plan.get("ok"):
            return plan

        moved, kept, warnings = [], [], []
        trash_index = TrashIndex()
        tx = _core.tx_begin("uninstall", plugin_id,
                            plan.get("removable", []) + plan.get("modified", []),
                            force=force)
        try:
            for item in plan["items"]:
                sname, kind = item["skill"], item["kind"]
                if kind in ("foreign", "other_plugin"):
                    kept.append({"skill": sname, "why": item["label"]})
                    continue
                if kind == "absent":
                    continue
                if kind == "modified" and not force:
                    kept.append({"skill": sname, "why": "安装后被修改过，未移除"})
                    continue
                d = SKILLS_DIR / sname
                try:
                    ensure_child(SKILLS_DIR, d)      # 删除前最后一道闸
                except ConfigError as exc:
                    kept.append({"skill": sname, "why": f"路径越界，拒绝处理：{exc}"})
                    continue
                reason = "uninstall" if kind == "safe" else "uninstall-modified"
                if not move_to_trash(d, reason, index=trash_index):
                    continue
                # 搬走成功就立刻登记 —— 此刻所有权还留着，日志就是「还没清」的凭证
                _core.tx_note_removed(tx, sname)
                moved.append(sname)

            if moved:
                try:
                    # 一次把所有权全清掉（forget_owner 内部只写一次文件）
                    forget_owner(moved)
                    tx["pendingForget"] = []
                except (OSError, ConfigError) as exc:
                    warnings.append(
                        f"所有权记录未能清除：{exc}（已记入事务日志，下次启动会自动补清）")
                    log("error", "uninstall", warnings[-1])

            log("warn" if dropped(plan, force) else "info", "uninstall",
                f"{plugin_id}: 移除 {len(moved)}，保留 {len(kept)}"
                + (f"（{'、'.join(moved)}）" if moved else ""))
            return {"ok": True, "moved": moved, "kept": kept,
                    "trash": str(TRASH_DIR), "force": force, "recovered": recovered,
                    "warnings": warnings,
                    "plan": {k: plan[k] for k in ("counts", "removable", "modified", "untouched")}}
        finally:
            if _core.tx_settled(tx):
                _core.tx_close(tx)
            else:
                _core.tx_release(tx)
            trash_index.flush()         # 整批搬移只写一次索引


def dropped(plan: dict, force: bool) -> bool:
    """这次卸载是否真的动了东西（决定日志级别）。"""
    return bool(plan.get("removable")) or (force and bool(plan.get("modified")))
