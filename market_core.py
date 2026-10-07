# -*- coding: utf-8 -*-
"""market_core —— WorkBuddy 本机插件市场的内核（v2.7）。

版本号只有一个来源：MARKET_VERSION。每一轮代码评审对应一个次版本号：
v1（初版）→ v2（第一轮）→ v2.1（第二轮）→ v2.2（第三轮）→ v2.3（第四轮）
→ v2.4（第五轮）→ v2.5（第六轮）→ v2.6（第七轮）→ v2.7（开源重构 R1，当前）。

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

# ---------------------------------------------------------------- 路径
#
# v2.7 起采用三层根目录（「仓库是产品，状态是环境」—— GitHub 开源重构方案 §2）：
#   WBM_MARKET_ROOT   市场仓库根：market.config.json / marketplace.json / plugins / web
#   WBM_STATE_HOME    运行状态根：state / ownership / tx / trash / backups / locks / logs
#   WBM_HOME          WorkBuddy 家目录：skills / known_marketplaces.json
# 旧名 GHPM_MARKET_ROOT / GHPM_HOME 继续兼容，每进程打一次 deprecation 告警。
#
# 运行状态分桶（评审定稿，防同机多 clone 互相污染）：
#   · 显式 WBM_STATE_HOME                    → 直接使用（隔离由设置者负责）
#   · 仅显式 *MARKET_ROOT（旧自检 / harness）→ 跟随 MARKET_ROOT，文件名沿用 v2.6 旧名，
#     完整复刻旧行为（_LEGACY_LAYOUT），迁移逻辑直接跳过
#   · 默认（真实使用）                       → ~/.workbuddy-market/markets/<bucket>/
#     bucket = <仓库目录名清洗>-<sha256(MARKET_ROOT 绝对路径) 前 12 位>
#     目录名人可读，hash 保证同机两个 clone 的锁 / trash / tx 绝不共享。

_DEPRECATED_ENVS_USED: list = []


def _env_root(new_name: str, old_name: str) -> "str | None":
    """新名优先；回退旧名时记录下来，待 log() 可用后统一打一次告警。"""
    v = os.environ.get(new_name)
    if v is not None:
        return v
    v = os.environ.get(old_name)
    if v is not None:
        _DEPRECATED_ENVS_USED.append((old_name, new_name))
        return v
    return None


_WBM_MARKET_ROOT = os.environ.get("WBM_MARKET_ROOT")
_GHPM_MARKET_ROOT = os.environ.get("GHPM_MARKET_ROOT")
_STATE_HOME_EXPLICIT = os.environ.get("WBM_STATE_HOME")

if _WBM_MARKET_ROOT is None and _GHPM_MARKET_ROOT is not None:
    _DEPRECATED_ENVS_USED.append(("GHPM_MARKET_ROOT", "WBM_MARKET_ROOT"))

MARKET_ROOT = Path(
    _WBM_MARKET_ROOT or _GHPM_MARKET_ROOT or Path(__file__).resolve().parent
).resolve()

# legacy 仅指「旧变量名 + 未显式给 WBM_STATE_HOME」的老自检 / harness 场景：
# 完整复刻 v2.6 布局。显式设置**新**变量 WBM_MARKET_ROOT 属于新式用法，
# 一律走 v2.7 布局（默认分桶），不会误入 legacy。
_LEGACY_LAYOUT = (_WBM_MARKET_ROOT is None
                  and _GHPM_MARKET_ROOT is not None
                  and _STATE_HOME_EXPLICIT is None)

if _LEGACY_LAYOUT:
    STATE_HOME = MARKET_ROOT
elif _STATE_HOME_EXPLICIT:
    STATE_HOME = Path(_STATE_HOME_EXPLICIT).resolve()
else:
    def _state_bucket() -> str:
        name = re.sub(r"[^A-Za-z0-9._-]+", "-", MARKET_ROOT.name).strip("-") or "market"
        digest = hashlib.sha256(str(MARKET_ROOT).encode("utf-8")).hexdigest()[:12]
        return f"{name[:40]}-{digest}"
    STATE_HOME = (Path.home() / ".workbuddy-market" / "markets" / _state_bucket()).resolve()

CONFIG_PATH = MARKET_ROOT / "market.config.json"
MANIFEST_DIR = MARKET_ROOT / ".codebuddy-plugin"
MANIFEST_PATH = MANIFEST_DIR / "marketplace.json"
PLUGINS_DIR = MARKET_ROOT / "plugins"
WEB_DIR = MARKET_ROOT / "web"

if _LEGACY_LAYOUT:
    # v2.6 布局：仅存在于旧自检 / 旧 harness 环境，行为不变
    STATE_PATH = MARKET_ROOT / ".market-state.json"
    LOG_PATH = MARKET_ROOT / ".market-log.ndjson"
    BACKUP_DIR = MARKET_ROOT / ".backups"
    TRASH_DIR = MARKET_ROOT / ".trash"
    TX_DIR = MARKET_ROOT / ".market-tx"
    OWNERSHIP_PATH = MARKET_ROOT / ".ownership.json"
    LOCK_PATH = MARKET_ROOT / ".market.lock"
    LOG_LOCK_PATH = MARKET_ROOT / ".market-log.lock"
else:
    # v2.7 布局：运行状态离开 Git 仓库，收进 STATE_HOME
    STATE_PATH = STATE_HOME / "state.json"
    LOG_PATH = STATE_HOME / "logs" / "market.ndjson"
    BACKUP_DIR = STATE_HOME / "backups"
    TRASH_DIR = STATE_HOME / "trash"
    TX_DIR = STATE_HOME / "tx"
    OWNERSHIP_PATH = STATE_HOME / "ownership.json"
    LOCK_PATH = STATE_HOME / "locks" / "market.lock"
    LOG_LOCK_PATH = STATE_HOME / "locks" / "log.lock"

WB = Path(_env_root("WBM_HOME", "GHPM_HOME") or (Path.home() / ".workbuddy")).resolve()
SKILLS_DIR = WB / "skills"
KNOWN_PATH = WB / "plugins" / "known_marketplaces.json"
GITHUB_REGISTRY = WB / "github-projects.json"

GHPM_PY = SKILLS_DIR / "github-project-manager" / "scripts" / "ghpm.py"
# 注：GHPM_PY 是「可选远端任务执行器」的本机路径常量（不是环境变量），
# R6 拆 api/ 时改名为 REMOTE_JOB_TOOL；__GHPM__ 事件前缀是外部协议适配，保留。

OWNERSHIP_SCHEMA = 1
TX_SCHEMA = 1
STATE_VERSION = 2
MARKET_VERSION = "2.7.0"             # 全项目唯一的版本号来源
LOG_MAX_BYTES = 10 * 1024 * 1024      # 单份日志上限，超过就 rotate
LOG_KEEP = 2                          # 保留 .1 / .2 两份历史
BACKUP_KEEP = 20                      # known_marketplaces 备份保留份数
HASH_CHUNK_BYTES = 1024 * 1024        # 流式 SHA-256 的默认块大小（可被配置覆盖）

INSTALL_MODES = ("missing", "update", "force")

# classify 的用途。用途决定「要不要读到内容」：
#   ui        —— 网页状态，允许用廉价指纹，判错只是显示不准
#   install   —— 决定要不要覆盖，必须准
#   uninstall —— 决定要不要移走用户目录，必须最准
CLASSIFY_PURPOSES = ("ui", "install", "uninstall")
EXACT_PURPOSES = ("install", "uninstall")


# ---------------------------------------------------------------- 小工具


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _rotate_log() -> None:
    """日志超过阈值就轮转：.ndjson → .1.ndjson → .2.ndjson（最旧的丢弃）。"""
    try:
        if not LOG_PATH.is_file() or LOG_PATH.stat().st_size < LOG_MAX_BYTES:
            return
    except OSError:
        return
    for i in range(LOG_KEEP, 0, -1):
        older = LOG_PATH.with_name(f"{LOG_PATH.stem}.{i}{LOG_PATH.suffix}")
        newer = LOG_PATH if i == 1 else LOG_PATH.with_name(f"{LOG_PATH.stem}.{i - 1}{LOG_PATH.suffix}")
        try:
            if newer.is_file():
                os.replace(newer, older)
        except OSError:
            pass


def log(level: str, event: str, detail: str = "", op_id: str = "") -> None:
    """DSH 风格的事件流：一行一条 ndjson，追加写，超限自动轮转。

    「轮转 + 追加」整体放在**独立的日志锁**里 —— 两个进程同时轮转会出现
    A 把 .1 挪成 .2、B 又把 .1 挪成 .2 的竞态。不共用主锁是为了避免
    记日志和业务操作互相等待；也刻意不参与事务（日志不该成为失败点），
    所以拿不到锁时退化成无锁追加，宁可顺序乱一点，也不让记日志把业务打断。
    """
    rec = {"at": now_iso(), "level": level, "event": event, "detail": detail}
    if op_id:
        rec["op"] = op_id
    line = json.dumps(rec, ensure_ascii=False) + "\n"

    def _append() -> None:
        try:
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)  # v2.7：logs/ 可能尚未创建
        except OSError:
            pass
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line)

    try:
        with FileLock(LOG_LOCK_PATH, timeout=2.0):
            _rotate_log()
            _append()
    except (FileLockTimeout, OSError):
        try:
            _append()
        except OSError:
            pass


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


def _fsync_dir(path: Path) -> None:
    """POSIX 上 fsync 目录项。

    `os.replace` 之后，文件**内容**已经 fsync 过了，但「rename 这个目录项」
    本身要不要落盘，取决于父目录有没有 fsync。断电场景下可能出现
    「内容在、改名没生效」或者反过来。Windows 没有这个语义（也不允许
    对目录 open），直接跳过。
    """
    if os.name == "nt":
        return
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def atomic_write_bytes(path: Path, data: bytes, *, durable: bool = False) -> None:
    """唯一临时文件 → fsync → os.replace（可选再 fsync 父目录）。

    durable=True 用于「丢了会很难受」的少数文件（ownership / 注册表 / 事务日志）。
    普通打包产物没必要付这个代价。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=path.suffix)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        if durable:
            _fsync_dir(path.parent)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_text(path: Path, text: str, *, durable: bool = False) -> None:
    """唯一临时文件 → fsync → os.replace，避免半截 JSON。"""
    atomic_write_bytes(path, text.encode("utf-8"), durable=durable)


