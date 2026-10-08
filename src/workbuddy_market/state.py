# -*- coding: utf-8 -*-
"""workbuddy_market.state —— 市场状态组装层（v2.19 新增，R6 收尾）。

自 market_core.py 逐字迁入（v2.19）：

  · installed_skill_names()  本机 skills 目录里的 skill 名（排除暂存）
  · installed_repos()        GitHub 源安装记录（ghpm 落盘的 registry）
  · build_state(purpose)     网页界面用的完整状态（插件 / 远端 / 分类 /
                             回收站 / 统计 / 校验档位）

市场语义（迁移前就有，务必保持）：

  · build_state 默认 purpose="ui" 走**展示**路径：卸载分级用廉价指纹，
    可能把「已被改过」显示成「可安全卸载」。真正的卸载动作会重新按
    purpose="uninstall" 精确判定一次 —— 界面上的偏差不会变成误删。
  · 只扫**声明的那几个 skill**（SkillScanCache 按名字分桶），不整树扫
    SKILLS_DIR —— selftest 19I 盯防扫描次数。
  · 注入点纪律（R5）：build_state 直调的 plugin_uninstall_plan 属于
    crash 注入矩阵盯防的编排入口，**调用点晚绑定** ``import market_core``
    后经 core 命名空间调用 —— patch core.plugin_uninstall_plan 依旧能拦到。
    其余（load_ownership / trash_stats / is_registered 等）是叶子读，
    直接从所属模块导入（与 R4/R5 先例一致）。

market_core 对以上名字全部 re-export：``import market_core`` 不受影响；
patch core.build_state 仍能拦到 server / launcher 的调用（它们都经 core
命名空间调用）。
"""
from __future__ import annotations

from .paths import (
    SKILLS_DIR, PLUGINS_DIR, MARKET_ROOT, WB, MANIFEST_PATH,
    KNOWN_PATH, GITHUB_REGISTRY, STATE_PATH, GHPM_PY,
)
from .fsutil import read_json
from .config import CLASSIFY_PURPOSES, load_config, verify_mode, needs_exact
from .scanner import SkillScanCache
from .version import MARKET_VERSION
from .ownership import load_ownership
from .trash import trash_stats, trash_config
from .adapters.workbuddy import is_registered


def installed_skill_names() -> set:
    """本机 skills 目录里的 skill 名。**排除暂存目录**（.x.installing-<pid>）。"""
    if not SKILLS_DIR.is_dir():
        return set()
    return {d.name for d in SKILLS_DIR.iterdir()
            if not d.name.startswith(".") and (d / "SKILL.md").is_file()}


def installed_repos() -> dict:
    data = read_json(GITHUB_REGISTRY, {}) or {}
    out = {}
    for proj in (data.get("projects") or []):
        if isinstance(proj, dict) and proj.get("repo"):
            out[proj["repo"]] = {
                "name": proj.get("name", ""),
                "sha_short": (proj.get("sha") or "")[:7],
                "skill_names": proj.get("skill_names") or [],
                "updated_at": proj.get("updated_at") or proj.get("installed_at") or "",
            }
    return out


