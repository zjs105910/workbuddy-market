---
name: github-project-manager
version: 4.0.0
description: "管理从 GitHub 下载到本机的开源项目与技能包：列出、扫描发现、安装前预检、检查更新、一键更新、移除、回滚、数据完整性校验与环境诊断。带 O_EXCL 原子锁 + 心跳租约、事务级失败回滚、InstallPlan 状态收敛、单次遍历的磁盘预检、批量更新复用远程信息（消灭 N+1 请求）、ZIP 预扫描与压缩炸弹/设备名双重防护、skill 冲突阻断、内容指纹校验、硬链接与 rename 两种备份介质。触发方式：/ghpm、『GitHub 项目管理』『检查插件更新』『更新开源项目』『我装了哪些 GitHub 项目』『这个插件有新版吗』『卸载插件』『这个仓库能装吗』『ghpm doctor』『ghpm verify』『文件丢了/装坏了』。"
metadata: {"source":"local","commands":["list","scan","inspect","add","check","update","remove","rollback","verify","doctor","unlock"]}
---

# github-project-manager

管理本机从 GitHub 下载的开源项目，尤其是安装到 `~/.workbuddy/skills/` 的技能包。
解决一个具体问题：**GitHub 上的项目在持续更新，本机副本会过期**，手动重下很麻烦。

## 清单文件

`~/.workbuddy/github-projects.json` 记录所有受管项目（仓库、分支、commit sha、安装位置、内容指纹）。

## 命令

脚本：`~/.workbuddy/skills/github-project-manager/scripts/ghpm.py`

```bash
python .../ghpm.py list [--json]              # 列出已登记项目
python .../ghpm.py scan [--fresh]             # 扫描本机未登记的 GitHub 项目（只登记不重装）
python .../ghpm.py inspect owner/repo [--force] [--fresh]   # 预检（只读）
python .../ghpm.py add owner/repo [--branch main] [--allow-non-skill] [--force]
python .../ghpm.py check [name] [--fresh]     # 比对远程最新 commit
python .../ghpm.py update <name> | --all [--dry-run] [--force] [--fresh]
python .../ghpm.py remove <name>              # 备份后移除
python .../ghpm.py rollback <备份目录>         # 把某次备份恢复到原位
python .../ghpm.py verify [name] [--remote] [--json]  # 清单 ↔ 磁盘 ↔ 远端 一致性校验
python .../ghpm.py doctor [--json] [--no-network]     # 环境与健康诊断
python .../ghpm.py unlock [--force]           # 清写锁（持有者还在跑则拒绝）
```

- `--dry-run`：只查远程有没有更新，不下载不写盘，适合 CI 里判断"要不要更新"。
- `--force`：`add` / `update` 强行覆盖已被其他项目占用的 skill；`update` 即使 sha 没变也
  重新下载覆盖；`unlock` 强行清活锁。
- `--fresh`：忽略本地 60 秒缓存，直接问 GitHub。

环境变量：
`GHPM_HOME`（换根目录）、`GHPM_MIRRORS`（逗号分隔的镜像前缀）、
`GHPM_TIMEOUT`（下载超时秒数）、`GHPM_CACHE_TTL`（远程信息缓存秒数，默认 60，设 0 关闭）、
`GHPM_WORKERS`（批量查询并发数，默认 8，上限 16）、
`GHPM_INFO_REUSE_SEC`（update --all 复用预检信息的保鲜窗口，默认 120 秒，见下）、
`GHPM_BACKUP_MODE`（`link` 硬链接，默认 / `rename` 同卷整目录搬迁 / `copy` 整目录复制）、
`GHPM_LOCK_LEASE`（锁租约秒数，默认 900）、
`GHPM_MAX_ZIP_UNCOMPRESSED`（默认 2 GB）、`GHPM_MAX_ZIP_FILE_SIZE`（默认 512 MB）、
`GHPM_DOCTOR_MIN_FREE_MB`（doctor 的低空间告警阈值，默认 1024 MB）。

测试：`python scripts/test_ghpm.py`（26 项回归，全隔离在临时目录，不碰真实 ~/.workbuddy）、
`python scripts/e2e_test.py`（走真实网络的端到端安装/校验/移除/回滚/收敛验证）。

## 代码结构（v4 从单文件拆成包）

