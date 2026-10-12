# -*- coding: utf-8 -*-
"""安装 / 更新：resolve → fetch → inspect → plan → apply。

「算出要做什么」和「真的做」严格分开：plan 是纯数据，apply 只认 plan。
v3.2 立的结构保留，v4 在此基础上改了三处：

1. **build_install_plan 只遍历一次**解压根（index_source_tree 同时产出
   技能清单、全树体积、各技能体积），不再 find_skill_dirs + 逐目录 rglob。
2. **install 可以接收调用方已经拿到的 info**：``ghpm update --all`` 批量
   预检拿到的 RepoInfo 直接传进来，不再让每个 install 重新查一遍远程。
   实测 5 个仓库从 10 次 repo_info（约 20 个 HTTP）降到 5 次。
3. **apply 不再把源码写两遍**：解压根直接搬进 source_dir（同卷 rename），
   然后把 skill 从 source_dir 拷进 skills/。
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from . import config
from .archive import fetch_zip
from .discovery import index_source_tree
from .errors import (E_CONFLICT, E_INVALID_SPEC, E_LOCKED, E_NOT_FOUND, E_NOT_SKILL,
                     E_WRITE, ConflictError, UnsafePathError)
from .lock import LockSession
from .models import InstallPlan, RepoInfo
from .pathguard import is_within, remove_managed_path, skill_dir, validate_skill_name
from .remote import classify_net_error, parse_repo, repo_info
from .registry import find_project, load, save, skill_owner_map, source_dir_for, upsert_project
from .transaction import Transaction, move_or_copy_tree, report_rollback
from .util import (dir_size_mb, emit, ensure_disk_space, estimate_install_bytes,
                   format_bytes, now, tree_fingerprint)


def build_install_plan(repo: str, name: str, branch: str, info, root: Path,
                       data: dict, allow_non_skill: bool = False,
                       index=None) -> InstallPlan:
    """算出这次安装要做什么。纯计算，不写盘、不删文件。

    关键点是 removed_skills：v3.1 只跟踪「这次远端发现的 skill」，
    远端删掉某个 skill 后本地那份永远留着，成为孤儿目录 ——
    清单里已经没有它，skill_owner_map 认不出，remove 也管不到。
    这里把清单里的旧 skill_names 一起拿来算差集，让本地状态向远端收敛。

    index 是 index_source_tree 的结果（可选）；传进来就复用它那次遍历，
    不传则自己扫一遍。
    """
    info = RepoInfo.from_dict(info)
    if index is None:
        index = index_source_tree(root, fallback=name)
    pairs = index.skills
    new_skills = index.names
    old = find_project(data, repo) or find_project(data, name)
    old_skills = list(old.get("skill_names", [])) if old else []

    plan = InstallPlan(repo=repo, name=name, branch=branch,
                       old_sha=(old.get("sha", "") if old else ""),
                       new_sha=info.get("sha") or (old.get("sha", "") if old else ""),
                       old_skills=old_skills, new_skills=new_skills,
                       pairs=pairs, is_update=old is not None,
                       skill_stats=dict(index.skill_bytes))

    # 远端删掉的 skill：本地必须跟着删，否则留下无主孤儿目录
    plan.removed_skills = [n for n in old_skills if n not in new_skills]

    owners = skill_owner_map(data)
    for n in new_skills:
        owner = owners.get(n)
        if owner and owner.lower() != repo.lower():
            plan.conflicts.append({"skill": n, "owner": owner})
    # force 覆盖时，被抢的 skill 归本项目；没 force 的路径已经在 install 里抛错了
    plan.added_skills = [n for n in new_skills if n not in old_skills]
    plan.updated_skills = [n for n in new_skills if n in old_skills]

    plan.source_dir = source_dir_for(repo, name, data)
    plan.extracted_root = Path(index.root)
    targets = install_targets(plan)
    # 复用同一次遍历的结果，不再把 root 和每个 skill 目录各扫一遍
    plan.required_bytes = estimate_install_bytes(index.root, pairs, targets, index=index)
    return plan


def install_targets(plan: InstallPlan) -> list:
    """事务要备份/还原的全部路径。

    注意 removed_skills 也在内：删掉也要能撤销，否则「远端删了 skill」会变成
    一次不可回滚的破坏性操作。
    """
    targets = []
    for n in plan.old_skills + plan.new_skills + plan.removed_skills:
        try:
            targets.append(skill_dir(n))
        except UnsafePathError:
            continue
        except Exception:
            continue
    if plan.source_dir:
        targets.append(Path(plan.source_dir))
    out, seen = [], set()
    for t in targets:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def plan_root(plan: InstallPlan) -> Path:
    """源码副本的来源目录。build_install_plan 时记下解压根，避免 apply 再猜。"""
    return plan.extracted_root


def install(repo: str, branch: str | None = None, allow_non_skill: bool = False,
            force: bool = False, info=None) -> dict:
    """安装/更新。全程 emit 状态机；任何一步失败都自动回滚到安装前状态。

    事务顺序：加锁 → 远程信息 → 下载 → 校验 → 建 plan → 冲突检查 → 磁盘预检
            → 备份（含清单快照） → 写文件 → 更新清单（原子提交） → 清备份
    写文件或 save 任一环节失败，都走同一条 rollback：文件系统 + 清单一起还原。

    info：调用方已经拿到的远程信息（``update --all`` 的批量预检结果）。
    传进来就跳过本次的远程查询 —— 这是消灭 N+1 请求的关键，
    但**只应由刚刚亲自查过、且和本次写入是同一个动作的调用方传**，
    不要拿一个几分钟前的缓存值来安装。
    """
    emit("starting", "解析仓库地址", percent=5)
    try:
        repo = parse_repo(repo)
    except ValueError as e:
        emit("failed", "地址无法解析", percent=100, code=E_INVALID_SPEC, detail=str(e),
             hint="应为 owner/repo 或 https://github.com/owner/repo")
        raise
    name = repo.split("/")[1]

    def on_busy(holder):
        emit("failed", "有另一个任务正在修改，请稍后再试", percent=100, code=E_LOCKED,
             detail="占用者：%s（%s）" % (holder.get("op", "?"), holder.get("at", "?")))

    result = None
    with LockSession("install %s" % repo, on_busy=on_busy):
        tmp = None
        try:
            if info is None:
                emit("checking", "读取仓库信息 · %s" % repo, percent=12)
                try:
                    info = repo_info(repo)      # 安装必须拿最新 sha，不走缓存
                except Exception as e:
                    code, hint = classify_net_error(e)
                    emit("failed", "仓库不可达或不存在" if code == E_NOT_FOUND else "连不上仓库",
                         percent=100, code=code, detail=str(e)[:160], hint=hint)
                    raise
            else:
                emit("checking", "复用批量预检结果 · %s" % repo, percent=12)
            info = RepoInfo.from_dict(info)
            branch = branch or info["branch"]
            print("拉取 %s  分支=%s  最新=%s" % (repo, branch, info["sha_short"]))

            tmp, root, zip_index = fetch_zip(repo, branch, require_skill=not allow_non_skill)

            emit("inspecting", "检查包结构", percent=42)
            # 递归找：仓库里的 skills 目录可能在任意层级
            data = load()
            plan = build_install_plan(repo, name, branch, info, root, data, allow_non_skill)
            if not plan.new_skills and not allow_non_skill:
                emit("failed", "仓库里没有可装的 skill（缺少 skills/*/SKILL.md）", percent=100,
                     code=E_NOT_SKILL, detail="源码仍可安装，请在预检后选择「仍然安装源码」")
                raise RuntimeError("%s 仓库 %s 不含 skills/*/SKILL.md" % (E_NOT_SKILL, repo))

            # 冲突：inspect 早就算出来了，但 v3.1 只报告不阻止，
            # 结果是 B 装上去悄悄顶掉 A 的 foo。现在默认真拦。
            if plan.conflicts and not force:
                emit("failed", "有 %d 个 skill 已被其他项目占用" % len(plan.conflicts),
                     percent=100, code=E_CONFLICT,
                     detail="；".join("%s ← %s" % (c["skill"], c["owner"])
                                      for c in plan.conflicts[:6]),
                     hint="确认要覆盖就加 --force；或先 `ghpm remove <占用它的项目>`。",
                     data={"conflicts": plan.conflicts, "plan": plan.summary()})
                raise ConflictError(plan.conflicts)
            if plan.conflicts and force:
                print("  [警告] --force：覆盖 %d 个他人已装的 skill（%s）"
                      % (len(plan.conflicts),
                         "、".join(c["skill"] for c in plan.conflicts[:6])), file=sys.stderr)

            if plan.new_skills:
                config.SKILLS.mkdir(parents=True, exist_ok=True)

            required = plan.required_bytes
            try:
                free = ensure_disk_space(config.WB, required, "安装与备份时")
            except OSError as e:
                emit("failed", "磁盘空间不足", percent=100, code=E_WRITE,
                     detail=str(e),
                     hint="清理磁盘空间后重试；尚未创建事务备份或改动已安装文件。",
                     data={"required_bytes": required,
                           "zip_entries": zip_index.get("entry_count", 0)})
                raise
            emit("checking", "磁盘预检通过 · 需要约 %s / 可用 %s"
                 % (format_bytes(required), format_bytes(free)), percent=48)

            result = apply_install_plan(plan, info, data)
        finally:
            if tmp:
                shutil.rmtree(tmp, ignore_errors=True)
    return result


def apply_install_plan(plan: InstallPlan, info, data: dict) -> dict:
    """按 plan 落盘。全程在一个事务里，失败即回滚到操作前状态。

    顺序：先删远端已删除的 skill → 再把解压根搬进 source_dir（同卷 rename，
    省掉一整次源码复制）→ 从 source_dir 把 skill 拷进 skills/ → 最后写清单。
    中途任何一步抛错，tx.rollback() 会把删除的、搬走的、新写的全部还原。
    """
    info = RepoInfo.from_dict(info)
    tx = Transaction(plan.repo, plan.name, "update" if plan.is_update else "install")
    tx.track(install_targets(plan))
    emit("backing-up", "备份现有版本", percent=52)
    try:
        bd = tx.begin()
    except Exception as e:
        emit("failed", "备份失败，未改动现有文件", percent=100, code=E_WRITE,
             detail=str(e)[:160], hint=classify_write_error(e))
        raise
    emit("applying", "写入文件（此阶段不可取消）", percent=62, backup=str(bd))

    src_root = plan_root(plan)
    linked_root = src_root
    try:
        # 1) 远端删掉的 skill：本地一起删，让状态收敛到远端
        for n in plan.removed_skills:
            dst = skill_dir(n)
            if dst.exists():
                remove_managed_path(dst, "skill 目录")
            emit("applying", "移除已下线的 skill · %s" % n, percent=64)

        # 2) 完整源码副本
        skill_sources = list(plan.pairs)
        src_dir = Path(plan.source_dir) if plan.source_dir else None
        if src_dir is not None:
            # 解压根与 source_dir 必须互不包含。「先删干净再拷」在两者重叠时会自毁
            # （或者把自己拷进自己）。正常流程下 root 是临时目录、src_dir 在 WB 内，
            # 不会相交；但 build_install_plan 也会被外部直接喂 plan，所以这里显式挡住。
            if src_dir.resolve() == src_root.resolve():
                pass                    # 已经是最终状态，无需再搬
            elif is_within(src_root, src_dir):
                raise RuntimeError("解压根 %s 位于目标源码目录 %s 之内，拒绝写入以免破坏源目录"
                                   % (src_root, src_dir))
            else:
                if src_dir.exists():
                    remove_managed_path(src_dir, "源码目录")
                move_or_copy_tree(src_root, src_dir)
                linked_root = src_dir
                # skill 源目录跟着一起搬过来了，重新定位（一次裁剪，不再重扫）
                rebound = []
                for n, srcd in plan.pairs:
                    try:
                        rebound.append((n, src_dir / Path(srcd).relative_to(src_root)))
                    except (ValueError, TypeError):
                        rebound.append((n, srcd))
                skill_sources = rebound
        emit("applying", "写入完整源码", percent=68)

        # 3) 新增 / 更新的 skill：整目录替换（不是原地覆盖）
        total = max(1, len(skill_sources))
        for i, (n, srcd) in enumerate(skill_sources):
            dst = skill_dir(n)
            if dst.exists():
                remove_managed_path(dst, "skill 目录")
            shutil.copytree(srcd, dst)
            emit("applying", "写入 skill %d/%d · %s" % (i + 1, total, n),
                 percent=70 + int(22 * (i + 1) / (total + 1)))

        # 4) 记录内容指纹（供 `ghpm verify` 发现本地被改过）+ 写清单
        plan.content_hash, stats = tree_fingerprint(linked_root, content=False)
        plan.source_stats = stats.as_dict()
        for n in plan.new_skills:
            try:
                plan.skill_hashes[n] = tree_fingerprint(skill_dir(n), content=True)[0]
            except Exception:
                pass
        rec = commit_registry(plan, info, data)
    except Exception as e:
        emit("rollback", "安装失败，正在回滚…", percent=94, backup=str(bd))
        restored = tx.rollback()
        report_rollback(bd, restored, e)
        raise

    tx.commit()         # 成功：清备份
    emit("done", "完成 · %s" % plan.name, percent=100, data=rec)
    print("完成：%s" % plan.name)
    if plan.new_skills:
        print("  已安装 %d 个 skill 到 %s" % (len(plan.new_skills), config.SKILLS))
        print("   %s" % ", ".join(plan.new_skills))
    if plan.removed_skills:
        print("  已移除 %d 个远端已下线的 skill：%s"
              % (len(plan.removed_skills), "、".join(plan.removed_skills)))
    size_mb = (plan.source_stats.get("bytes", 0) / config.MIB) if plan.source_stats \
        else dir_size_mb(plan.source_dir)
    print("  完整源码：%s（占 %.1f MB）" % (plan.source_dir, size_mb))
    print("  提示：源码只是副本，不需要可用 `ghpm remove %s` 一并清掉。" % plan.name)
    return rec


def commit_registry(plan: InstallPlan, info, data: dict) -> dict:
    """写清单。清单也是事务的一部分：save 失败会连同文件一起回滚。"""
    info = RepoInfo.from_dict(info)
    old = find_project(data, plan.repo) or find_project(data, plan.name)
    stamp = now()
    old_sha = old.get("sha", "") if old else ""
    new_sha = plan.new_sha or old_sha
    sha_changed = old is None or (bool(new_sha) and new_sha != old_sha)
    rec = {
        "name": plan.name,
        "repo": plan.repo,
        "url": "https://github.com/%s" % plan.repo,
        "branch": plan.branch,
        "sha": new_sha,
        "sha_short": new_sha[:7] if new_sha else info.get("sha_short", ""),
        "stars": info.get("stars", 0),
        "desc": info.get("desc", ""),
        "pushed_at": info.get("pushed_at", ""),
        "last_msg": info.get("msg", ""),
        "source_dir": str(plan.source_dir) if plan.source_dir else "",
        # 记录最终状态：被 force 覆盖掉的冲突 skill 归到本项目，没覆盖的 kept 不算进来
        "skill_names": list(plan.new_skills),
        "installed_at": old.get("installed_at", stamp) if old else stamp,
        "updated_at": (stamp if sha_changed else old.get("updated_at", stamp)),
        "checked_at": stamp,
        "previous_sha": (old_sha if old and sha_changed else
                         (old.get("previous_sha", "") if old else "")),
        # v4：内容指纹，供 verify 判断本地是否被改过
        "content_hash": plan.content_hash or (old.get("content_hash", "") if old else ""),
        "skill_hashes": dict(plan.skill_hashes) or
                        (old.get("skill_hashes", {}) if old else {}),
    }
    if old:
        # 走备用源时可能拿不到 stars/desc，别把已有数据抹成 0
        if not rec.get("stars"):
            rec["stars"] = old.get("stars", 0)
        if not rec.get("desc"):
            rec["desc"] = old.get("desc", "")
    upsert_project(data, rec)
    save(data)      # 原子提交；这里失败上面的 rollback 会把清单一起还原
    return rec
