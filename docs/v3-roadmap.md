# v3.0 路线图（2026-10-08 定稿）

来源：外部评审对本仓库的一轮全面走查（README / pyproject / 内核 / CI /
注册表 / Web 层），共 16 项建议。本文档把它们整理成带优先级的路线，
并记录**本轮的取舍与理由** —— 定稿不代表立即实现，每轮只做能被
selftest 全绿背书的部分。

总体判断（评审原文）：项目已从「个人本机工具」进入「可维护的开源
Marketplace 框架」阶段；安全基础扎实，下一阶段拉开差距的是**协议、
架构、可复现安装与可扩展性**，而不是继续给 market_core.py 加零散补丁。

---

## P0（v3.0 主线，决定项目天花板）

### 1. market_core.py 彻底降级为兼容层（R5+ 拆分）
现状：R2~R5 已迁出 14 个模块（core 2445 → 1379 行）；
**installer / uninstaller 已迁（v2.14 R5）**，register / state / api
仍留在 core。

目标布局（剩余部分）：

```
src/workbuddy_market/
├── register.py / state.py    # R6 候选
├── application.py            # 组合层
├── providers/{base,github,local,http}.py
└── api/{server,routes,schemas}.py
```

纪律延续 R4/R5：逐字搬迁、注入点调用点晚绑定 `import market_core`、
selftest patch 落点随迁、每轮 selftest 全绿。

### 2. 定义 Marketplace Package 协议（manifest.json）
**v0.2 已冻结全部六项开放问题；pack / verify（v2.15）、安装链路（v2.16）、
CI 产物源（v2.17：`build_artifacts.py` + `artifacts.yml` 每日按
sourceCommit 构建发布 + PR 回写）均已落地**。selftest 第 30/31/32 节
全覆盖攻击面；详见 docs/plugin-spec.md §6/§7。

### 3. 可复现安装（immutable artifact）
**v2.16/v2.17 已全链闭环**：Registry（packageUrl + packageHash）→
CI Release 资产（按审核固定的 sourceCommit 构建，同日重跑哈希不变）→
下载 → sha256 校验（无放行出口）→ install → packageHash 进 ownership
与事务日志。剩余：UI「安装审核版本 / 安装当前版本」双入口
（ghpm 路线仍是当前版本入口）。

### 4. 真正可安装的 CLI
现状：`workbuddy-market` 仍需位于 clone 目录（除 v2.13 的 doctor）；
**v2.17 起 CI 有 package job 把「构建 wheel → 安装 → CLI smoke」挡进
门槛**，PyPI 发布是最后一步。目标：`workbuddy-market
init/serve/sync/install/uninstall/registry/doctor` 在 pipx 安装后独立
可用；Windows 保留一键启动.cmd 作为新手入口。
分层不变：新手 → cmd；高级用户 → CLI；开发者 → `from workbuddy_market import …`。

### 5. Linux/macOS 测试真相化
**v2.17 已走「独立 POSIX 语义冒烟」路线**：`scripts/posix-smoke.py`
（fcntl 锁 / symlink 防线 / ensure_child / zip-slip）进 Ubuntu CI 槽位，
pytest 试点（tests/unit 平台无关用例）也在双平台跑。完整 selftest 的
硬门槛仍仅在 Windows（在补齐平台 skip 语义之前不扩大 POSIX 宣传口径）。

---

## P1（v3.0 内完成）

| 项 | 说明 | 前置 |
|---|---|---|
| selftest 拆 pytest | **试点已落地（v2.17）**：tests/unit 三件平台无关用例进 CI；继续把 selftest 各节按 unit / integration / security / fault 迁移，`python selftest.py` 保留为零依赖用户诊断入口 | R5 拆分 |
| /api/v1 稳定化 | v2.13 已落地别名；后续加 schemas + 契约测试，破坏性变化走 /api/v2 | 已开始 |
| Provider 抽象 | `Provider` Protocol：get_metadata / search / download / resolve_version / verify；先收编 catalog+registry 的 GitHub 路径，再考虑 Gitee / 本地 / HTTP | manifest 协议 |
| WorkBuddy Adapter | ✅ v2.17 落地：adapters/workbuddy.py 收拢宿主格式（known_marketplaces 读写 / 条目 / 备份 / 注册），register 迁出（R6 半程）；能力矩阵就位，版本探测随宿主变化逐步补 | — |
| packageHash 全量固定 | ✅ v2.16 完成：安装产物整包哈希进所有权与事务日志（含崩溃恢复补记），补全可复现安装链 | §3 |
| R6：state/application 迁出 | build_state / deep_check / sync 编排迁包后 market_core 收成兼容 shim（register 已迁 adapter 是第一步）；re-export 保证 `import market_core` 不坏 | adapter 已就位 |

## P2（v3.x / 生态期）

- **插件依赖系统**：skills/system/workbuddy 三类依赖声明、拓扑安装、
  冲突与循环检测 —— 从 plugin manager 升级为 package manager。
- **Quality Score**：来源可信度 / 维护活跃 / license / 文档 / 协议
  符合度加权评分；**必须与 trust 三级分开显示**（95 分 ≠ 官方）。
- **Web 拆文件**：✅ v2.17 完成第一步（index.html 84 行 + app.js +
  style.css，/static 白名单服务，零 npm / 零 bundler / 零 node 不变）；
  后续如需组件化再按 state/api/components 细分。
