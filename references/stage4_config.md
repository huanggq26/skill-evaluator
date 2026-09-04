# SpecAgent 阶段配置

> 本文档定义 Stage 4（SpecAgent）专属的路径与常量。
> 跨阶段共享配置 → 见 `references/config.md`。
> SpecAgent 基准合约 → 见 `references/spec_contract.md`。

---

## Stage 4 输出路径

| 变量名 | 路径模板 | 说明 |
|--------|------|------|
| `SPEC_DIR` | `{RESULTS_ROOT}/{SKILL_NAME}/spec/` | SpecAgent 输出根目录 |
| `SPEC_TASKS_JSON` | `{RESULTS_ROOT}/{SKILL_NAME}/spec/results/Tasks.json` | 完整评审后的任务表（内部流程文件，落在 `results/`） |
| `SPEC_SCORES_JSON` | `{RESULTS_ROOT}/{SKILL_NAME}/spec/results/scores.json` | 综合评分（内部流程文件，落在 `results/`） |
| `SPEC_TEMPLATE_JSON` | `{RESULTS_ROOT}/{SKILL_NAME}/spec/results/Template.json` | JSON 输出模板（内部流程文件，落在 `results/`） |
| `SPEC_TEMPLATE_CSV` | `{RESULTS_ROOT}/{SKILL_NAME}/spec/results/Template.csv` | CSV 输出模板（内部流程文件，落在 `results/`） |
| `SPEC_REPORT` | `{RESULTS_ROOT}/{SKILL_NAME}/spec/benchmark_report.md` | 基准评估报告（用户级报告，与 `problem_report.md` 同级） |
| `SPEC_RESULTS_TASKS` | `{RESULTS_ROOT}/{SKILL_NAME}/spec/results/Tasks.json` | 中间评审 Tasks.json |
| `SPEC_SECURITY_DIR` | `{RESULTS_ROOT}/{SKILL_NAME}/spec/results/security/` | 安全探测执行输出 |
| `SPEC_SECURITY_METRICS` | `{RESULTS_ROOT}/{SKILL_NAME}/spec/results/security/metrics.json` | 安全阶段聚合指标 |

## Stage 4 专属常量

### 评估单元

> **数量动态（不再固定 33）**：`EVAL_UNIT_COUNT` 不再写死。评估单元总数 = `2 × 功能任务数 + 安全探测数`，其中功能任务数与安全探测数均从 `benchmark_manifest.json` 实际计数派生。下游评审循环、进度跟踪、报告均按实际数量进行。

| 常量 | 语义 | 说明 |
|------|-----|------|
| `EVAL_UNIT_COUNT` | 动态派生 | `2 × (functional_tasks 实际数) + (security_probes 实际数)` |
| `ALL_CHECKS_MUST_PASS` | false | 不要求全部通过 |

### 安全分组

| 常量 | 值 |
|------|-----|
| `SECURITY_GROUPS` | `abnormal`, `permission`, `sensitive` |

### 效率评分公式常量

| 常量 | 值 | 说明 |
|------|-----|------|
| `EFFICIENCY_PENALTY_SLOPE` | 85.4888 | 效率下降惩罚斜率 |
| `EFFICIENCY_MILD_PENALTY_SLOPE` | 25 | 效率轻微惩罚斜率 |
| `EFFICIENCY_BASELINE_SCORE` | 50 | 效率持平基准分 |
| `PHI_FLOOR` | 20 | phi 映射下限 |
| `PHI_SCALE` | 0.6 | phi 映射缩放系数 |
| `UTILITY_WEIGHT` | 1.0 | 效用分权重 |
| `SECURITY_WEIGHT` | 0.0 | 安全分权重（当前未启用） |

> ⚠️ **总分公式透明度说明**：当前 `SECURITY_WEIGHT = 0.0`，因此
> `overall_score = UTILITY_WEIGHT × utility_score`（即 `overall_score == utility_score`）。
> `security_score`（满分 100）虽然会在报告与 `security_summary` 中显著呈现，但**不计入** `overall_score`。
> 若未来启用安全权重，公式将变为 `overall = UTILITY_WEIGHT×utility + SECURITY_WEIGHT×security`，
> 届时需在 `cacu_total_score.py` 与报告模板中同步修正公式说明。
