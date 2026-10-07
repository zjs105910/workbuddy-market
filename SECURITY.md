# 安全策略

## 支持的版本

| 版本 | 支持 |
| --- | --- |
| latest（main 分支） | ✅ |
| 更早的 tag / commit | ❌（请升级） |

## 报告漏洞

**请不要在公开 issue 里描述可利用细节。**

通过 GitHub 私密渠道报告：仓库页面 → Security → "Report a vulnerability"
（私密漏洞报告 / Security Advisories）。不要通过个人社交账号私信或公开渠道联系。

会在 72 小时内确认收到，修复时间视复杂度而定；修复发布前不公开细节。

## 本项目的安全模型（摘要）

这是一个**只监听 127.0.0.1** 的本地工具，但本地端口不等于安全入口，
因此默认防护包括：

- Web API 全部要求一次性口令（服务端注入页面，绝不落盘）+ Origin 校验；
- `/api/open/path` 只走白名单，不执行 shell；
- 请求体大小上限、连接超时、并发任务上限（JobLimiter + SingleFlight）；
- 任务超时 + 进程树击杀（POSIX 进程组 / Windows taskkill）；
- 安装/卸载走事务日志：凭证先于磁盘变更，失败可回滚，恢复只认内容指纹；
- 卸载按 ownership 分级：非本市场安装的内容**永不触碰**；
- 扫描 fail-closed：读不全时拒绝继续，绝不把「看不见」当「不存在」；
- 软链 / junction 一律不跟随（三层防线：打包、市场产物、安装）。

## 已知边界（诚实声明）

- 对**第三方 skill 内容**本身没有沙箱：skill 的实际能力由 WorkBuddy
  运行时决定。安装第三方插件前请自行审阅其内容与来源——这也是
  `plugins/` 不随本仓库分发、协议设计稿引入 permissions/verification
  的原因（见 `docs/protocol/`）。
- `GHPM_PY` 指向的本机远端任务执行器是可选组件，缺失时远端任务功能停用。
