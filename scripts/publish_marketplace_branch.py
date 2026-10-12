# -*- coding: utf-8 -*-
"""publish_marketplace_branch —— 把精选市场快照发布成原生 git 市场（v2.30 新增）。

产品定位：**一键入口**。blatwo/workbuddy-marketplace 验证了原生市场仓库
的安装体验：仓库根放 .codebuddy-plugin/marketplace.json，用户一条
`/plugin marketplace add <git-url>#marketplace` 即接入，零下载、零
Python、支持 marketplace update 自动刷新。本脚本把每日构建的
workbuddy-marketplace.zip（同一份 sourceCommit 固定的审核快照）原样
发布到本仓库的 `marketplace` 分支，与 zip 渠道共享同一内容契约：

  · 插件内容仍只来自 registry/plugins.json 固定 sourceCommit 的快照，
    不引用上游 HEAD —— 原生 github-source 会装漂移的上游，违背供应链
    口径，故不用；
  · 与 zip 唯一区别是分发介质（git 分支 vs zip 附件），取舍说明同 README。

幂等：先比对新旧 tree hash，内容没变就不推（避免每日空转产生 git 噪音）。

用法（CI 内）：

    REGISTRY_PAT=... python scripts/publish_marketplace_branch.py \
        --zip dist/workbuddy-marketplace.zip \
        --repo zjs105910/workbuddy-market --branch marketplace
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")   # CI runner 管道非 UTF-8（踩坑 #33）
    sys.stderr.reconfigure(encoding="utf-8")

BRANCH_README = """# WorkBuddy Community Marketplace（自动发布分支）

本分支是 [WorkBuddy Market](https://github.com/zjs105910/workbuddy-market)
精选社区市场的 **原生 git 市场快照**，由 CI 每日从人工审核的
`registry/plugins.json` 自动重建，内容与
[`marketplace` Release](https://github.com/zjs105910/workbuddy-market/releases/tag/marketplace)
的 zip 完全同源。

## 一键接入（CodeBuddy Code / WorkBuddy）

```
/plugin marketplace add https://github.com/zjs105910/workbuddy-market.git#marketplace
```

然后 `/plugin` 浏览，或：

```
/plugin install <插件名>@workbuddy-community-market
```

## 取舍说明

这条路是**技能分发快照**：按审核固定的 sourceCommit 生成，不含安装前四问、
所有权分级与可恢复卸载。要完整安全链路请用完整版 WorkBuddy Market。
勿直接改本分支任何文件——每日重建会覆盖；收录建议请给主仓库提 issue/PR。
"""


def run_git(args: list[str], cwd: Path | None = None,
            env_token: str | None = None, repo: str | None = None) -> str:
    """跑 git 子进程；给 clone/push 时把 token 注入 URL（不落盘、不回显）。"""
    cmd = ["git", *args]
    if env_token and repo:
        cmd = [a.replace(f"https://github.com/{repo}",
                         f"https://x-access-token:{env_token}@github.com/{repo}")
               for a in cmd]
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:2])} 失败: {p.stderr.strip()[-400:]}")
    return p.stdout.strip()


def extract_zip(zip_path: Path, dest: Path) -> dict:
    """解包 zip 到目标目录（剥掉单层包装目录），返回 marketplace.json 摘要。"""
    with zipfile.ZipFile(zip_path) as zf:
        if zf.testzip() is not None:
            raise ValueError("zip 损坏，拒绝发布")
        names = zf.namelist()
        if not any(n == ".codebuddy-plugin/marketplace.json" for n in names):
            raise ValueError("zip 里没有 .codebuddy-plugin/marketplace.json，不是市场快照")
        zf.extractall(dest)
    manifest = json.loads(
        (dest / ".codebuddy-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    return manifest


def tree_of(repo_dir: Path, ref: str) -> str | None:
    """取某 ref 的 tree hash；ref 不存在返回 None。"""
    p = subprocess.run(
        ["git", "rev-parse", f"{ref}^{{tree}}"], cwd=repo_dir,
        capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else None


def needs_push(new_tree: str, old_tree: str | None) -> bool:
    """内容没变就不推（幂等）。"""
    return old_tree != new_tree


def publish(zip_path: Path, repo: str, branch: str, token: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="mktbranch-") as td:
        work = Path(td) / "work"
        work.mkdir()
        manifest = extract_zip(zip_path, work)
        (work / "README.md").write_text(BRANCH_README, encoding="utf-8")

        run_git(["init", "-q", "-b", branch, "."], cwd=work)
        run_git(["config", "user.name", "workbuddy-market CI"], cwd=work)
        run_git(["config", "user.email",
                 "328969776+zjs105910@users.noreply.github.com"], cwd=work)
        run_git(["add", "-A"], cwd=work)
        msg = (f"marketplace snapshot: {manifest.get('builtAt', 'unknown')} "
               f"({len(manifest.get('included', []))} plugins)")
        run_git(["commit", "-q", "-m", msg], cwd=work)
        new_tree = run_git(["rev-parse", "HEAD^{tree}"], cwd=work)

        base = f"https://github.com/{repo}"
        try:
            run_git(["fetch", "--depth", "1", base, branch], cwd=work,
                    env_token=token, repo=repo)
            old_tree = tree_of(work, "FETCH_HEAD")
        except RuntimeError:
            # 首次发布：分支还不存在，fetch 失败属预期，旧树视为 None
            old_tree = None
        if not needs_push(new_tree, old_tree):
            return {"pushed": False, "reason": "内容与远端一致，跳过",
                    "plugins": len(manifest.get("included", []))}
        run_git(["push", "--force", base, f"HEAD:refs/heads/{branch}"],
                cwd=work, env_token=token, repo=repo)
        return {"pushed": True, "oldTree": (old_tree or "none")[:12],
                "newTree": new_tree[:12],
                "plugins": len(manifest.get("included", [])),
                "excluded": len(manifest.get("excluded", [])),
                "commit": msg}


def main() -> int:
    ap = argparse.ArgumentParser(description="发布精选市场快照到原生市场分支")
    ap.add_argument("--zip", required=True, type=Path, help="构建好的 marketplace zip")
    ap.add_argument("--repo", required=True, help="owner/repo")
    ap.add_argument("--branch", default="marketplace")
    ap.add_argument("--token-env", default="REGISTRY_PAT",
                    help="token 所在环境变量名（默认 REGISTRY_PAT）")
    args = ap.parse_args()

    token = __import__("os").environ.get(args.token_env, "")
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", args.repo):
        print(f"::error::repo 形态非法: {args.repo!r}")
        return 2
    if not token:
        print(f"::error::环境变量 {args.token_env} 为空——没有 token 就没有分发渠道，"
              "如实失败而不是静默跳过")
        return 2
    if not args.zip.is_file():
        print(f"::error::zip 不存在: {args.zip}")
        return 2

    result = publish(args.zip, args.repo, args.branch, token)
    print(json.dumps(result, ensure_ascii=False, indent=1))
    if result.get("pushed"):
        print(f"已发布：/plugin marketplace add "
              f"https://github.com/{args.repo}.git#{args.branch}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
