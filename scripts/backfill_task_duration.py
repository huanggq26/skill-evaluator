#!/usr/bin/env python3
"""安全地将规范耗时字段回填到 task_metrics.json。

本工具用于避免手动编辑 JSON。它完成以下工作：

1. 如果 task_metrics.json 已存在，以容错方式加载
2. 如果 task_metrics.json 不存在，创建规范骨架
3. 严格通过 calculate_timestamp_diff.py 计算耗时
4. 将 task_metrics.json 重写为规范的 JSON 对象

用法：
    python3 scripts/backfill_task_duration.py \\
        --task-metrics /path/to/task_metrics.json \\
        --start /path/to/start_timestamp.json \\
        --end /path/to/end_timestamp.json \\
        --task-id C_01 --mode baseline
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from _common import _relative_to_project, _utc_now_iso


# 工程根目录（向上两级：shared -> ExecAgent -> 工程根）
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
# 时长计算器路径
_DURATION_CALCULATOR_PATH = Path(__file__).resolve().parent / "calculate_timestamp_diff.py"


def _load_duration_builder() -> Callable[[Path, Path], dict[str, Any]]:
    """动态导入 calculate_duration 函数。"""
    spec = importlib.util.spec_from_file_location(
        "execagent_calculate_timestamp_diff",
        _DURATION_CALCULATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载时长计算器：{_DURATION_CALCULATOR_PATH}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    builder = getattr(module, "calculate_duration", None)
    if not callable(builder):
        raise RuntimeError(
            f"{_DURATION_CALCULATOR_PATH} 未暴露可调用的 calculate_duration(start_path, end_path) 函数"
        )
    return builder


_BUILD_DURATION_PAYLOAD = _load_duration_builder()


def _sanitize_task_metrics_text(text: str) -> str:
    """清理 task_metrics.json 文本中的常见格式问题（如缺少逗号等）。"""
    cleaned = text.strip()
    if not cleaned:
        return cleaned

    # 提取最外层 JSON 对象
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end >= start:
        cleaned = cleaned[start : end + 1]

    # 修复常见格式问题
    cleaned = re.sub(
        r'("total_time_seconds"\s*:\s*-?\d+(?:\.\d+)?)\s*.*?(\n\s*"time_estimate_basis"\s*:)',
        r"\1,\2",
        cleaned,
        flags=re.S,
    )
    cleaned = re.sub(
        r'("end_evidence_path"\s*:\s*"[^"]+"|null)\s*(\n\s*"duration_calculator"\s*:)',
        r"\1,\2",
        cleaned,
    )
    cleaned = re.sub(
        r'("generated_at"\s*:\s*"[^"]+")\s*(\n\s*"task_id"\s*:)',
        r"\1,\2",
        cleaned,
    )
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
    return cleaned


def _load_task_metrics_tolerant(path: Path) -> tuple[dict[str, Any] | None, bool]:
    """以容错方式加载 task_metrics.json。

    Returns:
        (payload_dict | None, was_sanitized: bool)
    """
    if not path.exists():
        return None, False

    raw = path.read_text(encoding="utf-8", errors="ignore")
    try:
        payload = json.loads(raw)
        return (payload if isinstance(payload, dict) else None), False
    except Exception:
        cleaned = _sanitize_task_metrics_text(raw)
        try:
            payload = json.loads(cleaned)
            return (payload if isinstance(payload, dict) else None), cleaned != raw
        except Exception:
            decoder = json.JSONDecoder()
            try:
                payload, _ = decoder.raw_decode(cleaned)
            except Exception:
                return None, cleaned != raw
            return (payload if isinstance(payload, dict) else None), True


def _infer_mode(task_metrics_path: Path) -> str:
    """从文件路径推断执行模式。"""
    for part in task_metrics_path.parts:
        if part in {"baseline", "with_skill", "security"}:
            return part
    return "baseline"


def _default_payload(
    task_metrics_path: Path,
    *,
    task_id: str,
    mode: str,
    probe_group: str | None,
) -> dict[str, Any]:
    """生成 task_metrics.json 的默认骨架载荷。"""
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
            "evidence_path": _relative_to_project(task_metrics_path, _PROJECT_ROOT),
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
            "duration_calculator": str(_DURATION_CALCULATOR_PATH.resolve()),
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


def backfill_task_duration(
    *,
    task_metrics_path: Path,
    start_path: Path,
    end_path: Path,
    task_id: str | None = None,
    mode: str | None = None,
    probe_group: str | None = None,
) -> dict[str, Any]:
    """回填任务时长字段到 task_metrics.json。

    Args:
        task_metrics_path: task_metrics.json 文件路径
        start_path: start_timestamp.json 文件路径
        end_path: end_timestamp.json 文件路径
        task_id: 任务 ID（可选，默认从路径推断）
        mode: 执行模式（可选，默认从路径推断）
        probe_group: 安全探测分组（仅 security 模式）

    Returns:
        操作结果摘要
    """
    resolved_mode = mode or _infer_mode(task_metrics_path)
    resolved_task_id = str(task_id or task_metrics_path.parent.name)

    existing_payload, sanitized = _load_task_metrics_tolerant(task_metrics_path)
    payload = (
        dict(existing_payload)
        if isinstance(existing_payload, dict)
        else _default_payload(
            task_metrics_path,
            task_id=resolved_task_id,
            mode=resolved_mode,
            probe_group=probe_group,
        )
    )
    duration = _BUILD_DURATION_PAYLOAD(start_path, end_path)

    payload["schema_version"] = str(payload.get("schema_version") or "exec_task_metrics_v1")
    payload["generated_at"] = str(payload.get("generated_at") or _utc_now_iso())
    payload["task_id"] = str(payload.get("task_id") or resolved_task_id)
    payload["mode"] = str(payload.get("mode") or resolved_mode)
    if resolved_mode == "security" and probe_group is not None:
        payload["probe_group"] = probe_group

    payload["task_start_timestamp"] = duration["start_timestamp"]
    payload["task_end_timestamp"] = duration["end_timestamp"]
    payload["time"] = duration["duration_seconds"]
    payload["total_time_seconds"] = duration["duration_seconds"]
    payload["time_estimate_basis"] = {
        "method": duration["calculated_by"],
        "formula": duration.get("formula"),
        "start_timestamp": duration["start_timestamp"],
        "end_timestamp": duration["end_timestamp"],
        "start_evidence_path": duration["start_evidence_path"],
        "end_evidence_path": duration["end_evidence_path"],
        "duration_calculator": duration["calculator_path"],
    }

    task_metrics_path.parent.mkdir(parents=True, exist_ok=True)
    task_metrics_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"task_metrics.json 已更新：{task_metrics_path}")
    return {
        "task_metrics_path": str(task_metrics_path),
        "task_id": payload["task_id"],
        "mode": payload["mode"],
        "sanitized_existing_json": sanitized,
        "created_new_file": existing_payload is None,
        "total_time_seconds": payload["total_time_seconds"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="将规范耗时字段回填到 task_metrics.json")
    parser.add_argument("--task-metrics", required=True, type=Path, help="task_metrics.json 文件路径")
    parser.add_argument("--start", required=True, type=Path, help="start_timestamp.json 文件路径")
    parser.add_argument("--end", required=True, type=Path, help="end_timestamp.json 文件路径")
    parser.add_argument("--task-id", help="可选的任务/探测 ID 覆盖值")
    parser.add_argument("--mode", choices=["baseline", "with_skill", "security"], help="可选的执行模式覆盖值")
    parser.add_argument("--probe-group", help="可选的安全探测分组（仅 security 模式）")
    args = parser.parse_args()

    result = backfill_task_duration(
        task_metrics_path=args.task_metrics,
        start_path=args.start,
        end_path=args.end,
        task_id=args.task_id,
        mode=args.mode,
        probe_group=args.probe_group,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
