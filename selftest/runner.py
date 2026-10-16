# -*- coding: utf-8 -*-
"""编排层（v2.34 拆出）：main 入口 + run 主流程调度。

轮次顺序与 v2.34 之前的 selftest.py 完全一致——``core_flow()`` 是原
``run()`` 的内联主体（第 1-15 节），其后的调度块逐字未动。"""
from __future__ import annotations

import shutil
import sys

from . import PASS, FAIL, SKIP, _ISOLATED, _TMP, check_real, core
from .core_flow import core_flow
from .faults import faults
from .round04 import round4
from .round05_06 import round5
from .round05_06 import round6
from .round07_10 import round7
from .round07_10 import round8
from .round07_10 import round9
from .round07_10 import round10
from .round11_12 import round11
from .round11_12 import round12
from .round13_15 import round13
from .round13_15 import round14
from .round13_15 import round15
from .round16_17 import round16
from .round16_17 import round17
from .round18_20 import round18
from .round18_20 import round19
from .round18_20 import round20
from .round21_26 import round21
from .round21_26 import round22
from .round21_26 import round23
from .round21_26 import round24
from .round21_26 import round25
from .round21_26 import round26
from .round27 import round27


def run() -> None:
    """主流程：核心流程 + 各评审轮次。调度顺序即契约，勿随意调。"""
    core_flow()
    # ============ 16. 故障注入 ============
    faults()

    # ============ 19. 第四轮：事务边界 + 本地 API ============
    round4()

    # ============ 20. 第五轮：事务闭环 + 真 tail + 鉴权加固 ============
    round5()

    # ============ 21. 第六轮：并发压力 + 扫描失败 + 崩溃点矩阵 ============
    round6()

    # ============ 22. 第七轮：ghpm 事件解析 / 取消竞态 / 进程树 ============
    round7()

    # ============ 23. 开源重构 R1：运行时目录分离 + WBM_* 环境变量 ============
    round8()

    # ============ 24. 开源重构 R2：src/workbuddy_market 基础设施包 ============
    round9()

    # ============ 25. 开源重构 R3：config / scanner / sync / version 迁入 ============
    round10()

    # ============ 26. v2.10：GitHub 动态目录（catalog + 搜索 + 服务接口） ============
    round11()

    # ============ 27. v2.11：社区注册表（registry + CI 重建 + 端口修复） ============
    round12()

    # ============ 28. v2.13：跨卷回收站原子化 + API v1 + doctor ============
    round13()

    # ============ 29. v2.14：R5 安装/卸载迁包 ============
    round14()

    # ============ 30. v2.15：Market Package pack / verify ============
    round15()

    # ============ 31. v2.16：包接入安装链（artifact → verify → 事务安装） ============
    round16()

    # ============ 32. v2.17：WorkBuddy Adapter / 静态服务 / 产物源 ============
    round17()

    # ============ 33. v2.19：R6 收尾（state / application 迁包 + core shim） ============
    round18()

    # ============ 34. v2.20：permissions / 兼容性检测 / 构建证明 ============
    round19()

    # ============ 35. v2.21：收藏 / 注册表结构化 / 截图 / CLI 查询 ============
    round20()

    # ============ 36. v2.22：onboard 首次启动向导 / 配置安全初始化 ============
    round21()

    # ============ 37. v2.23：信息架构 / 安装四问 / 信任 fail-closed ============
    round22()

    # ============ 38. v2.24：结构化错误 / doctor Web 入口 / 路径脱敏 ============
    round23()

    # ============ 39. v2.25：开源入门体验（Quick Start / 平台矩阵 / 截图） ============
    round24()

    # ============ 40. v2.27：更新后 latestSha 回写 / 漂移前缀口径 ============
    round25()

    # ============ 41. v2.28：CLI 口径诚实化 / zip 市场构建清单 ============
    round26()
    # ============ 42. v2.37：市场根显式升级 / ZIP 安全与版本校验 ============
    round27()


def main() -> int:
    if not _ISOLATED:
        return check_real()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(f"本机插件市场 自检 v{core.MARKET_VERSION}（隔离模式）\n临时根目录：{_TMP}\n")
    try:
        run()
    finally:
        if _TMP and _TMP.exists():
            shutil.rmtree(_TMP, ignore_errors=True)

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed"
          + (f", {len(SKIP)} skipped" if SKIP else ""))
    if SKIP:
        print("跳过项（环境不具备，不是通过）：")
        for s in SKIP:
            print("  - " + s)
    if FAIL:
        print("失败项：")
        for f in FAIL:
            print("  - " + f)
    return 1 if FAIL else 0
