#!/usr/bin/env python3
"""生成 task_metrics.json 规范骨架。

用法：
    python3 scripts/generate_task_metrics.py \\
        --output /path/to/task_metrics.json \\
        --task-id C_01 --mode baseline

    python3 scripts/generate_task_metrics.py \\
        --output /path/to/task_metrics.json \\
        --task-id P_01 --mode security --probe-group abnormal

输出的 JSON 结构见 references/specs/task_metrics.spec.md。
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _common import _utc_now_iso

# 时长计算器路径（写入 skeleton 的 time_estimate_basis 中）
_DURATION_CALCULATOR_PATH = str(
    (Path(__file__).resolve().parent / "calculate_timestamp_diff.py").resolve()
)


def generate_task_metrics(
    task_id: str,
    mode: str,
    probe_group: str | None = None,
) -> dict[str, Any]:
    """生成 task_metrics.json 规范骨架。

    Args:
        task_id: 任务 ID（如 C_01、H_01）
        mode: 执行模式（baseline / with_skill / security）
        probe_group: 安全探测分组（仅 security 模式）

    Returns:
        task_metrics.json 的规范骨架字典
    """
    payload: dict[str, Any] = {
        "schema_version": "exec_task_metrics_v1",
        "generated_at": _utc_now_iso(),
        "task_id": task_id,
        "mode": mode,
        "task_description": "",
        "status": "pending",
        "success": None,
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
            "evidence_path": "",
        },
        "task_start_timestamp": None,
        "task_end_timestamp": None,
        "time": None,
        "total_time_seconds": None,
        "time_estimate_basis": {
            "method": "calculate_timestamp_diff.py",
            "formula": "end_timestamp - start_timestamp",
            "start_timestamp": None,
            "end_timestamp": None,
            "start_evidence_path": None,
            "end_evidence_path": None,
            "duration_calculator": _DURATION_CALCULATOR_PATH,
        },
        "notes": "",
    }

    if mode == "with_skill":
        payload["skill_invocation_attempted"] = False
        payload["skill_invocation_success"] = False

    if mode == "security":
        payload["probe_group"] = probe_group or ""
        payload["probe_result"] = ""

    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 task_metrics.json 规范骨架")
    parser.add_argument("--output", required=True, help="输出文件路径")
    parser.add_argument("--task-id", required=True, help="任务或探测 ID")
    parser.add_argument("--mode", required=True, help="执行模式：baseline / with_skill / security")
    parser.add_argument("--probe-group", help="安全探测分组（仅 security 模式）")
    args = parser.parse_args()

    metrics = generate_task_metrics(args.task_id, args.mode, probe_group=args.probe_group)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"已生成 task_metrics.json 骨架：{output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
