# -*- coding: utf-8 -*-
"""update：更新已登记项目（单个 / --all / --dry-run）。

v4 重构要点（评审 P0#3）：

    v3.2  update --all
            ├── fetch_repo_infos()      5 个仓库 → 5 次 repo_info（每次 2 个 HTTP）
            └── install(A..E)           每个 install 又 ttl=0 查一遍 → 又 5 次
                                  合计 10 次 repo_info ≈ 20 个 HTTP
                                  匿名额度 60/h，一次 --all 只撑得住 15 个仓库

    v4    update --all
            ├── fetch_repo_infos()      5 次，作为「批量计划」
            └── install(A..E, info=…)   复用上面的结果，0 次额外请求
                                  合计 5 次 ≈ 10 个 HTTP，额度翻倍

为什么不干脆「预检完一次性批量写」：那样后面几个仓库会拿着几分钟前的
sha 去安装，而这期间远端可能又变了。所以这里保留**逐仓库独立事务**，
并且给复用的信息加了一个保鲜窗口（GHPM_INFO_REUSE_SEC，默认 120 秒）：
超出窗口就为那个仓库单独补查一次，宁可多一个请求，也不拿过期 sha 安装。
"""
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field

from .. import config
from ..errors import E_NETWORK, E_NOT_FOUND, ConflictError
from ..installer import install
from ..registry import find_project, load, persist_checked_at
from ..remote import classify_net_error, fetch_repo_infos, repo_info
from ..util import emit

try:
    INFO_REUSE_SEC = float(os.environ.get("GHPM_INFO_REUSE_SEC") or 120)
except Exception:
    INFO_REUSE_SEC = 120.0


@dataclass
class UpdateRequest:
    """一次 update 的全部输入。CLI 只负责把 args 变成它。"""

    names: list = field(default_factory=list)
    force: bool = False
    fresh: bool = False
    dry_run: bool = False
    is_all: bool = False

    @property
    def ttl(self) -> float:
        return 0.0 if self.fresh else config.CACHE_TTL

    @classmethod
    def from_args(cls, args, data: dict):
        """把 argparse 的命名空间翻译成请求。找不到项目时打印并返回 None。"""
        if getattr(args, "all", False):
            names = [p.get("repo") or p.get("name") for p in data.get("projects", [])]
            return cls(names=names, force=bool(getattr(args, "force", False)),
                       fresh=bool(getattr(args, "fresh", False)),
                       dry_run=bool(getattr(args, "dry_run", False)), is_all=True)
        name = getattr(args, "name", None)
        if not name:
            print("请指定项目名或 --all")
            return None
        hit = find_project(data, name)
        if not hit:
            emit("failed", "未找到项目", percent=100, code=E_NOT_FOUND, detail=name,
                 hint="用 `ghpm list` 看看已登记的项目名")
            print("未找到项目：%s" % name)
            return None
        return cls(names=[hit.get("repo") or hit.get("name")],
                   force=bool(getattr(args, "force", False)),
                   fresh=bool(getattr(args, "fresh", False)),
                   dry_run=bool(getattr(args, "dry_run", False)))


@dataclass
class UpdateResult:
    """一次 update 的结果。渲染层只认它，不关心过程。"""

    total: int = 0
    updated: int = 0
    skipped: list = field(default_factory=list)
    failed: list = field(default_factory=list)
    plans: list = field(default_factory=list)     # [{repo, status, from, to}]

    def successful(self) -> int:
        return self.updated + len(self.skipped)