def write_text_if_changed(path: Path, text: str, *, durable: bool = False) -> bool:
    """内容一样就不写。

    原子写要走 fsync，是个真开销（实测 8 次约 80ms）。而 plugin.json /
    README / 市场索引 / 状态文件在绝大多数同步里内容是一样的 —— 跳过它们
    能让「什么都没变」的那次同步几乎零写盘。返回是否真的写了。
    """
    try:
        if path.is_file() and path.read_text(encoding="utf-8") == text:
            return False
    except (OSError, UnicodeDecodeError):
        pass
    atomic_write_text(path, text, durable=durable)
    return True


def read_json(path: Path, default=None, *, strict: bool = False):
    """读 JSON。

    strict=False（默认）：容错，读不到/坏了就返回 default。
    strict=True：关键文件（配置、索引）用它，坏了直接抛，并带上
    行列出错信息 —— 否则「配置写坏了」会表现成「配置不存在」，很难查。
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if strict:
            raise ConfigError(f"{path.name} 不存在（{path}）") from None
        return default
    except UnicodeDecodeError as exc:
        if strict:
            raise ConfigError(f"{path.name} 不是合法 UTF-8：{exc}") from exc
        return default
    except ValueError as exc:
        if strict:
            raise ConfigError(f"{path.name} 不是合法 JSON：{exc}") from exc
        return default
    except OSError as exc:
        if strict:
            raise ConfigError(f"{path.name} 读取失败：{exc}") from exc
        return default


class ConfigError(RuntimeError):
    """配置/索引等关键文件不可用。"""


# ---------------------------------------------------------------- 配置校验
#
# 配置是手写的，一个手滑（"skills": ["../../x"]）不该让程序写到市场目录外面去。
# 所有来自配置的「名字」都必须先过 validate_id，所有由名字拼出来的路径
# 都必须再过一次 ensure_child。

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}/[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
_VER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")

# Windows 保留设备名（不区分大小写，且带扩展名也算：CON.txt 同样非法）
WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def validate_id(value, field: str) -> str:
    """插件名 / skill 名必须是安全的单段标识符。"""
    if not isinstance(value, str):
        raise ConfigError(f"{field} 必须是字符串，实际是 {type(value).__name__}")
    if not _ID_RE.fullmatch(value):
        raise ConfigError(
            f"{field} 非法：{value!r}\n"
            "只允许「字母或数字开头，后跟字母 / 数字 / . _ -」，最长 128 字符；"
            "不允许路径分隔符、盘符、.. 或空白。"
        )
    if value.split(".")[0].upper() in WINDOWS_RESERVED:
        raise ConfigError(f"{field} 使用了 Windows 保留设备名：{value!r}")
    return value


def validate_version(value, field: str) -> str:
    if not isinstance(value, str) or not _VER_RE.fullmatch(value):
        raise ConfigError(f"{field} 不是合法版本号：{value!r}")
    return value


def ensure_child(root: Path, child: Path) -> Path:
    """确认 child 落在 root 之内，否则拒绝。

    这是「最后一道闸」：即使前面某处漏了校验，越界路径也会在这里被拦下。
    """
    r = Path(root).resolve()
    c = Path(child).resolve()
    if c != r and r not in c.parents:
        raise ConfigError(f"路径越界：{c} 不在 {r} 之内")
    return c


def collision_key(value: str) -> str:
    """做「同名判定」用的归一 key。

    主战场是 Windows，而 NTFS 默认大小写不敏感 —— `SKILLS_DIR/Story` 与
    `SKILLS_DIR/story` 在磁盘上就是同一个目录。如果只在字符串层面比较，
    两个条目会互相覆盖，而且是**静默**覆盖。

    所以在**所有平台**上统一 casefold：宁可 Linux 也拒绝这种配置，
    也不要让同一个配置在两套系统上跑出两种行为。
    """
    return str(value).casefold()


def _check_collision(seen: dict, raw: str, where: str, what: str) -> None:
    """seen 的 key 是 casefold 后的名字，value 是第一次出现时的原始写法。"""
    key = collision_key(raw)
    prev = seen.get(key)
    if prev is not None and prev != raw:
        raise ConfigError(
            f"{what}名大小写冲突：{prev!r} 与 {raw!r}（{where}）\n"
            "Windows 文件系统大小写不敏感，这两个名字会指向同一个目录并互相覆盖。\n"
            "请只保留一个写法（本工具在所有平台上都拒绝这种配置，避免跨平台行为不一致）。"
        )
    if prev is not None:
        raise ConfigError(f"{what}名重复：{raw}")
    seen[key] = raw


def _check_number(value, field: str, *, lo: float = 0, integer: bool = False):
    """配置里的数值统一在这里过一遍。

    两个坑：
      · NaN / Infinity 能通过 `isinstance(v, (int, float))` 和大小比较，
        混进内部状态后会让 `int()` 抛异常或者让阈值判断永远为假。
      · `maxSizeBytes: 1.9` 会被后面的 `int(...)` 静默截成 1 —— 用户以为
        自己设了 1.9 字节，实际按 1 字节算。这种「悄悄改写的配置」应当直接拒绝。
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{field} 必须是数字。")
    if isinstance(value, float) and not math.isfinite(value):
        raise ConfigError(f"{field} 不能是 NaN 或 Infinity。")
    if integer and not isinstance(value, int):
        raise ConfigError(
            f"{field} 必须是整数（{value!r} 的小数部分会被静默截掉，容易误配）。")
    if value < lo:
        raise ConfigError(f"{field} 必须不小于 {lo}。")
    return value


