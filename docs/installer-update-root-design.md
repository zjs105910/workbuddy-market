# install.cmd `--update-root` 设计方案（草案 v1，评审用）

> 状态：**待评审，未实施**。本文只定方案，不含代码改动。
> 目标：补齐「重复运行 install.cmd 只升级 CLI、本体静默落后」的缺口，
> 同时不破坏首装路径，不违反事务 / 所有权 / fail-closed / SHA-256 校验的既有原则。

---

## 0. 方案总览

- **核心逻辑放 Python，不放 cmd**：新增 `src/workbuddy_market/rootupdate.py`，
  install.cmd 只做参数分发与输出。理由：目录替换回滚、版本比对、故障注入
  在批处理里不可靠也不可测；Python 模块可直接进 pytest / selftest 体系。
- **复用现有件**：
  - 版本获取：`selfupdate.py` 的 release 查询 + `parse_tag` / `compare_versions`
    （网络接缝保持一处、可整体替换的模式不变）；
  - 原子写：`fsutil.atomic_write_*`；
  - 体检：`doctor.run_doctor`；
  - 隔离：selftest 三变量（`WBM_MARKET_ROOT` / `WBM_STATE_HOME` / `WBM_HOME`）。
- **三个设计依据（来自代码核实，不是猜的）**：
  1. v2.7 起运行状态在 `~/.workbuddy-market/markets/<bucket>/`（bucket =
     MARKET_ROOT 绝对路径的 sha256 前 12 位，见 `paths.py`）。**只要原地
     替换、绝对路径不变，ownership / tx / trash / backups / locks / logs
     天然存活，完全不参与替换**。这是本方案敢做目录替换的根基。
  2. `launcher.py` 把自身目录插进 sys.path —— 从 `%DEST%` 运行时
     `MARKET_ROOT` 自动解析为 `%DEST%`。
  3. pipx CLI 跑 doctor 时「市场根 ✗」是预期（`paths.py` fallback 指向
     site-packages 一侧）—— **升级后体检必须显式指定根**（`WBM_MARKET_ROOT=%DEST%`
     或从新根跑 launcher），否则体检结果没有意义。

---

## 1. install.cmd 行为矩阵（默认行为不破坏）

| 调用 | CLI | 市场本体 | 说明 |
|---|---|---|---|
| `install.cmd`（无参数，已装） | pipx install/upgrade | **不动**，只报告 | 输出三段状态（见下） |
| `install.cmd`（无参数，未装） | pipx install | main.zip 首装 | 现状不变 |
| `install.cmd --update-root` | 不动（或顺带 upgrade） | 走 §3 升级流程 | 显式用户动作 |
| `install.cmd --no-launch` | 同上 | 同上 | 保留 |

**默认模式的三段状态输出（重复运行时）**：

```
[3/5] CLI: 已安装 2.35.1 → 已升级到 2.36.0
      本体: 当前 2.36.0（%DEST%\src\workbuddy_market\version.py）
      本体更新: 检测到最新 Release v2.37.0 —— 运行 install.cmd --update-root 升级
      本次实际更新: 仅 CLI
```

- 本体版本读 `%DEST%\src\workbuddy_market\version.py`；读不到 / 解析失败
  **如实显示 `未知`，绝不推断为最新**。
- 「检测到最新 Release」查询失败（断网）→ 该行显示 `检查失败（网络）`，
  不影响 CLI 升级继续。
- 结尾文案从「Re-run this file anytime to update the CLI」改为明确
  「update the CLI only; run with --update-root to update the market root」。

---

## 2. 受保护路径清单（显式允许清单制，不用 .gitignore 推断）

原则：**保什么靠白名单逐项列出**，其余一切以新版为准，不做合并拷贝。
「保」的含义：从旧根复制进新根（升级时），原副本在 `.old-<ts>` 备份里
保留到 doctor 通过后才删 —— 任何时刻都存在两份。

| # | 路径 | 性质 | 备注 |
|---|---|---|---|
| 1 | `market.config.json` | 个人配置 | 含个人 skill 组合 |
| 2 | `plugins/` | **个人数据（核心）** | 已安装技能本体，整目录保留 |
| 3 | `.codebuddy-plugin/marketplace.json` | 可能是本地市场清单 | 用户跑过 `--sync` 后指向本机市场；覆盖会让 plugins/ 失联。保留用户版，doctor 如实提示 |
| 4 | `.env` | 本机环境 | 密钥类，永不覆盖 |
| 5 | `.workbuddy/` | 本机工作区 | gitignored 但不是缓存 |
| 6 | 旧布局遗留根内状态：`.market-state.json` / `.market-log.ndjson*` / `.ownership.json` / `.market-tx/` / `.backups/` / `.trash/` / `.market.lock` / `.market-log.lock` / `.workbuddy-market/` | v2.7 前布局 / harness 环境 | **仅存在时才处理**；搬进新根并如实提示（恢复能力不能丢，doctor --fix 是恢复出口） |

