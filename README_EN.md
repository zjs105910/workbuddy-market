# WorkBuddy Market

[简体中文](README.md) · **English**

[![CI](https://github.com/zjs105910/workbuddy-market/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/zjs105910/workbuddy-market/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/workbuddy-market.svg)](https://pypi.org/project/workbuddy-market/)
[![Downloads](https://img.shields.io/pypi/dm/workbuddy-market.svg)](https://pypi.org/project/workbuddy-market/)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](pyproject.toml)
[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**A local-first plugin marketplace for WorkBuddy.** Package local Skills as plugins, browse a curated community registry or search public GitHub repositories, review declared permissions and compatibility, and manage installs, updates, and removals through hash verification and recoverable transactions.

## What it does

- **Package your own Skills** and register the marketplace in WorkBuddy's plugin panel.
- **Discover community Skills** through a curated registry and a GitHub search view.
- **Review before installing**: inspect source, declared permissions, compatibility, and package details.
- **Recover from mistakes**: transaction recovery and a trash area help protect managed Skills during updates and uninstalls.
- **Keep local data local**: the web UI binds to `127.0.0.1`; personal market configuration and local Skill contents are not meant to be committed to this repository.

## Demo and downloads

Watch the reproducible product demo (about 80 seconds) before choosing an installation path. Formal releases ship landscape and vertical demo videos, subtitles, the manifest, Python packages, and a SHA-256 checksum file together.

- **Watch first**: [landscape MP4 (16:9)](https://github.com/zjs105910/workbuddy-market/releases/latest/download/workbuddy-market-demo.mp4) · [vertical MP4 (9:16)](https://github.com/zjs105910/workbuddy-market/releases/latest/download/workbuddy-market-demo-vertical.mp4) · [Chinese subtitles (SRT)](https://github.com/zjs105910/workbuddy-market/releases/latest/download/workbuddy-market-demo.zh-CN.srt)
- **Install the full app**: [latest formal release](https://github.com/zjs105910/workbuddy-market/releases/latest) (Windows installer, wheel, sdist, and `SHA256SUMS.txt`); Windows users can also [download `install.cmd` directly](https://github.com/zjs105910/workbuddy-market/releases/latest/download/install.cmd).
- **Curated skills only**: see “Curated skills only (zip import)” below. This lightweight distribution does not include the full app's pre-install safety review or recoverable uninstall.
- **Recording and release details**: [reproducible demo and privacy boundaries](docs/demo-video.md) · [formal Release process](docs/release-process.md)

> `registry-artifacts-*` are daily community-plugin artifact pre-releases, not the marketplace app. Look for a formal release titled `WorkBuddy Market vX.Y.Z`; download `SHA256SUMS.txt` from that same page to verify assets.

## Quick start (Windows)

### Just one file? One-click installer (recommended) ✅

**[👉 Click here to download install.cmd](https://github.com/zjs105910/workbuddy-market/releases/latest/download/install.cmd)** (the download starts immediately; prefer to inspect it first? [open the file page](https://github.com/zjs105910/workbuddy-market/blob/main/install.cmd) and download manually).

After downloading, **double-click** it. It automatically: checks/installs Python → installs pipx → pipx-installs/upgrades the `workbuddy-market` CLI → downloads the market root to `%USERPROFILE%\workbuddy-market` → runs doctor → starts the first-run wizard (**Enter = browse only, 2 = register into WorkBuddy**).

> Windows will show an "unknown publisher" security warning on double-click — the script carries no paid code-signing certificate (normal for open source). Click **Run**; the script is plain text you can review line by line on the file page above.

This is the **full version**: pre-install review, hash verification, transactions, and recoverable uninstall are all included. Safe to re-run (every step is idempotent and upgrades the CLI).

### No Git? Three steps to run (no Git needed, Python 3.10+ still required)

> 1. **Download**: open the [latest release](https://github.com/zjs105910/workbuddy-market/releases/latest) (look for the entry titled `WorkBuddy Market vX.Y.Z`; `registry-artifacts-*` are plugin-artifact pre-releases, not the app) and grab **Source code (zip)** (or the [main-branch ZIP](https://github.com/zjs105910/workbuddy-market/archive/refs/heads/main.zip));
> 2. **Extract**: unzip to any folder;
> 3. **Run**: double-click `安全模式-只开网页.cmd` to browse the marketplace first; when ready to integrate with WorkBuddy, double-click `一键启动.cmd`.

Python 3.10+ is still required (first-run setup checks it and explains what to install). No manual config file needed — it is initialized automatically on first launch.

### Already using CodeBuddy Code / WorkBuddy? One or two commands ✅

Run this in the chat box (or CodeBuddy Code CLI):

```
/plugin marketplace add zjs105910/workbuddy-market
```

This is the **bundled plugin market** (pinned to the repo's `bundled/` directory, zero drift). Browse with `/plugin`, install with `/plugin install <plugin>@workbuddy-market`.

For the **full daily-rebuilt community catalog** (25+ curated skills, pinned at human-reviewed sourceCommits):

```
/plugin marketplace add https://github.com/zjs105910/workbuddy-market.git#marketplace
```

Run `/plugin marketplace update` to refresh. Prefer a file? Use the zip import below. See [FAQ section 8](docs/FAQ.md) for the trade-offs between the lightweight entries.

### Curated skills only (zip import)

Just want the curated community skills, no tooling: download the [marketplace zip](https://github.com/zjs105910/workbuddy-market/releases/download/marketplace/workbuddy-marketplace.zip) and add it as a custom marketplace in the WorkBuddy plugin panel. Rebuilt daily by CI from the human-reviewed registry.

> Entry scope: the zip import was verified on the **WorkBuddy desktop plugin panel (5.7.6)**. CodeBuddy Code's marketplace entries (`marketplace.json` URL / Git repo / local path) belong to a different client and do not accept this zip — on CodeBuddy Code, install the full marketplace via pipx and register it instead.

> Trade-off: this path gives you skill distribution only — no pre-install review, no ownership grading, no recoverable uninstall. For the full safety chain, use the full version above.

### Prefer the command line? One command

```bash
pipx install workbuddy-market
workbuddy-market doctor     # health check; list / search to browse the registry
```

(Requires [pipx](https://pipx.pypa.io/); `uv tool install workbuddy-market` is equivalent.)

### With Git

Requirements: Python 3.10+ and Git.

To try the web UI first without registering the marketplace in WorkBuddy:

```powershell
git clone https://github.com/zjs105910/workbuddy-market.git
cd workbuddy-market
.\安全模式-只开网页.cmd
```

The local web UI uses `http://127.0.0.1:8777/` by default. Keep the terminal window open while using it; press `Ctrl+C` in that window to stop the server.

When you are ready to integrate with WorkBuddy, run `一键启动.cmd`. On first-run setup, pressing Enter selects browse-only mode; choose option `2` explicitly to request registration. Packaging and self-check prerequisites still apply.

The launch scripts have Chinese filenames. You can also start from PowerShell with `python launcher.py --no-register` to open the web UI without registering it.

## Listed plugins

<!-- registry-table:start -->

> **50** listed plugins; this table is refreshed daily by CI from the human-reviewed registry.

| Plugin | Description | Category | Trust |
| --- | --- | --- | --- |
| [Anthropic 官方技能集](https://github.com/anthropics/skills) | Anthropic's official repository of Agent Skills: document processing (docx/pdf/pptx/xlsx), frontend design, MCP building, canvas design, brand guidelines and more. | 官方 | Official |
| [Superpowers 工程方法论](https://github.com/obra/superpowers) | A cohesive software development methodology skill pack: brainstorming, planning, TDD, systematic debugging, parallel subagents, code review and finishing branches. | 开发工具 | Reviewed |
| [Matt Pocock 工程技能集](https://github.com/mattpocock/skills) | Engineering skills straight from Matt Pocock's .agents directory: pragmatic coding, review and collaboration skills for real-world projects. | 开发工具 | Reviewed |
| [GStack 创业指挥栈](https://github.com/garrytan/gstack) | Garry Tan's exact Claude Code setup: 23 opinionated tools acting as CEO, designer, engineering manager and more - run AI like a full startup team. | 开发工具 | Reviewed |
| [Addy Osmani 工程技能](https://github.com/addyosmani/agent-skills) | Production-grade engineering skills for AI coding agents by Addy Osmani (Chrome eng): debugging, performance, architecture and code quality. | 开发工具 | Reviewed |
| [Open Design 设计插件](https://github.com/nexu-io/open-design) | The open-source DeepSeek Harness design plugin (a Claude Design alternative): local-first design skills for producing usable UI and visuals. | 设计 | Reviewed |
| [Taste 品味技能](https://github.com/Leonxlnx/taste-skill) | Gives your AI good taste: stops boring, generic, template-generated output and makes UI and copy feel designed (installer and examples included). | 设计 | Reviewed |
| [AI Scientist 科研技能库](https://github.com/K-Dense-AI/scientific-agent-skills) | Agent skills library for science: turn an AI agent into a research assistant covering data analysis, literature and experiments. | 科研 | Reviewed |
| [agent-browser 浏览器自动化](https://agent-browser.dev) | Vercel's browser automation CLI for AI agents (same source as the official CodeBuddy plugin): page interaction, screenshots and form filling. | 自动化 | Reviewed |
| [Agents 技能大全](https://github.com/wshobson/agents) | A massive engineering skills collection: 184 skills covering backend, frontend, Python, K8s, observability, security, payments, LLM fine-tuning, quant trading and more. | 合集 | Reviewed |
| [ECC 智能体优化系统](https://github.com/affaan-m/ECC) | An agent harness performance optimization system: skills, instincts, memory, security and research tooling, with plugin directories for a dozen coding agents. | 合集 | Reviewed |
| [Karpathy 行为技能](https://github.com/multica-ai/andrej-karpathy-skills) | Skills distilled from Andrej Karpathy's observations to improve agent behavior and engineering judgment. Stable content, low-frequency updates. | 开发工具 | Reviewed |
| [Ponytail 最懒工程师](https://github.com/DietrichGebert/ponytail) | Makes your AI agent think like the laziest senior dev in the room: the best code is the code you never write. | 开发工具 | Reviewed |
| [Archify 架构图技能](https://github.com/tt-a1i/archify) | Turn any idea, plan or codebase into a beautiful interactive diagram - an agent skill for Claude Code with renderers and recipes. | 设计 | Reviewed |
| [ADHD 友好输出](https://github.com/ayghri/i-have-adhd) | A skill to stop your coding agent from burying the answer: ADHD-friendly, straight-to-the-point output. | 效率 | Reviewed |
| [Humanizer 去 AI 味](https://github.com/blader/humanizer) | Agent skill that removes signs of AI-generated writing from text, making output read like a human wrote it. | 写作 | Reviewed |
| [营销技能包](https://github.com/coreyhaines31/marketingskills) | Marketing skills for Claude Code and AI agents: CRO, copywriting, SEO, analytics and growth engineering. | 商业 | Reviewed |
| [学术研究技能](https://github.com/Imbad0202/academic-research-skills) | Academic research skills for Claude Code: research, write, review, revise, finalize - with paper reviewing and deep research specialties. | 科研 | Reviewed |
| [编辑级图表设计](https://github.com/cathrynlavery/diagram-design) | Editorial diagram design skills with 42 diagram types, for Claude Code, Codex, GitHub Copilot and more. | 设计 | Reviewed |
| [逆向与渗透技能路由](https://github.com/zhaoxuya520/reverse-skill) | Skill router pack for reverse engineering and authorized penetration testing: CTF sandbox orchestration, Burp MCP, Kali tooling. Authorized research only. | 安全 | Reviewed |
| [网络安全技能库](https://github.com/mukul975/Anthropic-Cybersecurity-Skills) | 817 structured cybersecurity skills for AI agents, mapped to 6 frameworks: MITRE ATT&CK, NIST CSF 2.0 and more. | 安全 | Reviewed |
| [技术书转技能](https://github.com/virgiliojr94/book-to-skill) | Turn any technical book PDF into a Claude Code skill - ready to study, reference and use while you work. | 效率 | Reviewed |
| [Hallmark 反模板设计](https://github.com/Nutlope/hallmark) | Anti-AI-slop design skill for Claude Code, Cursor and Codex - stop generic, template-generated UI. | 设计 | Reviewed |
| [文件化任务规划](https://github.com/OthmanAdi/planning-with-files) | Persistent file-based planning for AI coding agents and long-running tasks: crash-proof markdown plans. | 效率 | Reviewed |
| [产品经理技能市场](https://github.com/phuryn/pm-skills) | PM skills marketplace: 100+ agentic skills, commands and plugins - from discovery to strategy, execution and go-to-market. | 商业 | Reviewed |
| [宝玉技能集](https://github.com/JimLiu/baoyu-skills) | Baoyu's agent skills collection for Claude Code, widely used in the Chinese community. | 开发工具 | Reviewed |
| [Distilly 思维蒸馏](https://github.com/titanwings/distilly) | Distill how experts think into reusable skills for any agent or bot. Formerly Colleague Skills. | 开发工具 | Reviewed |
| [花叔设计](https://github.com/alchaincyf/huashu-design) | Huashu Design - an HTML-native design skill for Claude Code producing high-fidelity prototypes (Chinese docs). | 设计 | Reviewed |
| [体育数据技能集](https://github.com/machina-sports/sports-skills) | 面向体育场景的开源 agent 技能集：实时赛事数据获取、比赛结果预测、联赛与球员信息查询等 27 个技能，按主题分组，适合构建体育资讯与数据分析工作流。 | 效率 | Reviewed |
| [产品营销技能市场](https://github.com/stefanoskarakasis/Product-Marketing-Skills) | 产品营销（PMM）技能市场：包含定位、发布、竞争分析、客户研究、内容与销售赋能等 30+ 个代理技能与命令，覆盖产品营销全流程。 | 商业 | Reviewed |
| [任务闭环 Mission](https://github.com/tackeyy/mission) | 质量门禁驱动的自治任务闭环技能集：任务拆解、执行、验证与交付全程受质量闸约束，含 12 个技能，适合让代理在明确验收标准下长跑完成任务。 | 开发工具 | Reviewed |
| [人工评审 Human-Review](https://github.com/victorrentea/human-review) | 为 Claude Code 设计的人工评审技能：自动汇编一页式变更摘要与风险清单，帮助人类评审者快速理解代理改动并给出批准或驳回意见。 | 开发工具 | Reviewed |
| [UI 间距规范](https://github.com/buidangminh23/spacing-skill) | 反拥挤间距技能：一条经过打磨的 UI 间距规范，让代理生成的界面保持呼吸感与一致的视觉节奏，适合嵌入任何前端工作流。 | 设计 | Reviewed |
| [旅行规划 Trip-Planner](https://github.com/skywain/trip-planner-skill) | AI 旅行规划技能：按天数、预算与偏好生成可执行的行程单，覆盖交通、住宿与景点编排，兼容 Claude Code / Codex 等多种代理工具。 | 效率 | Reviewed |
| [Reddit 浏览器自动化](https://github.com/beggarticksarthurtatum121/reddit-skills) | 基于真实浏览器与账号的 Reddit 自动化技能集：浏览、检索、发帖与互动等 6 个技能，强调以用户本人身份合规操作。 | 自动化 | Reviewed |
| [PubMed 引用核验](https://github.com/docsor1212/pubmed-verifier) | PubMed 文献引用批量核验工具：对 AI 生成的引用逐条比对 PubMed 数据库，检测编造与张冠李戴，降低科研写作中的幻觉引用。 | 科研 | Reviewed |
| [科研严谨执行](https://github.com/bsq415/research-rigor-skill) | 人类主导、证据门控的科研全周期执行技能：从问题定义、文献综述到实验设计与结论输出，每一步都要求可验证证据支撑。 | 科研 | Reviewed |
| [验收测试生成 Qikly](https://github.com/gal-a/qikly) | 从验收标准生成测试套件的技能：先按验收条件生成测试用例，再驱动实现直至全部通过，覆盖单元与集成两层。 | 测试 | Reviewed |
| [发布视频生成](https://github.com/Kimeur/motion-launch-videos) | 发布视频批量生成技能集：从简短的产品说明生成脚本、分镜与成片，循环产出可发布的宣传视频，共 12 个技能。 | 设计 | Reviewed |
| [数据经纪商除名](https://github.com/danieljustus/symaira-eraseme) | 自动化数据经纪商除名技能：批量向数据经纪商提交除名请求、跟踪处理进度，帮助清理个人数据痕迹，强化隐私保护。 | 安全 | Reviewed |
| [Compose 开发助手](https://github.com/yschimke/compose-ai-tools) | 面向 Jetpack Compose 的代理辅助技能：UI 组件生成、代码规范检查等 3 个技能，帮助代理写出符合 Compose 最佳实践的 Android 界面代码。 | 开发工具 | Reviewed |
| [pstack 技能集 T3 版](https://github.com/creedants/pstack-t3) | Lauren Tan 的 pstack 代理技能集向 T3 Code 的移植版：覆盖前端工程、产品思维与协作流程等 130 个技能，任何模型都能取用。 | 合集 | Reviewed |
| [工程品味合集 Shadowclone](https://github.com/theonly1me/shadowclone) | 把个人工程品味带进每一个编码代理的技能合集：代码风格、架构取舍与评审标准等 44 个技能，来自一线工程师的实战沉淀。 | 合集 | Reviewed |
| [上下文桥 Open-Bridge](https://github.com/bks-lab/open-bridge) | 给编码代理的上下文桥技能集：以纯 Markdown 沉淀工作约定、决策与领域知识等 41 个技能，免去反复向代理解释背景。 | 开发工具 | Reviewed |
| [循环工程套装 IDD](https://github.com/kurone-kito/idd-skill) | 循环工程（Iterative Development Discipline）自动化配置技能套件：4 个技能帮助代理建立稳定的需求-实现-验证迭代循环。 | 开发工具 | Reviewed |
| [技能共进化 NBLane](https://github.com/Marsjunwang/nblane) | 人 + 代理 + 团队技能共同进化平台：以纯文本沉淀技能资产，5 个技能覆盖个人与团队层面的技能演化与复用。 | 效率 | Reviewed |
| [便携技能包 Claude-Abo](https://github.com/Bank848/Claude-Abo) | 便携式 Claude Code 配置模板：66 个经过实战验证的技能开箱即用，一条命令即可在新机器上复原完整工作环境。 | 合集 | Reviewed |
| [逆向工程代理 Rea](https://github.com/morluto/rea) | 逆向工程代理技能：从应用行为入手向下还原实现细节，2 个技能覆盖行为观测与结构还原，适合学习与兼容性分析。 | 安全 | Reviewed |
| [星际智能系统](https://github.com/frankxai/Starlight-Intelligence-System) | 给整个 AI 舰队一个共享大脑：带证明的记忆、知识组织与跨会话延续等 69 个技能，适合多代理长期协作场景。 | 效率 | Reviewed |
| [代理技能百科 RSC](https://github.com/ericrisco/rsc-harness) | 超大体量的代理技能百科：开发、写作、测试、运维等方向 271 个技能，按需取用，适合作为团队技能弹药库。 | 合集 | Reviewed |

<!-- registry-table:end -->

Inclusion criteria and review process: [CONTRIBUTING.md](CONTRIBUTING.md); the entry contract is defined in `registry/registry-schema.json` and enforced in CI. The 3 bundled plugins (browser-cdp / github-project-manager / novel-writing-suite) live in the `bundled/` directory and ship with the repo — see the short command above.

## Contributing a plugin

Want your skills in this marketplace? Three steps:

1. Make sure your repository has discoverable `SKILL.md` files (criteria: complete structure, not archived, actively maintained; awesome lists, platform tools, and CLI bodies are not accepted);
2. Open an issue or PR adding one static entry to `registry/plugins.json` (repo / displayName / category / description / trust / sourceCommit, etc. — contract in `registry/registry-schema.json`);
3. CI fills in the dynamic fields and validates the contract; after human review and merge, the daily artifact build and this README table pick it up automatically.

## Screenshots

| Local Skills | Curated marketplace |
| --- | --- |
| ![Local Skills view](docs/screenshots/home-local.png) | ![Curated marketplace view](docs/screenshots/home-curated.png) |

Permission and compatibility details shown before installation:

![Pre-install details](docs/screenshots/detail-four-questions.png)

> Screenshots are captured with synthetic data. Available actions and results depend on your local environment and the source plugin.

## Safety notes

- The marketplace checks ownership and content changes before removing a managed Skill; Skills installed elsewhere are not supposed to be removed by this marketplace.
- **Declared permissions and a risk preview are not a runtime sandbox.** Third-party Skills can still execute their own logic. Review their source and origin before installation.
- `安全模式-只开网页.cmd` is for browsing without registering the marketplace. `撤销注册.cmd` removes the marketplace registration from WorkBuddy; this is different from uninstalling Skills.

## Platform status

| Platform | Status |
| --- | --- |
| Windows 10/11 | Primary development and use environment; the repository documents a WorkBuddy 5.7.6 panel test |
| Linux | CI hard gate on all three platforms: full isolated selftest (789 checks) + pytest + POSIX semantic smoke + wheel build + ui-smoke; real WorkBuddy host integration not yet verified |
| macOS | CI hard gate on all three platforms: full isolated selftest (789 checks) + pytest; real fcntl/symlink semantics exercised by CI; real WorkBuddy host integration not yet verified |

## Documentation and community

- [Detailed usage, configuration, CLI, architecture and self-check commands](ADVANCED_GUIDE.md)
- [FAQ](docs/FAQ.md)
- [Plugin package specification](docs/plugin-spec.md)
- [Security policy](SECURITY.md)
- [Contributing guide](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)
- [Report a bug or suggest an improvement](https://github.com/zjs105910/workbuddy-market/issues)

Feedback, reproducible bug reports, documentation improvements, and pull requests are welcome. Licensed under MIT.
