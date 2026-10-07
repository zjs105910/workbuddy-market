"""异常类型（v2.8 自 market_core.py 逐字迁入）。

三个异常分属三个子系统，但都是「调用方需要精确捕获」的公共类型，
所以集中在一个模块，供全包引用（避免环形 import）。
"""
from __future__ import annotations


class ConfigError(RuntimeError):
    """配置/索引等关键文件不可用。"""


class FileLockTimeout(RuntimeError):
    pass


class ScanError(OSError):
    """目录扫描不完整。

    `_scan` 原来遇到 OSError 就 `continue` —— 等于把「读失败」当成「这里没有文件」。
    这在状态页上顶多显示不全，但在**破坏性路径**上是真危险：同步时源端少看到一个
    文件，目标端那份就会被判成「多余」而被删掉（已用探针复现：一次读取抖动删掉了
    市场里的 2 个文件）。所以破坏性操作一律要求 fail-closed。

    继承 OSError 是刻意的：安装循环里本来就有 `except (OSError, shutil.Error)`
    的**按 skill 计**失败处理，这样"某一个 skill 读不了"只会让那一个失败，
    不会把整次安装全炸掉；而 sync 那条路上没人接，就会一路冒到调用方 ——
    正是我们要的"宁可整次同步失败也不误删"。
    """
