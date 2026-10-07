# Changelog

本项目的版本号唯一来源是 `src/workbuddy_market/version.py` 的 `MARKET_VERSION`。
每轮代码评审为一个次版本；schema 版本（ownership / tx / state / config）独立演进。
更详细的每轮变更说明见 `README.md` 第十节起（v2 → v2.11 各一节）。

## 2.11.0 — 2026-10-07（社区注册表 + 端口修复）

- 新增 `src/workbuddy_market/registry.py`：注册表本体是本仓库的
  `registry/plugins.json`（静态收录人工审核，stars / pushedAt / latestSha
  由每日 CI 重建）。市场端按 6h TTL 在线拉取：`WBM_REGISTRY_URL` →
  raw.githubusercontent.com → api.github.com contents（raw accept 头）→
  本地副本四级路线；缓存落 STATE_HOME 的 `registry.json`（不可信文件，
  全挂退缓存，`source` / `stale` / `fetched` 如实标注来源）。
  网络接缝只有 `_registry_http_get()` 一处，自检假接缝离线覆盖。
- 每日 CI：`scripts/build_registry.py`（单条失败保旧值、原子写、--dry-run、
  GITHUB_TOKEN 只进请求头）+ `.github/workflows/registry.yml`
  （每天 21:21 UTC，无变化不提交，concurrency 排队）。
- market_server：`GET /api/registry`（口令 + Origin、600s 内存缓存 +
  single-flight、?force=1），响应带 installedRepos；「刷新目录」任务
  同时刷新 catalog 与 registry，serve() 自动循环顺带按 6h TTL 检查注册表。
- ★ Windows 假空闲端口修复：`_find_port` 探测 socket 原设 SO_REUSEADDR，
  Windows 上允许绑定别的进程正监听的端口——同机 3 个市场进程同绑 8777、
  请求随机打到旧进程（2026-10-07 实测复现，即网页「not found」红色提示
  的根因）。探测在 Windows 改用 SO_EXCLUSIVEADDRUSE；POSIX 不变
  （Linux 的 SO_REUSEADDR 本就不允许双活监听）。
- web/index.html：新增「社区目录」区块（与收录源大小写去重），社区条目
  一键安装的确认框如实标注来源；安装链路仍复用 ghpm 全套保障。
- selftest 第 27 节（round12）新增 32 项（含端口修复盯防：真起服务后
  `_find_port(p)` 绝不允许返回 p；以及 main fetch 契约回归：实际请求
  必须是 /repos/... 路径）；SELFTEST_VERSION → 2.11；
  版本盯防用例同步 2.11.0 / 2.11。全量 509 passed, 0 failed。
- 注册表收录 10 条（新增 mattpocock/skills、garrytan/gstack、
  addyosmani/agent-skills、nexu-io/open-design、Leonxlnx/taste-skill、
  K-Dense-AI/claude-scientific-skills 六个，全部核实含 SKILL.md 结构）。
- 同步清单：core docstring（标题/链/新增 v2.11 节）、README 自检项数
  四处 + 目录结构 + 第八节 DSH 表 + 新增第二十一节、
  provider-api.md §5 状态注记。

## 2.10.0 — 2026-10-07（GitHub 动态目录）

- 新增 `src/workbuddy_market/catalog.py`：收录源实时元数据（stars / pushed_at /
  描述 / 语言 / 归档）+ GitHub 全网搜索。网络接缝只有 `_gh_request()` 一处，
  自检假接缝离线覆盖。按 provider-api.md 设计稿口径：易变数据缓存在
  STATE_HOME 的 `catalog.json`（TTL 24h），永不写回 market.config.json。
- market_server 三个新接口（全过 _guard）：`GET /api/catalog`、
  `GET /api/gh/search?q=`（词长上限 + 120s 内存缓存 + single-flight）、
  `POST /api/catalog/refresh`（走 JobLimiter，满员 429）。
- serve() 起 daemon 线程：每 15 分钟检查、条目过 24h TTL 自动重拉
  （按条目判断，全新鲜时零网络；WBM_CATALOG_OFF=1 可关）。
  make_server 不起线程，自检零网络依赖。
- 容错：单仓库失败保旧值并记 errors；整轮全败不更新 refreshedAt
  （失败不算刷新过，循环才会重试）；缓存损坏当不存在。
- web/index.html：收录源卡片显示实时星数 / 更新日期，「刷新目录」按钮；
  搜索框本地零匹配且 ≥2 字时自动搜 GitHub 全网，结果可直接一键安装
  （非收录仓库的确认框提示确认来源；安装链路复用 ghpm 全套保障）。
- selftest 第 26 节（round11）新增 38 项；SELFTEST_VERSION → 2.10；
  版本盯防用例同步 2.10.0 / 2.10。全量 477 passed, 0 failed，
  launcher --status 深度自检通过、--recover 补记 0 项，
  真实网络冒烟（4 源刷新 + 全网搜索）通过。
- 同步清单：core docstring（标题/链/新增 v2.9+v2.10 两节）、
  README 自检项数三处 + 第八节 DSH 对照表 + 新增第二十节。

## 未发布（隐私加固）

- 外部隐私评审整改（2026-10-07）：PII 级问题只有一处 —— Git 提交历史的 QQ 邮箱。
  用 git-filter-repo 把全部提交的 author/committer 重写为 GitHub noreply 邮箱，
  `market.config.json`（个人 skill 组合）同时从全部历史移除。
- 配置两层化：`market.config.json` 移出版本库（gitignore，本机保留），
  新增入库模板 `market.config.example.json`；clone 后先复制模板再启动。
- 新增 `scripts/privacy-audit.py`（扫 Git 跟踪文件，可选 `--history` 扫全部历史：
  邮箱 / 手机号 / 私钥 / 凭据前缀 / 通用键值凭据 / 用户目录路径，发现即失败），
  CI 新增 privacy audit 步骤。
- 文档去个人化：README 移除「本机 14 个 skill」等环境描述、示例改通用插件；
  SECURITY.md 漏洞报告改走 Security Advisories；manifest-v1.md 作者示例改 Example Author。
- CI 修复（14f473b / 后续提交）：privacy-audit 在 Windows runner 管道输出默认 ANSI 代码页，
  打中文 UnicodeEncodeError —— 补 selftest 同款 stdout/stderr reconfigure(utf-8)；
  selftest 24C 的 repo-root 见证文件由 market.config.json（已不入库）改为
  market.config.example.json，fresh clone 场景恢复全绿。
- 内核代码零改动，版本号与 selftest 项数不变。

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
