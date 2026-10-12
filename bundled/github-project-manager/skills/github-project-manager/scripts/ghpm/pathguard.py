# -*- coding: utf-8 -*-
"""路径安全（SafePath）。

remove / rollback 的删除目标来自清单，而清单可能被手工编辑、被旧版本写坏、
被程序自身的 bug 污染。v3.1 直接 ``rmtree(Path(hit["source_dir"]))``，
一个被改坏的清单就能删掉 ~/.workbuddy 之外的任意目录。

所有**删除类**操作统一收口到这里：先 containment 校验，再删。
越界就整条拒绝（E_UNSAFE_PATH），绝不会「跳过不认识的路径然后把剩下的删了」。
"""
from __future__ import annotations

from pathlib import Path

from . import config
from .errors import UnsafePathError
from .util import remove_path


def is_within(path: Path, root: Path) -> bool:
    """path 是否位于 root 之内（含 root 自身）。resolve 后比较，挡住 .. 与符号链接。"""
    try:
        p = Path(path).resolve()
        r = Path(root).resolve()
    except Exception:
        return False
    if p == r:
        return True
    try:
        p.relative_to(r)
        return True
    except ValueError:
        return False


def validate_managed_path(path, root: Path | None = None, what: str = "路径") -> Path:
    """确认 path 落在受管根目录内，返回 resolve 后的路径；否则抛 UnsafePathError。

    root 默认 WB。remove 只允许删 SKILLS 内与 WB 内；回滚只允许还原 WB 内。
    """
    root = Path(root or config.WB)
    p = Path(path)
    try:
        resolved = p.resolve()
    except Exception:
        resolved = p
    if not is_within(resolved, root):
        raise UnsafePathError(
            "%s 越界，拒绝操作：%s（只允许位于 %s 之内）" % (what, resolved, root))
    return resolved


def validate_skill_name(name: str) -> str:
    """skill 目录名必须是单个安全片段。

    name 来自远端仓库的目录名和清单记录，必须排除 ""、"."、".." 以及任何路径分隔符，
    否则 SKILLS / name 可能指向 skills 之外或 skills 自身。
    """
    n = str(name or "").strip()
    if not n or n in (".", "..") or "/" in n or "\\" in n or "\0" in n:
        raise UnsafePathError("非法的 skill 名称：%r" % (name,))
    return n


def skill_dir(name: str) -> Path:
    """校验过的 skill 目标目录。所有写 skill 的地方都该走它。"""
    return config.SKILLS / validate_skill_name(name)


def remove_managed_path(path, what: str = "路径") -> None:
    """删除前先做 containment 校验。删除类操作统一走这里，不要直接 remove_path。"""
    validate_managed_path(path, what=what)
    remove_path(Path(path))
