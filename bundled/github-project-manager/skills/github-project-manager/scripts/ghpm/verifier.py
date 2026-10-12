# -*- coding: utf-8 -*-
"""数据完整性检查（``ghpm verify``）。

和 doctor 的分工：
    doctor  —— 环境能不能用（Python / curl / token / 目录 / 锁 / 磁盘）
    verify  —— 数据对不对（清单记录的，磁盘上到底有没有、是不是那一份）

三条边各查一遍：
    清单 ──磁盘    source_dir / skills 是否存在、是否越界、SKILL.md 在不在
    磁盘 ──清单    有没有没人认领的孤儿目录
    清单 ──远端    sha 是否还跟得上（--remote，需要网络）

**指纹**是 v4 新增的能力：安装时把源码树与每个 skill 的指纹写进清单，
verify 重算一遍就能发现「GitHub 没更新，但本地被人手改过」——
只比对 sha 是发现不了的，sha 只描述远端。
"""
from __future__ import annotations

from . import config
from .pathguard import is_within, validate_managed_path
from .registry import skill_owner_map
from .util import tree_fingerprint
from .errors import UnsafePathError

LEVEL_OK = "ok"
LEVEL_WARN = "warn"
LEVEL_FAIL = "fail"


def _f(level: str, code: str, message: str, path: str = "") -> dict:
    item = {"level": level, "code": code, "message": message}
    if path:
        item["path"] = path
    return item


