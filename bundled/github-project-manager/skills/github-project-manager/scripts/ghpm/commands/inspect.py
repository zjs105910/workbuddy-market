# -*- coding: utf-8 -*-
"""inspect：安装前预检（只读）。"""
from __future__ import annotations

from .. import config
from ..errors import E_ALREADY, E_CONFLICT, E_INVALID_SPEC, E_NOT_FOUND, E_NOT_SKILL
from ..registry import find_skill_conflicts, load
from ..remote import classify_net_error, parse_repo, repo_info, repo_skill_index
from ..util import emit


def cmd_inspect(args):
    """安装前预检（仿 DSH 的 inspect(spec)）：先弄清楚这个地址到底指向什么，再决定装不装。"""
    emit("starting", "解析仓库地址", percent=8)
    try:
        repo = parse_repo(args.repo)
    except ValueError as e:
        emit("failed", "地址无法解析", percent=100, code=E_INVALID_SPEC,
             detail=str(e), hint="应为 owner/repo 或 https://github.com/owner/repo")
        return

    name = repo.split("/")[1]
    data = load()
    dup = [p for p in data["projects"] if str(p.get("repo", "")).lower() == repo.lower()]
    if dup and not args.force:
        emit("failed", "已经安装过了", percent=100, code=E_ALREADY,
             detail="%s（本地 %s）" % (repo, dup[0].get("sha_short", "-")),
             hint="要覆盖重装请用 update，或加 --force")
        return

    emit("checking", "连接仓库 · %s" % repo, percent=32)
    ttl = 0 if getattr(args, "fresh", False) else config.CACHE_TTL
    try:
        info = repo_info(repo, ttl=ttl)
    except Exception as e:
        code, hint = classify_net_error(e)
        emit("failed", "仓库不可达或不存在" if code == E_NOT_FOUND else "连不上仓库",
             percent=100, code=code, detail=str(e)[:160], hint=hint)
        return

    emit("checking", "检查包结构", percent=64)
    index = repo_skill_index(repo, info["branch"])
    unknown = index is None
    index = index or {"skills": {}, "tree_size": 0, "inspection_mode": "unavailable",
                      "complete": False}
    found = index["skills"]
    names = sorted(found)

    # 冲突检测：会覆盖掉别的项目已装的 skill（DSH 只管 npm 包，没有这层）
    # 与 install 用的是同一个 find_skill_conflicts，保证预检结论 == 安装行为
    conflicts = find_skill_conflicts(repo, names, data)

    payload = {
        "repo": repo,
        "name": name,
        "branch": info["branch"],
        "sha": info["sha"],
        "sha_short": info["sha_short"],
        "stars": info["stars"],
        "desc": info["desc"],
        "last_msg": info["msg"],
        "pushed_at": info["pushed_at"],
        "skill_names": names,
        "skill_paths": [{"name": n, "path": found[n]} for n in names],
        "skill_count": len(names),
        "tree_size": index.get("tree_size", 0),
        "inspection_mode": index.get("inspection_mode", "unavailable"),
        "inspection_complete": bool(index.get("complete", False)),
        "conflicts": conflicts,
        "already": bool(dup),
    }

    if not names:
        uncertain = unknown or not index.get("complete", False)
        emit("done", "预检完成：%s" % ("未能完整确认包结构" if uncertain else "该仓库不含标准 skill 包"),
             percent=100, ok=False, code=None if uncertain else E_NOT_SKILL,
             detail=("目录索引不完整或不可用，安装时会用 ZIP 索引最终确认" if uncertain
                     else "未发现 */skills/<name>/SKILL.md"),
             hint="仍可只安装源码备用", data=payload)
        return

    label = "预检完成：%s%d 个 skill" % (
        "至少 " if not index.get("complete", False) else "", len(names))
    if conflicts:
        label += "（有 %d 个会覆盖已装的）" % len(conflicts)
    emit("done", label, percent=100, ok=True,
         code=E_CONFLICT if conflicts else None,
         detail=("将覆盖：%s" % "、".join(c["skill"] for c in conflicts[:6])) if conflicts else None,
         data=payload)
