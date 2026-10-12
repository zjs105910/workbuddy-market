# -*- coding: utf-8 -*-
"""清单（Registry）：~/.workbuddy/github-projects.json 的读写、迁移与查询。

repo 是唯一 ID，name 只是显示名 —— alice/utils 和 bob/utils 都叫 utils，
v2 按 name 去重会让后者静默覆盖前者。
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .lock import LockSession
from .util import atomic_write_bytes, now, safe_key

GH_RE = config.GH_RE


def empty_registry() -> dict:
    return {"schema_version": config.REGISTRY_SCHEMA_VERSION, "projects": []}


# ---------- 迁移链 ----------

def migrate_v1_to_v2(data: dict) -> dict:
    """v1 以 name 为主键；v2 尽量从 url 补出 repo 唯一标识。"""
    for p in data.get("projects", []):
        if not isinstance(p, dict):
            continue
        if not p.get("repo"):
            m = GH_RE.search(str(p.get("url", "")))
            if m:
                p["repo"] = "%s/%s" % (m.group(1), m.group(2))
        if not p.get("name") and p.get("repo"):
            p["name"] = str(p["repo"]).split("/")[-1]
    data["schema_version"] = 2
    return data


def migrate_v2_to_v3(data: dict) -> dict:
    """v3 拆分版本变化时间与远端检查时间，并保留上一个 SHA。"""
    for p in data.get("projects", []):
        if not isinstance(p, dict):
            continue
        p.setdefault("checked_at", p.get("updated_at") or p.get("installed_at") or "")
        p.setdefault("previous_sha", "")
    data["schema_version"] = 3
    return data


def migrate_v3_to_v4(data: dict) -> dict:
    """v4 增加内容指纹，供 `ghpm verify` 判断本地是否被手动改过。

    老记录没有指纹，留空即可 —— verify 会把「没有指纹」报成 unknown，
    而不是报成「被改过」。
    """
    for p in data.get("projects", []):
        if not isinstance(p, dict):
            continue
        p.setdefault("content_hash", "")
        p.setdefault("skill_hashes", {})
    data["schema_version"] = 4
    return data


MIGRATIONS = [(2, migrate_v1_to_v2), (3, migrate_v2_to_v3), (4, migrate_v3_to_v4)]


def migrate_registry(data: dict) -> dict:
    if not isinstance(data, dict) or not isinstance(data.get("projects"), list):
        raise ValueError("projects 字段缺失或不是列表")
    try:
        version = int(data.get("schema_version", 1))
    except Exception:
        version = 1
    if version > config.REGISTRY_SCHEMA_VERSION:
        print("[警告] 清单 schema_version=%d 高于当前支持的 %d；将保留未知字段。"
              % (version, config.REGISTRY_SCHEMA_VERSION), file=sys.stderr)
        return data
    for target, fn in MIGRATIONS:
        if version < target:
            data = fn(data)
            version = target
    data["schema_version"] = config.REGISTRY_SCHEMA_VERSION
    return data


# ---------- 读写 ----------

def load() -> dict:
    """读清单并在内存中迁移。坏 JSON 先改名留档，避免后续 save() 静默覆盖。"""
    reg = config.REGISTRY
    if reg.exists():
        try:
            d = json.loads(reg.read_text(encoding="utf-8"))
            return migrate_registry(d)
        except Exception as e:
            bak = reg.with_name(
                reg.name + ".corrupt-" + time.strftime("%Y%m%d-%H%M%S"))
            try:
                reg.replace(bak)
            except Exception:
                bak = None
            print("[警告] 清单文件损坏（%s），原件已留档为 %s，本次按空清单处理。"
                  % (e, bak or "（改名失败，请手动检查）"), file=sys.stderr)
    return empty_registry()


def save(data: dict) -> None:
    """原子写清单，并统一落盘当前 schema_version；拒绝覆盖未来版本。"""
    try:
        version = int(data.get("schema_version", 1))
    except Exception:
        version = 1
    if version > config.REGISTRY_SCHEMA_VERSION:
        raise ValueError("清单 schema v%d 高于当前支持的 v%d，拒绝降级覆盖"
                         % (version, config.REGISTRY_SCHEMA_VERSION))
    data = migrate_registry(data)
    data["schema_version"] = config.REGISTRY_SCHEMA_VERSION
    atomic_write_bytes(config.REGISTRY,
                       json.dumps(data, ensure_ascii=False, indent=2))


# ---------- 查询 ----------

def project_id(p: dict) -> str:
    """项目唯一 ID = repo（小写）。name 只是显示名。"""
    return str(p.get("repo") or p.get("name") or "").lower()


def find_project(data: dict, ident: str) -> dict | None:
    """先按 repo 精确匹配，再退回 name（兼容用户输仓库名的习惯）。"""
    ident = (ident or "").strip().lower()
    if not ident:
        return None
    for p in data.get("projects", []):
        if str(p.get("repo", "")).lower() == ident:
            return p
    for p in data.get("projects", []):
        if str(p.get("name", "")).lower() == ident:
            return p
    return None


def upsert_project(data: dict, rec: dict) -> None:
    """按 repo 去重写入。老记录没有 repo 字段时，退化成按 name 去重。"""
    key = str(rec.get("repo", "")).lower()
    name = str(rec.get("name", "")).lower()

    def keep(p: dict) -> bool:
        if key and str(p.get("repo", "")).lower() == key:
            return False
        if not p.get("repo") and name and str(p.get("name", "")).lower() == name:
            return False
        return True

    data["projects"] = [p for p in data.get("projects", []) if keep(p)]
    data["projects"].append(rec)


def drop_project(data: dict, ident: str) -> dict | None:
    """从清单里摘掉一个项目，返回被摘掉的那条。"""
    hit = find_project(data, ident)
    if hit is None:
        return None
    data["projects"] = [p for p in data["projects"] if p is not hit]
    return hit


def persist_checked_at(repos, stamp: str | None = None) -> bool:
    """短暂加锁后记录成功检查时间；抢不到锁就跳过，不影响只读检查结果。"""
    repos = {str(r).lower() for r in repos if r}
    if not repos:
        return True
    try:
        with LockSession("record checked_at") as sess:
            data = load()
            stamp = stamp or now()
            changed = False
            for p in data.get("projects", []):
                if str(p.get("repo", "")).lower() in repos:
                    p["checked_at"] = stamp
                    changed = True
            if changed:
                save(data)
            return True
    except Exception as e:
        print("  [警告] 无法记录 checked_at：%s" % e, file=sys.stderr)
        return False


def source_dir_for(repo: str, name: str, data: dict | None = None) -> Path:
    """源码副本目录。默认 <repo名>-source（兼容 v2 已装的目录）；
    若该目录已被**另一个**仓库占用，退化为 owner__repo-source，避免互相覆盖。"""
    for p in (data or {}).get("projects", []):
        if str(p.get("repo", "")).lower() == repo.lower() and p.get("source_dir"):
            return Path(p["source_dir"])
    preferred = config.WB / ("%s-source" % name)
    try:
        preferred_resolved = preferred.resolve()
    except Exception:
        preferred_resolved = preferred
    for p in (data or {}).get("projects", []):
        if str(p.get("repo", "")).lower() == repo.lower():
            continue
        sd = p.get("source_dir")
        if not sd:
            continue
        try:
            if Path(sd).resolve() == preferred_resolved:
                return config.WB / ("%s-source" % safe_key(repo))
        except Exception:
            continue
    return preferred


def skill_owner_map(data: dict | None = None) -> dict:
    """已装的 skill 名 → 归属项目（repo），用于算冲突。

    同一个 skill 被两个项目登记是可能的（v3.1 的 install 会静默覆盖，
    两条记录都留在清单里）。这里保留**最后一个**声明者，
    跟「后装的赢」这个既有实际行为一致。
    """
    m = {}
    for p in (data if data is not None else load()).get("projects", []):
        if not isinstance(p, dict):
            continue
        for n in p.get("skill_names", []):
            m[n] = p.get("repo") or p.get("name", "?")
    return m


def find_skill_conflicts(repo: str, skill_names, data: dict | None = None) -> list:
    """列出「会被别的项目抢走」的 skill。

    inspect 报告它、install 拒绝它 —— 两边必须用同一个函数，
    否则预检说没冲突、安装时又覆盖，用户根本没法预判。
    """
    owners = skill_owner_map(data)
    out = []
    for n in skill_names:
        owner = owners.get(n)
        if owner and owner.lower() != repo.lower():
            out.append({"skill": n, "owner": owner})
    return out


def dir_ts(*paths, mtime: bool = False) -> str:
    """取第一个存在目录的 ctime（安装时间）/ mtime（最后改动时间），存 UTC ISO。
    scan 登记的是早就装好的项目，这里若填 now() 会让 list 的时间排序失去意义。"""
    attr = "st_mtime" if mtime else "st_ctime"
    for p in paths:
        try:
            if p and Path(p).exists():
                ts = getattr(Path(p).stat(), attr)
                return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")
        except Exception:
            continue
    return now()