class Updater:
    """update 的服务层：算计划 → 逐仓库执行 → 汇总。"""

    def __init__(self, data: dict, request: UpdateRequest, reuse_sec: float | None = None):
        self.data = data
        self.req = request
        self.reuse_sec = INFO_REUSE_SEC if reuse_sec is None else reuse_sec

    # ---- 批量计划 ----

    def build_plan(self, latest: dict) -> list:
        """把预检结果整理成一张「哪个要更新」的表。纯展示，不写盘。"""
        plans = []
        for repo in self.req.names:
            key = (repo or "").lower()
            cur = find_project(self.data, repo) or {}
            info = latest.get(key)
            if info is None:
                plans.append({"repo": repo, "status": "unknown",
                              "from": cur.get("sha_short", "-"), "to": "-"})
            elif not cur.get("sha") or cur.get("sha") != info.get("sha"):
                plans.append({"repo": repo, "status": "outdated",
                              "from": cur.get("sha_short", "-"),
                              "to": info.get("sha_short", "-")})
            else:
                plans.append({"repo": repo, "status": "latest",
                              "from": cur.get("sha_short", "-"),
                              "to": info.get("sha_short", "-")})
        return plans

    def _print_plan(self, plans: list) -> None:
        if len(self.req.names) <= 1:
            return
        counts = {"outdated": 0, "latest": 0, "unknown": 0}
        for p in plans:
            counts[p["status"]] = counts.get(p["status"], 0) + 1
        print("计划：%d 个需要更新，%d 个已是最新，%d 个没查到"
              % (counts["outdated"], counts["latest"], counts["unknown"]))
        for p in plans:
            mark = {"outdated": "有更新", "latest": "最新", "unknown": "未知"}[p["status"]]
            print("  [%-6s] %-42s %s -> %s"
                  % (mark, p["repo"], p["from"], p["to"]))

    # ---- 逐仓库 ----

    def _info_for(self, repo: str, latest: dict, stamp: float):
        """给这个仓库挑一份可信的最新信息。

        批量预检的结果只要还在保鲜窗口内就直接复用（这才消灭了 N+1）；
        超出窗口就为它单独补查一次 —— 长批量任务跑到后面几个仓库时，
        最初那份预检结果已经不能代表远端现状了。
        """
        info = latest.get((repo or "").lower())
        if info is not None and (time.time() - stamp) <= self.reuse_sec:
            return info, None
        try:
            return repo_info(repo), None
        except Exception as e:
            return None, e

    def run(self) -> UpdateResult:
        names = [n for n in self.req.names if n]
        result = UpdateResult(total=len(names))

        if not names:
            # 必须 emit，否则宿主等不到 __GHPM__ done 会一直挂着
            emit("done", "清单为空，没有可更新的项目", percent=100, ok=True,
                 data={"count": 0, "outdated": 0, "results": []})
            print("清单为空。用 `ghpm add <repo>` 添加，或 `ghpm scan` 自动发现。")
            return result

        if self.req.dry_run:
            return self._dry_run(names)

        # 预检一律 ttl=0：结果要被 install 复用，必须是最新的 sha。
        # 用缓存会让「要不要跳过」建立在过期 sha 上，可能漏更新，
        # 也可能把「已经是最新」判断错。写操作值得多花这几个请求。
        fetched, _fetch_errors = fetch_repo_infos(
            names, ttl=0,
            progress=lambda d, t, r: emit(
                "checking", "检查更新 %d/%d · %s" % (d, t, r),
                percent=int(20 * d / max(1, t))))
        stamp = time.time()
        result.plans = self.build_plan(fetched)
        self._print_plan(result.plans)

        for repo in names:
            info, err = self._info_for(repo, fetched, stamp)
            if err is not None:
                print("  [提示] %-42s 预检未取得信息（%s），改为直接尝试安装"
                      % (repo, str(err)[:50]))

            if not self.req.force and info is not None:
                # 先比 sha：没变就别下载别解压别备份（v2 的 update --all 每个项目都全量重装）
                cur = find_project(self.data, repo) or {}
                if cur.get("sha") and info.get("sha") and cur["sha"] == info.get("sha"):
                    print("  [跳过]   %-42s %s 已是最新" % (repo, info.get("sha_short")))
                    result.skipped.append(repo)
                    continue

            try:
                # 关键：把刚拿到的 info 传进去，install 不再重复查远程（N+1 → N）
                install(repo, allow_non_skill=True, force=self.req.force, info=info)
                result.updated += 1
            except ConflictError as e:
                result.failed.append(repo)
                print("skill 冲突，跳过 %s: %s" % (repo, e), file=sys.stderr)
            except Exception as e:
                result.failed.append(repo)
                print("更新失败 %s: %s" % (repo, e), file=sys.stderr)

        if result.skipped:
            persist_checked_at(result.skipped)
        self._render(result)
        return result

    def _render(self, result: UpdateResult) -> None:
        if result.total <= 1:
            # 单项目：install 已经 emit 过 done；只有「跳过」这条路需要自己收尾
            if result.skipped:
                emit("done", "已是最新，无需更新", percent=100, ok=True,
                     data={"repo": result.skipped[0], "skipped": 1, "count": 0})
            return
        successful = result.successful()
        print("\n%d/%d 处理成功（实际更新 %d）" % (successful, result.total, result.updated))
        if result.skipped:
            print("%d 个已是最新，已跳过（要强制重装用 --force）：%s"
                  % (len(result.skipped), "、".join(result.skipped)))
        if result.failed:
            print("失败：%s" % "、".join(result.failed))
        emit("done", "%d/%d 处理成功" % (successful, result.total), percent=100,
             ok=(successful == result.total),
             data={"count": result.updated, "total": result.total,
                   "skipped": result.skipped, "failed": result.failed,
                   "plan": result.plans})

    # ---- dry-run ----

    def _dry_run(self, names: list) -> UpdateResult:
        """只回答「有没有更新」，不下载不写盘。"""
        result = UpdateResult(total=len(names))
        fetched, fetch_errors = fetch_repo_infos(
            names, ttl=self.req.ttl,
            progress=lambda d, t, r: emit(
                "checking", "预检 %d/%d · %s" % (d, t, r),
                percent=int(90 * d / max(1, t))))

        results, checked = [], []
        # 按传入顺序输出，避免并发导致每次排列都不同（对 diff / CI 不友好）
        for repo in names:
            key = (repo or "").lower()
            cur = find_project(self.data, repo) or {}
            if key in fetch_errors:
                e = fetch_errors[key]
                code, hint = classify_net_error(e)
                results.append({"repo": repo, "status": "error", "code": code,
                                "error": str(e)[:120], "hint": hint})
                print("  %-42s 检查失败: %s" % (repo, str(e)[:60]))
                continue
            info = fetched.get(key)
            if info is None:
                results.append({"repo": repo, "status": "error", "code": E_NETWORK,
                                "error": "未取得仓库信息",
                                "hint": "稍后重试，或用 --fresh 重查。"})
                print("  %-42s 未取得信息" % repo)
                continue
            checked.append(repo)
            outdated = (not cur.get("sha")) or cur.get("sha") != info.get("sha")
            entry = {"repo": repo, "name": cur.get("name", repo.split("/")[-1]),
                     "status": "outdated" if outdated else "latest",
                     "from": cur.get("sha_short", "-"), "to": info.get("sha_short"),
                     "msg": info.get("msg"), "stars": info.get("stars")}
            results.append(entry)
            result.plans.append({"repo": repo, "status": entry["status"],
                                 "from": entry["from"], "to": entry["to"]})
            print("  [%-6s] %-42s %s -> %s"
                  % ("有更新" if outdated else "最新", repo,
                     cur.get("sha_short", "-"), info.get("sha_short")))
        persist_checked_at(checked)
        n = sum(1 for r in results if r.get("status") == "outdated")
        errs = sum(1 for r in results if r.get("status") == "error")
        emit("done", "%d 个可更新（dry-run，未做任何改动）" % n, percent=100, ok=not errs,
             detail=("其中 %d 个没查到" % errs if errs else None),
             data={"outdated": n, "count": len(results), "results": results})
        return result


def cmd_update(args):
    """CLI 只是「参数 → 请求 → 服务 → 结果」的搬运工。"""
    data = load()
    request = UpdateRequest.from_args(args, data)
    if request is None:
        return None
    return Updater(data, request).run()
