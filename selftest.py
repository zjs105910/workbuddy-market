# -*- coding: utf-8 -*-
"""selftest —— 本机插件市场的离线自检（v2.7）。

    python selftest.py            隔离模式：在临时目录里跑完整流程
    python selftest.py --real     只读检查现网状态，不写任何东西

隔离模式会造 3 个假 skill + 一份假配置，完完整整走一遍
「打包 → 安装 → 更新 → 卸载 → 回滚 → 加锁 → 日志轮转」，
**不碰真实的 ~/.workbuddy，也不动真实的插件市场目录**。

第 16 节   故障注入
第 17/18 节 v2.2：快速指纹误判、回收站路径穿越、大小写碰撞、删除失败统计
第 19 节   v2.3：事务日志、本地 API 鉴权、任务生命周期、扫描复用
第 20 节   v2.4：凭证前置、恢复校验 expected hash、卸载事务、真 tail
第 21 节   v2.5：并发压力、扫描失败 fail-closed、崩溃点矩阵
第 22 节   v2.6：ghpm 事件解析、取消竞态、进程树终止、真并发闸门
第 23 节   v2.7/R1：三层根目录、WBM_* 环境变量、运行时迁移（含跨卷回退）
第 24 节   v2.8/R2：src/workbuddy_market 包拆分——符号同一性、注入点保留、
           MARKET_ROOT fallback 盯防、包级功能冒烟
第 25 节   v2.9/R3：config / scanner / sync / version 迁入——同一性、注入点
           命名空间迁移（_walk_tree 跟随 scanner）、功能冒烟
第 26 节   v2.10：GitHub 动态目录——catalog 模块（缓存 / TTL / 失败保旧值 /
           坏缓存容错）、全网搜索解析、服务端三接口端到端（假接缝，零网络）
第 27 节   v2.11：社区注册表——registry 模块（解析 / 三路兜底 / TTL 缓存 /
           source 如实标注）、build_registry 的 refresh_entry、
           GET /api/registry 端到端、Windows 假空闲端口修复盯防
第 28 节   v2.13：跨卷回收站原子化（同卷 rename / 跨卷 复制-校验-落位-删源、
           校验失败源不动、重解析点拒绝跨卷）、API v1 版本化别名
           （鉴权前置、端到端等价）、doctor 体检（结构 / 渲染 / cli 分发）
第 29 节   v2.14/R5：installer / uninstaller 迁包——re-export 同一性、
           core 注入点晚绑定端到端（quick_fingerprint / tx_begin 拦截
           包内编排）、模块归属盯防（24B 已扩展）
第 30 节   v2.15：Market Package pack / verify——规范化 JSON 确定性、
           重打包哈希稳定、四类攻击面（改文件 / 塞文件 / 改清单 /
           路径穿越）、链接拒绝、平台 force 口径、依赖声明形状
第 31 节   v2.16：包接入安装链——registry 不可变产物字段 + trust
           fail-closed、artifact 流式下载（假接缝）、zip 安全解包
           （zip-slip / 链接成员 / zip bomb）、prepare_package 哈希校验、
           install_package_skills / install_from_entry 事务安装、
           packageHash 进 ownership 与事务恢复补记、build_registry
           last-known-good
第 32 节   v2.17：WorkBuddy Adapter（register 迁出 + patch 落点随迁 +
           能力矩阵）、/static 白名单端到端、Web 拆分发货一致性、
           build_artifacts（safe tar / 三种收录形态 / build_one 端到端
           假接缝 / --patch-registry 回写）
第 33 节   v2.19：R6 收尾 —— state / application 迁包 + core 收成兼容
           shim（符号同一性 / 归属盯防 / patch 语义回归 / shim 防膨胀）
第 34 节   v2.20：permissions（pack 形状 fail-fast / verify 攻击面 /
           风险预览三档）、兼容性检测（平台 + 宿主版本三态口径）、
           构建证明 attestation（build_one 对账 / patch-registry 回写 /
           registry 成套采纳 / fail-closed）、detect_host_version、
           cli verify 端到端
第 35 节   v2.21：收藏（本机持久化 / 形状不可信 / casefold 去重）、
           注册表结构化解析（嵌套 source/artifact/compatibility/trust/
           quality 与平铺等价）、截图域名白名单（fail-closed）、
           cli list / search 包级查询
第 36 节   v2.22：onboard 首次启动向导 —— 配置缺失自动初始化
           （独占创建 / 防覆盖 / 异常清理）、损坏配置字节级保留、
           模板缺失诚实报错、并发初始化、非交互不等待、
           回车=只浏览、注册闸门语义、全新克隆真子进程启动端到端
第 37 节   v2.23：信息架构 / 安装四问 —— trust fail-closed（后端
           回归 + 前端 fail-open 源码盯防）、四问结构、审核范围
           「未提供」不推断、三入口 tab 与高级信息折叠发货盯防、
           分类筛选控件原生 button
第 38 节   v2.24：结构化错误 / doctor Web 入口 —— 错误分类与
           retryable、内部错误不泄原文、不谎称「未受影响」、
           路径脱敏、/api/doctor 只读端到端 + 403 门禁、
           --status 配置缺失人话出口
第 39 节   v2.25：开源入门体验 —— 演示截图与采集脚本盯防、
           Quick Start / 平台矩阵 / FAQ 专节发货盯防
第 40 节   v2.27：更新后 latestSha 回写 —— ghpm 实测 sha 进注册
           表缓存、无关仓库与无 sha 行不动、get_registry 立即可见、
           _registry_drift 前 7 位比对（短 sha 回写不产生假 409）
第 41 节   v2.28：CLI 口径诚实化 / zip 市场构建清单

`SELFTEST_VERSION` 与内核的 `market_core.MARKET_VERSION` 必须同号 ——
自检里有一条用例专门盯这个，防止文档版本漂移（v2.3 时就漂过一次）。

布局（v2.34 拆分，原 5603 行单体 → selftest/ 包，逐字搬迁）：
    selftest/__init__.py    共享基础设施（隔离环境 / ck·sk·section / 夹具 / 链接助手）
    selftest/runner.py      main + run 编排（轮次调度顺序即契约）
    selftest/core_flow.py   第 1-15 节（打包/安装/卸载/锁/日志/回收站/注册）
    selftest/faults.py      第 16-18 节（故障注入 / 异常状态安全 / 扫描次数）
    selftest/roundNN.py      第 19 节起各评审轮次（模块名 = 轮次函数名，区间见各模块 docstring）
"""

from __future__ import annotations

import sys
from pathlib import Path

# 仓库根进 sys.path（selftest/ 包内的 __init__ 会幂等地再插一次）：
# 直接跑本文件时 sys.path[0] 已是仓库根，这里是防御显式调用。
sys.path.insert(0, str(Path(__file__).resolve().parent))

from selftest.runner import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
