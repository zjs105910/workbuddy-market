# -*- coding: utf-8 -*-
"""publish_marketplace_branch 的纯逻辑单测（git 编排部分不打网）。"""
from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location(
        "publish_mkt_branch", REPO_ROOT / "scripts" / "publish_marketplace_branch.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["publish_mkt_branch"] = mod
    spec.loader.exec_module(mod)
    return mod


pmb = _load()


def _make_zip(tmp_path: Path, market_name: str = "workbuddy-community-market") -> Path:
    zpath = tmp_path / "workbuddy-marketplace.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr(".codebuddy-plugin/marketplace.json", json.dumps({
            "name": market_name,
            "builtAt": "2026-10-12T00:00:00Z",
            "included": ["a", "b"], "excluded": [],
        }, ensure_ascii=False))
        zf.writestr("plugins/a/skills/x/SKILL.md", "---\nname: x\n---\nhi")
    return zpath


class TestExtractZip:
    def test_extracts_and_returns_manifest(self, tmp_path):
        z = _make_zip(tmp_path)
        dest = tmp_path / "out"
        dest.mkdir()
        m = pmb.extract_zip(z, dest)
        assert m["name"] == "workbuddy-community-market"
        assert (dest / ".codebuddy-plugin" / "marketplace.json").is_file()
        assert (dest / "plugins" / "a" / "skills" / "x" / "SKILL.md").is_file()

    def test_rejects_non_marketplace_zip(self, tmp_path):
        z = tmp_path / "bad.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("random.txt", "x")
        dest = tmp_path / "out2"
        dest.mkdir()
        with pytest.raises(ValueError, match="marketplace.json"):
            pmb.extract_zip(z, dest)

    def test_rejects_corrupt_zip(self, tmp_path):
        z = tmp_path / "corrupt.zip"
        z.write_bytes(b"PK\x03\x04garbage")
        dest = tmp_path / "out3"
        dest.mkdir()
        with pytest.raises(Exception):
            pmb.extract_zip(z, dest)


class TestNeedsPush:
    def test_same_tree_skips(self):
        assert pmb.needs_push("abc", "abc") is False

    def test_new_branch_pushes(self):
        assert pmb.needs_push("abc", None) is True

    def test_changed_tree_pushes(self):
        assert pmb.needs_push("abc", "def") is True

    def test_first_publish_missing_branch_is_push(self, tmp_path):
        """首次发布：分支不存在时旧树必须按 None 处理（回归钉防）。"""
        import subprocess
        repo_dir = tmp_path / "r"
        repo_dir.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo_dir)
        assert pmb.tree_of(repo_dir, "FETCH_HEAD") is None
        assert pmb.needs_push("t1", pmb.tree_of(repo_dir, "FETCH_HEAD")) is True


class TestBranchReadme:
    def test_readme_mentions_one_command_and_tradeoff(self):
        text = pmb.BRANCH_README
        assert "marketplace add" in text
        assert "workbuddy-market.git#marketplace" in text
        assert "sourceCommit" in text          # 固定来源口径要写明
        assert "前四问" in text                 # 取舍说明不能丢
