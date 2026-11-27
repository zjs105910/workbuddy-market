# WorkBuddy Market 优化说明（2026-11-27）

> **适用版本**：基于 `v2.41.0`（commit `fbc3ca16`）的工作区改动。
> **状态**：已提交并随 `v2.42.1` 发布；基线是 `v2.41.0`（commit `fbc3ca16`）。
> **约束**：正常路径的功能与外部行为保持不变；仅在故障路径修复了 3 处缺陷，本文单独列出。
> **方法**：先读代码形成候选 → 用只读探针在真实数据上复现/量化 → 修改 → 用同一探针复验 → 全量回归。所有性能数字均为本机（Windows、Python 3.13、25 个技能 / 134 个文件 / 110 条注册表）实测，非估算。

---

## 1. 结论速览

| 类别 | 优化点 | 效果（实测） | 主要风险 |
| --- | --- | --- | --- |
| 性能 | 消除 `build_state` 中每个 skill 一次的全量配置校验 | **567 ms → 32 ms**；`load_config` 41 次 → 1 次 | 极低：同一份已校验 `cfg` 贯穿一次状态构建 |
| 性能 | `_walk_tree` 用等价字符串切片替代逐文件 pathlib 构造 | 492 文件扫描 **13.9 → 3.7 ms**（3.7×） | 低：相对路径口径由单测逐键钉死 |
| 错误处理 | `_send` 客户端断连不再外抛 | GET 不再记误导性 error 事件；POST 不再打 traceback | 低：仅影响已断开的连接 |
| 并发 | `FileLock` 重入计数按锁文件隔离 | 持市场锁期间 `log()` 的日志锁获取次数 **0 → 1** | 低：写日志时多几次系统调用 |
| 去重 | 任务派发 / 注册表条目查找 / 卸载视图拼装收口 | 净减约 40 行样板；少 3 处会各改各的副本 | 低：行为等价，有回归钉子 |
| 缺陷 | 任务体漏异常不再永远停在「运行中」；弹窗按钮文案不再串台 | 仅改变故障/连续操作路径 | 中低：用户会看到「失败」而非卡住 |
| 基建 | pytest 显式优先加载仓库 `src/` | 停止「子集测试静默测到 venv 里 2.25.0 旧副本」 | 无产品行为影响 |

**验证总览**：py_compile OK · selftest **893/893** · pytest **127 → 165/165** · ruff 0.17.0 全过 · ui_smoke **49/49** · node --check 13 个模块 · privacy-audit 646 文件干净 · launcher 自检通过 · recover 0 项。

---

## 2. 详细优化项

### 2.1 性能：`build_state` 重复读配置（影响最大）

**问题 / 证据**
`build_state("ui")` 是页面加载与每次操作后刷新的后端入口。cProfile 实测每次约 **567 ms**，其中 **93.8%**（13.35 s / 14.2 s，20 次采样）耗在 `load_config()`：每次状态构建调用它 **41 次**，`ensure_child` 1183 次，`nt._getfinalpathname` 5824 次。根因是调用链：

```
classify_skill → needs_exact(purpose) → verify_mode() → load_config()
```

即**每分类一个 skill 就重新读盘 + 全量校验一次配置**（单次约 11 ms，因为 `validate_config` 对每个声明的 skill 做 `ensure_child` → 两次 `Path.resolve()`），而 `classify_skill` 的参数里本来就有已经校验过的 `cfg`。技能越多线性越慢；CLI `launcher --status` 也走同一入口。

**改动**
- `config.verify_mode(cfg=None)` / `config.needs_exact(purpose, cfg=None)`：新增可选参数；**不传时和原来一样自己读盘**。
- `trash.trash_config(cfg=None)`：同样处理。
- `uninstaller.classify_skill`、`state.build_state`（含 `verify` / `verifyEffective` / `trash.policy`）传入已有的 `cfg`。

**原因**
把配置读取留在唯一入口（`load_config`），只让调用链把已经拿到的值传下去；不是加缓存——缓存会带来「配置文件被改了但进程还用旧值」的语义风险。

**风险 / 缓解**
一次 `build_state` 内若磁盘上的配置在微秒级窗口里被改动，现在使用开头那一份，而不是每个 skill 各读一次。**这不是行为回退**：同一状态快照本来就应使用同一份配置。新增参数不改变任何已有调用方；`core.verify_mode is wm.config.verify_mode` 等注入点身份断言保持成立。

**验证**
- 同一探针：`load_config` **41 → 1 次**，`build_state("ui")` 中位数 **567.3 → 32.4 ms**（精确模式 55 → 37.8 ms）。
- **等价性硬证据**：把 HEAD 原始代码导出到临时目录，让新旧两版代码在同一组真实数据上各跑一次，`build_state(ui)` / `build_state(uninstall)` / `installed_repos` / `trash_stats` / `trash_config` / `verify_mode` / `needs_exact` 的 JSON **逐字节一致**（双方 sha256 均为 `b6260e2075771027623a…`）。
- `tests/unit/test_config_lookup.py`：12 个用例钉住「传 cfg 与不传结论一致」与「批量分类不再读盘」。

