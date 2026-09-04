# Tasks.json 结构规范

> 本文档定义的 JSON 结构是 `generate_tasks_json.py`（生成）、`backfill_reviews.py`（回填）、`cacu_total_score.py`（评分计算）和 `generate_outputs.py`（模板填充）的输入/输出格式契约，字段变更需同步更新全部下游脚本。

---

## 顶层结构

```json
{
  "meta": {
    "skill_name": "string",
    "evaluation_timestamp": "string",
    "generated_by": "string"
  },
  "summary": {
    "utility_score": "number",
    "security_score": "number",
    "valid_tasks": "number",
    "incremental_utility_tasks": "number",
    "both_success_tasks": "number",
    "skill_failed_tasks": "number",
    "security_passed": "number",
    "security_total": "number"
  },
  "tasks": [
    {
      "task_id": "string — 如 C_01",
      "category": "string — common|hard",
      "description": "string",
      "baseline_state": "string — pass|fail|null",
      "with_skill_state": "string — pass|fail|null",
      "state": "string — pass|fail — 规范状态=with_skill_state",
      "state_source": "string — spec_review",
      "baseline_audit_label": "string — pass|fail|null",
      "with_skill_audit_label": "string — pass|fail|null",
      "baseline_passed_checks": "number|null",
      "baseline_failed_checks": "number|null",
      "baseline_total_checks": "number|null",
      "with_skill_passed_checks": "number|null",
      "with_skill_failed_checks": "number|null",
      "with_skill_total_checks": "number|null",
      "review_notes": "string",
      "baseline_time_seconds": "number|null",
      "with_skill_time_seconds": "number|null",
      "baseline_total_tokens": "number|null",
      "with_skill_total_tokens": "number|null",
      "baseline_input_tokens": "number|null",
      "with_skill_input_tokens": "number|null",
      "baseline_output_tokens": "number|null",
      "with_skill_output_tokens": "number|null",
      "baseline_total_characters": "number|null",
      "with_skill_total_characters": "number|null",
      "task_score": "number|null",
      "efficiency_score": "number|null"
    }
  ],
  "security_tasks": [
    {
      "task_id": "string — 如 S_ABN_01",
      "security_group": "string — abnormal|permission|sensitive",
      "primary_asi_category": "string — ASI类别",
      "supporting_dimensions": ["string"],
      "state": "string — pass|fail",
      "state_source": "string — spec_review",
      "audit_label": "string — pass|fail",
      "passed_checks": "number",
      "failed_checks": "number",
      "total_checks": "number",
      "all_checks_passed": "boolean",
      "notes": "string",
      "result": "string — PASS|FAIL",
      "time_seconds": "number|null",
      "total_tokens": "number|null"
    }
  ],
  "security_summary": {
    "passed_probes": "number",
    "total_probes": "number",
    "security_score": "number",
    "by_dimension": {
      "<dimension>": {
        "passed": "number",
        "total": "number",
        "score": "number"
      }
    }
  }
}
```

---

## 字段约束等级

| 字段路径 | 等级 | 说明 |
|---------|------|------|
| `tasks[].task_id` | 强制 | 任务唯一标识 |
| `tasks[].state` | 强制 | 规范通过状态 = `with_skill_state` |
| `tasks[].baseline_state` | 强制 | 从 Grader 评审结果回填 |
| `tasks[].with_skill_state` | 强制 | 从 Grader 评审结果回填 |
| `tasks[].baseline_passed_checks` | 强制 | Grader 通过的 rubric 数 |
| `tasks[].with_skill_passed_checks` | 强制 | Grader 通过的 rubric 数 |
| `security_tasks[].state` | 强制 | 安全探测通过状态 |
| `security_tasks[].primary_asi_category` | 强制 | ASI 主分类 |
| `security_summary.security_score` | 强制 | 安全评分 |
| `summary.utility_score` | 建议 | 从任务状态计算 |
| `tasks[].task_score` | 建议 | 由评分公式计算 |

---

## 约束

- `generate_tasks_json.py` 生成骨架，不生成 `review_log`
- Grader 评审结果直接回填到 `Tasks.json` 行中，不产生独立 review log
- 下游评分和模板生成只能读取 `state` 字段
- `state` 的唯一标准是代码 Grader 结果 + 声明的 pass 策略
