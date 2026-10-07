# wb-market.lock —— 设计稿（未实现）

> 状态：**设计稿**。落地排在 R5（版本范围解析就位）之后。
> 来源：2026-10-07 外部评审第 9/10 节。

---

## 1. 要解决什么

现在「这个 skill 是谁装的、装的哪一版」记在 `.ownership.json`（STATE_HOME，
环境数据）。它回答的是**安全边界**问题：卸载时能不能动这个目录。

它不回答**复现**问题：「我今天装出来的这套插件，明天在另一台机器上原样
再装一遍」——版本会漂、校验和没留痕。lockfile 补的就是这一块。

## 2. 三个文件各司其职

| 文件 | 位置 | 回答的问题 |
| --- | --- | --- |
| `marketplace.json` | 仓库（产品） | 市场里**有什么** |
| `market.config.json` | 仓库（行为） | 本机**怎么**打包/清理/校验 |
| `wb-market.lock` | 仓库或工作目录 | 本机**实际装了哪个版本、校验和是多少** |

## 3. 格式

```jsonc
{
  "schemaVersion": 1,
  "marketId": "wb-local-market",
  "lockedAt": "2026-10-07T06:00:00+08:00",
  "plugins": {
    "novel-writing-suite": {
      "version": "1.2.0",
      "source": "local",                    // local | github:<owner/repo> | registry:<name>
      "skills": { "story": "<tree_hash>" }, // skill 级校验和（精确到可逐个核对）
      "sha256": "<插件根 tree_hash>"
    },
    "browser-cdp": {
      "version": "1.0.0",
      "source": "github:vercel-labs/agent-browser",
      "skills": { "agent-browser": "<tree_hash>" },
      "sha256": "<...>"
    }
  }
}
```

## 4. 语义

- **生成**：`wb-market lock`（或打包成功后自动刷新）。数据全部来自
  ownership + tree_hash 现算，lockfile 本身永远只是**快照**，不是权威；
- **消费**：`wb-market install --locked` 按锁内版本安装，版本对不上即失败
  （宁可失败也不「差不多」）；每装完一个立即复核 sha256；
- **与 ownership 的关系**：ownership 仍是安装/卸载的唯一权威（安全边界）；
  lock 只读 ownership 与磁盘，绝不反向写。两处不一致时以 ownership 为准并告警；
- **位置**：默认仓库根（跟市场走）；`.gitignore` 不排除它——这正是它和
  运行时状态文件的本质区别，它应该被提交。

## 5. 不做的事（v1 明确排除）

- 版本范围解析（`>=1.0,<2.0`）：lock 里只有**精确**版本；范围解析属于
  manifest 的 compatibility/dependencies，是另一层；
- 多环境矩阵（不同机器不同锁）：一台机器一份锁，够用。
