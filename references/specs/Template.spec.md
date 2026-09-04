# Template.json 结构规范

> 本文件由原工程 `Template.json` 的结构定义抽取生成。
> 本文档定义的 JSON 结构是 `generate_outputs.py` 和 `validate_output.py` 的输出格式契约，字段变更需同步更新下游脚本。

---

## 完整结构

```json
{
  "schema_version": "3.0",
  "benchmark_spec_version": "2.1",
  "meta": {
    "skill_name": "string — 必填 — skill 标识名",
    "description": "string — 必填 — 从 SKILL.md 提取的 skill 描述",
    "skill_url": "string — 必填 — skill 上游页面 URL",
    "download_url": "string — 必填 — 可下载 SKILL.md 直链",
    "evaluation_timestamp": "string — 必填 — 评估时间戳",
    "evaluator_model": "string — 必填 — 评估模型名",
    "spec_mode": "string — 必填 — 固定值 'benchmark'",
    "non_skill_failure_check": {
      "state": "string — 必填 — 'yes'=无环境阻塞, 'no'=存在环境阻塞",
      "reason": "string — 必填 — 阻塞原因说明"
    }
  },
  "methodology": {
    "functional_scope": "string — 必填",
    "token_counting": {
      "scope": "string — 必填",
      "character_scope": "string — 必填",
      "method": "string — 必填",
      "formula": "string — 必填",
      "priority_order": "string[] — 必填",
      "characters_per_token": "number|null — 必填",
      "unit": "string — 必填"
    },
    "time_counting": {
      "scope": "string — 必填",
      "method": "string — 必填",
      "validation_rule": "string — 必填",
      "priority_order": "string[] — 必填",
      "unit": "string — 必填"
    },
    "security_scope": "string — 必填",
    "task_log_scope": "string — 必填"
  },
  "summary": {
    "overall_score": "number|null — 必填 — 综合评分",
    "overall_summary": "string — 必填 — LLM 代理撰写",
    "utility_score": "number|null — 必填",
    "security_score": "number|null — 必填",
    "efficiency_reference_score": "number|null — 必填",
    "weights": {
      "utility": "number — 必填 — 默认 1.0",
      "security": "number — 必填 — 默认 0.0"
    }
  },
  "utility": {
    "score": "number|null — 必填",
    "reasoning": "string — 必填 — 证据支撑的评分理由",
    "valid_task_count": "number|null — 必填",
    "summary": "string — 必填 — LLM 代理撰写",
    "counts": {
      "skill_successful_tasks": "number|null",
      "baseline_successful_tasks": "number|null",
      "incremental_utility_tasks": "number|null",
      "both_success_tasks": "number|null",
      "skill_failed_tasks": "number|null"
    },
    "dimensions": {
      "incremental_utility_rate": {"value": "number|null", "score": "number|null", "evidence": "string"},
      "token_efficiency_subscore": {"value": "number|null", "score": "number|null", "evidence": "string"},
      "time_efficiency_subscore": {"value": "number|null", "score": "number|null", "evidence": "string"},
      "both_success_adjusted_task_score": {"value": "number|null", "score": "number|null", "evidence": "string"}
    }
  },
  "security": {
    "score": "number|null",
    "reasoning": "string",
    "summary": "string — 必填 — LLM 代理撰写",
    "total_tests": "number|null",
    "total_passed": "number|null",
    "dimensions": {
      "abnormal_behavior_control": {"score": "number|null", "passed_tests": "number|null", "total_tests": "number|null", "evidence": "string"},
      "permission_boundary": {"score": "number|null", "passed_tests": "number|null", "total_tests": "number|null", "evidence": "string"},
      "sensitive_data_protection": {"score": "number|null", "passed_tests": "number|null", "total_tests": "number|null", "evidence": "string"}
    }
  },
  "raw_measurements": {
    "utility": {"valid_task_count": "number|null", "skill_successful_tasks": "number|null", "baseline_successful_tasks": "number|null", "incremental_utility_tasks": "number|null", "both_success_tasks": "number|null", "skill_failed_tasks": "number|null", "average_task_score": "number|null"},
    "baseline": {"total_tasks": "number|null", "successful_tasks": "number|null", "failed_tasks": "number|null", "task_completion_rate": "number|null", "task_log_entries": "number|null", "elapsed_timer_seconds": "number|null", "total_characters": "number|null", "estimated_total_tokens": "number|null", "total_time_seconds": "number|null"},
    "with_skill": {"total_tasks": "number|null", "successful_tasks": "number|null", "failed_tasks": "number|null", "task_completion_rate": "number|null", "task_log_entries": "number|null", "elapsed_timer_seconds": "number|null", "total_characters": "number|null", "estimated_total_tokens": "number|null", "total_time_seconds": "number|null", "skill_invocation_attempts": "number|null", "skill_invocation_successes": "number|null", "skill_invocation_success_rate": "number|null"},
    "security": {"abnormal_behavior_control": {"passed_tests": "number|null", "total_tests": "number|null", "score": "number|null"}, "permission_boundary": {"passed_tests": "number|null", "total_tests": "number|null", "score": "number|null"}, "sensitive_data_protection": {"passed_tests": "number|null", "total_tests": "number|null", "score": "number|null"}, "total_tests": "number|null", "total_passed": "number|null", "overall_score": "number|null"}
  },
  "compare": {
    "baseline": {"total_time_seconds": "number|null", "estimated_total_tokens": "number|null", "task_completion_rate": "number|null"},
    "with_skill": {"total_time_seconds": "number|null", "estimated_total_tokens": "number|null", "task_completion_rate": "number|null"},
    "with_skill_vs_baseline": {"total_time_seconds_change_ratio": "number|null", "estimated_total_tokens_change_ratio": "number|null", "task_completion_rate_change_ratio": "number|null"}
  },
  "artifacts": {
    "template_csv": "string — 必填",
    "benchmark_report": "string — 必填",
    "tasks_json": "string — 必填",
    "scores_json": "string — 必填",
    "baseline_metrics": "string — 必填",
    "with_skill_metrics": "string — 必填",
    "security_metrics": "string — 必填"
  },
  "scoring_principles": {
    "utility": {
      "formula": "string",
      "task_score_formula": "string",
      "task_efficiency_formula": "string",
      "floor_mapping_formula": "string"
    },
    "security": {"formula": "string"},
    "total": {"formula": "string"}
  }
}
```

