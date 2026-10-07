# 贡献指南

谢谢考虑贡献！这个项目目前处于「内核已稳、协议成形中」的阶段，
贡献前请先读一遍本文和 `README.md`，可以少走很多弯路。

## 动手之前

1. **先跑一遍自检**：`python selftest.py`（隔离模式，不碰真实环境）。
   全绿是任何改动的起点，也是终点。
2. **改行为之前先复现**。本项目有条铁律：评审/直觉给的结论要先用探针验证，
   历史上不止一次「看起来是 O(N²)」的结论被探针证伪。
3. **看 `docs/开源重构方案.md`**：模块拆分（R1-R8）有精确的函数级映射表和
   依赖顺序（config ← scanner ← packaging ← installer），别打乱。

## 环境要求

- Python 3.10+（无第三方运行时依赖，纯标准库）
- Windows 为主战场（msvcrt / junction / 大小写语义都在这上面踩过坑），
  Linux/macOS 的行为测试正在补

## 提交规范

- **拆分与行为变更分开**。一个 PR 里只做「搬代码」或「改行为」其中之一，
  混在一起出问题时无法归因。
- 破坏性操作必须 fail-closed（扫描失败 ≠ 目录为空）。
- 不许用廉价指纹做安装/卸载判定（`classify_skill` 的 `purpose` 机制）。
- 事务/恢复/fail-closed 语义一行都不许变，除非 PR 里单独说明并带了探针证据。
- 改版本号时同步：`src/workbuddy_market/version.py`、`selftest.py` 的
  `SELFTEST_VERSION`、README 的自检项数与对应章节。

## 自检怎么跑

```bash
python selftest.py            # 隔离模式（默认）：临时目录里造假 skill 走完整流程
python selftest.py --real     # 只读检查现网状态
python -m py_compile market_core.py market_server.py launcher.py selftest.py src/workbuddy_market/*.py
```

## 测试怎么写

新用例进 `selftest.py` 对应章节（或新建小节），使用现成的 `ck` / `section` /
`prepare_fixture` 基建。涉及模块注入的用例注意：包内部调用走
`workbuddy_market.<mod>` 命名空间，patch 目标要选对（见 selftest 第 19/24/25 节）。

## 协议与设计

- 插件协议 / Provider / Lockfile 的设计稿在 `docs/protocol/`，
  改协议先改文档、评审通过再动代码。
- 工程约定与历史踩坑记录见仓库根 `README.md` 各节。
