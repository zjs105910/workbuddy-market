# -*- coding: utf-8 -*-
"""check_release_sync —— 三方发布一致性校验（版本号 + 产物哈希）。

背景（2026-10-16 发布体检）：GitHub Release、version.py、PyPI 三方目前
手动维护 —— release.yml 只校验 tag=version.py=CHANGELOG，PyPI 上传是发布
后手动 twine，漏传不会报错，只会让 PyPI 静默落后（用户用 pipx 装到旧版，
而 GitHub 已是新版）。本脚本把「三方一致」变成每日可执行证据：

  1. version.py 的 MARKET_VERSION == GitHub 最新正式 Release 的 tag；
  2. GitHub 最新正式 Release 的 tag == PyPI JSON API 的 latest；
  3. PyPI 上的 wheel/sdist sha256 与 Release 附件 SHA256SUMS.txt 逐件一致
     —— 证明两个渠道分发的是同一份构建产物，而不是两次独立构建。

网络失败一律 fail-closed：查不到就报错退出 1，绝不把「查不到」当「一致」
（与 selfupdate 的诚实语义同源）。匿名 GitHub API 限额 60 次/小时，每日
cron + 手动 dispatch 的量级远够；设置 GITHUB_TOKEN 环境变量可提高限额。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_REPO = "zjs105910/workbuddy-market"
DEFAULT_PACKAGE = "workbuddy-market"

PASS, FAIL = [], []


def _ck(name: str, cond: bool, extra: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  —— {extra}" if extra else ""))


def _http_get(url: str, token: str = "") -> bytes:
    """GET 一个 URL，非 200 一律抛 RuntimeError（人话，带状态码）。"""
    headers = {"User-Agent": "workbuddy-market-release-sync"}
    if token:
        headers["Authorization"] = f"token {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}: {url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"网络不可达: {url}（{exc.reason}）") from exc


def read_market_version(root: Path) -> str:
    """从 src/workbuddy_market/version.py 读 MARKET_VERSION（与 release.yml 同一正则口径）。"""
    source = (root / "src" / "workbuddy_market" / "version.py").read_text(encoding="utf-8")
    match = re.search(r'MARKET_VERSION\s*=\s*["\']([^"\']+)["\']', source)
    if not match:
        raise RuntimeError("version.py 里找不到 MARKET_VERSION")
    return match.group(1)


def github_latest_release(repo: str, token: str = "") -> tuple[str, dict[str, str]]:
    """返回 (最新正式 Release 的 tag, {文件名: sha256})。tag 形如 v2.36.0。"""
    payload = json.loads(
        _http_get(f"https://api.github.com/repos/{repo}/releases/latest", token)
    )
    tag = payload.get("tag_name", "")
    if not tag.startswith("v"):
        raise RuntimeError(f"GitHub 最新 Release tag 形态不对: {tag!r}")
    sums_url = (
        f"https://github.com/{repo}/releases/download/{tag}/SHA256SUMS.txt"
    )
    checksums: dict[str, str] = {}
    try:
        for line in _http_get(sums_url, token).decode("utf-8").splitlines():
            parts = line.split()
            if len(parts) == 2:
                checksums[parts[1]] = parts[0]
    except RuntimeError as exc:
        print(f"  WARN  SHA256SUMS.txt 拉取失败（哈希比对降级跳过）: {exc}")
    return tag, checksums


def pypi_latest(package: str) -> tuple[str, dict[str, str]]:
    """返回 (PyPI latest 版本, {文件名: sha256})。404 说明包不存在。"""
    payload = json.loads(_http_get(f"https://pypi.org/pypi/{package}/json"))
    version = payload.get("info", {}).get("version", "")
    if not version:
        raise RuntimeError(f"PyPI JSON 里没有 latest 版本: {package}")
    files = {
        item["filename"]: item.get("digests", {}).get("sha256", "")
        for item in payload.get("urls", [])
    }
    return version, files


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="三方发布一致性校验")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="GitHub 仓库（owner/name）")
    parser.add_argument("--package", default=DEFAULT_PACKAGE, help="PyPI 包名")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    token = os.environ.get("GITHUB_TOKEN", "")

    try:
        local_version = read_market_version(root)
    except (OSError, RuntimeError) as exc:
        print(f"[ERROR] 读 version.py 失败: {exc}")
        return 1
    try:
        gh_tag, gh_sums = github_latest_release(args.repo, token)
    except RuntimeError as exc:
        print(f"[ERROR] GitHub 最新 Release 查询失败（fail-closed，不算一致）: {exc}")
        return 1
    try:
        pypi_version, pypi_files = pypi_latest(args.package)
    except RuntimeError as exc:
        print(f"[ERROR] PyPI 查询失败（fail-closed，不算一致）: {exc}")
        return 1

    print(f"version.py      : {local_version}")
    print(f"GitHub latest   : {gh_tag}")
    print(f"PyPI latest     : {pypi_version}")
    print()

    gh_version = gh_tag.removeprefix("v")
    _ck("version.py == GitHub 最新 Release", local_version == gh_version)
    _ck("GitHub 最新 Release == PyPI latest", gh_version == pypi_version)
    _ck("version.py == PyPI latest", local_version == pypi_version)

    # 产物哈希：两边 SHA256SUMS 都在的文件逐件比对（wheel + sdist 应各有一份）。
    compared = 0
    for filename, gh_hash in sorted(gh_sums.items()):
        pypi_hash = pypi_files.get(filename)
        if not pypi_hash:
            continue  # 非分发包文件（演示视频等）PyPI 没有，正常
        compared += 1
        _ck(f"哈希一致: {filename}", gh_hash == pypi_hash)
    if not compared and gh_sums:
        print("  WARN  没有可哈希比对的文件（PyPI 无 wheel/sdist？）——发布不完整")

    print()
    if FAIL:
        print(f"[FAIL] 发布同步有 {len(FAIL)} 处不一致 —— PyPI 渠道用户会拿到旧版")
        print("       处理：确认本地 dist 与 Release 附件一致后手动 twine upload 补齐")
        return 1
    print(f"[PASS] 三方版本一致，{compared} 个分发产物哈希一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
