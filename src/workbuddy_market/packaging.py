# -*- coding: utf-8 -*-
"""packaging —— Market Package 的 pack / verify（v2.15 新增，协议见
docs/plugin-spec.md v0.2）。

定位：**纯函数层**。pack 把一个本地插件目录打成带 manifest 的
Market Package（第四层抽象：Skill / Plugin / GitHub Repo 之外的可校验
分发单元）；verify 对一个包做完整校验。v2.16 起接入安装链：
registry 带 packageUrl + packageHash → artifact.py 下载解包 →
verify → installer.install_package_skills 两阶段事务安装。

六项开放问题的冻结决定（2026-10-08，详见 plugin-spec.md §6）：

  1. 产物来源 = 不可变 artifact（CI 构建）；pack 的 source.ref 固定来源；
  2. 规范化 JSON = UTF-8（无 BOM）+ 键排序 + 紧凑分隔符 + LF，
     见 canonical_json()；
  3. 签名 = v0.1 不做（integrity 预留 signature 字段位）；
  4. 平台不匹配 = 默认拒绝，force=True 放行并记 warning
     （与 --allow-non-skill 同一口径）；
  5. ghpm 兼容 = 无 manifest 走现有路径（不在本轮）；
  6. 依赖 = 声明不解析，verify 只校验声明形状。

安全纪律（与全项目一致）：

  · **不可信状态文件**：manifest.json 是普通 JSON，可能被改 —— verify
    按攻击面处理：自哈希 → 逐文件哈希 → 磁盘与清单**双向一致**
    （多一个未列出的文件也算失败）→ 链接防线 → 路径穿越零容忍；
  · 链接防线：pack 源含重解析点直接拒绝；verify 的包内出现即失败；
  · pack / verify 都是 fail-closed：任何一项不过，整包拒绝，无半截状态。
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

from .config import ConfigError, ensure_child, validate_id, validate_version
from .fsutil import atomic_write_text
from .hasher import sha256_file
from .scanner import _scan

MANIFEST_NAME = "manifest.json"
PACKAGE_SCHEMA_VERSION = 1
PACKAGE_ALGORITHM = "sha256"

# 依赖声明的合法形状（v0.1 声明不解析；verify 只查形状）
_DEP_KEYS = {"skills", "system", "workbuddy"}


# ---------------------------------------------------------------- 规范化

def canonical_json(obj) -> bytes:
    """manifest 哈希用的规范化序列化（冻结决定 #2）。

    UTF-8（无 BOM）+ 键按 Unicode 码位排序 + 紧凑分隔符 + ensure_ascii=False
    （中文按原样编码，不转 \\uXXXX）+ 末尾无换行。任何跨工具的
    manifest 自哈希都必须用这个口径，否则不可复现。
    """
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def content_hash(files: dict) -> str:
    """整包内容哈希（P1 packageHash 的地基）：对「相对路径 → 文件哈希」
    的映射做规范化序列化再哈希。路径或内容任一变化都会改变它。"""
    return hashlib.sha256(canonical_json(files)).hexdigest()


# ---------------------------------------------------------------- pack

def pack_package(src: Path, out: Path, *, pid: str, name: str, version: str,
                 description: str = "", author: str = "", license: str = "",
                 skills: list | None = None, platforms: list | None = None,
                 min_workbuddy_version: str | None = None,
                 dependencies: dict | None = None,
                 source: dict | None = None) -> dict:
    """把本地插件目录打成 Market Package。

    · src → out 全量复制（symlinks=True 复制链接本身；源里出现重解析点
      则直接拒绝 —— 与安装阶段同一防线）；
    · skills 缺省自动发现 src/skills/ 下的子目录；每个声明的 skill 目录
      必须有 SKILL.md；
    · 生成 manifest.json：逐文件 sha256 + manifest 自哈希（canonical_json）
      + 整包 content_hash；
    · id / version 复用配置层校验（validate_id / validate_version）。

    返回 {"ok", "out", "files", "bytes", "packageHash", "manifest"}。
    失败时抛 ConfigError / OSError（调用方决定怎么呈现），out 里不会
    留下半截包（失败即清理）。
    """
    src, out = Path(src), Path(out)
    validate_id(pid, "包 id")
    validate_version(version, "包 version")

    _files, links = _scan(src, on_error="raise")
    if links:
        raise OSError(f"源目录含 {len(links)} 个符号链接 / junction，拒绝打包：{links[:3]}")

    if skills is None:
        sdir = src / "skills"
        skills = sorted(d.name for d in sdir.iterdir()
                        if d.is_dir() and not d.is_symlink()) if sdir.is_dir() else []
    if not skills:
        raise ConfigError("没有可打包的 skill（src/skills/ 下没有子目录，也未显式声明）")

    manifest = {
        "schemaVersion": PACKAGE_SCHEMA_VERSION,
        "id": pid, "name": name, "version": version,
        "description": description, "author": author, "license": license,
        "skills": [f"skills/{s}" for s in skills],
    }
    if platforms is not None:
        manifest["platforms"] = list(platforms)
    if min_workbuddy_version:
        manifest["minWorkBuddyVersion"] = str(min_workbuddy_version)
    if dependencies is not None:
        manifest["dependencies"] = dependencies
    if source is not None:
        manifest["source"] = source

    if out.exists():
        shutil.rmtree(out)
    try:
        shutil.copytree(src, out, symlinks=True)
        files, total = {}, 0
        for p in sorted(out.rglob("*")):
            if not p.is_file() or p.is_symlink():
                continue
            rel = p.relative_to(out).as_posix()
            if rel == MANIFEST_NAME:
                continue
            # v2.16：流式分块（约定 8/19）—— pack 路径此前是 read_bytes()
            # 整读，100 MB 的包会整个进内存；sha256_file 峰值 O(chunk)。
            digest = sha256_file(p).hex()
            files[rel] = digest
            total += p.stat().st_size
        for s in skills:
            if not (out / "skills" / s / "SKILL.md").is_file():
                raise ConfigError(f"skill {s!r} 缺少 SKILL.md，拒绝打包")
        manifest["integrity"] = {
            "algorithm": PACKAGE_ALGORITHM,
            "manifest": hashlib.sha256(
                canonical_json({k: v for k, v in manifest.items() if k != "integrity"})
            ).hexdigest(),
            "files": files,
        }
        atomic_write_text(out / MANIFEST_NAME,
                          json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    except BaseException:
        shutil.rmtree(out, ignore_errors=True)
        raise
    return {"ok": True, "out": out, "files": len(files), "bytes": total,
            "packageHash": content_hash(files), "manifest": manifest}


# ---------------------------------------------------------------- verify

def verify_package(pkg: Path, *, force: bool = False,
                   check_platform: bool = True) -> dict:
    """校验一个 Market Package（不可信输入，按攻击面处理）。

    校验序（任何一项失败即整包拒绝，errors 非空）：

      1. manifest 形状：schemaVersion / 必填字段 / id / version；
      2. skills 路径：必须以 skills/ 开头、无路径穿越、落在包内；
      3. manifest 自哈希：integrity.manifest == canonical_json(去 integrity)；
      4. 逐文件哈希 + **双向一致**：清单里每个文件存在且哈希一致，
         磁盘上（除 manifest.json 外）也不允许多出任何未列出文件；
      5. 链接防线：包内任何重解析点即失败；
      6. 每个 skill 目录有 SKILL.md；
      7. 平台：manifest 声明了 platforms 且不含本机 → 拒绝
         （force=True 放行并记 warning，冻结决定 #4）；
      8. 依赖声明形状（声明不解析，冻结决定 #6）。

    返回 {"ok", "errors", "warnings", "packageHash", "manifest"}。
    """
    pkg = Path(pkg)
    errors: list[str] = []
    warnings: list[str] = []
    manifest = None

    raw = None
    try:
        raw = json.loads((pkg / MANIFEST_NAME).read_text(encoding="utf-8"))
    except OSError as exc:
        errors.append(f"读不到 {MANIFEST_NAME}：{exc}")
    except ValueError as exc:
        errors.append(f"{MANIFEST_NAME} 不是合法 JSON：{exc}")

    files_ref: dict = {}
    if isinstance(raw, dict):
        manifest = raw
        errors.extend(_check_shape(manifest))
        errors.extend(_check_skills_paths(manifest, pkg))
        errors.extend(_check_deps_shape(manifest))
        integ = manifest.get("integrity")
        if not isinstance(integ, dict) or integ.get("algorithm") != PACKAGE_ALGORITHM:
            errors.append(f"integrity.algorithm 必须是 {PACKAGE_ALGORITHM!r}")
        elif not isinstance(integ.get("files"), dict):
            errors.append("integrity.files 缺失或不是对象")
        else:
            files_ref = integ["files"]
            want = hashlib.sha256(canonical_json(
                {k: v for k, v in manifest.items() if k != "integrity"})).hexdigest()
            if integ.get("manifest") != want:
                errors.append("manifest 自哈希不符（清单本身被改动过）")
    elif not errors:
        errors.append(f"{MANIFEST_NAME} 必须是一个 JSON 对象")

    # 链接防线：包内出现任何重解析点即失败（fail-closed，绝不跟进）
    try:
        _fi, links = _scan(pkg, on_error="raise")
        if links:
            errors.append(f"包内含 {len(links)} 个符号链接 / junction：{links[:3]}")
    except (OSError, ConfigError) as exc:
        errors.append(f"包扫描失败：{exc}")

    # 逐文件哈希 + 双向一致（在包内扫描通过后做，磁盘视图可信）
    if files_ref and pkg.is_dir():
        disk: dict[str, int] = {}
        for p in sorted(pkg.rglob("*")):
            if not p.is_file() or p.is_symlink():
                continue
            rel = p.relative_to(pkg).as_posix()
            if rel == MANIFEST_NAME:
                continue
            disk[rel] = p.stat().st_size
        for rel, digest in sorted(files_ref.items()):
            f = pkg / rel
            try:
                ensure_child(pkg, f)
            except ConfigError:
                errors.append(f"清单路径越界，拒绝处理：{rel!r}")
                continue
            if not f.is_file():
                errors.append(f"清单声明了但包里没有：{rel}")
                continue
            # v2.16：流式分块哈希。verify 是安装链的必经闸门，1 GB 的
            # 文件用 read_bytes() 会把整个文件吃进内存（评审 P1 实锤）。
            actual = sha256_file(f).hex()
            if actual != digest:
                errors.append(f"文件哈希不符（内容被改动过）：{rel}")
        for rel in sorted(set(disk) - set(files_ref)):
            errors.append(f"包里有清单未列出的文件：{rel}")

    # 平台（冻结决定 #4：默认拒绝，force 放行并记 warning）
    if check_platform and isinstance(manifest, dict):
        declared = manifest.get("platforms")
        if isinstance(declared, list) and declared:
            this = {"win32": "windows", "linux": "linux", "darwin": "macos"}.get(sys.platform)
            if this and this not in declared:
                if force:
                    warnings.append(
                        f"平台不匹配（本机 {this}，包声明 {declared}）—— force 放行")
                else:
                    errors.append(f"平台不匹配：本机 {this}，包声明 {declared}"
                                  "（force=True 可放行）")

    return {"ok": not errors, "errors": errors, "warnings": warnings,
            "packageHash": content_hash(files_ref) if files_ref else None,
            "manifest": manifest}


def _check_shape(man: dict) -> list[str]:
    errors = []
    if man.get("schemaVersion") != PACKAGE_SCHEMA_VERSION:
        errors.append(f"schemaVersion 必须是 {PACKAGE_SCHEMA_VERSION}")
    for field in ("id", "name", "version", "skills"):
        if field not in man:
            errors.append(f"缺少必填字段：{field}")
    if "id" in man:
        try:
            validate_id(man["id"], "包 id")
        except ConfigError as exc:
            errors.append(str(exc).splitlines()[0])
    if "version" in man:
        try:
            validate_version(man["version"], "包 version")
        except ConfigError as exc:
            errors.append(str(exc))
    return errors


def _check_skills_paths(man: dict, pkg: Path) -> list[str]:
    errors = []
    skills = man.get("skills")
    if not isinstance(skills, list) or not skills:
        return ["skills 必须是非空数组"]
    for s in skills:
        if not isinstance(s, str) or not s.startswith("skills/"):
            errors.append(f"skill 路径必须以 skills/ 开头：{s!r}")
            continue
        d = pkg / s
        try:
            ensure_child(pkg, d)
        except ConfigError:
            errors.append(f"skill 路径越界，拒绝处理：{s!r}")
            continue
        if not (d / "SKILL.md").is_file():
            errors.append(f"skill 缺少 SKILL.md：{s}")
    return errors


def _check_deps_shape(man: dict) -> list[str]:
    deps = man.get("dependencies")
    if deps is None:
        return []
    if not isinstance(deps, dict) or set(deps) - _DEP_KEYS:
        return ["dependencies 形状非法（只允许 skills / system / workbuddy）"]
    errors = []
    sk = deps.get("skills")
    if sk is not None:
        if not isinstance(sk, list) or not all(
                isinstance(d, dict) and isinstance(d.get("id"), str)
                and isinstance(d.get("range"), str) for d in sk):
            errors.append("dependencies.skills 必须是 [{id, range}] 数组")
    sy = deps.get("system")
    if sy is not None and not isinstance(sy, dict):
        errors.append("dependencies.system 必须是对象")
    wb = deps.get("workbuddy")
    if wb is not None and not isinstance(wb, str):
        errors.append("dependencies.workbuddy 必须是字符串")
    return errors