- **隐私审计加历史保护**：push/PR 扫当前树（已有），release 加
  git history，weekly 全量历史。
- **JSON 配置去注释**：README 里的 JSON 示例不再写 `//` 注释
  （保持纯 JSON，不引入 JSONC 依赖）。

---

## 外部评审 #2：dsh-market 对比（2026-10-08 定稿）

第二轮外部走查拿本仓库与 dsh-market（DeepSeek Harness 宿主内插件市场）
逐项对比，结论：dsh-market 赢在产品成熟度与生态规模，本仓库赢在
本机安全、可恢复、可复现、私有化能力；路线不是把自己变成
「小号 dsh-market」，而是把内核能力包装成「本机优先、安全可验证、
可复现安装」的 Marketplace。评审给的 5 件事映射如下
（v2.20 当轮落地的部分标 ✅）：

| 评审建议 | 取舍与落点 |
|---|---|
| 1. WorkBuddy 原生插件市场 UI（评审的 P0） | **记录理由，暂不做原生面板**：5.7.6 实测宿主面板没有市场 UI 位（见 docs/WorkBuddy-5.7.6-面板实测.md），「市场必须在宿主里面」在这台宿主上走不通；现实路径 = Web UI 产品化（✅ v2.20 详情弹窗 / 风险预览；收藏 / 更新中心 / 截图进 P2） |
| 2. 插件详情 + Screenshot + Compatibility | ✅ v2.20：详情弹窗（来源 / 信任 / 产物对账 / 兼容性声明 / 权限）+ 宿主版本与平台三态检测；screenshots 需要注册表截图字段与「仅 GitHub 图源」的策展规范，进 P2 |
| 3. Trust + Permissions + Security Scan | ✅ v2.20：permissions 声明 + 安装前风险预览 + attestation 对账（trust / sourceCommit v2.12 已有）；第三方 skill 的静态安全扫描是独立工程，进 P2/P3 评估 |
| 4. Registry 独立化 + Artifact 分发 | Artifact 分发 ✅（v2.17 CI 产物源）；独立 registry 仓库（PR 投稿 / review 流 / 评分）进 P3 —— 当前 `registry/` 目录 + 每日 PR 回写已具备同构形态，拆仓是运营动作不是代码动作 |
| 5. Profile / Bundle 一键环境 | 依赖系统（P2）落地后再做：bundle = 一组 skill 的声明式集合 + 拓扑安装，语义上是依赖系统的薄壳；先做「收藏 / 分组」的纯前端形态起步 |

其余记录（一并进 v3.x 候选）：更新中心（后端已有 /api/remote/update，
产品化成「全部更新」入口）、多平台 CI 矩阵真相化（P0-5 延续）、
marketplace.json / plugin.json 独立身份（docs/protocol/manifest-v1.md
设计稿）。节奏不变：每轮只做能被 selftest 全绿背书的部分。

## 已落地的部分

**v2.17**：
- ✅ WorkBuddy Adapter（adapters/workbuddy.py：register 迁出 + 能力矩阵
  + known_health），patch 落点随迁
- ✅ CI 产物源闭环：build_artifacts.py + artifacts.yml（Release 发布 +
  PR 回写 artifact 字段）
- ✅ CI 提档：wheel 构建/安装/CLI smoke job、POSIX 语义冒烟、pytest
  试点（tests/unit 31 项，双平台）
- ✅ Web 拆文件第一步（index 84 行 + app.js/style.css + /static 白名单）

**v2.16**：
- ✅ P0-2 收官：包接入安装链全链闭环（artifact 下载/解包/校验 →
  两阶段事务安装），packageHash 进 ownership + 事务日志
- ✅ 供应链信任收紧：trust 缺失/未知 fail-closed 为 external；
  artifact 字段成套采纳；verify/pack 流式哈希；build_registry
  last-known-good

**v2.15**：
- ✅ P0-2 完成：plugin-spec 六项开放问题全部冻结（v0.2）+
  `packaging.py` 的 pack / verify 纯函数层（攻击面全覆盖）
- ✅ round5 自检零网络漏洞修复（remote/add 假接缝）

**v2.14（R5）**：
- ✅ P0-1 半程：installer / uninstaller 迁包（core 1755 → 1379 行），
  注入点晚绑定语义经全部既有崩溃矩阵回归
- ✅ P0-2 讨论稿：docs/plugin-spec.md v0.1（schema + 开放问题）

**v2.13**：
- ✅ 跨卷回收站搬移原子化（评审 P0 数据安全项，含重解析点拒绝跨卷、
  校验失败源不动；selftest 第 28 节盯防）
- ✅ API /api/v1 版本化别名（鉴权前置归一化）
- ✅ CLI doctor 子命令（pipx 可用、--fix 走同一事务恢复入口）
- ✅ POSIX 支持口径诚实化（pyproject/README 标注实验性）
- ✅ 本路线文档定稿

## 明确不做（记录理由）

- **引入 React/Vue 前端框架**：单文件零构建是这个项目的明确优点。
- **market_core 继续加零散安全补丁**：结构性问题走上面的拆分路线。
- **把 Linux selftest 没跑过就说支持**：宁可口径保守。
