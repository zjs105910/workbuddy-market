# Plugin Manifest v1 —— 设计稿（未实现）

> 状态：**设计稿**。本文只定协议，不含任何实现；落地排在 R3（config/scanner
> 拆分完成、manifest.py dataclass 就位）之后。定稿前允许改，定稿后 schemaVersion
> 只增不减。
>
> 来源：2026-10-07 外部评审第 2/3/5 节 + 开源重构方案 §3.1 manifest.py 预留位。

---

## 1. 要解决什么

现在的插件身份是「market.config.json 里的一条 localPlugins + 打包出来的目录名」。
这对单机工具够用，但对**市场协议**不够：

- 第三方无法产出「符合规范的插件」，因为没有规范可循；
- 插件没有独立于市场配置的身份（id、版本、许可证、来源、校验和）；
- `wb-market install <id>` 这类通用入口无从谈起。

## 2. 两个文件，两层身份

| 文件 | 归属 | 作用 |
| --- | --- | --- |
| `marketplace.json` | 市场仓库 | 这个市场**是**谁、**有**哪些插件（现由 `sync_packaging()` 生成，字段升级而非推倒） |
| `plugin.json` | 每个插件目录 | 插件自身身份，**随插件分发**，第三方可自行产出 |

## 3. plugin.json（Plugin Manifest v1）

```jsonc
{
  "schemaVersion": 1,

  "id": "novel-writing-suite",          // validate_id 同款规则；= 目录名
  "displayName": "网文创作套件",
  "version": "1.2.0",                   // validate_version 同款规则
  "description": "中文网文创作工作流",
  "description_en": "Chinese web-novel writing pipeline",

  "author": { "name": "zjs105910", "url": "https://github.com/zjs105910" },
  "license": "MIT",                     // SPDX 表达式；再分发的硬门槛（见 §6）
  "homepage": "",
  "repository": "https://github.com/owner/repo",

  "compatibility": {
    "workbuddy": ">=1.0",               // 语义化范围；v1 先只存不解析
    "python": ">=3.10"
  },

  "skills": [
    { "id": "story", "path": "skills/story" }   // path 相对插件根，安装前过 ensure_child
  ],

  "dependencies": [],                   // ["browser-cdp >=1.0.0"]，v1 先只存不解析

  "permissions": {                      // 声明式权限，见 §5
    "filesystem": ["~/.workbuddy/skills"],
    "network": ["api.github.com"],
    "process": false,
    "browser": false
  },

  "checksum": { "algorithm": "sha256", "value": "<tree_hash(插件根)>" }
}
```

### 校验规则（复用内核既有函数，不新造轮子）

- `id` → `validate_id(..., "id")`；与目录名做 `collision_key()` 碰撞检查；
- `version` → `validate_version(...)`；
- `skills[].path` → `ensure_child(插件根, 解析后路径)`，防穿越（约定 3 同源）；
- `checksum.value` → 安装时用 `tree_hash()` 复核，不一致按 install 失败计；
- 结构错误 → `ConfigError`（fail-fast），warning 只留给「能降级」的字段。

## 4. marketplace.json 的升级路径

现有 `sync_packaging()` 生成的 marketplace.json **保持向后兼容**，v1 起每条
plugin 记录内嵌其 plugin.json 的规范化副本（`"manifest": {...}`），并追加
`"manifestVersion": 1`。老字段（name/displayName/…）继续存在一个过渡期，
读取方优先 manifest。

## 5. 权限模型（v1 只声明，不强制）

v1 的 permissions 是**声明式**的：安装时原样展示给用户，不做运行时拦截。
理由：skill 的实际能力由 WorkBuddy 运行时决定，市场侧拦不住；但「装之前
明示它能干什么」本身就是供应链安全的第一道闸。运行时强制留给 WorkBuddy
本体协议成熟之后。

UI 展示约定：`process/browser: true` 的插件在网页卡片上必须出现显式警示徽标。

## 6. 许可证是硬门槛

`license` 字段缺省的插件**允许上架本机市场、禁止进入任何可分发的
marketplace.json**（plugins/ 已因同样理由不随 git 分发，这是协议层的延伸）。
来源不是自己的 skill，必须先确认原许可允许再分发。

## 7. 不做的事（v1 明确排除）

- 依赖解析（dependencies 只存不解析，R5 再做）；
- 签名（signature 字段预留位，算法与信任根定不了就不上）；
- 多版本共存（一个插件目录只有一个版本，回滚走 .trash 既有机制）。
