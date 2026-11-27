# -*- coding: utf-8 -*-
"""_walk_tree 的相对路径口径（扫描提速的回归钉子）。

scanner._walk_tree 原来对每个文件做 Path(e.path).relative_to(root)：每个文件
要构造两个 PurePath 再逐段比对，占整次扫描约 3/4 的时间。现在改成「e.path
去掉根前缀」的字符串切片 —— 剖面里快 3~4 倍（492 个文件 14.2ms → 3.6ms）。

_scan 是打包 / 校验 / 安装暂存 / 内容哈希 / 回收站计量的共同底座，相对路径
就是 manifest 的 files 键、所有权指纹的口径 —— 键错一个字符，整条供应链校验
就全错。所以这里用 pathlib 的旧算法当参照，逐键钉死等价性。
"""
from __future__ import annotations

import os
from pathlib import Path

from workbuddy_market.scanner import _scan, _make_excluder


def _reference_keys(root: Path) -> set:
    """旧算法：pathlib.relative_to(...).replace('\\\\', '/')。"""
    out = set()
    for p in root.rglob("*"):
        if p.is_file():
            out.add(str(p.relative_to(root)).replace("\\", "/"))
    return out


def _make_tree(root: Path) -> None:
    dirs = ["", "a", "a/b", "a/b/c", "中文 目录", "with'space", "x-y_z"]
    for d in dirs:
        (root / d).mkdir(parents=True, exist_ok=True)
        (root / d / ("f" + d.replace("/", "_") + ".md")).write_text("x", encoding="utf-8")
    # 排除目标：目录与文件各一
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "x.pyc").write_bytes(b"\x00")
    (root / "a" / "notes.pyc").write_bytes(b"\x00")


def test_keys_match_pathlib_reference(tmp_path):
    root = tmp_path / "skill"
    _make_tree(root)
    files, links = _scan(root)
    assert links == []
    assert set(files) == _reference_keys(root)
    assert "a/b/c/fa_b_c.md" in files           # 嵌套
    assert "f.md" in files                      # 根层文件没有前导分隔符
    assert "中文 目录/f中文 目录.md" in files    # 空白 / 非 ASCII
    assert "with'space/fwith'space.md" in files
    assert files["a/b/c/fa_b_c.md"][0] == 1     # (size, mtime_ns) 的形状不变


def test_excluder_still_applies(tmp_path):
    root = tmp_path / "skill"
    _make_tree(root)
    ex = _make_excluder(["__pycache__"], ["*.pyc"])
    files, _ = _scan(root, ex)
    assert files and not any("__pycache__" in k or k.endswith(".pyc") for k in files)
    assert set(files) == {k for k in _reference_keys(root)
                          if "__pycache__" not in k and not k.endswith(".pyc")}


def test_root_given_with_trailing_separator(tmp_path):
    """根带尾分隔符时切片起点差 1 —— 不能把首段目录名吃掉，也不能留前导斜杠。"""
    root = tmp_path / "skill"
    (root / "sub").mkdir(parents=True)
    (root / "sub" / "SKILL.md").write_text("x", encoding="utf-8")
    plain, _ = _scan(root)
    sep = os.sep
    trailing, _ = _scan(str(root) + sep)
    assert plain == trailing == {"sub/SKILL.md": plain["sub/SKILL.md"]}


def test_missing_root_is_empty(tmp_path):
    files, links = _scan(tmp_path / "nope")
    assert files == {} and links == []
