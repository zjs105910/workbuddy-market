# -*- coding: utf-8 -*-
"""build_artifacts —— 注册表不可变产物的批量构建 / 发布 / 回写（v2.17 新增）。

v2.16 把客户端链路做完了（registry 带 packageUrl + packageHash → 下载 →
verify → 事务安装），这一步补上**产物源**：CI 对注册表里每个收录条目，
按审核固定的 sourceCommit 构建一个 Market Package 并发布为 GitHub
Release 资产，然后把 packageUrl / packageHash / manifestHash 回写进
registry/plugins.json（走 PR，不直推 main）。

用法：

    python scripts/build_artifacts.py --out artifacts/              # 构建全部
    python scripts/build_artifacts.py --repo owner/name --out artifacts/
    python scripts/build_artifacts.py --patch-registry --out artifacts/ \
        --release-tag registry-artifacts-2026-10-08                 # 回写字段

供应链口径（与 plugin-spec 冻结决定一致）：

  · tarball 固定拉 ``sourceCommit``（审核时看的那一份），不是默认分支；
  · 构建动作本身不产生信任 —— 信任来自收录时的人工审核 + packageHash
    把那一份字节钉死；哈希由构建环境算出、发布后任何人可复验；
  · 打包遵循 packaging.pack_package 全部纪律（链接拒绝、SKILL.md 必须、
    失败清理无半截）；单个条目失败只记录失败，不拖垮整批；
  · 回写一律走 PR —— 注册表的静态 / 产物字段永远人工可审。

v2.35 NEXT_STEPS 任务4（打包瘦身，影响评估见 CHANGELOG 2.35.0）：

  · 瘦身暂存（stage_clean）：只带 manifest 声明的 skills，剔除 VCS 元数据 /
    语言与测试缓存 / 系统垃圾（``_JUNK_*``）—— 不参与 skill 运行时的内容
    不进产物；node_modules/.venv 刻意不剔（vendor 依赖是内容，剔了即破坏），
    真大到离谱交给体积闸门；
  · 体积闸门（ARTIFACT_MAX_BYTES=64MB）：超限条目拒发固定工件
    （report.excluded，非失败），--patch-registry 拔掉其工件指针字段，
    安装回落 ghpm 源码路线（与 pkg=N 条目同路径）；闸门下的旧制品
    安装行为逐字节不变。

网络接缝只有一个：``_tarball_fetch(url)``（自检 monkeypatch 它离线测）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import tarfile
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from workbuddy_market.config import validate_id, validate_version  # noqa: E402
from workbuddy_market.packaging import (                           # noqa: E402
    ATTESTATION_SCHEMA_VERSION, ATTESTATION_TYPE, pack_package)
from workbuddy_market.registry import REGISTRY_REPO                # noqa: E402
from workbuddy_market.version import MARKET_VERSION                # noqa: E402

DEFAULT_REGISTRY_FILE = REPO_ROOT / "registry" / "plugins.json"
TARBALL_TIMEOUT = 120.0
DOWNLOAD_CHUNK = 1024 * 1024
MAX_TARBALL_BYTES = 256 * 1024 * 1024        # 与 artifact.py 同一量级上限

# ---------------------------------------------------------------- 打包瘦身
# v2.35 NEXT_STEPS 任务4（影响评估实锤：21 个制品共 585MB，两个巨头
# K-Dense-AI/scientific-agent-skills 246MB、nexu-io/open-design 179MB；
# 拆包分析显示重量几乎全在 skill 目录内的图片等**内容资产**里）。
#
# 两层策略，都不动「装什么」：
#   ① 垃圾剔除（_JUNK_*）：VCS 元数据 / 语言缓存 / 测试缓存 / 系统垃圾
#      文件一律不进产物。这些**永远不参与 skill 运行时**，剔除零风险。
#      node_modules / .venv **刻意不剔**——skill 若 vendor 了依赖，
#      剔了就是破坏内容；真大到离谱交给 ② 的体积闸门说话。
#   ② 体积闸门（ARTIFACT_MAX_BYTES）：产物超限的条目**拒绝发布固定
#      工件**（记进 report.excluded，不是失败），注册表拔掉工件指针，
#      安装回落 ghpm 源码路线（与 14 个 pkg=N 条目同一路径，UI 已有
#      「无固定产物」引导，任务5）。旧制品（低于闸门）安装行为不变。
_JUNK_DIRS = {".git", ".hg", ".svn",
              "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
              ".tox", ".ipynb_checkpoints", "coverage"}
_JUNK_FILES = {".ds_store", "thumbs.db", "desktop.ini"}
_JUNK_SUFFIXES = (".pyc", ".pyo", ".log", ".tmp")

ARTIFACT_MAX_BYTES = 64 * 1024 * 1024        # 工件体积上限（超过走 ghpm 路线）


class ArtifactOversized(Exception):
    """产物超过体积闸门（任务4）：策略性拒发，不是构建失败。"""


def _junk_ignore(src, names: list):
    """shutil.copytree 的 ignore 回调（签名 (src, names)）：返回要剔除的名字集合。"""
    drop = set()
    for n in names:
        low = n.lower()
        if n in _JUNK_DIRS or low in _JUNK_DIRS:
            drop.add(n)
        elif n in _JUNK_FILES or low in _JUNK_FILES:
            drop.add(n)
        elif low.endswith(_JUNK_SUFFIXES):
            drop.add(n)
    return drop


def _tree_bytes(path) -> int:
    return sum(p.stat().st_size for p in Path(path).rglob("*") if p.is_file())


def stage_clean(src, skills, dest) -> dict:
    """瘦身暂存（任务4）：``src/skills/<name>`` → ``dest/skills/<name>``。

    只带声明的 skills（manifest 之外的非 skill 内容——仓库级 README、
    示例、宣传图——本来就不会被安装端解包，不进产物），并剔除
    ``_JUNK_*`` 垃圾。剔除量如实返回，由 build_one 记进 report。
    """
    import shutil
    from workbuddy_market.errors import ConfigError
    src, dest = Path(src), Path(dest)
    shutil.rmtree(dest, ignore_errors=True)
    (dest / "skills").mkdir(parents=True)
    stats = {"excludedFiles": 0, "excludedBytes": 0}
    for name in skills:
        s = src / "skills" / name
        if not s.is_dir():
            raise ConfigError(f"skill {name!r} 在 {s} 不存在，拒绝打包")
        # 先按同一把尺算出顶层要剔的名字，用于如实统计 —— copytree 只
        # 返回目标路径，拿不到剔除清单，只能自己算（递归层由 ignore 兜底）。
        for ig in _junk_ignore(s, [p.name for p in s.iterdir()]):
            junk = s / ig
            if junk.is_file():
                stats["excludedFiles"] += 1
                stats["excludedBytes"] += junk.stat().st_size
            else:
                for p in junk.rglob("*"):
                    if p.is_file():
                        stats["excludedFiles"] += 1
                        stats["excludedBytes"] += p.stat().st_size
        shutil.copytree(s, dest / "skills" / name, symlinks=True,
                        ignore=_junk_ignore)
    return stats

_SKILL_MD = "SKILL.md"


# ---------------------------------------------------------------- 接缝

def _tarball_fetch(url: str) -> bytes:
    """tarball 下载的唯一网络接缝。自检 monkeypatch 这个名字离线测。

    tarball 是构建输入不是安装输入（装的是 pack 之后验过哈希的 zip），
    所以这里一次性读入即可；大小上限仍然保留 —— 上限是防御，不是优化。
    """
    req = urllib.request.Request(url, headers={"User-Agent": "workbuddy-market-artifact-builder"})
    with urllib.request.urlopen(req, timeout=TARBALL_TIMEOUT) as resp:
        buf = bytearray()
        while True:
            chunk = resp.read(DOWNLOAD_CHUNK)
            if not chunk:
                break
            buf.extend(chunk)
            if len(buf) > MAX_TARBALL_BYTES:
                raise ValueError(f"tarball 超过大小上限（>{MAX_TARBALL_BYTES} 字节）")
        return bytes(buf)


# ---------------------------------------------------------------- 纯函数层

def safe_extract_tar(tar_path: Path, dest: Path,
                     materialized: list | None = None) -> Path:
    """安全解包 GitHub tarball（不可信输入，按攻击面处理）。

    · 成员名绝对路径 / 盘符 / ``..`` 段 → 拒绝；硬链接 / 设备成员 → 拒绝；
    · v2.35.2 起，**指向包内普通文件的相对符号链接**按「物化」处理：
      解析出最终目标文件后，把目标内容写成普通文件（产物里从此没有
      链接，安装端三层链接防线原样有效）。链式链接最多跟 8 跳；
      指向目录、悬空、成环、绝对路径、出包（``..`` 逃逸 / 盘符）的
      链接一律 fail-closed 拒绝 —— 收紧范围只这一种安全形态；
    · 自动剥掉 tarball 的第一层前缀（GitHub 恒为 ``<repo>-<ref>/``）；
    · ``materialized`` 传 list 时逐项记录 ``{"from": 链接路径, "to": 目标}``
      （调用方如实写进 report，供人工对账）；
    · 返回剥前缀后的内容根目录。
    """
    import posixpath
    import workbuddy_market.errors as werr
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    prefix = None
    members = []
    # 第一遍：全部成员先校验（任何一项非法整包拒绝，无半截状态）
    with tarfile.open(tar_path, "r:gz") as tf:
        for m in tf:
            name = m.name.replace("\\", "/")
            if name.startswith("/") or re.match(r"^[A-Za-z]:", name) or ".." in name.split("/"):
                raise werr.ArtifactError(f"tar 成员非法（路径穿越）：{name!r}")
            if m.issym():
                ln = m.linkname.replace("\\", "/")
                # 这里只拒绝对路径 / 盘符（任何上下文都不可物化）；
                # 含 ``..`` 的相对链接放行到解析阶段 —— 以成员目录为
                # 基准归一化后仍在包内的（docs/../guide.md 这类）是合法形态。
                if ln.startswith("/") or re.match(r"^[A-Za-z]:", ln):
                    raise werr.ArtifactError(
                        f"tar 符号链接目标不在包内（fail-closed）：{name!r} -> {m.linkname!r}")
            elif not (m.isfile() or m.isdir()):
                raise werr.ArtifactError(f"tar 含硬链接 / 设备等非常规成员：{name!r}")
            seg = name.split("/", 1)[0]
            if prefix is None:
                prefix = seg
            elif name != prefix and not name.startswith(prefix + "/"):
                raise werr.ArtifactError(f"tar 存在多个顶层前缀：{seg!r} vs {prefix!r}")
            members.append(m)
    if prefix is None:
        raise werr.ArtifactError("tarball 是空的")

    # 剥前缀视图：普通文件与符号链接分别建表，供链接解析
    file_rels: dict = {}
    sym_rels: dict = {}
    for m in members:
        rel = m.name.replace("\\", "/")
        if rel == prefix:
            continue
        rel = rel[len(prefix) + 1:] if rel.startswith(prefix + "/") else rel
        if m.isfile():
            file_rels[rel] = m
        elif m.issym():
            sym_rels[rel] = m.linkname.replace("\\", "/")

    def _resolve_link(rel: str) -> tuple:
        """解析包内文件符号链接 → 最终普通文件成员；解析不到就拒绝。"""
        cur, seen, hops = rel, set(), 0
        while cur in sym_rels:
            hops += 1
            if hops > 8:
                raise werr.ArtifactError(f"tar 符号链接链过长（>8 跳）：{rel!r}")
            if cur in seen:
                raise werr.ArtifactError(f"tar 符号链接成环：{rel!r}")
            seen.add(cur)
            nxt = posixpath.normpath(
                posixpath.join(posixpath.dirname(cur), sym_rels[cur])).replace("\\", "/")
            if (nxt.startswith("/") or re.match(r"^[A-Za-z]:", nxt)
                    or nxt.startswith("../")):
                raise werr.ArtifactError(
                    f"tar 符号链接解析后出包（fail-closed）：{rel!r} -> {cur!r}")
            cur = nxt
        if cur in file_rels:
            return cur, file_rels[cur]
        raise werr.ArtifactError(
            f"tar 符号链接指向目录或缺失目标，无法物化（fail-closed）：{rel!r}")

    resolved: dict = {rel: _resolve_link(rel) for rel in sym_rels}

    # 第二遍：解包（TarFile 不支持 seek，重新打开同一个文件即可）
    with tarfile.open(tar_path, "r:gz") as tf:
        for m in members:
            rel = m.name.replace("\\", "/")
            if rel == prefix:
                continue
            if rel.startswith(prefix + "/"):
                rel = rel[len(prefix) + 1:]
            else:
                raise werr.ArtifactError(f"tar 成员不在顶层前缀下：{m.name!r}")
            target = dest / rel
            if m.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if m.issym():
                # v2.35.2：物化 —— 写目标文件的内容，不留链接
                src_rel, src_m = resolved[rel]
                src = tf.extractfile(src_m)
                if src is None:
                    raise werr.ArtifactError(f"tar 链接目标读不出：{src_rel!r}")
                with target.open("wb") as dst:
                    while True:
                        chunk = src.read(DOWNLOAD_CHUNK)
                        if not chunk:
                            break
                        dst.write(chunk)
                if materialized is not None:
                    materialized.append({"from": rel, "to": src_rel})
                continue
            src = tf.extractfile(m)
            if src is None:
                raise werr.ArtifactError(f"tar 成员读不出：{m.name!r}")
            with target.open("wb") as dst:
                while True:
                    chunk = src.read(DOWNLOAD_CHUNK)
                    if not chunk:
                        break
                    dst.write(chunk)
    return dest


def choose_skills_root(root: Path, slug_hint: str) -> tuple[Path, list[str]]:
    """在解包后的 repo 内容里定位「可打包的 skills 根」。

    三种收录形态（与注册表收录标准一致）：

      a. ``root/skills/<name>/SKILL.md`` → (root, [names])；
      b. root 的子目录各自含 SKILL.md → 组 staging/skills/ 再打包；
      c. root 本身就是一个 skill（root/SKILL.md）→ staging/skills/<slug>；
      d. 嵌套合集（v2.35.2）：``<dir>/skills/<name>/SKILL.md`` —— 上游把
         skills 挂在自己插件的 skills/ 子目录下（wshobson/agents 的
         ``plugins/*/skills/*``），收全部命中的 skill 组 staging 打包，
         跨插件同名按父目录名消歧。

    都不是 → ConfigError（这个条目不满足打包形态，如实记录失败）。
    """
    from workbuddy_market.errors import ConfigError
    root = Path(root)
    sdir = root / "skills"
    if sdir.is_dir():
        names = sorted(d.name for d in sdir.iterdir()
                       if d.is_dir() and not d.is_symlink() and (d / _SKILL_MD).is_file())
        if names:
            return root, names
    sub_skills = sorted(d.name for d in root.iterdir()
                        if d.is_dir() and not d.is_symlink() and (d / _SKILL_MD).is_file())
    if sub_skills:
        staging = root.parent / f"{root.name}-staging"
        staging.mkdir(parents=True, exist_ok=True)
        (staging / "skills").mkdir(exist_ok=True)
        import shutil
        for name in sub_skills:
            shutil.copytree(root / name, staging / "skills" / name, symlinks=True)
        return staging, sub_skills
    if (root / _SKILL_MD).is_file():
        single = re.sub(r"[^A-Za-z0-9._-]+", "-", slug_hint).strip("-") or "skill"
        staging = root.parent / f"{root.name}-staging"
        import shutil
        shutil.rmtree(staging, ignore_errors=True)
        (staging / "skills" / single).parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(root, staging / "skills" / single, symlinks=True)
        return staging, [single]
    # d. 嵌套合集（v2.35.2）：任何 ``<dir>/skills/<name>/SKILL.md``。
    #    注意这是内容质量敏感的贪心收集（示例目录也会进包）—— 由收录
    #    人工审核 + 64MB 体积闸门兜底，构建侧不做语义筛选。
    import shutil
    nested = sorted({d.parent for d in root.rglob(_SKILL_MD)
                     if d.is_file() and d.parent.parent.name == "skills"})
    if nested:
        staging = root.parent / f"{root.name}-staging"
        shutil.rmtree(staging, ignore_errors=True)
        (staging / "skills").mkdir(parents=True, exist_ok=True)
        used: dict = {}
        for sd in nested:
            name = sd.name
            if name in used:                      # 跨插件同名：父目录名消歧
                name = f"{sd.parent.parent.name}-{sd.name}"
            used[name] = sd
        for name, sd in used.items():
            shutil.copytree(sd, staging / "skills" / name, symlinks=True)
        return staging, sorted(used)
    raise ConfigError(f"{slug_hint}: 解包内容里找不到可打包的 skill（无 skills/、无含 SKILL.md 的子目录）")


def slug_for(repo: str) -> str:
    """repo → 合法包 id（validate_id 口径）。"""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", repo).strip("-")
    return validate_id(slug, "包 id")


def fallback_version(ref: str, now: datetime | None = None) -> str:
    """注册表条目没写 version 时的市场版本回退（v2.18）。

    评审 8：上游仓库大多没有插件语义版本，落 0.0.0 会让安装记录出现
    「version=0.0.0」这种无信息值。这里改为 ``<构建日期>.<sourceCommit 前 7 位>``
    （如 ``2026.10.08.3e2a429``）——日期给人读，短 SHA 钉死来源；
    真正的不可变身份仍然是 sourceCommit，两者不混（评审推荐口径）。
    格式过 config.validate_version（_VER_RE 接受字母数字点号，长度 18 ≤ 64）。
    """
    ts = now or datetime.now(timezone.utc)
    return f"{ts:%Y.%m.%d}.{ref[:7]}"


def zip_dir(pkg_dir: Path, zip_path: Path) -> None:
    """把 pack 好的包目录压成发布用的 zip（与 artifact.unpack_zip 的期望一致：
    相对路径、无符号链接成员）。"""
    pkg_dir, zip_path = Path(pkg_dir), Path(zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(pkg_dir.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(pkg_dir).as_posix())


# ---------------------------------------------------------------- 编排

def build_one(entry: dict, out_dir: Path, fetch=_tarball_fetch,
              work_root: Path | None = None) -> dict:
    """单个条目：下载 tarball → 解包 → 定位 skills → pack → zip。

    返回 report 条目；失败抛异常（调用方按条目记录，不拖垮整批）。
    """
    repo = entry["repo"]
    ref = str(entry.get("sourceCommit") or "").strip()
    if not ref:
        raise ValueError(f"{repo}: 没有 sourceCommit（审核固定缺失），拒绝构建不可变产物")
    slug = slug_for(repo)
    version = str(entry.get("version") or fallback_version(ref))
    validate_version(version, "包 version")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f"wbm-artifact-{slug}-")) if work_root is None else Path(work_root)
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        tar_path = tmp / "src.tar.gz"
        tar_path.write_bytes(fetch(f"https://codeload.github.com/{repo}/tar.gz/{ref}"))
        mat: list = []                      # v2.35.2：包内文件链接物化清单（如实进 report）
        root = safe_extract_tar(tar_path, tmp / "src", materialized=mat)
        src, skills = choose_skills_root(root, slug)
        # v2.35 任务4：瘦身暂存后再 pack —— 只带声明的 skills + 剔除垃圾。
        # pack_package 对 src 是全量复制，不先瘦身的话仓库级非 skill 内容
        # （README / 示例 / 宣传图）也会进 zip 和 manifest 的 files 表。
        clean = tmp / "clean"
        excluded = stage_clean(src, skills, clean)
        pkg_dir = tmp / "pkg"
        # 收录条目若人工审核过 permissions（静态字段），打包时固化进
        # manifest —— 从此它受 manifestHash 保护，改一个字都过不了 verify。
        entry_perms = entry.get("permissions")
        packed = pack_package(clean, pkg_dir, pid=slug, name=entry.get("displayName") or slug,
                              version=version,
                              description=entry.get("description", ""),
                              license=str(entry.get("license") or ""),
                              skills=skills,
                              permissions=entry_perms if isinstance(entry_perms, dict) else None,
                              source={"type": "github", "repo": repo, "ref": ref})
        asset = f"{slug}-{version}.zip"
        zip_path = out_dir / asset
        zip_dir(pkg_dir, zip_path)
        # v2.35 任务4：体积闸门。超限条目**不发布固定工件**——抛
        # ArtifactOversized（main 记进 report.excluded，注册表拔指针，
        # 安装回落 ghpm 源码路线）。已落盘的 zip 必须删掉，否则会被
        # workflow 的 artifacts/*.zip 通配上传（拒发 ≠ 留在发布清单里）。
        zip_bytes = zip_path.stat().st_size
        if zip_bytes > ARTIFACT_MAX_BYTES:
            zip_path.unlink(missing_ok=True)
            raise ArtifactOversized(
                f"{repo}: 产物 {zip_bytes / 1048576:.1f} MB 超过上限 "
                f"{ARTIFACT_MAX_BYTES / 1048576:.0f} MB，拒绝发布固定工件"
                "（安装走 ghpm 源码路线）")
        # 构建证明（v2.20 / plugin-spec v0.3）：把「谁、按哪份 commit、
        # 构建出了哪个哈希」钉成随 Release 分发的 JSON 记录。v0.1 不带
        # 签名（冻结决定 #3 的 signature 位预留）—— 防篡改仍由安装端
        # 逐包 packageHash 校验承担，attestation 的价值是**可对账**。
        attestation = {
            "schemaVersion": ATTESTATION_SCHEMA_VERSION,
            "type": ATTESTATION_TYPE,
            "package": asset,
            "packageHash": packed["packageHash"],
            "manifestHash": packed["manifest"]["integrity"]["manifest"],
            "version": version,
            "source": {"type": "github", "repo": repo, "ref": ref},
            "builder": {"tool": "workbuddy-market", "toolVersion": MARKET_VERSION,
                        "entrypoint": "scripts/build_artifacts.py"},
            "builtAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        att_name = f"{asset}.attestation.json"
        (out_dir / att_name).write_text(
            json.dumps(attestation, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8", newline="\n")
        manifest = packed["manifest"]
        return {"repo": repo, "slug": slug, "version": version,
                "sourceCommit": ref,
                "packageHash": packed["packageHash"],
                "manifestHash": manifest["integrity"]["manifest"],
                "asset": asset, "attestationFile": att_name,
                "permissions": manifest.get("permissions") or {},
                "platforms": manifest.get("platforms") or [],
                "minWorkBuddyVersion": manifest.get("minWorkBuddyVersion") or "",
                "skills": skills,
                "bytes": zip_path.stat().st_size,
                # v2.35 任务4：瘦身剔除量如实记进 report（剔了什么、多少字节）
                "excluded": excluded,
                # v2.35.2：包内文件符号链接物化清单（构建期决
                # 策可对账；产物里从此没有链接，安装端防线不变）
                "materializedLinks": mat}
    finally:
        import shutil
        if work_root is None:
            shutil.rmtree(tmp, ignore_errors=True)


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description="构建注册表条目的不可变 artifact")
    ap.add_argument("--out", default="artifacts", help="产物输出目录（默认 artifacts/）")
    ap.add_argument("--registry", default=str(DEFAULT_REGISTRY_FILE))
    ap.add_argument("--repo", action="append", default=[],
                    help="只构建指定 repo（可多次）")
    ap.add_argument("--only-missing", action="store_true",
                    help="跳过已带 packageHash 的条目")
    ap.add_argument("--patch-registry", action="store_true",
                    help="把 artifacts/report.json 的哈希回写进 plugins.json")
    ap.add_argument("--release-tag", default="",
                    help="回写时的 Release tag（决定 packageUrl）")
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    out_dir = Path(args.out)
    report_path = out_dir / "report.json"

    if args.patch_registry:
        if not args.release_tag:
            print("!! --patch-registry 需要 --release-tag", file=sys.stderr)
            return 2
        report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {"built": []}
        built = {b["repo"]: b for b in report.get("built", [])}
        # v2.35 任务4：体积超限拒发的条目（report.excluded）拔掉工件指针
        # 字段 —— 注册表不再指认超大工件，安装回落 ghpm 源码路线（与
        # pkg=N 条目同一路径，UI 有「无固定产物」引导）。旧制品资产
        # 仍留在 Release 里可下载，只是不再被注册表指认。
        oversized = {x["repo"] for x in report.get("excluded", [])}
        reg_path = Path(args.registry)
        doc = json.loads(reg_path.read_text(encoding="utf-8"))
        patched = stripped = 0
        for entry in doc.get("plugins", []):
            repo = entry.get("repo", "")
            if repo in oversized:
                for k in ("packageUrl", "packageHash", "manifestHash", "attestationUrl"):
                    entry.pop(k, None)
                stripped += 1
                continue
            b = built.get(repo)
            if not b:
                continue
            entry["packageUrl"] = (f"https://github.com/{REGISTRY_REPO}"
                                   f"/releases/download/{args.release_tag}/{b['asset']}")
            entry["packageHash"] = b["packageHash"]
            entry["manifestHash"] = b["manifestHash"]
            # v2.20：构建证明与权限/兼容性声明随产物字段一起回写 ——
            # 与 packageUrl 同源同批，动态字段只许 CI 改的口径不变。
            entry["attestationUrl"] = (
                f"https://github.com/{REGISTRY_REPO}"
                f"/releases/download/{args.release_tag}/{b['attestationFile']}")
            if b.get("permissions"):
                entry["permissions"] = b["permissions"]
            if b.get("platforms"):
                entry["platforms"] = b["platforms"]
            if b.get("minWorkBuddyVersion"):
                entry["minWorkBuddyVersion"] = b["minWorkBuddyVersion"]
            patched += 1
        if patched == 0 and stripped == 0:
            print("没有可回写的条目（report 里没有成功构建的产物）。", file=sys.stderr)
            return 1
        text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
        tmp = reg_path.with_suffix(".json.tmp")
        tmp.write_text(text, encoding="utf-8", newline="\n")
        os.replace(tmp, reg_path)
        print(f"已回写 {patched} 条 artifact 字段 → {reg_path}"
              + (f"；拔除 {stripped} 条超大工件指针（安装走 ghpm 路线）" if stripped else ""))
        return 0

    doc = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    entries = doc.get("plugins", [])
    if args.repo:
        wanted = {r.strip() for r in args.repo}
        entries = [e for e in entries if e.get("repo") in wanted]
    built, failed, excluded = [], [], []
    for entry in entries:
        repo = entry.get("repo", "?")
        if args.only_missing and entry.get("packageHash"):
            print(f"  skip  {repo}: 已有 artifact 字段")
            continue
        try:
            info = build_one(entry, out_dir)
            built.append(info)
            ex = info.get("excluded") or {}
            print(f"  ok    {repo}: {info['asset']}  packageHash {info['packageHash'][:12]}…"
                  f"  skills {len(info['skills'])}"
                  + (f"  (瘦身剔除 {ex.get('excludedFiles', 0)} 个文件 / "
                     f"{ex.get('excludedBytes', 0) / 1024:.0f} KB)"
                     if ex.get("excludedFiles") else ""))
        except ArtifactOversized as exc:
            # v2.35 任务4：体积超限是**策略性拒发**，记 excluded 不算失败。
            excluded.append({"repo": repo, "reason": str(exc)})
            print(f"  --    {repo}: {exc}")
        except Exception as exc:  # noqa: BLE001 —— 单条失败记录，不拖垮整批
            failed.append({"repo": repo, "error": f"{type(exc).__name__}: {exc}"})
            print(f"  !!    {repo}: {type(exc).__name__}: {exc}", file=sys.stderr)

    report = {"builtAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "built": built, "failed": failed, "excluded": excluded}
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8", newline="\n")
    print(f"\n构建 {len(built)} 个 / 失败 {len(failed)} 个 / 超限拒发 {len(excluded)} 个；"
          f"report → {report_path}")
    return 1 if (built == [] and failed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
