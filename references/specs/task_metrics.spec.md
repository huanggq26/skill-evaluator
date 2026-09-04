# task_metrics.json 结构规范

---


> 本文档定义的 JSON 结构是后续脚本（`backfill_task_duration.py`、`generate_tasks_json.py` 等）的输入格式契约，字段变更需同步更新下游脚本。
> 本文件由原工程脚本 `scripts/generate_task_metrics.py` 的结构定义抽取生成。
> 原脚本为纯结构说明型，不保留为独立 `.py` 文件。

## 用途

记录 ExecAgent 单个任务的执行指标（时间、字符统计、执行状态）。

## JSON 结构

### baseline 模式

```json
{
  "schema_version": "exec_task_metrics_v1",
  "generated_at": "2026-01-15T08:30:00.123Z",
  "task_id": "C_01",
  "mode": "baseline",
  "task_description": "",
  "status": "pending",
  "success": null,
  "exec_label": "",
  "files_read": [],
  "files_created": [],
  "thoutlog": "",
  "input_characters": 0,
  "output_characters": 0,
  "thoutlog_characters": 0,
  "total_characters": 0,
  "estimated_total_tokens": 0,
  "token_estimate_basis": {
    "method": "ceil(total_characters / 4)",
    "scope": "task inputs + thoutlog + task outputs",
    "formula": "ceil(total_characters / 4)",
    "characters_per_token": 4,
    "evidence_path": ""
  },
  "task_start_timestamp": null,
  "task_end_timestamp": null,
  "time": null,
  "total_time_seconds": null,
  "time_estimate_basis": {
    "method": "calculate_timestamp_diff.py",
    "formula": "end_timestamp - start_timestamp",
    "start_timestamp": null,
    "end_timestamp": null,
    "start_evidence_path": null,
    "end_evidence_path": null,
    "duration_calculator": "<calculate_timestamp_diff.py 绝对路径>"
  },
  "notes": ""
}
```

### with_skill 模式（额外字段）

```json
{
  "...": "...",
  "skill_invocation_attempted": false,
  "skill_invocation_success": false
}
```

### security 模式（额外字段）

```json
{
  "...": "...",
  "probe_group": "<abnormal|permission|sensitive>",
  "probe_result": ""
}
```

## 字段定义

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `schema_version` | string | **强制** | 固定值 `"exec_task_metrics_v1"` |
| `generated_at` | string | **强制** | UTC 时间戳，ISO 8601 毫秒精度 |
| `task_id` | string | **强制** | 任务 ID，如 `C_01`、`H_01` |
| `mode` | string | **强制** | 执行模式：`baseline` / `with_skill` / `security` |
| `task_description` | string | **建议** | 任务描述摘要 |
| `status` | string | **强制** | 执行状态：`pending` / `running` / `completed` / `failed` |
| `success` | boolean\|null | **强制** | 任务是否成功，null 表示未完成 |
| `exec_label` | string | **建议** | 执行标签 |
| `files_read` | string[] | **建议** | 读取的文件路径列表 |
| `files_created` | string[] | **建议** | 创建的文件路径列表 |
| `thoutlog` | string | **建议** | 思考日志（think-out-loud log） |
| `input_characters` | number | **建议** | 输入总字符数 |
| `output_characters` | number | **建议** | 输出总字符数 |
| `thoutlog_characters` | number | **建议** | 思考日志字符数 |
| `total_characters` | number | **建议** | 总字符数 = input + output + thoutlog |
| `estimated_total_tokens` | number | **建议** | 估算 token 数 = ceil(total_characters / 4) |
| `token_estimate_basis` | object | **建议** | Token 估算依据 |
| `task_start_timestamp` | string\|null | **强制** | 任务开始时间戳，由 backfill 脚本填充 |
| `task_end_timestamp` | string\|null | **强制** | 任务结束时间戳 |
| `time` | number\|null | **强制** | 别名 = total_time_seconds |
| `total_time_seconds` | number\|null | **强制** | 任务总耗时（秒） |
| `time_estimate_basis` | object | **强制** | 耗时估算依据 |
| `notes` | string | **建议** | 备注 |
| `skill_invocation_attempted` | boolean | with_skill **强制** | 是否尝试调用 skill |
| `skill_invocation_success` | boolean | with_skill **强制** | skill 调用是否成功 |
| `probe_group` | string | security **强制** | 安全探测分组 |
| `probe_result` | string | security **建议** | 安全探测结果 |

## 填充规则

- **骨架生成**：由 `generate_task_metrics.py` 生成初始骨架（所有数值字段为 0 或 null）
- **时长回填**：由 `backfill_task_duration.py` 通过 `calculate_timestamp_diff.py` 计算并回填 `time`/`total_time_seconds`/`time_estimate_basis`
- **字符统计回填**：由 Agent 在执行过程中更新 `input_characters`/`output_characters`/`total_characters` 等字段，或由 `backfill_character_metrics.py`（可选脚本）事后回填
- **禁止手动编辑**：`time`/`total_time_seconds`/`task_start_timestamp`/`task_end_timestamp` 只能由脚本路径写入
