# Changelog

本项目的版本号唯一来源是 `src/workbuddy_market/version.py` 的 `MARKET_VERSION`。
每轮代码评审为一个次版本；schema 版本（ownership / tx / state / config）独立演进。
更详细的每轮变更说明见 `README.md` 第十节起（v2 → v2.9 各一节）。

## 未发布（文档）

- 新增 `docs/WorkBuddy-5.7.6-面板实测.md`：WorkBuddy 5.7.6 三个标签页的数据源实测、
  自定义市场在面板中的可见形态（技能页「用户自定义」）、与本机市场的优劣对比。
- README 方式 A 与第九节 FAQ 按 5.7.6 实测修正（面板无「市场来源」入口）。
- 纯文档变更，无代码改动，版本号不变。

## 2.9.0 — 2026-10-07（R3：config / scanner / sync / version 迁入）

- `src/workbuddy_market/` 新增 `config.py`（validate_* / ensure_child / collision_key /
  validate_config / load_config / verify_mode / needs_exact / hash_chunk_bytes）、
  `scanner.py`（_scan 全家 / SkillScanCache / parse_skill_meta / _make_excluder /
  _sub_index）、`sync.py`（_sync_tree）、`version.py`（版本常量唯一来源）。
- 全部逐字搬迁，行为零变化；`quick_fingerprint` / `tree_hash*` 因依赖
  `core._scan`（注入点）暂留 market_core。
- 注入点命名空间迁移：patch `core._walk_tree` 改为 patch
  `workbuddy_market.scanner._walk_tree`（selftest 第 19 节同批调整）。
- selftest 410 → 439 项，全绿。

## 2.8.0 — 2026-10-07（R2：拆出无状态基础设施包）

- `src/workbuddy_market/` 落地：`paths.py`（三层根目录 + 全部路径常量）、
  `errors.py`、`fsutil.py`（原子写 + JSON）、`hasher.py`（流式 SHA-256）、
  `locking.py`（可重入文件锁）、`logging.py`（事件流 + 真 tail）。
- 唯一必要适配：MARKET_ROOT 仓库根 fallback 改用 `parents[2]`（src 布局）。
- 新增协议设计稿（未实现）：`docs/protocol/{manifest-v1, provider-api, lockfile}.md`。
- selftest 384 → 410 项。

## 2.7.0 — 2026-10-07（R1：运行时与仓库分离）

- 三层根目录：`WBM_MARKET_ROOT` / `WBM_STATE_HOME` / `WBM_HOME`
  （旧 `GHPM_*` 兼容，每进程告警一次）。
- 运行状态收进 `~/.workbuddy-market/markets/<bucket>/`，同机多 clone 天然隔离；
  仅设旧变量时完整复刻 v2.6 布局。
- `migrate_runtime_files()`：旧运行时文件幂等搬入 STATE_HOME
  （os.replace 优先、跨卷退回 shutil.move、绝不删用户原件）。

## 2.6.0 — 2026-10-06

- ghpm 事件解析、任务取消竞态、进程树终止（POSIX 进程组 / Windows taskkill）、
  真并发闸门（barrier 实测并发上限）。

## 2.5.0 — 2026-10-06

- 并发压力、扫描失败 fail-closed（`_scan(on_error=)`）、崩溃点矩阵
  （tx_begin / os.replace / record_owner 五个注入点）。

## 2.4.0 — 2026-10-06

- 凭证前置（事务日志开不出来就不动磁盘）、恢复校验 expected hash、
  卸载事务化、日志真 tail（反向分块读）。

## 2.3.0 — 2026-10-06

- 事务日志与恢复、本地 API 鉴权加固、任务生命周期、扫描复用
  （SkillScanCache 分桶扫描）。

## 2.2.0 — 2026-10-06

- 回收站路径穿越防线、大小写碰撞全平台拒绝、`/api/open/path` 白名单、
  快速指纹误判修正。

## 2.1.0 — 2026-10-06

- 链接三层防线（打包不跟随 / 市场产物禁止 / 安装再禁一次），
  junction 用 `FILE_ATTRIBUTE_REPARSE_POINT` 判定。

## 2.0.0 — 2026-10-06

- 卸载安全模型（ownership 分级：可安全卸载 / 被改过 / 非本市场），
  `.trash/` 可回滚，安装事务化。
