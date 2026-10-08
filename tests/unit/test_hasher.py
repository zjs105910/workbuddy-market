# -*- coding: utf-8 -*-
"""hasher / 哈希口径（纯函数，全平台）。"""
import hashlib

import market_core as core
import workbuddy_market.hasher as wh


class TestNormalizeSha256:
    def test_bare_hex(self):
        assert wh.normalize_sha256("a" * 64) == "a" * 64

    def test_prefixed_and_casefold(self):
        assert wh.normalize_sha256("sha256:" + "A" * 64) == "a" * 64
        assert wh.normalize_sha256(" " + "b" * 64 + " ") == "b" * 64

    def test_bad_values(self):
        assert wh.normalize_sha256("xyz") is None
        assert wh.normalize_sha256("c" * 63) is None
        assert wh.normalize_sha256("d" * 65) is None
        assert wh.normalize_sha256(42) is None
        assert wh.normalize_sha256(None) is None

    def test_reexport_identity(self):
        assert core.normalize_sha256 is wh.normalize_sha256


class TestSha256File:
    def test_matches_hashlib(self, tmp_path):
        p = tmp_path / "f.bin"
        data = b"X" * (3 * 1024 * 1024 + 7)      # 跨多个 1MiB 块
        p.write_bytes(data)
        assert wh.sha256_file(p) == hashlib.sha256(data).digest()

    def test_chunk_size_override(self, tmp_path):
        p = tmp_path / "f.txt"
        p.write_bytes(b"hello world")
        assert wh.sha256_file(p, chunk_size=4) == hashlib.sha256(b"hello world").digest()


class TestFingerprintFromIndex:
    def test_shape(self):
        idx = {"a": (10, 111), "b": (5, 222)}
        fp = wh.fingerprint_from_index(idx, links=("l",))
        assert fp == {"files": 2, "bytes": 15, "mtime_ns_max": 222,
                      "mtime_ns_sum": 333, "links": 1}

    def test_empty(self):
        fp = wh.fingerprint_from_index({})
        assert fp["files"] == 0 and fp["bytes"] == 0 and fp["mtime_ns_max"] == 0