### 2.2 性能：`_walk_tree` 去掉逐文件 pathlib 开销

**问题 / 证据**
`scanner._walk_tree` 对每个文件做 `Path(e.path).relative_to(root)`：两个 `PurePath` 构造 + 逐段归一化/比较。cProfile 显示这条路径占整次扫描累计时间的约 **75%**。而 `_scan` 是打包、包校验、安装暂存、内容哈希、回收站计量的共同底座。

**改动**
`e.path` 恒等于「扫描目录 + 分隔符 + 名字」（`DirEntry.path` 即 `os.path.join`），改为字符串切片 `e.path[cut:].replace("\\", "/")`；根本身以分隔符结尾时（盘符根 `C:\`、POSIX `/`）切片起点差 1，已单独处理。

**原因**
不改变任何键的格式（仍是 POSIX 风格相对路径），只去掉每文件重复的对象构造。

**风险 / 缓解**
相对路径就是 manifest 的 `files` 键与所有权指纹口径，错一个字符整条供应链校验就失效。因此：
- 修改前在 3 棵真实目录树 × 2 种排除器上逐键比对新旧实现，**全部一致**；
- `tests/unit/test_scanner_walk.py` 用旧算法（pathlib）当参照，钉住嵌套、根层文件、空格/中文/引号文件名、尾分隔符根、排除器。

**验证**
| 目录 | 文件数 | 改前（12 次最小值） | 改后 |
| --- | --- | --- | --- |
| bundled/novel-writing-suite | 492 | 13.93 ms | 3.73 ms |
| plugins | 499 | 15.39 ms | 3.91 ms |
| ~/.workbuddy/skills | 166 | 7.35 ms | 3.75 ms |

### 2.3 错误处理：客户端提前断开时的 `_send`

**问题 / 证据**
探针假造一个「一写就抛 `ConnectionResetError`（Windows 10054）」的 socket，直接调用 `Handler._send`：
- 原来 `end_headers()`（它本身就会写 socket）在 `try` 之外，连 `BrokenPipeError` 都漏出去；`ConnectionResetError` / `TimeoutError` 也不在 `except` 列表里。
- 后果：`GET` 被兜底逻辑记成一条 error 级「未捕获异常」事件（用户能在事件流抽屉里看到）；`POST` 异常冒出 `do_POST`，标准库 `socketserver.handle_error` 往 stderr 打 traceback。

**改动**
`end_headers()` 与 `wfile.write(body)` 一起进 `try`，按 `except OSError` 兜住断连/超时的所有形态，并置 `close_connection = True`（连接已废，不让 `handle()` 继续读下一个请求）。

**原因**
响应发不出去没有补救手段；普通断连不是服务端错误，不该污染事件流/控制台。

**风险 / 缓解**
`except OSError` 比原来宽，可能掩盖真实的 socket 写入错误——但此时同样无法向对端交付响应，且标准库对超时也是「丢弃连接」的同一处理。健康连接的响应字节与头保持不变（单测断言 200 状态行、CSP、X-Frame-Options、Cache-Control、body）。

**验证**
探针复验：三种断连异常 + 超时全部静默返回，`close_connection=True`，`do_GET` / `do_POST` 留下的事件日志为空；`tests/unit/test_server_regressions.py` 6 个相关用例；ui_smoke 49/49。

### 2.4 并发：`FileLock` 的可重入计数按锁文件隔离

**问题 / 证据**
`FileLock._depth` 是**类级** `thread-local`，被所有实例共享。持市场锁期间 `log()` 会 new 一个日志锁 `FileLock` 实例，它看到共享深度 > 0 就当作重入，**根本不去拿日志锁**。计数探针：

```
无锁时 log()          日志锁真实获取次数 = 1
持市场锁时 log()      日志锁真实获取次数 = 0
释放市场锁后 log()    日志锁真实获取次数 = 1
```

安装 / 卸载 / 打包 / 恢复正是写日志最多的操作，恰恰在这些时段「轮转 + 追加」没有锁保护（与另一进程并发写时可出现乱序/丢行）。

**改动**
嵌套深度改为「每线程 + 每锁文件」一份：`_depths` thread-local dict，key 为 `os.path.normcase(str(path))`。`locked()` 与 `_HELD` 的逻辑不动。

**原因**
同一把锁重入要识别，不同锁文件不该互相冒充重入。

**风险 / 缓解**
持市场锁写日志时现在会真的抢日志锁（每次多几次系统调用，可忽略）；已确认加锁顺序只有「市场锁 → 日志锁」，日志锁内不会反向取市场锁，无死锁环。同一实例嵌套、跨实例同文件重入、跨线程独占等旧语义均有单测。

**验证**
探针复验三种场景均变成 **1 次**；`tests/unit/test_locking.py` 6 个用例；selftest 的三平台文件锁/并发用例 893/893。

> 附注：曾用推演怀疑「`_HELD` 计数被日志锁的 `__exit__` 抹掉，导致嵌套 `locked()` 自锁超时」。探针**否定了这一半**（`__exit__` 在深度 > 1 时直接返回，不碰 `_HELD`），因此没有针对它做改动。

### 2.5 重复代码收口

| 位置 | 重复内容 | 收口后 |
| --- | --- | --- |
| `market_server.py` | `_remote_job` / `_registry_install_job` / `_catalog_refresh_job` 各抄一份「抢闸门 → 建任务 → finally 还令牌」 | 统一 `_start_job(title, body, reject_detail)`，保留原函数名/签名与「并发满员回 None」契约 |
| `registry.py` | 按 `repo` casefold 查注册表条目 3 处 | `find_entry(reg, repo)`（形状不对按「没有」处理） |
| `state.py` | 卸载视图 7 字段 + `skillDetail` 各 2 处 | `_plan_view(plan)` / `_skill_detail(want, items)`；ghpm 组是手工合成计划，语义不同，保持原样 |
| `catalog.py` | `is_stale` docstring 说自动刷新循环用它做闸门（实际不用） | 改正文档口径 |

**风险 / 缓解**
`_start_job` 改的是并发闸门的核心路径。selftest 里「真并发上限」「满载计数」「被拒不入任务表」等用例全部保留并通过；pytest 另加 7 个 `_start_job` 用例（满员、建任务失败还令牌、令牌归还一次、任务体异常收尾、三个任务函数各一条）。

### 2.6 仅改变故障路径的缺陷修复（需单独知悉）

1. **`_remote_job` 任务卡死**：原任务体只有 `finally` 没有 `except`，一个未料到的异常会冒到线程顶层，`_job_finish` 不执行，任务**永远停在「运行中」**（与项目历史里 v2.5 的 NameError 同类）。现在 `_start_job` 统一兜底：记「失败」、写事件日志、归还令牌。正常任务的输出与文案不变。
2. **弹窗按钮文案串台**：三个弹窗共用 `#cfmYes` / `#cfmNo`。`errorBox` 把次要按钮改成「关闭」后不还原，下一次确认框的取消按钮就一直叫「关闭」；`errorBox` 不设主按钮文案，前一个确认框传的「卸载」等会残留在错误弹窗的关闭按钮上。现在两个入口各自显式设置自己负责的按钮文案（`utils.js` 两行）。ui_smoke 49/49 通过。

