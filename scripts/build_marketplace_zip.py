# -*- coding: utf-8 -*-
"""build_marketplace_zip —— 把社区注册表组装成 WorkBuddy 原生 zip 市场（v2.27 新增）。

产品定位：**轻量入口**。让 WorkBuddy 用户不改任何配置、不装 Python，
直接在插件面板添加一个 zip 市场 URL 就能用上精选收录的社区技能。
它不替代本市场本体 —— 走这条路的用户拿不到安装前四问 / 所有权分级 /
事务回收站，README 已明示这一取舍。

内容口径（隐私红线）：

  · 插件内容**只**来自 registry/plugins.json 的收录条目（按审核固定的
    sourceCommit 拉上游 tarball），绝不打包任何本机 plugins/ 或个人 skill；
  · 复用 build_artifacts 的网络接缝（_tarball_fetch）与安全解包
    （safe_extract_tar / choose_skills_root），不另开网络口子；
  · 单条失败只记录、不拖垮整批；全部失败才非零退出。

用法：

    python scripts/build_marketplace_zip.py --out dist/workbuddy-marketplace.zip
    python scripts/build_marketplace_zip.py --limit 3 --out dist/smoke.zip   # 冒烟
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")   # CI runner 管道非 UTF-8（踩坑 #33）
    sys.stderr.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from workbuddy_market.version import MARKET_VERSION  # noqa: E402

DEFAULT_REGISTRY_FILE = REPO_ROOT / "registry" / "plugins.json"

# 复用 build_artifacts 的接缝（单一事实来源，不复制网络/解包代码）
_spec = importlib.util.spec_from_file_location(
    "build_artifacts", REPO_ROOT / "scripts" / "build_artifacts.py")
_ba = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ba)

MARKET_NAME = "workbuddy-community-market"
MARKET_DESCRIPTION = (
    "WorkBuddy Market 精选社区市场（只读快照）：全部条目来自人工审核的 "
    "registry/plugins.json，按 sourceCommit 固定来源。想要安装前四问、"
    "所有权分级与可恢复卸载，请使用完整版 WorkBuddy Market。")


def plugin_slug(repo: str, taken: set[str]) -> str:
    """repo → 合法插件目录名；撞名时加 owner 前缀。"""
    slug = _ba.slug_for(repo)
    if slug in taken:
        owner = repo.split("/")[0]
        slug = f"{owner}-{slug}"
    n = 2
    base = slug
    while slug in taken:
        slug = f"{base}-{n}"
        n += 1
    taken.add(slug)
    return slug


def _fetch_with_retry(url: str, attempts: int = 4) -> bytes:
    """直连/代理都可能抖（10054 / 10060 / 10061），指数退避重试。"""
    last: Exception | None = None
    for i in range(attempts):
        try:
            return _ba._tarball_fetch(url)
        except Exception as exc:
            last = exc
            if i + 1 < attempts:
                time.sleep(2 ** i)
    raise last  # type: ignore[misc]


def build_marketplace(registry_file: Path, out_zip: Path,
                      limit: int | None = None,
                      max_plugin_bytes: int = 30 * 1024 * 1024) -> dict:
    registry = json.loads(registry_file.read_text(encoding="utf-8"))
    entries = registry.get("plugins") or []
    if limit:
        entries = entries[:limit]
    if not entries:
        raise SystemExit("注册表里没有条目，拒绝构建空市场")

    now = datetime.now(timezone.utc)
    staging = out_zip.parent / f".{out_zip.stem}.staging"
    if staging.exists():
        shutil.rmtree(staging)
    (staging / ".codebuddy-plugin").mkdir(parents=True)

    built: list[dict] = []
    failed: list[str] = []
    taken: set[str] = set()

    for i, entry in enumerate(entries, 1):
        repo = entry.get("repo") or ""
        commit = entry.get("sourceCommit") or ""
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo) or not commit:
            failed.append(f"{repo or '?'}: 缺 repo/sourceCommit")
            continue
        try:
            # 拉取 + 安全解包 + 选 skills 根（与产物构建同一套纪律）
            url = f"https://github.com/{repo}/archive/{commit}.tar.gz"
            tar_bytes = _fetch_with_retry(url)
            tmp_tar = staging.parent / f".mktar-{i}.tgz"
            tmp_tar.write_bytes(tar_bytes)
            try:
                extract_root = _ba.safe_extract_tar(tmp_tar, staging.parent / f".mkext-{i}")
                skills_root, skills = _ba.choose_skills_root(extract_root, repo)
                if not skills:
                    raise ValueError("未找到任何 SKILL.md")
                slug = plugin_slug(repo, taken)
                dest = staging / "plugins" / slug
                dest.parent.mkdir(parents=True, exist_ok=True)
                version = _ba.fallback_version(commit, now)
                shutil.copytree(skills_root, dest / "skills")
                # 体积闸门：zip 市场是给 WorkBuddy 直接下载的，单个插件超大
                # 会拖垮整个市场（首版曾因个别大仓库整包 878MB）。超限即剔除
                # 并如实记录，不静默裁剪内容。
                used = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file())
                if used > max_plugin_bytes:
                    shutil.rmtree(dest, ignore_errors=True)
                    taken.discard(slug)
                    raise ValueError(
                        f"插件体积 {used // 1048576}MB 超过上限 "
                        f"{max_plugin_bytes // 1048576}MB，已剔除")
                (dest / ".codebuddy-plugin").mkdir()
                plugin_json = {
                    "name": slug,
                    "version": version,
                    "description": entry.get("description") or entry.get("displayName") or repo,
                    "description_en": entry.get("descriptionEn"),
                    "author": {"name": repo.split("/")[0]},
                    "keywords": entry.get("keywords") or [],
                    "category": entry.get("category") or "社区",
                    "license": entry.get("license"),
                    "homepage": entry.get("homepage") or f"https://github.com/{repo}",
                    "sourceCommit": commit,
                }
                plugin_json = {k: v for k, v in plugin_json.items() if v}
                (dest / ".codebuddy-plugin" / "plugin.json").write_text(
                    json.dumps(plugin_json, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")
                built.append({
                    "name": slug,
                    "description": plugin_json["description"],
                    "version": version,
                    "source": f"./plugins/{slug}",
                    "category": entry.get("category") or "社区",
                    "author": {"name": repo.split("/")[0]},
                    "keywords": entry.get("keywords") or [],
                })
            finally:
                tmp_tar.unlink(missing_ok=True)
                shutil.rmtree(staging.parent / f".mkext-{i}", ignore_errors=True)
            print(f"[{i}/{len(entries)}] OK  {repo} → {slug}（{len(skills)} 个 skill）")
        except Exception as exc:  # 单条失败不拖垮整批
            failed.append(f"{repo}: {type(exc).__name__}: {exc}")
            print(f"[{i}/{len(entries)}] FAIL {repo}: {exc}")

    if not built:
        for p in sorted(staging.parent.glob(".mkext-*")):
            shutil.rmtree(p, ignore_errors=True)
        shutil.rmtree(staging, ignore_errors=True)
        raise SystemExit("全部条目构建失败，拒绝发布空市场：" + "；".join(failed[:5]))

    marketplace = {
        "name": MARKET_NAME,
        "description": MARKET_DESCRIPTION,
        "owner": {"name": "WorkBuddy Market"},
        "marketVersion": MARKET_VERSION,
        "builtAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sourceRegistry": "registry/plugins.json",
        "plugins": built,
    }
    (staging / ".codebuddy-plugin" / "marketplace.json").write_text(
        json.dumps(marketplace, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    out_zip.parent.mkdir(parents=True, exist_ok=True)
    if out_zip.exists():
        out_zip.unlink()
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(staging.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(staging).as_posix())
    shutil.rmtree(staging, ignore_errors=True)

    summary = {
        "built": len(built), "failed": len(failed),
        "sizeBytes": out_zip.stat().st_size,
        "failures": failed,
    }
    (out_zip.parent / "workbuddy-marketplace.manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"完成：{len(built)} 个插件 → {out_zip} "
          f"（{out_zip.stat().st_size // 1024} KB，失败 {len(failed)}）")
    return summary


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description="从社区注册表构建 WorkBuddy 原生 zip 市场")
    ap.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_FILE)
    ap.add_argument("--out", type=Path, default=Path("dist/workbuddy-marketplace.zip"))
    ap.add_argument("--limit", type=int, default=None, help="只构建前 N 条（冒烟用）")
    ap.add_argument("--max-plugin-mb", type=int, default=30,
                    help="单插件体积上限（MB），超限剔除并记录")
    args = ap.parse_args(argv)
    summary = build_marketplace(args.registry, args.out, args.limit,
                                args.max_plugin_mb * 1024 * 1024)
    return 0 if summary["built"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