def validate_repo(value, field: str = "repo") -> str:
    """GitHub 仓库标识 `owner/repo` 的唯一校验入口。

    配置层、API 层、后台任务层共用这一个 —— v2.3 之前只有配置层在用，
    `/api/remote/add` 只判断了「非空」，等于把已有的边界绕过去了。

    拒绝：空、非字符串、超长、不是 owner/repo 形状、任一段以 `-` 开头
    （会被下游当命令行选项）、任一段是 `.` / `..`、含空白或控制字符。
    """
    if not isinstance(value, str):
        raise ConfigError(f"{field} 必须是字符串，实际是 {type(value).__name__}。")
    if not value or value != value.strip():
        raise ConfigError(f"{field} 不能为空或首尾带空白：{value!r}")
    if len(value) > 201:
        raise ConfigError(f"{field} 太长了（{len(value)} 字符）。")
    if not _REPO_RE.fullmatch(value):
        raise ConfigError(
            f"{field} 必须是 owner/repo 形式（只用字母数字 . _ -，两段都要以字母数字开头）：{value!r}")
    owner, _, repo = value.partition("/")
    for seg in (owner, repo):
        if seg in (".", ".."):
            raise ConfigError(f"{field} 里不能出现 {seg!r}：{value!r}")
    return value


def validate_config(cfg: dict) -> list:
    """校验配置结构与安全性，返回 warning 列表；结构性错误直接抛 ConfigError。

    这里只查「结构和安全」，不查「skill 在本机存不存在」——
    后者是 deep_check 的活，因为源不在本机时市场会沿用历史副本，属于正常状态。
    """
    if not isinstance(cfg, dict):
        raise ConfigError("market.config.json 的顶层必须是一个对象。")

    warnings = []

    # --- 市场标识
    mid = cfg.get("marketId")
    if not mid:
        raise ConfigError("配置缺少 marketId。")
    validate_id(mid, "marketId")
    if not isinstance(cfg.get("name", ""), str):
        raise ConfigError("name 必须是字符串。")
    owner = cfg.get("owner", {})
    if not isinstance(owner, dict):
        raise ConfigError("owner 必须是一个对象，例如 {\"name\": \"...\"}。")
    if "schemaVersion" in cfg:
        sv = cfg["schemaVersion"]
        if not isinstance(sv, int) or isinstance(sv, bool) or sv < 1:
            raise ConfigError("schemaVersion 必须是正整数。")

    # --- 本机插件
    plugins = cfg.get("localPlugins", [])
    if not isinstance(plugins, list):
        raise ConfigError("localPlugins 必须是数组。")
    seen_plugins = {}                      # casefold(name) -> 第一次出现的原始写法
    skill_owner = {}                       # casefold(skill) -> (原始写法, 插件原始写法)
    for i, spec in enumerate(plugins):
        where = f"localPlugins[{i}]"
        if not isinstance(spec, dict):
            raise ConfigError(f"{where} 必须是对象。")
        name = validate_id(spec.get("name"), f"{where}.name")
        _check_collision(seen_plugins, name, where, "插件")
        validate_version(spec.get("version", "1.0.0"), f"{where}({name}).version")
        for key in ("description", "description_en", "category", "homepage", "repository", "license"):
            if key in spec and not isinstance(spec[key], str):
                raise ConfigError(f"{where}({name}).{key} 必须是字符串。")
        if "keywords" in spec:
            if not isinstance(spec["keywords"], list) or not all(
                    isinstance(k, str) for k in spec["keywords"]):
                raise ConfigError(f"{where}({name}).keywords 必须是字符串数组。")
        if "author" in spec and not isinstance(spec["author"], dict):
            raise ConfigError(f"{where}({name}).author 必须是对象。")

        skills = spec.get("skills", [])
        if not isinstance(skills, list) or not skills:
            raise ConfigError(f"{where}({name}).skills 必须是非空数组。")
        seen_here = {}
        for s in skills:
            sid = validate_id(s, f"{where}({name}).skills")
            _check_collision(seen_here, sid, f"{where}({name}).skills", "skill")
            key = collision_key(sid)
            prev = skill_owner.get(key)
            if prev is not None and collision_key(prev[1]) != collision_key(name):
                raise ConfigError(
                    f"skill {sid!r} 被两个插件同时声明：{prev[1]} 与 {name}"
                    "（同一个 skill 只能属于一个插件，否则内容会互相覆盖）"
                )
            skill_owner[key] = (prev[0] if prev else sid, name)
            # 最后一道闸：拼出来的路径必须在合法根目录之内
            ensure_path = MARKET_ROOT / "plugins" / name / "skills" / sid
            ensure_child(MARKET_ROOT / "plugins", ensure_path)
            ensure_child(SKILLS_DIR, SKILLS_DIR / sid)

    # --- 远端源
    remotes = cfg.get("remoteSources", [])
    if not isinstance(remotes, list):
        raise ConfigError("remoteSources 必须是数组。")
    seen_repos = {}                        # casefold(repo) -> 原始写法
    for i, spec in enumerate(remotes):
        where = f"remoteSources[{i}]"
        if not isinstance(spec, dict):
            raise ConfigError(f"{where} 必须是对象。")
        repo = spec.get("repo")
        try:
            validate_repo(repo, f"{where}.repo")
        except ConfigError:
            raise ConfigError(f"{where}.repo 必须是 owner/repo 形式：{repo!r}")
        # GitHub 的 owner/repo 也是大小写不敏感的，同样要归一
        _check_collision(seen_repos, repo, where, "远端源")

    # --- 打包 / 回收站 / 校验模式
    pack = cfg.get("packaging", {})
    if not isinstance(pack, dict):
        raise ConfigError("packaging 必须是对象。")
    if pack.get("verify", "auto") not in ("auto", "fast", "strict"):
        raise ConfigError('packaging.verify 只能是 auto / fast / strict。')
    if "hashAlgorithm" in pack and pack["hashAlgorithm"] != "sha256":
        raise ConfigError('packaging.hashAlgorithm 目前只支持 "sha256"。')
    if "hashChunkBytes" in pack:
        _check_number(pack["hashChunkBytes"], "packaging.hashChunkBytes",
                      lo=4096, integer=True)
    for key in ("excludeNames", "excludeGlobs"):
        v = pack.get(key, [])
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            raise ConfigError(f"packaging.{key} 必须是字符串数组。")

    trash = cfg.get("trash", {})
    if not isinstance(trash, dict):
        raise ConfigError("trash 必须是对象。")
    if "maxAgeDays" in trash:
        _check_number(trash["maxAgeDays"], "trash.maxAgeDays", lo=0)
    if "maxSizeBytes" in trash:
        # 必须整数：避免 1.9 被 int() 截成 1 这种「悄悄改配置」
        _check_number(trash["maxSizeBytes"], "trash.maxSizeBytes", lo=0, integer=True)
    if "protectModified" in trash and not isinstance(trash["protectModified"], bool):
        raise ConfigError("trash.protectModified 必须是布尔值。")

    if not plugins and not remotes:
        warnings.append("配置里既没有本机插件也没有 GitHub 源，市场是空的。")

    return warnings


