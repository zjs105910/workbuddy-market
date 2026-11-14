# 这一次实跑遇到了什么

记录用途：下次实跑时对照，判断遇到的问题是老问题还是新出现的。
不记录顺利跑过的步骤——正常执行不构成信息。

版本：`0e2fdff`（v0.4.2）+ 本次修复。原著与产物见同目录。

## 需要人替系统解决问题的地方（6 处）

| # | 阶段 | 类型 | 事情 |
|---|---|---|---|
| 1 | novel-analyze S1 | 流程停靠 | SKILL.md 规定快评后必须问创作者是否继续全量拆解 |
| 2 | novel-analyze S0 | 文档缺口 | `_progress.md` 被列为 S0 产出，但每个阶段都要更新它，而 publish 规定一个输出路径只能有一个 owner；文档没说它该用哪个 artifact-id。本次自行开了 `source-analysis:progress` |
| 3 | write | 模板缺陷 | `episode-card.json` 模板投影了 5 个分集地图已删的字段，`beats.jsonl` 的 `payoff_refs` 默认也指向已删字段。照抄模板会产生 6 个悬空指针。**已在本次修复中改掉** |
| 4 | write | 工具缺陷 | 配音本装不下 `[VO]`，`channel` 枚举里的 `VO`/`OS` 结构上不可达。**已修复** |
| 5 | write | 内容修复 | `screenplay_index` 报 `invalid_voice_tag_syntax`——`[VO]` 的说话者字段不允许带括号提示，而同样的提示写在普通对白行里合法 |
| 6 | write | 工具缺陷 | 时长估算把 `[VO]` 计零秒，本集漏计 30.8 秒（报 64.0s，实为 94.8s）。**已修复** |

## 检查器报错（7 处，全部自修）

| 阶段 | 报错 | 修法 |
|---|---|---|
| novel-analyze S2 | ch-3 的「功能：」计数比情节点多 1 | 情节点的功能文本里含「功能：」四字，改写措辞 |
| assets | 角色记录缺 `creator_acceptance` | 补上 |
| assets | `pending` 不在验收状态枚举内 | 改成 `proposed`；各阶段状态词不一致，见下 |
| image-prompts | `location_plate` 也必须有 `variant_ref` | 补建 `设定集/location-views.jsonl` |
| storyboard（编辑测试） | 4 个新块无人认领 | 重切末段，新增两镜 |
| storyboard（本次修订） | `SHT21_BLOCK_NOT_IN_SCREENPLAY`（v0.5.0 起改称 `SHT01_BLOCK_NOT_IN_SCREENPLAY`），点名 `SHOT-EP001-017` | 改写倒计时字幕后旧块号退役，把 4 处下游引用重指到新块号——**这正是索引机制该有的表现** |
| write | `invalid_voice_tag_syntax` | 见上表第 5 条 |

## 仍未处理的观察

- **验收状态词各阶段不一致**：analyze / develop 层用 `pending`，assets 层的枚举是
  `accepted` / `proposed` / `pending_choice`，写 `pending` 会被拒。
- **`format.episode_count` 没有写入路径**，但全套件没有任何读者——它可以留空。
