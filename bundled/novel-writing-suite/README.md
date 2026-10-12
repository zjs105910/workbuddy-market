# 网文创作套件

中文网文创作全流程：扫榜选题、长篇与短篇写作、长篇与短篇拆文、多视角审查、去 AI 味、逆向导入、封面生成，外加工具集基础设施部署。12 个互相路由的 skill 组成一条完整流水线，入口是 story。

- 市场：`wb-local-market`
- 版本：`1.0.0`
- 分类：写作

## 包含的 skill

- **story** v1.0.0 — 网络小说工具箱主入口。根据用户需求自动路由到对应 skill，并可管理作者习惯、启动本地 Dashboard。触发方式：/story、$story、/story dashboard、/网文、「我想写小说」「记住我的写作习惯」「打开工作台」「
- **story-setup** v1.3.2 — 网文写作工具集基础设施部署与检查。为 Claude Code / OpenCode / Codex / Google Antigravity / ZCode / OpenClaw / Reasonix 提供内置适配；Web AI / 通用 
- **story-long-write** v1.0.0 — 长篇网文规划与写作。支持只讨论结构、只写大纲或指定细纲，明确要求正文后再写章节。触发方式：/story-long-write、/写长篇、「帮我开书」「定设定」「出卷纲」「规划剧情」「写大纲」「补细纲」「日更」「续写」「继续写」「修改第X章」
- **story-short-write** v1.0.0 — 短篇网文写作。辅助短篇小说创作，从构思到成稿，聚焦情绪拉扯与节奏把控。触发方式：/story-short-write、/写短篇、「帮我写一篇短篇」「写个盐言故事」。
- **story-long-analyze** v1.0.0 — 长篇网文拆文。保留黄金三章、逐章摘要、剧情、情绪、节奏、角色、设定和文风接口，以连续章节块完成因果、双时间线、关系与三维节奏分析；兼容旧成果直接使用、按需增强和断点续跑。含可选三层灵感库管道（灵感库、跨书灵感聚合、更新灵感库）。触发方式：/
- **story-short-analyze** v3.1.0 — 短篇网文拆文。拆解爆款短篇小说（番茄短篇 / 故事会 / 知乎盐选 / 追妻 / 世情 / 重生 / 虐渣等通俗题材）的故事核、结构、情感线、反转设计、写作手法、共鸣层次。单一全量拆解管道：跑完 Stage 2-6 产出完整拆文报告，落盘到
- **story-long-scan** v1.0.0 — 长篇网文扫榜。分析起点、番茄、晋江等平台排行榜数据，提炼市场趋势与热门题材。触发方式：/story-long-scan、/长篇扫榜、「长篇什么火」「起点排行」。
- **story-short-scan** v1.0.0 — 短篇网文扫榜。分析知乎盐言、七猫、黑岩、点众等平台热门短篇数据，捕捉风口题材。触发方式：/story-short-scan、/短篇扫榜、「短篇什么火」「知乎故事排行」。
- **story-review** v1.1.1 — 多视角对抗式审查。full/lean 模式在已部署 reviewer agents 时并行 spawn；缺失/异常 agents 或 spawn 失败时自动降级 solo，参考文件不可读时使用内置 rubric fallback。触发方式：
- **story-deslop** v1.0.0 — 网文去AI味。检测并清除文本中的AI写作痕迹，让文字回归自然、非模板化。触发方式：/story-deslop、/去AI味、「去AI味」「这篇太AI了」「网文去AI味」。
- **story-import** v1.0.0 — 逆向导入已有小说。将已写好的小说（半成品或完本）反向解析为标准项目目录结构，兼容 story-long-write / story-short-write 后续写作流程；内部复用 story-long-analyze / story-sho
- **story-cover** v1.0.0 — 小说封面生成。根据书名、作者名自动分析题材风格，调用 GPT-Image-2 生成含标题和署名的专业级网文封面；Codex CLI 优先使用内置 ImageGen，无需单独 API Key。触发方式：/story-cover、/封面、「帮我

---

此文件由 `launcher.py --sync` 依据 `market.config.json` 自动生成，请勿手改。
