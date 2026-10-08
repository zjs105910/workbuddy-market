# -*- coding: utf-8 -*-
"""market_core —— WorkBuddy 本机插件市场的内核（v2.18）。

版本号只有一个来源：MARKET_VERSION。每一轮代码评审对应一个次版本号：
v1（初版）→ v2（第一轮）→ v2.1（第二轮）→ v2.2（第三轮）→ v2.3（第四轮）
→ v2.4（第五轮）→ v2.5（第六轮）→ v2.6（第七轮）→ v2.7（开源重构 R1）
→ v2.8（R2）→ v2.9（R3）→ v2.10（GitHub 动态目录）→ v2.11（社区注册表）
→ v2.12（R4）→ v2.13（跨卷原子化 + API v1 + doctor）
→ v2.14（R5：installer / uninstaller 迁包）
→ v2.15（Market Package 协议冻结 + pack/verify）
→ v2.16（包接入安装链：artifact 下载/解包/verify → 两阶段事务安装，
  packageHash 进 ownership 与事务日志，trust fail-closed）
→ v2.17（WorkBuddy Adapter + register 迁出（R6 半程）+ CI 产物源 +
  Web 拆文件 + pytest 试点 + wheel/POSIX CI）
→ v2.18（artifact 版本回退 0.0.0 → 日期.短SHA + FAQ 自检数漂移修复 +
  隐私历史审计 CI + macOS 语义冒烟槽位，当前）。

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

v2.12 → v2.13 的变化（P0 工程边界：跨卷原子化 / API 版本化 / doctor）：

  · **跨卷回收站搬移原子化（trash.py）**：WBM_HOME 与 WBM_STATE_HOME
    允许在不同磁盘，原来的 shutil.move() 跨卷退化成 copy+delete ——
    中途崩掉两边都不完整。现在同卷走 os.rename（原子）；
    跨卷走「staging 复制（.trash 内 .partial）→ 结构校验（相对路径
    集合 + 每文件大小）→ 同卷原子 rename 落位 → 最后才删源」，
    任何一步失败源目录原样保留。重解析点条目拒绝跨卷搬移
    （copytree 无法保真复制 junction）。_same_volume()：Windows 按
    盘符、POSIX 按 st_dev，stat 失败保守按跨卷处理。
  · **API 版本化（market_server.py）**：全部接口接受 /api/v1/<路由>
    别名（_normalize_api_path 在鉴权/Origin 校验之前归一化，版本前缀
    不提供绕过闸门的途径）；裸 /api/* 即 v1 语义，前端与旧脚本零迁移。
  · **doctor（workbuddy_market/doctor.py 新模块）**：Python 版本 /
    市场根 / 配置 / skills / ghpm / 所有权 / 事务日志 / 回收站（含
    索引安全）/ 注册表缓存 逐项体检，每项独立捕获异常；--fix 只做
    recover_transactions()（与 launcher --recover 同一入口）。
    doctor 是唯一不依赖 clone 布局的子命令：cli 在 clone 内先把仓库根
    写进 WBM_MARKET_ROOT 再导入包，pipx 安装后也能体检正确的市场。
  · **POSIX 支持口径诚实化**：pyproject/README 明确 Linux/macOS 目前
    是「CI 语法级验证」，selftest 硬门槛仍只在 Windows 跑；
    v3.0 的完整路线（manifest 协议 / Provider 抽象 / 拆分计划）见
    docs/v3-roadmap.md。

v2.13 → v2.14 的变化（R5：installer / uninstaller 迁包，逐字搬迁、行为零变化）：

  · classify_skill / inspect_skill / plugin_uninstall_plan /
    uninstall_local_plugin / dropped 迁 ``workbuddy_market.uninstaller``；
    _stage_dir / _sweep_staging / _stage_skill / _commit_staged /
    install_local_plugin / INSTALL_MODES 迁
    ``workbuddy_market.installer``（core 1755 → 1379 行）；
  · 对 core 注入点（_scan / quick_fingerprint / tree_hash /
    tree_hash_from_index / tx_* / recover_transactions /
    _sync_packaging / record_owner / classify_skill / _stage_skill /
    _commit_staged）一律**调用点晚绑定 ``import market_core``** ——
    selftest 崩溃矩阵（core._scan / tree_hash / quick_fingerprint /
    tx_begin / tx_note_committed / record_owner）与 20B 的
    「tx_begin 失败 → OSError 硬失败、磁盘零改动」契约原样保持；
  · patch 落点随迁：classify_skill 等包内互调 → wm.uninstaller，
    安装内部符号 → wm.installer（24B 盯防清单已扩展 8 项）；
    quick_fingerprint / tree_hash* / build_state 仍留 core（纪律不变）；
  · manifest 协议讨论稿见 docs/plugin-spec.md（v3.0 P0-2 的设计起点，
    本轮只定稿 schema 讨论，不做实现）。
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
    ConfigError, FileLockTimeout, ScanError, ArtifactError,
)
from workbuddy_market.fsutil import (         # noqa: E402,F401
    _fsync_dir, atomic_write_bytes, atomic_write_text, write_text_if_changed,
    read_json,
)
from workbuddy_market.hasher import (         # noqa: E402,F401
    fingerprint_from_index, sha256_file, _same_content, normalize_sha256,
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

from workbuddy_market.trash import (         # noqa: E402,F401  （v2.12 R4 新增）
    TRASH_INDEX_PATH, _TRASH_NAME_BAD, _load_trash_index, _save_trash_index,
    _trash_entry, _measure, TrashIndex, move_to_trash, trash_config,
    trash_stats, _safe_mtime, prune_trash,
)
from workbuddy_market.ownership import (     # noqa: E402,F401  （v2.12 R4 新增）
    load_ownership, save_ownership, record_owner, _market_id, forget_owner,
)
from workbuddy_market.transactions import (  # noqa: E402,F401  （v2.12 R4 新增）
    _TX_ACTIVE, tx_path, tx_save, tx_begin, tx_note_staged, tx_note_committed,
    tx_note_removed, tx_drop, tx_settled, tx_release, tx_close, tx_list,
    recover_transactions,
)
from workbuddy_market.installer import (     # noqa: E402,F401  （v2.14 R5 新增）
    INSTALL_MODES, _stage_dir, _sweep_staging, _stage_skill, _commit_staged,
    install_local_plugin, install_package_skills,
)
from workbuddy_market.artifact import (      # noqa: E402,F401  （v2.16 新增）
    MAX_ARTIFACT_BYTES, ARTIFACT_TIMEOUT, _artifact_open,
    download_artifact, unpack_zip, prepare_package, install_from_entry,
)
from workbuddy_market.adapters.workbuddy import (   # noqa: E402,F401  （v2.17 新增）
    WORKBUDDY_ADAPTER_VERSION, read_known, _read_known, read_known_or_die,
    _read_known_or_die, backup_known, _prune_backups, is_registered,
    entry_for, _entry_for, commit_known, _commit_known,
    register, unregister, capabilities, known_health,
)
from workbuddy_market.uninstaller import (   # noqa: E402,F401  （v2.14 R5 新增）
    classify_skill, inspect_skill, plugin_uninstall_plan, uninstall_local_plugin,
    dropped,
)

# CLASSIFY_PURPOSES / EXACT_PURPOSES 已迁 workbuddy_market.config（v2.9 R3），
# 此处 re-export（见上方 import 块）。INSTALL_MODES 已迁 installer（v2.14 R5）。
# artifact 编排层（v2.16）经 core 命名空间调 install_package_skills ——
# 注入点晚绑定纪律要求 re-export 在先。WorkBuddy 宿主格式（v2.17）已整体
# 迁 adapters/workbuddy.py，patch 注册链路的读请落点该模块。


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


# 回收站已迁 workbuddy_market.trash（v2.12 R4），此处 re-export。
# `.trash/.index.json` 按不可信状态文件处理、rename 成功即事实、诚实统计等
# 纪律见 trash.py；core._scan / say 的晚绑定接缝也记录在那里。


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


# ---------------------------------------------------------------- 所有权 / 事务日志
# 已迁 workbuddy_market.ownership / workbuddy_market.transactions（v2.12 R4），
# 此处 re-export。core.tree_hash / core.quick_fingerprint / core._scan /
# core._sweep_staging / say 的晚绑定接缝（selftest 注入点语义保持不变）
# 见相关模块的 docstring。

# classify_skill / plugin_uninstall_plan / inspect_skill 已迁
# workbuddy_market.uninstaller（v2.14 R5），此处 re-export（见上方 import 块）。
# 它们对 core 注入点（quick_fingerprint / tree_hash / tx_*）的调用在包内
# 走调用点晚绑定 —— patch core.X 依旧能拦到分类与卸载链路。


# ---------------------------------------------------------------- 注册
# v2.17 起整段迁入 workbuddy_market.adapters.workbuddy（WorkBuddy Adapter，
# R6 半程）：known_marketplaces.json 的全部读写、备份、条目构造、
# 乐观合并、register / unregister 都只经 adapter 触碰宿主。此处 re-export
# 保持旧名字可用；**patch 语义随迁** —— 要拦截注册链路里的读，patch
# ``workbuddy_market.adapters.workbuddy.read_known_or_die``（与 R4 把
# ownership / trash 的 patch 落点迁进包内同一先例）。


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
# 已迁 workbuddy_market.installer / workbuddy_market.uninstaller
# （v2.14 R5），此处 re-export（见上方 import 块）。
#
# 注入点语义（selftest 逐项盯防，见两模块 docstring）：
#   · 仍定义在 core：quick_fingerprint / tree_hash / tree_hash_from_index
#     （_scan 注入点纪律，只搬不改）；
#   · 已迁包、经 core 晚绑定调用：_scan / tx_* / recover_transactions /
#     _sync_packaging / classify_skill / _stage_skill / _commit_staged ——
#     patch core.X 对安装 / 卸载链路的拦截与迁移前一致；
#   · 已迁包、patch 落点随迁：move_to_trash → wm.trash、
#     save_ownership → wm.ownership（R4 起）、classify_skill 等包内互调 →
#     wm.uninstaller（R5 起）。


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

    # --- WorkBuddy 侧（v2.17 起经 adapter 诊断宿主格式）
    _known_err = known_health()
    if _known_err:
        errors.append(_known_err)

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
