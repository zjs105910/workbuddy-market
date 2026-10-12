# -*- coding: utf-8 -*-
"""错误码与异常类型（仿 DSH plugin-manager 的 failedAt / code 归因）。

错误码以字符串常量暴露给宿主 —— CLI 与 ``__GHPM__`` 事件协议里出现的是
这些字面量，改动它们等于破坏宿主契约，只能新增不能改名。
"""
from __future__ import annotations

# 错误码
E_INVALID_SPEC = "E_INVALID_SPEC"
E_NOT_FOUND = "E_NOT_FOUND"
E_NOT_SKILL = "E_NOT_SKILL"
E_ALREADY = "E_ALREADY"
E_NETWORK = "E_NETWORK"
E_TIMEOUT = "E_TIMEOUT"
E_CANCELLED = "E_CANCELLED"
E_LOCKED = "E_LOCKED"
E_CONFLICT = "E_CONFLICT"
E_WRITE = "E_WRITE"              # 本地写入失败（磁盘满 / 文件被占用 / 权限不足）
E_UNSAFE_PATH = "E_UNSAFE_PATH"  # 路径越界：拒绝操作 WB 目录之外的目标
E_BAD_ARCHIVE = "E_BAD_ARCHIVE"  # ZIP 结构异常：条目过多 / 单文件过大 / 设备名 / 压缩炸弹


class UnsafePathError(RuntimeError):
    """路径越界。单独一类，便于 CLI 归因成 E_UNSAFE_PATH。"""


class HttpError(RuntimeError):
    """带状态码的 HTTP 失败。

    GitHub 的 404 会返回合法 JSON，只看 curl 退出码会把「仓库不存在」
    当成「响应格式错误」，所以必须把状态码带上来。
    """

    def __init__(self, status: int, body: str, url: str):
        super().__init__("HTTP %d %s" % (status, body[:160]))
        self.status = status
        self.body = body
        self.url = url


class NotSkillError(RuntimeError):
    """仓库里没有 skills/*/SKILL.md。"""


class BadArchiveError(RuntimeError):
    """ZIP 结构不合法 / 超出安全上限。解压前抛出，此时磁盘上还没有任何改动。"""


class ConflictError(RuntimeError):
    """skill 已被别的项目占用。默认拒绝安装，除非 --force。"""

    def __init__(self, conflicts: list):
        self.conflicts = conflicts
        super().__init__("以下 skill 已被其他项目占用：%s"
                         % "、".join("%s（属 %s）" % (c["skill"], c["owner"])
                                     for c in conflicts[:6]))
