# Changelog

本项目的版本号唯一来源是 `src/workbuddy_market/version.py` 的 `MARKET_VERSION`。
每轮代码评审为一个次版本；schema 版本（ownership / tx / state / config）独立演进。
更详细的每轮变更说明见 `docs/versions.md`（v2 → v2.11 各一节，v2.12 起自 README 迁出）。

## 2.18.0 — 2026-10-08（快赢包：版本回退修复 + 文档漂移修复 + 隐私历史审计 + macOS 冒烟）

外部评审（第二轮）四个快赢项，逐条探针核实后当轮落地：

**artifact 版本回退修复（评审 8）**
- `scripts/build_artifacts.py`：条目无 version 时不再回退 `0.0.0`
  （安装记录里出现无信息值），改回退 `<构建日期>.<sourceCommit 前 7 位>`
  （如 `2026.10.08.3e2a429`）。日期给人读、短 SHA 钉死来源；不可变身份
  仍是 sourceCommit，两者不混（评审推荐口径）。回退值过
  `config.validate_version` 闸。新增 `tests/unit/test_build_artifacts.py`
  （pytest 31 → 37 项）。

**FAQ 自检数漂移修复（评审 4）**
- README 已写 647 项，`docs/FAQ.md` 两处仍是 509 项（v2.12 时代的旧数），
  违反本项目「数量必须同步」的维护规则 —— 全部对齐 647。
  CI 自动生成测试状态（徽章 / generated 文件）进 v3 候选。

**隐私历史审计 CI（评审 10）**
- 新增 `.github/workflows/privacy-history.yml`：每周一 03:00 UTC +
  手动触发，`privacy-audit.py --history` 扫 `git log -p --all`
  （含提交元数据；checkout 用 fetch-depth: 0）。「工作区干净」不等于
  「历史干净」——push 级 CI 只扫当前跟踪文件，全历史审计放定期任务。
  2026-10-07 本项目已全历史重写为 noreply 邮箱，此项为持续盯防。

**macOS 语义冒烟槽位（评审 11）**
- ci.yml test 矩阵加 `macos-latest`；`posix-smoke.py` 从 Linux-only
  扩到全部非 Windows 槽位（`runner.os != 'Windows'`）。darwin 与 linux
  同为 POSIX 但此前从未被本项目验证，先让语义冒烟说话；macOS 侧
  selftest 全量门槛仍不在本轮范围。

**其他**
- 版本号同步：version.py / core docstring / SELFTEST_VERSION /
  24C·25B 版本盯防用例（硬编码防漂移）。

## 2.17.0 — 2026-10-08（WorkBuddy Adapter + CI 产物源 + Web 拆文件 + pytest 试点）

**WorkBuddy Adapter（评审 7，R6 半程：register 迁出）**
- 新模块 `workbuddy_market/adapters/workbuddy.py`：known_marketplaces.json
  的全部读写（含 strict「坏了宁可报错也不覆盖」口径）、纳秒戳备份与轮转、
  条目构造、乐观合并写入（`commit_known`）、`register` / `unregister`、
  `capabilities()` 能力矩阵（`security_scan` / `skill_enable` 等未验证能力
  **如实 False，不虚报**）、`known_health()`（deep_check 消费）。
  market_core 的注册段（约 180 行）逐字迁入；core 侧全部 re-export，
  第三方 `import market_core` 不受影响。
- **patch 语义随迁**（R4 ownership/trash 同一先例）：要拦截注册链路里的
  读，patch `workbuddy_market.adapters.workbuddy.read_known_or_die`；
  patch `core._read_known_or_die` 不再拦到 adapter 内部调用。
- `register()` 依赖的 `_sync_packaging` 注入点经 core 晚绑定（R4/R5 纪律）。
- 以后 WorkBuddy 5.x / 6.x 换市场格式，只改 adapter 一个文件。

**CI 产物源（评审 1 的后半程：artifact 有了源头）**
- `scripts/build_artifacts.py`：按注册表条目的 **sourceCommit** 拉
  tarball（不是默认分支）→ `safe_extract_tar`（穿越 / 链接 / 设备成员
  拒绝；自动剥 GitHub tarball 的 `<repo>-<ref>/` 前缀）→
  `choose_skills_root` 三种收录形态（root/skills/、子目录即 skill、
  root 即 skill；都不是 → 诚实失败）→ `pack_package` → zip →
  `report.json`（packageHash / manifestHash / asset / sourceCommit）。
  单条失败记录不拖垮整批；`--patch-registry` 把哈希回写 plugins.json。
