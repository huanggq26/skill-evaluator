# Template.csv 结构规范

> 本文件由原工程 `Template.csv` 的结构定义抽取生成。
> 本文档定义的 CSV 结构是 `generate_outputs.py` 和 `validate_output.py` 的输出格式契约。

---

## CSV 列定义

| 列名 | 必填 | 值类型 | 数据来源 | 说明 |
|------|------|--------|---------|------|
| `json_path` | 是 | string | — | 对应 Template.json 的 JSON 路径 |
| `required` | 是 | string | — | 固定值 `yes` |
| `value_type` | 是 | string | — | 值类型：`string`/`number`/`json_array` |
| `source_hint` | 是 | string | — | 数据来源提示 |
| `formula_hint` | 是 | string | — | 计算公式提示（若无则为空） |
| `value` | 是 | — | 计算/复制 | 实际填充值 |
| `notes` | 是 | string | — | 备注说明 |

---

## 完整列清单（113 行）

CSV 覆盖 Template.json 的以下字段路径：

### meta 字段（8 行）
- `meta.skill_name` — skill 标识名
- `meta.description` — skill 描述
- `meta.skill_url` — skill 上游页面 URL
- `meta.download_url` — 可下载链接
- `meta.evaluation_timestamp` — 评估时间戳
- `meta.spec_mode` — 固定 `benchmark`
- `meta.non_skill_failure_check.state` — 环境阻塞状态
- `meta.non_skill_failure_check.reason` — 阻塞原因

### methodology 字段（16 行）
- token_counting（7 个字段）、time_counting（6 个字段）、functional_scope、security_scope、task_log_scope

### summary 字段（5 行）
- overall_score、overall_summary、utility_score、security_score、efficiency_reference_score

### utility 字段（17 行）
- score、reasoning、valid_task_count、summary、counts（5 个）、dimensions（4 组×3 字段）

### security 字段（16 行）
- score、reasoning、summary、total_tests、total_passed、dimensions（3 组×4 字段）

### raw_measurements 字段（32 行）
- utility（6 个）、baseline（9 个）、with_skill（12 个）、security（12 个，含 3 组）

### compare 字段（9 行）
- baseline（3 个）、with_skill（3 个）、with_skill_vs_baseline（3 个）

### artifacts 字段（7 行）
- template_csv、benchmark_report、tasks_json、scores_json、baseline_metrics、with_skill_metrics、security_metrics

---

## 约束

- 所有行 `required` 均为 `yes`
- `value` 列在生成前为空，由 `generate_outputs.py` 填充
- 源数据来源标注在 `source_hint` 和 `formula_hint` 中
