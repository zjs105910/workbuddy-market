# -*- coding: utf-8 -*-
"""skill 发现：从 ZIP 索引或本地目录里认出 ``<任意深度>/skills/<name>/SKILL.md``。

v4 的 index_source_tree() 把「找 skill」和「量体积」并进**同一次**遍历：

    v3.2  find_skill_dirs()  rglob("*.md")   ← 遍历 1
          path_size_bytes()  rglob("*")      ← 遍历 2
          每个 skill 子目录再各 rglob("*")     ← 遍历 3..N
    v4    index_source_tree() 一次 scandir 递归，同时产出技能清单 / 全树体积 / 各技能体积

顺带把 os.scandir 换成底层调用：DirEntry 自带 stat 结果，
比 ``rglob + f.stat()`` 少一次系统调用 / 每项。
"""
from __future__ import annotations

import re
from pathlib import Path

from .models import SourceIndex, TreeStats
from .util import iter_tree


def match_skill_path(parts) -> str | None:
    """判断是否 <任意深度>/skills/<name>/SKILL.md，是则返回 skill 名。
    注意仓库里的 skills 目录不一定在顶层：oh-story-dsh 就是
    packages/knowledge/oh-story/skills/<name>/SKILL.md。"""
    if len(parts) < 3:
        return None
    if parts[-1].lower() != "skill.md":
        return None
    if parts[-3].lower() != "skills":
        return None
    name = parts[-2]
    return name or None


def skill_name_from_meta(d: Path, fallback: str) -> str:
    """单 skill 仓库用 SKILL.md frontmatter 里的 name，没有就用仓库名"""
    f = Path(d) / "SKILL.md"
    try:
        txt = f.read_text(encoding="utf-8", errors="replace")[:2000]
    except Exception:
        return fallback
    m = re.search(r"^name:\s*[\"']?([A-Za-z0-9_.-]+)[\"']?\s*$", txt, re.M)
    return (m.group(1) if m else fallback) or fallback


def index_source_tree(root, fallback: str = "") -> SourceIndex:
    """一次遍历拿到：技能清单 + 整树体积 + 每个 skill 目录的体积。

    技能识别规则与 v3.2 find_skill_dirs 完全一致（包括「按路径排序先到先得」
    和「根目录单个 SKILL.md 算单 skill 仓库」两条），只是合并到同一次遍历里。
    """
    root = Path(root)
    stats = TreeStats()
    skill_mds: list = []
    # 目录 → 该目录下**直接**文件的字节数；比记每个文件省内存（大仓库 20 万文件时差一个量级）
    dir_file_bytes: dict = {}

    for d, e in iter_tree(root):
        try:
            if e.is_dir(follow_symlinks=False):
                stats.dirs += 1
                continue
            if not e.is_file(follow_symlinks=True):
                continue
            size = e.stat(follow_symlinks=True).st_size
        except OSError:
            continue
        stats.files += 1
        stats.bytes += size
        dir_file_bytes[d] = dir_file_bytes.get(d, 0) + size
        if e.name.lower() == "skill.md":
            skill_mds.append(Path(e.path))

    out: dict = {}
    for f in sorted(skill_mds):        # 与 sorted(root.rglob("*.md")) 同序
        try:
            parts = f.relative_to(root).parts
        except ValueError:
            continue
        name = match_skill_path(parts)
        if name and name not in out:
            out[name] = f.parent
    if not out and (root / "SKILL.md").is_file():
        out[skill_name_from_meta(root, fallback or root.name)] = root

    skills = [(k, out[k]) for k in sorted(out)]
    skill_bytes = _bucket_by_skill(root, out, dir_file_bytes)
    return SourceIndex(root=root, stats=stats, skills=skills, skill_bytes=skill_bytes)


def _bucket_by_skill(root: Path, out: dict, dir_file_bytes: dict) -> dict:
    """把「每个目录自己的文件字节」归到它所属的 skill 名下。

    沿祖先链上溯（深度有限），命中 skill 目录就归它 —— O(目录数 × 深度)，
    比「对每个 skill 再遍历一遍子树」少一个量级。
    """
    skill_dir_to_name = {p: k for k, p in out.items()}
    result = {k: 0 for k in out}
    for d, size in dir_file_bytes.items():
        cur = d
        for _ in range(64):
            name = skill_dir_to_name.get(cur)
            if name is not None:
                result[name] += size
                break
            if cur == root:
                break
            parent = cur.parent
            if parent == cur:
                break
            cur = parent
    return result


def find_skill_dirs(root: Path, fallback: str = ""):
    """在本地解压目录里找 skill，返回 [(name, dirPath)]。

    两种形态都认：① 多 skill 包 .../skills/<name>/SKILL.md
                ② 单 skill 仓库 —— 根目录直接一个 SKILL.md
    保留这个入口是为了兼容既有调用方；实现已并进 index_source_tree。
    """
    return index_source_tree(root, fallback).skills