- `.github/workflows/artifacts.yml`：每日构建 → 发布 GitHub Release 资产
  → PR 回写 artifact 字段（不直推 main，与 registry.yml 同一约束）。
  同日重跑得到同一份 packageHash（sourceCommit 固定 + pack 规范化），
  Release 资产 `--clobber` 覆盖是安全的。
- 至此 v2.16 的安装链有了产物源：Registry（packageUrl+packageHash）→
  Release 资产 → 下载 → 校验 → 事务安装，端到端闭环。

**CI 提档（评审 10 / 5）**
- `package` job（Windows + Ubuntu）：`python -m build` → 安装 wheel →
  CLI smoke（`workbuddy-market doctor --help` 必须退出 0）—— 把
  「源码跑得通、pip 装完就坏」挡在 CI 里。`doctor.main` 顺手换 argparse
  （`--help` 有正经出口，未知参数不再被静默忽略）。
- pytest 步骤（双平台）：`tests/unit` 试点 31 项（hasher / registry 解析
  / packaging+artifact 攻击面），conftest 在首次导入前预设 WBM_* 隔离
  环境；pyproject 增 `dev` extra 与 `[tool.pytest.ini_options]`。
  selftest 保留为**零依赖一键环境诊断**，定位不变（评审 9 的组合拳）。
- `scripts/posix-smoke.py`（Ubuntu 槽位）：fcntl 锁独占与重入、symlink
  被 `_scan` 如实报出、`os.replace` 原子换位、`ensure_child` 穿越闸门、
  `unpack_zip` zip-slip 防线 —— POSIX 分支第一次有了**语义级**证据
  （v3-roadmap §5 认可的冒烟路线；Windows 上运行明确 SKIP）。

**Web 拆文件（评审 9，零构建不变）**
- `web/index.html` 913 → 84 行；`app.js`（635 行）+ `style.css`
  （192 行）随仓库分发，`<script src>` / `<link>` 引用，零 npm / 零
  bundler / 零 node（node --check 只是开发期校验手段）。
- 服务端 `/static` **白名单制**静态服务：`_STATIC_FILES` 名字 → Content-Type
  精确映射，白名单外的名字（含一切穿越写法）一律 404 —— 不存在「路径
  解析」这一步；`no-store` + `nosniff` 沿用 `_send` 统一头；静态文件
  不含机密（口令注入点仍只在 index.html 的 meta）。

**版本同步**：version 2.17.0；selftest 625 → 647 项（第 32 节 22 项：
adapter 同一性与 patch 落点盯防、能力矩阵、/static 端到端、Web 拆分
发货一致性、safe tar / 三形态 / build_one 端到端假接缝 / --patch-registry
回写）；README / pyproject / roadmap 同步。

## 2.16.0 — 2026-10-08（包接入安装链：不可变 artifact → verify → 事务安装）

**安装链闭环**（plugin-spec v0.2 冻结后的第一步落地，本轮 P0 主题）

之前安装走的是 `Registry → GitHub repo → ghpm → 当前 HEAD`，装到的是
活的代码；现在注册表条目可携带不可变产物，安装端只信哈希：

    Registry（packageUrl + packageHash + manifestHash）
      → download_artifact   流式下载，边下边算 sha256，超限即断
      → unpack_zip          zip-slip / 绝对路径 / 链接成员 / zip bomb 全拒绝
      → verify_package      manifest 自哈希 → 逐文件双向一致 → 链接 → 穿越
      → install_package_skills   两阶段事务安装（与本地插件同一条链路）

