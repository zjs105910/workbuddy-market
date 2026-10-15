# -*- coding: utf-8 -*-
"""v2.35.2 两项修复的回归钉子：

1. safe_extract_tar 的包内文件符号链接物化（wshobson/agents 等条目
   因上游 CLAUDE.md -> README.md 链接整包拒建、被迫回落 ghpm 的修复）；
2. download_artifact 网络失败的人话化（agent-browser 工件下载失败时
   原样抛 urlopen 异常的修复）。
"""
import io
import sys
import tarfile
import urllib.error
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "scripts"
for p in (str(_REPO_ROOT), str(_SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import build_artifacts as bld  # noqa: E402
from workbuddy_market import artifact as art  # noqa: E402
from workbuddy_market.errors import ArtifactError  # noqa: E402

_PREFIX = "owner_repo-abc123"


def _mk_tar(path: Path, entries) -> None:
    """entries: [(name, kind, payload)]；kind: file / dir / sym（payload=linkname）。"""
    with tarfile.open(path, "w:gz") as tf:
        for name, kind, payload in entries:
            full = f"{_PREFIX}/{name}" if _PREFIX else name
            if kind == "dir":
                ti = tarfile.TarInfo(full)
                ti.type = tarfile.DIRTYPE
                tf.addfile(ti)
            elif kind == "sym":
                ti = tarfile.TarInfo(full)
                ti.type = tarfile.SYMTYPE
                ti.linkname = payload
                tf.addfile(ti)
            else:
                ti = tarfile.TarInfo(full)
                ti.size = len(payload.encode("utf-8"))
                tf.addfile(ti, io.BytesIO(payload.encode("utf-8")))


class TestSymlinkMaterialization:
    def test_file_symlink_is_materialized(self, tmp_path):
        """CLAUDE.md -> README.md（上游常见形态）→ 物化成普通文件。"""
        t = tmp_path / "t.tar.gz"
        _mk_tar(t, [
            ("skills/a/SKILL.md", "file", "---\nname: a\n---\n"),
            ("README.md", "file", "# real content"),
            ("CLAUDE.md", "sym", "README.md"),
        ])
        mat: list = []
        root = bld.safe_extract_tar(t, tmp_path / "x", materialized=mat)
        claude = root / "CLAUDE.md"
        assert claude.is_file() and not claude.is_symlink()
        assert claude.read_text(encoding="utf-8") == "# real content"
        assert mat == [{"from": "CLAUDE.md", "to": "README.md"}]

    def test_chained_symlink_resolves(self, tmp_path):
        """a -> b -> 普通文件：链式解析（≤8 跳）。"""
        t = tmp_path / "t.tar.gz"
        _mk_tar(t, [
            ("skills/a/SKILL.md", "file", "---\nname: a\n---\n"),
            ("guide.md", "file", "# guide"),
            ("AGENTS.md", "sym", "docs/AGENTS.md"),
            ("docs/AGENTS.md", "sym", "../guide.md"),
        ])
        root = bld.safe_extract_tar(t, tmp_path / "x")
        assert (root / "AGENTS.md").read_text(encoding="utf-8") == "# guide"

    def test_symlink_into_subdir_resolves(self, tmp_path):
        """相对路径带子目录的链接目标（build_one 端到端前置）。"""
        t = tmp_path / "t.tar.gz"
        _mk_tar(t, [
            ("skills/a/SKILL.md", "file", "---\nname: a\n---\n"),
            ("skills/a/real.txt", "file", "payload"),
            ("skills/a/link.txt", "sym", "real.txt"),
        ])
        root = bld.safe_extract_tar(t, tmp_path / "x")
        assert (root / "skills" / "a" / "link.txt").read_text(encoding="utf-8") == "payload"

    def test_dir_symlink_rejected(self, tmp_path):
        """指向目录的链接无法物化 → fail-closed 整包拒绝。"""
        t = tmp_path / "t.tar.gz"
        _mk_tar(t, [
            ("skills/a/SKILL.md", "file", "---\nname: a\n---\n"),
            ("skills/real", "dir", None),
            ("alias", "sym", "skills/real"),
        ])
        with pytest.raises(ArtifactError, match="目录或缺失目标"):
            bld.safe_extract_tar(t, tmp_path / "x")

    def test_dangling_symlink_rejected(self, tmp_path):
        t = tmp_path / "t.tar.gz"
        _mk_tar(t, [
            ("skills/a/SKILL.md", "file", "---\nname: a\n---\n"),
            ("ghost.md", "sym", "no-such-file.md"),
        ])
        with pytest.raises(ArtifactError, match="目录或缺失目标"):
            bld.safe_extract_tar(t, tmp_path / "x")

    def test_escaping_symlink_rejected(self, tmp_path):
        """解析后出包（a/../../out）→ 拒绝。"""
        t = tmp_path / "t.tar.gz"
        _mk_tar(t, [
            ("skills/a/SKILL.md", "file", "---\nname: a\n---\n"),
            ("docs/x.md", "file", "x"),
            ("docs/evil", "sym", "../../outside.md"),
        ])
        with pytest.raises(ArtifactError, match="出包"):
            bld.safe_extract_tar(t, tmp_path / "x")

    def test_absolute_symlink_rejected(self, tmp_path):
        t = tmp_path / "t.tar.gz"
        _mk_tar(t, [
            ("skills/a/SKILL.md", "file", "---\nname: a\n---\n"),
            ("evil", "sym", "/etc/passwd"),
        ])
        with pytest.raises(ArtifactError, match="不在包内"):
            bld.safe_extract_tar(t, tmp_path / "x")

    def test_loop_symlink_rejected(self, tmp_path):
        t = tmp_path / "t.tar.gz"
        _mk_tar(t, [
            ("skills/a/SKILL.md", "file", "---\nname: a\n---\n"),
            ("a1", "sym", "a2"),
            ("a2", "sym", "a1"),
        ])
        with pytest.raises(ArtifactError, match="成环"):
            bld.safe_extract_tar(t, tmp_path / "x")

    def test_hardlink_still_rejected(self, tmp_path):
        """收紧范围只有符号链接：硬链接 / 设备成员维持整包拒绝。"""
        t = tmp_path / "t.tar.gz"
        with tarfile.open(t, "w:gz") as tf:
            ti = tarfile.TarInfo(f"{_PREFIX}/hard.md")
            ti.type = tarfile.LNKTYPE
            ti.linkname = f"{_PREFIX}/skills/a/SKILL.md"
            tf.addfile(ti)
        with pytest.raises(ArtifactError, match="非常规成员"):
            bld.safe_extract_tar(t, tmp_path / "x")


class TestDownloadErrorHumanized:
    """download_artifact 的网络失败必须翻成人话（v2.35.2）。"""

    def test_urllib_error_connection_refused(self, tmp_path):
        def fake_fetch(url, timeout=0):
            raise urllib.error.URLError(
                ConnectionRefusedError(10061, "由于目标计算机积极拒绝，无法连接。"))
        with pytest.raises(ArtifactError, match="连不上 GitHub") as ei:
            art.download_artifact("https://example.com/x.zip", tmp_path,
                                  fetch=fake_fetch)
        assert "网络问题" in str(ei.value)
        assert not list(tmp_path.glob("*.part")) and not list(tmp_path.glob("*.zip"))

    def test_http_404_hint(self, tmp_path):
        def fake_fetch(url, timeout=0):
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, io.BytesIO(b""))
        with pytest.raises(ArtifactError, match="HTTP 404") as ei:
            art.download_artifact("https://example.com/gone.zip", tmp_path,
                                  fetch=fake_fetch)
        assert "清理或不存在" in str(ei.value)

    def test_midstream_oserror_reports_bytes(self, tmp_path):
        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self, n):
                raise OSError("connection reset mid-stream")
        def fake_fetch(url, timeout=0):
            return FakeResp()
        with pytest.raises(ArtifactError, match="连不上或中断"):
            art.download_artifact("https://example.com/x.zip", tmp_path,
                                  fetch=fake_fetch)
        assert not list(tmp_path.glob("*.part"))
