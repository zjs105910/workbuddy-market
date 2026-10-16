"""Focused tests for reproducible ClawHub publish staging."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build-clawhub-upload.py"


def load_builder():
    spec = importlib.util.spec_from_file_location("pwf_build_clawhub", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def staging_repo(tmp_path: Path, monkeypatch):
    builder = load_builder()
    canonical = tmp_path / "skills" / "planning-with-files"
    (canonical / "scripts").mkdir(parents=True)
    (canonical / "templates").mkdir()
    (canonical / "SKILL.md").write_bytes(b"---\nname: planning-with-files\n---\n")
    (canonical / "scripts" / "clean.py").write_bytes(b"print('clean')\n")
    (canonical / "templates" / "task_plan.md").write_bytes(b"# Plan\n")

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "add", "--", "skills/planning-with-files"],
        cwd=tmp_path,
        check=True,
    )

    monkeypatch.setattr(builder, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(builder, "CANONICAL", canonical)
    monkeypatch.setattr(builder, "TARGET", tmp_path / "clawhub-upload")
    return builder, canonical, tmp_path / "clawhub-upload"


def test_build_copies_exact_tracked_inventory_and_excludes_untracked_cache(
    staging_repo,
) -> None:
    builder, canonical, target = staging_repo
    (canonical / "untracked-secret.txt").write_text("do not publish", encoding="utf-8")
    cache = canonical / "scripts" / "__pycache__"
    cache.mkdir()
    (cache / "clean.cpython-313.pyc").write_bytes(b"cache")

    count = builder.build()

    assert count == 3
    assert builder.verification_issues() == []
    assert (target / "SKILL.md").read_bytes() == (
        canonical / "SKILL.md"
    ).read_bytes()
    assert (target / "scripts" / "clean.py").read_bytes() == b"print('clean')\n"
    assert not (target / "untracked-secret.txt").exists()
    assert not (target / "scripts" / "__pycache__").exists()


def test_tracked_python_cache_artifacts_are_always_excluded(staging_repo) -> None:
    builder, canonical, target = staging_repo
    cache = canonical / "scripts" / "__pycache__"
    cache.mkdir()
    pyc = cache / "tracked.pyc"
    pyc.write_bytes(b"cache")
    subprocess.run(
        ["git", "add", "-f", "--", pyc.relative_to(builder.REPO_ROOT).as_posix()],
        cwd=builder.REPO_ROOT,
        check=True,
    )

    builder.build()

    assert not (target / "scripts" / "__pycache__").exists()
    assert builder.verification_issues() == []


def test_verify_rejects_stale_bytes_and_extraneous_files(staging_repo, capsys) -> None:
    builder, _canonical, target = staging_repo
    builder.build()
    (target / "SKILL.md").write_bytes(b"stale\n")
    (target / "extra.txt").write_text("extra", encoding="utf-8")

    result = builder.main(["--verify"])

    output = capsys.readouterr()
    assert result == 1
    assert "byte mismatch: SKILL.md" in output.err
    assert "extraneous: extra.txt" in output.err


def test_verify_rejects_missing_tracked_file(staging_repo) -> None:
    builder, _canonical, target = staging_repo
    builder.build()
    (target / "templates" / "task_plan.md").unlink()

    assert builder.verification_issues() == ["missing: templates/task_plan.md"]


def test_build_replaces_extraneous_stage_and_preserves_exact_bytes(staging_repo) -> None:
    builder, canonical, target = staging_repo
    target.mkdir()
    (target / "old-only.txt").write_text("stale", encoding="utf-8")
    binary = canonical / "payload.bin"
    binary.write_bytes(b"\x00\xff\r\n")
    subprocess.run(
        ["git", "add", "--", binary.relative_to(builder.REPO_ROOT).as_posix()],
        cwd=builder.REPO_ROOT,
        check=True,
    )

    builder.build()

    assert not (target / "old-only.txt").exists()
    assert (target / "payload.bin").read_bytes() == b"\x00\xff\r\n"
    assert builder.verification_issues() == []


@pytest.mark.parametrize("suffix", [".sh", ".py", ".ps1"])
def test_crlf_canonical_script_fails_closed_without_replacing_stage(
    staging_repo, suffix: str
) -> None:
    builder, canonical, target = staging_repo
    target.mkdir()
    marker = target / "existing.txt"
    marker.write_text("keep", encoding="utf-8")
    bad = canonical / "scripts" / f"bad{suffix}"
    bad.write_bytes(b"first\r\nsecond\r\n")
    subprocess.run(
        ["git", "add", "--", bad.relative_to(builder.REPO_ROOT).as_posix()],
        cwd=builder.REPO_ROOT,
        check=True,
    )

    with pytest.raises(builder.StagingError, match="must use LF line endings"):
        builder.build()

    assert marker.read_text(encoding="utf-8") == "keep"


def test_cli_has_no_destination_override() -> None:
    builder = load_builder()

    with pytest.raises(SystemExit):
        builder.parse_args(["outside-directory"])


def test_build_refuses_target_outside_repository(staging_repo, monkeypatch) -> None:
    builder, _canonical, _target = staging_repo
    outside = builder.REPO_ROOT.parent / "clawhub-upload"
    monkeypatch.setattr(builder, "TARGET", outside)

    with pytest.raises(builder.StagingError, match="outside the repository root"):
        builder.build()
