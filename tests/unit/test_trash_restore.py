# -*- coding: utf-8 -*-
"""回收站 restore 的纯输入防线（v2.40）—— 全部只读，不碰本机状态。

端到端闭环、事务与服务端接口在 `selftest/round40.py`；这里只钉住
「不可信状态文件里的字段怎么解析」这一层，防止后续重构悄悄放宽口径：

  · 恢复唯一认的指纹形状（64 位小写 hex，不能是廉价指纹或空串）；
  · 索引里的 skill 名必须单层 basename，origin 绝不参与路径构造；
  · doctor 的「脏条目名」判定必须与内核 `_trash_entry` 完全同口径。
"""
from __future__ import annotations

from workbuddy_market import doctor
from workbuddy_market.paths import TRASH_DIR
from workbuddy_market.trash import (
    _hash_ok, _restore_skill_name, _trash_entry, restore_from_trash,
)


class TestTreeHashShape:
    def test_valid_sha256(self):
        assert _hash_ok("a" * 64)
        assert _hash_ok("0123456789abcdef" * 4)

    def test_rejects_everything_else(self):
        for value in ("", None, 123, "z" * 64, "A" * 64, "a" * 63,
                      "a" * 65, "a" * 64 + "\n", {"hash": "a" * 64}):
            assert not _hash_ok(value), repr(value)


class TestRestoreSkillName:
    def test_plain_basename(self):
        assert _restore_skill_name({"skill": "my-skill"}) == "my-skill"
        assert _restore_skill_name({"skill": "中文技能"}) == "中文技能"

    def test_rejects_path_shapes(self):
        for value in ("../evil", "..", ".", "", "a/b", "a\\b", "C:evil",
                      "a\x00b", None, 42, ["a"]):
            assert _restore_skill_name({"skill": value}) is None, repr(value)

    def test_missing_field(self):
        assert _restore_skill_name({}) is None
        assert _restore_skill_name({"origin": "/tmp/absolute/evil"}) is None


class TestTrashEntry:
    def test_valid_basename_stays_inside_trash(self):
        p = _trash_entry("20261106-120000__alpha__uninstall")
        assert p is not None and p.parent == TRASH_DIR

    def test_rejects_bad_names(self):
        for name in ("..", ".", ".index.json", "../x", "a/b", "C:\\x",
                     "a\x00b", "", 42, None):
            assert _trash_entry(name) is None, repr(name)


class TestDoctorParity:
    def test_same_verdict_as_kernel(self):
        for name in ("ok__uninstall", "..", ".index.json", "../x",
                     "leftover.partial", "C:\\x", 42, ""):
            assert doctor._bad_entry_name(name) == (_trash_entry(name) is None), repr(name)


class TestKernelSurface:
    def test_restore_entrypoint_exists(self):
        assert callable(restore_from_trash)