- **新模块 `workbuddy_market/artifact.py`**：
  - `download_artifact()`：流式分块（内存 O(chunk)）、`.part` 临时文件 +
    `os.replace` 原子落位、落位文件名取哈希前 16 位（不可变命名）、
    `expected_hash` 对不上即拒绝（**供应链校验无放行出口**，不像
    `--allow-non-skill` 有 force）、大小上限在读取路径上数（不信
    Content-Length）；网络接缝只有 `_artifact_open()` 一处；
  - `unpack_zip()`：`..` 段 / 绝对路径 / 盘符成员拒绝（且逐路径过
    `ensure_child`）；Unix mode 类型位非普通文件/目录（符号链接等）拒绝；
    声明值与实际写出量双重计数防 zip bomb；失败清理无半截状态；
  - `prepare_package()`：URL 或本地 zip → 解包 → verify → 与注册表
    固定的 packageHash / manifestHash 比对。哈希语义分层：packageHash
    是包**内容**哈希（manifest 口径，解包后重算比对），不是 zip 文件哈希；
  - `install_from_entry()`：条目没有成套的 packageUrl + packageHash 时
    **诚实报错并提示走 ghpm 路线** —— 绝不静默降级（「看起来走了校验链、
    实际走的是 clone」是最坏情况）。
- **安装循环归一**（`installer.py`）：新增 `install_package_skills()`，
  `install_local_plugin()` 委托它 —— 本地插件目录与 Market Package 走
  同一条两阶段事务链路（暂存 → 校验 → 换位 → 记账），foreign 绝不覆盖。
- **packageHash 全程携带**：`tx_begin()` 顶层、`tx_note_staged()` 条目、
  `record_owner()`（ownership 记录新增可选 `packageHash` 字段，
  OWNERSHIP_SCHEMA 保持 1）、`recover_transactions()` 补记不丢 ——
  「我安装的到底是哪一个不可变产物」全程可审计，为按 artifact 回滚打底。
- **服务端** `POST /api/registry/install {repo, mode?}`：与 remote/add
  同一套 `_RUNNER` 并发闸门与任务表；进度回调直喂任务面板；条目无
  artifact 时任务失败并给出诚实提示。哈希钉死的那一份不存在上游漂移，
  因此无需 remote/add 的 409 漂移闸门。网页确认框按条目能力如实切换
  安装路线与文案（v2.16）。

**信任 fail-closed**（评审供应链细节项）
- `parse_registry()`：trust 缺失 / 值不认识（拼写错误、未来的
  "official-ish"）一律 **external**。旧口径降为 reviewed，等于把
  「来历不明」自动洗成「社区已审核」；现网 28 条全有显式 trust，
  行为不受影响；
- artifact 字段**成套采纳**：packageUrl + packageHash 同时合法才进条目
  （半套比没有更危险），manifestHash / version 可选；平铺与嵌套
  `artifact{}` 两种写法都收。

**性能与 CI**
- `pack_package()` / `verify_package()` 的逐文件哈希从 `read_bytes()`
  整读改为 `sha256_file()` 流式分块（1 GB 的包不再整个进内存，
  与全项目「大文件 fail-safe」原则对齐）；
- `scripts/build_registry.py` **last-known-good**：全部失败 → 不写盘、
  不 bump updatedAt、退出码 1；零成功刷新 → 同样不写盘。旧口径在
  changed==0 且 failed>0 时也会重写 updatedAt，制造一次假更新 + 假 PR
  —— 「CI → registry → PR」从此只反映真实刷新。

**自检**：579 → 625 项（第 31 节 46 项）：假接缝下载矩阵（哈希不符 /
超限 / .part 清理 / URL 协议）、zip 攻击面（四类 zip-slip / 链接成员 /
zip bomb / 清理）、prepare 端到端（URL 全链 / manifestHash 不符 /
篡改拒绝）、install_from_entry 全链（无 artifact 诚实报错 / 装入 /
ownership 带 packageHash / 重复 skipped / foreign 不覆盖）、事务
packageHash（tx_begin 顶层 / staged 条目 / 崩溃恢复补记）、
build_registry last-known-good 三态、registry 解析 fail-closed。

## 2.15.0 — 2026-10-08（Market Package 协议冻结 + pack / verify 实现）

**协议冻结**（`docs/plugin-spec.md` v0.1 → v0.2，六项开放问题全部定稿）
1. 产物来源 = **不可变 artifact（CI 构建）**；从源 repo 原地取 commit
   只作过渡兼容；
2. 规范化 JSON = **UTF-8（无 BOM）+ 键按码位排序 + 紧凑分隔符 +
   ensure_ascii=False + 末尾无换行**（`packaging.canonical_json`）；
