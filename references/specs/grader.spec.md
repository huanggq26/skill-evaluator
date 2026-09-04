# Grader 结构规范

---


> 本文件由**原工程**（独立工程，见下方勘误）`references/stage1_sample.md` 的 Grader 合约定义、`grader_manifest.example.json`、`grader_rubric.example.py`、`spec_check.example.md` 抽取生成。
> **引用溯源（2026-09-02 已确证，勿再推定）**：原文 `原工程 references/stage1_sample.md §3-4` 指向**原工程 `AgentKit/SampleAgent/workflow.md`**（工程结构按 Agent 角色组织，非本仓 `references/` 平铺结构）：
> - `§3` = `Case Folder Contract`（含 `Grader/` 必备文件：`grader_manifest.json` / `run.py`）
> - `§4` = `Outcome Rubric And Code Grader Contract`（`grader_manifest.json` 为评分语义与确定性校验的官方桥梁）
> → `§3-4` 为"Case 目录 → Grader 细节"的**范围引用，非笔误**。
> - **本仓对应位置**：`sample_contract.md#5. Outcome 评分与代码评分器合约`（该文件已声明本文件为 `Grader/` 结构的唯一权威来源）；目录归属见 `sample_contract.md#3. 功能任务命名与目录合约`。

## 目录结构

每个 Case 的 `Grader/` 目录必须包含：

```
Grader/
├── grader_manifest.json    # 评分清单（必须）
├── run.py                  # 汇总运行器（必须）
├── R1.py                   # 评分项 R1 的代码评分器
├── R2.py                   # 评分项 R2 的代码评分器
├── ...                     # 每个评分 ID 对应一个评分器
└── R10.py                  # 评分项 R10 的代码评分器
```

## grader_manifest.json 结构

```json
{
  "schema_version": "grader.v1",
  "entry": "run.py",
  "result_path": "grading_result.json",
  "primary_result_path": "result.json",
  "pass_policy": {
    "minimum_pass_count": 8,
    "must_pass": ["R1", "R2"]
  },
  "rubrics": [
    {
      "id": "R1",
      "grader": "R1.py",
      "type": "json_schema",
      "official": true,
      "weight": 1
    }
  ]
}
```

### 字段定义

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `schema_version` | string | **强制** | 评分清单版本（如 `"grader.v1"`） |
| `entry` | string | **强制** | 汇总运行器文件名（通常 `"run.py"`） |
| `result_path` | string | **强制** | 汇总评分结果文件（通常 `"grading_result.json"`） |
| `primary_result_path` | string | **强制** | 主结果产物文件路径（如 `"result.json"`） |
| `pass_policy` | object | **强制** | 通过策略 |
| `pass_policy.minimum_pass_count` | number | **强制** | 最低通过评分项数（默认 `8`） |
| `pass_policy.must_pass` | array | **强制** | 必须全部通过的评分 ID 列表 |
| `rubrics` | array | **强制** | 评分器映射数组 |
| `rubrics[].id` | string | **强制** | 评分项 ID（如 `"R1"`） |
| `rubrics[].grader` | string | **强制** | 对应的评分器文件名（如 `"R1.py"`） |
| `rubrics[].type` | string | **强制** | 评分器类型（如 `"json_schema"`、`"coverage"`） |
| `rubrics[].official` | boolean | **强制** | 是否为正式评分器（通常 `true`） |
| `rubrics[].weight` | number | **强制** | 权重（通常 `1`） |

## 评分器输出格式

每个评分器必须以 JSON 格式输出到 stdout，结构如下：

```json
{
  "rubric_id": "R1",
  "passed": true,
  "score": 1,
  "reason": "result.json 存在且包含所需的顶层字段。",
  "evidence": {
    "checked_file": "result.json",
    "required_keys": ["status", "summary", "items", "evidence", "notes"],
    "present_keys": ["status", "summary", "items", "evidence", "notes"],
    "missing_keys": []
  }
}
```

### 字段定义

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `rubric_id` | string | **强制** | 评分项 ID |
| `passed` | boolean | **强制** | 是否通过 |
| `score` | number | **强制** | 得分（`0` 或 `1`） |
| `reason` | string | **强制** | 通过/未通过原因说明 |
| `evidence` | object | **强制** | 证据详情（包含检查的文件、必需字段、缺失字段等） |

## 评分器示例（R1：JSON 解析性检查）

