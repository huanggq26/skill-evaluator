# metrics.json 结构规范

---


> 本文件由原工程脚本 `scripts/generate_stage_metrics.py` 的结构定义抽取生成。
> 原脚本为纯结构说明型，不保留为独立 `.py` 文件。

## 用途

汇总 ExecAgent 某个阶段（baseline / with_skill / security）下所有任务的聚合指标。

## JSON 结构

### baseline 模式

```json
{
  "schema_version": "exec_stage_metrics_v1",
  "generated_at": "2026-01-15T08:30:00.123Z",
  "execution_mode": "baseline",
  "aggregation_source": "task_metrics_bundles",
  "status": "pending",
  "task_metrics_scope": "{RESULTS_ROOT}/{SKILL_NAME}/exec/baseline/tasks/*/task_metrics.json",
  "total_tasks": 0,
  "successful_tasks": 0,
  "failed_tasks": 0,
  "total_input_characters": 0,
  "total_output_characters": 0,
  "total_thoutlog_characters": 0,
  "total_characters": 0,
  "estimated_total_tokens": 0,
  "total_time_seconds": 0,
  "notes": ""
}
```

### with_skill 模式（额外字段）

```json
{
  "...": "...",
  "skill_invocation_attempts": 0,
  "skill_invocation_successes": 0
}
```

### security 模式（额外字段）

```json
{
  "...": "...",
  "probe_groups": {
    "abnormal": 0,
    "permission": 0,
    "sensitive": 0
  }
}
```

## 字段定义

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `schema_version` | string | **强制** | 固定值 `"exec_stage_metrics_v1"` |
| `generated_at` | string | **强制** | UTC 时间戳，ISO 8601 毫秒精度 |
| `execution_mode` | string | **强制** | 执行模式：`baseline` / `with_skill` / `security` |
| `aggregation_source` | string | **强制** | 固定值 `"task_metrics_bundles"` |
| `status` | string | **强制** | 阶段状态：`pending` / `completed` |
| `task_metrics_scope` | string | **强制** | 任务指标文件的路径模式 |
| `total_tasks` | number | **强制** | 总任务数 |
| `successful_tasks` | number | **强制** | 成功任务数 |
| `failed_tasks` | number | **强制** | 失败任务数 |
| `total_input_characters` | number | **建议** | 聚合输入字符数 |
| `total_output_characters` | number | **建议** | 聚合输出字符数 |
| `total_thoutlog_characters` | number | **建议** | 聚合思考日志字符数 |
| `total_characters` | number | **建议** | 聚合总字符数 |
| `estimated_total_tokens` | number | **建议** | 聚合估算 token 数 |
| `total_time_seconds` | number | **建议** | 聚合总耗时（秒） |
| `notes` | string | **建议** | 备注 |
| `skill_invocation_attempts` | number | with_skill **强制** | skill 调用尝试次数 |
| `skill_invocation_successes` | number | with_skill **强制** | skill 调用成功次数 |
| `probe_groups` | object | security **强制** | 安全探测分组计数 |