3. 签名 = v0.1 不做，`integrity.signature` 预留字段位；
4. 平台不匹配 = **默认拒绝，force=True 放行并记 warning**
   （与 `--allow-non-skill` 同一口径）；
5. ghpm 兼容 = 无 manifest 走现有路径，如实标注「无完整性清单」；
6. 依赖 = **声明不解析**，verify 只校验声明形状。

**pack / verify 纯函数层**（新模块 `workbuddy_market/packaging.py`，
P0-2 落地第一步；安装链路接入是下一步）
- `pack_package()`：本地插件目录 → 带 manifest 的 Market Package。
  源含重解析点拒绝；skill 目录必须有 SKILL.md；id / version 复用
  配置层 `validate_id` / `validate_version`；逐文件 sha256 +
  manifest 自哈希（canonical_json）+ 整包 `packageHash`（对
  「相对路径 → 文件哈希」映射规范化再哈希）—— **重打包哈希稳定**；
  失败即清理，不留半截包。
- `verify_package()`：不可信输入按攻击面处理，校验序 fail-closed：
  manifest 形状（schemaVersion / 必填 / id / version）→ skills 路径
  （skills/ 前缀 + ensure_child 越界闸）→ manifest 自哈希 → 逐文件
  哈希 + **双向一致**（磁盘上多出任何未列出文件也算失败）→ 链接
  防线（包内任何重解析点即失败）→ SKILL.md 存在性 → 平台
  （force 口径）→ 依赖声明形状。坏 JSON / 缺文件返回 errors 不抛。
- `content_hash()`：整包内容哈希（P1 packageHash 全量固定的地基）。

**自检**：560 → 579 项（第 30 节 19 项：规范化键序无关与中文原样、
重打包哈希稳定、攻击面八连（改文件 / 塞文件 / 删文件 / 改清单 /
穿越 / 坏 id / 坏依赖形状 / 坏 JSON）、链接拒绝、平台默认拒绝 +
force 放行）。另修 round5 零网络漏洞：`/api/remote/add` 用例的漂移
闸门原先会真发 registry 请求（代理抽风时拖垮整个自检），改为空
注册表假接缝（27H 已有该闸门的专用端到端，无覆盖损失）。

## 2.14.0 — 2026-10-08（R5：installer / uninstaller 迁包 + manifest 协议讨论稿）

**R5 模块化**（逐字搬迁，行为零变化；core 1755 → 1379 行）
- `classify_skill` / `inspect_skill` / `plugin_uninstall_plan` /
  `uninstall_local_plugin` / `dropped` 迁 `workbuddy_market/uninstaller.py`；
- `_stage_dir` / `_sweep_staging` / `_stage_skill` / `_commit_staged` /
  `install_local_plugin` / `INSTALL_MODES` 迁
  `workbuddy_market/installer.py`；
- 对 core 注入点（`_scan` / `quick_fingerprint` / `tree_hash` /
  `tree_hash_from_index` / `tx_*` / `recover_transactions` /
  `_sync_packaging` / `record_owner` / `_sync` 组合层）一律**调用点
  晚绑定 `import market_core`** —— 与 R4 同一纪律，patch `core.X`
  对安装/卸载链路的拦截语义与迁移前完全一致；
- patch 落点随迁：`classify_skill` 等包内互调 → `wm.uninstaller`、
  安装内部符号 → `wm.installer`；`quick_fingerprint` / `tree_hash*` /
  `build_state` 仍留 core（_scan 注入点纪律不变）；
- 24B 盯防清单扩展 8 项（installer / uninstaller 符号的模块归属）。
- 契约回归要点：20B「tx_begin 失败 → OSError 硬失败、磁盘零改动」、
  第 21/22 节崩溃矩阵（`core._scan` / `tree_hash` /
  `quick_fingerprint` / `tx_note_committed` / `record_owner` 注入）
  全部经真实流水线验证通过。

**manifest 协议讨论稿**（v3-roadmap P0-2，只定稿讨论、不含实现）
- 新增 `docs/plugin-spec.md`：Market Package 第四层抽象
  （WorkBuddy Skill / Plugin / GitHub Repo 之外）——包布局、
  manifest.json schema v0.1、与现有安全模型的衔接
  （trust 与 integrity 正交、source.ref 即 sourceCommit 的包级形态、
  跨卷结构校验可升级为逐文件哈希）、installer 视角的生命周期、
  6 项开放问题（immutable artifact 来源、规范化 JSON、签名、
  平台策略、ghpm 过渡、依赖解析时机）。

