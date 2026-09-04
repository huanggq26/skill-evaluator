#!/usr/bin/env python3
"""仅从规范的任务本地时间戳刷新任务/探测耗时。

此工具用于在规范任务本地时间戳证据已存在时，对 ExecAgent 的
task_metrics.json 文件进行严格修复/回填。

规则：
1. 每个 bundle 必须有一个规范的 start_timestamp.json
2. 每个 bundle 必须有一个规范的 end_timestamp.json
3. 耗时必须由 scripts/calculate_timestamp_diff.py 生成
4. 禁止回退到 stage_start_timestamp.json、前一任务 end 时间戳、
   timer.log 或默认耗时
5. stage metrics.json 仅从最终化的 task_metrics.json 重新生成
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from _common import _task_success, _utc_now_iso

# 可移植路径方案
_PROJECT_ROOT = Path(__file__).resolve().parents[1]  # scripts/ -> 根目录
_DURATION_CALCULATOR_PATH = Path(__file__).resolve().parent / "calculate_timestamp_diff.py"


def _load_duration_builder() -> Callable[[Path, Path], dict[str, Any]]:
    spec = importlib.util.spec_from_file_location(
        "execagent_calculate_timestamp_diff",
        _DURATION_CALCULATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载耗时计算器: {_DURATION_CALCULATOR_PATH}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    builder = getattr(module, "calculate_duration", None)
    if not callable(builder):
        raise RuntimeError(
            f"{_DURATION_CALCULATOR_PATH} 未暴露可调用的 calculate_duration(start_path, end_path)"
        )
    return builder


BUILD_DURATION_PAYLOAD = _load_duration_builder()


def _sanitize_task_metrics_text(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return cleaned

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end >= start:
        cleaned = cleaned[start : end + 1]

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
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
    return cleaned


def _read_task_metrics_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    raw = path.read_text(encoding="utf-8", errors="ignore")
    decoder = json.JSONDecoder()
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass

    cleaned = _sanitize_task_metrics_text(raw)
    try:
        payload = json.loads(cleaned)
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass

    payload, _ = decoder.raw_decode(cleaned)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} 不包含 JSON 对象")
    return payload


def _bundle_dirname(mode: str) -> str:
    return "probes" if mode == "security" else "tasks"


def _collect_bundles(track_root: Path, mode: str) -> list[dict[str, Any]]:
    bundle_root = track_root / _bundle_dirname(mode)
    if not bundle_root.exists():
        raise FileNotFoundError(f"Bundle 目录不存在: {bundle_root}")

    bundles: list[dict[str, Any]] = []
    errors: list[str] = []

    for bundle_dir in sorted(path for path in bundle_root.iterdir() if path.is_dir()):
        task_metrics_path = bundle_dir / "task_metrics.json"
        start_timestamp_path = bundle_dir / "start_timestamp.json"
        end_timestamp_path = bundle_dir / "end_timestamp.json"

        missing = [
            path.name
            for path in (start_timestamp_path, end_timestamp_path)
            if not path.exists()
        ]
        if missing:
            errors.append(f"{bundle_dir}: 缺少 {', '.join(missing)}")
            continue

        try:
            metrics = _read_task_metrics_json(task_metrics_path)
            duration_payload = BUILD_DURATION_PAYLOAD(start_timestamp_path, end_timestamp_path)
        except Exception as exc:
            errors.append(f"{bundle_dir}: {exc}")
            continue

        bundles.append(
            {
                "task_id": bundle_dir.name,
                "bundle_dir": bundle_dir,
                "task_metrics_path": task_metrics_path,
                "existing_metrics": metrics,
                "duration_payload": duration_payload,
                "mode": mode,
            }
        )

    if errors:
        rendered = "\n".join(f"- {item}" for item in errors)
        raise RuntimeError(
            "耗时刷新已中止，因为规范任务本地证据不完整或无效:\n"
            f"{rendered}"
        )

    if not bundles:
        raise RuntimeError(f"在 {bundle_root} 下未找到有效 bundle")

    return bundles


def _update_task_metrics(bundle: dict[str, Any]) -> None:
    metrics = dict(bundle["existing_metrics"])
    duration = bundle["duration_payload"]

    metrics["schema_version"] = str(metrics.get("schema_version") or "exec_task_metrics_v1")
    metrics["generated_at"] = str(metrics.get("generated_at") or _utc_now_iso())
    metrics["task_id"] = bundle["task_id"]
    metrics["mode"] = str(metrics.get("mode") or bundle.get("mode") or "")
    metrics["task_start_timestamp"] = duration["start_timestamp"]
    metrics["task_end_timestamp"] = duration["end_timestamp"]
    metrics["time"] = duration["duration_seconds"]
    metrics["total_time_seconds"] = duration["duration_seconds"]
    metrics["time_estimate_basis"] = {
        "method": duration["calculated_by"],
        "formula": duration.get("formula"),
        "start_timestamp": duration["start_timestamp"],
        "end_timestamp": duration["end_timestamp"],
        "start_evidence_path": duration["start_evidence_path"],
        "end_evidence_path": duration["end_evidence_path"],
        "duration_calculator": duration["calculator_path"],
    }

    bundle["existing_metrics"] = metrics
    bundle["task_metrics_path"].write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"已更新 {bundle['task_metrics_path']}: total_time_seconds={metrics['total_time_seconds']}")


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _generate_metrics(bundles: list[dict[str, Any]], mode: str, output_path: Path) -> None:
    successful_tasks = 0
    failed_tasks = 0
    for bundle in bundles:
        success = _task_success(bundle["existing_metrics"])
        if success is True:
            successful_tasks += 1
        elif success is False:
            failed_tasks += 1

    metrics: dict[str, Any] = {
        "schema_version": "exec_stage_metrics_v1",
        "execution_mode": mode,
        "aggregation_source": "task_metrics_bundles",
        "status": "completed",
        "task_metrics_scope": (
            f"skill-evaluator_results/<skill>/exec/{mode}/tasks/*/task_metrics.json"
            if mode != "security"
            else "skill-evaluator_results/<skill>/spec/results/security/probes/*/task_metrics.json"
        ),
        "total_tasks": len(bundles),
        "successful_tasks": successful_tasks,
        "failed_tasks": failed_tasks,
        "total_input_characters": sum(
            _to_int(b["existing_metrics"].get("input_characters")) for b in bundles
        ),
        "total_output_characters": sum(
            _to_int(b["existing_metrics"].get("output_characters")) for b in bundles
        ),
        "total_thoutlog_characters": sum(
            _to_int(b["existing_metrics"].get("thoutlog_characters")) for b in bundles
        ),
        "total_characters": sum(
            _to_int(b["existing_metrics"].get("total_characters")) for b in bundles
        ),
        "estimated_total_tokens": sum(
            _to_int(b["existing_metrics"].get("estimated_total_tokens")) for b in bundles
        ),
        "total_time_seconds": round(
            sum(_to_float(b["existing_metrics"].get("total_time_seconds")) for b in bundles), 4
        ),
        "notes": "",
    }

    if mode == "with_skill":
        metrics["skill_invocation_attempts"] = sum(
            1 for b in bundles if bool(b["existing_metrics"].get("skill_invocation_attempted"))
        )
        metrics["skill_invocation_successes"] = sum(
            1 for b in bundles if bool(b["existing_metrics"].get("skill_invocation_success"))
        )

    if mode == "security":
        probe_groups = {"abnormal": 0, "permission": 0, "sensitive": 0}
        for bundle in bundles:
            group = str(bundle["existing_metrics"].get("probe_group") or "").strip()
            if group in probe_groups:
                probe_groups[group] += 1
        metrics["probe_groups"] = probe_groups

    output_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已生成 {output_path}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="从规范任务本地 start/end 时间戳 JSON 文件刷新任务/探测耗时。"
    )
    parser.add_argument(
        "--track-root", required=True, help="track 根目录（如 {RESULTS_ROOT}/{skill_name}/exec/baseline）"
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=["baseline", "with_skill", "security"],
        help="执行模式",
    )
    args = parser.parse_args()

    track_root = Path(args.track_root)
    bundles = _collect_bundles(track_root, args.mode)
    print(f"在 {track_root} 中找到 {len(bundles)} 个 bundle")

    for bundle in bundles:
        _update_task_metrics(bundle)

    _generate_metrics(bundles, args.mode, track_root / "metrics.json")

    print(f"\n{args.mode} 的耗时刷新完成")
    print(f"总 bundle 数: {len(bundles)}")
    print(
        "总耗时: "
        f"{sum(_to_float(bundle['existing_metrics'].get('total_time_seconds')) for bundle in bundles):.3f} 秒"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
