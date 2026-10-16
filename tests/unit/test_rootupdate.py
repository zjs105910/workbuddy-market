# -*- coding: utf-8 -*-
"""Offline unit tests for the fail-closed source-root updater."""
from __future__ import annotations

import os
import stat
import sys
import zipfile
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (str(_REPO_ROOT), str(_REPO_ROOT / "src")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from workbuddy_market import rootupdate as updater  # noqa: E402


def _release_zip(path: Path, version: str = "2.37.0", *, omit=(), extras=None) -> Path:
    """Build a tiny GitHub-zipball-shaped tree with one top-level directory."""
    prefix = "zjs105910-workbuddy-market-test"
    files = {
        "launcher.py": "# launcher\n",
        "market_core.py": "# core\n",
        "install.cmd": "@echo off\n",
        "web/index.html": "<!doctype html>\n",
        "src/workbuddy_market/application.py": "# app\n",
        "src/workbuddy_market/installer.py": "# installer\n",
        "src/workbuddy_market/doctor.py": "# doctor\n",
        "src/workbuddy_market/paths.py": "# paths\n",
        "src/workbuddy_market/version.py": f'MARKET_VERSION = "{version}"\n',
        "registry/plugins.json": '{"plugins": []}\n',
        "bundled/example.txt": "bundle\n",
    }
    for name in omit:
        files.pop(name, None)
    files.update(extras or {})
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(f"{prefix}/{name}", data)
    return path


def _old_root(root: Path, version: str = "2.36.0", *, git=False) -> Path:
    (root / "src" / "workbuddy_market").mkdir(parents=True, exist_ok=True)
    (root / "src" / "workbuddy_market" / "version.py").write_text(
        f'MARKET_VERSION = "{version}"\n', encoding="utf-8"
    )
    (root / "launcher.py").write_text("# old launcher\n", encoding="utf-8")
    (root / "market.config.json").write_text('{"marketId":"personal"}\n', encoding="utf-8")
    (root / "plugins" / "my-skill").mkdir(parents=True)
    (root / "plugins" / "my-skill" / "SKILL.md").write_text(
        "personal skill stays\n", encoding="utf-8"
    )
    if git:
        (root / ".git").mkdir()
    return root


def _mock_download(monkeypatch, tmp_path: Path, version="2.37.0"):
    def fake_download(tag, destination):
        _release_zip(destination, version)
    monkeypatch.setattr(updater, "_resolve_release_tag", lambda requested: (f"v{version}", version))
    monkeypatch.setattr(updater, "_download_release_zip", fake_download)
    monkeypatch.setattr(updater, "_listening_ports", lambda: [])


def _state_home(monkeypatch, tmp_path: Path) -> Path:
    home = tmp_path / "state-home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("WBM_STATE_HOME", str(home))
    monkeypatch.delenv("GHPM_MARKET_ROOT", raising=False)
    return home


def test_read_market_version_is_literal_and_fail_closed(tmp_path):
    root = tmp_path / "market"
    version_file = root / "src" / "workbuddy_market" / "version.py"
    version_file.parent.mkdir(parents=True)
    version_file.write_text('MARKET_VERSION = "2.37.0"\n', encoding="utf-8")
    assert updater.read_market_version(root) == "2.37.0"
    version_file.write_text('MARKET_VERSION = "latest"\n', encoding="utf-8")
    assert updater.read_market_version(root) is None
    assert updater.read_market_version(tmp_path / "missing") is None


def test_state_bucket_matches_market_root_not_pipx_package(tmp_path, monkeypatch):
    monkeypatch.delenv("WBM_STATE_HOME", raising=False)
    monkeypatch.delenv("GHPM_MARKET_ROOT", raising=False)
    monkeypatch.delenv("WBM_MARKET_ROOT", raising=False)
    root = tmp_path / "workbuddy-market"
    expected = updater.hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()[:12]
    home = updater._state_home_for_root(root)
    assert home.name == f"workbuddy-market-{expected}"
    assert home.parts[-3:-1] == (".workbuddy-market", "markets")


def test_zip_extraction_strips_one_root_and_validates_version(tmp_path):
    archive = _release_zip(tmp_path / "release.zip")
    extracted = updater._extract_verified_zip(archive, tmp_path / "stage")
    updater._validate_release_tree(extracted, "2.37.0")
    assert (extracted / "launcher.py").is_file()
    assert updater.read_market_version(extracted) == "2.37.0"


@pytest.mark.parametrize("name", [
    "../escape.txt",
    "/absolute.txt",
    r"C:/absolute.txt",
    "repo/../escape.txt",
])
def test_zip_member_path_traversal_is_rejected(name):
    info = zipfile.ZipInfo(name)
    with pytest.raises(updater.RootUpdateError):
        updater._check_zip_member(info)


def test_zip_symlink_member_is_rejected():
    info = zipfile.ZipInfo("repo/link")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(updater.RootUpdateError, match="符号链接"):
        updater._check_zip_member(info)


def test_release_missing_required_file_is_rejected(tmp_path):
    archive = _release_zip(tmp_path / "release.zip", omit=("src/workbuddy_market/doctor.py",))
    extracted = updater._extract_verified_zip(archive, tmp_path / "stage")
    with pytest.raises(updater.RootUpdateError, match="doctor.py"):
        updater._validate_release_tree(extracted, "2.37.0")


def test_release_version_must_equal_tag(tmp_path):
    archive = _release_zip(tmp_path / "release.zip", version="2.36.0")
    extracted = updater._extract_verified_zip(archive, tmp_path / "stage")
    with pytest.raises(updater.RootUpdateError, match="版本不一致"):
        updater._validate_release_tree(extracted, "2.37.0")


def test_git_clone_is_refused_before_network_or_mutation(tmp_path, monkeypatch):
    root = _old_root(tmp_path / "market", git=True)
    before = (root / "launcher.py").read_text(encoding="utf-8")
    monkeypatch.setattr(updater, "_resolve_release_tag",
                        lambda requested: pytest.fail("network/release lookup must not run"))
    with pytest.raises(updater.RootUpdateError, match="Git 工作区"):
        updater.update_root(root)
    assert (root / "launcher.py").read_text(encoding="utf-8") == before
    assert (root / ".git").is_dir()


def test_port_precheck_refuses_by_default(tmp_path, monkeypatch):
    root = _old_root(tmp_path / "market")
    monkeypatch.setattr(updater, "_listening_ports", lambda: [8777])
    monkeypatch.setattr(updater, "_resolve_release_tag",
                        lambda requested: pytest.fail("must stop before release lookup"))
    with pytest.raises(updater.RootUpdateError, match="8777"):
        updater.update_root(root)
    assert updater.read_market_version(root) == "2.36.0"


def test_successful_update_preserves_personal_data_and_keeps_backup(tmp_path, monkeypatch):
    root = _old_root(tmp_path / "workbuddy-market")
    state_home = _state_home(monkeypatch, tmp_path)
    _mock_download(monkeypatch, tmp_path)
    monkeypatch.setattr(updater, "_doctor_ok", lambda root: (True, ""))

    result = updater.update_root(root)

    assert result == 0
    assert updater.read_market_version(root) == "2.37.0"
    assert (root / "market.config.json").read_text(encoding="utf-8") == '{"marketId":"personal"}\n'
    assert (root / "plugins" / "my-skill" / "SKILL.md").read_text(
        encoding="utf-8"
    ) == "personal skill stays\n"
    backups = list(tmp_path.glob("workbuddy-market.old-*"))
    assert len(backups) == 1
    assert updater.read_market_version(backups[0]) == "2.36.0"
    metadata = state_home / "root-update.json"
    assert metadata.is_file()


def test_second_rename_failure_rolls_back_old_root(tmp_path, monkeypatch):
    root = _old_root(tmp_path / "workbuddy-market")
    _state_home(monkeypatch, tmp_path)
    _mock_download(monkeypatch, tmp_path)
    monkeypatch.setattr(updater, "_doctor_ok", lambda root: (True, ""))
    real_rename = os.rename
    calls = {"count": 0}

    def fail_new_root_once(source, target):
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("injected second rename failure")
        return real_rename(source, target)

    monkeypatch.setattr(updater.os, "rename", fail_new_root_once)
    with pytest.raises(updater.RootUpdateError, match="旧版已恢复"):
        updater.update_root(root)
    assert updater.read_market_version(root) == "2.36.0"
    assert not list(tmp_path.glob("workbuddy-market.old-*"))


def test_doctor_failure_rolls_back_and_keeps_recovery_workspace(tmp_path, monkeypatch):
    root = _old_root(tmp_path / "workbuddy-market")
    _state_home(monkeypatch, tmp_path)
    _mock_download(monkeypatch, tmp_path)
    monkeypatch.setattr(updater, "_doctor_ok", lambda root: (False, "injected doctor failure"))
    with pytest.raises(updater.RootUpdateError, match="doctor 未通过"):
        updater.update_root(root)
    assert updater.read_market_version(root) == "2.36.0"
    assert "2.37.0" not in (
        root / "src" / "workbuddy_market" / "version.py"
    ).read_text(encoding="utf-8")


def test_failed_rollback_reports_manual_recovery_commands(tmp_path, monkeypatch):
    root = _old_root(tmp_path / "workbuddy-market")
    _state_home(monkeypatch, tmp_path)
    _mock_download(monkeypatch, tmp_path)
    monkeypatch.setattr(updater, "_doctor_ok", lambda root: (False, "injected doctor failure"))
    real_rename = os.rename

    def fail_restore_backup(source, target):
        source_path, target_path = Path(source), Path(target)
        if source_path.name.startswith(root.name + ".old-") and target_path == root:
            raise OSError("injected rollback failure")
        return real_rename(source, target)

    monkeypatch.setattr(updater.os, "rename", fail_restore_backup)
    with pytest.raises(updater.RootUpdateError, match="需要人工恢复") as exc:
        updater.update_root(root)
    assert "move /Y" in str(exc.value)
    assert "旧版备份" in str(exc.value)