**自检**：545 → 560 项（第 29 节 9 项 + 24B 扩展 8 项 − 2 项随迁合并：
installer/uninstaller re-export 同一性、`core.quick_fingerprint` /
`core.tx_begin` 注入拦到包内编排的晚绑定端到端、迁移后安装/卸载
全流程回归；`core._stage_skill` / `_commit_staged` 的归属断言随迁
至「已迁包」清单）。

## 2.13.0 — 2026-10-08（跨卷原子化 + API v1 + doctor + v3.0 路线定稿）

**跨卷回收站搬移原子化**（评审 P0：数据安全）
- `move_to_trash()` 显式分两条路：同卷 `os.rename()`（原子，与原行为
  等价）；跨卷走「staging 复制（`.trash` 内 `<名>.partial`）→ 结构校验
  （相对路径集合 + 每文件大小）→ 同卷原子 rename 落位 → **最后才删源**」。
  原来 `shutil.move()` 跨卷退化成 copy+delete，中途崩掉两边都不完整。
- 任何一步失败：清掉 `.partial`、源目录原样保留、返回 None ——
  调用方（如 `_commit_staged`）可以放心中止，不会出现半截状态。
- 重解析点条目（symlink / junction）拒绝跨卷搬移：copytree 无法保真
  复制 junction，宁可失败（同卷 rename 不受影响）。
- `_same_volume()`：Windows 按 splitdrive 盘符、POSIX 按 st_dev；
  stat 失败**保守按跨卷处理**（宁走慢的校验搬移，不赌假原子）。
- 校验口径刻意不比内容哈希（回收站允许 2GB，代价不成比例）——
  安全语义仍由 `needs_exact` 的 tree_hash 负责，与完整性校验分层。

**API 版本化**
- 全部接口接受 `/api/v1/<路由>` 别名（`_normalize_api_path`），
  含 `/api/v1/job/<id>[/cancel]` 带参数路由；归一化在**鉴权 / Origin
  校验之前**——版本前缀不提供任何绕过闸门的途径。
- 裸 `/api/*` 即 v1 语义，前端与旧脚本零迁移；今后破坏性变化走
  `/api/v2`（`API_VERSION = 1`）。

**doctor（新模块 `workbuddy_market/doctor.py`）**
- `workbuddy-market doctor` / `python -m workbuddy_market doctor`：
  Python 版本 / 市场根 / 配置 / WorkBuddy 家目录 / skills / 打包索引 /
  ghpm / 所有权 / 事务日志 / 回收站（含索引越界条目安全检查）/
  注册表缓存 / STATE_HOME 逐项体检，每项独立捕获异常，坏了标 ✗
  并给下一步动作，绝不让一项故障拖垮整份报告。
- `--fix` 只做 `recover_transactions()`（与 `launcher --recover` 同一
  入口，不新增第二种恢复语义）。
- doctor 是唯一**不依赖 clone 布局**的子命令：cli 在 clone 内先把
  仓库根写进 `WBM_MARKET_ROOT` 再导入包（必须在首次导入 paths 前），
  pipx 安装后在 clone 目录里运行也能体检正确的市场；clone 外运行时
  「市场根」一项如实标 ✗。

**POSIX 支持口径诚实化**
- pyproject/README 明确：Linux/macOS 目前是「CI 语法级验证」
  （py_compile + 隐私审计），完整 selftest 硬门槛暂只在 Windows；
  不让开源用户误以为 README 声称的 POSIX 支持已被完整测试。

**v3.0 路线定稿**
- 外部评审的 16 项建议整理成带优先级的路线文档 `docs/v3-roadmap.md`
  （Marketplace Package / manifest 协议、Provider 抽象、installer /
  uninstaller 拆分、pytest 拆分、依赖系统、Quality Score 等）——
  本轮只定稿路线，不动协议实现。

**自检**：523 → 545 项（第 28 节 22 项：跨卷搬移端到端 / 校验失败源
不动 / 重解析点拒绝 / API v1 归一化语义与端到端等价 / doctor 结构、
渲染与 cli 分发；跨卷路径用 `wm.trash._same_volume` 假接缝强制触发，
磁盘动作真实）。