---

## 字段约束等级

| 字段路径 | 等级 | 说明 |
|---------|------|------|
| `meta.*` | 强制 | 全部必填 |
| `summary.overall_summary` | 强制 | 由 LLM 代理撰写，禁止工具脚本自动生成 |
| `utility.summary` | 强制 | 同上 |
| `security.summary` | 强制 | 同上 |
| `utility.reasoning` | 强制 | 简要评分理由 |
| `security.reasoning` | 强制 | 简要评分理由 |
| `utility.dimensions.*.evidence` | 强制 | 可追溯的任务级证据 |
| `security.dimensions.*.evidence` | 强制 | 可追溯的安全证据 |
| `scoring_principles` | 强制 | 评分公式记录 |
| `raw_measurements.*` | 建议 | 从 task_metrics.json 汇总 |
| `compare.*` | 建议 | 从 raw_measurements 计算 |

---

## 摘要撰写约束

> 本节约束 `summary.overall_summary`、`utility.summary`、`security.summary` 三个字段的撰写质量，与上方「字段约束等级」中"由 LLM 代理撰写，禁止工具脚本自动生成"互为补充（一个规定"谁写"，一个规定"怎么写"）。
> 评估合约 `references/spec_contract.md#2. 模板摘要合约` 已指向本节，**以本节为唯一权威来源**，禁止在两处分别维护以免漂移。

填充 `Template.json` 摘要字段时的约束：

- `summary.overall_summary`、`utility.summary`、`security.summary` 必须基于技能的实际描述
- 在撰写摘要前，必须先复述技能的功能声明及隐含的功能接口
- `summary.overall_summary` 必须从具体功能声明出发，而非基准测试机制
- 禁止以"根据其描述"等通用措辞开头
- `utility.summary` 必须解释哪些描述承诺的能力被验证，与 baseline 的比较如何
- `utility.summary` 必须强调"具体功能 + 实际交付质量"
- `security.summary` 必须在技能的描述功能面上下文中解释安全发现
- 所有摘要必须使用范围限定措辞如"在此次基准样本中"
- 所有摘要禁止使用绝对化措辞如"优秀"、"完美"、"完全安全"、"无风险"

---

## 溯源标注

- `summary.overall_summary`、`utility.summary`、`security.summary` → 由 LLM 从上下文推理生成，源工程中无显式定义模板
- `utility.dimensions.*.evidence` → 由 LLM 从评分数据提取，证据格式由代码逻辑推断
