# -*- coding: utf-8 -*-
"""add：安装（install 的 CLI 适配层）。"""
from __future__ import annotations

from ..installer import install


def cmd_add(args):
    """CLI 只做参数转换，真正的安装逻辑在 installer.install。"""
    return install(args.repo, args.branch, args.allow_non_skill, args.force)