### 2.7 测试基建：pytest 测到了 venv 里的旧副本

**问题 / 证据**
开发机 venv 的 site-packages 装着 **2.25.0** 的 `workbuddy-market`；`tests/conftest.py` 只把仓库根加入 `sys.path`，没加 `src/`。`workbuddy_market` 能解析到仓库源码，全靠「按字母序第一个被收集的 `test_artifact.py` 先 `import market_core`」（由它把 `src/` 插到最前）。**单独运行测试子集时会静默测到 2.25.0 旧代码**——本次新增测试初次单独运行时就以 `ImportError: cannot import name 'SEARCH_PAGE_MAX'` 暴露了这一点。

**改动 / 验证**
`tests/conftest.py` 显式把 `src/` 放到 `sys.path[0]`。验证：单独运行任意一个新增测试文件都能通过；打印 `workbuddy_market.__file__` 确认解析到仓库 `src/`。

---

## 3. 发现但未改动的问题（会改变外部产物/CI 行为，需你决定）

这些是本轮检查中发现的真实缺陷，但修复会改变**已发布的分发产物或 CI 产出**，超出「不改变外部行为」的授权，因此只报告、不修改。

### 3.1 【高】精选市场 zip 的 skill 目录多嵌套一层

- **证据**：用合成的 `repo/skills/<name>/SKILL.md` tarball 替换网络抓取，跑真实的 `scripts/build_marketplace_zip.py`，产物结构为：

  ```
  .codebuddy-plugin/marketplace.json
  plugins/acme-form-a/skills/README.md              ← 仓库级杂物也被拷进 skills/
  plugins/acme-form-a/skills/skills/alpha/SKILL.md  ← 多了一层 skills/
  plugins/acme-form-a/skills/skills/beta/SKILL.md
  ```

