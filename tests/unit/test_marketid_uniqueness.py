# -*- coding: utf-8 -*-
"""marketId 唯一性与注册冲突守卫（v2.29 修复的 P1 回归钉）。

2026-10-12 半验收实锤：向导给新 clone 恒用模板默认 marketId
「wb-local-market」，多个 clone 注册进 known_marketplaces.json 互相顶替，
--unregister 删掉共享 key —— 卸载 A 毁掉 B 的注册。本文件钉死两层修复：
  1. onboard.unique_market_id：新配置 marketId 追加路径哈希后缀（clone 级唯一）；
  2. adapters.workbuddy.check_market_id_conflict：同 key 被另一位置占用时
     注册必须拒绝（fail-closed），绝不静默覆盖。
"""
from __future__ import annotations

import hashlib

import pytest

from workbuddy_market.adapters.workbuddy import check_market_id_conflict
from workbuddy_market.config import ConfigError
from workbuddy_market.onboard import unique_market_id


class TestUniqueMarketId:
    def test_suffix_is_path_hash(self, tmp_path):
        got = unique_market_id("wb-local-market", tmp_path)
        want = hashlib.sha256(str(tmp_path).encode("utf-8")).hexdigest()[:12]
        assert got == f"wb-local-market-{want}"

    def test_different_rocks_differ(self, tmp_path):
        a = unique_market_id("wb-local-market", tmp_path / "a")
        b = unique_market_id("wb-local-market", tmp_path / "b")
        assert a != b

    def test_stable_for_same_root(self, tmp_path):
        assert unique_market_id("wb-local-market", tmp_path) == \
            unique_market_id("wb-local-market", tmp_path)

    def test_long_base_truncated_to_128(self, tmp_path):
        got = unique_market_id("m" * 128, tmp_path)
        assert len(got) <= 128 and got.startswith("m")

    def test_passes_validate_id(self, tmp_path):
        from workbuddy_market.config import validate_id
        assert validate_id(unique_market_id("wb-local-market", tmp_path),
                           "marketId")


class TestCheckMarketIdConflict:
    def test_free_key_is_ok(self, tmp_path):
        assert check_market_id_conflict({}, "m1", tmp_path) is None

    def test_same_location_is_ok(self, tmp_path):
        known = {"m1": {"installLocation": str(tmp_path)}}
        assert check_market_id_conflict(known, "m1", tmp_path) is None

    def test_other_location_rejected(self, tmp_path):
        known = {"m1": {"installLocation": str(tmp_path / "other")}}
        msg = check_market_id_conflict(known, "m1", tmp_path)
        assert msg is not None and "另一个市场" in msg

    def test_source_path_fallback_checked(self, tmp_path):
        known = {"m1": {"source": {"source": "directory",
                                   "path": str(tmp_path / "other")}}}
        assert check_market_id_conflict(known, "m1", tmp_path) is not None

    def test_non_dict_entry_is_ok(self, tmp_path):
        assert check_market_id_conflict({"m1": "garbage"}, "m1", tmp_path) is None


class TestWizardInjectsUniqueId:
    def test_init_config_writes_unique_id(self, tmp_path, monkeypatch):
        """模板默认 ID 落盘时必须已带上哈希后缀（clone 级唯一）。"""
        import json
        from workbuddy_market import onboard

        template = tmp_path / "market.config.example.json"
        template.write_text(json.dumps({
            "_comment": "t", "schemaVersion": 1,
            "marketId": "wb-local-market",
            "name": "n", "description": "d", "owner": {"name": "o"},
            "localPlugins": [], "remoteSources": [],
            "packaging": {}, "trash": {"retentionDays": 30},
        }, ensure_ascii=False), encoding="utf-8")

        root = tmp_path / "clone"
        root.mkdir()
        config_path = root / "market.config.json"
        monkeypatch.setattr(onboard, "MARKET_ROOT", root)
        monkeypatch.setattr(onboard, "CONFIG_PATH", config_path)

        rep = onboard.init_config(template)
        assert rep["action"] == "created", rep
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert data["marketId"] == unique_market_id("wb-local-market", root)
        assert data["marketId"] != "wb-local-market"

    def test_init_config_rejects_bad_template_id(self, tmp_path, monkeypatch):
        """模板 ID 非法时依旧诚实失败（注入后仍过 validate_config）。"""
        import json
        from workbuddy_market import onboard

        template = tmp_path / "market.config.example.json"
        template.write_text(json.dumps({
            "marketId": "bad id with spaces", "name": "n",
            "description": "d", "owner": {"name": "o"}, "localPlugins": [],
            "remoteSources": [], "packaging": {},
            "trash": {"retentionDays": 30},
        }), encoding="utf-8")
        root = tmp_path / "clone"
        root.mkdir()
        monkeypatch.setattr(onboard, "MARKET_ROOT", root)
        monkeypatch.setattr(onboard, "CONFIG_PATH", root / "market.config.json")

        rep = onboard.init_config(template)
        assert rep["action"] == "error"
        assert not (root / "market.config.json").exists()