```
scripts/
├── ghpm.py              入口：只做 sys.path + 调 ghpm.cli.main（python ghpm.py <cmd> 照旧可用）
└── ghpm/
    ├── config.py        路径 / 环境变量 / 安全上限
    ├── errors.py        错误码与异常
    ├── models.py        TreeStats / SourceIndex / RepoInfo / InstallPlan
    ├── util.py          时间戳、原子写、单次遍历、指纹、事件输出
    ├── pathguard.py     路径 containment（删除类操作统一收口）
    ├── lock.py          写锁 + 心跳租约
    ├── registry.py      清单读写与 v1→v4 迁移
    ├── discovery.py     skill 发现（与体积统计共用一次遍历）
    ├── remote.py        Provider（api / ungh / atom）+ 解析器 + 缓存 + 下载
    ├── archive.py       ZIP 索引、安全上限、文件名校验、安全解压
    ├── transaction.py   事务与回滚
    ├── installer.py     resolve → fetch → inspect → plan → apply
    ├── verifier.py      数据完整性检查
    ├── commands/        各命令（list/scan/inspect/add/update/remove/verify/doctor…）
    └── cli.py           argparse 与分发
```

三种调用方式等价：`python ghpm.py list`、`python -m ghpm list`、`import ghpm; ghpm.install(...)`。
**测试注意**：拆分后 monkeypatch 要打在**定义处**（`ghpm.remote.repo_info`、
`ghpm.installer.fetch_zip`），打在包属性（`ghpm.repo_info`）上不会影响模块内部调用。

## 进度输出（宿主可解析）

所有写操作都会打印结构化进度行，前缀 `__GHPM__ `，后面是 JSON：

```
__GHPM__ {"phase":"downloading","label":"下载中 · 主源 codeload","percent":25}
```

phase 取值：`starting` → `checking` → `downloading` → `inspecting` → `backing-up`
→ `applying` → `done` / `failed`（失败前会有 `rollback`）。
`applying` 阶段**不可取消**（正在写盘）。

失败时带 `code` 与 `hint`：`E_INVALID_SPEC` / `E_NOT_FOUND` / `E_NOT_SKILL` /
`E_ALREADY` / `E_NETWORK` / `E_TIMEOUT` / `E_LOCKED` / `E_CANCELLED` / `E_CONFLICT` /
`E_UNSAFE_PATH` / `E_BAD_ARCHIVE`。

## add 做了什么

1. 查仓库 `default_branch` 与最新 commit sha（这一步**不走缓存**，必须拿最新值）
2. 下载 codeload ZIP；先扫描中央目录确认 skill、条目数和展开体积，无 skill 时不解压；
   解压前查压缩炸弹上限（条目数 / 单文件大小 / 总展开体积 / 压缩比）+ 条目名合法性
3. 解压前及事务前分别检查磁盘空间；主源失败时依次回退镜像
4. 识别 skill：既认 `.../skills/<name>/SKILL.md`（多 skill 包），也认仓库根目录
   直接一个 `SKILL.md`（单 skill 仓库），逐个安装到 `~/.workbuddy/skills/`
5. **算 InstallPlan**：对比清单里的旧 skill 与远端的新 skill，得出新增 / 更新 /
   **下线** 三类；查冲突（skill 已被别的项目占用则默认拒绝，`--force` 才覆盖）
6. 完整源码副本保存到 `~/.workbuddy/<repo名>-source/`（解压根直接搬过去，不重拷一遍）
7. 记录内容指纹（源码树 + 每个 skill），写清单；**改动前先备份**到 `~/.workbuddy/.ghpm-backup-<owner__repo>-<ts>`
8. 任何一步失败 → 自动从备份回滚；回滚返回 `restored` / `failed` 明细，
   `failed` 非空时保留备份并提示手动恢复

## verify：清单 ↔ 磁盘 ↔ 远端

`doctor` 回答「环境能不能用」，`verify` 回答「数据对不对」。三条边各查一遍：

```
清单 ──磁盘    source_dir / skills 是否存在、SKILL.md 在不在、路径是否越界
磁盘 ──清单    有没有没人认领的孤儿 skill 目录
清单 ──远端    sha 是否还跟得上（--remote）
```

**内容指纹**是 v4 新加的能力：安装时把源码树与每个 skill 的指纹写进清单，
verify 重算一遍就能发现「GitHub 没更新，但本地 skill 被人手改过」——
只比对 sha 是发现不了的，sha 描述的是远端。
指纹规则：源码树记「路径 + 大小」，skill 额外记小文件（≤ 64 KB）的内容哈希。
老清单（v3.2 之前装的）没有指纹，verify 会报 `no_source_hash` 而不是报「被改过」。
`--json` 输出结构化结果（`projects[].findings[].code`），适合脚本消费。

## 事务模型（v3 的核心）

`install` / `update` / `remove` / `scan` / `rollback` 全部走同一套 `Transaction` **和同一把写锁**：

