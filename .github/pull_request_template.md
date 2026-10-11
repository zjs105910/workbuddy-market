## What changed / 改动内容

<!-- 简述改了什么、为什么改，以及用户会感知到什么变化。 -->

## Change type / 改动类型

- [ ] Bug fix / 修复问题
- [ ] Feature / 新功能
- [ ] Refactor / 重构（尽量保持行为不变）
- [ ] Documentation / 文档
- [ ] Registry or protocol / 注册表或协议

## Validation / 验证结果

- [ ] `python selftest.py`
- [ ] `python -m pytest tests/ -q`
- [ ] `python scripts/validate_registry.py registry/plugins.json`（注册表相关改动）
- [ ] `python scripts/privacy-audit.py`
- [ ] `python scripts/ui_smoke.py --ci`（前端、安装流程或关键 UI 交互改动）
- [ ] Not run / 未运行的检查已在下方解释

**Commands and results / 命令与结果：**

<!-- 粘贴精简后的 PASS/FAIL 与关键报错；发布前先脱敏。 -->

**Skipped checks and reasons / 未运行检查及原因：**

<!-- 说明哪些未运行、原因是什么，以及尚未验证的风险。 -->

## Safety and compatibility / 安全与兼容性

- [ ] No secrets, private config, real user Skill contents, or unsanitized local paths/logs were added.
- [ ] Install/uninstall, transaction recovery, and fail-closed behavior were considered where relevant.
- [ ] Protocol, schema, version contracts, and related docs were updated where relevant.
- [ ] Destructive behavior is explicit, bounded, and recoverable where possible.

## Checklist

- [ ] The change is focused and has a clear user impact.
- [ ] Documentation and tests were updated where needed.
- [ ] This PR does not claim unsupported platform compatibility.
