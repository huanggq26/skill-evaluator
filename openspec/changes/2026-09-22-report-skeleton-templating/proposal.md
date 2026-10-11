## Why

阶段 4 两份报告（`benchmark_report.md`、`problem_report.md`）的**章节骨架仍硬编码在脚本内**：
评分报告由 `generate_outputs.py` 的 128 行 f-string 拼出，问题报告由 `assemble_findings.py`
逐行拼接 157 行。`assets/benchmark_report.template.md` 与 `assets/problem_report.template.md`
虽然存在，但**生成流程并未读取它们**——模板是摆设。

由此产生的后果（均已实测）：

- 章节编号错乱：曾出现两个 `## 7.`（v14 实证，已于 v14 修）、`## 3.1` 层级错误
- 编号靠代码动态计算，模板与产物可各自漂移而不被发现
- 文档定义章数与实际产出不符
- `scores.json` 路径存在两套口径

本变更**从** `2026-09-18-stage4-report-template-and-role-gate` **拆分而来**：该 change 的
R16（职能红线门禁）已完成并归档，R14 / R15 / R17 及 `validate_report_role.py` 接入因改动面大
（一动即影响两份报告的全部输出结构），需独立承载与独立验证，故拆出。

## 任务类别判定

- 判据：是否改变对外可观察行为 → **是**（改变两份报告的章节结构、编号、内容边界）
- 分流：**行为变更**，任务态由本变更承载，不登记 TASKLOG

## What Changes

| # | 变更 | 优先级 |
|---|---|---|
| R14 | 评分报告骨架模板化：改 `generate_outputs.py` 按 `assets/benchmark_report.template.md` 输出；节编号由模板固定，**禁止动态计算** | P1 |
| R15 | 问题报告骨架模板化：改 `assemble_findings.py` 按 `assets/problem_report.template.md` 输出；条件节按 `optional` 标注处理 | P1 |
| R17 | 修正既有不一致：`## 3.1` 层级错误、编号动态计算、文档章数不符、`scores.json` 路径两套口径 | P2 |
| — | 上述完成后，将 `validate_report_role.py` 接入流水线（**须在 R14/R15 之后**，否则当前硬编码产物会被拦断） | P2 |

## Non-goals（本次不做）

- 不改两份报告的**内容口径**（哪些章节写什么），只改**骨架来源**
- 不调整职能红线定义（沿用 `2026-09-18-stage4-report-template-and-role-gate` 中已确立的定义）

## 风险与验证要求

改动直接影响所有历史评测产物的结构可比性，故：

1. 必须先用**真实评测产物**（非模拟数据）跑通前后对比
2. 需确认旧产物与新产物在章节集合上一致（仅编号与来源变化）
3. 未通过上述验证不得合并
