<div align="center">

# Distilly 路线图 🗺️

### 从 Colleague Skill / `colleague-skill`（原「同事 Skill」）到 Distilly —— 把人物蒸馏成可供 AI Agent 与兼容 Bot 复用的 Skill

<br>

我们从一个简单的想法开始：**离职的同事带走了知识，能不能留下来？**

两周内，13,000+ 人给了我们答案。

但社区告诉我们，这件事远不止同事 ——
你们蒸馏了罗翔、蒸馏了前任、蒸馏了自己、甚至蒸馏了虚拟角色。

**所以我们决定，把 Colleague Skill / `colleague-skill`（原「同事 Skill」）升级为 Distilly。**

任何人物，都可以被蒸馏成 `.skill`，供 AI Agent 与兼容 Bot 复用。

<br>

*最后更新：2026-08-23*

[**English**](../../ROADMAP.md) · [**Español**](ROADMAP_ES.md) · [**Deutsch**](ROADMAP_DE.md) · [**日本語**](ROADMAP_JA.md) · [**Русский**](ROADMAP_RU.md) · [**Português**](ROADMAP_PT.md) · [**한국어**](ROADMAP_KO.md)

</div>

---

## ✅ 已完成（v1.0）

这是我们已经做到的：

| 能力 | 状态 |
|------|:----:|
| `/distilly` 选择人物类型后的完整创建流程 | ✅ |
| 飞书全量自动采集（消息 + 文档 + 表格） | ✅ |
| 钉钉自动采集 | ✅ |
| Slack 自动采集 | ✅ |
| 微信聊天记录（SQLite 导出） | ✅ |
| 邮件 / PDF / 图片 / Markdown 导入 | ✅ |
| Work Skill + Persona 双模型架构 | ✅ |
| 对话纠正 & 增量进化 | ✅ |
| 版本管理 & 回滚 | ✅ |
| [社区 Gallery](https://titanwings.github.io/colleague-skill-site/) 99+ 技能 | ✅ |

---

## 🗺️ 路线图阶段

### 🏗️ Phase 1 —— 社区共建

> 13k stars 不应该只是数字。我们要让每个人都能参与进来。

**你会看到：**

- **GitHub Discussions 开放** —— 不用再在 Issue 里聊天了，我们会有专门的讨论区
- **`CONTRIBUTING.md` 上线** —— 清晰的贡献指南，第一次参与开源也能上手
- **`good-first-issue` 标记** —— 为新贡献者准备的入门任务
- **v1.0.0 正式发布** —— 第一个有版本号的 Release，告别"从 main 拉代码"的时代
- **公开路线图看板** —— 你在看的就是，但我们还会有 GitHub Projects 实时版

**你可以做：** 帮忙翻译文档、提交你的 .skill、在 Windows 上测试并反馈、帮忙整理 Issue

---

### 🌍 Phase 2 —— Distilly：不止同事

> Colleague Skill / `colleague-skill`（原「同事 Skill」）是起点，Distilly 是未来。

**已经上线：**

- **`/distilly` 作为统一正式入口** —— 选择 `colleague`、`relationship` 或 `celebrity`，再蒸馏任何人物，包括你自己
- **可移植的生成 Skill** —— 在受支持的 Agent 宿主中使用 `{character}-{slug}` 正式名称

**尚未上线的后续扩展：**

- **Gallery 分类升级** —— 同事 / 名人 / 亲密关系 / 虚拟角色 / 自我 / 元技能，按需浏览
- **更多数据源**
  - 企业微信支持
  - iMessage 自动读取
- **平台兼容性** —— Windows 兼容性修复

**你可以做：** 提交你想蒸馏的人物类型需求、贡献新的数据源采集器、参与 Gallery 分类设计讨论

---

### 🧩 Phase 3 —— 技能生态

> 当一个人变成了 skill，一群人能不能变成一个团队？

**我们在探索：**

- **多 skill 协作** —— `/meeting @zhangsan @lisi @wangwu`，三个人开会讨论一个议题
- **关系图谱** —— 定义 persona 之间的关系：谁和谁是搭档、谁和谁有张力
- **一键安装** —— 像装插件一样安装社区技能
- **主动进化** —— skill 定期自动从新数据源吸收知识，保持更新

**你可以做：** 提出你理想中的技能组合场景、参与分发机制设计讨论

---

### 🎨 Phase 4 —— 多模态：让 TA 活起来

> 现在的 .skill 只会说话。我们要让 TA 会发图、会发表情包、会说话、甚至会拍视频。

**第一步：视觉表达**
- 对话中自动发送 TA 风格的表情包和梗图
- 生成 TA 风格的"生活照" —— 今天 TA 会拍什么发朋友圈？
- 每个 skill 可以有自己的表情包库和图片资源

**第二步：语音**
- 用 TA 的音色说话 —— 基于会议录音、语音消息等素材克隆
- 对话中直接发送语音回复

**第三步：视频（探索中）**
- 短视频风格的"TA 的一天"
- 数字人 / 动画头像

**你可以做：** 分享你对多模态的使用场景想法、贡献表情包素材、测试语音克隆效果


## 💬 参与方式

| 方式 | 链接 |
|------|------|
| 提交你的 .skill | [Gallery PR](https://titanwings.github.io/colleague-skill-site/) |
| 讨论与提议 | [GitHub Discussions](https://github.com/titanwings/distilly/discussions)（即将开放） |
| 实时交流 | [Discord](https://discord.gg/NVX66RxWZv) |
| 报告 Bug | [Issue](https://github.com/titanwings/distilly/issues/new) |
| 贡献代码 | 看 `good-first-issue` 标签，或直接提 PR |

**我们尤其需要：**
- 🪟 Windows 用户 —— 帮我们测试和修复兼容性问题
- 🌐 多语言使用者 —— 帮忙翻译文档
- 🔧 数据源开发者 —— 写新的采集器（企业微信、Notion、Google Docs……）
- 🎨 设计师 —— Gallery 和网站需要你的审美

---

<div align="center">

**这份路线图属于社区。优先级会根据你们的反馈动态调整。**

有想法？来 [Discord](https://discord.gg/NVX66RxWZv) 聊，或者直接开一个 Discussion。

每一个 `.skill`，都是一段关系的延续。

</div>
