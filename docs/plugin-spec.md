# WorkBuddy Market Package 协议（v0.2，2026-10-08）

> 状态：**v0.2 —— 六项开放问题已冻结（见 §6），`pack` / `verify` 纯函数
> 层已实现（`workbuddy_market/packaging.py`，selftest 第 30 节盯防）**。
> 安装链路接入（registry 带 manifestHash → 安装走 verify）是下一步。
> schema 版本独立于市场版本号演进（`schemaVersion` 从 1 开始，
> 向后兼容的字段新增不升版）。

## 1. 动机：第四层抽象

本市场目前实际处理三层概念，职责挤在一起：

| 层 | 现状载体 | 问题 |
|---|---|---|
| WorkBuddy Skill | 目录 + SKILL.md | WorkBuddy 原生协议，市场不控制 |
| WorkBuddy Plugin | market.config.json 的 localPlugins | 市场私有配置格式，无完整性 / 依赖语义 |
| GitHub Repository | ghpm 的 repo 源 | 是「来源」，不是「产物」——同一 repo 的内容随上游漂移 |

Marketplace 要分发的是**第四层**：Market Package —— 一个
可校验、可复现、与来源解耦的分发单元。它解决三个具体问题：

1. **可复现安装**：审核的是 commit A，用户装到的也必须是 A 的内容
   （v2.12 的 sourceCommit 固定只做到「漂移提醒」，产物本身仍取自上游）；
2. **完整性**：manifest 带内容清单与哈希，安装时逐项校验
   （v2.13 跨卷搬移的「结构校验」可升级为哈希校验）；
3. **依赖与元数据**：声明版本、平台、依赖、license，
   给未来 Quality Score 和依赖系统提供数据源。

## 2. 包布局

```
wbm-package/
├── manifest.json          # 唯一入口（见 §3）
├── skills/                # 一个或多个符合 WorkBuddy Skill 协议的目录
│   └── <skill-name>/
│       └── SKILL.md
├── README.md              # 可选，市场页展示
├── LICENSE                # 可选，SPDX 标识进 manifest
└── checksums.json         # 由打包工具生成，进 manifest.integrity
```

约束：

* `skills/` 内每个子目录必须有合法 `SKILL.md`（WorkBuddy 原生协议）；
* 包内**禁止**符号链接 / junction（沿用 v2.1 起的三道防线）；
* 除 manifest 外的一切文件都参与完整性校验（含 `skills/` 全部内容）。

## 3. manifest.json schema（草案）

```json
{
  "schemaVersion": 1,
  "id": "example-skill",
  "name": "Example Skill",
  "version": "1.2.0",
  "description": "Example WorkBuddy skill",
  "author": "Example Author",
  "license": "MIT",
  "skills": ["skills/example"],
  "minWorkBuddyVersion": "5.7.0",
  "platforms": ["windows", "linux", "macos"],
  "dependencies": {
    "skills": [{"id": "pdf-tools", "range": ">=1.2"}],
    "system": {"python": ">=3.10"},
    "workbuddy": ">=5.7"
  },
  "source": {
    "type": "github",
    "repo": "owner/repo",
    "ref": "abc123...",
    "fetchedAt": "2026-10-08T03:00:00Z"
  },
  "integrity": {
    "algorithm": "sha256",
    "manifest": "<对除 integrity 外全部 manifest 字节的 SHA-256>",
    "files": {"skills/example/SKILL.md": "<sha256>", "README.md": "<sha256>"}
  }
}
```

字段口径：

* `id`：全局唯一、`validate_id` 同规则（小写字母数字与连字符）；
* `version`：SemVer（`validate_version` 同规则）；
* `skills`：包内相对路径，**必须**以 `skills/` 开头且经
  `ensure_child` 语义约束在包内（路径穿越零容忍，与回收站索引同一纪律）；
* `platforms`：缺省 = 全平台；与本机不符时安装期警告（不是拒绝，
  「警告还是拒绝」见开放问题 4）；
* `dependencies`：v0.1 只**声明不解析**（P2 依赖系统落地前原样透传）；
* `source.ref`：打包时固定的 commit / tag；`ref` 缺失 = 不可复现包，
  注册表侧必须标 `unverified`；