def load_config() -> dict:
    cfg = read_json(CONFIG_PATH, None, strict=True)
    validate_config(cfg)
    return cfg


def verify_mode() -> str:
    """packaging.verify：auto（默认）/ fast / strict。"""
    try:
        cfg = load_config()
    except ConfigError:
        return "auto"
    mode = (cfg.get("packaging") or {}).get("verify", "auto")
    return mode if mode in ("auto", "fast", "strict") else "auto"


def needs_exact(purpose: str) -> bool:
    """这个用途要不要读到文件内容（完整 SHA-256）。

    · strict  —— 一律精确（连网页状态也精确，方便排查）
    · auto / fast —— 只有 install / uninstall 这种会**动用户磁盘**的用途才精确。
      网页状态用廉价指纹，误差只是显示；而 fast 不再能削弱破坏性判定，
      v2 那种「fast 导致 update 漏判 modified」的路子被彻底堵死。
    """
    if purpose not in CLASSIFY_PURPOSES:
        raise ValueError(f"未知用途 {purpose!r}")
    if verify_mode() == "strict":
        return True
    return purpose in EXACT_PURPOSES


def hash_chunk_bytes() -> int:
    """流式 SHA-256 的块大小，来自 packaging.hashChunkBytes。"""
    try:
        cfg = load_config()
    except ConfigError:
        return HASH_CHUNK_BYTES
    v = (cfg.get("packaging") or {}).get("hashChunkBytes", HASH_CHUNK_BYTES)
    if isinstance(v, int) and not isinstance(v, bool) and v >= 4096:
        return v
    return HASH_CHUNK_BYTES