> v2.7+ 正常安装的根目录里 #6 不存在（状态在 STATE_HOME），清单照查不误报。

---

## 3. `--update-root` 流程（每步 fail-closed）

```
Step 0  前置检查
Step 1  获取目标版本（正式 Release tag）
Step 2  下载 zip → 同卷临时目录
Step 3  校验（不通过即清理临时目录，旧根全程未动）
Step 4  运行中预检
Step 5  搬迁保护路径（§2 白名单）
Step 6  原地替换（三段 rename + 回滚，§4）
Step 7  升级后体检（通过前备份绝不删）
Step 8  清理（doctor 通过后才删备份）
```

**Step 0 前置检查**
- `%DEST%\launcher.py` 不存在 → 转首装流程（main.zip），并明说走的是首装。
- 读旧版本：解析失败 → 显示 `未知`，继续（用户显式要求升级），但全程打警示。
- **Git 克隆检测**：存在 `.git/` → **一律拒绝自动升级**，打印建议命令
  （`git pull`）后退出。理由：工作区状态无法可靠区分「用户本地修改」，
  宁可拒绝不覆盖（与评审意见一致）。
- 磁盘空间：旧根体积 + 新 zip 解压体积 × 1.2 > 剩余空间 → 拒绝。

**Step 1 目标版本**：复用 selfupdate 的 release 查询取 `latestTag`；
`--update-root vX.Y.Z` 可显式指定（含降级重装）。网络失败 → 人话报错终止。

**Step 2 下载**：沿 install.cmd 双通道策略（`api.github.com` zipball 优先、
`github.com/archive/refs/tags/<tag>.zip` 兜底），存到 **`%DEST%` 父目录下
的 `.wbm-update-<ts>/`**（不用 `%TEMP%` —— 必须与 `%DEST%` 同卷，rename 才有效）。

**Step 3 校验**（任一失败 → 删临时目录，退出，旧根未动）：
1. zip CRC 完整性（Python zipfile 逐件校验）；
2. 解压（处理 zipball 顶层目录）；
3. 解压后 `src/workbuddy_market/version.py` 的 `MARKET_VERSION` **必须等于**
   tag 版本（复用 `selfupdate.parse_tag`）；
4. 必备文件清单存在：`launcher.py` / `market_core.py` / `install.cmd` /
   `web/index.html` / `src/workbuddy_market/{application,installer,doctor,paths}.py` /
   `bundled/` 非空 / `registry/plugins.json`。

> 说明：GitHub tag 源码 zip 没有已发布的哈希清单（SHA256SUMS.txt 只盖
> Release 附件），所以校验口径 = tag 名 + MARKET_VERSION + 必备文件清单 +
> zip CRC。tag 由 GitHub 保证不可变，此口径在本项目威胁模型下够用；
> 若后续上 Artifact Attestations，可在 Step 3 追加来源证明核对。

**Step 4 运行中预检**（人话预警，不是唯一防线）：
- 探测 8777–8791 端口监听（`market_server.DEFAULT_PORT` 起步）→ 有监听 →
  提示「市场界面可能开着，请关闭后重试」，默认拒绝，`--force` 跳过。
- 真正的占用防线是 Step 6 的 rename 本身（Windows 对含打开句柄的目录
  rename 必失败）—— 预检只为给出人话，不假装是保证。

**Step 5 搬迁保护路径**：§2 白名单逐项从旧根复制到新根临时目录，逐行打印
`保留: market.config.json` / `保留: plugins/ (23 项)`；冲突以用户数据为准。

**Step 6 原地替换**（Windows 目录替换不是原子事务，三段式设计）：

```
① rename %DEST%            →  %DEST%.old-<ts>     （备份侧让位）
② rename .wbm-update-<ts>/新根 →  %DEST%            （新根上位）
```

- ①② 均为同卷目录级 rename，O(1) 且不占额外空间；
- **①失败**（占用/权限，最常见）→ 中止退出，旧根原位未动，打印
  「文件被占用 —— 请关闭市场与相关终端后重试」；
- **②失败** → 新根仍持临时名、`%DEST%` 空缺 → 立即执行回滚
  `rename %DEST%.old-<ts> → %DEST%`（重试 3 次指数退避）；
- **回滚也失败**（病态：备份目录句柄刚被打开）→ **exit 2**，原样打印
  两个目录的绝对路径和两条手工 rename 命令，明确「需要人工恢复」，
  绝不静默、绝不假装成功；
- 任一时刻不存在「两边都不是 %DEST%」的无提示终态。
- 成功后把升级元数据（旧/新版本、备份路径、时间戳）写入 STATE_HOME
  （`atomic_write`），供 doctor 展示与后续清理。