```
加锁 → 远程信息 → 下载 → 校验 → 算 plan → 备份（含清单快照） → 写文件 → 原子提交清单 → 清备份
                                        ↓ 任一步失败
                              文件系统 + 清单一起还原 → 保留备份
```

- 备份 manifest 记录每个目标路径**操作前是否存在**：
  存在的还原内容，**不存在的删除新建出来的目录**。v2 只备份已存在的路径，
  全新安装失败时 `expected==0`，回滚形同虚设、还会误判成功并删掉备份。
- 清单文件 `github-projects.json` 也在事务内：写盘成功但 `save()` 失败时，
  不会出现"文件是新版、清单还是旧版"。
- `save()` 走「唯一临时文件 → fsync → `os.replace`」原子提交，进程被 `kill -9`
  也不会留下半截 JSON，且并发进程不会互相覆盖临时文件。
- 回滚结果按项记录 `restored` / `failed` / `skipped`；只有 `failed` 为空才判定完整成功。
- 备份任一项失败时不会进入 applying，避免在没有完整恢复点的情况下覆盖文件。
- **回滚也要拿写锁**：它同样是写操作，否则会和正在进行的 install/update 并发改同一个目录。
- 备份介质（`GHPM_BACKUP_MODE`）：
  - `link`（默认）—— 同卷内建硬链接树，不读数据、不占第二份磁盘，跨卷自动退回 `copy2`。
  - `rename` —— 同卷整目录 rename 到备份目录，**O(1)、零遍历**；代价是写入期间
    原目录暂时不在原位。回滚就是 rename 回来。适合超大仓库。
  - `copy` —— 整目录复制，行为与 v3.1 一致。
  三种模式都要求 apply 阶段**整目录替换**（rmtree + 写入）而不是原地改写 ——
  原地改会顺着硬链接把备份也改了，当前所有写入路径都满足这条。

## 状态收敛：update 以远端为目标，不是「把新增的拷进来」

v3.1 只跟踪「本次远端发现的 skill」。远端删掉某个 skill 后，本地那份永远留着，
变成**孤儿目录**：清单里已经没有它，`skill_owner_map` 认不出，`remove` 也管不到，
多次 update 后垃圾越来越多。

v3.2 起把清单里的旧 `skill_names` 一起纳入计算：

```
old_skills = 清单记录的          new_skills = 远端包里的
removed    = old - new           ← 这些本地目录必须删掉
added      = new - old
updated    = 交集
```

`removed` 里的目录**也进事务**，所以「删掉」同样可回滚 —— 删除是破坏性操作，
不能做成不可逆的。实测：远端下线 1 个 skill 后，磁盘与清单同步收敛到 14 个（见 e2e 第 7 步）。

## 路径安全

`remove` / `rollback` 的删除目标来自清单，而清单可能被手工编辑、被旧版本写坏、
被程序自身的 bug 污染。v3.1 直接 `rmtree(Path(hit["source_dir"]))`，
一个被改坏的清单就能删掉 `~/.workbuddy` 之外的任意目录。

v3.2 起所有删除都先过 containment 校验（`validate_managed_path` /
`validate_skill_name` / `remove_managed_path`），越界就整条拒绝并报 `E_UNSAFE_PATH`，
**不会「跳过不认识的路径然后把剩下的删了」**。`restore_backup` 同样校验每个还原目标，
坏 manifest 借回滚删外部目录的路被堵死。

## v4.0 增量

- **整包拆成模块**：2721 行单文件 → 14 个模块 + `commands/`，入口 `ghpm.py` 保持
  `python ghpm.py <cmd>` 与 `__GHPM__` 协议完全兼容。改 GitHub API 不用碰事务代码。
- **一次遍历**：`index_source_tree()` 用 `os.scandir` 递归**一次**同时产出
  「技能清单 + 整树体积 + 各 skill 体积」。v3.2 是 `find_skill_dirs` 走一遍、
  `path_size_bytes(root)` 再走一遍、每个 skill 子目录又各走一遍，
  实测（2100 文件 / 100 skill）放大 **2.02x**，现在压到 1 次。
  ⚠️ 注意：这不是评审里说的 `O(root × skill_count)` —— skill 目录是 root 的
  **不相交子树**，重复度是常数 2，不是 N 倍。
- **消灭 N+1 远程请求**：`install()` 新增 `info=` 参数，`update --all` 把批量预检
  拿到的 `RepoInfo` 直接传进去重新查。实测 5 个仓库从 **10 次 `repo_info`
  （约 20 个 HTTP）降到 5 次（约 10 个）**，匿名额度下能处理的仓库数翻倍。
