# -*- coding: utf-8 -*-
"""build_registry —— 注册表每日重建脚本（CI 与本机共用）。

.github/workflows/registry.yml 每天跑一次：
    python scripts/build_registry.py
对本仓库 registry/plugins.json 的每条 entry 拉一次 GitHub API，
只更新动态字段（stars / pushedAt / latestSha / refreshedAt），
静态字段（收录信息）原样保留 —— 注册表是「人工审核 + 机器补数据」。

原则与内核一致：
  · 单条失败不动那条的旧值（下轮再试），整轮失败退出码非 0；
  · 原子写（临时文件 + os.replace），绝不留半截 JSON；
  · 凭证从环境变量 GITHUB_TOKEN 读取（CI 的内置 token 就够），
    只进请求头，绝不落盘、绝不打印。

本机也可以手动跑（比如收录了新条目想立刻补数据）：
    python scripts/build_registry.py            # 实际写回
    python scripts/build_registry.py --dry-run  # 只看会改成什么样
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_FILE = REPO_ROOT / "registry" / "plugins.json"
GH_API = "https://api.github.com"
GH_TIMEOUT = 15.0

DYNAMIC_FIELDS = ("stars", "pushedAt", "latestSha", "refreshedAt")


def _gh_get(path: str) -> dict:
    """GitHub API GET。GITHUB_TOKEN 存在时附带（速率 60/h → 1000+/h）。"""
    url = GH_API + path
    headers = {"User-Agent": "workbuddy-market-registry-builder",
               "Accept": "application/vnd.github+json"}
    token = (os.environ.get("GITHUB_TOKEN") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=GH_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def refresh_entry(entry: dict, fetch, ref_fetch=None) -> dict:
    """单条刷新（纯函数，自检直接测）：fetch(repo) → 更新动态字段。

    fetch(repo) 返回 GitHub /repos/{repo} 的 payload（stars / pushed_at）；
    ref_fetch(repo) 可选，返回最新 commit 的 sha（/repos/{repo}/commits?per_page=1，
    列表首项）—— /repos 端点本身不给 sha，所以拆成两个函数，各自好测。
    fetch 抛异常时原样上抛（调用方记失败、保旧值）；返回**新 dict**，
    不改传入对象 —— 便于对比与测试。
    """
    data = fetch(entry["repo"])
    if not isinstance(data, dict) or not data.get("full_name"):
        raise ValueError(f"GitHub 返回缺 full_name：{entry['repo']}")
    out = dict(entry)
    out["stars"] = int(data.get("stargazers_count") or 0)
    out["pushedAt"] = (data.get("pushed_at") or "")[:10]
    out["latestSha"] = ""
    if ref_fetch is not None:
        try:
            commits = ref_fetch(entry["repo"])
            if isinstance(commits, list) and commits and isinstance(commits[0], dict):
                out["latestSha"] = str(commits[0].get("sha") or "")[:40]
        except Exception:            # noqa: BLE001 —— sha 只是展示字段，拿不到就算了
            pass
    out["refreshedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return out


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description="刷新 registry/plugins.json 的动态字段")
    ap.add_argument("--dry-run", action="store_true",
                    help="只打印将发生的变更，不写回文件")
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")   # Windows runner 的 ANSI 代码页
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    raw = REGISTRY_FILE.read_bytes()
    doc = json.loads(raw.decode("utf-8"))
    if doc.get("schema") != 1 or not isinstance(doc.get("plugins"), list):
        print(f"!! {REGISTRY_FILE} 形状不对（schema/plugins）", file=sys.stderr)
        return 2

    changed = failed = 0
    out_entries = []
    # refresh_entry 的 fetch 契约是「收 repo 名」；_gh_get 是「收 API 路径」，
    # 必须在这里包一层 —— 直接传 _gh_get 会拼出 api.github.comanthropics/skills
    # 这种坏主机名（代理表现为 Tunnel 502，极难排查）。
    fetch_repo = lambda r: _gh_get(f"/repos/{r}")          # noqa: E731
    ref_repo = lambda r: _gh_get(f"/repos/{r}/commits?per_page=1")  # noqa: E731
    for entry in doc["plugins"]:
        repo = entry.get("repo", "?")
        try:
            new_e = refresh_entry(entry, fetch_repo, ref_fetch=ref_repo)
            if new_e != entry:
                changed += 1
            diff = " ".join(f"{k}={new_e[k]}" for k in DYNAMIC_FIELDS)
            print(f"  ok  {repo}: {diff}")
            out_entries.append(new_e)
        except Exception as exc:  # noqa: BLE001 —— 单条失败保旧值
            failed += 1
            print(f"  !!  {repo}: {type(exc).__name__}: {exc}", file=sys.stderr)
            out_entries.append(entry)

    doc["plugins"] = out_entries
    doc["updatedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"

    if args.dry_run:
        print(f"\n[dry-run] {changed} 条会更新，{failed} 条失败，文件未写。")
        return 1 if (failed and changed == 0) else 0

    if changed == 0 and failed == 0:
        print("\n全部条目无变化，不写盘。")
        return 0

    # 原子写：临时文件同目录 + os.replace（同卷 rename 原子）
    fd, tmp = tempfile.mkstemp(dir=str(REGISTRY_FILE.parent),
                               suffix=".tmp", prefix=".plugins-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, REGISTRY_FILE)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    print(f"\n已写回 {REGISTRY_FILE}（更新 {changed} 条，失败 {failed} 条）。")
    return 1 if (failed and changed == 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