## 2.12.0 — 2026-10-08（供应链信任 + R4 模块化收尾 + CI 加固）

**三级信任模型**
- 注册表条目新增 `trust` 字段：`official`（官方收录）/ `reviewed`
  （社区精选，人工审核）/ `external`（未审核）。`parse_registry`
  白名单放行，值不认识降为 `reviewed`；当前 28 条 = 1 官方 + 27 已审核。
- 网页卡片徽标：✓ 官方 / ✓ 已审核 / ! 未审核——GitHub 全网搜索结果
  一律标「! 未审核」，搜索到 ≠ 官方认可；安装确认框同步标注来源等级。

**供应链固定来源**
- 注册表新增 `sourceCommit`（审核时固定的 commit，28/28 已补齐）、
  `license`（26/28，其余如实留空）、`review{status,reviewedAt,method}`
  字段（可选增量，schema 保持 1——向前向后兼容，不破坏既有消费者）。
- 安装闸门：`POST /api/remote/add` 对收录仓库比对 `sourceCommit` 与
  CI 刷出的 `latestSha`，上游已前移 → **409 拦下**并带凭证；前端把
  差异摆给用户，`force=true` 显式放行（装的是当前版本、非审核版本，
  这个事实先说清楚）。注册表不可用时跳过校验、不锁死安装。
- `build_registry.py` 对漂移条目输出「建议重新审核」预警（静态字段
  仍只许人工改）。
- 收紧 `--allow-non-skill`：默认**不带**，安装链路默认只接受符合
  Skill 协议的仓库；兼容模式必须在确认框显式勾选，且记 warn 日志。
- 注册表描述去营销化（"250,000+ researchers" 之类未经验证的数字清出，
  registry 是 metadata 不是广告页）。

**CI / 供应链加固**
- `.github/workflows/*.yml`：第三方 action（checkout / setup-python）
  全部 pin 到完整 SHA（升级换 SHA 并同步注释版本号）。
- `registry.yml` 每日刷新**不再直推 main**：生成 → 分支 → PR → CI →
  人工合并（`permissions` 增 `pull-requests: write`）。

**R4 模块化收尾**（逐字搬迁，行为零变化）
- trash / ownership / transactions 迁入 `src/workbuddy_market/`
  （`market_core.py` 2445 → 1755 行；`_measure` 等对 `core._scan` /
  `tree_hash` / `quick_fingerprint` / `say` / `_sweep_staging` 的依赖
  改为调用点晚绑定 `import market_core`——这些注入点的 patch 语义与
  v2.11 前完全一致）。
- selftest patch 落点随迁：`save_ownership` → `wm.ownership`、
  `_save_trash_index` → `wm.trash`；第 24 节新增迁包符号的 module 归属
  与 re-export 同一性盯防。

**产品化**
- 新增 `pyproject.toml`（版本动态读 `version.py`，不出现第二个常量）+
  `workbuddy-market` console script + `python -m workbuddy_market`
  （`cli.py` 向上定位 clone 根后委托 `launcher.main()`，行为与
  `python launcher.py` 一致；不在 clone 内则明确报错）。
- README 瘦身：1256 → 429 行；v2 → v2.11 各轮详解迁 `docs/versions.md`，
  历史摘要收敛为一张表；注册表口径更新（trust / sourceCommit）。

**自检**：509 → 523 项（R4 同一性/归属盯防 + 第 27H 节漂移闸门端到端
7 项：409 凭证、force 放行、未漂移放行、缺 latestSha 不误拦、兼容模式
显式传参、注册表不可用不锁死）。Windows 隔离模式全绿。

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
- 2026-10-07 晚补记（数据轮，不升版本）：注册表扩至 28 条——新增 18 条
  （ECC、andrej-karpathy-skills、ponytail、archify、i-have-adhd、humanizer、
  marketingskills、academic-research-skills、diagram-design、reverse-skill、
  Anthropic-Cybersecurity-Skills、book-to-skill、hallmark、planning-with-files、
  pm-skills、baoyu-skills、distilly、huashu-design，逐仓核实根目录
  SKILL.md / skills/ 结构）；K-Dense 仓库改名同步为 scientific-agent-skills；
  前端 ICON 表新增效率 / 商业 / 安全三类。
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
