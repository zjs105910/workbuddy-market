# -*- coding: utf-8 -*-
"""workbuddy_market.state —— 市场状态组装层（v2.19 新增，R6 收尾）。

自 market_core.py 逐字迁入（v2.19）：

  · installed_skill_names()  本机 skills 目录里的 skill 名（排除暂存）
  · installed_repos()        GitHub 源安装记录（ghpm 落盘的 registry）
  · build_state(purpose)     网页界面用的完整状态（插件 / 远端 / 社区安装分组 /
                             本机技能一览 / 分类 / 回收站 / 统计 / 校验档位）

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
        via = ""
        if not hit:
            # 2026-10-14 P1 修复（审计 D1）：ghpm 的 registry 看不到 artifact
            # 链安装（记录只在所有权里，pid=仓库名）——收录源卡片的「已安装」
            # 状态同样要如实，否则装完在探索页仍显示「一键安装」。
            owned = [s for s, rec in own["skills"].items()
                     if rec.get("plugin") == spec["repo"]]
            if owned:
                hit = {"name": spec["repo"], "sha_short": "",
                       "skill_names": owned, "updated_at": ""}
                via = "artifact"
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
            "via": via,
        })

    cats = []
    for p in plugins + remotes:
        if p["category"] not in cats:
            cats.append(p["category"])

    # ---- 社区安装分组（2026-10-14 用户实测 P1 修复，审计缺口 D1；
    #      2026-10-14 用户实测二修：ghpm 源码链同样要看得见）----
    # 两条安装链路装进来的技能都不在 localPlugins 里，但记录在案：
    #   · artifact 链（精选市场「安装固定产物」）→ 所有权记录（pid=仓库名），
    #     本市场是管理者，卸载通路经所有权回退覆盖（见 uninstaller）；
    #   · ghpm 源码链（探索 GitHub「一键安装」）→ ghpm 自己的 registry
    #     （~/.workbuddy/github-projects.json）。本市场**不记所有权** ——
    #     ghpm 才是那些技能的管理者，市场代记所有权等于替别人认领文件，
    #     之后市场卸载就会删掉 ghpm 还在管的技能。并组只为「看得见」。
    # 按来源仓库分组展示：「装过的东西看得见、卸得掉」。
    # 只收本市场装的（owner 对得上）；别的市场装的不占本市场版面。
    # 卸载分级经 plugin_uninstall_plan 的所有权回退（见 uninstaller），
    # classify_skill 逐项校验 owner/哈希，fail-closed 语义不变。
    mid = cfg.get("marketId", "wb-local-market")
    local_names = {p["name"] for p in cfg.get("localPlugins", [])}
    local_declared = {s for p in cfg.get("localPlugins", []) for s in p.get("skills", [])}
    owned_names = set(own["skills"])          # 任何所有权记录 = 已有归属，不重复占版面
    groups: dict = {}
    for sname, rec in own["skills"].items():
        plug = str(rec.get("plugin") or "")
        if not plug or plug in local_names or sname in local_declared:
            continue
        if rec.get("owner") and rec.get("owner") != mid:
            continue
        g = groups.setdefault(plug, {"skills": [], "packageHash": "",
                                     "version": "", "installedAt": "",
                                     "via": "artifact"})
        g["skills"].append(sname)
        if rec.get("packageHash"):
            g["packageHash"] = rec["packageHash"]
        if rec.get("version"):
            g["version"] = rec["version"]
        if rec.get("installedAt"):
            g["installedAt"] = rec["installedAt"]

    # ghpm 源码安装的仓库（用户实测二修：装完只在「探索 GitHub」页显示已装，
    # 本机技能页的社区安装分区看不到——「安装完成之后都显示在本机社区安装
    # 页面」）。并组规则：
    #   · 同一仓库已走 artifact 链（groups 里已有）→ 跳过，不重复展示；
    #   · 技能与 localPlugins 声明 / 一切所有权记录逐名去重 —— 社区分区是
    #     「一个技能只出现一次」的干净分区，归谁的组就由谁管理；
    #   · ghpm 组不调 plugin_uninstall_plan（没有所有权记录，计划必然是空的），
    #     skillDetail 直接合成 kind=ghpm（在盘，ghpm 管理）/ absent；
    #   · 清单里已全部不在盘的组也展示（ghpm 记录比磁盘旧），如实显示未装，
    #     用户可经「移除」让 ghpm 清掉自己的清单。
    for repo, rec in repos.items():
        if not repo or repo in groups:
            continue
        names = [s for s in (rec.get("skill_names") or [])
                 if s not in local_declared and s not in owned_names]
        if not names:
            continue
        groups[repo] = {"skills": names, "packageHash": "", "version": "",
                        "installedAt": rec.get("updated_at", "") or "",
                        "via": "ghpm",
                        "shaShort": str(rec.get("sha_short") or "")[:7]}

    community = []
    for plug, g in sorted(groups.items()):
        want = sorted(g["skills"])
        have = [s for s in want if s in skills_here]
        base = {
            "id": plug,
            "kind": "community",
            "name": plug,
            "rawName": plug,
            "category": "社区安装",
            "via": g.get("via", "artifact"),
            "description": "通过精选市场安装：不可变工件 + SHA-256 校验 + 事务安装，可经市场卸载",
            "version": g["version"] or "",
            "packageHash": g["packageHash"],
            "installedAt": g["installedAt"],
            "skills": want,
            "installedSkills": have,
            "installedRatio": f"{len(have)}/{len(want)}",
            "installed": len(have) == len(want) and len(want) > 0,
            "partial": 0 < len(have) < len(want),
        }
        if g.get("via") == "ghpm":
            # ghpm 源码链：市场不拥有这些技能 → 市场卸载通路**不**覆盖
            # （fail-closed：没有所有权记录的技能一律不代删，卸载对话框
            # 也不会为它出现）。检查更新 / 移除走 ghpm 自己的命令
            # （remove 自带备份与事务回滚），由前端 /api/remote/remove 触发。
            base.update({
                "description": "通过 ghpm 源码安装：联网下载 + ghpm 事务与回滚，"
                               "由 ghpm 管理（可检查更新 / 移除）",
                "shaShort": g.get("shaShort", ""),
                "uninstall": {
                    "counts": {"ghpm": len(have),
                               "absent": len(want) - len(have)},
                    "removable": [], "modified": [],
                    "untouched": list(want),
                    "absent": [s for s in want if s not in skills_here],
                    "items": [], "safeToUninstall": False,
                },
                "skillDetail": [
                    {"skill": s,
                     "kind": "ghpm" if s in skills_here else "absent",
                     "label": ("ghpm 安装，市场不卸载（移除走 ghpm）"
                               if s in skills_here else "未安装")}
                    for s in want],
            })
        else:
            # 社区技能的扫描不走本地声明缓存（名字不在桶里），传 None 让
            # classify_skill 直接走 quick_fingerprint/tree_hash，语义不变。
            plan = core.plugin_uninstall_plan(plug, cfg, purpose="ui")
            items = plan.get("items", [])
            by = {i["skill"]: i for i in items}
            base.update({
                "uninstall": {
                    "counts": plan.get("counts", {}),
                    "removable": plan.get("removable", []),
                    "modified": plan.get("modified", []),
                    "untouched": plan.get("untouched", []),
                    "absent": plan.get("absent", []),
                    "items": items,
                    "safeToUninstall": bool(plan.get("removable")),
                },
                "skillDetail": [{"skill": s, "kind": by.get(s, {}).get("kind", "absent"),
                                 "label": by.get(s, {}).get("label", "")} for s in want],
            })
        community.append(base)
    for p in community:
        if p["category"] not in cats:
            cats.append(p["category"])

    # ---- 本机技能只读清单（2026-10-14 用户实测反馈：「本机技能应该显示
    # 本机 WorkBuddy 的所有技能」）—— SKILLS_DIR 全量快照 + 来源标注，
    # 纯展示不进任何管理动作（打包/注册仍只认 localPlugins，安全设计不变）。
    owned_community = {s for g in groups.values() for s in g["skills"]}
    all_skills = [{"name": s,
                   "source": ("market" if s in local_declared
                              else "community" if s in owned_community else "other")}
                  for s in sorted(skills_here)]

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
        "community": community,
        "allSkills": all_skills,
        "categories": cats,
        "trash": {
            "count": ts["count"],
            "bytes": ts["bytes"],
            "policy": trash_config(),
        },
        "stats": {
            "localPlugins": len(plugins),
            "remoteSources": len(remotes),
            "communityPlugins": len(community),
            "localSkills": sum(len(p["skills"]) for p in plugins),
            "installedLocalSkills": sum(len(p["installedSkills"]) for p in plugins),
            "ownedSkills": len(own["skills"]),
            "allSkills": len(all_skills),
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
