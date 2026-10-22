# -*- coding: utf-8 -*-
"""第 42 节（v2.36.1）：兼容模式 0 skill 仓库全量可见可卸载。

用户实测（2026-10-22，录安装视频时发现）：探索 GitHub 以兼容模式
（--allow-non-skill）安装非 Skill 仓库（Go 项目 workbuddy2api-panel），
任务报「成功」，但本机技能页三处全隐形 —— 社区分组此前对 skill_names
为空的 ghpm 记录整卡跳过（``if not all_names: continue``），违背
「装过的东西看得见、卸得掉」。

盯防线（防回归）：
1. 0 skill 的 ghpm 记录**必须**出社区卡：sourceOnly=True、via=ghpm、
   sourceDir 如实、shaShort 截 7 位、installedRatio=0/0；
2. 卡片描述必须自解释「未含 Skill，仅保留完整源码副本；移除走 ghpm」；
3. 卸载分级 fail-closed 不变：ghpm 组没有所有权记录，safeToUninstall
   恒为 False（移除走 ghpm 自己的命令，市场绝不代删）；
4. 带 skill 的 ghpm 记录行为不变（无 sourceOnly 字段污染）。
"""
from __future__ import annotations

import json

from . import _TMP, ck, core, section


def round27():
    section("42. v2.36.1：兼容模式 0 skill 仓库全量可见可卸载")

    reg = core.GITHUB_REGISTRY
    existed = reg.exists()
    backup = reg.read_text(encoding="utf-8") if existed else None
    try:
        reg.parent.mkdir(parents=True, exist_ok=True)
        reg.write_text(json.dumps({
            "projects": [
                {"repo": "owner/with-skills", "name": "with-skills",
                 "sha": "a" * 40, "skill_names": ["alpha"],
                 "source_dir": str(_TMP / "with-skills-source"),
                 "updated_at": "2026-10-21T07:31:25+00:00"},
                {"repo": "owner/src-only", "name": "src-only",
                 "sha": "b" * 40, "skill_names": [],
                 "source_dir": str(core.WB / "src-only-source"),
                 "updated_at": "2026-10-21T15:59:36+00:00"},
            ]}, ensure_ascii=False), encoding="utf-8")

        st = core.build_state()
        cards = {c["id"]: c for c in st["community"]}

        # --- 42A. 0 skill 记录出卡（核心回归钉子）
        c = cards.get("owner/src-only")
        ck("★ 0 skill ghpm 记录出社区卡（不再整卡跳过）", c is not None)
        if c:
            ck("sourceOnly=True / via=ghpm / skills 空",
               c.get("sourceOnly") is True and c.get("via") == "ghpm"
               and c["skills"] == [])
            ck("sourceDir 如实（用户能对上源码副本落点）",
               c.get("sourceDir") == str(core.WB / "src-only-source"))
            ck("shaShort 截 7 位 / installedRatio=0/0",
               c.get("shaShort") == "b" * 7
               and c.get("installedRatio") == "0/0")
            ck("描述自解释：未含 Skill + 移除走 ghpm",
               "未含 Skill" in (c.get("description") or "")
               and "ghpm" in (c.get("description") or ""))

        # --- 42B. 卸载分级 fail-closed 不变（ghpm 组市场绝不代删）
        if c:
            u = c["uninstall"]
            ck("卸载分级 fail-closed：safeToUninstall=False / items 空",
               u["safeToUninstall"] is False and u["items"] == []
               and u["counts"] == {"ghpm": 0, "absent": 0})

        # --- 42C. 带 skill 的记录行为不变（无 sourceOnly 污染）
        w = cards.get("owner/with-skills")
        ck("★ 带 skill 的 ghpm 记录照常出卡、无 sourceOnly 字段",
           w is not None and w.get("skills") == ["alpha"]
           and not w.get("sourceOnly"))
    finally:
        if existed:
            reg.write_text(backup, encoding="utf-8")
        else:
            reg.unlink(missing_ok=True)
