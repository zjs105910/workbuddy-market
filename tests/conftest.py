# -*- coding: utf-8 -*-
"""pytest 试点（v2.17 新增）—— 开发者测试框架的最小起点。

定位（v3-roadmap P1，评审 9）：selftest.py 保留为「零依赖、一键环境
诊断」，pytest 承担开发者日常回归。本目录只收**纯函数层**用例
（hasher / registry 解析 / packaging / artifact），不依赖磁盘状态、
零网络 —— 全平台可跑（CI 的 Windows + Ubuntu 矩阵都会执行）。

环境隔离纪律与 selftest 相同：必须在**首次导入** workbuddy_market 之前
设置 WBM_* 环境变量（paths 常量是 import 期求值的），所以这里用模块级
代码而不是 fixture —— pytest 收集测试文件之前就会加载 conftest。
"""
import os
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))      # market_core 在仓库根

_ROOT = tempfile.mkdtemp(prefix="wbm-pytest-")
os.environ["WBM_MARKET_ROOT"] = os.path.join(_ROOT, "market")
os.environ["WBM_HOME"] = os.path.join(_ROOT, "wb")
os.makedirs(os.environ["WBM_MARKET_ROOT"], exist_ok=True)
os.makedirs(os.path.join(_ROOT, "wb", "skills"), exist_ok=True)
os.makedirs(os.path.join(_ROOT, "wb", "plugins"), exist_ok=True)
