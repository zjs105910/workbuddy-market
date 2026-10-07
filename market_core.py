# -*- coding: utf-8 -*-
"""market_core —— WorkBuddy 本机插件市场的内核（v2.11）。

版本号只有一个来源：MARKET_VERSION。每一轮代码评审对应一个次版本号：
v1（初版）→ v2（第一轮）→ v2.1（第二轮）→ v2.2（第三轮）→ v2.3（第四轮）
→ v2.4（第五轮）→ v2.5（第六轮）→ v2.6（第七轮）→ v2.7（开源重构 R1）
→ v2.8（R2）→ v2.9（R3）→ v2.10（GitHub 动态目录）→ v2.11（社区注册表，
当前）。

v1 → v2 的变化（第一轮评审）：

  正确性
    · mtime 判定改用 st_mtime_ns。v1 用 int(st_mtime) 砍到秒，
      同秒内「大小不变」的修改会被漏检（已用探针复现）。
  安全
    · 安装记 ownership（.ownership.json）。v1 卸载时无条件把我方 skill 目录
      移进回收站 —— 连用户自己原有的 skill 也会被移走。现在按
      「本市场装的 / 用户改过的 / 别人的」三档处理，别人的绝不碰。
    · 删除统一走 move_to_trash()，并带保留期限与容量上限的自动清理。
  并发
    · 跨平台 FileLock（Windows msvcrt / POSIX fcntl），可重入。
  功能
    · install 支持 missing / update / force 三种模式，修掉
      「市场显示 v2、本机还是 v1」的静默不一致。
  性能
    · 目录扫描从每 skill 两遍 os.walk + 末尾一遍 rglob，收敛成
      「一次遍历出一个索引，两边索引比对」。
    · tail_log() 改成 deque(maxlen=N)，不再把整个日志读进内存。
      （I/O 仍然是整个文件 —— 真正的反向分块读在 v2.4 才做，见下。）
  可维护性
    · 日志按大小 rotation；strict JSON 便于诊断；selfcheck 升级为
      配置 ↔ 索引 ↔ 插件清单 ↔ 实际文件 四层一致性校验。

v2 → v2.1 的变化（第二轮评审）：两阶段安装（PREPARE→COPY→VERIFY→COMMIT→RECORD）、
  known_marketplaces.json 损坏时拒绝覆盖、配置边界校验、junction 防护、
  快速指纹快路径、回收站索引、日志独立锁。详见 README 第十一节。

v2.1 → v2.2 的变化（第三轮评审，把「理论上安全」推进到「故意构造异常状态也安全」）：

  P0 安全 / 正确性
    · **快速指纹不再用于破坏性判定**。指纹（文件数 / 字节 / mtime_ns 聚合）
      只在「网页状态」这种可容忍误差的场合用；install / uninstall / update
      一律走完整 tree_hash()。v2.1 让 update 也走指纹，于是「改了一个旧文件、
      大小和 mtime 都没变、而最大值由别的文件贡献」的场景会被误判成 safe
      —— 明明本地已被改过，update 却跳过覆盖（已用探针复现）。
    · **.trash/.index.json 视为不可信状态文件**。所有从索引读出的名字必须
      是单层 basename 且经 ensure_child() 约束在 TRASH_DIR 内。v2.1 直接
      `TRASH_DIR / name` 后 rmtree，索引里写一条 "../../X" 就能删掉市场根
      之外的真实目录（已用探针复现）。
    · **配置层做大小写归一**。Windows 文件系统大小写不敏感，配置里同时
      出现 "Story" 与 "story" 会指向同一个目录、互相覆盖。现在用
      casefold() 做 collision_key，全平台一律拒绝这种冲突（不让 Linux 和
      Windows 出现行为差异）。
  P1 事务 / 性能
    · move_to_trash() 的 rename 成功、索引写失败时，不再把整个业务判成失败
      —— 磁盘状态已变，报告必须如实；索引交给 trash_stats() 的自动补录自愈。
    · prune_trash() 区分「计划删」与「真删成功」：失败项计入 failed，
      freed 只累加真正删掉的体积，不再虚报。
    · SHA-256 全部改流式分块（默认 1 MiB），内存从 O(文件大小) 降到
      O(chunk)；strict 模式遇到大文件不再吃内存。
    · 安装阶段 copytree(symlinks=True) 并**拒绝含重解析点的源/暂存**，
      和打包阶段形成 defense-in-depth 闭环。
  P2 结构性
    · 打包时 destination 侧按插件只扫一次，再按 skill 前缀切片。
    · 配置加 schemaVersion / packaging.hashAlgorithm / hashChunkBytes /
      trash.protectModified；packaging.verify 支持 "auto"。
    · 版本号收敛到 MARKET_VERSION，README / 配置 / 代码 / 自检同一口径。

v2.2 → v2.3 的变化（第四轮评审：主题从「代码速度」转到「事务边界」）：

  P0 事务 / 安全
    · **ownership 纳入事务日志**（.market-tx/）。v2.2 的流程是
      COMMIT 之后再 record_owner() —— 一旦写 .ownership.json 失败，
      会出现两种坏结果：全新安装时 skill 在盘上但无所有权记录，被判成
      foreign **永久不再受本市场管辖**；更新时文件已被换掉，调用方却看到
      失败、所有权还停在旧 hash。现在装/卸全程写一份 tx journal，
      phase=committed 的残留会在下次启动时自动补记并清账。
    · **launcher 不再「一步失败也继续注册」**。打包或深度自检失败时，
      只启动只读网页，**跳过 register** —— 那条路径有外部副作用，
      会让 WorkBuddy 看到一个根本没更新成功的旧市场。
  P0 服务端
    · **本地 API 加鉴权**：启动时生成一次性 token 注入页面，所有 /api/*
      校验 X-Local-Market-Token + Origin。v2.2 里任何 origin 的网页都能
      直接 POST install / uninstall / register / purge（实测全部 200）。
    · **/api/open/path 收紧**为白名单：只接受市场根内的已知目标，
      不再把任意本机路径交给 explorer / open / xdg-open。
  P1
    · POST body 限 1 MiB（413）；坏 JSON 返回 400 而不是静默变成 {}。
    · 任务（job）加 TTL + 上限，已完成任务不再永久滞留内存。
    · ghpm 后台任务支持超时自动终止与 /api/job/<id>/cancel。
    · build_state 批量指纹扫描（一次 _scan(SKILLS_DIR) 切片）+ 短 TTL 缓存。
    · 安装复用暂存阶段已经算出的索引，不再 commit 后重扫新版本。
  P2
    · register / unregister 改成「读 → 改 → 重读 → 比对 → 重试」的乐观合并，
      缩小与 WorkBuddy 自身写文件的竞争窗口。
    · atomic_write 支持 durable=True（POSIX 上补父目录 fsync）。
    · 配置数值校验拒绝非整数与 NaN / Infinity。

v2.3 → v2.4 的变化（第五轮评审：把「事务」真正闭环，顺带修两个我自己的疏漏）：

  P0 事务闭环
    · **凭证先于磁盘变更**。v2.3 是 `_commit_staged()` 成功之后才 tx_begin() ——
      进程恰好死在那两步之间，磁盘已经是新版本、却一份日志都没留下。
      现在 tx_begin() 提到循环之前，并且**在 os.replace 之前**就把
      「换位后应该长什么样」（expected hash + 指纹）写进日志（state=staged）。
    · **恢复要校验内容，不能「看到文件在就认领」**。v2.3 只看目录是否存在，
      于是「崩 → 用户改了文件 → 恢复」会把用户的改动洗白成「市场装的、没改过」，
      之后一键卸载就会搬走它。现在逐条比对 tree_hash：一致才认领
      （state=staged 时静默放过，state=committed 时记 conflict 并**保留日志**）。
    · **卸载纳入同一套事务**。pendingForget 记「已搬进回收站、所有权还没清」
      的 skill，`forget_owner()` 成功才清账 —— 不再是「文件没了、ownership 还认它」。
  P1
    · tail_log() 换成真正的反向分块读（实测 3 份日志 22.9 MB 时，
      从「读满 28.6 MB / 1378 ms」降到「读 32 KB / 1 ms」）。
    · /api/remote/add|update 复用内核的 validate_repo()，不再只判「非空」。
    · /api/state 加 single-flight，堵住 TTL 过期瞬间的缓存击穿。
    · HTTP 连接加读写超时与接收队列长度（防慢连接占线程）。
  P2
    · launcher 换成 argparse：互斥动作、非法端口、冲突参数都有规范报错。
  （顺带修掉两个我自己的疏漏：selftest 里 `_drop_link` 用 `is_dir()` 判断类型
    会跟随链接、导致链接摘不掉；selftest 头部版本号停在 v2.2 没跟着升。）

v2.4 → v2.5 的变化（第六轮评审：重点从「再加安全补丁」转到**并发边界与 I/O 路径**）：

  P0 并发
    · **SingleFlight 的超时/异常路径也是 single-flight 了。** v2.4 是
      「leader 刷，等待线程 `ev.wait()` 之后**自己再跑一次 fn()**」——
      正常路径没问题，但 leader 超时或抛异常时，等待线程会各自重跑，
      击穿又回来了（实测「leader 抛异常 + 6 并发」→ build_state 跑了 6 次）。
      改成共享结果盒：value / error 都由 leader 填，等待线程直接取。
    · **后台任务真的有了并发上限。** MAX_JOBS 只淘汰**已完成**的任务，
      运行中的一个都不动 —— 它是「历史任务表上限」，不是并发上限。
      实测连开 140 个 running 任务，表里就真留着 140 个，每个带一条线程 +
      一个 ghpm 子进程。新增 MAX_RUNNING_JOBS 信号量，抢不到令牌直接 429。
  P1 I/O 与正确性
    · **扫描不完整 = 失败，不是「这里没有文件」。** `_scan` 原来遇到 OSError 就
      `continue`，于是在同步里「源端少看见一个文件」会被解读成「目标端那份是多余的」
      → **删掉市场里的内容**（实测一次读取抖动删了 2 个文件）。
      现在 `_scan(..., on_error=)` 显式区分：状态展示可以 skip，
      sync / install / uninstall 一律 fail-closed（抛 ScanError）。
      ScanError 继承 OSError，所以安装循环里「一个 skill 读不了」只让那一个失败，
      而同步那条路没人接就会一路冒到调用方 —— 宁可整次同步失败也不误删。
    · **批量扫描只走声明的 skill，不再整树扫。** `SkillScanCache` 原来
      `_scan(SKILLS_DIR)` 然后再按前缀切，市场只声明 6 个 skill 却要扫
      406 个目录 / 2842 个文件（实测 223 ms）。现在 `_scan_many()` 只走声明的
      子树，并在扫描时就**按名字分桶** —— 顺带解决 `_sub_index` 每个 skill
      都要遍历一遍完整索引的问题（6 个 skill = 17124 次迭代）。
      实测：223 ms → 72 ms。
    · **回收站索引整批只落一次盘。** `TrashIndex` 把索引提到内存，
      批量装/卸做完 flush 一次，不再是「搬一个 → 读 → 改 → 原子写」× N。
  P2 工程化
    · launcher 加 `--json` / `--quiet`，方便 CI / Harness 调用。

v2.5 → v2.6 的变化（第七轮评审：后台任务生命周期的最后两个边角）：

  P0 正确性 / 测试
    · **ghpm 失败事件（无 error 字段）不再抛 NameError。** v2.5 在
      `_run_ghpm()` 里引用了未定义的 `label`（探针实锤：NameError 一路冒到
      worker，`_job_finish()` 不跑，任务永远停在 running）。现在兜底为
      「ghpm 执行失败」，有 error/label 字段时优先展示原文。
    · **并发闸门测试改成了真并发。** v2.5 的用例是**串行**调 _remote_job，
      而隔离环境里 ghpm 秒失败、令牌秒还，下一个串行请求又能抢到 ——
      accepted 超过上限（探针 10/10 轮复现：上限 4，accepted 全是 10；
      之前全量自检能过纯属真实 ghpm 失败得稍慢）。现在用 barrier 让
      MAX+6 个请求同时出发、用 gate 挂住假 ghpm 保证满载可观察。
  P1 任务生命周期
    · **POSIX 上 kill_process_tree() 真的杀整棵树了。** 子进程改用
      start_new_session=True 启动（pgid == pid），取消/超时走
      os.killpg(SIGTERM → SIGKILL)，git / 凭证助手不会再变孤儿。
      Windows 的 taskkill /T 路径不变。
    · **堵上「取消发生在 Popen 前后」的竞态窗口。** Popen 之前先查
      canceled（不白白拉起进程）；Popen 之后、把 proc 挂上 job 时再查一次
      —— 若 cancel_job 恰好落在中间（那时它杀无可杀），由这里补杀。
    · **JobLimiter 取代裸信号量。** 闸门与运行计数由同一把锁保证一致，
      running_jobs() 不再读 `BoundedSemaphore._value`（私有字段）。
  暂缓（记录在案）
    · job 状态机（queued/starting/…/timeout）：值得做，但要同步改前端
      对 status/ok 的契约，放到下一轮单独做。
    · 全局 invariant 断言框架：本轮已把「并发槽归还」「无卡死任务」
      作为不变量嵌进并发用例，完整框架随状态机一起做。

v2.6 → v2.7 的变化（GitHub 开源重构 R1：运行时与仓库分离）：

  · **三层根目录**：仓库（MARKET_ROOT，产品）/ 运行状态（STATE_HOME，环境）/
    WorkBuddy 家目录（WB）各自独立。环境变量升级为 WBM_MARKET_ROOT /
    WBM_STATE_HOME / WBM_HOME；旧 GHPM_MARKET_ROOT / GHPM_HOME 兼容且每进程
    打一次 deprecation 告警。
  · **运行状态分桶**：默认收进 ~/.workbuddy-market/markets/<bucket>/
    （bucket = 仓库目录名 + MARKET_ROOT 路径哈希前 12 位），同机多个 clone 的
    state / 锁 / trash / tx 天然隔离。仅设旧变量时完全复刻 v2.6 布局（自检零改动）。
  · **运行时文件迁移**：仓库根的 .market-state / .ownership / .market-log /
    .market-tx / .backups / .trash 幂等搬进 STATE_HOME（os.replace 优先、
    跨卷退回 shutil.move；目标已存在以 STATE_HOME 为准、仓库侧原件保留）。
    锁文件无持久语义，不迁移。
  · 本轮只做行为变更与自测用例，模块拆分（R2-R6）随后分批进行；
    详见 docs/开源重构方案.md。

v2.7 → v2.8 的变化（GitHub 开源重构 R2：拆出无状态基础设施包）：

  · **src/workbuddy_market/ 包落地**：paths（三层根目录 + 全部路径常量）/
    errors（ConfigError / FileLockTimeout / ScanError）/ fsutil（原子写 + JSON）/
    hasher（流式 SHA-256 + 指纹叶子函数）/ locking（可重入文件锁）/
    logging（事件流 + 真.tail）六个模块自本文件**逐字迁入**，行为零变化。
  · quick_fingerprint / tree_hash* 因依赖 core._scan（自检崩溃注入点）与
    hash_chunk_bytes()（读配置）暂留本文件，R3 拆 config/scanner 时再走。
  · 唯一必要适配：MARKET_ROOT 的仓库根 fallback 由 ``Path(__file__).parent``
    改为 ``parents[2]``（src 布局），语义不变；有自检用例盯防。
  · market_core 仍是唯一兼容入口：re-export 全部迁出符号，selftest 的
    core.X 属性注入（_scan / tree_hash / save_ownership / tx_* 等 44 处）
    全部保持有效。

v2.8 → v2.9 的变化（GitHub 开源重构 R3：config / scanner / sync / version 迁入）：

  · 四个模块逐字迁入包内，行为零变化；注入点命名空间随之迁移
    （包内互调 patch wm.scanner._walk_tree，core 侧仍 patch core._scan）。
  · validate_config 补跨插件 skill 大小写冲突的配置期拒绝。
  · 详见 README 第十九节。

v2.9 → v2.10 的变化（GitHub 动态目录：参考 DSH 市场的「目录 / 动态数据」分层）：

  · **src/workbuddy_market/catalog.py 新模块**：收录源的实时元数据
    （stars / pushed_at / 描述）+ GitHub 全网搜索。网络接缝只有
    `_gh_request()` 一处，自检 monkeypatch 它离线测试全部逻辑。
  · **易变数据不进配置**（provider-api.md 设计稿的口径）：动态元数据
    缓存在 STATE_HOME 的 catalog.json（TTL 24 小时），remoteSources
    继续只承担静态身份；展示层优先用实时值，配置里的 stars 退为快照。
  · **容错口径**：单仓库失败保留旧值并记 errors；整轮全败不更新
    refreshedAt（失败不算刷新过，自动循环按 TTL 继续重试）；
    缓存损坏当不存在。
  · **服务端**：GET /api/catalog、GET /api/gh/search（口令 + Origin、
    词长上限、120 秒内存缓存）、POST /api/catalog/refresh（走
    JobLimiter 的后台任务）。serve() 起 daemon 线程每 15 分钟检查、
    过期即自动刷新（make_server 不起线程，自检零网络依赖）；
    WBM_CATALOG_OFF=1 可关。
  · **前端**：收录源卡片显示实时星数 / 更新日期 + 「刷新目录」按钮；
    本地搜索无结果且关键词 ≥2 字时自动搜 GitHub 全网，结果卡片
    可直接「一键安装」（仍走 ghpm 的任务进度 / 取消 / 超时链路）。

v2.10 → v2.11 的变化（社区注册表：DSH 市场那层「registry 仓库」的本机实现）：

  · **src/workbuddy_market/registry.py 新模块**：注册表本体就是本仓库的
    registry/plugins.json（静态提交人工审核，stars / pushedAt / latestSha
    由每日 CI 重建——scripts/build_registry.py + registry.yml）。
    市场端按 TTL 在线拉取，三条网络路线 + 本地副本兜底；网络接缝只有
    `_registry_http_get()` 一处，缓存口径与 catalog 一致（不可信文件 /
    全挂退缓存、source 如实标注来源）。
  · **Windows 假空闲端口修复**：_find_port 的探测 socket 原来设
    SO_REUSEADDR —— Windows 上它允许绑定「别的进程正监听着」的端口，
    同机三个市场进程可以同时绑 8777，请求随机打到旧进程（2026-10-07
    实测复现）。探测在 Windows 改用 SO_EXCLUSIVEADDRUSE，POSIX 沿用
    SO_REUSEADDR（Linux 上 SO_REUSEADDR 本就不允许双活监听）。
  · **服务端**：GET /api/registry（口令 + Origin、600 秒内存缓存 +
    single-flight、?force=1 强制在线拉取）；「刷新目录」后台任务
    同时刷新 catalog 与 registry。
  · **前端**：新增「社区目录」区块（与收录源大小写去重后展示），社区
    条目可直接一键安装（确认框如实标注来自社区目录）；搜索兜底同时
    看社区目录与 GitHub 全网。
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import stat
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

# ------------------------------------------------------- 基础设施包（v2.8，R2）
#
# 路径 / 错误 / 原子写 / 哈希 / 锁 / 日志已逐字迁入 src/workbuddy_market/
# （docs/开源重构方案.md §3.1、§9-R2）。本文件保留：
#   · 版本与模式常量（version.py 到 R3 再拆）
#   · 依赖 scanner / config 的组合函数（quick_fingerprint / tree_hash* 等）
#   · 其余全部业务实现
# market_core 仍是唯一兼容入口：re-export 全部迁出符号，selftest 的
# core.X 属性注入不受影响。

# --- sys.path 引导：src 布局，未安装 pip 包时也能直接 import ---
_SRC_DIR = Path(__file__).resolve().parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from workbuddy_market.paths import (          # noqa: E402,F401
    _DEPRECATED_ENVS_USED, _LEGACY_LAYOUT,
    MARKET_ROOT, STATE_HOME,
    CONFIG_PATH, MANIFEST_DIR, MANIFEST_PATH, PLUGINS_DIR, WEB_DIR,
    STATE_PATH, LOG_PATH, BACKUP_DIR, TRASH_DIR, TX_DIR, OWNERSHIP_PATH,
    LOCK_PATH, LOG_LOCK_PATH, CATALOG_PATH, REGISTRY_PATH,
    WB, SKILLS_DIR, KNOWN_PATH, GITHUB_REGISTRY, GHPM_PY,
    LOG_MAX_BYTES, LOG_KEEP, BACKUP_KEEP, HASH_CHUNK_BYTES,
)
from workbuddy_market.errors import (         # noqa: E402,F401
    ConfigError, FileLockTimeout, ScanError,
)
from workbuddy_market.fsutil import (         # noqa: E402,F401
    _fsync_dir, atomic_write_bytes, atomic_write_text, write_text_if_changed,
    read_json,
)
from workbuddy_market.hasher import (         # noqa: E402,F401
    fingerprint_from_index, sha256_file, _same_content,
)
from workbuddy_market.locking import (        # noqa: E402,F401
    FileLock, locked, _HELD, _NullLock,
)
from workbuddy_market.logging import (        # noqa: E402,F401
    now_iso, _rotate_log, log, _tail_lines, tail_log,
)
from workbuddy_market.version import (        # noqa: E402,F401
    OWNERSHIP_SCHEMA, TX_SCHEMA, STATE_VERSION, MARKET_VERSION,
)
from workbuddy_market.config import (         # noqa: E402,F401
    CLASSIFY_PURPOSES, EXACT_PURPOSES,
    _ID_RE, _REPO_RE, _VER_RE, WINDOWS_RESERVED,
    validate_id, validate_version, ensure_child, collision_key,
    _check_collision, _check_number, validate_repo,
    validate_config, load_config, verify_mode, needs_exact, hash_chunk_bytes,
)
from workbuddy_market.scanner import (        # noqa: E402,F401
    _is_reparse, _walk_tree, _raise_if_errors, _scan, _scan_many,
    file_index, SkillScanCache, _FM_RE, parse_skill_meta,
    _make_excluder, _sub_index,
)
from workbuddy_market.sync import _sync_tree  # noqa: E402,F401
from workbuddy_market.catalog import (        # noqa: E402,F401  （v2.10 新增）
    GH_API, CATALOG_TTL, GH_TIMEOUT,
    SEARCH_LIMIT_DEFAULT, SEARCH_LIMIT_MAX, MAX_QUERY, CATALOG_SCHEMA,
    _gh_request, normalize_repo_payload, validate_query,
    fetch_meta, search_repos, catalog_path,
    load_catalog, save_catalog, is_stale, refresh_catalog,
)
from workbuddy_market.registry import (       # noqa: E402,F401  （v2.11 新增）
    REGISTRY_REPO, REGISTRY_BRANCH, REGISTRY_FILENAME, REGISTRY_TTL,
    REGISTRY_TIMEOUT, REGISTRY_SCHEMA, REGISTRY_RAW_URL, REGISTRY_API_URL,
    ENV_REGISTRY_URL, _registry_http_get, registry_routes,
    local_registry_file, parse_registry, registry_path,
    load_registry_cache, save_registry_cache, get_registry,
)

INSTALL_MODES = ("missing", "update", "force")

# CLASSIFY_PURPOSES / EXACT_PURPOSES 已迁 workbuddy_market.config（v2.9 R3），
# 此处 re-export（见上方 import 块）。


# ---------------------------------------------------------------- 小工具
# now_iso / _rotate_log / log 已迁 workbuddy_market.logging（v2.8 R2），此处 re-export。


def say(msg: str = "") -> None:
    print(msg, flush=True)


# ------------------------------------------------------- 运行时迁移（v2.7，R1）

# v2.6 布局散落在仓库根的运行时文件 → v2.7 STATE_HOME 布局。
# 两个 .lock 没有持久语义，不迁移：留在原地是无害遗留（新锁直接在 locks/ 重建）。
_RUNTIME_MIGRATIONS = (
    (".market-state.json", "state.json", False),
    (".ownership.json", "ownership.json", False),
    (".market-log.ndjson", "logs/market.ndjson", False),
    (".market-log.ndjson.1", "logs/market.ndjson.1", False),
    (".market-log.ndjson.2", "logs/market.ndjson.2", False),
    (".market-tx", "tx", True),
    (".backups", "backups", True),
    (".trash", "trash", True),
)


def migrate_runtime_files(quiet: bool = False) -> dict:
    """把 v2.6 留在仓库根的运行时文件搬进 STATE_HOME（v2.7 布局）。

    · 幂等：调用两遍结果一致；目标已存在时以 STATE_HOME 为准，
      仓库侧原件**保留不删**（绝不洗掉用户的文件，工程约定 5）。
    · 原子：同卷走 os.replace；跨卷（C: ↔ D: 等）OSError 退回 shutil.move。
    · 失败不致命：单条失败记入 errors 并告警，下次启动自动重试剩余项。
    · 仅 v2.7 布局生效；legacy 布局（旧自检 / harness）恒为 no-op。
    import market_core 时自动调用一次，也可手工调用检查返回值。
    """
    result = {"mode": "legacy" if _LEGACY_LAYOUT else "v2.7",
              "moved": [], "skipped": [], "errors": []}
    if _LEGACY_LAYOUT:
        return result
    for old_name, new_rel, _is_dir in _RUNTIME_MIGRATIONS:
        src = MARKET_ROOT / old_name
        dst = STATE_HOME / new_rel
        if not src.exists() and not src.is_symlink():
            continue
        if dst.exists() or dst.is_symlink():
            result["skipped"].append({"src": str(src), "dst": str(dst)})
            continue
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.replace(src, dst)
            except OSError:
                shutil.move(str(src), str(dst))     # 跨卷回退
            result["moved"].append({"src": str(src), "dst": str(dst)})
        except OSError as exc:
            result["errors"].append({"src": str(src), "error": str(exc)})
    if result["moved"] and not quiet:
        # 全新环境里 logs/ 可能还不存在（.market-log.ndjson 不在迁移清单时）——
        # log() 不会自建父目录，这里补上，保证迁移留痕不静默丢失。
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOG_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        log("info", "runtime_migrated", json.dumps(result, ensure_ascii=False))
    if result["errors"] and not quiet:
        log("warn", "runtime_migration_failed",
            json.dumps(result["errors"], ensure_ascii=False))
    return result


def _warn_deprecated_envs() -> None:
    """旧 GHPM_* 环境变量每进程只提醒一次（stderr + 事务日志各一条）。"""
    if not _DEPRECATED_ENVS_USED:
        return
    detail = "; ".join(f"{old} -> {new}" for old, new in _DEPRECATED_ENVS_USED)
    print(f"WARNING: deprecated environment variable(s): {detail}", file=sys.stderr)
    try:
        log("warn", "deprecated_env", detail)
    except Exception:
        pass


# _fsync_dir / atomic_write_* / write_text_if_changed / read_json 已迁
# workbuddy_market.fsutil（v2.8 R2），此处 re-export。


# ---------------------------------------------------------------- 配置校验
# validate_* / ensure_child / collision_key / validate_config / load_config /
# verify_mode / needs_exact / hash_chunk_bytes 已迁 workbuddy_market.config
# （v2.9 R3），此处 re-export（见上方 import 块）。


# ---------------------------------------------------------------- 文件锁
# FileLockTimeout / _HELD / FileLock / locked / _NullLock 已迁
# workbuddy_market.locking（v2.8 R2），此处 re-export。


# ---------------------------------------------------------------- 文件索引 / 指纹
# _is_reparse / _walk_tree / _raise_if_errors / _scan / _scan_many /
# file_index / SkillScanCache / parse_skill_meta / _make_excluder / _sub_index
# 已迁 workbuddy_market.scanner（v2.9 R3），此处 re-export。
# 注意：包内互调（file_index→_scan、_scan_many→_walk_tree 等）走 scanner
# 命名空间，patch `core._scan/_walk_tree` 只对 core 侧直接调用有效
# （如 _sync_packaging / _stage_skill / prune_trash）；需要拦截包内路径时
# patch workbuddy_market.scanner 里的名字（selftest 第 19 节已按此调整）。


# ScanError 已迁 workbuddy_market.errors（v2.8 R2），此处 re-export。


# fingerprint_from_index / sha256_file / _same_content 已迁
# workbuddy_market.hasher（v2.8 R2），此处 re-export。
# quick_fingerprint / tree_hash* 留在这里：它们依赖 core._scan
# （selftest 崩溃注入点）与 hash_chunk_bytes()（读配置），R3 再迁。


def quick_fingerprint(root: Path, excluded=None) -> dict:
    """廉价指纹：只看文件数 / 总字节 / mtime_ns 的**和与最大值**，不读内容。

    ⚠️ 定位：**候选状态**判定，不是「内容没改」的证明。

    只比 max(mtime_ns) 有个真实盲区：A 文件 mtime=1000（最大），B 文件 mtime=100，
    用户改了 B（内容变了、大小没变、mtime 仍 <= 1000）—— files / bytes / max
    三者可以完全不变。所以这里再加一个 mtime_ns_sum：**任何一个文件的时间戳变了，
    和就会变**，能堵掉绝大多数这类情况（已经不依赖「最大值恰好是那个文件」）。

    但它仍然只是启发式：内容变了而 size 与 mtime 都原样（刻意构造/工具回写）
    依然可能骗过它。因此**破坏性操作一律不用它** —— 见 needs_exact()。
    """
    files, links = _scan(root, excluded)
    return fingerprint_from_index(files, links)


def tree_hash_from_index(root: Path, index: dict, chunk_size: int | None = None) -> str:
    """从**已经扫好的**索引算内容指纹（仍然要读文件内容，但不重扫目录）。"""
    h = hashlib.sha256()
    cs = chunk_size or hash_chunk_bytes()
    base = Path(root)
    for rel in sorted(index):
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        try:
            h.update(sha256_file(base / rel, cs))
        except OSError:
            h.update(b"<unreadable>")
        h.update(b"\0")
    return h.hexdigest()


def tree_hash(root: Path, excluded=None, chunk_size: int | None = None,
              *, on_error: str = "raise") -> str:
    """目录内容指纹：只跟内容有关（含相对路径），不含时间戳。

    用来判断「这个 skill 还是不是我当初装进去的那个」。**要读全部文件**，
    所以只在需要精确判定时调用（install / uninstall / strict 状态检查）。

    on_error 默认 "raise"：这个哈希会被用来决定「能不能安全卸载」或
    「要不要覆盖」，扫不全时给一个"看起来对得上"的值比报错危险得多。
    """
    return tree_hash_from_index(root, file_index(root, excluded, on_error=on_error),
                                chunk_size)


# ---------------------------------------------------------------- skill 元信息 / 打包辅助
# SkillScanCache / _FM_RE / parse_skill_meta / _make_excluder / _sub_index
# 已随 scanner 迁入 workbuddy_market.scanner（v2.9 R3），此处 re-export。


TRASH_INDEX_PATH = TRASH_DIR / ".index.json"

# 索引里不允许出现的字符：路径分隔符、盘符、以及 Windows 的非法字符
_TRASH_NAME_BAD = ("/", "\\", ":", "\x00")


def _load_trash_index() -> dict:
    d = read_json(TRASH_INDEX_PATH, None)
    if not isinstance(d, dict) or not isinstance(d.get("items"), dict):
        return {"version": 1, "items": {}}
    return d


def _save_trash_index(idx: dict) -> None:
    idx["version"] = 1
    atomic_write_text(TRASH_INDEX_PATH, json.dumps(idx, ensure_ascii=False, indent=2) + "\n")


def _trash_entry(name) -> Path | None:
    """把索引里的一个名字解析成 .trash 内的真实路径；不合法一律返回 None。

    .index.json 是普通 JSON 文件，手工能改、也可能被投毒的包写坏 ——
    所以这里**按不可信状态文件处理**，读的时候就把恶意输入挡住：

      · 必须是字符串、非空、无 NUL
      · 不能是 "." / ".." / 索引自己
      · 必须是单层 basename：含 / \\ : 的一律拒绝
      · 最后再过 ensure_child()，把结果钉死在 TRASH_DIR 之内

    v2 是直接 `TRASH_DIR / name` 然后 rmtree —— 索引里写一条 "../../X"
    就能删掉市场根之外的真实目录。
    """
    if not isinstance(name, str) or not name:
        return None
    if name in (".", "..") or name == TRASH_INDEX_PATH.name:
        return None
    if any(ch in name for ch in _TRASH_NAME_BAD):
        return None
    if Path(name).name != name:            # 兜底：任何形式的路径成分
        return None
    try:
        return ensure_child(TRASH_DIR, TRASH_DIR / name)
    except ConfigError:
        return None


def _measure(path: Path) -> tuple:
    """(字节数, 文件数)。只用于回收站记账，所以走一次 _scan 就够。"""
    try:
        if path.is_dir():
            files, _links = _scan(path)
            return sum(v[0] for v in files.values()), len(files)
        return path.stat().st_size, 1
    except OSError:
        return 0, 0


class TrashIndex:
    """回收站索引的内存视图 —— 批量操作只落一次盘。

    `move_to_trash()` 原来是「搬一个 → 读索引 → 改 → 原子写」。批量卸载 12 个
    skill 就是 12 次读 + 12 次原子写（每次都带 fsync），纯属把同一份 JSON 反复
    重写。把索引提到内存里，整批做完 flush 一次。

    安全性上不比原来差：万一中途崩掉，那些目录只是「没登记」，
    `trash_stats()` 的未登记补录会把它们收进来。
    """

    def __init__(self):
        self._idx = _load_trash_index()
        self._dirty = False

    @property
    def items(self) -> dict:
        return self._idx["items"]

    def record(self, name: str, entry: dict) -> None:
        self.items[name] = entry
        self._dirty = True

    def forget(self, name: str) -> None:
        if self.items.pop(name, None) is not None:
            self._dirty = True

    @property
    def dirty(self) -> bool:
        return self._dirty

    def flush(self) -> bool:
        if not self._dirty:
            return False
        try:
            _save_trash_index(self._idx)
        except (OSError, ConfigError) as exc:
            log("warn", "trash", f"回收站索引回写失败（{exc}），下次刷新状态会自动补录")
            return False
        self._dirty = False
        return True


def move_to_trash(path: Path, reason: str = "", index: "TrashIndex | None" = None) -> Path | None:
    """统一入口：把一个目录/文件整个 rename 进回收站，并记账。

    刻意用 rename 而不是 rmtree：O(1)、不遍历几百个文件，
    也不会触发宿主/沙箱的「批量删除」保护。
    体积在搬之前就算好写进索引 —— 否则每次刷新状态都要重新 rglob 整个回收站。

    **事务语义**：rename 成功之后，磁盘状态就已经变了。索引只是缓存，
    写索引失败**不能**让整个调用方判成失败 —— 否则会出现「旧版本已经被搬进
    回收站，调用方却以为操作没发生」。所以这里降级为记一条 warn 并照常返回，
    索引由 trash_stats() 的「未登记项自动补录」自愈。

    index: 传一个 `TrashIndex` 就只在内存里记账，由调用方在整批做完后 flush；
           不传就当场读写索引（单次操作的默认行为）。
    """
    path = Path(path)
    if not path.exists():
        return None
    TRASH_DIR.mkdir(parents=True, exist_ok=True)

    size, nfiles = _measure(path)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    tag = f"{stamp}__{path.name}"
    if reason:
        tag += f"__{reason}"
    dst = TRASH_DIR / tag
    n = 1
    while dst.exists():
        dst = TRASH_DIR / f"{tag}.{n}"
        n += 1
    try:
        shutil.move(str(path), str(dst))
    except OSError as exc:
        log("error", "trash", f"回收 {path} 失败：{exc}")
        return None

    entry = {"bytes": size, "files": nfiles, "at": time.time(),
             "reason": reason or "unknown", "origin": str(path)}
    if index is not None:
        index.record(dst.name, entry)
    else:
        own_idx = TrashIndex()
        own_idx.record(dst.name, entry)
        own_idx.flush()
    return dst


def trash_config() -> dict:
    """回收站清理策略，来自 market.config.json 的 trash 段。"""
    try:
        cfg = load_config()
    except ConfigError:
        cfg = {}
    t = cfg.get("trash") or {}
    return {
        "max_age_days": float(t.get("maxAgeDays", 30) or 0),
        "max_bytes": int(t.get("maxSizeBytes", 2 * 1024 ** 3) or 0),
        "protect_modified": bool(t.get("protectModified", True)),
    }


def trash_stats() -> dict:
    """回收站清单。

    v2 是每次都对整个 .trash 做 rglob，回收站一大（配置允许到 2GB）状态页就明显变慢。
    现在优先读索引；只有「磁盘上有、索引里没有」的情况（比如你手工往里拖了东西）
    才重新扫一遍，并顺手补进索引。

    索引里的非法条目名（路径穿越之类）会被剔除并记警告，绝不按它去访问磁盘。
    """
    if not TRASH_DIR.is_dir():
        return {"count": 0, "bytes": 0, "items": []}

    idx = _load_trash_index()
    recorded = idx["items"]
    items, total = [], 0
    seen = set()
    dirty = False

    for name, rec in list(recorded.items()):
        target = _trash_entry(name)
        if target is None:
            log("warn", "trash", f"索引里的条目名非法，已剔除：{name!r}")
            del recorded[name]
            dirty = True
            continue
        if not target.exists():
            continue                       # 已被手工删掉 → 稍后从索引里剔除
        seen.add(name)
        if not isinstance(rec, dict):
            rec = {}
        size = int(rec.get("bytes", 0) or 0)
        at = float(rec.get("at", 0) or 0) or _safe_mtime(target)
        items.append({"name": name, "size": size, "mtime": at,
                      "reason": rec.get("reason", "")})
        total += size

    # 磁盘上有、索引里没有的（手工拖进去的 / 索引丢了）
    try:
        children = list(TRASH_DIR.iterdir())
    except OSError:
        children = []
    for child in children:
        if child.name == TRASH_INDEX_PATH.name or child.name in seen:
            continue
        size, nfiles = _measure(child)
        at = _safe_mtime(child)
        items.append({"name": child.name, "size": size, "mtime": at, "reason": "未登记"})
        recorded[child.name] = {"bytes": size, "files": nfiles, "at": at,
                                "reason": "未登记", "origin": ""}
        total += size
        seen.add(child.name)
        dirty = True

    # 索引里有、磁盘上没了 → 剔除
    for name in [n for n in list(recorded) if n not in seen]:
        del recorded[name]
        dirty = True

    if dirty:
        try:
            _save_trash_index(idx)
        except (OSError, ConfigError) as exc:
            log("warn", "trash", f"回收站索引回写失败（{exc}），本次只在内存里修正")

    items.sort(key=lambda x: x["mtime"])
    return {"count": len(items), "bytes": total, "items": items}


def _safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def prune_trash(force: bool = False, quiet: bool = False) -> dict:
    """按配置清理回收站：先按保留天数，再按容量上限（从最旧的开始）。

    这是本工具唯一的「真删除」，只作用于 .trash/ 内部，
    而且只在超过阈值时才动 —— 不配阈值就等于永不清理。

    统计口径：**removed 只数真正删成功的**，freed 只累加这些项的字节，
    删失败的进 failed。v2 用 `except OSError: continue` 后照原计划累加，
    计划删 10 个、实际成功 8 个也会报 removed=10 / freed=500MB —— 说谎的统计
    比崩溃更麻烦。

    force=True 表示「用户明确要求清空」，此时不受保护项与阈值约束。
    """
    conf = trash_config()
    st = trash_stats()
    idx = _load_trash_index()
    candidates = []                       # [(item, why)]
    protected = []                        # 受保护、本轮放过的
    now = time.time()

    def _is_protected(item) -> bool:
        return conf["protect_modified"] and "modified" in str(item.get("reason", ""))

    keep = list(st["items"])

    # 1) 超过保留天数（force 时不必判断：最后一步会全清）
    if conf["max_age_days"] > 0 and not force:
        cutoff = now - conf["max_age_days"] * 86400
        rest = []
        for it in keep:
            if it["mtime"] >= cutoff:
                rest.append(it)
            elif _is_protected(it):
                protected.append(it)
                rest.append(it)
            else:
                candidates.append((it, "超过保留天数"))
        keep = rest

    # 2) 超过容量上限（从最旧的开始丢）
    if conf["max_bytes"] > 0 and not force:
        total = sum(i["size"] for i in keep)
        rest = []
        for it in keep:
            if total > conf["max_bytes"] and not _is_protected(it):
                total -= it["size"]
                candidates.append((it, "超过容量上限"))
            else:
                if total > conf["max_bytes"]:
                    protected.append(it)
                rest.append(it)
        keep = rest

    # 3) force：剩下的全清
    if force:
        candidates += [(i, "手动清理") for i in keep]
        keep = []

    removed_ok, removed_failed = [], []
    for item, _why in candidates:
        target = _trash_entry(item["name"])
        if target is None:
            removed_failed.append({"name": item["name"], "error": "条目名非法，拒绝删除"})
            log("error", "trash", f"拒绝删除非法条目名：{item['name']!r}")
            continue
        try:
            stt = target.lstat()
            if stat.S_ISDIR(stt.st_mode) and not target.is_symlink() and not _is_reparse(stt):
                shutil.rmtree(target)
            elif stat.S_ISDIR(stt.st_mode):
                # 重解析点（软链 / junction）：只摘掉链接本身，绝不跟进目标
                os.rmdir(str(target))
            else:
                target.unlink()
        except OSError as exc:
            removed_failed.append({"name": item["name"], "error": str(exc)})
            log("error", "trash", f"删除 {item['name']} 失败：{exc}")
            continue
        removed_ok.append(item)
        idx["items"].pop(item["name"], None)

    if removed_ok:
        try:
            _save_trash_index(idx)
        except (OSError, ConfigError) as exc:
            log("warn", "trash", f"回收站索引回写失败（{exc}）")

    freed = sum(i["size"] for i in removed_ok)
    if removed_ok and not quiet:
        say(f"  回收站清理：移除 {len(removed_ok)} 项")
    if removed_ok or removed_failed:
        log("info" if not removed_failed else "warn", "trash",
            f"清理成功 {len(removed_ok)} 项（{freed} 字节）"
            + (f"，失败 {len(removed_failed)} 项" if removed_failed else ""))
    if protected:
        log("info", "trash", f"{len(protected)} 项受保护（安装后被改过），本轮不清理")

    return {"removed": len(removed_ok), "failed": len(removed_failed),
            "failedItems": removed_failed,
            "freed": freed, "kept": len(keep),
            "bytes": sum(i["size"] for i in keep),
            "protected": len(protected)}


def sync_packaging(quiet: bool = False) -> dict:
    """把本机 skill 打包成插件 + 生成市场索引。增量同步，可反复跑。"""
    with locked():
        # 上一次如果崩在「已落位、所有权还没写」那一步，这里补上
        rec = recover_transactions(quiet=quiet)
        return _sync_packaging(quiet=quiet, recovered=rec["recovered"])


def _sync_packaging(quiet: bool = False, recovered: list | None = None) -> dict:
    cfg = load_config()
    pack = cfg.get("packaging", {})
    excluded = _make_excluder(pack.get("excludeNames"), pack.get("excludeGlobs"))
    mode = pack.get("verify", "auto")
    if mode not in ("auto", "fast", "strict"):
        mode = "auto"
    # 打包的比对档位仍然只有「比时间戳」和「比内容」两种；
    # auto 在这里等价于 fast —— 真正需要精确的是 install / uninstall
    # 那两条路径（见 needs_exact），打包慢一点没有安全收益。
    strict = mode == "strict"

    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    manifest_plugins = []
    report = {"plugins": [], "missing": [], "cachedSkills": [], "copiedSkills": 0,
              "totalSkills": 0, "copiedFiles": 0, "removedFiles": 0, "skippedLinks": 0,
              "bytes": 0, "verify": mode, "recovered": list(recovered or [])}

    # 上次生成、这次配置里已经不要的插件 → 回收站（rename，不是删除）
    wanted = {p["name"] for p in cfg.get("localPlugins", [])}
    for existing in sorted(PLUGINS_DIR.iterdir()):
        if existing.is_dir() and existing.name not in wanted:
            retired = move_to_trash(existing, "retire")
            log("info", "sync",
                f"插件 {existing.name} 已不在配置中，移入回收站 {retired.name if retired else ''}")

    total_bytes = 0
    for spec in cfg.get("localPlugins", []):
        pname = spec["name"]
        pdir = PLUGINS_DIR / pname
        skills_root = pdir / "skills"
        skills_root.mkdir(parents=True, exist_ok=True)

        # 目标侧整树只扫一次，之后按 skill 前缀切片 ——
        # v2 是「每个 skill 扫一次目标目录」，一个 12 skill 的插件要扫 12 次。
        # 切片后：源侧仍是每 skill 一次（内容不同，必须各扫），目标侧收敛成 1 次。
        # on_error="raise"：这一步决定了紧接着要删哪些「多余文件」，
        # 看不到就等于删错 —— 必须 fail-closed。
        dst_all, _dst_links = _scan(skills_root, excluded, on_error="raise")

        present = []
        for sname in spec.get("skills", []):
            src = SKILLS_DIR / sname
            dst = skills_root / sname
            if not (src / "SKILL.md").is_file():
                report["missing"].append(f"{pname}/{sname}")
                cached = _sub_index(dst_all, sname)
                if (dst / "SKILL.md").is_file():
                    # 本机没有，但市场里还留着上次打包的副本 —— 保留。
                    # 市场是「仓库」不是「镜像」：源没了不该让货架也空掉，
                    # 否则「先卸载、再从市场装回来」这条路根本走不通。
                    present.append(sname)
                    report["cachedSkills"].append(f"{pname}/{sname}")
                    report["totalSkills"] += 1
                    total_bytes += sum(v[0] for v in cached.values())
                    log("warn", "sync", f"{sname} 本机已不存在，沿用市场里的历史副本")
                else:
                    log("warn", "sync", f"{sname} 本机不存在，且没有历史副本，跳过")
                continue
            c, r, sz, nl = _sync_tree(src, dst, excluded, strict=strict,
                                      dst_index=_sub_index(dst_all, sname))
            report["copiedFiles"] += c
            report["removedFiles"] += r
            report["skippedLinks"] += nl
            total_bytes += sz
            present.append(sname)
            report["copiedSkills"] += 1
            report["totalSkills"] += 1

        if not present:
            log("warn", "sync", f"{pname} 没有任何可用 skill，未生成插件")
            report["plugins"].append({"name": pname, "skills": 0, "skipped": True})
            continue

        # 该插件下已经不该存在的 skill 目录（本轮配置删掉了）→ 回收站
        keep = set(present)
        for child in sorted(skills_root.iterdir()):
            if child.is_dir() and child.name not in keep:
                move_to_trash(child, "retire")
                log("info", "sync", f"{pname}: skill {child.name} 已不在配置中，移入回收站")

        plugin_json = build_plugin_json(cfg, spec)
        write_text_if_changed(
            pdir / ".codebuddy-plugin" / "plugin.json",
            json.dumps(plugin_json, ensure_ascii=False, indent=2) + "\n",
        )
        write_text_if_changed(pdir / "README.md", _plugin_readme(cfg, spec, present))

        manifest_plugins.append({
            "name": pname,
            "description": spec.get("description", ""),
            "description_en": spec.get("description_en", ""),
            "version": spec.get("version", "1.0.0"),
            "source": f"./plugins/{pname}",
            "category": spec.get("category", ""),
            "author": plugin_json["author"],
            "keywords": spec.get("keywords", []),
        })
        report["plugins"].append({"name": pname, "skills": len(present), "skillsList": present})
        if not quiet:
            say(f"  [打包] {spec.get('displayName', pname)} —— {len(present)} 个 skill")
        log("info", "sync", f"{pname}: 打包 {len(present)} 个 skill")

    manifest = {
        "name": cfg.get("marketId", "wb-local-market"),
        "description": cfg.get("description", ""),
        "owner": cfg.get("owner", {}),
        "plugins": manifest_plugins,
    }
    write_text_if_changed(MANIFEST_PATH, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

    # 体积：直接用上面各 skill 索引里累加的值，不再 rglob 全量扫一遍
    report["bytes"] = total_bytes

    state = read_json(STATE_PATH, {}) or {}
    state.update({
        "version": STATE_VERSION,
        "marketVersion": MARKET_VERSION,
        "marketId": manifest["name"],
        "lastSync": now_iso(),
        "pluginCount": len(manifest_plugins),
        "skillCount": report["totalSkills"],
        "cachedCount": len(report["cachedSkills"]),
        "sizeBytes": total_bytes,
    })
    atomic_write_text(STATE_PATH, json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    return report

def build_plugin_json(cfg: dict, spec: dict) -> dict:
    """插件级清单。抽出来是因为 sync 与深度自检都要用同一份构造逻辑。"""
    author = {"name": spec.get("author", {}).get("name", cfg.get("owner", {}).get("name", ""))}
    pj = {
        "name": spec["name"],
        "version": spec.get("version", "1.0.0"),
        "description": spec.get("description", ""),
        "description_zh": spec.get("description", ""),
        "description_en": spec.get("description_en", ""),
        "author": author,
        "keywords": spec.get("keywords", []),
        "category": spec.get("category", ""),
    }
    for key in ("homepage", "repository", "license"):
        if spec.get(key):
            pj[key] = spec[key]
    return pj


def _plugin_readme(cfg: dict, spec: dict, skills: list) -> str:
    lines = [
        f"# {spec.get('displayName', spec['name'])}",
        "",
        spec.get("description", ""),
        "",
        f"- 市场：`{cfg.get('marketId')}`",
        f"- 版本：`{spec.get('version', '1.0.0')}`",
        f"- 分类：{spec.get('category', '—')}",
        "",
        "## 包含的 skill",
        "",
    ]
    for s in skills:
        meta = parse_skill_meta(MARKET_ROOT / "plugins" / spec["name"] / "skills" / s)
        lines.append(f"- **{s}** v{meta['version']} — {meta['description'][:120]}")
    lines += ["", "---", "",
              "此文件由 `launcher.py --sync` 依据 `market.config.json` 自动生成，请勿手改。", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------- 所有权

def load_ownership() -> dict:
    data = read_json(OWNERSHIP_PATH, None)
    if not isinstance(data, dict) or "skills" not in data:
        return {"version": OWNERSHIP_SCHEMA, "skills": {}}
    data.setdefault("skills", {})
    return data


def save_ownership(own: dict) -> None:
    own["version"] = OWNERSHIP_SCHEMA
    atomic_write_text(OWNERSHIP_PATH,
                      json.dumps(own, ensure_ascii=False, indent=2) + "\n",
                      durable=True)


def record_owner(plugin_id: str, skills: list, version: str,
                 snapshots: dict | None = None) -> None:
    """记下「这些 skill 是本市场这个插件装的」，并留两层指纹。

    hash         内容 SHA-256（准，但要读全部文件）
    fingerprint  文件数 / 总字节 / mtime_ns 聚合（廉价，只 stat）

    snapshots: {skill: {"hash": ..., "fingerprint": ...}}。
    安装路径会把暂存阶段已经算好的结果传进来 —— 落位用的是同一批文件、
    内容一模一样，没必要在 commit 之后把新版本整个重扫一遍再算一次哈希。
    """
    own = load_ownership()
    mid = _market_id()
    snaps = snapshots or {}
    for s in skills:
        d = SKILLS_DIR / s
        if not (d / "SKILL.md").is_file():
            continue
        pre = snaps.get(s) if isinstance(snaps.get(s), dict) else {}
        own["skills"][s] = {
            "owner": mid,
            "plugin": plugin_id,
            "version": version,
            "installedAt": now_iso(),
            "hash": pre.get("hash") or tree_hash(d),
            "fingerprint": pre.get("fingerprint") or quick_fingerprint(d),
        }
    save_ownership(own)


def _market_id() -> str:
    try:
        return load_config().get("marketId", "wb-local-market")
    except ConfigError:
        return "wb-local-market"


def forget_owner(skills: list) -> None:
    own = load_ownership()
    changed = False
    for s in skills:
        if s in own["skills"]:
            del own["skills"][s]
            changed = True
    if changed:
        save_ownership(own)


# ---------------------------------------------------------------- 事务日志
#
# v2.2 只保证「文件」这一步是事务的：
#
#     PREPARE → COPY → VERIFY → COMMIT
#
# 而 record_owner() 在 COMMIT **之后**才跑。一旦写 .ownership.json 失败，
# 有两种坏结果（都已用探针复现）：
#
#   · 全新安装 —— 文件在盘上、所有权缺失 → classify_skill 判成 foreign，
#     这个 skill 永久不再受本市场管辖（既不能更新也不能卸载）。
#   · 更新安装 —— 文件已经被换掉，调用方却看到异常；所有权停在旧 hash。
#
# 现在把「记所有权」纳入同一份日志，从「文件事务」升级成「文件 + 状态事务」：
#
#     BEGIN → COPY → VERIFY → COMMIT → WRITE_OWNERSHIP → FINALIZE
#
# 每个 skill 换位成功就立刻登记进 pendingOwnership；收尾时一次性写所有权，
# 写成功才清账。中途任何一步崩掉，下次启动 / 下次装改卸之前会自动补记。
#
# v2.3 → v2.4 又补了两条硬约束（第四轮评审，均已用探针复现）：
#
#   ① **凭证必须先于磁盘变更。** 日志要在任何可能改变正式 skill 目录的动作
#      *之前* 落盘，并且带上恢复时用来比对的 expected hash。
#      v2.3 是 commit 之后才 tx_begin() —— 进程恰好死在那两步之间，磁盘已经
#      换成新版本，却没有留下任何恢复凭证。
#
#   ② **恢复要校验内容，不能「看到文件在就认领」。** 崩溃之后、恢复之前，
#      用户完全可能自己改过那个 skill。只看「目录还在」就补记所有权，等于把
#      用户的改动**洗白**成「市场装的、没改过」—— 之后一键卸载就会搬走它。
#      只有当前内容仍等于 commit 那一份才允许认领；不一致就是 conflict，
#      保留日志并报出来。
#
# 卸载走同一套模型：pendingForget 记「已搬进回收站、所有权还没清」的 skill，
# 同样在动磁盘之前就有凭证。

_TX_ACTIVE: set = set()        # 本进程正在写的事务 id —— tx_list() 要跳过它们


def tx_path(tx_id: str) -> Path:
    """事务日志路径。tx_id 是我们自己生成的，但仍然过一遍 basename 校验 ——
    将来若有人把外部值传进来，这里就是最后一道闸。"""
    if (not isinstance(tx_id, str) or not tx_id or Path(tx_id).name != tx_id
            or any(ch in tx_id for ch in ("/", "\\", ":", "\x00"))):
        raise ConfigError(f"非法事务 id：{tx_id!r}")
    return TX_DIR / f"{tx_id}.json"


def tx_save(tx: dict) -> None:
    tx["updatedAt"] = now_iso()
    atomic_write_text(tx_path(tx["id"]),
                      json.dumps(tx, ensure_ascii=False, indent=2) + "\n",
                      durable=True)


def tx_begin(operation: str, plugin: str, skills: list, **extra) -> dict:
    """开一份事务日志。**必须在动磁盘之前调用。**

    调用点的标准不是「看着顺眼」，而是：从这里到 tx_close() 之间，无论进程
    在哪一行消失，恢复流程都能仅凭这份日志把状态推回一致。
    """
    TX_DIR.mkdir(parents=True, exist_ok=True)
    tx = {
        "schema": TX_SCHEMA,
        "id": f"{operation}-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
              f"-{time.time_ns() % 1_000_000:06d}",
        "operation": operation,
        "plugin": plugin,
        "skills": sorted(str(s) for s in skills),
        "pid": os.getpid(),
        "pendingOwnership": [],         # [{skill, hash, fingerprint, plugin, version, state}]
        "pendingForget": [],            # 已搬进回收站、所有权还没清的 skill
        "startedAt": now_iso(),
    }
    tx.update(extra)
    tx_save(tx)
    _TX_ACTIVE.add(tx["id"])
    return tx


def _tx_put(tx: dict, sname: str, **fields) -> None:
    pend = [e for e in (tx.get("pendingOwnership") or [])
            if not (isinstance(e, dict) and e.get("skill") == sname)]
    entry = {"skill": sname, "plugin": tx.get("plugin") or "",
             "version": tx.get("version") or ""}
    entry.update({k: v for k, v in fields.items() if v is not None})
    pend.append(entry)
    tx["pendingOwnership"] = sorted(pend, key=lambda e: e.get("skill", ""))


def tx_note_staged(tx: dict, sname: str, expected: dict | None = None,
                   plugin: str | None = None, version: str | None = None) -> None:
    """**换位之前**落盘：记下这次 commit 完成之后应该长什么样。

    为什么要提前记：如果只记「已交付」，那么「os.replace 成功 → 写日志」这个
    窗口里崩掉，磁盘已经是新版本、日志却什么都没写 —— 恢复流程两眼一抹黑。
    提前记下的 expected hash 就是那个窗口的凭证。

    state="staged" 表示「我打算换，但还没确认换成功」。恢复时：
      · 磁盘内容 == expected  → 其实换成功了（崩在 replace 之后）→ 认领
      · 磁盘内容 != expected  → 没换，或已被改动 → **不认领**（也不报冲突，
        因为这次交付本来就没完成）
    """
    _tx_put(tx, sname, state="staged",
            hash=(expected or {}).get("hash"),
            fingerprint=(expected or {}).get("fingerprint"),
            plugin=plugin, version=version)
    tx_save(tx)


def tx_note_committed(tx: dict, sname: str) -> None:
    """换位成功 —— 把该条目升级成 committed。

    升级之后就"交付确认"了：此后磁盘内容只要和 expected 不一致，一定是有人
    在崩溃之后改过它，恢复流程必须拒绝认领并报冲突。
    """
    for e in (tx.get("pendingOwnership") or []):
        if isinstance(e, dict) and e.get("skill") == sname and e.get("state") != "committed":
            e["state"] = "committed"
            tx_save(tx)
            return


def tx_note_removed(tx: dict, sname: str) -> None:
    """某个 skill 已经搬进回收站 —— 登记「待清所有权」。"""
    fg = set(tx.get("pendingForget") or ())
    fg.add(sname)
    tx["pendingForget"] = sorted(fg)
    tx_save(tx)


def tx_drop(tx: dict, sname: str) -> None:
    """把某条待办从日志里摘掉（收尾时用）。只改内存，由调用方决定何时 tx_save。"""
    tx["pendingOwnership"] = [
        e for e in (tx.get("pendingOwnership") or [])
        if not (isinstance(e, dict) and e.get("skill") == sname)]


def tx_settled(tx: dict) -> bool:
    """这份日志还有没有未了结的事。"""
    return not (tx.get("pendingOwnership") or tx.get("pendingForget"))


def tx_release(tx: dict) -> None:
    """操作结束了，但账还没清 —— 把日志交还给恢复流程。

    必须显式释放：`_TX_ACTIVE` 是「本进程正在改这份日志」的意思，
    如果一次安装带着未了结的条目就结束了，还把它留在 _TX_ACTIVE 里，
    同一进程里的 recover_transactions() 就永远看不到它。
    """
    _TX_ACTIVE.discard(tx["id"])


def tx_close(tx: dict) -> None:
    tx_release(tx)
    try:
        tx_path(tx["id"]).unlink()
    except OSError:
        pass


def tx_list() -> list:
    """列出还挂着的日志。**本进程正在写的不算**（按 id 认，不靠 pid 猜）。"""
    if not TX_DIR.is_dir():
        return []
    out = []
    for p in sorted(TX_DIR.glob("*.json")):
        rec = read_json(p, None)
        if not isinstance(rec, dict):
            try:
                p.unlink()
            except OSError:
                pass
            continue
        if rec.get("id") in _TX_ACTIVE:
            continue                    # 本进程正在跑的事务，别碰
        out.append(rec)
    return out


def recover_transactions(quiet: bool = True, discard_conflicts: bool = False) -> dict:
    """补账：把上一次没走完的事务收尾。

    在每次打包 / 安装 / 卸载之前，以及服务启动时调用。
    持市场锁运行 —— 同一时刻只会有一次操作，所以这里看到的日志要么属于
    已经结束的操作，要么属于已经崩掉的进程。

    **认领的条件是「内容还是当初那一份」，不是「目录还在」：**

      pendingOwnership，state="staged"    → 还没确认交付；内容对上才认领，对不上静默放过
      pendingOwnership，state="committed" → 已确认交付；内容对不上 = 有人改过 → conflict
      pendingForget                       → 目录确实不在了才清所有权；还在说明当时没搬成

    conflict 会**保留日志**并报出来：要么用户重装覆盖（内容对上了自然消解），
    要么显式 discard_conflicts=True 表示「这次的账不要了」。默认绝不替用户决定。
    """
    recovered, finished, failed, conflicts = [], [], [], []
    with locked():
        stale = _sweep_staging()
        for tx in tx_list():
            txid = tx.get("id", "?")

            # --- 认领：必须内容对得上 ---
            claim, snapshots, versions = [], {}, {}
            for entry in (tx.get("pendingOwnership") or []):
                if not isinstance(entry, dict):
                    continue
                s = entry.get("skill")
                if not isinstance(s, str):
                    continue
                d = SKILLS_DIR / s
                try:
                    ensure_child(SKILLS_DIR, d)
                except ConfigError:
                    continue
                if not (d / "SKILL.md").is_file():
                    continue            # 落位后又被人删了 → 没什么可认领
                want = entry.get("hash")
                try:
                    got = tree_hash(d)
                except ScanError as exc:
                    log("warn", "tx", f"跳过 {s}：内容读不全（{exc}），不认领")
                    conflicts.append({"tx": txid, "skill": s,
                                      "expected": want, "actual": None,
                                      "reason": "unreadable"})
                    continue
                if want and got != want:
                    if entry.get("state") == "committed":
                        # 交付确认过，现在内容却不对 —— 一定是崩溃之后有人改了它。
                        # 认领 = 把用户的改动洗白成「市场装的、没改过」。
                        conflicts.append({"tx": txid, "skill": s,
                                          "expected": want, "actual": got})
                        log("error", "tx",
                            f"拒绝认领 {s}：内容与当时 commit 的不一致"
                            f"（期望 {str(want)[:12]}…，实际 {str(got)[:12]}…）"
                            "—— 这是你的改动，本工具不会把它当成市场版本")
                    else:
                        # 还没确认交付（崩在 replace 前后）→ 这次交付本来就没完成，
                        # 不认领，也不用报警
                        log("warn", "tx",
                            f"跳过未确认交付的 {s}（内容与预期不符，本次事务未完成）")
                    continue
                claim.append(s)
                snapshots[s] = {"hash": got, "fingerprint": entry.get("fingerprint")}
                versions[s] = entry.get("version") or tx.get("version") or ""

            if claim:
                full = all(v.get("fingerprint") for v in snapshots.values())
                by_version = {}
                for s in claim:
                    by_version.setdefault(versions.get(s) or "", []).append(s)
                failed_here = False
                for ver, group in by_version.items():
                    snaps = {s: (snapshots[s] if full else {"hash": snapshots[s]["hash"]})
                             for s in group}
                    try:
                        # 按版本分组写：不能把不同版本号的 skill 混成一条记录
                        record_owner(tx.get("plugin") or "", group, ver, snapshots=snaps)
                    except (OSError, ConfigError) as exc:
                        failed.append((txid, str(exc)))
                        log("error", "tx", f"补记所有权失败（保留日志下次再试）：{txid} — {exc}")
                        failed_here = True
                        break
                    recovered.extend(group)
                    log("warn", "tx",
                        f"补记了上一次未完成的所有权记录：{', '.join(group)}")
                if failed_here:
                    continue

            # --- 清账：已搬进回收站、所有权还留着的 ---
            forgotten = [s for s in (tx.get("pendingForget") or [])
                         if isinstance(s, str) and not (SKILLS_DIR / s).exists()]
            if forgotten:
                try:
                    forget_owner(forgotten)
                    log("warn", "tx", f"补清了上一次未完成的所有权移除：{', '.join(forgotten)}")
                except (OSError, ConfigError) as exc:
                    failed.append((txid, str(exc)))
                    log("error", "tx", f"补清所有权失败（保留日志下次再试）：{txid} — {exc}")
                    continue

            # --- 收尾：了结的条目摘掉，被挡下的（冲突 / 没搬成）留着 ---
            conflict_skills = {c["skill"] for c in conflicts if c["tx"] == txid}
            if discard_conflicts:
                conflict_skills = set()
            tx["pendingOwnership"] = [
                e for e in (tx.get("pendingOwnership") or [])
                if isinstance(e, dict) and e.get("skill") in conflict_skills]
            tx["pendingForget"] = [
                s for s in (tx.get("pendingForget") or [])
                if isinstance(s, str) and (SKILLS_DIR / s).exists()]
            if tx_settled(tx):
                tx_close(tx)
                finished.append(txid)
            else:
                tx_save(tx)             # 保留日志：让人知道有笔账被挡下了

    if recovered or finished or stale or conflicts:
        log("info", "tx",
            f"事务恢复：补记 {len(recovered)} / 清账 {len(finished)}"
            f" / 冲突 {len(conflicts)} / 清暂存 {stale}")
    if not quiet and (recovered or finished or conflicts):
        say(f"  事务恢复：补记所有权 {len(recovered)} 项，清理残留日志 {len(finished)} 份")
        for c in conflicts:
            say(f"  ! 拒绝认领 {c['skill']}：内容已被改动，未记为本市场版本")
    return {"recovered": recovered, "finished": finished, "failed": failed,
            "conflicts": conflicts, "stagingSwept": stale}


def classify_skill(plugin_id: str, sname: str, cfg: dict, own: dict | None = None,
                   purpose: str = "ui", always_hash: bool | None = None,
                   scan_cache: "SkillScanCache | None" = None) -> dict:
    """判断一个 skill 当前该归哪一档。网页界面与卸载都靠它。

    返回 kind: absent / safe / modified / foreign / other_plugin

    **准不准由 purpose 决定**，而不是由调用方随手传一个开关：

      ui         网页状态。允许用廉价指纹，快；判错只是显示不准。
      install    决定要不要覆盖本机文件 → 必须 READ 内容。
      uninstall  决定要不要把用户目录搬进回收站 → 必须 READ 内容。

    真正的开关是 needs_exact(purpose)：strict 模式一律精确；auto/fast 下
    install / uninstall 精确、ui 走指纹。

    v2 的 bug 是让 update 也走指纹：只要「文件数 / 总字节 / 最大 mtime_ns」
    三者不变就判 safe —— 用户改了某个旧文件（内容变、大小不变、mtime 仍小于
    最大值）时会被误判成「没动过」，于是 update 静默跳过覆盖。已用探针复现。
    """
    if purpose not in CLASSIFY_PURPOSES:
        raise ValueError(f"未知用途 {purpose!r}（可选：{', '.join(CLASSIFY_PURPOSES)}）")
    exact = needs_exact(purpose)
    if always_hash:                       # 兼容旧签名：只允许「更严」，不允许更松
        exact = True

    mid = cfg.get("marketId", "wb-local-market")
    d = SKILLS_DIR / sname
    try:
        ensure_child(SKILLS_DIR, d)
    except ConfigError:
        return {"skill": sname, "kind": "foreign", "label": "路径越界，拒绝处理"}

    if not (d / "SKILL.md").is_file():
        return {"skill": sname, "kind": "absent", "label": "未安装"}

    own = own if own is not None else load_ownership()
    rec = own["skills"].get(sname)
    if not rec:
        return {"skill": sname, "kind": "foreign", "label": "非本市场安装（不会动）"}
    if rec.get("plugin") != plugin_id:
        return {"skill": sname, "kind": "other_plugin",
                "label": f"由插件 {rec.get('plugin')} 安装"}
    if rec.get("owner") != mid:
        return {"skill": sname, "kind": "foreign", "label": "非本市场安装（不会动）"}

    # 快路径只服务「可以容忍误差」的用途
    if not exact:
        rec_fp = rec.get("fingerprint")
        if isinstance(rec_fp, dict):
            cur = (scan_cache.fingerprint(sname) if scan_cache is not None
                   else quick_fingerprint(d))
            if cur == rec_fp:
                return {"skill": sname, "kind": "safe", "label": "可安全卸载",
                        "checked": "fingerprint", "purpose": purpose}

    try:
        same = tree_hash(d) == rec.get("hash")
    except ScanError as exc:
        # 扫不全就没法证明「没被动过」。fail-closed：当作被改过 ——
        # 卸载会保留它，更新会覆盖它（市场那份是完整的，覆盖是安全方向）。
        return {"skill": sname, "kind": "modified",
                "label": f"内容读取失败，保守当成被改过：{exc}",
                "checked": "error", "purpose": purpose}
    if not same:
        return {"skill": sname, "kind": "modified", "label": "安装后被修改过",
                "checked": "hash", "purpose": purpose}
    return {"skill": sname, "kind": "safe", "label": "可安全卸载",
            "checked": "hash", "purpose": purpose}


# 兼容别名：语义就是「按用途判断」，旧名字保留给外部脚本
inspect_skill = classify_skill


def plugin_uninstall_plan(plugin_id: str, cfg: dict | None = None,
                          purpose: str = "ui", always_hash: bool | None = None,
                          scan_cache: "SkillScanCache | None" = None) -> dict:
    """插件的卸载分级计划。

    · 网页展示（purpose="ui"）用指纹，快
    · 真正执行卸载（purpose="uninstall"）必须精确 —— 否则可能把
      「其实已经被用户改过」的目录当 safe 搬进回收站
    """
    cfg = cfg or load_config()
    spec = next((p for p in cfg.get("localPlugins", []) if p["name"] == plugin_id), None)
    if not spec:
        return {"ok": False, "error": f"市场里没有插件 {plugin_id}"}
    own = load_ownership()          # 只读一次，别在循环里反复读文件
    items = [classify_skill(plugin_id, s, cfg, own, purpose=purpose,
                            always_hash=always_hash, scan_cache=scan_cache)
             for s in spec.get("skills", [])]
    counts = {}
    for it in items:
        counts[it["kind"]] = counts.get(it["kind"], 0) + 1
    return {
        "ok": True,
        "plugin": plugin_id,
        "purpose": purpose,
        "items": items,
        "counts": counts,
        "removable": [i["skill"] for i in items if i["kind"] == "safe"],
        "modified": [i["skill"] for i in items if i["kind"] == "modified"],
        "untouched": [i["skill"] for i in items if i["kind"] in ("foreign", "other_plugin")],
        "absent": [i["skill"] for i in items if i["kind"] == "absent"],
    }


# ---------------------------------------------------------------- 注册

def _read_known(strict: bool = False) -> dict:
    """读 known_marketplaces.json。

    strict=True 时，文件存在但读不出来会**抛 ConfigError**，而不是当成空表。
    这一点很关键：如果当成空表，register() 就会拿一个只含自己一条的记录
    去覆盖原文件 —— 用户其它几个市场（包括 WorkBuddy 自带的）会被直接抹掉。
    宁可报错让用户去 .backups 里恢复，也不能替用户把数据删了。
    """
    data = read_json(KNOWN_PATH, None, strict=strict)
    if data is None:
        return {}
    if not isinstance(data, dict):
        if strict:
            raise ConfigError(f"{KNOWN_PATH.name} 的顶层必须是一个对象，实际是 {type(data).__name__}")
        return {}
    return data


def _read_known_or_die() -> dict:
    """写操作前读 —— 文件坏了就拒绝继续，绝不覆盖。"""
    if not KNOWN_PATH.is_file():
        return {}
    try:
        return _read_known(strict=True)
    except ConfigError as exc:
        raise RuntimeError(
            f"拒绝覆盖：{KNOWN_PATH.name} 已损坏，读不出来。\n"
            f"  原因：{exc}\n"
            f"  文件：{KNOWN_PATH}\n"
            f"  备份：{BACKUP_DIR}（挑一份改名成 known_marketplaces.json 即可恢复）\n"
            "  修好或删掉它再重试。"
        ) from exc


def backup_known() -> Path | None:
    """备份 known_marketplaces.json。

    时间戳带纳秒，避免同一秒内两次备份互相覆盖
    （v1 用秒级戳 + 「已存在就返回」会让第二次修改没有备份）。
    """
    if not KNOWN_PATH.is_file():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{time.time_ns() % 1_000_000_000:09d}"
    dst = BACKUP_DIR / f"known_marketplaces.{stamp}.json"
    shutil.copy2(KNOWN_PATH, dst)
    log("info", "backup", f"已备份 known_marketplaces.json → {dst.name}")
    return dst


def _prune_backups(keep: int = BACKUP_KEEP) -> None:
    if not BACKUP_DIR.is_dir():
        return
    items = sorted(BACKUP_DIR.glob("known_marketplaces.*.json"))
    if len(items) <= keep:
        return
    for old in items[: len(items) - keep]:
        try:
            old.unlink()
        except OSError:
            pass


def is_registered(cfg: dict | None = None) -> bool:
    cfg = cfg or load_config()
    return cfg.get("marketId") in _read_known()


def _entry_for(cfg: dict) -> dict:
    return {
        "manifestName": cfg.get("marketId", "wb-local-market"),
        "type": "directory",
        "source": {"source": "directory", "path": str(MARKET_ROOT)},
        "installLocation": str(MARKET_ROOT),
        "description": cfg.get("description", ""),
        "lastUpdated": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "autoUpdate": False,
        "isBuiltIn": False,
    }


def _commit_known(mutate, *, attempts: int = 4, what: str = "修改"):
    """对 known_marketplaces.json 做乐观合并写入。

    WorkBuddy 自己也会改这个文件（autoUpdate 市场刷新 lastUpdated、zip 地址
    换成带内容哈希的版本），而它**不抢我们这把锁**。原来的
    「读 → 改 → 原子写 → 读回校验」只能发现「整个条目消失」，
    发现不了「某个市场的字段在中间被别人改了、又被我们整份覆盖回去」。

    改成：落笔之前再读一次，确认和我们读到的快照一模一样才写；
    不一样就基于最新内容重新合并。这把竞争窗口从「整个读-改-写过程」
    压到了「重读到 replace 之间的几十微秒」。

    返回 (before, candidate)。mutate 返回 False 表示无需改动（提前收工）。
    """
    for attempt in range(attempts):
        before = _read_known_or_die()
        candidate = mutate(dict(before))
        if candidate is False:
            return before, None
        latest = _read_known_or_die()
        if latest != before:
            log("warn", "register",
                f"{what}前发现 {KNOWN_PATH.name} 已被外部改动"
                f"（第 {attempt + 1} 次），基于最新内容重新合并")
            continue
        backup_known()
        atomic_write_text(KNOWN_PATH,
                          json.dumps(candidate, ensure_ascii=False, indent=2) + "\n",
                          durable=True)
        _prune_backups()
        after = _read_known()
        lost = set(before) - set(after)
        if lost:
            log("warn", "register",
                f"检测到写回期间有市场消失：{', '.join(sorted(lost))}（WorkBuddy 可能同时在写）")
        return before, after
    raise RuntimeError(
        f"{what}失败：{KNOWN_PATH.name} 被反复改写（{attempts} 次都撞车）。\n"
        "如果 WorkBuddy 正在运行，稍后再试一次即可；文件没有被写坏。"
    )


def register(force: bool = False) -> bool:
    """把本市场写进 known_marketplaces.json。幂等；返回是否发生了改动。

    WorkBuddy 运行时会自己改写这个文件，所以并发保护有两层：
      · 全程持文件锁 → 防本工具自己的多个进程互相覆盖（lost update）
      · 乐观合并（读 → 改 → 重读 → 比对 → 写）→ 缩小与 WorkBuddy 自身写入的竞争窗口
    """
    with locked():
        cfg = load_config()
        mid = cfg.get("marketId", "wb-local-market")

        if not MANIFEST_PATH.is_file():
            _sync_packaging(quiet=True)

        entry = _entry_for(cfg)

        # 比较时忽略 lastUpdated，否则每次启动都会重写一遍这个文件
        def _same(a: dict, b: dict) -> bool:
            return ({k: v for k, v in a.items() if k != "lastUpdated"}
                    == {k: v for k, v in b.items() if k != "lastUpdated"})

        def _mutate(known: dict):
            if not force and isinstance(known.get(mid), dict) and _same(known[mid], entry):
                return False
            known[mid] = entry
            return known

        before, after = _commit_known(_mutate, what="注册")
        if after is None:
            log("info", "register", "已注册且条目未变，跳过")
            return False
        if mid not in after:
            log("warn", "register", "写回后本市场条目不见了 —— WorkBuddy 可能同时改写了该文件")
            raise RuntimeError("写回校验失败：注册条目未生效（可能和 WorkBuddy 的自动更新撞车，重跑一次即可）")
        log("info", "register", f"已注册市场 {mid} → {MARKET_ROOT}")
        return True


def unregister() -> bool:
    with locked():
        cfg = load_config()
        mid = cfg.get("marketId", "wb-local-market")

        def _mutate(known: dict):
            if mid not in known:
                return False
            del known[mid]
            return known

        before, after = _commit_known(_mutate, what="撤销注册")
        if after is None:
            log("info", "unregister", "本来就没注册，跳过")
            return False
        log("info", "unregister", f"已撤销注册 {mid}")
        return True


# ---------------------------------------------------------------- 状态

def installed_skill_names() -> set:
    """本机 skills 目录里的 skill 名。**排除暂存目录**（.x.installing-<pid>）。"""
    if not SKILLS_DIR.is_dir():
        return set()
    return {d.name for d in SKILLS_DIR.iterdir()
            if not d.name.startswith(".") and (d / "SKILL.md").is_file()}


def installed_repos() -> dict:
    data = read_json(GITHUB_REGISTRY, {}) or {}
    out = {}
    for proj in (data.get("projects") or []):
        if isinstance(proj, dict) and proj.get("repo"):
            out[proj["repo"]] = {
                "name": proj.get("name", ""),
                "sha_short": (proj.get("sha") or "")[:7],
                "skill_names": proj.get("skill_names") or [],
                "updated_at": proj.get("updated_at") or proj.get("installed_at") or "",
            }
    return out


def build_state(purpose: str = "ui") -> dict:
    """给网页界面用的完整状态。

    ⚠️ 默认走**展示**路径：卸载分级用 purpose="ui"（廉价指纹），
    可能把「已被改过」显示成「可安全卸载」。真正的卸载动作会重新按
    purpose="uninstall" 精确判定一次 —— 界面上的偏差不会变成误删。
    需要一份「所见即所得」的状态时传 purpose="uninstall"（会读全部文件，慢）。
    """
    if purpose not in CLASSIFY_PURPOSES:
        purpose = "ui"
    cfg = load_config()
    skills_here = installed_skill_names()
    repos = installed_repos()
    state = read_json(STATE_PATH, {}) or {}
    own = load_ownership()

    # 只扫**声明的那几个 skill**，一次调用、按名字分桶。
    # 不去扫整棵 SKILLS_DIR —— 那会把几百个无关目录（ghpm / 第三方装的）也走一遍。
    # 注意这里不传 excluder：要和 quick_fingerprint(d) / tree_hash(d) 的口径一致
    # （它们都不做排除），否则指纹对不上、全部退回完整哈希。
    declared = [s for p in cfg.get("localPlugins", []) for s in p.get("skills", [])]
    scan_cache = SkillScanCache(declared) if declared else None

    plugins = []
    for spec in cfg.get("localPlugins", []):
        want = spec.get("skills", [])
        plan = plugin_uninstall_plan(spec["name"], cfg, purpose=purpose,
                                     scan_cache=scan_cache)
        items = plan.get("items", [])
        by = {i["skill"]: i for i in items}
        have = [s for s in want if s in skills_here]
        plugins.append({
            "id": spec["name"],
            "kind": "local",
            "name": spec.get("displayName", spec["name"]),
            "rawName": spec["name"],
            "category": spec.get("category", "未分类"),
            "description": spec.get("description", ""),
            "description_en": spec.get("description_en", ""),
            "version": spec.get("version", "1.0.0"),
            "keywords": spec.get("keywords", []),
            "skills": want,
            "installedSkills": have,
            "installedRatio": f"{len(have)}/{len(want)}",
            "installed": len(have) == len(want) and len(want) > 0,
            "partial": 0 < len(have) < len(want),
            "packaged": (PLUGINS_DIR / spec["name"]).is_dir(),
            # 卸载安全分级
            "uninstall": {
                "counts": plan.get("counts", {}),
                "removable": plan.get("removable", []),
                "modified": plan.get("modified", []),
                "untouched": plan.get("untouched", []),
                "absent": plan.get("absent", []),
                "items": items,
                "safeToUninstall": bool(plan.get("removable")),
            },
            "ownership": {s: own["skills"].get(s, {}).get("plugin", "") for s in want
                          if s in own["skills"]},
            "skillDetail": [{"skill": s, "kind": by.get(s, {}).get("kind", "absent"),
                             "label": by.get(s, {}).get("label", "")} for s in want],
        })

    remotes = []
    for spec in cfg.get("remoteSources", []):
        hit = repos.get(spec["repo"])
        remotes.append({
            "id": spec["repo"].replace("/", "__"),
            "kind": "remote",
            "name": spec.get("displayName", spec["repo"]),
            "rawName": spec["repo"],
            "category": spec.get("category", "未分类"),
            "description": spec.get("description", ""),
            "keywords": spec.get("keywords", []),
            "skillCount": spec.get("skillCount", 0),
            "stars": spec.get("stars", 0),
            "verifiedAt": spec.get("verifiedAt", ""),
            "installed": bool(hit),
            "installedSha": (hit or {}).get("sha_short", ""),
            "installedSkills": len((hit or {}).get("skill_names") or []),
        })

    cats = []
    for p in plugins + remotes:
        if p["category"] not in cats:
            cats.append(p["category"])

    ts = trash_stats()
    return {
        "marketVersion": MARKET_VERSION,
        "schemaVersion": cfg.get("schemaVersion", 1),
        "marketId": cfg.get("marketId"),
        "marketName": cfg.get("name"),
        "root": str(MARKET_ROOT),
        "wbHome": str(WB),
        "registered": is_registered(cfg),
        "manifestOk": MANIFEST_PATH.is_file(),
        "knownPath": str(KNOWN_PATH),
        "ghpmOk": GHPM_PY.is_file(),
        "plugins": plugins,
        "remotes": remotes,
        "categories": cats,
        "trash": {
            "count": ts["count"],
            "bytes": ts["bytes"],
            "policy": trash_config(),
        },
        "stats": {
            "localPlugins": len(plugins),
            "remoteSources": len(remotes),
            "localSkills": sum(len(p["skills"]) for p in plugins),
            "installedLocalSkills": sum(len(p["installedSkills"]) for p in plugins),
            "ownedSkills": len(own["skills"]),
            "installedRemotes": sum(1 for r in remotes if r["installed"]),
            "sizeBytes": state.get("sizeBytes", 0),
            "lastSync": state.get("lastSync", ""),
            "marketVersion": MARKET_VERSION,
            "stateVersion": state.get("version", 0),
            "verify": verify_mode(),
            "verifyEffective": {"ui": needs_exact("ui"),
                                "install": needs_exact("install"),
                                "uninstall": needs_exact("uninstall")},
        },
    }


# ---------------------------------------------------------------- 日志读取
# _tail_lines / tail_log 已迁 workbuddy_market.logging（v2.8 R2），此处 re-export。


# ---------------------------------------------------------------- 打开目录（白名单）
#
# v2.2 的 /api/open/path 直接 `Path(body["path"])` 交给 explorer / open / xdg-open。
# 实测 `C:\Windows`、用户家目录都能被"打开" —— 虽然没执行 shell，但
# explorer / open 本身就是操作系统行为，不该由任意本机网页来点名。
# 现在只认市场自己地盘里的目标。

OPEN_TARGETS = ("root", "plugins", "web", "trash", "plugin")


def resolve_open_request(payload: dict) -> tuple[Path | None, str]:
    """把请求解析成一个**允许打开**的路径。返回 (path, error)。

    两种写法：
      {"target": "plugin", "id": "novel-writing-suite"}    ← 推荐：服务器自己拼路径
      {"target": "root" | "plugins" | "web" | "trash"}
      {"path": "..."}                                      ← 兼容旧前端，仍要过白名单

    无论哪条路，最终都过一遍 `ensure_child(MARKET_ROOT, ...)`。
    """
    roots = {"root": MARKET_ROOT, "plugins": PLUGINS_DIR,
             "web": WEB_DIR, "trash": TRASH_DIR}
    target = payload.get("target")

    if target == "plugin":
        try:
            pid = validate_id(payload.get("id"), "插件 id")
        except ConfigError as exc:
            return None, str(exc)
        p = PLUGINS_DIR / pid
        try:
            ensure_child(PLUGINS_DIR, p)
        except ConfigError:
            return None, "插件目录越界"
        if not p.is_dir():
            return None, f"插件目录不存在：{pid}"
        return p, ""

    if target is not None:
        if isinstance(target, str) and target in roots:
            return roots[target], ""
        return None, (f"未知的打开目标 {target!r}（可选：{', '.join(OPEN_TARGETS)}）")

    raw = payload.get("path")
    if not raw:
        return MARKET_ROOT, ""
    try:
        return ensure_child(MARKET_ROOT, Path(str(raw))), ""
    except ConfigError:
        return None, "只允许打开市场目录之内的路径"


# ---------------------------------------------------------------- 安装 / 卸载


def _stage_dir(sname: str) -> Path:
    return SKILLS_DIR / f".{sname}.installing-{os.getpid()}"


def _sweep_staging() -> int:
    """清掉上次崩在中途留下的暂存目录。"""
    n = 0
    try:
        for d in SKILLS_DIR.glob(".*.installing-*"):
            if d.is_dir():
                shutil.rmtree(d, ignore_errors=True)
                n += 1
    except OSError:
        pass
    return n


def _stage_skill(src: Path, sname: str) -> Path:
    """PREPARE + COPY + VERIFY：把 skill 完整复制到暂存目录并校验。

    失败时清掉暂存并原样抛出 —— 此时**正式目录一点没动**。

    链接防线（defense-in-depth）：打包阶段已经不跟随 symlink / junction，
    但「正常流程不会产生」不等于「不可能发生」—— 手工往市场目录塞一个
    重解析点就够了。而 `copytree(..., symlinks=False)` 会**跟随**链接，
    把技能目录之外的内容复制进 ~/.workbuddy。所以这里三道：

      1. 源目录里有任何重解析点 → 直接拒绝安装
      2. copytree 用 symlinks=True（复制链接本身，绝不跟随）
      3. 暂存副本里若出现重解析点 → 同样拒绝

    和打包阶段连起来就是完整闭环：源 → 打包禁止 → 市场产物禁止 → 安装再禁一次。

    返回 dict：`{"tmp", "index", "links", "bytes"}`。把暂存副本的索引一并交出去，
    是因为落位后的内容与暂存**完全一致**（rename 不改内容也不改 mtime），
    后续算所有权指纹 / 内容哈希可以直接用它，不必再扫一遍新版本。
    """
    tmp = _stage_dir(sname)
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    try:
        si, s_links = _scan(src, on_error="raise")   # 看不见源内容就别谈"校验通过"
        if s_links:
            raise OSError(
                f"源目录含 {len(s_links)} 个符号链接 / junction，拒绝安装：{s_links[:3]}"
            )
        shutil.copytree(src, tmp, symlinks=True)
        if not (tmp / "SKILL.md").is_file():
            raise OSError("暂存目录里没有 SKILL.md")
        ti, t_links = _scan(tmp, on_error="raise")
        if t_links:
            raise OSError(
                f"暂存副本里出现 {len(t_links)} 个符号链接 / junction，拒绝安装：{t_links[:3]}"
            )
        if set(si) != set(ti):
            miss = sorted(set(si) - set(ti))[:3]
            raise OSError(f"暂存内容不完整，缺少 {miss}")
        for rel, (sz, _mt) in si.items():
            if ti[rel][0] != sz:
                raise OSError(f"暂存文件大小与源不符：{rel}")
        return {"tmp": tmp, "index": ti, "links": t_links,
                "bytes": sum(v[0] for v in ti.values())}
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def _commit_staged(tmp: Path, dst: Path, sname: str,
                   index: "TrashIndex | None" = None) -> None:
    """COMMIT：把暂存目录原子换到正式位置；换失败就把旧版本放回去。

    顺序很重要 —— **先复制好、校验过，再动旧版本**。
    v2 是反过来的（先把旧的搬走再复制新的），所以复制一旦失败，
    旧版本躺在回收站、新版本没写上，本机 skill 直接消失。
    """
    trashed = None
    if dst.exists():
        trashed = move_to_trash(dst, "reinstall", index=index)
        if trashed is None:
            raise OSError("旧目录无法移入回收站，未改动")
    try:
        os.replace(str(tmp), str(dst))
    except OSError:
        if trashed is not None:
            try:
                shutil.move(str(trashed), str(dst))
                log("warn", "install", f"{sname} 落位失败，已把旧版本放回原位")
            except OSError as exc:
                log("error", "install",
                    f"{sname} 落位失败且回滚也失败：{exc}；旧版本仍在 {trashed}")
        raise


def install_local_plugin(plugin_id: str, mode: str = "missing") -> dict:
    """把插件的 skill 装到 ~/.workbuddy/skills/。

    mode:
      missing（默认）只补缺，已有的一律不碰
      update      补缺 + 覆盖「本市场装的且内容已变」的
      force       补缺 + 覆盖全部同名目录

    每个 skill 都走「暂存 → 校验 → 换位」两阶段：任何一步失败，
    本机原来的那份**原样还在**。三种模式都绝不静默覆盖非本市场安装的 skill。
    """
    if mode not in INSTALL_MODES:
        return {"ok": False, "error": f"未知安装模式 {mode}（可选：{', '.join(INSTALL_MODES)}）"}

    with locked():
        op = f"install-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
        try:
            cfg = load_config()
        except ConfigError as exc:
            return {"ok": False, "error": f"配置不可用：{exc}"}
        spec = next((p for p in cfg.get("localPlugins", []) if p["name"] == plugin_id), None)
        if not spec:
            return {"ok": False, "error": f"市场里没有插件 {plugin_id}"}

        # 先把上一次未完成的事务补上（比如上次正好卡在
        # 「文件已落位、所有权还没写」那一步）
        rec = recover_transactions(quiet=True)
        recovered = rec["recovered"]

        src_root = PLUGINS_DIR / plugin_id / "skills"
        if not src_root.is_dir():
            _sync_packaging(quiet=True)
        if not src_root.is_dir():
            return {"ok": False, "error": f"插件 {plugin_id} 尚未打包，请先运行同步"}

        SKILLS_DIR.mkdir(parents=True, exist_ok=True)

        version = spec.get("version", "1.0.0")
        own = load_ownership()
        added, updated, skipped, foreign, failed, warnings = [], [], [], [], [], []
        expected_by_skill = {}          # 换位前算好的「期望状态」，收尾直接复用
        trash_index = TrashIndex()      # 整批只落一次回收站索引

        # 事务日志**必须早于任何磁盘变更**。哪怕后面一个 skill 都不用装，
        # 也只是一份空日志，收尾时会被删掉 —— 代价是一次原子写，
        # 换来的是「从这里起无论死在哪一行都有凭证」。
        tx = tx_begin("install", plugin_id, spec.get("skills", []),
                      version=version, mode=mode)

        try:
            for sname in spec.get("skills", []):
                src = src_root / sname
                if not (src / "SKILL.md").is_file():
                    continue
                dst = SKILLS_DIR / sname
                try:
                    ensure_child(SKILLS_DIR, dst)
                except ConfigError as exc:
                    failed.append(f"{sname}: {exc}")
                    continue

                # 安装决策必须精确：指纹只服务网页显示，绝不用来决定要不要覆盖
                kind = classify_skill(plugin_id, sname, cfg, own, purpose="install")["kind"]

                if kind == "foreign" or kind == "other_plugin":
                    foreign.append(sname)
                    continue
                if kind == "absent":
                    action = "add"
                elif mode == "missing" or (mode == "update" and kind == "safe"):
                    skipped.append(sname)
                    continue
                else:
                    action = "update"

                # 两阶段：先备好新的，再动旧的
                try:
                    st = _stage_skill(src, sname)
                except (OSError, shutil.Error) as exc:
                    failed.append(f"{sname}: 暂存失败（本机版本未改动）：{exc}")
                    continue

                # 先算出「换位之后应该长什么样」，**在动正式目录之前落盘**。
                # 中间那一步 os.replace 成功但进程随即死掉，靠的就是这份 expected。
                expected = {
                    "hash": tree_hash_from_index(st["tmp"], st["index"]),
                    "fingerprint": fingerprint_from_index(st["index"], st["links"]),
                }
                tx_note_staged(tx, sname, expected,
                               plugin=plugin_id, version=version)

                try:
                    _commit_staged(st["tmp"], dst, sname, index=trash_index)
                except OSError as exc:
                    shutil.rmtree(st["tmp"], ignore_errors=True)
                    failed.append(f"{sname}: 落位失败：{exc}")
                    continue

                tx_note_committed(tx, sname)     # 交付确认
                expected_by_skill[sname] = expected

                (added if action == "add" else updated).append(sname)
                log("info", "install", f"{sname} {'新增' if action == 'add' else '更新'}完成",
                    op_id=op)

            done = added + updated
            if done:
                try:
                    # 这些 hash / 指纹就是上面刚算过的，不用再读一遍新版本
                    record_owner(plugin_id, done, version,
                                 snapshots={s: expected_by_skill[s]
                                            for s in done if s in expected_by_skill})
                    for s in done:
                        tx_drop(tx, s)
                except (OSError, ConfigError) as exc:
                    # 文件已经装好了，只是账没记上。如实报告，但**不能**谎称成功
                    # 之后什么都没发生 —— 日志会保留，下次启动自动补记。
                    warnings.append(
                        f"所有权记录写入失败：{exc}（已记入事务日志，"
                        "下次启动/下次安装会自动补记）")
                    log("error", "install", warnings[-1], op_id=op)

            msg = (f"{plugin_id}[{mode}]: 新增 {len(added)} 更新 {len(updated)} "
                   f"跳过 {len(skipped)} 非本市场 {len(foreign)} 失败 {len(failed)}")
            log("warn" if (failed or warnings) else "info", "install", msg, op_id=op)
            return {"ok": True, "mode": mode, "op": op, "added": added, "updated": updated,
                    "skipped": skipped, "foreign": foreign, "failed": failed,
                    "warnings": warnings, "recovered": recovered,
                    "tx": tx["id"]}
        finally:
            # 账清干净了就删日志；还有没结的，就把日志交还给恢复流程 ——
            # 必须显式释放，否则这个 id 会一直挂在 _TX_ACTIVE 里，同进程的
            # recover_transactions() 反而看不见它。
            if tx_settled(tx):
                tx_close(tx)
            else:
                tx_release(tx)
            trash_index.flush()         # 整批搬移只写一次索引


def uninstall_local_plugin(plugin_id: str, force: bool = False) -> dict:
    """卸载。**只动本市场装的**，用户自己的和别的插件的绝不碰。

    分级：
      safe      本市场装的且没被改过  → 移入回收站
      modified  装过但被改过          → 默认保留，force=True 才移走
      foreign   不是本市场装的        → 永不移动

    和安装共用同一套事务模型：搬走之前就有日志，搬走之后立刻登记
    pendingForget，`forget_owner()` 成功才清账。崩在中间的话，下次恢复
    会看到「目录已不在 + 所有权还在」并把账补平 —— 而不是留下
    「文件没了、ownership 还认着它」这种半截状态。
    """
    with locked():
        try:
            cfg = load_config()
        except ConfigError as exc:
            return {"ok": False, "error": f"配置不可用：{exc}"}
        # 卸载前先把上一次没记完的账补上，否则分级会不准
        recovered = recover_transactions(quiet=True)["recovered"]
        # 卸载是要真的把用户目录搬走，必须用精确判定，不看指纹
        plan = plugin_uninstall_plan(plugin_id, cfg, purpose="uninstall")
        if not plan.get("ok"):
            return plan

        moved, kept, warnings = [], [], []
        trash_index = TrashIndex()
        tx = tx_begin("uninstall", plugin_id, plan.get("removable", []) + plan.get("modified", []),
                      force=force)
        try:
            for item in plan["items"]:
                sname, kind = item["skill"], item["kind"]
                if kind in ("foreign", "other_plugin"):
                    kept.append({"skill": sname, "why": item["label"]})
                    continue
                if kind == "absent":
                    continue
                if kind == "modified" and not force:
                    kept.append({"skill": sname, "why": "安装后被修改过，未移除"})
                    continue
                d = SKILLS_DIR / sname
                try:
                    ensure_child(SKILLS_DIR, d)      # 删除前最后一道闸
                except ConfigError as exc:
                    kept.append({"skill": sname, "why": f"路径越界，拒绝处理：{exc}"})
                    continue
                reason = "uninstall" if kind == "safe" else "uninstall-modified"
                if not move_to_trash(d, reason, index=trash_index):
                    continue
                # 搬走成功就立刻登记 —— 此刻所有权还留着，日志就是「还没清」的凭证
                tx_note_removed(tx, sname)
                moved.append(sname)

            if moved:
                try:
                    # 一次把所有权全清掉（forget_owner 内部只写一次文件）
                    forget_owner(moved)
                    tx["pendingForget"] = []
                except (OSError, ConfigError) as exc:
                    warnings.append(
                        f"所有权记录未能清除：{exc}（已记入事务日志，下次启动会自动补清）")
                    log("error", "uninstall", warnings[-1])

            log("warn" if dropped(plan, force) else "info", "uninstall",
                f"{plugin_id}: 移除 {len(moved)}，保留 {len(kept)}"
                + (f"（{'、'.join(moved)}）" if moved else ""))
            return {"ok": True, "moved": moved, "kept": kept,
                    "trash": str(TRASH_DIR), "force": force, "recovered": recovered,
                    "warnings": warnings,
                    "plan": {k: plan[k] for k in ("counts", "removable", "modified", "untouched")}}
        finally:
            if tx_settled(tx):
                tx_close(tx)
            else:
                tx_release(tx)
            trash_index.flush()         # 整批搬移只写一次索引


def dropped(plan: dict, force: bool) -> bool:
    """这次卸载是否真的动了东西（决定日志级别）。"""
    return bool(plan.get("removable")) or (force and bool(plan.get("modified")))


# ---------------------------------------------------------------- 自检

def deep_check() -> tuple:
    """四层一致性校验：配置 ↔ 索引 ↔ 插件清单 ↔ 实际文件。

    返回 (ok, errors, warnings)。errors 非空即视为不一致。
    """
    errors, warnings = [], []

    # --- 配置层（validate_config 会做结构 + 安全校验，问题直接抛）
    try:
        cfg = load_config()
        warnings += validate_config(cfg)
    except ConfigError as exc:
        return (False, [f"配置不可用：{exc}"], [])

    # --- 暂存残留：上次安装崩在中途留下的
    try:
        leftovers = [d.name for d in SKILLS_DIR.glob(".*.installing-*")] if SKILLS_DIR.is_dir() else []
    except OSError:
        leftovers = []
    if leftovers:
        warnings.append(f"skills 目录里有 {len(leftovers)} 个安装暂存残留 {leftovers[:3]}"
                        "（下次安装会自动清理）")

    # --- 索引层
    if not MANIFEST_PATH.is_file():
        errors.append("市场索引 .codebuddy-plugin/marketplace.json 不存在（先跑 --sync）")
        return (False, errors, warnings)
    try:
        man = read_json(MANIFEST_PATH, None, strict=True)
    except ConfigError as exc:
        return (False, [f"市场索引不可用：{exc}"], warnings)
    if not isinstance(man, dict) or not isinstance(man.get("plugins"), list):
        return (False, ["市场索引结构不对（应有 plugins 数组）"], warnings)

    local = {p["name"]: p for p in cfg.get("localPlugins", [])}
    indexed = {p.get("name"): p for p in man["plugins"]}

    # 配置有、索引没有 → 错误
    for name in local:
        if name not in indexed:
            errors.append(f"配置里的插件 {name} 没有出现在市场索引里")
    # 索引有、配置没有 → 警告（多半是上次同步残留）
    for name in indexed:
        if name not in local:
            warnings.append(f"市场索引里的插件 {name} 已不在 market.config.json 中（重新打包可清掉）")

    # --- 插件清单层 + 文件层
    for name, spec in local.items():
        ip = indexed.get(name)
        src_rel = (ip or {}).get("source") or f"./plugins/{name}"
        pdir = MARKET_ROOT / str(src_rel)[2:]
        if not pdir.is_dir():
            errors.append(f"插件 {name} 的 source 目录不存在：{pdir}")
            continue

        pj_path = pdir / ".codebuddy-plugin" / "plugin.json"
        if not pj_path.is_file():
            errors.append(f"插件 {name} 缺少 .codebuddy-plugin/plugin.json")
        else:
            try:
                pj = read_json(pj_path, None, strict=True)
            except ConfigError as exc:
                errors.append(f"插件 {name} 的 plugin.json 不可用：{exc}")
                pj = None
            if isinstance(pj, dict):
                if pj.get("name") != name:
                    errors.append(f"插件 {name} 的 plugin.json 里 name={pj.get('name')}，不一致")
                want_v = spec.get("version", "1.0.0")
                if ip and ip.get("version") != want_v:
                    errors.append(f"插件 {name} 版本不一致：索引 v{ip.get('version')} vs 配置 v{want_v}")
                if pj.get("version") != want_v:
                    errors.append(f"插件 {name} 版本不一致：plugin.json v{pj.get('version')} vs 配置 v{want_v}")

        # 配置声明 vs 实际打包
        declared = set(spec.get("skills", []))
        sroot = pdir / "skills"
        actual = {p.name for p in sroot.iterdir() if (p / "SKILL.md").is_file()} if sroot.is_dir() else set()
        for miss in sorted(declared - actual):
            if (SKILLS_DIR / miss / "SKILL.md").is_file():
                errors.append(f"插件 {name} 声明了 {miss}，但没有打包进去")
            else:
                warnings.append(f"插件 {name} 声明的 {miss} 在本机 skills 里不存在")
        for extra in sorted(actual - declared):
            warnings.append(f"插件 {name} 里多了未声明的 {extra}（重新打包可清掉）")

    # --- WorkBuddy 侧
    if not KNOWN_PATH.parent.is_dir():
        errors.append(f"WorkBuddy 插件目录不存在：{KNOWN_PATH.parent}")
    elif KNOWN_PATH.is_file():
        try:
            read_json(KNOWN_PATH, None, strict=True)
        except ConfigError as exc:
            errors.append(f"known_marketplaces.json 不可用：{exc}")

    # --- 所有权残留
    own = load_ownership()["skills"]
    legacy = 0
    for s, rec in own.items():
        if not (SKILLS_DIR / s / "SKILL.md").is_file():
            warnings.append(f"所有权记录里的 {s} 在本机已不存在（残留记录）")
            continue
        if rec.get("plugin") not in local:
            warnings.append(f"所有权记录里的 {s} 指向已不存在的插件 {rec.get('plugin')}")
        fp = rec.get("fingerprint")
        # 旧记录只有 files/bytes/mtime_ns_max，缺少 mtime_ns_sum —— 结构对不上
        # 就会一直退回完整 SHA-256（正确但慢），所以提示重装补齐
        if not isinstance(fp, dict) or "mtime_ns_sum" not in fp:
            legacy += 1
    if legacy:
        warnings.append(f"{legacy} 条所有权记录没有完整的快速指纹"
                        "（v2.1 之前装的记录）；重装一次即可补上，"
                        "期间状态检查会退回完整 SHA-256")

    # --- 回收站索引安全性
    # 索引是普通 JSON，手工可改。里面的条目名必须都是合法 basename，
    # 否则说明它被改过（或写坏了）—— 这是「越界删除」的唯一入口，必须报出来。
    if TRASH_INDEX_PATH.is_file():
        try:
            tidx = _load_trash_index()
        except Exception:
            tidx = {"items": {}}
        bad = [n for n in tidx.get("items", {}) if _trash_entry(n) is None]
        if bad:
            errors.append(
                f"回收站索引里有 {len(bad)} 个非法条目名 {bad[:3]}"
                "（含路径成分，属于越界删除风险；本工具已拒绝按它访问磁盘，"
                f"可删掉 {TRASH_INDEX_PATH.name} 让它重建）"
            )

    # --- 未完成的事务
    # 挂着待办条目的日志，说明上一次装/卸在「文件已变更、状态还没跟上」那一步
    # 中断了。数据没丢，但账没记上 —— 必须报出来。
    for tx in tx_list():
        pend = tx.get("pendingOwnership") or []
        forget = tx.get("pendingForget") or []
        if pend or forget:
            names = [e.get("skill") if isinstance(e, dict) else e for e in (pend or forget)]
            errors.append(
                f"有未完成的事务 {tx.get('id')}（{tx.get('operation')} "
                f"{tx.get('plugin')}）：{names} 的磁盘状态与所有权记录不一致"
                "（下次打包/安装/启动会自动补账；若内容已被你改过，"
                "本工具会拒绝认领并一直留着这份日志）"
            )

    return (not errors, errors, warnings)


def selfcheck() -> tuple:
    """兼容 v1 的签名：返回 (ok, 问题列表)，只含 error 级。"""
    ok, errors, _warnings = deep_check()
    return (ok, errors)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    cmd = argv[0] if argv else "status"
    if cmd == "recover":
        r = recover_transactions(quiet=False,
                                 discard_conflicts="--discard-conflicts" in argv)
        say(f"事务恢复：补记所有权 {len(r['recovered'])} 项，"
            f"清理日志 {len(r['finished'])} 份，清理暂存 {r['stagingSwept']} 个")
        for c in r["conflicts"]:
            say(f"  ! 拒绝认领 {c['skill']}：内容已被改动（不是当时 commit 的那一份）")
        for tid, err in r["failed"]:
            say(f"  ✗ {tid}：{err}")
        return 0 if not r["failed"] else 1
    if cmd == "sync":
        rep = sync_packaging()
        say(f"打包完成：{len(rep['plugins'])} 个插件，{rep['copiedSkills']} 个 skill")
        if rep.get("recovered"):
            say(f"  顺带补记了上次未完成的所有权：{', '.join(rep['recovered'])}")
        if rep["missing"]:
            say("缺失： " + ", ".join(rep["missing"]))
        return 0
    if cmd == "register":
        say("已注册。" if register() else "已是注册状态，无需改动。")
        return 0
    if cmd == "unregister":
        say("已撤销注册。" if unregister() else "未注册，无需撤销。")
        return 0
    if cmd == "purge-trash":
        r = prune_trash(force=True)
        say(f"回收站已清空：移除 {r['removed']} 项，释放 {r['freed'] / 1048576:.1f} MB")
        if r["failed"]:
            say(f"  ! 有 {r['failed']} 项删除失败，仍在回收站里："
                + "、".join(str(i["name"]) for i in r["failedItems"][:3]))
        return 0
    if cmd == "status":
        st = build_state()
        say(f"市场：{st['marketName']}（{st['marketId']}） v{st['marketVersion']}")
        say(f"注册状态：{'已注册' if st['registered'] else '未注册'}")
        say(f"本机插件 {st['stats']['localPlugins']} 个 / GitHub 源 {st['stats']['remoteSources']} 个")
        eff = st["stats"]["verifyEffective"]
        say(f"校验档位：{st['stats']['verify']}"
            f"（精确判定：安装 {'是' if eff['install'] else '否'}"
            f" / 卸载 {'是' if eff['uninstall'] else '否'}）")
        say(f"回收站 {st['trash']['count']} 项，{st['trash']['bytes'] / 1048576:.1f} MB")
        ok, errors, warns = deep_check()
        say(f"深度自检：{'通过' if ok else '发现 ' + str(len(errors)) + ' 个错误'}")
        for e in errors:
            say("  ✗ " + e)
        for w in warns[:6]:
            say("  ! " + w)
        return 0
    say(f"未知命令：{cmd}")
    return 2


# ------------------------------------------------------- 模块末尾：迁移触发点
# 放在最后是有意的：迁移要写日志，必须等 FileLock / FileLockTimeout 全部定义完；
# 且对 import 本模块的 market_server / launcher / selftest 同样生效。
_warn_deprecated_envs()
migrate_runtime_files()

if __name__ == "__main__":
    raise SystemExit(main())
