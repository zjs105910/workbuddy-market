#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ghpm 入口 —— 保持 ``python ghpm.py <cmd>`` 这个调用方式不变。

v4 把 2721 行的实现拆进了同目录的 ``ghpm/`` 包（见 ghpm/__init__.py 的模块图）。
这个文件只剩下三件事：

1. 把脚本所在目录放进 ``sys.path``（直接跑脚本时 Python 不会自动加，
   而包导入需要它）；
2. 统一 stdout/stderr 编码（Windows 默认 GBK，会把中文进度打成乱码）；
3. 调用 ``ghpm.cli.main()``。

三种调用方式都可用：
    python ghpm.py list
    python -m ghpm list        （在 scripts/ 目录下）
    import ghpm; ghpm.install(...)

为了兼容「把本文件当模块加载」的老用法（例如旧版测试里的
``spec_from_file_location("ghpm", "ghpm.py")``），这里用 ``__getattr__``
把属性访问转发给真正的包 —— 所以 ``m.load()`` / ``m.install_targets(...)``
这类写法不会因为拆分而失效。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

if sys.version_info < (3, 10):
    print("ghpm 需要 Python 3.10+，当前 %d.%d" % sys.version_info[:2], file=sys.stderr)
    sys.exit(2)

from ghpm.cli import main  # noqa: E402


def __getattr__(name):
    """把 ghpm.py 当模块用时，属性访问转发给 ghpm 包。"""
    import ghpm as _pkg
    try:
        return getattr(_pkg, name)
    except AttributeError:
        raise AttributeError("module 'ghpm' has no attribute %r" % name)


if __name__ == "__main__":
    raise SystemExit(main())
