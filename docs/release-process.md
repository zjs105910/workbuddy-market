# 正式 Release 发布流程

正式 Release 是 WorkBuddy Market 本体的版本发布；仓库中 `registry-artifacts-*` 命名的日常 Release 用于发布社区插件不可变产物，不代表 WorkBuddy Market 本体版本。

## 发布前清单

- [ ] 确认 `src/workbuddy_market/version.py` 的 `MARKET_VERSION` 与 `CHANGELOG.md` 的最新版本段一致。
- [ ] 先将准备发布的代码合入 `main`，确认该 commit 的 CI 成功。
- [ ] 确认 `Demo video` 工作流成功，或在 Actions 手动重跑；检查 MP4、SRT、manifest 均存在。
- [ ] 检查 README 的快速开始、已知安全边界、平台验证状态与发行说明一致。
- [ ] 确认变更日志只写真实已实现的能力，不承诺未经验证的 WorkBuddy 宿主兼容性。

## 发布机制

发布由 `.github/workflows/release.yml` 负责。它只响应 `v*` tag；不会因普通 push 自动发布正式 Release。

1. 版本号只在 `src/workbuddy_market/version.py` 中维护。准备发 `X.Y.Z` 时，tag 必须是 `vX.Y.Z`，并且 `CHANGELOG.md` 必须有对应的 `## X.Y.Z` 段。本文统一用 `X.Y.Z` 作占位符，实际发布时替换成版本文件中的当前值。
2. 在已通过验证的 main commit 上创建并推送带注释的 tag：

```bash
git checkout main
git pull --ff-only origin main
git tag -a vX.Y.Z -m "WorkBuddy Market vX.Y.Z"
git push origin vX.Y.Z
```

`X.Y.Z` 只是一个占位符示例，不要照抄；永远以 `src/workbuddy_market/version.py` 的当前值为准。不要为了让工作流通过而随意更改版本或删减变更日志校验。

3. 工作流先在 Windows/Linux/macOS 与 Python 3.10/3.13 矩阵中运行语法、隐私、注册表契约、POSIX 语义冒烟、pytest；Windows 另跑完整隔离 selftest。
4. 验证通过后构建 wheel 与 sdist，使用 tagged source 录制演示视频，生成中文字幕与 manifest，计算 SHA-256 校验和。
5. 工作流用 GitHub CLI 创建正式 Release。发行页面包含 Python 包、MP4、SRT、manifest 和校验文件；版本专属说明摘自 `CHANGELOG.md`，并给出快速开始、Issue 与贡献入口。

## 发布失败如何处理

- 测试失败：不要强行发布。根据 Actions 失败步骤修复问题，推送修复 commit，再创建新的正确版本 tag 前确认 changelog/版本号同步。
- 视频失败：检查 Playwright、Chromium、FFmpeg、espeak-ng 依赖和录制脚本。演示脚本运行在隔离临时目录中，不能为了录制成功而复制真实用户 Skill 或配置。
- 若正式 Release 已创建，不要移动或重写已公开的 tag；修复后发布新的 patch 版本，并在说明中写清差异。
- Release workflow 会在 tag 与 `MARKET_VERSION` 不一致、没有对应 changelog 段、任一验证失败或演示录制失败时停止发布。

## 发布后让流量转化为使用与贡献

1. 将 Release 页面、MP4 和首页链接放在同一条社区公告里；首屏优先展示“安全模式试用”，不要让访客先读长技术文档。
2. 每条推广信息只留一个主动作：先试用；遇到阻塞再用 Issue 模板报告；确认项目有用后请求 Star；有能力的开发者再引导阅读贡献指南和提交 PR。
3. 回复问题时提供可复现步骤与已有 FAQ 链接；不要要求用户上传私人 Skill、token、真实配置或未经脱敏的日志。
4. 一周后查看 GitHub Insights 的流量、克隆、Issue、Star 和 PR 变化；用反馈改进上手流程，不要用虚假计数或自动化互刷。

相关入口：[项目首页](../README.md) · [演示录制说明](demo-video.md) · [变更日志](../CHANGELOG.md) · [贡献指南](../CONTRIBUTING.md)
