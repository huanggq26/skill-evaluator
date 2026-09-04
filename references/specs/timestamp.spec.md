# timestamp.json 结构规范

---


> 本文件由原工程脚本 `scripts/write_system_timestamp.py` 的结构定义抽取生成。
> 原脚本为纯结构说明型，不保留为独立 `.py` 文件。

## 用途

记录系统 UTC 时间戳，用于 `start_timestamp.json` 和 `end_timestamp.json`。

## JSON 结构

```json
{
  "schema_version": "system_timestamp_v1",
  "timestamp": "<ISO 8601 UTC 毫秒精度，如 2026-01-15T08:30:00.123Z>",
  "generated_by": "write_system_timestamp.py",
  "generator_path": "<脚本绝对路径>",
  "timestamp_source": "system_utc_now"
}
```

## 字段定义

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `schema_version` | string | **强制** | 固定值 `"system_timestamp_v1"` |
| `timestamp` | string | **强制** | UTC 时间戳，ISO 8601 格式，毫秒精度，以 `Z` 结尾 |
| `generated_by` | string | **强制** | 生成脚本名称，用于下游验证 |
| `generator_path` | string | **强制** | 生成脚本的绝对路径 |
| `timestamp_source` | string | **强制** | 固定值 `"system_utc_now"` |

## 生成方式

由 `write_system_timestamp.py` 通过 `datetime.now(timezone.utc)` 生成，**禁止手动创建或通过 `echo`/`date`/`touch` 等命令生成**。

下游脚本 `calculate_timestamp_diff.py` 会验证 `generated_by` 和 `generator_path` 字段，非规范载荷将报错。