def verify_project(p: dict, data: dict, owners: dict | None = None,
                   remote: dict | None = None) -> dict:
    """检查单个项目。返回 {repo, name, status, findings}。纯只读。"""
    repo = p.get("repo") or p.get("name") or "?"
    findings = []
    owners = owners if owners is not None else skill_owner_map(data)

    # ---- 清单字段本身 ----
    if not p.get("repo"):
        findings.append(_f(LEVEL_WARN, "no_repo", "清单记录缺 repo 字段（v1 遗留），"
                                                 "无法比对远端，也无法作为唯一 ID"))
    for k in ("sha", "skill_names", "source_dir"):
        if not p.get(k):
            findings.append(_f(LEVEL_WARN, "missing_field", "清单缺字段 %s" % k))

    # ---- source_dir ----
    sd = p.get("source_dir")
    source_ok = False
    resolved = None
    if sd:
        try:
            resolved = validate_managed_path(sd, config.WB, "source_dir")
        except UnsafePathError as e:
            findings.append(_f(LEVEL_FAIL, "source_outside_wb", str(e), sd))
            resolved = None
        if resolved is not None:
            if resolved.is_dir():
                source_ok = True
                findings.append(_f(LEVEL_OK, "source",
                                   "源码副本存在 · %s" % resolved))
            else:
                findings.append(_f(LEVEL_FAIL, "source_missing",
                                   "清单登记了源码目录，磁盘上却没有", str(resolved)))
    if not sd:
        findings.append(_f(LEVEL_WARN, "no_source", "没有登记源码副本目录"))

    # ---- 内容指纹：源码 ----
    if source_ok and p.get("content_hash"):
        try:
            digest, stats = tree_fingerprint(resolved, content=False)
            if digest != p["content_hash"]:
                findings.append(_f(LEVEL_WARN, "source_modified",
                                   "源码副本与安装时不一致（本地被改过，"
                                   "或上次安装未记录指纹）", str(resolved)))
            else:
                findings.append(_f(LEVEL_OK, "source_hash",
                                   "源码指纹一致 · %d 文件" % stats.files))
        except Exception as e:
            findings.append(_f(LEVEL_WARN, "source_hash_error",
                               "无法计算源码指纹：%s" % str(e)[:120], str(resolved)))
    elif source_ok:
        findings.append(_f(LEVEL_WARN, "no_source_hash",
                           "清单没有源码指纹（v3.2 之前装的），本次无法判断是否被改过"))

    # ---- skills ----
    hashes = p.get("skill_hashes") or {}
    skill_names = list(p.get("skill_names", []) or [])
    for n in skill_names:
        dst = config.SKILLS / str(n)
        if not dst.is_dir():
            findings.append(_f(LEVEL_FAIL, "skill_missing",
                               "skill %s：清单里有，磁盘上没有" % n, str(dst)))
            continue
        if not (dst / "SKILL.md").is_file():
            findings.append(_f(LEVEL_FAIL, "skill_no_skillmd",
                               "skill %s：目录在，但缺 SKILL.md" % n, str(dst)))
        else:
            findings.append(_f(LEVEL_OK, "skill", "skill %s 存在" % n, str(dst)))
        owner = owners.get(n)
        if owner and str(owner).lower() != str(repo).lower():
            findings.append(_f(LEVEL_WARN, "skill_shared",
                               "skill %s 同时被 %s 登记（后装的赢，实际内容以它为准）"
                               % (n, owner), str(dst)))
        if n in hashes:
            try:
                digest = tree_fingerprint(dst, content=True)[0]
                if digest != hashes[n]:
                    findings.append(_f(LEVEL_WARN, "skill_modified",
                                       "skill %s 的内容与安装时不一致（本地被改过）" % n,
                                       str(dst)))
            except Exception:
                pass
        if not is_within(dst, config.SKILLS):
            findings.append(_f(LEVEL_FAIL, "skill_outside", "skill 目录越界", str(dst)))

    # ---- 远端 ----
    if remote is not None:
        info = remote.get(repo.lower())
        if info is None:
            findings.append(_f(LEVEL_WARN, "remote_unavailable", "没查到远端信息"))
        elif not p.get("sha"):
            findings.append(_f(LEVEL_WARN, "remote_unknown_local",
                               "本地没有 sha，无法判断是否落后（远端 %s）"
                               % (info.get("sha_short") or "-")))
        elif info.get("sha") == p.get("sha"):
            findings.append(_f(LEVEL_OK, "remote", "已是最新 · %s" % info.get("sha_short")))
        else:
            findings.append(_f(LEVEL_WARN, "outdated",
                               "落后于远端：%s → %s"
                               % (p.get("sha_short") or "-", info.get("sha_short"))))

    status = LEVEL_FAIL if any(x["level"] == LEVEL_FAIL for x in findings) else (
        LEVEL_WARN if any(x["level"] == LEVEL_WARN for x in findings) else LEVEL_OK)
    return {"repo": repo, "name": p.get("name", repo), "status": status,
            "findings": findings}


def find_orphans(data: dict) -> list:
    """SKILLS 目录里像 ghpm 装的、却没有任何项目认领的 skill。

    只做提示不做错误：用户完全可以手动往 skills/ 里放东西。
    判据是「有 SKILL.md 但没被任何项目登记」。
    """
    claimed = set()
    for p in data.get("projects", []):
        claimed.update(p.get("skill_names", []) or [])
    orphans = []
    try:
        for d in sorted(config.SKILLS.iterdir()):
            if not d.is_dir() or d.name in claimed:
                continue
            if (d / "SKILL.md").is_file():
                orphans.append(str(d))
    except Exception:
        pass
    return orphans


def verify_all(data: dict, remote_infos: dict | None = None) -> dict:
    """检查清单里的全部项目，返回结构化结果（CLI 只负责渲染）。"""
    owners = skill_owner_map(data)
    projects = []
    for p in data.get("projects", []):
        if not isinstance(p, dict):
            continue
        projects.append(verify_project(p, data, owners=owners, remote=remote_infos))
    orphans = find_orphans(data)
    summary = {s: sum(1 for x in projects if x["status"] == s)
               for s in (LEVEL_OK, LEVEL_WARN, LEVEL_FAIL)}
    return {"ok": summary[LEVEL_FAIL] == 0,
            "projects": projects,
            "orphans": orphans,
            "summary": summary,
            "checked": len(projects)}
