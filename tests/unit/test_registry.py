# -*- coding: utf-8 -*-
"""registry 解析（纯函数）：artifact 字段成套采纳 + trust fail-closed。"""
import market_core as core


def _parse(plugins):
    return core.parse_registry({"schema": 1, "updatedAt": "", "plugins": plugins})


def _by_repo(parsed, repo):
    return {e["repo"]: e for e in parsed["plugins"]}[repo]


class TestArtifactFields:
    def test_flat_fields_adopted_when_complete(self):
        e = _by_repo(_parse([
            {"repo": "o/r", "packageUrl": "https://x/p.zip",
             "packageHash": "a" * 64, "manifestHash": "b" * 64,
             "version": "1.2.0"}]), "o/r")
        assert e["packageUrl"] == "https://x/p.zip"
        assert e["packageHash"] == "a" * 64
        assert e["manifestHash"] == "b" * 64
        assert e["version"] == "1.2.0"

    def test_nested_artifact_object(self):
        e = _by_repo(_parse([
            {"repo": "o/r", "artifact": {"packageUrl": "https://x/n.zip",
                                         "packageHash": "c" * 64}}]), "o/r")
        assert e["packageHash"] == "c" * 64

    def test_half_fields_dropped(self):
        p = _parse([{"repo": "o/r", "packageUrl": "https://x/h.zip"}])
        assert "packageUrl" not in p["plugins"][0]

    def test_bad_hash_dropped(self):
        p = _parse([{"repo": "o/r", "packageUrl": "https://x/x.zip",
                     "packageHash": "xyz"}])
        assert "packageHash" not in p["plugins"][0]


class TestTrustFailClosed:
    def test_typo_becomes_external(self):
        assert _by_repo(_parse([{"repo": "o/r", "trust": "offical"}]), "o/r")["trust"] == "external"

    def test_missing_becomes_external(self):
        assert _by_repo(_parse([{"repo": "o/r"}]), "o/r")["trust"] == "external"

    def test_unknown_becomes_external(self):
        assert _by_repo(_parse([{"repo": "o/r", "trust": "official-ish"}]),
                        "o/r")["trust"] == "external"

    def test_explicit_values_kept(self):
        p = _parse([{"repo": "o/a", "trust": "official"},
                    {"repo": "o/b", "trust": "reviewed"},
                    {"repo": "o/c", "trust": "external"}])
        assert [e["trust"] for e in p["plugins"]] == ["official", "reviewed", "external"]


class TestEntryHygiene:
    def test_bad_entries_skipped(self):
        parsed = _parse([{"repo": "bad"}, {"repo": 42}, "not-a-dict", {"repo": "ok/one"}])
        assert [e["repo"] for e in parsed["plugins"]] == ["ok/one"]
        assert parsed["skipped"] == 3

    def test_case_dedup(self):
        parsed = _parse([{"repo": "O/R"}, {"repo": "o/r"}])
        assert len(parsed["plugins"]) == 1 and parsed["skipped"] == 1