# ---------------------------------------------------------------- 文件锁

class FileLockTimeout(RuntimeError):
    pass


# 线程级的「本线程当前是否持有市场锁」计数。
# FileLock._depth 是**实例**属性，没法跨实例识别重入，所以单独放一份模块级状态。
_HELD = threading.local()


class FileLock:
    """跨平台排他文件锁，**可重入**（同进程同线程重复获取不会自锁）。

    Windows 用 msvcrt.locking，POSIX 用 fcntl.flock。都没有时退化成
    O_EXCL 哨兵文件。

    注意：这把锁只能串行化**本工具自己**的多个进程。WorkBuddy 自身
    不会来抢这把锁，所以对 known_marketplaces.json 仍然保留
    「写回校验」，两者互补。
    """

    _depth = threading.local()

    def __init__(self, path: Path = LOCK_PATH, timeout: float = 15.0):
        self.path = Path(path)
        # v2.7：锁文件可能落在全新 STATE_HOME/locks/ 下，父目录必须先建好
        # （os.open(O_CREAT) 不会建父目录）。
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        self.timeout = timeout
        self._fd = None

    # ---- 平台原语
    def _try_lock(self) -> bool:
        fd = os.open(str(self.path), os.O_RDWR | os.O_CREAT, 0o644)
        try:
            if os.fstat(fd).st_size == 0:
                os.write(fd, b"\0")
            if os.name == "nt":
                import msvcrt

                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            return False
        self._fd = fd
        return True

    def _unlock(self) -> None:
        if self._fd is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                os.lseek(self._fd, 0, os.SEEK_SET)
                msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._fd, fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

    # ---- 可重入包装
    def __enter__(self):
        depth = getattr(self._depth, "n", 0)
        if depth > 0:
            self._depth.n = depth + 1
            return self
        deadline = time.monotonic() + self.timeout
        delay = 0.02
        while True:
            if self._try_lock():
                self._depth.n = 1
                _HELD.n = getattr(_HELD, "n", 0) + 1
                return self
            if time.monotonic() >= deadline:
                raise FileLockTimeout(
                    f"等锁超时（{self.timeout:.0f}s）：{self.path}\n"
                    "可能另一次安装/同步正在跑。若确认没有，删掉这个文件再试。"
                )
            time.sleep(delay)
            delay = min(delay * 1.6, 0.25)

    def __exit__(self, *exc):
        depth = getattr(self._depth, "n", 0)
        if depth > 1:
            self._depth.n = depth - 1
            return False
        self._depth.n = 0
        _HELD.n = max(0, getattr(_HELD, "n", 0) - 1)
        self._unlock()
        return False