- **保鲜窗口**（`GHPM_INFO_REUSE_SEC`，默认 120 秒）：这是对「批量预检 → 批量执行」
  的修正。如果预检完一次性写，后面几个仓库会拿着几分钟前的 sha 去安装，
  而这期间远端可能又变了。所以保留**逐仓库独立事务**，复用的信息超窗就为那个
  仓库单独补查一次 —— 宁可多一个请求，也不拿过期 sha 安装。
- **源码不再写两遍**：解压根直接 `rename` 进 `source_dir`（跨卷自动退回 copytree），
  再把 skill 从 source_dir 拷进 `skills/`。v3.2 是「解压 → copytree 到 source →
  copytree 到 skills」，同一份源码完整落盘两次。
- **Provider 抽象**：`api.github.com` / `ungh.cc` / `commits.atom` 拆成独立
  Provider，由 `RemoteResolver` 负责顺序与合并。回退顺序仍然是
  **ungh 在 atom 之前**（见踩过的坑）。以后加 Gitee / GitLab / 企业 GitHub
  只要再写一个 Provider。
- **`RepoInfo` dataclass**：字段有了类型与补全，但保留 `info["sha"]` 式访问，
  老调用、缓存文件、事件载荷都不用改。
- **ZIP 设备名防护**：实测标准库 `extractall` 已经会剥掉 `..`、绝对路径、
  盘符和 `:`（换成 `_`），但**不管 Windows 保留设备名** —— 条目叫 `NUL`/`CON`
  时解压不报错，文件却被系统吞掉（目录里啥都没有，而 `(dest/"NUL").exists()`
  反而是 True），属于**静默丢数据**。`check_zip_names` 在解压前拦下设备名（仅 nt）
  与控制字符、绝对路径/盘符。
- **锁心跳租约**：持有写锁期间每 5 秒 `utime` 锁文件续租（不重写内容，
  避免破坏 O_EXCL 语义）。进程存活仍是权威判据；查不出来时（`tasklist` 缺失 /
  无权限）退回租约判断，**拿不准就当成有人在跑**，不抢活锁。
  v3.2 的 `pid_alive` 会在 `tasklist` 不可用时抛异常并一路穿透 `acquire_lock`。
- **`verify` 命令** + 清单 `schema_version: 4`（新增 `content_hash` / `skill_hashes`，
  v1→v2→v3→v4 迁移链）。
- **`update --all` 先打计划**：安装前先输出「N 个需要更新 / M 个已是最新 / K 个没查到」
  的表格，再逐个执行（不再是黑盒刷屏）。

## v3.2 增量

- **状态收敛**：update 删除远端已下线的 skill，且删除可回滚（见上）。
- **install 真正阻断冲突**：v3.1 的 `inspect` 早就算出了冲突，但 install 只报告不阻止，
  结果是 B 装上去悄悄顶掉 A 的 skill。现在默认报 `E_CONFLICT` 拒绝，`--force` 才覆盖。
  `inspect` 与 `install` 共用同一个 `find_skill_conflicts`，保证预检结论 == 安装行为。
- **rollback 纳入写锁**，与 install/update/remove/scan 互斥。
- **路径 containment**：remove / rollback 只允许动 WB 目录内的路径。
- **并发批量查询**：`check --all` / `update --dry-run --all` / `scan` 走线程池
  （默认 8 并发）。实测 12 个仓库 **24.73s → 2.94s（8.4×）**。worker 封顶 16：
  目标是压掉串行等待，不是打爆 GitHub API（匿名额度只有 60 次/小时）。
- **缓存原子写用唯一临时名**（`mkstemp`），并把容量清理从「每次写都遍历」改成低频触发。
- **ZIP 压缩炸弹防护**：条目数、单文件大小、总展开体积、压缩比四道上限，
  全部在**解压前**检查（此时零成本）。结构性问题直接失败，不换镜像重试。
- **parse_repo 严格化**：改用 urlparse 校验 https + github.com + 恰好两段路径。
  v3.1 的正则 search 会把 `.../foo/bar/xxxx` 截成 foo/bar、把 `?query` 一起吞进去。
- **时间戳改 UTC ISO 8601**：v3.1 的 `time.strftime` 没有时区、无法跨机器比较、
  夏令时附近有歧义。清单存 UTC，`list` 展示时转本地时间（兼容旧格式）。
- **install 拆成五层**：`resolve → fetch → inspect → plan → apply`，
  引入 `InstallPlan` dataclass。「算出要做什么」和「真的做」完全分开。

## v3.1 增量