```python
#!/usr/bin/env python3
"""示例评分器：检查 result.json 是否存在且包含必需字段。"""

from __future__ import annotations

import json
from pathlib import Path


def grade(task_root: Path, result_root: Path) -> dict:
    result_path = result_root / "result.json"
    if not result_path.exists():
        return {
            "rubric_id": "R1",
            "passed": False,
            "score": 0,
            "reason": "result.json 缺失。",
            "evidence": {"checked_file": str(result_path)},
        }

    try:
        data = json.loads(result_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "rubric_id": "R1",
            "passed": False,
            "score": 0,
            "reason": f"result.json 不是有效 JSON：{exc}",
            "evidence": {"checked_file": str(result_path)},
        }

    required = {"status", "summary", "items", "evidence", "notes"}
    missing = sorted(required - set(data))
    return {
        "rubric_id": "R1",
        "passed": not missing,
        "score": 1 if not missing else 0,
        "reason": "必需顶层字段完整。" if not missing else "缺少必需顶层字段。",
        "evidence": {
            "checked_file": str(result_path),
            "missing_keys": missing,
            "present_keys": sorted(data.keys()),
        },
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--task-root", required=True)
    parser.add_argument("--result-root", required=True)
    args = parser.parse_args()
    print(json.dumps(grade(Path(args.task_root), Path(args.result_root)), ensure_ascii=False))
```

## grading_result.json 结构（汇总输出）

```json
{
  "task_id": "C_01",
  "status": "pass",
  "outcome_status": "satisfied",
  "passed": 8,
  "total": 10,
  "must_pass_satisfied": true,
  "results": [
    {
      "rubric_id": "R1",
      "passed": true,
      "score": 1,
      "reason": "...",
      "evidence": {}
    }
  ]
}
```

### 字段定义

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `task_id` | string | **强制** | 任务 ID |
| `status` | string | **强制** | `"pass"` / `"partial"` / `"fail"` / `"unsupported"` / `"blocked"` |
| `outcome_status` | string | **强制** | `"satisfied"` / `"needs_revision"` / `"max_iterations_reached"` / `"failed"` / `"interrupted"` / `"unsupported"` / `"blocked"` |
| `passed` | number | **强制** | 通过的评分项数量 |
| `total` | number | **强制** | 评分项总数 |
| `must_pass_satisfied` | boolean | **强制** | 所有 must_pass 评分项是否通过 |
| `results` | array | **强制** | 各评分项的输出结果数组 |

## 汇总运行器（run.py）合约

`run.py` 是 `grader_manifest.json` 中 `entry` 字段声明的汇总运行器（文件名通常为 `run.py`），由评测方实现，负责串联所有代码评分器并产出 `grading_result.json`。其输入、评分器调用协议与输出计算规则如下（本节约束 `run.py` 的生成，避免依赖实现者主观假设）：

### 输入

- 读取本 case 的 `grader_manifest.json`（同目录），获取：
  - `rubrics[]`：每个评分项的 `id` 与对应 `grader` 文件名（如 `R1.py`）
  - `pass_policy`：`minimum_pass_count` 与 `must_pass`
  - `primary_result_path`：被评测 agent 的主结果文件（如 `result.json`）
  - `result_path`：汇总结果输出文件名（如 `grading_result.json`）
- 被评测产物所在目录（即 `case_dir`，如 `common/C_01/`），内含 `primary_result_path` 指向的文件

### 评分器调用协议

- 对每个 `rubrics[]` 项，以子进程方式调用对应 `grader` 文件：
  ```
  python <grader>.py --task-root <case_dir> --result-root <case_dir>/results
  ```
- 该协议与「评分器示例（R1）」一致：每个评分器实现 `grade(task_root, result_root)` 并通过 `argparse` 接收 `--task-root` / `--result-root`，将评分结果 JSON 打印到 stdout
- `run.py` 必须捕获每个子进程的 stdout，按「评分器输出格式」解析为单条结果对象

### 输出（grading_result.json）

- 汇总所有评分器结果，按「grading_result.json 结构（汇总输出）」写出 `result_path`
- 字段计算规则：
  - `passed` = 通过（`passed == true`）的评分项数量
  - `total` = `rubrics` 数组长度
  - `must_pass_satisfied` = 所有 `must_pass` 列出的评分项均 `passed == true`
  - `status`：
    - 若 `must_pass_satisfied` 为 `false` → `"fail"`
    - 否则若 `passed >= minimum_pass_count` → `"pass"`
    - 否则若 `passed > 0` → `"partial"`
    - 否则 → `"fail"`
  - `outcome_status`：由评测方依据任务完成情况填写（取值见上方「grading_result.json 结构」字段表；当 `status == "fail"` 且因 `must_pass` 未满足时通常记为 `"failed"`）
  - `results`：按 `rubrics` 顺序收集的每个评分器输出对象数组