def locked(timeout: float = 15.0):
    """取市场锁。**同线程可重入** —— 已持锁时直接返回空锁。

    为什么需要这一层：`locked()` 每次调用都会 new 一个 FileLock 实例，
    而 `FileLock._depth` 是**实例**属性。同一个线程在已持锁的状态下再
    `with locked():` 会拿着**另一个 fd** 去抢同一段区域，Windows 的
    msvcrt.locking / POSIX 的 flock 都会立刻失败 —— 结果是等锁超时，
    也就是自己把自己锁死。用一个线程级计数器绕开它。
    """
    if getattr(_HELD, "n", 0) > 0:
        return _NullLock()
    return FileLock(LOCK_PATH, timeout=timeout)


class _NullLock:
    """已经持锁时的占位上下文。"""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


# ---------------------------------------------------------------- 文件索引 / 指纹

def _is_reparse(st) -> bool:
    """Windows 重解析点：符号链接、junction、挂载点都算。

    实测（本机 Python 3.13）：junction 的 `is_symlink()` 返回 **False**，
    但 `st_file_attributes` 带 FILE_ATTRIBUTE_REPARSE_POINT。
    只看 `is_symlink()` 会把 junction 当成普通目录递归进去，
    把技能目录之外的内容带进市场目录 —— 这是实打实能造出来的逃逸路径。
    """
    attr = getattr(st, "st_file_attributes", 0)
    return bool(attr & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


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


def _walk_tree(root: Path, excluded, files: dict, links: list, errors: list) -> None:
    """把一个子树走完，结果写进调用方给的 files / links / errors。

    「一次遍历」的公共实现：单根（_scan）和多根分桶（_scan_many）都走这里，
    免得两份游走逻辑慢慢长歪。

    用 os.scandir 而不是 os.walk：DirEntry 的 stat 结果直接来自目录项、缓存着，
    不用再按路径查一次 —— 既更快，又能顺手拿到文件属性位。

    **软链 / junction 一律跳过、不跟随**：一个指向技能目录之外的重解析点，
    跟随它就会把外部文件的内容带进市场目录（copy2 默认跟随软链）。
    """
    root = Path(root)
    if not root.is_dir():
        return
    stack = [str(root)]
    while stack:
        cur = stack.pop()
        try:
            entries = list(os.scandir(cur))
        except OSError as exc:
            errors.append((cur, str(exc)))      # 读不了这个目录 —— 别当成"空的"
            continue
        for e in entries:
            if excluded is not None and excluded(e.name):
                continue
            try:
                st = e.stat(follow_symlinks=False)
                if e.is_symlink() or _is_reparse(st):
                    links.append(e.path)
                    continue
                if stat.S_ISDIR(st.st_mode):
                    stack.append(e.path)
                    continue
                if not stat.S_ISREG(st.st_mode):
                    continue
            except OSError as exc:
                errors.append((e.path, str(exc)))   # stat 失败同样是"看不见"
                continue
            rel = str(Path(e.path).relative_to(root)).replace("\\", "/")
            files[rel] = (st.st_size, st.st_mtime_ns)


def _raise_if_errors(errors: list, what: str) -> None:
    if errors:
        sample = "、".join(p for p, _ in errors[:3])
        raise ScanError(
            f"{what} 扫描不完整：{len(errors)} 处读取失败（例如 {sample}）。"
            "拒绝在「看不见部分内容」的情况下继续 —— 那会把读失败当成文件不存在。")


def _scan(root: Path, excluded=None, *, on_error: str = "skip") -> tuple:
    """**一次遍历**同时得到：
        files = {相对路径str: (size, mtime_ns)}
        links = 被跳过的重解析点（软链 / junction，绝对路径）

    on_error:
      "skip"（默认）—— 读不了的条目跳过，适合状态展示这类"尽力而为"的用途
      "raise"      —— 有任何一处读失败就抛 ScanError，破坏性操作必须用这个
    """
    files: dict = {}
    links: list = []
    errors: list = []
    _walk_tree(root, excluded, files, links, errors)
    if on_error == "raise":
        _raise_if_errors(errors, f"{Path(root).name}")
    return files, links


def _scan_many(named: dict, excluded=None, *, on_error: str = "raise") -> tuple:
    """一次调用、只走给定的那些子树，并且**按名字分桶**。

    返回 ({name: {rel: (size, mtime)}}, {name: [links]}, errors)

    为什么不是「扫一遍整棵 skills 根再按前缀切」：
      · 市场声明 6 个 skill、而 skills 根下有 400 个别的目录时，整树扫要
        走 2854 个文件（实测 223 ms），而只需要其中 6 个子树；
      · 切分本身也不便宜 —— `_sub_index` 每个 skill 都要遍历一遍**完整**索引，
        6 个 skill 就是 17124 次字典迭代（实测）。
    分桶之后两个问题一起没了：扫描量 = O(声明的那几个 skill)，
    取用时 O(1) 拿到自己的子树。
    """
    buckets: dict = {name: {} for name in named}
    link_buckets: dict = {name: [] for name in named}
    errors: list = []
    for name, root in named.items():
        _walk_tree(root, excluded, buckets[name], link_buckets[name], errors)
    if on_error == "raise":
        _raise_if_errors(errors, "skills 目录")
    return buckets, link_buckets, errors


def file_index(root: Path, excluded=None, *, on_error: str = "skip") -> dict:
    """只要文件索引的便捷包装。"""
    return _scan(root, excluded, on_error=on_error)[0]


def fingerprint_from_index(index: dict, links=()) -> dict:
    """从一份**已经扫好的**索引算指纹，不再碰磁盘。

    批量状态检查和安装暂存阶段都复用这个 —— 索引已经在那儿了，
    没必要为了算指纹再把同一棵树走一遍。
    """
    mtimes = [v[1] for v in index.values()]
    return {
        "files": len(index),
        "bytes": sum(v[0] for v in index.values()),
        "mtime_ns_max": max(mtimes, default=0),
        "mtime_ns_sum": sum(mtimes),
        "links": len(links),
    }


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


def sha256_file(path: Path, chunk_size: int | None = None) -> bytes:
    """流式 SHA-256：内存占用 O(chunk)，不是 O(文件大小)。

    strict 模式会对每个文件算哈希；某个 skill 里出现几百 MB 的大文件时，
    read_bytes() 会直接把文件整个读进内存。分块读则与文件大小无关。

    实测（64 MiB 文件）：read_bytes 峰值 64.0 MiB → 流式 2.01 MiB，
    耗时可忽略（44.9 ms vs 45.5 ms）。
    """
    cs = chunk_size or HASH_CHUNK_BYTES
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        while True:
            chunk = fh.read(cs)
            if not chunk:
                break
            h.update(chunk)
    return h.digest()


def _same_content(a: Path, b: Path, chunk_size: int | None = None) -> bool:
    """两个文件内容是否一致（strict 模式下用）。流式比对，不整读。"""
    cs = chunk_size or HASH_CHUNK_BYTES
    try:
        if a.stat().st_size != b.stat().st_size:
            return False
        return sha256_file(a, cs) == sha256_file(b, cs)
    except OSError:
        return False


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


class SkillScanCache:
    """一次批量扫描**已声明的那些 skill**，结果按 skill 分桶。

    build_state 会给每个插件的每个 skill 各调一次 classify_skill，而 ui 模式下
    每个 skill 都要一个指纹。v2.3 的做法是「扫一遍整棵 SKILLS_DIR 再按前缀切」，
    在「市场 6 个 skill + skills 根下 400 个无关目录」的场景里实测要扫 2854 个文件
    （223 ms），而且每切一个 skill 都要遍历一遍完整索引（6 个 skill = 17124 次迭代）。

    现在换成：只走声明的那些子树，扫描时就按名字分桶。
      · 扫描量 = O(声明的那几个 skill)
      · `fingerprint(name)` 是 O(1) 取桶
    """

    def __init__(self, names, excluded=None):
        self._names = [str(n) for n in names]
        self._excluded = excluded
        self._buckets = None
        self._links = None
        self.scans = 0
        self.errors: list = []

    def _ensure(self):
        if self._buckets is not None:
            return
        named = {n: SKILLS_DIR / n for n in self._names}
        self._buckets, self._links, self.errors = _scan_many(
            named, self._excluded, on_error="skip")   # UI 用：尽量显示，不因为一处失败就白屏
        self.scans += 1

    def fingerprint(self, sname: str) -> dict:
        """等价于 quick_fingerprint(SKILLS_DIR / sname)，但不单独遍历。"""
        self._ensure()
        return fingerprint_from_index(self._buckets.get(str(sname), {}),
                                      self._links.get(str(sname), ()))


# ---------------------------------------------------------------- skill 元信息

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S | re.M)


