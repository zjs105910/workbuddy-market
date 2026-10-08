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
from workbuddy_market.packaging import pack_package                # noqa: E402
from workbuddy_market.registry import REGISTRY_REPO                # noqa: E402

DEFAULT_REGISTRY_FILE = REPO_ROOT / "registry" / "plugins.json"
TARBALL_TIMEOUT = 120.0
DOWNLOAD_CHUNK = 1024 * 1024
MAX_TARBALL_BYTES = 256 * 1024 * 1024        # 与 artifact.py 同一量级上限

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

def safe_extract_tar(tar_path: Path, dest: Path) -> Path:
    """安全解包 GitHub tarball（不可信输入，按攻击面处理）。

    · 成员名绝对路径 / 盘符 / ``..`` 段 → 拒绝；链接 / 设备成员 → 拒绝；
    · 自动剥掉 tarball 的第一层前缀（GitHub 恒为 ``<repo>-<ref>/``）；
    · 返回剥前缀后的内容根目录。
    """
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
            if not (m.isfile() or m.isdir()):
                raise werr.ArtifactError(f"tar 含符号链接 / 非常规成员：{name!r}")
            seg = name.split("/", 1)[0]
            if prefix is None:
                prefix = seg
            elif name != prefix and not name.startswith(prefix + "/"):
                raise werr.ArtifactError(f"tar 存在多个顶层前缀：{seg!r} vs {prefix!r}")
            members.append(m)
    if prefix is None:
        raise werr.ArtifactError("tarball 是空的")
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
      c. root 本身就是一个 skill（root/SKILL.md）→ staging/skills/<slug>。

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
        root = safe_extract_tar(tar_path, tmp / "src")
        src, skills = choose_skills_root(root, slug)
        pkg_dir = tmp / "pkg"
        packed = pack_package(src, pkg_dir, pid=slug, name=entry.get("displayName") or slug,
                              version=version,
                              description=entry.get("description", ""),
                              license=str(entry.get("license") or ""),
                              skills=skills,
                              source={"type": "github", "repo": repo, "ref": ref})
        asset = f"{slug}-{version}.zip"
        zip_path = out_dir / asset
        zip_dir(pkg_dir, zip_path)
        return {"repo": repo, "slug": slug, "version": version,
                "sourceCommit": ref,
                "packageHash": packed["packageHash"],
                "manifestHash": packed["manifest"]["integrity"]["manifest"],
                "asset": asset, "skills": skills,
                "bytes": zip_path.stat().st_size}
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
        reg_path = Path(args.registry)
        doc = json.loads(reg_path.read_text(encoding="utf-8"))
        patched = 0
        for entry in doc.get("plugins", []):
            b = built.get(entry.get("repo", ""))
            if not b:
                continue
            entry["packageUrl"] = (f"https://github.com/{REGISTRY_REPO}"
                                   f"/releases/download/{args.release_tag}/{b['asset']}")
            entry["packageHash"] = b["packageHash"]
            entry["manifestHash"] = b["manifestHash"]
            patched += 1
        if patched == 0:
            print("没有可回写的条目（report 里没有成功构建的产物）。", file=sys.stderr)
            return 1
        text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
        tmp = reg_path.with_suffix(".json.tmp")
        tmp.write_text(text, encoding="utf-8", newline="\n")
        os.replace(tmp, reg_path)
        print(f"已回写 {patched} 条 artifact 字段 → {reg_path}")
        return 0

    doc = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    entries = doc.get("plugins", [])
    if args.repo:
        wanted = {r.strip() for r in args.repo}
        entries = [e for e in entries if e.get("repo") in wanted]
    built, failed = [], []
    for entry in entries:
        repo = entry.get("repo", "?")
        if args.only_missing and entry.get("packageHash"):
            print(f"  skip  {repo}: 已有 artifact 字段")
            continue
        try:
            info = build_one(entry, out_dir)
            built.append(info)
            print(f"  ok    {repo}: {info['asset']}  packageHash {info['packageHash'][:12]}…"
                  f"  skills {len(info['skills'])}")
        except Exception as exc:  # noqa: BLE001 —— 单条失败记录，不拖垮整批
            failed.append({"repo": repo, "error": f"{type(exc).__name__}: {exc}"})
            print(f"  !!    {repo}: {type(exc).__name__}: {exc}", file=sys.stderr)

    report = {"builtAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "built": built, "failed": failed}
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8", newline="\n")
    print(f"\n构建 {len(built)} 个 / 失败 {len(failed)} 个；report → {report_path}")
    return 1 if (built == [] and failed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
