# WorkBuddy Market

**简体中文** · [English](README_EN.md)

[![CI](https://github.com/zjs105910/workbuddy-market/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/zjs105910/workbuddy-market/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](pyproject.toml)
[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**给 WorkBuddy 用的本机优先插件市场。** 将本机 Skills 打包成插件，在精选社区目录或 GitHub 中查找技能；安装前查看来源、权限声明和兼容性，再通过哈希校验与可恢复事务完成安装、更新和卸载。

*A local-first plugin marketplace for WorkBuddy: package local Skills, explore community and GitHub sources, review declared permissions and compatibility, and manage installs through hash verification and recoverable transactions.*

## 30 秒了解它

- **管理自己的 Skills**：将本机技能打包、同步，并注册到 WorkBuddy 插件面板。
- **发现社区技能**：浏览精选目录，也可以搜索 GitHub 上的公开仓库。
- **安装过程更可追溯**：安装前有来源与风险预览；支持内容校验、事务恢复和回收站。
- **本机优先**：网页服务只监听 `127.0.0.1`；你的私有市场配置和本机技能内容不随仓库提交。

## 快速开始（Windows）

要求：Python 3.10+、Git。想先体验网页，不改动 WorkBuddy 配置，推荐从安全模式开始。

```powershell
git clone https://github.com/zjs105910/workbuddy-market.git
cd workbuddy-market
.\安全模式-只开网页.cmd
```

启动后打开本机地址（默认 `http://127.0.0.1:8777/`）。**请保持启动窗口打开**；结束时回到窗口按 `Ctrl+C`。

已经准备好要接入 WorkBuddy 时，再运行 `一键启动.cmd`。首次初始化的交互向导中，**直接回车是只浏览**；只有明确输入 `2` 才会请求注册到 WorkBuddy。注册前仍会进行打包与自检前置检查。

不会使用命令行？克隆仓库后，也可以在资源管理器中双击 `安全模式-只开网页.cmd`。想了解其他启动参数、插件配置或 CLI，请看[详细使用与技术参考](ADVANCED_GUIDE.md)。

## 看看界面

| 本机技能 | 精选市场 |
| --- | --- |
| ![本机技能管理界面](docs/screenshots/home-local.png) | ![精选社区插件界面](docs/screenshots/home-curated.png) |

安装前的来源、权限与兼容性预览：

![安装前详情预览](docs/screenshots/detail-four-questions.png)

> 截图由项目脚本使用合成数据生成。实际可用操作会根据本机环境与插件来源有所不同。

## 安装前请知道

- 卸载时会检查插件是否由本市场管理、内容是否被修改；不属于本市场管理的技能不会被随意删除。回收站与事务恢复用于降低误操作影响。
- **权限声明和风险预览不是运行时沙箱。** 第三方 Skill 仍可能执行其自身逻辑；安装前请核查来源与内容，不要仅凭“精选”标签就盲目信任。
- 首次只想体验网页：使用 `安全模式-只开网页.cmd`。想撤销 WorkBuddy 中的市场注册：使用 `撤销注册.cmd`。这与卸载已经安装的技能是不同操作。

## 平台验证状态

| 平台 | 当前状态 |
| --- | --- |
| Windows 10/11 | 主要使用与验证环境；仓库文档记录了 WorkBuddy 5.7.6 面板实测 |
| Linux | 有 CI 与部分自动化检查；尚未验证真实 WorkBuddy 宿主集成 |
| macOS | 尚未验证 |

## 文档与社区

| 你想做什么 | 入口 |
| --- | --- |
| 配置市场、使用命令行、了解安全边界 | [详细使用与技术参考](ADVANCED_GUIDE.md) |
| 了解首次启动、收录和恢复问题 | [FAQ](docs/FAQ.md) |
| 了解插件包协议与校验 | [插件包协议](docs/plugin-spec.md) |
| 报告安全问题 | [安全策略](SECURITY.md) |
| 提交代码或改进文档 | [贡献指南](CONTRIBUTING.md) |
| 查看版本变化 | [CHANGELOG](CHANGELOG.md) |
| 提交 Bug / 功能建议 | [GitHub Issues](https://github.com/zjs105910/workbuddy-market/issues) |

欢迎 Star、提 Issue、提交可复现的问题与 PR。项目采用 MIT License。