* `integrity.manifest`：对 manifest 自身（去掉 integrity 字段）做
  规范化 JSON 序列化后哈希 —— 防止「改一个文件再同步改清单」绕过校验。

## 4. 与现有安全模型的衔接

| 现有机制 | 协议落地后的角色 |
|---|---|
| trust 三级（official/reviewed/external） | **独立于包内容**。95 分 / official 是对「谁审核的」的判定；integrity 是对「内容没被改过」的判定，两者正交（v2.12 已确立的原则，评分不得混淆） |
| sourceCommit / latestSha 漂移闸门 | `source.ref` 即 sourceCommit 的包级形态；闸门从「安装时比对上游」升级为「安装固定产物」 |
| 事务日志（tx_*） | 安装一个 Package = 安装 N 个 skill，事务粒度不变，manifest 进 tx 元数据 |
| 跨卷搬移结构校验（v2.13） | 校验口径从「路径+大小」升级为「逐文件 sha256」（包有清单，代价可接受） |
| tree_hash / 所有权快照 | 不变 —— 装完的 skill 在本机侧仍是普通 skill，所有权照记 |

## 5. 生命周期（ installer 视角）

```
fetch（provider: github/local/http → 不可变产物）
  → verify（manifest 自身哈希 → 逐文件哈希 → 链接防线 → 平台/版本检查）
  → stage（现有 _stage_skill 语义：暂存 → 校验 → 换位）
  → record（所有权 + tx，照旧）
```

verify 失败 = 整包拒绝，无半截状态（与「任何一步失败源目录原样保留」
同一纪律）。

## 6. 开放问题（v0.2 已全部冻结 ✅）

1. **产物从哪来** → ✅ **不可变 artifact（CI 构建）**。审核后由 CI
   构建产物并分发（release attachment / registry 登记 `packageHash`）；
   从源 repo 原地取 commit 的路径只作为过渡兼容。`pack` 的
   `source.ref` 固定来源 commit。
2. **规范化 JSON** → ✅ **UTF-8（无 BOM）+ 键按 Unicode 码位排序 +
   紧凑分隔符 `,` `:` + ensure_ascii=False + 末尾无换行**。
   实现见 `packaging.canonical_json()`；manifest 自哈希与
   `packageHash`（对「相对路径 → 文件哈希」映射的规范化序列化再哈希）
   都用这个口径。
3. **签名** → ✅ **v0.1 不做**。完整性由 sha256 清单承担，真实性由
   trust 三级 + source.ref 承担；`integrity.signature` 预留字段位，
   引入 GPG / sigstore 时升 schemaVersion。
4. **平台不匹配** → ✅ **默认拒绝，`force=True` 放行并记 warning**
   （与 `--allow-non-skill` 同一口径）。实现见 `verify_package(force=)`。
5. **ghpm 兼容** → ✅ **无 manifest 的安装走现有路径**，注册表/界面
   如实标注「无完整性清单」；不做格式转换。
6. **依赖解析时机** → ✅ **v0.1 声明不解析**：`verify_package` 只校验
   依赖声明形状（skills=[{id,range}] / system / workbuddy），
   冲突 / 循环检测等解析语义在依赖系统（P2）落地时另立文档。

## 7. 落地顺序（对应 v3-roadmap）

1. ~~冻结 §6 开放问题 → schema v1 定稿~~ ✅（2026-10-08，本文档 v0.2）
2. ~~`pack`：本地目录 → 合法 Package~~ ✅（`packaging.pack_package`：
   复制 + 链接拒绝 + 逐文件 sha256 + manifest 自哈希 + packageHash）
3. ~~`verify`：独立纯函数~~ ✅（`packaging.verify_package`：不可信输入、
   自哈希 → 逐文件 → **双向一致**（多一个未列出文件也算失败）→
   链接防线 → 路径穿越 → 平台 force 口径 → 依赖形状；
   selftest 第 30 节覆盖全部攻击面）
4. registry 接入：条目带 `packageHash` / `manifestHash`，安装走 verify
   链路（下一步）
5. 依赖系统（P2）另起。
