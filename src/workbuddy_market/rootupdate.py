# -*- coding: utf-8 -*-
"""Fail-closed updater for the WorkBuddy Market source root.

This module is shipped in the pipx CLI package, not only in the market root
being replaced. All filesystem operations are kept in Python so they can be
tested with pytest and the isolated selftest harness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

from .fsutil import atomic_write_text
from .paths import MARKET_ROOT, STATE_HOME as _IMPORTED_STATE_HOME
from .selfupdate import _release_fetch, compare_versions, parse_tag

REPO = "zjs105910/workbuddy-market"
API_RELEASES = f"https://api.github.com/repos/{REPO}/releases"
API_ZIPBALL = f"https://api.github.com/repos/{REPO}/zipball"
ARCHIVE_URL = f"https://github.com/{REPO}/archive/refs/tags"
PORTS = tuple(range(8777, 8792))
MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024
MAX_UNPACKED_BYTES = 5 * 1024 * 1024 * 1024
DISK_MARGIN_BYTES = 64 * 1024 * 1024
STATE_HOME = _IMPORTED_STATE_HOME

REQUIRED_FILES = (
    "launcher.py",
    "market_core.py",
    "install.cmd",
    "web/index.html",
    "src/workbuddy_market/application.py",
    "src/workbuddy_market/installer.py",
    "src/workbuddy_market/doctor.py",
    "src/workbuddy_market/paths.py",
    "registry/plugins.json",
)
PROTECTED_PATHS = (
    "market.config.json",
    "plugins",
    ".codebuddy-plugin/marketplace.json",
    ".env",
    ".workbuddy",
    ".workbuddy-market",
)
# Old in-root state is migrated into the same path-hashed STATE_HOME bucket.
# Lock files are deliberately not migrated: OS locks are process-owned, and a
# stale lock file must not be mistaken for a live lock.
LEGACY_STATE_FILES = {
    ".market-state.json": "state.json",
    ".ownership.json": "ownership.json",
    ".market-catalog.json": "catalog.json",
    ".market-registry.json": "registry.json",
}
LEGACY_STATE_DIRS = {
    ".market-tx": "tx",
    ".backups": "backups",
    ".trash": "trash",
}
_VERSION_RE = re.compile(r"""MARKET_VERSION\s*=\s*["'](\d+\.\d+\.\d+)["']""")
_BACKUP_RE = re.compile(r"^.+\.old-\d{14}$")


class RootUpdateError(RuntimeError):
    """A safe-to-report upgrade failure that leaves the old root in place."""


def read_market_version(root: Path) -> str | None:
    """Read the literal MARKET_VERSION from a market root, never infer it."""
    try:
        source = (root / "src" / "workbuddy_market" / "version.py").read_text(
            encoding="utf-8"
        )
    except (OSError, UnicodeError):
        return None
    match = _VERSION_RE.search(source)
    if not match or parse_tag(match.group(1)) is None:
        return None
    return match.group(1)


def _is_reparse_or_link(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            return True
        attrs = getattr(path.lstat(), "st_file_attributes", 0)
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        return bool(reparse_flag and attrs & reparse_flag)
    except FileNotFoundError:
        return False


def _assert_no_links(path: Path) -> None:
    """Refuse protected data containing symlinks/junctions; never follow them."""
    if _is_reparse_or_link(path):
        raise RootUpdateError(f"受保护路径包含符号链接或 junction，拒绝复制：{path}")
    if path.is_dir():
        for child in path.iterdir():
            _assert_no_links(child)


def _remove_path(path: Path) -> None:
    if _is_reparse_or_link(path) or not path.is_dir():
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    elif path.exists():
        shutil.rmtree(path)


def _copy_path(source: Path, target: Path) -> None:
    _assert_no_links(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    _remove_path(target)
    if source.is_dir():
        shutil.copytree(source, target, copy_function=shutil.copy2)
    else:
        shutil.copy2(source, target)


def _path_size(path: Path) -> int:
    """Best-effort regular-file byte count without traversing links."""
    if _is_reparse_or_link(path) or not path.exists():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    for base, dirs, files in os.walk(path, followlinks=False):
        base_path = Path(base)
        dirs[:] = [name for name in dirs if not _is_reparse_or_link(base_path / name)]
        for name in files:
            child = base_path / name
            if _is_reparse_or_link(child):
                continue
            try:
                total += child.stat().st_size
            except OSError:
                pass
    return total


def _protected_size(root: Path) -> int:
    total = 0
    candidates = [root / p for p in PROTECTED_PATHS]
    candidates.extend(root.glob(".market-log.ndjson*"))
    candidates.extend(root / p for p in (
        ".market-state.json", ".ownership.json", ".market-tx",
        ".backups", ".trash", ".market.lock", ".market-log.lock",
        ".market-catalog.json", ".market-registry.json",
    ))
    seen: set[str] = set()
    for path in candidates:
        if not path.exists() or str(path).casefold() in seen:
            continue
        seen.add(str(path).casefold())
        _assert_no_links(path)
        if path.is_file():
            try:
                total += path.stat().st_size
            except OSError:
                pass
        elif path.is_dir():
            for base, dirs, files in os.walk(path, followlinks=False):
                base_path = Path(base)
                for name in list(dirs):
                    p = base_path / name
                    if _is_reparse_or_link(p):
                        raise RootUpdateError(
                            f"受保护路径包含符号链接或 junction，拒绝复制：{p}"
                        )
                for name in files:
                    p = base_path / name
                    if _is_reparse_or_link(p):
                        raise RootUpdateError(
                            f"受保护路径包含符号链接或 junction，拒绝复制：{p}"
                        )
                    try:
                        total += p.stat().st_size
                    except OSError:
                        pass
    return total


def _check_zip_member(info: zipfile.ZipInfo) -> tuple[str, bool]:
    name = info.filename
    if not name or name.startswith(("/", "\\")) or "\\" in name:
        raise RootUpdateError(f"ZIP 含非法路径：{name!r}")
    raw = name[:-1] if name.endswith("/") else name
    if not raw or ":" in raw:
        raise RootUpdateError(f"ZIP 含非法路径：{name!r}")
    path = PurePosixPath(raw)
    if any(part in ("", ".", "..") for part in path.parts):
        raise RootUpdateError(f"ZIP 含路径穿越：{name!r}")
    mode = (info.external_attr >> 16) & 0xFFFF
    if stat.S_ISLNK(mode):
        raise RootUpdateError(f"ZIP 含符号链接成员，拒绝解压：{name!r}")
    kind = stat.S_IFMT(mode)
    if kind not in (0, stat.S_IFREG, stat.S_IFDIR):
        raise RootUpdateError(f"ZIP 含特殊文件成员，拒绝解压：{name!r}")
    return raw, info.is_dir()


def _extract_verified_zip(zip_path: Path, stage_dir: Path) -> Path:
    """CRC-check and safely extract one GitHub zipball root without extractall()."""
    try:
        archive = zipfile.ZipFile(zip_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise RootUpdateError(f"下载内容不是有效 ZIP：{exc}") from exc
    with archive:
        bad_member = archive.testzip()
        if bad_member is not None:
            raise RootUpdateError(f"ZIP CRC 校验失败：{bad_member}")
        infos = archive.infolist()
        if not infos:
            raise RootUpdateError("ZIP 为空。")
        total_size = sum(max(0, item.file_size) for item in infos)
        if total_size > MAX_UNPACKED_BYTES:
            raise RootUpdateError(
                f"ZIP 解压体积过大（{total_size} 字节），拒绝继续。"
            )
        normalized: list[tuple[zipfile.ZipInfo, str, bool]] = []
        root_names: set[str] = set()
        folded: set[str] = set()
        for info in infos:
            raw, is_dir = _check_zip_member(info)
            parts = PurePosixPath(raw).parts
            root_names.add(parts[0])
            relative = "/".join(parts[1:])
            if relative:
                key = relative.casefold().rstrip("/")
                if key in folded:
                    raise RootUpdateError(
                        f"ZIP 含 Windows 大小写冲突或重复路径：{relative!r}"
                    )
                folded.add(key)
            normalized.append((info, relative, is_dir))
        if len(root_names) != 1:
            raise RootUpdateError("ZIP 顶层目录不唯一，拒绝解压。")
        archive_root = next(iter(root_names))
        extracted_root = stage_dir / archive_root
        extracted_root.mkdir(parents=True, exist_ok=True)
        for info, relative, is_dir in normalized:
            if not relative:
                continue
            target = extracted_root.joinpath(*PurePosixPath(relative).parts)
            if not target.resolve().is_relative_to(extracted_root.resolve()):
                raise RootUpdateError(f"ZIP 成员越界：{info.filename!r}")
            if is_dir:
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
    return extracted_root


def _validate_release_tree(root: Path, expected_version: str) -> None:
    for rel in REQUIRED_FILES:
        path = root / rel
        if not path.is_file():
            raise RootUpdateError(f"Release ZIP 缺少必备文件：{rel}")
    bundled = root / "bundled"
    if not bundled.is_dir() or not any(p.is_file() for p in bundled.rglob("*")):
        raise RootUpdateError("Release ZIP 的 bundled/ 不存在或为空。")
    actual = read_market_version(root)
    if actual != expected_version:
        raise RootUpdateError(
            f"版本不一致：tag 是 {expected_version}，ZIP 中 MARKET_VERSION 是 {actual or '未知'}。"
        )


def _resolve_release_tag(requested: str | None) -> tuple[str, str]:
    if requested:
        parsed = parse_tag(requested)
        if parsed is None:
            raise RootUpdateError("目标版本格式错误；请使用 vX.Y.Z 或 X.Y.Z。")
        tag = "v" + ".".join(str(part) for part in parsed)
        url = f"{API_RELEASES}/tags/{urllib.parse.quote(tag, safe='')}"
        try:
            release = _release_fetch(url=url)
        except Exception as exc:
            raise RootUpdateError(f"无法读取 Release {tag}：{exc}") from exc
        if release.get("draft") or release.get("prerelease"):
            raise RootUpdateError(f"{tag} 不是可安装的正式 Release。")
        actual_tag = str(release.get("tag_name") or "")
        if parse_tag(actual_tag) != parsed:
            raise RootUpdateError(f"Release 返回的 tag 与请求不一致：{actual_tag!r}")
        return tag, ".".join(str(part) for part in parsed)

    try:
        release = _release_fetch()
    except Exception as exc:
        raise RootUpdateError(f"检查 GitHub 最新 Release 失败：{exc}") from exc
    tag = str(release.get("tag_name") or "")
    parsed = parse_tag(tag)
    if parsed is None or release.get("draft") or release.get("prerelease"):
        raise RootUpdateError(f"最新 Release 的 tag 无效或不是正式版：{tag!r}")
    return tag, ".".join(str(part) for part in parsed)


def _download_url(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={
        "User-Agent": "workbuddy-market-root-updater",
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        length = response.headers.get("Content-Length")
        if length and int(length) > MAX_ARCHIVE_BYTES:
            raise RootUpdateError("Release ZIP 超过下载体积上限。")
        with destination.open("wb") as output:
            shutil.copyfileobj(response, output)
    if destination.stat().st_size > MAX_ARCHIVE_BYTES:
        destination.unlink(missing_ok=True)
        raise RootUpdateError("Release ZIP 超过下载体积上限。")


def _download_release_zip(tag: str, destination: Path) -> None:
    encoded = urllib.parse.quote(tag, safe="")
    errors = []
    for url in (f"{API_ZIPBALL}/{encoded}", f"{ARCHIVE_URL}/{encoded}.zip"):
        try:
            _download_url(url, destination)
            return
        except Exception as exc:
            errors.append(f"{url}: {exc}")
            destination.unlink(missing_ok=True)
    raise RootUpdateError(
        "Release ZIP 下载失败（两个来源都不可用）：\n  " + "\n  ".join(errors)
    )


def _listening_ports() -> list[int]:
    """A user-friendly warning only; directory rename remains the real lock test."""
    listening = []
    for port in PORTS:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.15)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                listening.append(port)
    return listening


def _legacy_state_sources(root: Path) -> list[tuple[Path, Path]]:
    sources: list[tuple[Path, Path]] = []
    for source_name, target_name in LEGACY_STATE_FILES.items():
        source = root / source_name
        if source.exists():
            sources.append((source, STATE_HOME / target_name))
    for source_name, target_name in LEGACY_STATE_DIRS.items():
        source = root / source_name
        if source.exists():
            sources.append((source, STATE_HOME / target_name))
    for source in sorted(root.glob(".market-log.ndjson*")):
        if source.name == ".market-log.ndjson":
            target_name = "market.ndjson"
        else:
            target_name = "market.ndjson" + source.name[len(".market-log.ndjson"):]
        target = STATE_HOME / "logs" / target_name
        if (source, target) not in sources:
            sources.append((source, target))
    return sources


def _copy_legacy_state_to_staging(sources: list[tuple[Path, Path]], txn_dir: Path) -> list[tuple[Path, Path]]:
    """Stage legacy state on the STATE_HOME volume; do not modify live state yet."""
    staged: list[tuple[Path, Path]] = []
    for source, target in sources:
        if target.exists():
            raise RootUpdateError(
                f"发现旧布局状态 {source.name}，但目标状态已存在：{target}。"
                "为避免覆盖新状态，已中止升级；请先人工核对两份状态。"
            )
        _assert_no_links(source)
        staged_path = txn_dir / "state" / target.relative_to(STATE_HOME)
        _copy_path(source, staged_path)
        staged.append((staged_path, target))
    return staged


def _apply_state_migrations(staged: list[tuple[Path, Path]]) -> list[tuple[Path, Path]]:
    applied: list[tuple[Path, Path]] = []
    try:
        for staged_path, target in staged:
            if target.exists():
                raise RootUpdateError(f"迁移目标在执行中出现冲突：{target}")
            target.parent.mkdir(parents=True, exist_ok=True)
            os.rename(staged_path, target)
            applied.append((target, staged_path))
    except Exception:
        _rollback_state_migrations(applied)
        raise
    return applied


def _rollback_state_migrations(applied: list[tuple[Path, Path]]) -> None:
    errors = []
    for target, staged_path in reversed(applied):
        try:
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                os.rename(target, staged_path)
        except OSError as exc:
            errors.append(f"{target} -> {staged_path}: {exc}")
    if errors:
        raise RootUpdateError("旧状态回滚失败：\n  " + "\n  ".join(errors))


def _restore_root(root: Path, backup: Path, failed_new_root: Path) -> None:
    """Move new root aside, then put the complete old root back."""
    errors = []
    try:
        if root.exists():
            os.rename(root, failed_new_root)
    except OSError as exc:
        errors.append(f"{root} -> {failed_new_root}: {exc}")
    if not errors:
        restored = False
        for attempt in range(3):
            try:
                os.rename(backup, root)
                restored = True
                break
            except OSError as exc:
                if attempt == 2:
                    errors.append(f"{backup} -> {root}: {exc}")
                else:
                    time.sleep(0.2 * (2 ** attempt))
        if not restored and not errors:
            errors.append(f"{backup} -> {root}: 未能恢复")
    if errors:
        raise RootUpdateError(
            "自动回滚失败，需要人工恢复。\n"
            f"旧版备份：{backup}\n新版本目录：{failed_new_root}\n"
            f"请在关闭占用进程后依次执行：\n"
            f'  ren "{root}" "{failed_new_root.name}"\n'
            f'  ren "{backup}" "{root}"\n'
            "错误详情：\n  " + "\n  ".join(errors)
        )


def _state_home_for_root(root: Path) -> Path:
    """Mirror paths.py's bucket rule for the target root, not the pipx package."""
    explicit = os.environ.get("WBM_STATE_HOME")
    if explicit:
        return Path(explicit).expanduser().resolve()
    if os.environ.get("WBM_MARKET_ROOT") is None and os.environ.get("GHPM_MARKET_ROOT") is not None:
        # Compatibility with the old selftest/harness layout.
        return root.resolve()
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", root.resolve().name).strip("-") or "market"
    digest = hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()[:12]
    return (Path.home() / ".workbuddy-market" / "markets" / f"{name[:40]}-{digest}").resolve()


def _doctor_ok(root: Path) -> tuple[bool, str]:
    """Run the doctor's real CLI in a fresh process with explicit roots."""
    env = os.environ.copy()
    env["WBM_MARKET_ROOT"] = str(root.resolve())
    env["WBM_STATE_HOME"] = str(STATE_HOME.resolve())
    old_pythonpath = env.get("PYTHONPATH", "")
    source_path = str(root.resolve() / "src")
    env["PYTHONPATH"] = source_path + (os.pathsep + old_pythonpath if old_pythonpath else "")
    try:
        # Run outside the root: Windows cannot rename a process's current directory.
        result = subprocess.run(
            [sys.executable, "-m", "workbuddy_market", "doctor"],
            cwd=str(root.resolve().parent),
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=120,
            check=False,
        )
    except Exception as exc:
        return False, f"doctor 子进程执行失败：{exc}"
    output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
    if output:
        print(output)
    if result.returncode == 0:
        return True, ""
    return False, f"doctor 退出码 {result.returncode}。\n{output or '无诊断输出。'}"


def _cleanup_old_backups(root: Path, keep: Path) -> None:
    candidates = []
    for child in root.parent.iterdir():
        if child == keep or not child.name.startswith(root.name + ".old-"):
            continue
        if _BACKUP_RE.match(child.name):
            candidates.append(child)
    for old in candidates:
        _remove_path(old)


def _format_bytes(value: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{value} B"
        value /= 1024
    return str(value)


def check_root_update(root: Path) -> int:
    current = read_market_version(root)
    if current is None:
        print(f"本体：未知（无法读取 {root / 'src' / 'workbuddy_market' / 'version.py'}）")
    else:
        print(f"本体：当前 {current}")
    try:
        tag, latest = _resolve_release_tag(None)
    except RootUpdateError as exc:
        print(f"本体更新检查失败（不影响 CLI）：{exc}")
        return 0
    if current is None:
        print(f"本体更新：最新正式 Release {tag}；当前版本未知，运行 --update-root 升级")
    else:
        order = compare_versions(latest, current)
        if order > 0:
            print(f"本体更新：检测到最新 Release {tag} —— 运行 install.cmd --update-root 升级")
        elif order < 0:
            print(f"本体更新：最新 Release {latest} 低于当前 {current}（可能使用预发布源码）")
        else:
            print(f"本体更新：已是最新正式版本 {current}")
    return 0


def update_root(root: Path, requested_tag: str | None = None, *, force: bool = False) -> int:
    root = root.expanduser().resolve()
    if not (root / "launcher.py").is_file():
        raise RootUpdateError(f"市场根不存在（{root}），应走首装流程。")
    if (root / ".git").exists():
        raise RootUpdateError(
            f"检测到 Git 工作区：{root / '.git'}。为保护工作区（即使干净也可能含有本地意图），"
            "拒绝自动替换；请在该目录内使用 git pull。"
        )
    current = read_market_version(root)
    if current is None:
        print("警告：无法读取旧版本号；将继续显式升级，但旧版本显示为“未知”。")
    ports = _listening_ports()
    if ports and not force:
        joined = "、".join(str(port) for port in ports)
        raise RootUpdateError(
            f"检测到本机端口 {joined} 正在监听。请关闭市场界面后重试；"
            "确认无关程序占用时可显式添加 --force。"
        )
    if ports and force:
        print(f"警告：--force 跳过端口预检（监听端口：{', '.join(map(str, ports))}）；"
              "目录 rename 仍可能因文件占用失败。")

    tag, target_version = _resolve_release_tag(requested_tag)
    if current and compare_versions(target_version, current) < 0:
        print(f"警告：显式降级 {current} → {target_version}。")

    root.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d%H%M%S", time.gmtime())
    backup = root.with_name(f"{root.name}.old-{stamp}")
    if backup.exists():
        raise RootUpdateError(f"备份路径已存在，拒绝覆盖：{backup}")
    txn_id = stamp + "-" + str(os.getpid())
    work_dir = Path(tempfile.mkdtemp(prefix=".wbm-update-", dir=str(root.parent)))
    archive_path = work_dir / "release.zip"
    stage_dir = work_dir / "unpack"
    stage_dir.mkdir()
    state_txn_dir = STATE_HOME / (".rootupdate-stage-" + txn_id)
    if state_txn_dir.exists():
        raise RootUpdateError(f"状态暂存路径已存在，拒绝覆盖：{state_txn_dir}")
    root_moved = False
    new_root_moved = False
    staged_states: list[tuple[Path, Path]] = []
    applied_states: list[tuple[Path, Path]] = []
    keep_work_dir = False
    try:
        state_sources = _legacy_state_sources(root)
        _download_release_zip(tag, archive_path)
        with zipfile.ZipFile(archive_path) as archive:
            expanded_size = sum(max(0, item.file_size) for item in archive.infolist())
        free = shutil.disk_usage(root.parent).free
        protected_size = _protected_size(root)
        legacy_state_size = sum(_path_size(source) for source, _ in state_sources)
        needed = int(expanded_size * 1.2) + protected_size + DISK_MARGIN_BYTES
        if expanded_size > MAX_UNPACKED_BYTES:
            raise RootUpdateError("Release ZIP 解压体积超出上限。")
        if free < needed:
            raise RootUpdateError(
                f"磁盘空间不足：预计至少还需 {_format_bytes(needed)}，"
                f"当前可用 {_format_bytes(free)}。旧市场根尚未改动。"
            )
        STATE_HOME.mkdir(parents=True, exist_ok=True)
        state_volume = STATE_HOME
        while not state_volume.exists() and state_volume != state_volume.parent:
            state_volume = state_volume.parent
        state_free = shutil.disk_usage(state_volume).free
        state_needed = legacy_state_size + DISK_MARGIN_BYTES
        if state_free < state_needed:
            raise RootUpdateError(
                f"运行状态盘空间不足：迁移旧状态预计需要 {_format_bytes(state_needed)}，"
                f"当前可用 {_format_bytes(state_free)}。旧市场根尚未改动。"
            )
        new_root = _extract_verified_zip(archive_path, stage_dir)
        _validate_release_tree(new_root, target_version)
        staged_states = _copy_legacy_state_to_staging(state_sources, state_txn_dir)
        for rel in PROTECTED_PATHS:
            source = root / rel
            if source.exists():
                _copy_path(source, new_root / rel)
                print(f"保留：{rel}")
        for source in root.glob(".market-log.ndjson*"):
            _assert_no_links(source)
            target = new_root / source.name
            _copy_path(source, target)
            print(f"保留旧布局状态：{source.name}")
        for rel in (".market-state.json", ".ownership.json", ".market-tx",
                    ".backups", ".trash", ".market.lock", ".market-log.lock",
                    ".market-catalog.json", ".market-registry.json"):
            if (root / rel).exists():
                print(f"迁移旧布局状态：{rel} → STATE_HOME（原件保留在备份）")

        # Release a cwd inside the market root before attempting a Windows rename.
        os.chdir(root.parent)
        os.rename(root, backup)
        root_moved = True
        try:
            os.rename(new_root, root)
            new_root_moved = True
        except OSError as exc:
            for attempt in range(3):
                try:
                    os.rename(backup, root)
                    root_moved = False
                    break
                except OSError:
                    if attempt == 2:
                        keep_work_dir = True
                        raise RootUpdateError(
                            "新根上位失败且自动回滚失败；需要人工恢复。\n"
                            f"旧版备份：{backup}\n临时新版：{new_root}\n"
                            f'  ren "{backup}" "{root}"\n'
                            f"原始错误：{exc}"
                        ) from exc
                    time.sleep(0.2 * (2 ** attempt))
            raise RootUpdateError(f"新根上位失败，旧版已恢复：{exc}") from exc

        applied_states = _apply_state_migrations(staged_states)
        ok, detail = _doctor_ok(root)
        if not ok:
            _rollback_state_migrations(applied_states)
            applied_states = []
            failed_new_root = work_dir / "failed-new-root"
            _restore_root(root, backup, failed_new_root)
            root_moved = False
            new_root_moved = False
            keep_work_dir = True
            raise RootUpdateError(
                "升级后 doctor 未通过，已回滚到旧版本；旧版备份仍保留。\n" + detail
            )

        metadata = {
            "schema": 1,
            "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "previousVersion": current,
            "newVersion": target_version,
            "tag": tag,
            "backup": str(backup),
            "legacyStateMigrated": [source.name for source, _ in state_sources],
        }
        try:
            atomic_write_text(
                STATE_HOME / "root-update.json",
                json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                durable=True,
            )
        except Exception as exc:
            _rollback_state_migrations(applied_states)
            applied_states = []
            failed_new_root = work_dir / "failed-new-root"
            _restore_root(root, backup, failed_new_root)
            root_moved = False
            new_root_moved = False
            keep_work_dir = True
            raise RootUpdateError(
                f"升级元数据写入失败，已回滚到旧版本：{exc}"
            ) from exc

        _cleanup_old_backups(root, backup)
        shutil.rmtree(state_txn_dir, ignore_errors=True)
        shutil.rmtree(work_dir, ignore_errors=True)
        if current is None:
            print(f"升级完成：未知 → {target_version}（{tag}）；保留旧版备份 {backup}")
        else:
            print(f"升级完成：{current} → {target_version}（{tag}）；保留最近一份备份 {backup}")
        print("校验口径：正式 Release tag + MARKET_VERSION 一致 + 必备文件清单 + ZIP CRC。")
        print("注意：源码 ZIP 未附可核对的 SHA-256 清单；以上不等于独立来源证明。")
        return 0
    except Exception as exc:
        if root_moved and backup.exists():
            try:
                if applied_states:
                    _rollback_state_migrations(applied_states)
                    applied_states = []
                if root.exists():
                    failed_new_root = work_dir / "failed-new-root"
                    _restore_root(root, backup, failed_new_root)
                    root_moved = False
                    new_root_moved = False
                    keep_work_dir = True
                elif not root.exists():
                    last_error = None
                    for attempt in range(3):
                        try:
                            os.rename(backup, root)
                            root_moved = False
                            break
                        except OSError as rollback_exc:
                            last_error = rollback_exc
                            if attempt < 2:
                                time.sleep(0.2 * (2 ** attempt))
                    if root_moved:
                        raise RootUpdateError(f"恢复旧根失败：{last_error}")
            except Exception as rollback_exc:
                keep_work_dir = True
                raise RootUpdateError(
                    "升级发生异常，自动回滚失败；需要人工恢复。\n"
                    f"市场根：{root}\n旧版备份：{backup}\n"
                    f"临时目录：{work_dir}\n"
                    f'  ren "{root}" "{(work_dir / "failed-new-root")}"\n'
                    f'  ren "{backup}" "{root}"\n'
                    f"原始异常：{exc}\n回滚异常：{rollback_exc}"
                ) from rollback_exc
        if isinstance(exc, RootUpdateError):
            raise
        raise RootUpdateError(f"升级失败，旧市场根未被静默覆盖：{exc}") from exc
    finally:
        if not keep_work_dir:
            shutil.rmtree(work_dir, ignore_errors=True)
        if not keep_work_dir:
            shutil.rmtree(state_txn_dir, ignore_errors=True)
        try:
            if original_cwd.exists():
                os.chdir(original_cwd)
        except OSError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="workbuddy-market root-update",
        description="显式升级 WorkBuddy Market 源码根目录；默认模式只检查，不自动安装。",
    )
    default_root = MARKET_ROOT
    if not (default_root / "launcher.py").is_file():
        home_root = Path.home() / "workbuddy-market"
        if (home_root / "launcher.py").is_file() or not (default_root / "launcher.py").exists():
            default_root = home_root
    parser.add_argument("--market-root", type=Path, default=default_root,
                        help="待管理的市场根目录（默认尝试当前市场或 ~/workbuddy-market）")
    parser.add_argument("--check-only", action="store_true",
                        help="仅显示当前根版本与最新正式 Release，不替换文件")
    parser.add_argument("--tag", help="指定正式 Release 版本（vX.Y.Z 或 X.Y.Z；允许显式降级）")
    parser.add_argument("--force", action="store_true",
                        help="跳过端口占用预检；不能绕过目录 rename 的文件占用检查")
    args = parser.parse_args(argv)
    root = args.market_root.expanduser().resolve()
    if args.check_only:
        return check_root_update(root)
    try:
        return update_root(root, args.tag, force=args.force)
    except RootUpdateError as exc:
        print(f"市场本体升级失败：{exc}")
        return 2 if "人工恢复" in str(exc) else 1
