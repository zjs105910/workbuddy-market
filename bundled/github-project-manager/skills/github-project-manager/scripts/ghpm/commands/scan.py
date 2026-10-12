# -*- coding: utf-8 -*-
"""scan：扫描本机已存在但尚未登记的 GitHub 项目，只登记不重装。"""
from __future__ import annotations

from .. import config
from ..discovery import find_skill_dirs
from ..errors import E_LOCKED, E_WRITE
from ..lock import LockSession
from ..registry import dir_ts, load, project_id, save, source_dir_for, upsert_project
from ..remote import fetch_repo_infos
from ..transaction import Transaction, report_rollback
from ..util import classify_write_error, emit, now


def _cmd_scan_locked(args):
    """扫描本机已存在但尚未登记的 GitHub 项目（调用方必须持锁）。"""
    data = load()
    known = {project_id(p) for p in data["projects"]}
    found = []

    # 1) skills 目录下 SKILL.md 里带 github source 的
    if config.SKILLS.is_dir():
        for d in sorted(config.SKILLS.iterdir()):
            f = d / "SKILL.md"
            if not f.is_file():
                continue
            try:
                txt = f.read_text(encoding="utf-8", errors="replace")[:2000]
            except Exception:
                continue
            m = config.GH_RE.search(txt)
            if m:
                found.append(("%s/%s" % (m.group(1), m.group(2)), d.name))

    # 2) ~/.workbuddy/*-source 目录
    for d in sorted(config.WB.glob("*-source")):
        if not d.is_dir():
            continue
        rf = d / "README.md"
        if not rf.is_file():
            continue
        try:
            txt = rf.read_text(encoding="utf-8", errors="replace")[:3000]
        except Exception:
            continue
        for m in config.GH_RE.finditer(txt):
            found.append(("%s/%s" % (m.group(1), m.group(2)), d.name))

    seen, uniq = set(), []
    for repo, src in found:
        if repo.lower() in known or repo.lower() in seen:
            continue
        seen.add(repo.lower())
        uniq.append((repo, src))

    if not uniq:
        print("没有发现新的未登记项目。")
        return

    print("发现 %d 个未登记项目：" % len(uniq))
    ttl = 0 if getattr(args, "fresh", False) else config.CACHE_TTL
    added = []
    # scan 也要逐个问 GitHub，串行时项目一多就很慢；同样走并发。
    fetched, fetch_errors = fetch_repo_infos(
        [repo for repo, _ in uniq], ttl=ttl,
        progress=lambda d, t, r: emit(
            "checking", "查询 %d/%d · %s" % (d, t, r), percent=int(20 * d / max(1, t))))

    tx = Transaction("registry-scan", "scan", "scan")
    tx.track([])                    # 只写清单，也走事务，写坏能还原
    try:
        tx.begin()
    except Exception as e:
        emit("failed", "清单备份失败，未登记任何项目", percent=100, code=E_WRITE,
             detail=str(e)[:160], hint=classify_write_error(e))
        raise
    try:
        for repo, src in uniq:
            info = fetched.get(repo.lower())
            if info is None:
                e = fetch_errors.get(repo.lower())
                print("  %-40s 跳过（%s）" % (repo, str(e)[:60] if e else "未取得信息"))
                continue
            name = repo.split("/")[1]
            if src.endswith("-source") and (config.WB / src).is_dir():
                src_dir = config.WB / src          # 扫到的就是源码目录本身
            else:
                src_dir = source_dir_for(repo, name, data)
            if src.endswith("-source"):
                # 从源码目录里找 skill，只算那些确实已装进 SKILLS 的
                skill_names = [n for n, _ in find_skill_dirs(config.WB / src, fallback=name)
                               if (config.SKILLS / n).is_dir()]
            else:
                # src 是某个已装 skill 的目录名，它的 SKILL.md 里写了这个仓库地址
                skill_names = [src] if (config.SKILLS / src).is_dir() else []
            rec = {
                "name": name, "repo": repo, "url": "https://github.com/%s" % repo,
                "branch": info["branch"], "sha": info["sha"], "sha_short": info["sha_short"],
                "stars": info["stars"], "desc": info["desc"], "last_msg": info["msg"],
                "source_dir": str(src_dir) if src_dir.exists() else "",
                # 之前这里硬编码成 []，前面算出来的 skill_names 全白算了：
                # remove 时不会删已装的 skill，skill_owner_map 也算不出冲突。
                "skill_names": skill_names,
                "installed_at": dir_ts(src_dir, *[config.SKILLS / n for n in skill_names]),
                "updated_at": dir_ts(src_dir, *[config.SKILLS / n for n in skill_names],
                                     mtime=True),
                "checked_at": now(),
                "previous_sha": "",
                # scan 只登记既有目录，不重写内容，所以没有可信指纹
                "content_hash": "",
                "skill_hashes": {},
            }
            upsert_project(data, rec)
            added.append(rec)
            print("  + %-40s %s  (%s)" % (repo, info["sha_short"], info["desc"][:40]))
        save(data)
    except Exception as e:
        emit("rollback", "登记失败，正在回滚清单…", percent=94, backup=str(tx.bd))
        restored = tx.rollback()
        report_rollback(tx.bd, restored, e)
        raise
    tx.commit()
    print("\n已登记 %d 个。注意：scan 只登记不重装，skill 归属请用 add 明确安装。" % len(added))


def cmd_scan(args):
    def on_busy(holder):
        emit("failed", "有另一个任务正在修改，请稍后再试", percent=100, code=E_LOCKED,
             detail="占用者：%s" % holder.get("op", "?"))

    with LockSession("scan", on_busy=on_busy):
        return _cmd_scan_locked(args)
