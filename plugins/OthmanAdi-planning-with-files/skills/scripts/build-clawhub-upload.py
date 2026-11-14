#!/usr/bin/env python3
"""Build or verify the fixed ClawHub upload staging directory.

The Git-tracked files below ``skills/planning-with-files/`` are the complete
publish inventory.  Untracked files and Python cache artifacts are never
copied.  The destination is intentionally fixed at ``clawhub-upload/`` so this
release helper cannot be pointed at an arbitrary directory.

Usage from the repository root::

    python scripts/build-clawhub-upload.py
    python scripts/build-clawhub-upload.py --verify
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path, PurePosixPath


REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_REL = PurePosixPath("skills/planning-with-files")
CANONICAL = REPO_ROOT / Path(*CANONICAL_REL.parts)
TARGET = REPO_ROOT / "clawhub-upload"
LF_SUFFIXES = frozenset({".sh", ".py", ".ps1"})


class StagingError(RuntimeError):
    """Raised when staging cannot be built or verified safely."""


def _is_cache_artifact(relative: PurePosixPath) -> bool:
    return "__pycache__" in relative.parts or relative.suffix.lower() == ".pyc"


def tracked_inventory() -> tuple[PurePosixPath, ...]:
    """Return the sorted, publishable Git-tracked canonical inventory."""
    try:
        result = subprocess.run(
            [
                "git",
                "ls-files",
                "-z",
                "--",
                CANONICAL_REL.as_posix(),
            ],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise StagingError(
            f"cannot read the Git-tracked canonical inventory: {exc}"
        ) from exc

    prefix = CANONICAL_REL.as_posix() + "/"
    inventory: list[PurePosixPath] = []
    for raw_path in result.stdout.split(b"\0"):
        if not raw_path:
            continue
        try:
            tracked_path = raw_path.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise StagingError("Git returned a non-UTF-8 canonical path") from exc
        if not tracked_path.startswith(prefix):
            raise StagingError(
                f"unexpected tracked path outside canonical source: {tracked_path}"
            )
        relative = PurePosixPath(tracked_path[len(prefix) :])
        if relative.is_absolute() or ".." in relative.parts:
            raise StagingError(f"unsafe canonical path: {tracked_path}")
        if _is_cache_artifact(relative):
            continue
        inventory.append(relative)

    unique = tuple(sorted(set(inventory), key=lambda path: path.as_posix()))
    if not unique:
        raise StagingError("canonical tracked inventory is empty")
    return unique


def _source_bytes(relative: PurePosixPath) -> bytes:
    source = CANONICAL / Path(*relative.parts)
    if source.is_symlink() or not source.is_file():
        raise StagingError(
            f"canonical entry is not a regular file: {relative.as_posix()}"
        )
    data = source.read_bytes()
    if relative.suffix.lower() in LF_SUFFIXES and b"\r" in data:
        raise StagingError(
            f"canonical script must use LF line endings: {relative.as_posix()}"
        )
    return data


def _directory_inventory(root: Path) -> tuple[PurePosixPath, ...]:
    if root.is_symlink():
        raise StagingError(f"staging root must not be a symlink: {root}")
    if not root.is_dir():
        raise StagingError(f"staging directory is missing: {root}")

    inventory: list[PurePosixPath] = []
    for directory, dirnames, filenames in os.walk(root):
        directory_path = Path(directory)
        for dirname in dirnames:
            child = directory_path / dirname
            if child.is_symlink():
                relative = child.relative_to(root).as_posix()
                raise StagingError(f"staging entry must not be a symlink: {relative}")
        for filename in filenames:
            child = directory_path / filename
            relative = PurePosixPath(child.relative_to(root).as_posix())
            if child.is_symlink() or not child.is_file():
                raise StagingError(
                    f"staging entry is not a regular file: {relative.as_posix()}"
                )
            inventory.append(relative)
    return tuple(sorted(inventory, key=lambda path: path.as_posix()))


def verification_issues(root: Path | None = None) -> list[str]:
    """Return exact-inventory, byte-parity, and line-ending failures."""
    if root is None:
        root = TARGET
    expected = tracked_inventory()
    expected_set = set(expected)
    try:
        actual = _directory_inventory(root)
    except StagingError as exc:
        return [str(exc)]
    actual_set = set(actual)

    issues = [
        f"missing: {path.as_posix()}" for path in sorted(expected_set - actual_set)
    ]
    issues.extend(
        f"extraneous: {path.as_posix()}" for path in sorted(actual_set - expected_set)
    )

    for relative in sorted(expected_set & actual_set):
        source_data = _source_bytes(relative)
        staged_data = (root / Path(*relative.parts)).read_bytes()
        if staged_data != source_data:
            issues.append(f"byte mismatch: {relative.as_posix()}")
        if relative.suffix.lower() in LF_SUFFIXES and b"\r" in staged_data:
            issues.append(f"staged script is not LF-only: {relative.as_posix()}")
    return issues


def _assert_managed_path(
    path: Path,
    *,
    expected_name: str | None = None,
    expected_prefix: str | None = None,
) -> None:
    if path.parent.resolve() != REPO_ROOT.resolve():
        raise StagingError(
            f"refusing to manage a path outside the repository root: {path}"
        )
    if expected_name is not None and path.name != expected_name:
        raise StagingError(f"refusing to manage unexpected path: {path}")
    if expected_prefix is not None and not path.name.startswith(expected_prefix):
        raise StagingError(f"refusing to manage unexpected path: {path}")


def _safe_remove_tree(path: Path, *, prefix: str) -> None:
    _assert_managed_path(path, expected_prefix=prefix)
    if not path.exists():
        return
    if path.is_symlink() or not path.is_dir():
        raise StagingError(f"refusing to remove non-directory managed path: {path}")
    shutil.rmtree(path)


def build() -> int:
    """Rebuild ``clawhub-upload/`` from canonical tracked bytes."""
    _assert_managed_path(TARGET, expected_name="clawhub-upload")
    if TARGET.is_symlink():
        raise StagingError(f"refusing to replace symlinked staging root: {TARGET}")
    if TARGET.exists() and not TARGET.is_dir():
        raise StagingError(f"staging target is not a directory: {TARGET}")

    inventory = tracked_inventory()
    temp_root = Path(
        tempfile.mkdtemp(prefix=".clawhub-upload-build-", dir=REPO_ROOT)
    )
    backup: Path | None = None
    try:
        for relative in inventory:
            destination = temp_root / Path(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(_source_bytes(relative))

        temp_issues = verification_issues(temp_root)
        if temp_issues:
            raise StagingError(
                "temporary stage failed verification: " + "; ".join(temp_issues)
            )

        if TARGET.exists():
            backup = REPO_ROOT / f".clawhub-upload-backup-{uuid.uuid4().hex}"
            _assert_managed_path(backup, expected_prefix=".clawhub-upload-backup-")
            os.replace(TARGET, backup)

        try:
            os.replace(temp_root, TARGET)
        except BaseException:
            if backup is not None and backup.exists() and not TARGET.exists():
                os.replace(backup, TARGET)
            raise

        if backup is not None:
            _safe_remove_tree(backup, prefix=".clawhub-upload-backup-")
        return len(inventory)
    finally:
        if temp_root.exists():
            _safe_remove_tree(temp_root, prefix=".clawhub-upload-build-")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the fixed ClawHub stage from tracked canonical files."
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="check exact inventory, bytes, and script line endings without writing",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.verify:
            issues = verification_issues()
            if issues:
                for issue in issues:
                    print(f"ERROR: {issue}", file=sys.stderr)
                return 1
            print(f"ClawHub staging verified: {len(tracked_inventory())} files match.")
            return 0

        count = build()
        print(f"ClawHub staging rebuilt: {count} tracked canonical files.")
        return 0
    except StagingError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
