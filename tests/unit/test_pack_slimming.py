# -*- coding: utf-8 -*-
"""打包瘦身与工件日期（v2.35 NEXT_STEPS 任务3/4/5 的 pytest 扩面）。

selftest 27B-2 / 32D-2 已有端到端盯防；本文件补单元层快速回归：
artifact_build_date 解析、_junk_ignore 口径、stage_clean 剔除统计、
体积闸门与 --patch-registry 拔指针。
"""
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "scripts"
for p in (str(_REPO_ROOT), str(_SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import build_artifacts  # noqa: E402
from workbuddy_market.registry import artifact_build_date  # noqa: E402


# ---------------------------------------------------------------- 任务3

class TestArtifactBuildDate:
    def test_parses_release_tag_date(self):
        e = {"packageUrl": ("https://github.com/o/r/releases/download/"
                            "registry-artifacts-2026-10-11/x.zip")}
        assert artifact_build_date(e) == "2026-10-11"

    def test_no_package_url_is_empty(self):
        assert artifact_build_date({"pushedAt": "2026-10-09"}) == ""
        assert artifact_build_date({}) == ""

    def test_untagged_url_is_empty(self):
        e = {"packageUrl": "https://github.com/o/r/releases/download/latest/x.zip"}
        assert artifact_build_date(e) == ""

    def test_never_fakes_from_pushed_at(self):
        # 没有工件日期就别说有 —— 绝不用 pushedAt 冒充
        assert artifact_build_date({"packageUrl": "x", "pushedAt": "2026-10-09"}) == ""


# ---------------------------------------------------------------- 任务4

def _mk_skill(root: Path, name: str = "alpha") -> None:
    """造一个带 SKILL.md + 正常文件 + 各类垃圾的 skill 目录。"""
    d = root / "skills" / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
    (d / "tool.py").write_text("print(1)\n", encoding="utf-8")
    (d / "__pycache__").mkdir()
    (d / "__pycache__" / "t.pyc").write_bytes(b"x" * 100)
    (d / ".git").mkdir()
    (d / ".git" / "config").write_bytes(b"[core]\n")
    (d / ".DS_Store").write_bytes(b"y" * 50)


class TestStageClean:
    def test_keeps_skill_content_only(self, tmp_path):
        root = tmp_path / "src"
        _mk_skill(root)
        (root / "README.md").write_text("# repo\n", encoding="utf-8")
        dest = tmp_path / "clean"
        st = build_artifacts.stage_clean(root, ["alpha"], dest)
        kept = sorted(p.relative_to(dest).as_posix()
                      for p in dest.rglob("*") if p.is_file())
        assert kept == ["skills/alpha/SKILL.md", "skills/alpha/tool.py"]
        assert st["excludedFiles"] == 3          # pyc + .git/config + .DS_Store
        assert st["excludedBytes"] == 100 + 7 + 50

    def test_missing_skill_raises(self, tmp_path):
        with pytest.raises(Exception):
            build_artifacts.stage_clean(tmp_path / "none", ["alpha"],
                                        tmp_path / "clean")


class TestSizeGate:
    def test_gate_is_64mb(self):
        assert build_artifacts.ARTIFACT_MAX_BYTES == 64 * 1024 * 1024

    def test_gate_exception_type(self):
        # 策略性拒发走专用异常（不是 ArtifactError/ConfigError）——
        # main() 按 except 分支把超限记进 report.excluded 而非 failed
        assert issubclass(build_artifacts.ArtifactOversized, Exception)


class TestPatchRegistryStrip:
    def test_excluded_entry_fields_stripped(self, tmp_path):
        out_dir = tmp_path / "artifacts"
        out_dir.mkdir()
        (out_dir / "report.json").write_text(json.dumps({
            "built": [], "failed": [],
            "excluded": [{"repo": "big/one", "reason": "超过上限"}]}),
            encoding="utf-8")
        reg = tmp_path / "plugins.json"
        reg.write_text(json.dumps({"schema": 1, "plugins": [
            {"repo": "big/one", "trust": "reviewed",
             "packageUrl": "https://old/x.zip", "packageHash": "0" * 64,
             "manifestHash": "1" * 64, "attestationUrl": "https://old/a.json"},
            {"repo": "ok/one", "trust": "reviewed"}]}), encoding="utf-8")
        rc = build_artifacts.main(["--patch-registry", "--out", str(out_dir),
                                   "--registry", str(reg),
                                   "--release-tag", "registry-artifacts-2026-10-14"])
        assert rc == 0
        doc = json.loads(reg.read_text(encoding="utf-8"))
        big = doc["plugins"][0]
        assert not any(k in big for k in ("packageUrl", "packageHash",
                                          "manifestHash", "attestationUrl"))
        assert big["trust"] == "reviewed"          # 静态字段不动
        assert "packageHash" not in doc["plugins"][1]

    def test_build_entries_still_patched(self, tmp_path):
        out_dir = tmp_path / "artifacts"
        out_dir.mkdir()
        built = {"repo": "ok/one", "slug": "ok-one", "version": "2026.10.14.abc1234",
                 "packageHash": "a" * 64, "manifestHash": "b" * 64,
                 "asset": "ok-one-2026.10.14.abc1234.zip",
                 "attestationFile": "ok-one.attestation.json",
                 "permissions": {}, "platforms": [], "minWorkBuddyVersion": "",
                 "skills": ["x"], "bytes": 10, "excluded": {"excludedFiles": 0,
                                                            "excludedBytes": 0}}
        (out_dir / "report.json").write_text(json.dumps(
            {"built": [built], "failed": [], "excluded": []}), encoding="utf-8")
        reg = tmp_path / "plugins.json"
        reg.write_text(json.dumps({"schema": 1, "plugins": [
            {"repo": "ok/one", "trust": "reviewed"}]}), encoding="utf-8")
        rc = build_artifacts.main(["--patch-registry", "--out", str(out_dir),
                                   "--registry", str(reg),
                                   "--release-tag", "registry-artifacts-2026-10-14"])
        assert rc == 0
        e = json.loads(reg.read_text(encoding="utf-8"))["plugins"][0]
        assert e["packageHash"] == "a" * 64
        assert "registry-artifacts-2026-10-14" in e["packageUrl"]