def parse_skill_meta(skill_dir: Path) -> dict:
    """从 SKILL.md 的 frontmatter 里取 version/description，取不到就给默认值。"""
    meta = {"version": "1.0.0", "description": ""}
    try:
        text = (Path(skill_dir) / "SKILL.md").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return meta
    m = _FM_RE.match(text)
    if not m:
        return meta
    for line in m.group(1).splitlines():
        if line.startswith("version:"):
            meta["version"] = line.split(":", 1)[1].strip().strip('"').strip("'") or "1.0.0"
        elif line.startswith("description:"):
            meta["description"] = line.split(":", 1)[1].strip().strip('"').strip("'")[:300]
    return meta


# ---------------------------------------------------------------- 打包

def _make_excluder(exclude_names, exclude_globs):
    """返回一个 name -> bool 的排除判定。"""
    import fnmatch

    names = set(exclude_names or [])
    globs = list(exclude_globs or [])

    def excluded(name: str) -> bool:
        if name in names:
            return True
        return any(fnmatch.fnmatch(name, pat) for pat in globs)

    return excluded


def _sub_index(full: dict, prefix: str) -> dict:
    """从一个「以 root 为基准」的整树索引里切出 prefix/ 这一支。

    key 会从 "alpha/SKILL.md" 变回 "SKILL.md"，这样 _sync_tree 完全无感。
    用来把「每个 skill 扫一次目标目录」降成「每个插件扫一次目标目录」。
    """
    p = str(prefix).rstrip("/") + "/"
    n = len(p)
    return {rel[n:]: val for rel, val in full.items() if rel.startswith(p)}


