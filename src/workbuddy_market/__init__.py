"""WorkBuddy 本机插件市场 —— 内核包。

v2.8（R2）起，market_core.py 的实现按 docs/开源重构方案.md §3.1 陆续迁入本包：

* R2（v2.8）：paths / errors / fsutil / hasher / locking / logging（无状态纯函数）
* R3+（后续轮次）：config / scanner / sync / manifest / ownership / transactions /
  trash / registry / installer / uninstaller / state / diagnostics / cli / api

兼容入口仍是仓库根的 ``market_core.py``：它 re-export 本包的全部公开符号，
``import market_core`` 与 ``core.X`` 的用法（含 selftest 的属性注入）不受影响。
"""
