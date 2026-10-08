# -*- coding: utf-8 -*-
"""build_artifacts.fallback_version：0.0.0 回退的替代口径（v2.18，评审 8）。"""
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "scripts"
for p in (str(_REPO_ROOT), str(_SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import build_artifacts  # noqa: E402
from workbuddy_market.config import validate_version  # noqa: E402

_SHA = "3e2a429abcdef0123456789abcdef0123456789a"
_FIXED = datetime(2026, 10, 8, 12, 0, 0, tzinfo=timezone.utc)


class TestFallbackVersion:
    def test_format_and_length(self):
        v = build_artifacts.fallback_version(_SHA, _FIXED)
        assert v == "2026.10.08.3e2a429"
        assert len(v) <= 64

    def test_passes_validate_version(self):
        # 与包 manifest 同一口径：回退出来的版本必须能过包校验闸
        validate_version(build_artifacts.fallback_version(_SHA, _FIXED), "包 version")

    def test_short_sha_is_7_chars(self):
        v = build_artifacts.fallback_version(_SHA, _FIXED)
        assert re.fullmatch(r"\d{4}\.\d{2}\.\d{2}\.[0-9a-f]{7}", v)

    def test_deterministic_for_same_inputs(self):
        assert (build_artifacts.fallback_version(_SHA, _FIXED)
                == build_artifacts.fallback_version(_SHA, _FIXED))

    def test_different_sha_different_version(self):
        other = "a" + _SHA[1:]
        assert (build_artifacts.fallback_version(_SHA, _FIXED)
                != build_artifacts.fallback_version(other, _FIXED))

    def test_no_now_uses_current_time(self):
        # 不传 now 时取当前 UTC：只验形状，不钉具体日期
        assert re.fullmatch(r"\d{4}\.\d{2}\.\d{2}\.[0-9a-f]{7}",
                            build_artifacts.fallback_version(_SHA))
