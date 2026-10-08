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
**v0.2 已冻结全部六项开放问题，pack / verify 已实现**
（`workbuddy_market/packaging.py`，selftest 第 30 节全覆盖攻击面；
详见 docs/plugin-spec.md §6/§7）。剩余：registry 安装链路接入
（条目带 packageHash，安装走 verify）。

### 3. 可复现安装（immutable artifact）
现状的 trust 模型解决「上游变了会提醒」，但安装的仍是**当时的
最新版**。目标：reviewed commit → 不可变产物 → sha256 → install，
UI 提供「安装审核版本 / 安装当前版本」双入口。
（本轮 v2.13 的漂移闸门 + sourceCommit 固定是前置。）

### 4. 真正可安装的 CLI
现状：`workbuddy-market` 仍需位于 clone 目录（除 v2.13 的 doctor）。
目标：`workbuddy-market init/serve/sync/install/uninstall/registry/doctor`
在 pipx 安装后独立可用；Windows 保留一键启动.cmd 作为新手入口。
分层不变：新手 → cmd；高级用户 → CLI；开发者 → `from workbuddy_market import …`。

### 5. Linux/macOS 测试真相化
现状：CI 的 Ubuntu 槽位只做 py_compile + 隐私审计，selftest 硬门槛
仅在 Windows（v2.13 已在 pyproject/README 如实标注）。
目标二选一：给 523+ 项用例补平台 skip 语义后把 selftest 纳入 Linux
矩阵；或先做独立的 POSIX 语义冒烟（fcntl 锁 / symlink / 进程组）。
在补齐之前不扩大 POSIX 支持的宣传口径。

---

## P1（v3.0 内完成）

| 项 | 说明 | 前置 |
|---|---|---|
| selftest 拆 pytest | tests/{unit,integration,security,e2e}；`python selftest.py` 保留为零依赖用户诊断入口（这个定位很好，不砍） | R5 拆分 |
| /api/v1 稳定化 | v2.13 已落地别名；后续加 schemas + 契约测试，破坏性变化走 /api/v2 | 已开始 |
| Provider 抽象 | `Provider` Protocol：get_metadata / search / download / resolve_version / verify；先收编 catalog+registry 的 GitHub 路径，再考虑 Gitee / 本地 / HTTP | manifest 协议 |
| WorkBuddy Adapter | 把「读 known_marketplaces / 写 skills 目录」等对 WorkBuddy 内部格式的依赖收进 adapters/workbuddy.py，抵御宿主格式变化 | — |
| packageHash 全量固定 | 安装产物整包哈希进所有权与事务日志，补全可复现安装链 | §3 |

## P2（v3.x / 生态期）

- **插件依赖系统**：skills/system/workbuddy 三类依赖声明、拓扑安装、
  冲突与循环检测 —— 从 plugin manager 升级为 package manager。
- **Quality Score**：来源可信度 / 维护活跃 / license / 文档 / 协议
  符合度加权评分；**必须与 trust 三级分开显示**（95 分 ≠ 官方）。
- **Web 拆文件**：index.html 单文件拆 app.js / api.js / state.js /
  components.js / style.css，保持零 npm / 零 bundler / 零 node。
- **隐私审计加历史保护**：push/PR 扫当前树（已有），release 加
  git history，weekly 全量历史。
- **JSON 配置去注释**：README 里的 JSON 示例不再写 `//` 注释
  （保持纯 JSON，不引入 JSONC 依赖）。

---

## 已落地的部分

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
