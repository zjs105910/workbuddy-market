# 工具书质量回归材料

这些材料全部为本次编写的**合成样本**，不来自群友的书，也不代表“项目四算/资源管道管理”的内容。它们用于防止筛选标准回退和测试评分器，不证明真实书籍蒸馏效果。

## 三关分流检查

`validation-cases.json` 包含 10 个样本，覆盖单处完整公式、无作者亲历故事的流程、标准清单、孤立金句、不完整公式、重复转述、来源冲突、无依据规则、范围越界及单处框架。

做行为测试时，执行者只获取 `source / candidate_type / candidate / task` 和新版三关说明，输出判定及引用理由；不能给其 `expected_decision / rubric`。评审者再对照后两项核查。测试执行前固定宿主/模型/预算；没有独立盲测时，只能标记为人工或主流程自查。

预期分布仅描述这组固定样本：4 verified、2 reference、3 needs_review、1 rejected。**不是实际书籍的通过率配额**。验收同时检查理由，不能只匹配 decision 字符串。

## 输出断言示例

`output-suite.json` 含 3 个合成输出任务：总额及单位、缺输入判停、流程状态。Prompt 为自包含规则，便于检验执行和评分；它不是 A/B 效益基准，不能用这三个样本声称 Skill 提升效果。真实 A/B 用例应从原书任务清单构建，业务请求不直接抄入整条解法。

先生成新的、空目录中的匿名任务包：

```sh
python3 scripts/run_output_evals.py prepare benchmarks/toolbook/output-suite.json --out /tmp/cangjie-toolbook-eval-unique --variants new_skill,without_skill
```

运行者按任务实际操作，把最终回答保存到 `<case_id>/<label>/output.md`，其他交付物留在该变体目录。`prepare` 不调用模型。然后评分：

```sh
python3 scripts/run_output_evals.py score benchmarks/toolbook/output-suite.json --outputs /tmp/cangjie-toolbook-eval-unique --mapping /tmp/cangjie-toolbook-eval-unique/mapping.json --out /tmp/cangjie-toolbook-eval-unique/report.md
```

输出不足会返回 2，并在汇总保留计划分母；断言失败返回 1。完整通过返回 0，只代表所配机械断言通过。

## 自动化回归与真实案例补充

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

单测检查评分器、资源编译、schema 和样本契约，不替代模型行为测试。群友原书问题仍需获得授权原文、原始候选与 rejected 记录，核对丢失位置，再跑新版补审和同任务输出对照。
