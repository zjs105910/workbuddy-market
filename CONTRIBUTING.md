# 贡献指南

感谢你考虑为 WorkBuddy Market 贡献代码、文档或插件收录建议。欢迎先从修正文档、复现问题或完善测试开始。

## 动手之前

1. 阅读 [项目首页](README.md)、[详细使用指南](ADVANCED_GUIDE.md) 与 [安全策略](SECURITY.md)。
2. **改行为前先复现问题**：提供可重复的步骤或测试用例，避免只按直觉修改。
3. 如果涉及内核模块迁移，请先查看 `docs/开源重构方案.md` 中的依赖顺序。
4. 尽量把纯重构与行为变化拆成不同 PR，便于审查与定位回归。

## 环境要求

- Python 3.10+
- 运行时使用 Python 标准库；测试额外需要 pytest（开发可选依赖）
- Windows 是主要实测环境；Linux 有 CI 与部分语义测试；macOS 尚不代表真实 WorkBuddy 宿主已验证

安装开发测试依赖：

```bash
python -m pip install -e ".[dev]"
```

## 本地验证

提交前，请在项目根目录、与你的改动相符的环境里运行：

```bash
python -m py_compile market_core.py market_server.py launcher.py selftest.py src/workbuddy_market/*.py scripts/*.py
python -m ruff check market_core.py market_server.py launcher.py selftest.py src/ scripts/ tests/
python selftest.py
python -m pytest tests/ -q
python scripts/validate_registry.py registry/plugins.json
python scripts/privacy-audit.py
python scripts/check_dup_sync.py
```

其中 ruff 规则集钉死在 `pyproject.toml` 的 `[tool.ruff.lint]`（未用导入/变量、未定义名、裸 except、分号语句等真实缺陷类），CI 同款门禁见 `.github/workflows/ci.yml` 的 `lint` job；未安装时可 `python -m pip install ruff==0.17.0` 或 `pip install -e ".[dev]"`。

`check_dup_sync.py` 管两组协议约束下的必然重复：bundled 共享助手脚本（per-skill 安装协议下不能共享目录，改一份必须同步所有副本）与 plugins/ ↔ bundled/ 三个自有插件（后者只在有 plugins/ 个人目录的本机有效，CI 自动跳过）。改了 `bundled/` 里任何技能内容时跑一遍。

其中 `selftest.py` 默认使用隔离临时目录；`--real` 是面向现有环境的只读检查，不应在普通回归中替代隔离自检。

如果改动了前端、安装流程或关键 UI 交互，还应运行浏览器门禁：

```bash
python -m pip install playwright
python -m playwright install chromium
python scripts/ui_smoke.py --ci
```

`--ci` 是严格模式：Playwright 缺失或核心检查被跳过都会失败。若当前环境不能运行某项检查，请在 PR 中写明原因与尚未验证的部分，不要把未运行写成通过。

在发布或大范围改动前，还可运行完整历史隐私审计：

```bash
python scripts/privacy-audit.py --history
```

## 提交规范

- 破坏性操作必须 fail-closed（扫描失败不等于目录为空）。
- 不要用廉价指纹作为安装或卸载判定；遵守 `classify_skill` 的 `purpose` 机制。
- 事务、恢复与 fail-closed 语义的变更必须单独说明风险、探针证据和回滚路径。
- 不要提交真实用户的 Skill 内容、本机私有配置、令牌、私人路径或未经脱敏的日志。
- 修改插件协议时，先更新协议文档并说明向后兼容性。
- 如修改版本号或自检契约，请同步更新 `src/workbuddy_market/version.py`、`selftest.py` 对应盯防和相关文档；不要为让测试变绿而删除有效的回归断言。

## 测试怎么写

新增用例请优先放入相关的 `tests/` 单元测试，涉及核心不变量时同步补充 `selftest.py` 对应章节。使用现有的 `ck` / `section` / `prepare_fixture` 基础设施。包内依赖通常通过 `workbuddy_market.<module>` 命名空间调用，patch 时请确认目标位置。

## 协议与设计

- 插件协议、Provider 与 Lockfile 的设计材料见 `docs/protocol/`。
- 使用者问题先查 [FAQ](docs/FAQ.md)；安全漏洞请按 [SECURITY.md](SECURITY.md) 中的私密渠道报告，不要公开发布可利用细节。
- 提交 PR 时请使用仓库的 PR 模板，说明行为变化、验证结果和未覆盖的风险。