- 写锁通过 `os.open(..., O_CREAT | O_EXCL | O_WRONLY)` 排他创建；竞争者不能覆盖现有锁。
- `github-projects.json` 固定写入 `schema_version`，旧清单在内存中按版本迁移。
- 时间字段区分 `installed_at`、`updated_at`、`checked_at`、`previous_sha`；
  相同 SHA 的强制重装不会刷新 `updated_at`。
- `inspect` 输出 `tree_size`、`inspection_mode`、`inspection_complete`，能识别 Git Trees 截断。
- `doctor` 检查 Python、curl、GitHub API、token、目录、registry、锁、缓存、skills、备份和磁盘。

## v3 基础能力

- **repo 是唯一 ID**，`name` 只是显示名：`alice/utils` 和 `bob/utils` 不再互相覆盖；
  源码目录撞车时自动退化为 `owner__repo-source`。
- **远程信息有 60 秒缓存**（`~/.workbuddy/.ghpm-cache/`）：`check --all` 不再几十个
  请求轰 GitHub（实测第二次 2.5s → 0.6s）。装/更新永远 `ttl=0` 拿最新 sha，`--fresh` 可绕过。
- **`update --all` 先比 sha**：没变就跳过，不重复下载解压备份（`--force` 强制重装）。
- **`unlock` 不再无条件删锁**：先看持有者进程是否活着，活着就拒绝（否则等于绕过
  token 锁放行并发写），只有确认已退出或 `--force` 才清。

## 关键约束（踩过的坑）

- **不要用 `git clone`**。本机直连会被代理拦截（`CONNECT tunnel failed, response 502`）。
  curl 会读取 `http_proxy/https_proxy` 环境变量，可正常连通。脚本所有网络请求都走 curl。
- **Python 是 Windows 原生程序，不认 Git Bash 的 `/tmp`**。临时路径交给 `tempfile`，不要手写 `/tmp/...`。
- **GitHub API 未认证限流 60 次/小时**，很容易打光。实测限流时 `api.github.com/.../git/trees`
  返回 403、`ungh.cc/.../files` 返回 429，此时 `inspect` 只能靠 atom 拿到 sha，
  `skill_names` 会是空的（**这不是 bug**，安装时以 ZIP 中央目录为准）。
  脚本有三层回退：① 配 `GITHUB_TOKEN` → 5000 次/小时；② ungh.cc 代理；
  ③ commits atom feed（不需要额度，能拿到最新 sha）。预检/检查在限流下仍能工作。
  **回退顺序必须是 ungh 在 atom 之前**：限流时 branch 还停在默认 main，先拉 atom
  会去请求 `commits/main.atom`，默认分支非 main 的仓库就白跑一趟。
- 写操作靠 `~/.workbuddy/.ghpm.lock` 串行化。判定「是否真被占用」看的是
  **持有者进程是否还活着**，所以进程被强杀后锁不会永久堵死。
  加锁用 `O_CREAT | O_EXCL` 排他创建；只有创建成功的进程才持锁，竞争者不会覆盖；
  解锁仍校验 token，只删自己创建的锁（pid 会被系统回收复用，不能只信 pid）。
  手动清锁用 `ghpm unlock`——它会先确认持有者进程是否还活着，活着就拒绝（避免并发写）。
- 备份目录名用 `owner__repo`，不是光用仓库名 —— 否则 `owner1/utils` 和 `owner2/utils`
  的备份会撞车，remove 可能误删。
- 清单文件损坏时**先改名留档**为 `github-projects.json.corrupt-<ts>` 再按空清单处理，
  不会无声重置后被覆盖。
- 所有网络请求都走 curl 且**必看 HTTP 状态码**：`curl -sSL` 对 404 页面也返回 0，
  只看退出码会把「下到一张错误页」当成功。
- **文件改名比复制便宜得多**：能 rename 就不要 copytree（apply 阶段与 rename 备份
  都靠这条）。但 rename 的前提是「整目录替换」，原地改文件会顺着硬链接污染备份。

## 用法建议

- 用户问"我装了哪些 GitHub 项目"→ `list`。
- 用户问"这个仓库能装吗/里面有什么"→ `inspect`（只读，安全，会告诉你有几个 skill、
  会不会覆盖已装的）。
- 用户问"有没有更新"→ `check`。
- 用户说"更新一下"→ 先 `check` 确认，再 `update`。**更新会覆盖本地改动**，改过源码先确认。
- 用户说"检查环境/为什么不能安装"→ `doctor`；用户说"文件丢了/本地被改过吗/清单和磁盘对不上"→ `verify`。
- CI 可用 `doctor --json`、`verify --json`；离线诊断用 `doctor --no-network`。
- 移除/更新出错 → 从 `.ghpm-backup-*` 目录用 `rollback` 恢复。
