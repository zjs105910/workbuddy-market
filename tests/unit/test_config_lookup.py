# -*- coding: utf-8 -*-
"""配置查询的「复用已校验配置」口径（build_state 提速的回归钉子）。

背景：classify_skill → needs_exact → verify_mode → load_config。load_config
每次都读盘 + 全量校验（validate_config 对每个 skill 跑 ensure_child，
本机实测一次约 11ms），而分类时调用方手里**本来就有**校验过的 cfg。
build_state 每次刷新要分类全部 skill，实测 41 次读盘、约 567ms；
给 verify_mode / needs_exact 加可选 cfg 后降到 1 次、约 32ms。

这里钉住两件事：
  · 传 cfg 与不传 cfg 的**结论必须一致**（否则等于偷偷改了校验档位）；
  · 批量分类路径上**不再读盘**（否则性能修复会被下一次重构悄悄抹掉）。
"""
from __future__ import annotations

import json

import pytest

from workbuddy_market import config as cfgmod
from workbuddy_market import uninstaller


def _write_config(monkeypatch, tmp_path, verify):
    """把 load_config 的读取目标指到临时配置；路径常量是 import 期求值的。"""
    p = tmp_path / "market.config.json"
    p.write_text(json.dumps({
        "marketId": "test-market",
        "localPlugins": [],
        "remoteSources": [],
        "packaging": {"verify": verify},
    }), encoding="utf-8")
    monkeypatch.setattr(cfgmod, "CONFIG_PATH", p)


class TestVerifyModeWithCfg:
    @pytest.mark.parametrize("verify", ["auto", "fast", "strict"])
    def test_cfg_matches_disk(self, monkeypatch, tmp_path, verify):
        _write_config(monkeypatch, tmp_path, verify)
        cfg = cfgmod.load_config()
        assert cfgmod.verify_mode(cfg) == cfgmod.verify_mode() == verify

    def test_bad_shaped_cfg_falls_back_to_auto(self):
        # 传入的 cfg 只取值不再校验，形状不对按 auto —— 与「配置不可用」同方向
        assert cfgmod.verify_mode({}) == "auto"
        assert cfgmod.verify_mode({"packaging": "x"}) == "auto"
        assert cfgmod.verify_mode({"packaging": {"verify": "???"}}) == "auto"
        assert cfgmod.verify_mode(None) == "auto"       # 不传：自己读（无配置文件）

    def test_disk_still_read_when_cfg_omitted(self, monkeypatch, tmp_path):
        _write_config(monkeypatch, tmp_path, "strict")
        assert cfgmod.verify_mode() == "strict"          # 无参旧行为不变


class TestNeedsExactWithCfg:
    @pytest.mark.parametrize("verify", ["auto", "fast", "strict"])
    def test_same_verdict_as_disk(self, monkeypatch, tmp_path, verify):
        _write_config(monkeypatch, tmp_path, verify)
        cfg = cfgmod.load_config()
        for purpose in ("ui", "install", "uninstall"):
            assert cfgmod.needs_exact(purpose, cfg) == cfgmod.needs_exact(purpose)

    def test_strict_makes_ui_exact(self):
        strict = {"packaging": {"verify": "strict"}}
        assert cfgmod.needs_exact("ui", strict) is True
        assert cfgmod.needs_exact("ui", {}) is False          # auto：状态页用指纹
        assert cfgmod.needs_exact("uninstall", {}) is True     # 破坏性操作一律精确

    def test_unknown_purpose_still_rejected(self):
        with pytest.raises(ValueError):
            cfgmod.needs_exact("bogus", {"packaging": {}})


class TestBatchClassifyDoesNotReload:
    def test_plan_with_cfg_never_touches_disk(self, monkeypatch):
        """plugin_uninstall_plan 拿到 cfg 后，整批分类不该再读一次配置。"""
        def _boom():
            raise AssertionError("批量分类又去读盘了（性能回归）")
        monkeypatch.setattr(cfgmod, "load_config", _boom)
        monkeypatch.setattr(uninstaller, "load_config", _boom)
        cfg = {"marketId": "test-market",
               "localPlugins": [{"name": "bundle-one", "skills": ["alpha", "beta"]}],
               "packaging": {"verify": "auto"}}
        plan = uninstaller.plugin_uninstall_plan("bundle-one", cfg, purpose="ui")
        assert plan["ok"] and plan["absent"] == ["alpha", "beta"]

    def test_classify_without_cfg_still_works(self):
        """不传 cfg 的单次调用保持旧语义：needs_exact 自己读盘。"""
        cfg = {"marketId": "test-market", "localPlugins": [], "packaging": {}}
        assert uninstaller.classify_skill("bundle-one", "nope", cfg,
                                         purpose="ui")["kind"] == "absent"
