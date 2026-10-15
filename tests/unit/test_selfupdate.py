# -*- coding: utf-8 -*-
"""selfupdate（v2.36 市场本体更新检查）的回归钉子。

重点盯防：
  · 版本比较纯函数（段数不齐 / 相等 / 大小）；
  · tag 形态不对 → 如实报告拿不到，绝不猜；
  · 网络失败 → updateAvailable=None + 人话 error，绝不伪装「已是最新」；
  · 有更新 / 无更新两条路的判定与升级指引存在。
"""
import sys
import urllib.error
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for p in (str(_REPO_ROOT), str(_REPO_ROOT / "src")):
    if p not in sys.path:
        sys.path.insert(0, p)

from workbuddy_market import selfupdate as su  # noqa: E402


class TestParseTagAndCompare:
    def test_parse_tag_with_and_without_v(self):
        assert su.parse_tag("v2.36.0") == (2, 36, 0)
        assert su.parse_tag("2.36.0") == (2, 36, 0)

    @pytest.mark.parametrize("bad", ["", "v2", "v2.36", "latest", "v2.36.0-beta",
                                     "vX.Y.Z", None])
    def test_parse_tag_rejects_malformed(self, bad):
        assert su.parse_tag(bad) is None

    def test_compare_versions(self):
        assert su.compare_versions("2.36.0", "2.35.2") == 1
        assert su.compare_versions("2.35.2", "2.36.0") == -1
        assert su.compare_versions("2.36.0", "2.36.0") == 0
        assert su.compare_versions("2.36", "2.36.0") == 0      # 段数不齐补零

    def test_compare_rejects_non_numeric(self):
        with pytest.raises(ValueError):
            su.compare_versions("2.36.0", "beta")


class TestCheckForUpdate:
    def test_update_available(self):
        def fake_fetch(url=None, timeout=0):
            return {"tag_name": "v9.9.9"}
        r = su.check_for_update(current="2.36.0", fetch=fake_fetch)
        assert r["updateAvailable"] is True
        assert r["latest"] == "9.9.9" and r["latestTag"] == "v9.9.9"
        assert r["howToUpdate"] and "install.cmd" in r["howToUpdate"][0]

    def test_no_update_when_same_or_older(self):
        r = su.check_for_update(current="9.9.9", fetch=lambda u=None, t=0: {"tag_name": "v9.9.9"})
        assert r["updateAvailable"] is False
        r2 = su.check_for_update(current="10.0.0", fetch=lambda u=None, t=0: {"tag_name": "v9.9.9"})
        assert r2["updateAvailable"] is False

    def test_malformed_tag_reported_not_guessed(self):
        r = su.check_for_update(current="2.36.0", fetch=lambda u=None, t=0: {"tag_name": "hello"})
        assert r["updateAvailable"] is None
        assert "形态不对" in r["error"]

    def test_network_failure_humanized(self):
        def fake_fetch(url=None, timeout=0):
            raise urllib.error.URLError(ConnectionRefusedError(10061, "拒绝"))
        r = su.check_for_update(current="2.36.0", fetch=fake_fetch)
        assert r["updateAvailable"] is None
        assert "连不上 GitHub" in r["error"]
        assert "已是最新" not in r["error"]          # 绝不伪装

    def test_malformed_json_payload(self):
        r = su.check_for_update(current="2.36.0", fetch=lambda u=None, t=0: None)
        assert r["updateAvailable"] is None

    def test_default_current_from_version_module(self):
        from workbuddy_market.version import MARKET_VERSION
        r = su.check_for_update(fetch=lambda u=None, t=0: {"tag_name": "v0.0.1"})
        assert r["current"] == MARKET_VERSION
        assert r["updateAvailable"] is False
