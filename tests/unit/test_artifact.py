# -*- coding: utf-8 -*-
"""packaging / artifact 纯函数层：pack-verify 确定性与 zip 攻击面。"""
import hashlib
import zipfile

import pytest

import market_core as core
import workbuddy_market.artifact as ar
import workbuddy_market.errors as werr
import workbuddy_market.packaging as pk


def _make_src(tmp_path):
    src = tmp_path / "src"
    (src / "skills" / "alpha").mkdir(parents=True)
    (src / "skills" / "alpha" / "SKILL.md").write_text(
        "---\nname: alpha\nversion: 1.0.0\n---\n# alpha\n", encoding="utf-8")
    (src / "skills" / "alpha" / "x.txt").write_text("X" * 32, encoding="utf-8")
    return src


class TestPackVerify:
    def test_pack_and_verify_roundtrip(self, tmp_path):
        src = _make_src(tmp_path)
        r1 = pk.pack_package(src, tmp_path / "p1", pid="demo", name="D", version="1.0.0")
        r2 = pk.pack_package(src, tmp_path / "p2", pid="demo", name="D", version="1.0.0")
        assert r1["packageHash"] == r2["packageHash"]        # 重打包哈希稳定
        v = pk.verify_package(tmp_path / "p1")
        assert v["ok"] and v["packageHash"] == r1["packageHash"]

    def test_tamper_rejected(self, tmp_path):
        src = _make_src(tmp_path)
        pk.pack_package(src, tmp_path / "p1", pid="demo", name="D", version="1.0.0")
        (tmp_path / "p1" / "skills" / "alpha" / "x.txt").write_text("Y" * 32, encoding="utf-8")
        assert not pk.verify_package(tmp_path / "p1")["ok"]

    def test_extra_file_rejected(self, tmp_path):
        src = _make_src(tmp_path)
        pk.pack_package(src, tmp_path / "p1", pid="demo", name="D", version="1.0.0")
        (tmp_path / "p1" / "evil.txt").write_text("x", encoding="utf-8")
        assert not pk.verify_package(tmp_path / "p1")["ok"]

    def test_canonical_json(self):
        assert pk.canonical_json({"b": 1, "a": 2}) == b'{"a":2,"b":1}'
        assert pk.canonical_json({"k": "中"}) == '{"k":"中"}'.encode("utf-8")


class TestUnpackZip:
    def _zip(self, tmp_path, entries, attrs=None):
        p = tmp_path / "t.zip"
        with zipfile.ZipFile(p, "w") as z:
            for name, data in entries:
                zi = zipfile.ZipInfo(name)
                if attrs and name in attrs:
                    zi.external_attr = attrs[name] << 16
                z.writestr(zi, data)
        return p

    def test_normal(self, tmp_path):
        z = self._zip(tmp_path, [("m.json", "{}"), ("skills/a/SKILL.md", "---\n")])
        u = core.unpack_zip(z, tmp_path / "out")
        assert u["ok"] and (tmp_path / "out" / "skills" / "a" / "SKILL.md").is_file()

    @pytest.mark.parametrize("name", ["../evil.txt", "a/../..//e.txt",
                                      "/abs/e.txt", "C:e.txt"])
    def test_zip_slip_rejected(self, tmp_path, name):
        z = self._zip(tmp_path, [("ok.txt", "x"), (name, "evil")])
        with pytest.raises(werr.ArtifactError):
            core.unpack_zip(z, tmp_path / "out")
        assert not (tmp_path / "out").exists()

    def test_symlink_member_rejected(self, tmp_path):
        z = self._zip(tmp_path, [("ok.txt", "x"), ("skills/lnk", "y")],
                      attrs={"skills/lnk": 0o120777})
        with pytest.raises(werr.ArtifactError):
            core.unpack_zip(z, tmp_path / "out")

    def test_size_limit(self, tmp_path):
        z = self._zip(tmp_path, [("big.bin", "x" * 100)])
        with pytest.raises(werr.ArtifactError):
            core.unpack_zip(z, tmp_path / "out", size_limit=10)


class TestDownloadArtifact:
    def test_download_and_hash(self, tmp_path, monkeypatch):
        payload = b"pkg-bytes" * 50
        want = hashlib.sha256(payload).hexdigest()

        class FakeResp:
            def __init__(self, data):
                self._b = memoryview(data)
                self._i = 0

            def read(self, n=-1):
                if self._i >= len(self._b):
                    return b""
                take = min(n if n and n > 0 else 1 << 20, len(self._b) - self._i)
                out = bytes(self._b[self._i:self._i + take])
                self._i += take
                return out

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(ar, "_artifact_open",
                            lambda u, timeout=None: FakeResp(payload))
        r = core.download_artifact("https://x.example/a.zip", tmp_path,
                                   expected_hash=want)
        assert r["ok"] and r["sha256"] == want and r["bytes"] == len(payload)

    def test_hash_mismatch_no_part_left(self, tmp_path, monkeypatch):
        class FakeResp:
            def __init__(self, data):
                self._b = memoryview(data)
                self._i = 0

            def read(self, n=-1):
                if self._i >= len(self._b):
                    return b""
                out = bytes(self._b[self._i:self._i + 4])
                self._i += 4
                return out

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(ar, "_artifact_open",
                            lambda u, timeout=None: FakeResp(b"data"))
        with pytest.raises(werr.ArtifactError):
            core.download_artifact("https://x.example/a.zip", tmp_path,
                                   expected_hash="0" * 64)
        assert not any(p.name.endswith(".part") for p in tmp_path.iterdir())