def _sync_tree(src: Path, dst: Path, excluded=None, strict: bool = False,
               dst_index: dict | None = None) -> tuple:
    """把 src **增量**同步到 dst，返回 (拷贝数, 删除数, 源端总字节, 跳过的软链数)。

    判定用 size + **mtime_ns**（v1 的 int(st_mtime) 会把精度砍到秒，
    同秒内大小不变的修改会被漏掉）。
    strict=True 时，对「大小和时间戳都一样」的文件再比一遍内容 ——
    代价是要读文件，但能堵住「改完再把时间戳改回去」这种情况。

    dst_index 可由调用方预先算好（插件级整树扫描 + _sub_index 切片），
    避免每个 skill 都把目标目录重扫一遍。

    **两侧都 fail-closed**：源端少看见一个文件，目标端那份就会被判成「多余」
    而被删掉 —— 一次读取抖动就能把市场里的内容删掉（已用探针复现）。
    所以这里任何一处扫描失败都直接抛 ScanError，宁可整次同步失败。
    """
    src_index, src_links = _scan(src, excluded, on_error="raise")
    if dst_index is None:
        dst_index, _ = _scan(dst, excluded, on_error="raise")
    # strict 下每个变动文件都要比内容 —— 块大小在这里解析一次，别在循环里反复读配置
    chunk = hash_chunk_bytes() if strict else HASH_CHUNK_BYTES
    copied = removed = 0

    for rel, (ssize, smtime) in src_index.items():
        dfull = dst / rel
        cur = dst_index.get(rel)
        skip = False
        if cur is not None:
            if strict:
                # strict：以内容为准 —— 内容一样就不重写，哪怕时间戳不同
                skip = (cur[0] == ssize) and _same_content(src / rel, dfull, chunk)
            else:
                # fast：只看 size + mtime_ns
                skip = (cur[0] == ssize and cur[1] == smtime)
        if skip:
            continue
        dfull.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(src / rel, dfull)
            copied += 1
        except OSError as exc:
            log("error", "sync", f"拷贝 {rel} 失败：{exc}")

    # 删掉目标端多出来的（通常个位数），并记下受影响的目录
    prune_dirs = set()
    for rel in dst_index:
        if rel in src_index:
            continue
        p = dst / rel
        try:
            p.unlink()
            removed += 1
            prune_dirs.add(str(p.parent))
        except OSError:
            pass

    # 只收「确实删过文件的那些目录」及其祖先。
    # 不对全树目录试 rmdir —— 宿主/沙箱会给每次 os.rmdir 套一层路径校验，
    # 几百次空转 rmdir 能占掉整个同步一半的耗时（实测 0.32s/156 次）。
    tried = set()
    for d in sorted(prune_dirs, key=len, reverse=True):
        cur = Path(d)
        while cur not in tried and cur != dst and dst in cur.parents:
            tried.add(cur)
            try:
                os.rmdir(cur)
            except OSError:
                break
            cur = cur.parent

    if src_links:
        log("warn", "sync", f"{len(src_links)} 个符号链接被跳过，未打包：{src_links[:3]}")

    total = sum(v[0] for v in src_index.values())
    return copied, removed, total, len(src_links)


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

def _tail_lines(path: Path, want: int, block: int = 64 * 1024) -> tuple:
    """从文件**尾部**反向分块读，凑够 want 行就停。

    返回 (行列表[按时间正序, bytes], 是否读到了文件开头)。
    没读到开头时，返回的第一行可能是被截断的半行 —— 调用方靠第二个返回值判断。

    为什么不直接 `deque(fh, maxlen=N)`：那样内存是 O(N)，但**磁盘 I/O 仍然是
    整个文件**。实测 3 份日志合计 28.6 MB 时，取最后 60 行要读满 28.6 MB、
    耗时 1.4 秒。反向读只碰最后 64 KB，成本与日志历史长度无关。
    """
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            pos = fh.tell()
            chunks, newlines = [], 0
            while pos > 0 and newlines <= want:
                step = min(block, pos)
                pos -= step
                fh.seek(pos)
                chunk = fh.read(step)
                chunks.append(chunk)
                newlines += chunk.count(b"\n")
            at_start = pos == 0
    except OSError:
        return [], True
    data = b"".join(reversed(chunks))
    lines = data.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()                     # 文件以换行结尾
    if not at_start and lines:
        lines.pop(0)                    # 最前面那条是被截断的半行
    if len(lines) > want:
        lines = lines[-want:]
    return lines, at_start


def tail_log(limit: int = 60) -> list:
    """最近 limit 条事件（最新在前）。

    **真 tail**：从每个文件的尾部反向读，凑够就停。
    多份轮转日志按「新 → 旧」补足，所以日志越大，读的量也不会跟着涨。

    （v2.3 的实现是 `deque.extend(fh)` —— 内存省了，I/O 没省：
    每次仍要把整份日志从头扫一遍。README 里写的「反向读」名不副实。）
    """
    want = max(1, int(limit))
    files = [LOG_PATH]                  # 最新的一份
    for i in range(1, LOG_KEEP + 1):    # 越往后越旧
        files.append(LOG_PATH.with_name(f"{LOG_PATH.stem}.{i}{LOG_PATH.suffix}"))

    buf: list = []                      # 按时间正序累积
    for p in files:
        if not p.is_file():
            continue
        need = want - len(buf)
        if need <= 0:
            break
        lines, at_start = _tail_lines(p, need)
        buf = lines + buf
        if not at_start:
            break                       # 这一份还没读到头，就说明已经凑够了

    out = []
    for raw in buf[-want:]:
        text = raw.decode("utf-8", "replace").strip()
        if not text:
            continue
        try:
            out.append(json.loads(text))
        except ValueError:
            continue
    return list(reversed(out))


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