- **原因**：`choose_skills_root()` 返回的是「**含有 `skills/` 子目录的那一层**」（产物构建脚本随后按 `src / "skills" / name` 取用），而 zip 脚本第 128 行却 `shutil.copytree(skills_root, dest / "skills")`。
- **影响**：README 第 85 行把 `workbuddy-marketplace.zip` 作为面向用户的安装路径公开推广；按当前布局，WorkBuddy 原生市场在 `skills/<name>/` 这一层找不到任何 skill。
- **建议修法**：按产物构建的口径逐 skill 拷贝 `skills_root / "skills" / name`，并排除非 skill 的仓库内容；随后重建并发布 zip，必要时通知已下载用户。
- **为什么没改**：会改变公开分发产物的内容，且需要重新发版/重新分发，属于产品发布决策。

### 3.2 【中】注册表刷新失败时 `latestSha` 被写成空串

- **证据**：`scripts/build_registry.py:68` 先置 `out["latestSha"] = ""`，`ref_fetch` 异常被 `pass` 吞掉；而 `validate_registry.py:271` 要求 `latestSha` 为 40 位十六进制，`registry.yml` 在提交前跑校验。结果：GitHub commits 接口抖一次，当天整轮注册表刷新作废（落不到 main）；运行时 `_registry_drift()` 遇到空 `latestSha` 直接放行，上游漂移检测对该条目静默失效。
- **建议修法**：初值改为 `str(entry.get("latestSha") or "")`，与函数 docstring 里「失败保旧值」的承诺一致。
- **为什么没改**：会改变每日 CI 的写入行为，应作为发版项处理。

### 3.3 【低】其他待办

- `uninstall_market.py:190` 直接 `write_text` 覆盖 `known_marketplaces.json`，非原子写（前面有备份兜底）。
- `jobs.js:127` 任务轮询 `catch(e){ return; }`：服务重启/任务丢失后每 700 ms 无限空转，弹窗一直显示「执行中」，无提示。
- 审计报告里被标为最高优先级的「errorBox 从不显示、重试按钮无效」和「发版同步 fail-open」经逐条核实**均为误报**（前者把记录历史 bug 的注释当成现状，后者没读 `return 1`），没有据此改动。

---

## 4. 验证方式（可复现命令）

```bash
cd <仓库目录>
PY=python                     # 用本项目要求的 Python 3.13（venv 或受管解释器均可）
export PYTHONPATH=            # 必须清空：避开 WorkBuddy shim 劫持 os.unlink

"$PY" -m py_compile market_core.py market_server.py launcher.py selftest.py \
      src/workbuddy_market/*.py scripts/*.py uninstall_market.py
"$PY" selftest.py                                  # 893 passed, 0 failed
"$PY" -m pytest tests/ -q                          # 165 passed
"$PY" -m ruff check market_core.py market_server.py launcher.py selftest.py \
      src/ scripts/ tests/                         # ruff 0.17.0, CI 六路径口径
"$PY" scripts/privacy-audit.py                     # 646 个跟踪文件干净
"$PY" launcher.py --status                         # v2.41.0 / 自检通过
"$PY" launcher.py --recover                        # 0 项
for f in web/app/*.js; do node --check "$f"; done  # 13 个模块
"$PY" scripts/ui_smoke.py                          # 49 passed, 0 failed
```

**针对具体优化的验证**
- 性能：`build_state("ui")` 计时 + 统计 `load_config` 调用次数（改前 567 ms / 41 次，改后 32 ms / 1 次）；`_scan` 在大目录上计时（见 2.2 表）。
- 等价性：把 HEAD 导出到临时目录，新旧两版代码在同一组真实数据上分别输出 `build_state` JSON，`cmp` 结果一致。
- 回归钉子：`tests/unit/test_config_lookup.py`、`test_scanner_walk.py`、`test_locking.py`、`test_server_regressions.py`（共 38 个新用例）。
- **变异验证**：把这些新测试拿到 HEAD 旧代码上运行——`config` 10/12 失败、`locking` 3/6 失败、`server` 10/14 失败；通过的恰好是「旧行为不变」的兼容性用例，`scanner` 4 个新旧都过（等价性测试本应如此）。

---

## 5. 变更文件清单与回滚

**修改（12 个 tracked 文件，251 行新增 / 152 行删除）**

`market_server.py`、`src/workbuddy_market/{catalog,config,importer,locking,registry,scanner,state,trash,uninstaller}.py`、`tests/conftest.py`、`web/app/utils.js`

**新增（4 个测试文件 + 本文档）**

`tests/unit/{test_config_lookup,test_scanner_walk,test_locking,test_server_regressions}.py`、`docs/optimization-2026-11-27.md`

**回滚**：改动未提交，可基于 `git diff` 逐项审阅后决定；4 个新增测试文件是未跟踪文件，回滚时需要单独处理。版本号与 CHANGELOG 未动，因此本轮改动本身不构成发版。
