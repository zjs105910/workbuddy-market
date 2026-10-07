# Provider API —— 设计稿（未实现）

> 状态：**设计稿**。落地排在 R4（installer/registry 拆分完成）之后。
> 来源：2026-10-07 外部评审第 4/6/7/16/17 节。

---

## 1. 要解决什么

现在「插件从哪来」有两种互不相通的写法：`localPlugins`（本机 skill 打包）和
`remoteSources`（写死在 market.config.json 里的 GitHub 仓库 + 手工维护的
stars/skillCount/verifiedAt 快照）。问题：

- 加一种来源（Gitee / URL / ZIP / 官方 Registry）就要改打包与状态代码；
- stars 这类动态数据写死在配置里会过期，还得手工更新；
- 「验证状态」只是展示字段，没有与来源、校验和形成闭环。

## 2. Provider 接口

```python
class PluginProvider:
    """插件来源的统一抽象。每个来源一个实现，市场状态页聚合它们的输出。"""

    name: str                                  # "local" / "github" / "registry" / ...

    def list(self) -> list[ProviderEntry]:     # 该来源当前能提供的插件清单
        ...
    def metadata(self, plugin_id: str) -> ProviderMeta:   # 单插件详情（含动态字段）
        ...
    def fetch(self, plugin_id: str, version: str | None,
              dest: Path) -> FetchResult:      # 下载/复制到暂存目录；返回校验和
        ...
    def search(self, query: str) -> list[ProviderEntry]:   # v1 允许 = list() 后内存过滤
        ...
```

要点：

- `fetch()` 只负责把内容放进**暂存目录**，安装语义（事务、ownership、校验）
  仍由内核 `install_local_plugin` 一条路走 —— 输入边界只留一处（约定 14）；
- `metadata()` 返回动态字段（stars / latestRelease / updatedAt），**永不落盘
  进 market.config.json**；配置里只留静态身份（repo、category、description）；
- 远端执行器：GitHub 来源的 fetch 目前仍委托 ghpm（`GHPM_PY`），Provider 是
  包在它外面的一层适配，不是替代 —— ghpm 的事务/回滚/镜像回退继续复用。

## 3. market.config.json 的瘦身

```jsonc
{
  "localPlugins":   [ ... ],              // 语义变为 LocalProvider 的输入
  "remoteSources":  [ { "repo": "anthropics/skills", "category": "官方" } ],
                                            // 只留静态身份；stars/verifiedAt 删除
  "packaging": ..., "trash": ...
}
```

`verifiedAt` 的语义由「手工写进配置的日期」升级为 Provider 层的验证缓存
（落 STATE_HOME 的 metadata 缓存，带 TTL），配置文件不再承担易变数据。

## 4. 验证状态（正式化现有 verifiedAt）

```jsonc
"verification": {
  "status": "verified",          // official | verified | community | unverified | blocked
  "verifiedBy": "workbuddy-market",
  "method": "static-analysis",   // static-analysis | checksum-match | manual
  "verifiedAt": "2026-10-06",
  "checksum": "<tree_hash>"
}
```

- `official`：WorkBuddy/本市场作者出品；`verified`：来源与校验和双重核对过；
  `community`：仅来源可考；`unverified`：默认态；`blocked`：本地拉黑名单。
- 校验和与上次不一致 → 自动降级 `unverified` 并在网页显眼告警；
  `blocked` 由用户手工维护（STATE_HOME 本地文件，不进配置）。

## 5. 未来：Registry Index（评审第 17 节）

Registry 就是一个静态 GitHub 仓库（registry/index.json + plugins/*.json），
Provider 实现里最薄的一种：`list/metadata` 读 index，`fetch` 交给 GitHub
raw/ghpm。不需要服务器，先有生态再有基础设施。