**Step 7 升级后体检**（通过前 `.old-<ts>` 绝不删）：
- 从**新根**运行：`python launcher.py doctor --no-wizard`（sys.path 落新根，
  MARKET_ROOT 正确），并叠加显式 `WBM_MARKET_ROOT=%DEST%` 双保险；
- 退出码与「报告必须含 ✓」沿用 release-smoke 的口径（市场根缺配置等
  ✗ 项按 doctor 语义放行，其余非 0/1 退出码 = 失败）；
- 打印升级前后版本号对照；
- 失败 → 按回滚分支处理（§4）。

**Step 8 清理**：doctor 通过 → 删 `.old-<ts>` 与临时目录，打印
「升级完成：2.35.1 → 2.36.0」；失败 → 保留备份并告知绝对路径。

---

## 4. 回滚策略（失败分支逐条定死）

| 失败点 | 动作 | 终态 |
|---|---|---|
| Step 1/2 网络失败 | 报错退出 | 旧根原样可用 |
| Step 3 校验失败 | 删临时目录退出 | 旧根原样可用 |
| Step 6-① rename 失败 | 报错退出 | 旧根原样可用（rename 即探测） |
| Step 6-② rename 失败 | 自动回滚（重试 3 次） | 旧根回到 %DEST% |
| 回滚 rename 也失败 | **exit 2 + 人工恢复指引**（路径 + 命令原文） | 显式报告，不静默 |
| Step 7 doctor 失败 | 反向 rename 回滚（新→临时，旧→%DEST%） | 旧版回来，临时新根保留供排查 |
| 回滚反向 rename 失败 | exit 2 + 人工指引 | 显式报告 |
| 磁盘不足 | Step 0 预检拦截 | ——（目录 rename 本身不占空间，解压在替换前完成，天然规避中途 ENOSPC） |

原则：`%DEST%` 在 doctor 通过前**始终**有一份完整旧版副本；所有不确定
分支以显式退出码 + 人话 + 可执行的人工恢复命令收场。

---

## 5. 失败注入测试（进 pytest + selftest 新 round）

核心思想：**安全逻辑全部压在 Python 层可测面**，cmd 层只测分发与文案
（cmd 不做自动化故障注入，边界如实声明）。

网络接缝整体替换（同 selfupdate 模式），三变量隔离 + 指向假更新源：

1. release 查询失败 / 返回坏 tag → 如实报错，旧根未动；
2. zip 内 `MARKET_VERSION` ≠ tag → 拒绝替换；
3. 必备文件缺失 → 拒绝替换；
4. 保护路径搬迁：`plugins/` 自定义技能逐字节保留、`market.config.json`
   保留、遗留 dot 状态文件搬进新根；
5. rename-① 失败注入（持旧根文件句柄）→ 中止且旧根可用；
6. rename-② 失败注入（monkeypatch 第二次 `os.rename` 抛错）→ 自动回滚成功；
7. 回滚也失败注入 → exit 2 + 人工指引输出；
8. doctor 失败注入 → 回滚，旧版回来；
9. `.git` 存在 → 拒绝（含干净工作区）；
10. 端口被占 → 默认拒绝，`--force` 放行。

cmd 层（脚本断言 + 手工冒烟）：`--help` 文案、默认模式三段状态输出、
「本体版本未知」场景如实显示未知、无参数路径与现首装逐字节等价行为。

---

## 6. 验收标准（映射测试用例编号）

| 场景 | 必须满足 | 用例 |
|---|---|---|
| 首次安装 | 原流程不变 | cmd 层冒烟 |
| 重复运行默认模式 | 只升 CLI，三段状态如实，未知就写未知 | cmd 层 + 文案断言 |
| `--update-root` | 下载+校验正式版后才替换 | 2/3 |
| 保留配置与个人技能 | 内容不变，所有权/事务状态不丢（STATE_HOME 分桶路径不变） | 4 |
| 下载失败 / 版本不符 | 原目录可用 | 1/2/3 |
| 替换中途失败 | 回滚成功或 exit 2 人工指引 | 5/6/7 |
| 升级完成 | doctor 通过 + 显示新版本号 | 8 + Step 7 |
| 市场开着 / git 本地修改 | 不静默覆盖 | 9/10 |

---

## 7. 明确不做的事

- 不做自动/定时升级（升级永远是显式用户动作）；
- 不动 main.zip 首装路径与 `--no-launch`；
- 不做合并式升级（除 §2 白名单外一律以新版为准）；
- 不引入构建、不改前端、不动 git 历史。

## 8. 待用户拍板的三个开放点

1. **端口预检的严格度**：建议默认拒绝 + `--force` 放行（而非仅提示）。
2. **git clone 一律拒绝**（建议）还是干净工作区放行？
3. **备份保留策略**：建议 doctor 通过即删（省空间）；备选保留最近 1 份
   （`.old-*` 常驻一份）。