def build_state(purpose: str = "ui") -> dict:
    """给网页界面用的完整状态。

    ⚠️ 默认走**展示**路径：卸载分级用 purpose="ui"（廉价指纹），
    可能把「已被改过」显示成「可安全卸载」。真正的卸载动作会重新按
    purpose="uninstall" 精确判定一次 —— 界面上的偏差不会变成误删。
    需要一份「所见即所得」的状态时传 purpose="uninstall"（会读全部文件，慢）。
    """
    import market_core as core   # 调用点晚绑定（R5 纪律）：注入点经 core 命名空间
    if purpose not in CLASSIFY_PURPOSES:
        purpose = "ui"
    cfg = load_config()
    skills_here = installed_skill_names()
    repos = installed_repos()
    state = read_json(STATE_PATH, {}) or {}
    own = load_ownership()

    # 只扫**声明的那几个 skill**，一次调用、按名字分桶。
    # 不去扫整棵 SKILLS_DIR —— 那会把几百个无关目录（ghpm / 第三方装的）也走一遍。
    # 注意这里不传 excluder：要和 quick_fingerprint(d) / tree_hash(d) 的口径一致
    # （它们都不做排除），否则指纹对不上、全部退回完整哈希。
    declared = [s for p in cfg.get("localPlugins", []) for s in p.get("skills", [])]
    scan_cache = SkillScanCache(declared) if declared else None

    plugins = []
    for spec in cfg.get("localPlugins", []):
        want = spec.get("skills", [])
        plan = core.plugin_uninstall_plan(spec["name"], cfg, purpose=purpose,
                                          scan_cache=scan_cache)
        items = plan.get("items", [])
        by = {i["skill"]: i for i in items}
        have = [s for s in want if s in skills_here]
        plugins.append({
            "id": spec["name"],
            "kind": "local",
            "name": spec.get("displayName", spec["name"]),
            "rawName": spec["name"],
            "category": spec.get("category", "未分类"),
            "description": spec.get("description", ""),
            "description_en": spec.get("description_en", ""),
            "version": spec.get("version", "1.0.0"),
            "keywords": spec.get("keywords", []),
            "skills": want,
            "installedSkills": have,
            "installedRatio": f"{len(have)}/{len(want)}",
            "installed": len(have) == len(want) and len(want) > 0,
            "partial": 0 < len(have) < len(want),
            "packaged": (PLUGINS_DIR / spec["name"]).is_dir(),
            # 卸载安全分级
            "uninstall": {
                "counts": plan.get("counts", {}),
                "removable": plan.get("removable", []),
                "modified": plan.get("modified", []),
                "untouched": plan.get("untouched", []),
                "absent": plan.get("absent", []),
                "items": items,
                "safeToUninstall": bool(plan.get("removable")),
            },
            "ownership": {s: own["skills"].get(s, {}).get("plugin", "") for s in want
                          if s in own["skills"]},
            "skillDetail": [{"skill": s, "kind": by.get(s, {}).get("kind", "absent"),
                             "label": by.get(s, {}).get("label", "")} for s in want],
        })

    remotes = []
    for spec in cfg.get("remoteSources", []):
        hit = repos.get(spec["repo"])
        remotes.append({
            "id": spec["repo"].replace("/", "__"),
            "kind": "remote",
            "name": spec.get("displayName", spec["repo"]),
            "rawName": spec["repo"],
            "category": spec.get("category", "未分类"),
            "description": spec.get("description", ""),
            "keywords": spec.get("keywords", []),
            "skillCount": spec.get("skillCount", 0),
            "stars": spec.get("stars", 0),
            "verifiedAt": spec.get("verifiedAt", ""),
            "installed": bool(hit),
            "installedSha": (hit or {}).get("sha_short", ""),
            "installedSkills": len((hit or {}).get("skill_names") or []),
        })

    cats = []
    for p in plugins + remotes:
        if p["category"] not in cats:
            cats.append(p["category"])

    ts = trash_stats()
    return {
        "marketVersion": MARKET_VERSION,
        "schemaVersion": cfg.get("schemaVersion", 1),
        "marketId": cfg.get("marketId"),
        "marketName": cfg.get("name"),
        "root": str(MARKET_ROOT),
        "wbHome": str(WB),
        "registered": is_registered(cfg),
        "manifestOk": MANIFEST_PATH.is_file(),
        "knownPath": str(KNOWN_PATH),
        "ghpmOk": GHPM_PY.is_file(),
        "plugins": plugins,
        "remotes": remotes,
        "categories": cats,
        "trash": {
            "count": ts["count"],
            "bytes": ts["bytes"],
            "policy": trash_config(),
        },
        "stats": {
            "localPlugins": len(plugins),
            "remoteSources": len(remotes),
            "localSkills": sum(len(p["skills"]) for p in plugins),
            "installedLocalSkills": sum(len(p["installedSkills"]) for p in plugins),
            "ownedSkills": len(own["skills"]),
            "installedRemotes": sum(1 for r in remotes if r["installed"]),
            "sizeBytes": state.get("sizeBytes", 0),
            "lastSync": state.get("lastSync", ""),
            "marketVersion": MARKET_VERSION,
            "stateVersion": state.get("version", 0),
            "verify": verify_mode(),
            "verifyEffective": {"ui": needs_exact("ui"),
                                "install": needs_exact("install"),
                                "uninstall": needs_exact("uninstall")},
        },
    }
