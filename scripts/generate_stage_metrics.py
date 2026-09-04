#!/usr/bin/env python3
"""生成阶段级 metrics.json 规范骨架。

用法：
    python3 scripts/generate_stage_metrics.py \\
        --output /path/to/metrics.json \\
        --mode baseline

输出的 JSON 结构见 references/specs/metrics.spec.md。
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _common import _utc_now_iso


def generate_stage_metrics(mode: str) -> dict[str, Any]:
    """生成阶段级 metrics.json 规范骨架。

    Args:
        mode: 执行模式（baseline / with_skill / security）

    Returns:
        metrics.json 的规范骨架字典
    """
    payload: dict[str, Any] = {
        "schema_version": "exec_stage_metrics_v1",
        "generated_at": _utc_now_iso(),
        "execution_mode": mode,
        "aggregation_source": "task_metrics_bundles",
        "status": "pending",
        "task_metrics_scope": (
            f"skill-evaluator_results/<skill>/exec/{mode}/tasks/*/task_metrics.json"
            if mode != "security"
            else "skill-evaluator_results/<skill>/spec/results/security/probes/*/task_metrics.json"
        ),
        "total_tasks": 0,
        "successful_tasks": 0,
        "failed_tasks": 0,
        "total_input_characters": 0,
        "total_output_characters": 0,
        "total_thoutlog_characters": 0,
        "total_characters": 0,
        "estimated_total_tokens": 0,
        "total_time_seconds": 0,
        "notes": "",
    }

    if mode == "with_skill":
        payload["skill_invocation_attempts"] = 0
        payload["skill_invocation_successes"] = 0

    if mode == "security":
        payload["probe_groups"] = {
            "abnormal": 0,
            "permission": 0,
            "sensitive": 0,
        }

    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="生成阶段级 metrics.json 规范骨架")
    parser.add_argument("--output", required=True, help="输出文件路径")
    parser.add_argument("--mode", required=True, help="执行模式：baseline / with_skill / security")
    args = parser.parse_args()

    metrics = generate_stage_metrics(args.mode)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"已生成 metrics.json 骨架：{output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
