# WorkBuddy Community Marketplace（自动发布分支）

本分支是 [WorkBuddy Market](https://github.com/zjs105910/workbuddy-market)
精选社区市场的 **原生 git 市场快照**，由 CI 每日从人工审核的
`registry/plugins.json` 自动重建，内容与
[`marketplace` Release](https://github.com/zjs105910/workbuddy-market/releases/tag/marketplace)
的 zip 完全同源。

## 一键接入（CodeBuddy Code / WorkBuddy）

```
/plugin marketplace add https://github.com/zjs105910/workbuddy-market.git#marketplace
```

然后 `/plugin` 浏览，或：

```
/plugin install <插件名>@workbuddy-community-market
```

## 取舍说明

这条路是**技能分发快照**：按审核固定的 sourceCommit 生成，不含安装前四问、
所有权分级与可恢复卸载。要完整安全链路请用完整版 WorkBuddy Market。
勿直接改本分支任何文件——每日重建会覆盖；收录建议请给主仓库提 issue/PR。
