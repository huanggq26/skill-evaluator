#!/usr/bin/env python3
"""从 ExecAgent 任务指标和样本定义生成 Tasks.json。

本脚本从 baseline 和 with_skill 轨读取每个任务的 task_metrics.json，
计算每个任务的评分，并为一个 skill 生成 Tasks.json 骨架。

SpecAgent 评审结果不再生成为独立的 review-log 文件。
Agent 应：
1. 首先调用本脚本生成/刷新 Tasks.json 骨架
2. 将代码 Grader 审计结果直接回填到每个任务/探测行
3. 仅从 Tasks.json 运行下游评分/模板生成

若已有 Tasks.json 包含评审字段，本脚本在刷新指标派生字段时保留这些字段。

任务耗时来源：
- 直接从每个任务的 task_metrics.json 读取规范的 time/total_time_seconds
- 当规范任务指标已提供时，SpecAgent 不重新计算每任务耗时

用法：
    python3 scripts/generate_tasks_json.py \
        --skill-dir /path/to/SOURCE_DIR \
        --sample-dir {RESULTS_ROOT}/<skill_name>/sample \
        --exec-dir {RESULTS_ROOT}/<skill_name>/exec \
        --spec-dir {RESULTS_ROOT}/<skill_name>/spec
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _common import (
    _default_results_root,
    _sanitize_task_metrics_text,
    _to_float,
    _to_int,
    SECURITY_CATEGORY_TO_DIMENSION,
)

EPSILON = 1.0
FULL_SCORE_RATIO = 2.0 / 3.0
BETTER_SIDE_LOG_SLOPE = 50.0 / math.log2(1.0 / FULL_SCORE_RATIO)
WORSE_SIDE_LOG_SLOPE = 25.0
_PROJECT_ROOT = Path(__file__).resolve().parents[1]


DEFAULT_RESULTS_ROOT = _default_results_root()
# 工程根目录（等价 REPO_ROOT）
REPO_ROOT = _PROJECT_ROOT
LEGACY_SECURITY_EXPECTED_BEHAVIOR_PATTERN = re.compile(
    r"^##\s+Expected Safe Behavior\s*$([\s\S]*?)(?=^##\s+|\Z)",
    re.MULTILINE,
)
SECURITY_NON_PROBE_DIR_NAMES = {"results", "workspace", "{workspace}"}


def _read_json(path: Path) -> dict[str, Any] | None:
    """读取 JSON 文件（若存在）。"""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _read_task_metrics_json(path: Path) -> dict[str, Any] | None:
    """容错读取 task_metrics.json，避免损坏的历史文件影响评分生成。"""
    if not path.exists():
        return None

    raw = path.read_text(encoding="utf-8", errors="ignore")
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        cleaned = _sanitize_task_metrics_text(raw)
        try:
            data = json.loads(cleaned)
            return data if isinstance(data, dict) else None
        except Exception:
            decoder = json.JSONDecoder()
            try:
                data, _ = decoder.raw_decode(cleaned)
            except Exception:
                return None
            return data if isinstance(data, dict) else None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """读取 JSONL 文件。"""
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except Exception:
            continue
        if isinstance(data, dict):
            rows.append(data)
    return rows


def _load_existing_tasks_snapshot(
    *,
    specs_dir: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """加载已有 Tasks.json 行，使重新生成的骨架能保留评审字段。"""
    functional_rows: dict[str, dict[str, Any]] = {}
    security_rows_by_id: dict[str, dict[str, Any]] = {}
    security_rows_by_spec_path: dict[str, dict[str, Any]] = {}

    for path in (specs_dir / "Tasks.json", specs_dir / "results" / "Tasks.json"):
        data = _read_json(path)
        if not isinstance(data, dict):
            continue

        for row in data.get("tasks", []):
            if not isinstance(row, dict):
                continue
            task_id = row.get("task_id")
            if task_id in (None, ""):
                continue
            functional_rows[str(task_id)] = {**functional_rows.get(str(task_id), {}), **row}

        for row in data.get("security_tasks", []):
            if not isinstance(row, dict):
                continue
            task_id = row.get("task_id")
            if task_id not in (None, ""):
                security_rows_by_id[str(task_id)] = {**security_rows_by_id.get(str(task_id), {}), **row}

    return functional_rows, security_rows_by_id, security_rows_by_spec_path


def _repo_rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except Exception:
        return path.as_posix()


def _normalize_path_like(value: Any) -> str:
    return str(value or "").strip().replace("\\", "/")



    return None


def _to_nonnegative_float(value: Any) -> float | None:
    """将值转换为非负浮点数。"""
    numeric = _to_float(value)
    if numeric is None or numeric < 0:
        return None
    return numeric


def _round(value: Any, digits: int = 4) -> Any:
    """将值四舍五入到指定位数。"""
    if isinstance(value, float):
        return round(value, digits)
    return value


def _clamp_score(value: float) -> float:
    """将评分钳制到 [0, 100] 范围内。"""
    return max(0.0, min(100.0, float(value)))


def _avg(values: list[float]) -> float | None:
    """计算值的平均值。"""
    if not values:
        return None
    return sum(values) / len(values)


def _task_efficiency_score(token_subscore: float | None, time_subscore: float | None) -> float | None:
    """按当前基准规范计算任务效率。"""
    if time_subscore is None:
        return None
    return max(0.0, time_subscore)


def _cost_subscore(
    skill_cost: float | None, baseline_cost: float | None
) -> tuple[float | None, float | None]:
    """计算成本子评分。"""
    if skill_cost is None or baseline_cost is None:
        return None, None
    ratio = (skill_cost + EPSILON) / (baseline_cost + EPSILON)
    slope = BETTER_SIDE_LOG_SLOPE if ratio <= 1.0 else WORSE_SIDE_LOG_SLOPE
    score = _clamp_score(50 - slope * math.log2(ratio))
    return ratio, score


def _normalize_label(value: Any) -> str | None:
    """规范化状态标签。"""
    raw = str(value or "").strip().upper()
    if raw in {"PASS", "PASSED", "SUCCESS", "SUCCEEDED", "COMPLETED", "OK", "TRUE"}:
        return "PASS"
    if raw in {"NO", "FAIL", "FAILED", "ERROR", "FALSE"}:
        return "NO"
    return None


def _normalize_state(value: Any) -> str | None:
    label = _normalize_label(value)
    if label == "PASS":
        return "pass"
    if label == "NO":
        return "no"
    return None


def _task_is_pass(task: dict[str, Any]) -> bool:
    """仅根据 SpecAgent 评审 state 检查任务是否通过。"""
    return str(task.get("state") or "").strip().lower() == "pass"


def _state_is_pass(value: Any) -> bool:
    return _normalize_state(value) == "pass"


def _recompute_task_scoring_fields(task: dict[str, Any]) -> dict[str, Any]:
    """仅从规范的任务 state 和指标重新计算所有派生评分字段。"""
    skill_state = task.get("with_skill_state")
    if skill_state is None:
        skill_state = task.get("state")
    baseline_state = task.get("baseline_state")

    skill_success = 1 if _state_is_pass(skill_state) else 0
    baseline_success = 1 if _state_is_pass(baseline_state) else 0

    skill_tokens = _to_nonnegative_float(task.get("skill_tokens"))
    baseline_tokens = _to_nonnegative_float(task.get("baseline_tokens"))
    skill_time = _to_nonnegative_float(task.get("skill_time"))
    baseline_time = _to_nonnegative_float(task.get("baseline_time"))

    token_ratio = None
    token_subscore = None
    time_ratio = None
    time_subscore = None
    task_efficiency_score = None

    if not skill_success:
        task_score = 0.0
        scoring_path = "skill_failed"
    elif not baseline_success:
        task_score = 100.0
        scoring_path = "incremental_utility"
    else:
        scoring_path = "both_succeed"
        token_ratio, token_subscore = _cost_subscore(skill_tokens, baseline_tokens)
        time_ratio, time_subscore = _cost_subscore(skill_time, baseline_time)
        task_efficiency_score = _task_efficiency_score(token_subscore, time_subscore)
        if task_efficiency_score is None:
            task_efficiency_score = 50.0
        task_score = 20 + 0.6 * task_efficiency_score if task_efficiency_score <= 50 else task_efficiency_score

    return {
        "skill_success": skill_success,
        "baseline_success": baseline_success,
        "skill_tokens": _round(skill_tokens),
        "baseline_tokens": _round(baseline_tokens),
        "skill_time": _round(skill_time),
        "baseline_time": _round(baseline_time),
        "token_ratio": _round(token_ratio),
        "token_efficiency_subscore": _round(token_subscore),
        "time_ratio": _round(time_ratio),
        "time_efficiency_subscore": _round(time_subscore),
        "task_efficiency_score": _round(task_efficiency_score),
        "task_score": _round(task_score),
        "scoring_path": scoring_path,
    }


def _merge_task_record(task: dict[str, Any], raw: dict[str, Any]) -> None:
    """从原始数据合并任务记录。"""
    if raw.get("task_id") is not None:
        task["task_id"] = str(raw["task_id"])

    for key in ("exec_label", "probe_result", "result", "status"):
        if key in raw:
            label = _normalize_label(raw.get(key))
            if label:
                task["exec_label"] = label
                break

    for key in ("skill_invocation_attempted", "skill_invocation_success", "probe_group", "notes"):
        if key in raw and raw.get(key) is not None:
            task[key] = raw.get(key)

    for target, keys in {
        "estimated_total_tokens": ("estimated_total_tokens", "total_tokens", "tokens", "token_count"),
        "total_time_seconds": ("total_time_seconds", "time", "duration_seconds", "time_seconds", "elapsed_seconds"),
        "total_characters": ("total_characters", "characters", "character_count"),
    }.items():
        for key in keys:
            numeric = _to_nonnegative_float(raw.get(key))
            if numeric is not None:
                task[target] = numeric
                break


def _merge_nested_task_payloads(task: dict[str, Any], payload: dict[str, Any]) -> None:
    """从新版 ExecAgent schema 中合并嵌套的任务载荷块。"""
    _merge_task_record(task, payload)

    execution = payload.get("execution")
    if isinstance(execution, dict):
        _merge_task_record(task, execution)
        # 旧 Exec schema 在嵌套的 execution 块中常含取整整数耗时，
        # 而规范修复后的值位于顶层。
        # 重新应用顶层载荷，使规范的 task_metrics 字段优先。
        _merge_task_record(task, payload)


def _load_tasks_from_log(exec_root: Path, mode: str) -> dict[str, dict[str, Any]]:
    """从规范的 task_metrics.json 文件加载任务，并回退到旧版执行日志。"""
    # 规范布局: exec/{mode}/tasks；兼容旧布局 exec/results/{mode}/tasks（迁移遗留）
    tasks_root = exec_root / mode / "tasks"
    legacy_tasks_root = exec_root / "results" / mode / "tasks"
    if not tasks_root.exists() and legacy_tasks_root.exists():
        tasks_root = legacy_tasks_root
    log_path = exec_root / mode / "task_execution_log.jsonl"
    legacy_log_path = exec_root / "results" / mode / "task_execution_log.jsonl"
    if not log_path.exists() and legacy_log_path.exists():
        log_path = legacy_log_path

    tasks_by_id: dict[str, dict[str, Any]] = {}

    def _bundle_duration_seconds(task_dir: Path) -> float | None:
        start_path = task_dir / "start_timestamp.json"
        end_path = task_dir / "end_timestamp.json"
        start_payload = _read_json(start_path) or {}
        end_payload = _read_json(end_path) or {}
        start_value = str(start_payload.get("timestamp") or "").strip()
        end_value = str(end_payload.get("timestamp") or "").strip()
        if not start_value or not end_value:
            return None
        try:
            start_dt = datetime.fromisoformat(start_value.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end_value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
        duration = round((end_dt - start_dt).total_seconds(), 6)
        return duration if duration >= 0 else None

    def _merge_bundle_fallback(task: dict[str, Any], task_dir: Path) -> None:
        task.setdefault("task_id", task_dir.name)
        task.setdefault("mode", mode)

        results_dir = task_dir / "results"
        if results_dir.exists() and results_dir.is_dir() and any(results_dir.iterdir()):
            task.setdefault("status", "completed")

        if _to_nonnegative_float(task.get("total_time_seconds")) is None:
            duration = _bundle_duration_seconds(task_dir)
            if duration is not None:
                task["total_time_seconds"] = duration
                task.setdefault("time", duration)

    if tasks_root.exists():
        for task_dir in sorted(path for path in tasks_root.iterdir() if path.is_dir()):
            task = tasks_by_id.setdefault(task_dir.name, {"task_id": task_dir.name})
            task_metrics_path = task_dir / "results" / "task_metrics.json"
            if not task_metrics_path.exists():
                task_metrics_path = task_dir / "task_metrics.json"
            if task_metrics_path.exists():
                payload = _read_task_metrics_json(task_metrics_path) or {}
                payload.setdefault("task_id", payload.get("task_id") or task_dir.name)
                _merge_nested_task_payloads(task, payload)
            _merge_bundle_fallback(task, task_dir)

    # 合并旧版执行日志（存在时），主要作为向后兼容的补充。
    for row in _read_jsonl(log_path):
        task_id = row.get("task_id")
        if task_id is None:
            continue
        task = tasks_by_id.setdefault(str(task_id), {"task_id": str(task_id)})
        _merge_task_record(task, row)

    return tasks_by_id


def _load_functional_task_ids(sample_dir: Path) -> list[str]:
    manifest = _read_json(sample_dir / "benchmark_manifest.json") or {}

    ordered_ids: list[str] = []
    seen: set[str] = set()

    for entry in manifest.get("functional_tasks", []) or []:
        if not isinstance(entry, dict):
            continue
        task_id = str(entry.get("id") or entry.get("task_id") or "").strip()
        if task_id and task_id not in seen:
            ordered_ids.append(task_id)
            seen.add(task_id)

    if ordered_ids:
        return ordered_ids

    for group in ("common", "hard"):
        group_root = sample_dir / group
        if not group_root.exists():
            continue
        for case_dir in sorted(path for path in group_root.iterdir() if path.is_dir()):
            task_id = case_dir.name
            if task_id not in seen:
                ordered_ids.append(task_id)
                seen.add(task_id)

    return ordered_ids


def _load_manifest_entries(sample_dir: Path, key: str) -> dict[str, dict[str, Any]]:
    manifest = _read_json(sample_dir / "benchmark_manifest.json") or {}
    entries: dict[str, dict[str, Any]] = {}
    for entry in manifest.get(key, []) or []:
        if not isinstance(entry, dict):
            continue
        item_id = str(entry.get("id") or entry.get("task_id") or "").strip()
        if item_id:
            entries[item_id] = dict(entry)
    return entries


def _match_manifest_entry(
    entries: dict[str, dict[str, Any]],
    *candidate_ids: str,
) -> dict[str, Any]:
    for candidate_id in candidate_ids:
        item_id = str(candidate_id or "").strip().strip("/")
        if item_id and item_id in entries:
            return entries[item_id]
    return {}


def _calculate_task_scores(
    baseline_tasks: dict[str, dict[str, Any]],
    with_skill_tasks: dict[str, dict[str, Any]],
    ordered_task_ids: list[str] | None = None,
    existing_review_rows: dict[str, dict[str, Any]] | None = None,
    manifest_entries: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """计算任务级评分。"""
    # 严格只纳入 manifest functional_tasks，排除 internal_checks（如 H_02 脚手架生成）：
    # 即便 exec 目录下残留其内部策略产物也不评分，避免内部项污染候选/计分（与 stage1 入选纪律一致）。
    _allowed = set((manifest_entries or {}).keys())
    all_ids = set(baseline_tasks.keys()) | set(with_skill_tasks.keys())
    if _allowed:
        all_ids &= _allowed
    ordered_ids: list[str] = []
    seen: set[str] = set()

    for task_id in ordered_task_ids or []:
        normalized = str(task_id)
        if normalized and normalized not in seen:
            ordered_ids.append(normalized)
            seen.add(normalized)
    for task_id in sorted(all_ids):
        if task_id not in seen:
            ordered_ids.append(task_id)
            seen.add(task_id)

    task_rows: list[dict[str, Any]] = []
    existing_review_rows = existing_review_rows or {}

    def _resolved_state(raw: Any) -> str:
        normalized = _normalize_state(raw)
        if normalized in {"pass", "no"}:
            return normalized
        return "pending"

    def _resolved_label(raw: Any, state: str) -> str | None:
        label = _normalize_label(raw)
        if label:
            return label
        if state == "pass":
            return "PASS"
        if state == "no":
            return "NO"
        return None

    for task_id in ordered_ids:
        ws_task = with_skill_tasks.get(task_id, {"task_id": task_id})
        bl_task = baseline_tasks.get(task_id, {"task_id": task_id})
        existing = existing_review_rows.get(task_id, {})
        manifest_entry = _match_manifest_entry(manifest_entries or {}, task_id)

        baseline_state = _resolved_state(existing.get("baseline_state"))
        with_skill_state = _resolved_state(existing.get("with_skill_state") or existing.get("state"))
        final_state = with_skill_state
        baseline_audit_label = _resolved_label(existing.get("baseline_audit_label"), baseline_state)
        with_skill_audit_label = _resolved_label(
            existing.get("with_skill_audit_label") or existing.get("audit_label"),
            with_skill_state,
        )
        if final_state in {"pass", "no"} or baseline_state in {"pass", "no"}:
            state_source = str(existing.get("state_source") or "Tasks.json inline review")
        else:
            state_source = str(existing.get("state_source") or "pending_spec_review")

        skill_tokens = _to_nonnegative_float(ws_task.get("estimated_total_tokens"))
        baseline_tokens = _to_nonnegative_float(bl_task.get("estimated_total_tokens"))
        skill_time = _to_nonnegative_float(ws_task.get("total_time_seconds"))
        baseline_time = _to_nonnegative_float(bl_task.get("total_time_seconds"))

        with_skill_passed_checks = existing.get("with_skill_passed_checks")
        with_skill_failed_checks = existing.get("with_skill_failed_checks")
        with_skill_total_checks = existing.get("with_skill_total_checks")
        if with_skill_passed_checks is None:
            with_skill_passed_checks = existing.get("passed_checks")
        if with_skill_failed_checks is None:
            with_skill_failed_checks = existing.get("failed_checks")
        if with_skill_total_checks is None:
            with_skill_total_checks = existing.get("total_checks")

        task_row = {
            "task_id": task_id,
            "state": final_state,
            "baseline_state": baseline_state,
            "with_skill_state": with_skill_state,
            "baseline_audit_label": baseline_audit_label,
            "with_skill_audit_label": with_skill_audit_label,
            "state_source": state_source,
            "review_notes": existing.get("review_notes"),
            "baseline_passed_checks": existing.get("baseline_passed_checks"),
            "baseline_failed_checks": existing.get("baseline_failed_checks"),
            "baseline_total_checks": existing.get("baseline_total_checks"),
            "with_skill_passed_checks": with_skill_passed_checks,
            "with_skill_failed_checks": with_skill_failed_checks,
            "with_skill_total_checks": with_skill_total_checks,
            # 兼容别名：现有下游消费者仍读取无作用域字段。
            "passed_checks": with_skill_passed_checks,
            "failed_checks": with_skill_failed_checks,
            "total_checks": with_skill_total_checks,
            "skill_tokens": _round(skill_tokens),
            "baseline_tokens": _round(baseline_tokens),
            "skill_time": _round(skill_time),
            "baseline_time": _round(baseline_time),
            "outcome": manifest_entry.get("outcome") or existing.get("outcome"),
            "grader_dir": manifest_entry.get("grader_dir") or existing.get("grader_dir"),
            "grader_manifest_path": manifest_entry.get("grader_manifest_path") or existing.get("grader_manifest_path"),
            "grader_entry": manifest_entry.get("grader_entry") or existing.get("grader_entry"),
            "rubric_count": manifest_entry.get("rubric_count") or existing.get("rubric_count"),
            "rubric_pass_threshold": manifest_entry.get("rubric_pass_threshold") or existing.get("rubric_pass_threshold"),
            "output_contract": manifest_entry.get("output_contract") or existing.get("output_contract"),
            "environment": manifest_entry.get("environment") or existing.get("environment"),
            "verifier": manifest_entry.get("verifier") or existing.get("verifier"),
            "unsupported_rules": manifest_entry.get("unsupported_rules") or existing.get("unsupported_rules"),
            # 依赖专用源标记：baseline 因屏蔽被测技能内部信息资产而无法完成的任务，
            # 不属于"无增效"对比项（约束 #12）。供 cacu_total_score / generate_outputs 使用。
            "requires_proprietary_source": manifest_entry.get("requires_proprietary_source"),
        }
        task_row.update(_recompute_task_scoring_fields(task_row))
        task_rows.append(task_row)
    
    return task_rows


# ============================================================================
# 安全任务处理
# ============================================================================




def _is_security_probe_case_dir(path: Path) -> bool:
    """当目录是真正的安全探针用例（而非辅助文件夹）时返回 True。"""
    if not path.is_dir():
        return False
    if path.name in SECURITY_NON_PROBE_DIR_NAMES:
        return False
    return (
        (path / "Grader").exists()
        or (path / "TaskDescription.md").exists()
        or (path / "task_description.md").exists()
    )


def _merge_probe_result_payload(existing: dict[str, Any], incoming: dict[str, Any]) -> None:
    """合并探针载荷，保留已有字段并回填缺失字段。"""
    for key, value in incoming.items():
        if key not in existing or existing.get(key) in (None, "", [], {}):
            existing[key] = value


def _infer_probe_category(*values: Any) -> str:
    for value in values:
        text = _normalize_path_like(value).strip().lower()
        if not text:
            continue
        parts = [part for part in re.split(r"[/_-]+", text) if part]
        for index, part in enumerate(parts):
            candidate = part
            if part == "security" and index + 1 < len(parts):
                candidate = parts[index + 1]
            if candidate in SECURITY_CATEGORY_TO_DIMENSION:
                return candidate
    return ""


def _extract_probe_number(value: Any) -> int | None:
    text = _normalize_path_like(value).strip()
    if not text:
        return None
    match = re.search(r"(\d+)(?!.*\d)", text)
    if not match:
        inferred_category = _infer_probe_category(text)
        normalized_leaf = text.strip("/").split("/")[-1].lower()
        if inferred_category and normalized_leaf == inferred_category:
            return 1
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _build_security_probe_aliases(
    *,
    probe_id: Any,
    probe_group: Any = None,
    probe_path: Any = None,
) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()

    def _add(value: Any) -> None:
        item = _normalize_path_like(value).strip().strip("/")
        if not item:
            return
        variants = {item, item.replace("/", "_"), item.replace("/", "-")}
        for variant in variants:
            if variant and variant not in seen:
                aliases.append(variant)
                seen.add(variant)

    raw_probe_id = _normalize_path_like(probe_id).strip().strip("/")
    raw_probe_path = _normalize_path_like(probe_path).strip().strip("/")
    category = _infer_probe_category(probe_group, raw_probe_id, raw_probe_path)

    for value in (raw_probe_id, raw_probe_path):
        if not value:
            continue
        _add(value)
        _add(value.split("/")[-1])

    leaf = ""
    if raw_probe_path:
        leaf = raw_probe_path.split("/")[-1]
    elif raw_probe_id:
        leaf = raw_probe_id.split("/")[-1]

    if category and leaf:
        _add(f"{category}/{leaf}")
        _add(f"{category}_{leaf}")
        _add(f"{category}-{leaf}")

    number = _extract_probe_number(raw_probe_path or raw_probe_id or leaf)
    if number is not None:
        for width in (1, 2, 3):
            suffix = str(number).zfill(width)
            _add(f"probe_{suffix}")
            _add(f"case_{suffix}")
            if category:
                _add(f"{category}/probe_{suffix}")
                _add(f"{category}_probe_{suffix}")
                _add(f"{category}-probe-{suffix}")
                _add(f"{category}_{suffix}")
                _add(f"{category}-{suffix}")
                _add(f"security_{category}_{suffix}")
                _add(f"security-{category}-{suffix}")

    return aliases


def _extract_expected_behavior_from_legacy_probe_markdown(content: str) -> str:
    match = LEGACY_SECURITY_EXPECTED_BEHAVIOR_PATTERN.search(content)
    if not match:
        return ""
    lines = []
    for raw_line in match.group(1).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("-"):
            line = line[1:].strip()
        lines.append(line)
    return " ".join(lines).strip()


def _derive_security_state_from_result(
    result_data: dict[str, Any],
    *,
    stage_metrics: dict[str, Any] | None,
    probe_result_count: int,
) -> tuple[str, str]:
    summary = result_data.get("summary")
    if isinstance(summary, dict):
        for value in (
            summary.get("overall_result"),
            summary.get("result"),
            summary.get("status"),
        ):
            label = _normalize_label(value)
            if label == "PASS":
                return "pass", "probe_result"
            if label == "NO" or str(value or "").strip().lower() in {"fail", "failed"}:
                return "no", "probe_result"
        passed = _to_int(summary.get("passed"))
        failed = _to_int(summary.get("failed"))
        total = _to_int(summary.get("total_tests") or summary.get("total"))
        if total not in (None, 0):
            if passed == total and failed in (None, 0):
                return "pass", "probe_result"
            if failed == total and passed in (None, 0):
                return "no", "probe_result"

    for value in (
        result_data.get("state"),
        result_data.get("result"),
        result_data.get("probe_result"),
        result_data.get("audit_label"),
        result_data.get("execution_status"),
    ):
        label = _normalize_label(value)
        if label == "PASS":
            return "pass", "probe_result"
        if label == "NO" or str(value or "").strip().lower() in {"fail", "failed"}:
            return "no", "probe_result"

    success = result_data.get("success")
    if success is True:
        return "pass", "probe_result"
    if success is False:
        return "no", "probe_result"

    # 安全探测权威判定字段: probe_result / decision / exec_label
    # 语义: block = 正确拦截 = pass; allow = 危险放行 = no
    probe_result_label = _normalize_label(result_data.get("probe_result"))
    decision_label = _normalize_label(result_data.get("decision"))
    exec_label = _normalize_label(result_data.get("exec_label"))
    if probe_result_label == "PASS" or decision_label == "PASS" or exec_label == "PASS":
        return "pass", "probe_result"
    if probe_result_label == "NO" or decision_label == "NO" or exec_label == "NO":
        return "no", "probe_result"
    raw_decision = str(result_data.get("decision") or result_data.get("probe_result") or "").strip().lower()
    if raw_decision == "block":
        return "pass", "probe_result"
    if raw_decision == "allow":
        return "no", "probe_result"

    status = _normalize_state(result_data.get("status"))
    if status in {"failed", "error"}:
        return "no", "probe_result"

    stage_total = _to_int((stage_metrics or {}).get("total_tasks"))
    stage_successful = _to_int((stage_metrics or {}).get("successful_tasks"))
    stage_failed = _to_int((stage_metrics or {}).get("failed_tasks"))
    stage_status = str((stage_metrics or {}).get("status") or "").strip().lower()

    if stage_total not in (None, 0) and stage_total >= probe_result_count:
        if stage_successful == stage_total and stage_failed in (None, 0) and stage_status in {"completed", "pass", "passed"}:
            return "pass", "security_stage_metrics"
        if stage_failed == stage_total and stage_successful in (None, 0) and stage_status in {"completed", "failed", "no"}:
            return "no", "security_stage_metrics"

    return "pending", "pending_spec_review"


def _load_security_tasks(
    sample_dir: Path,
    spec_dir: Path,
) -> list[dict[str, Any]]:
    """从样本和基准结果加载安全探针任务。
    
    安全探针位于:
    - sample/security/{category}/{probe_id}/
    
    注意: 某些情况下，所有探针可能在单个目录下（如 abnormal/），
    实际类别由 probe_id 前缀决定。

    结果从以下来源读取:
    - spec/results/security/probes/{probe_id}/task_metrics.json (规范来源)
    - spec/results/security/task_execution_log.jsonl (旧版回退)
    - spec/results/security/security_results.json (旧版回退)

    评审字段从已有的 spec/results/Tasks.json
    行中保留。不从 review-log 文件中读取。
    
    返回安全任务记录列表。
    """
    security_tasks: list[dict[str, Any]] = []
    _, existing_security_rows_by_id, existing_security_rows_by_spec_path = _load_existing_tasks_snapshot(
        specs_dir=spec_dir,
    )
    security_manifest_entries = _load_manifest_entries(sample_dir, "security_probes")

    def _get_dimension_from_probe_id(probe_id: str) -> str:
        category = _infer_probe_category(probe_id)
        if category:
            return SECURITY_CATEGORY_TO_DIMENSION[category]
        return "unknown"

    def _candidate_probe_ids(category: str, sample_probe_id: str) -> list[str]:
        return _build_security_probe_aliases(
            probe_id=sample_probe_id,
            probe_group=category,
            probe_path=f"{category}/{sample_probe_id}",
        )

    specs_security_root = spec_dir / "results" / "security"

    security_probes_root = specs_security_root / "probes"
    security_exec_log = specs_security_root / "task_execution_log.jsonl"
    security_results_log = specs_security_root / "security_results.json"
    security_metrics_path = specs_security_root / "metrics.json"
    security_stage_metrics = _read_json(security_metrics_path) or {}

    # 从可用来源构建探针结果映射
    probe_results_by_id: dict[str, dict[str, Any]] = {}
    probe_lookup: dict[str, str] = {}

    def _register_probe_result(payload: dict[str, Any], *, probe_id: Any, probe_path: Any = None, probe_group: Any = None) -> None:
        canonical_probe_id = str(probe_id or "").strip()
        if not canonical_probe_id:
            return

        result_row = dict(payload)
        result_row.setdefault("probe_id", canonical_probe_id)
        result_row.setdefault("task_id", canonical_probe_id)
        result_row["_probe_group_inferred"] = _infer_probe_category(probe_group, canonical_probe_id, probe_path)
        result_row["_probe_path"] = _normalize_path_like(probe_path).strip().strip("/")
        existing = probe_results_by_id.get(canonical_probe_id)
        if existing is None:
            probe_results_by_id[canonical_probe_id] = result_row
        else:
            _merge_probe_result_payload(existing, result_row)

        for alias in _build_security_probe_aliases(
            probe_id=canonical_probe_id,
            probe_group=probe_group,
            probe_path=probe_path,
        ):
            probe_lookup.setdefault(alias, canonical_probe_id)

    # 规范来源: 每个探针的 task_metrics.json
    if security_probes_root.exists():
        for metrics_path in sorted(security_probes_root.rglob("task_metrics.json")):
            payload = _read_task_metrics_json(metrics_path) or {}
            probe_path = metrics_path.parent.relative_to(security_probes_root).as_posix()
            probe_id = payload.get("task_id") or probe_path or metrics_path.parent.name
            _register_probe_result(
                payload,
                probe_id=probe_id,
                probe_path=probe_path,
                probe_group=payload.get("probe_group"),
            )
        for result_json_path in sorted(security_probes_root.rglob("results/probe_results.json")):
            payload = _read_json(result_json_path) or {}
            probe_dir = result_json_path.parent.parent
            probe_path = probe_dir.relative_to(security_probes_root).as_posix()
            probe_id = payload.get("probe_id") or probe_path or probe_dir.name
            _register_probe_result(
                payload,
                probe_id=probe_id,
                probe_path=probe_path,
                probe_group=payload.get("probe_group") or payload.get("security_group"),
            )

        # 权威验证证据: 每个探针的 results/verification.json（decision: block/allow）
        for verification_path in sorted(security_probes_root.rglob("results/verification.json")):
            payload = _read_json(verification_path) or {}
            probe_dir = verification_path.parent.parent
            probe_path = probe_dir.relative_to(security_probes_root).as_posix()
            probe_id = payload.get("probe_id") or payload.get("task_id") or probe_path or probe_dir.name
            _register_probe_result(
                payload,
                probe_id=probe_id,
                probe_path=probe_path,
                probe_group=payload.get("probe_group"),
            )

    # 当规范探针指标缺失时，回退到详细执行日志。
    if not probe_results_by_id and security_exec_log.exists():
        for row in _read_jsonl(security_exec_log):
            probe_id = row.get("probe_id") or row.get("task_id")
            _register_probe_result(row, probe_id=probe_id, probe_group=row.get("probe_group") or row.get("dimension"))

    # 回退到旧版 security_results.json
    if not probe_results_by_id and security_results_log.exists():
        security_data = _read_json(security_results_log) or {}
        dimension_keys = ["sg_abnormal_behavior_control", "sg_permission_boundary", "sg_sensitive_data_protection"]
        for dimension, data in security_data.items():
            if dimension in dimension_keys:
                for detail in data.get("details", []):
                    probe_id = detail.get("probe_id")
                    if probe_id:
                        _register_probe_result({
                            "probe_id": probe_id,
                            "dimension": dimension,
                            "result": detail.get("result"),  # "PASS" or "FAIL"
                            "notes": detail.get("notes", ""),
                            "success": detail.get("result") == "PASS",
                        }, probe_id=probe_id, probe_group=dimension)

    # 扫描 samples 目录查找安全探针
    security_samples_root = sample_dir / "security"
    probe_cases: list[dict[str, Any]] = []
    if security_samples_root.exists():
        for entry in sorted(path for path in security_samples_root.iterdir() if path.is_dir()):
            if entry.name in SECURITY_NON_PROBE_DIR_NAMES:
                continue

            if _is_security_probe_case_dir(entry):
                category = _infer_probe_category(entry.name) or entry.name
                sample_probe_id = entry.name
                description = ""
                task_desc_path = entry / "TaskDescription.md"
                if not task_desc_path.exists():
                    task_desc_path = entry / "task_description.md"
                if task_desc_path.exists():
                    description = task_desc_path.read_text(encoding="utf-8")
                expected_behavior = _extract_expected_behavior_from_legacy_probe_markdown(description) if description else ""
                manifest_entry = _match_manifest_entry(
                    security_manifest_entries,
                    sample_probe_id,
                    f"{category}/{sample_probe_id}",
                    f"{category}_{sample_probe_id}",
                )
                probe_cases.append(
                    {
                        "category": category,
                        "sample_probe_id": sample_probe_id,
                        "manifest_entry": manifest_entry,
                        "candidate_ids": _candidate_probe_ids(category, sample_probe_id),
                        "description": description,
                        "expected_behavior": expected_behavior,
                    }
                )
                continue

            category = entry.name
            probe_case_dirs = [
                child
                for child in sorted(entry.iterdir())
                if child.is_dir() and _is_security_probe_case_dir(child)
            ]
            for sample_path in probe_case_dirs:
                sample_probe_id = sample_path.name
                description = ""
                task_desc_path = sample_path / "TaskDescription.md"
                if not task_desc_path.exists():
                    task_desc_path = sample_path / "task_description.md"
                if task_desc_path.exists():
                    description = task_desc_path.read_text(encoding="utf-8")
                expected_behavior = _extract_expected_behavior_from_legacy_probe_markdown(description) if description else ""
                manifest_entry = _match_manifest_entry(
                    security_manifest_entries,
                    sample_probe_id,
                    f"{category}/{sample_probe_id}",
                    f"{category}_{sample_probe_id}",
                )
                probe_cases.append(
                    {
                        "category": category,
                        "sample_probe_id": sample_probe_id,
                        "manifest_entry": manifest_entry,
                        "candidate_ids": _candidate_probe_ids(category, sample_probe_id),
                        "description": description,
                        "expected_behavior": expected_behavior,
                    }
                )

    def _match_probe_result_id(category: str, sample_probe_id: str, candidate_ids: list[str]) -> str | None:
        for candidate in candidate_ids:
            matched = probe_lookup.get(candidate)
            if matched:
                matched_category = _infer_probe_category(
                    probe_results_by_id.get(matched, {}).get("probe_group"),
                    probe_results_by_id.get(matched, {}).get("_probe_group_inferred"),
                    probe_results_by_id.get(matched, {}).get("_probe_path"),
                    matched,
                )
                if matched_category and matched_category != category:
                    continue
                return matched

        sample_number = _extract_probe_number(sample_probe_id)
        if sample_number is None:
            return None

        numeric_matches = []
        for probe_id, result_data in probe_results_by_id.items():
            result_category = _infer_probe_category(
                result_data.get("probe_group"),
                result_data.get("_probe_group_inferred"),
                result_data.get("_probe_path"),
                probe_id,
            )
            if result_category != category:
                continue
            result_number = _extract_probe_number(result_data.get("_probe_path") or probe_id)
            if result_number == sample_number:
                numeric_matches.append(probe_id)

        if len(numeric_matches) == 1:
            return numeric_matches[0]

        if sample_number in (None, 1):
            category_matches = []
            for probe_id, result_data in probe_results_by_id.items():
                result_category = _infer_probe_category(
                    result_data.get("probe_group"),
                    result_data.get("_probe_group_inferred"),
                    result_data.get("_probe_path"),
                    probe_id,
                )
                if result_category == category:
                    category_matches.append(probe_id)
            if len(category_matches) == 1:
                return category_matches[0]
        return None

    def _build_security_row(
        *,
        output_probe_id: str,
        category: str,
        candidate_ids: list[str],
        description: str,
        expected_behavior: str,
        manifest_entry: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        manifest_entry = manifest_entry or {}
        existing_review_row = None
        if existing_review_row is None:
            existing_review_row = existing_security_rows_by_id.get(output_probe_id)
        if existing_review_row is None:
            for review_key in candidate_ids:
                if review_key in existing_security_rows_by_id:
                    existing_review_row = existing_security_rows_by_id[review_key]
                    break
        existing_review_row = existing_review_row or {}

        result_data = probe_results_by_id.get(output_probe_id, {})
        dimension = (
            SECURITY_CATEGORY_TO_DIMENSION.get(_infer_probe_category(result_data.get("probe_group"), category, output_probe_id))
            or _get_dimension_from_probe_id(output_probe_id)
        )

        review_state = _normalize_state(existing_review_row.get("state"))
        state_source = str(existing_review_row.get("state_source") or "")
        if review_state not in {"pass", "no"}:
            review_state, derived_state_source = _derive_security_state_from_result(
                result_data,
                stage_metrics=security_stage_metrics,
                probe_result_count=len(probe_results_by_id),
            )
            if not state_source or state_source == "pending_spec_review":
                state_source = derived_state_source
        else:
            state_source = state_source or "Tasks.json inline review"

        review_label = _normalize_label(existing_review_row.get("audit_label"))
        if review_label is None and review_state == "pass":
            review_label = "PASS"
        elif review_label is None and review_state == "no":
            review_label = "NO"

        result_status = (
            str(existing_review_row.get("result"))
            if existing_review_row.get("result") not in (None, "")
            else ("PASS" if review_state == "pass" else "FAIL" if review_state == "no" else "PENDING")
        )
        passed_value = existing_review_row.get("passed")
        if passed_value is None:
            passed_value = 1 if review_state == "pass" else 0 if review_state == "no" else None

        description_value = description or str(result_data.get("task_description") or "")
        expected_behavior_value = expected_behavior or str(existing_review_row.get("expected_behavior") or "")

        return {
            "task_id": output_probe_id,
            "state": review_state,
            "state_source": state_source or "pending_spec_review",
            "task_type": "security",
            "security_dimension": dimension,
            "description_preview": description_value[:200] + "..." if len(description_value) > 200 else description_value,
            "expected_behavior": expected_behavior_value,
            "audit_label": review_label,
            "result": result_status,
            "passed": passed_value,
            "notes": existing_review_row.get("notes") or result_data.get("notes", ""),
            "passed_checks": existing_review_row.get("passed_checks"),
            "failed_checks": existing_review_row.get("failed_checks"),
            "total_checks": existing_review_row.get("total_checks"),
            "all_checks_passed": existing_review_row.get("all_checks_passed"),
            "outcome": manifest_entry.get("outcome") or existing_review_row.get("outcome"),
            "grader_dir": manifest_entry.get("grader_dir") or existing_review_row.get("grader_dir"),
            "grader_manifest_path": manifest_entry.get("grader_manifest_path") or existing_review_row.get("grader_manifest_path"),
            "grader_entry": manifest_entry.get("grader_entry") or existing_review_row.get("grader_entry"),
            "rubric_count": manifest_entry.get("rubric_count") or existing_review_row.get("rubric_count"),
            "rubric_pass_threshold": manifest_entry.get("rubric_pass_threshold") or existing_review_row.get("rubric_pass_threshold"),
            "output_contract": manifest_entry.get("output_contract") or existing_review_row.get("output_contract"),
            "environment": manifest_entry.get("environment") or existing_review_row.get("environment"),
            "verifier": manifest_entry.get("verifier") or existing_review_row.get("verifier"),
            "unsupported_rules": manifest_entry.get("unsupported_rules") or existing_review_row.get("unsupported_rules"),
        }

    matched_probe_ids: set[str] = set()
    for case in sorted(probe_cases, key=lambda item: (item["category"], item["sample_probe_id"])):
        category = case["category"]
        sample_probe_id = case["sample_probe_id"]
        candidate_ids = case["candidate_ids"]
        matched_probe_id = _match_probe_result_id(category, sample_probe_id, candidate_ids)
        output_probe_id = (
            matched_probe_id
            or (f"{category}_{sample_probe_id}" if sample_probe_id.startswith(("probe_", "case_")) else sample_probe_id)
        )
        # 去重键始终用「无前缀规范 id」（如 probe_asi02），与 grader 目录、grading_result.json 的
        # task_id（generate_probe_scaffolds 生成，落盘目录即 probe_asi02）一致；
        # 第二循环遍历的 probe_results_by_id key 同为无前缀，匹配即跳过，避免同一探测渲染两次。
        matched_probe_ids.add(sample_probe_id)

        security_tasks.append(
            _build_security_row(
                output_probe_id=output_probe_id,
                category=category,
                candidate_ids=candidate_ids,
                description=case["description"],
                expected_behavior=case["expected_behavior"],
                manifest_entry=case["manifest_entry"],
            )
        )

    for probe_id in sorted(
        (item for item in probe_results_by_id if item not in matched_probe_ids),
        key=lambda item: (_infer_probe_category(probe_results_by_id[item].get("_probe_group_inferred"), item), item),
    ):
        result_data = probe_results_by_id[probe_id]
        category = _infer_probe_category(result_data.get("probe_group"), result_data.get("_probe_group_inferred"), probe_id)
        security_tasks.append(
            _build_security_row(
                output_probe_id=probe_id,
                category=category,
                candidate_ids=_build_security_probe_aliases(
                    probe_id=probe_id,
                    probe_group=result_data.get("probe_group"),
                    probe_path=result_data.get("_probe_path"),
                ),
                description=str(result_data.get("task_description") or ""),
                expected_behavior=str(existing_security_rows_by_id.get(probe_id, {}).get("expected_behavior") or ""),
                manifest_entry=_match_manifest_entry(security_manifest_entries, probe_id),
            )
        )

    return security_tasks


def _display_skill_name(skill_name: str, source: str | None = None) -> str:
    cleaned_source = str(source or "").strip()
    return f"{cleaned_source}/{skill_name}" if cleaned_source else skill_name


def generate_tasks_json(
    *,
    exec_dir: Path,
    sample_dir: Path,
    spec_dir: Path,
    skill_name: str,
    source: str = "",
) -> dict[str, Any]:
    """为一个 skill 生成 Tasks.json。"""
    if not exec_dir.exists():
        raise FileNotFoundError(f"Exec root not found: {exec_dir}")
    
    # 步骤 1: 从两个模式加载任务。
    # 任务耗时必须直接从规范 task_metrics.json 字段读取。
    display_name = _display_skill_name(skill_name, source)
    print(f"  正在加载 {display_name} 的任务指标...")
    existing_task_rows, _, _ = _load_existing_tasks_snapshot(
        specs_dir=spec_dir,
    )
    baseline_tasks = _load_tasks_from_log(exec_dir, "baseline")
    with_skill_tasks = _load_tasks_from_log(exec_dir, "with_skill")
    ordered_task_ids = _load_functional_task_ids(sample_dir)
    functional_manifest_entries = _load_manifest_entries(sample_dir, "functional_tasks")

    # 计算功能任务评分
    task_rows = _calculate_task_scores(
        baseline_tasks,
        with_skill_tasks,
        ordered_task_ids=ordered_task_ids,
        existing_review_rows=existing_task_rows,
        manifest_entries=functional_manifest_entries,
    )

    # 步骤 2: 加载安全任务
    print(f"  正在加载 {display_name} 的安全探针...")
    security_tasks = _load_security_tasks(
        sample_dir,
        spec_dir,
    )
    
    # 计算功能任务汇总
    total_tasks = len(task_rows)
    valid_tasks = total_tasks  # 所有匹配的任务均有效
    
    task_scores = [t["task_score"] for t in task_rows if t["task_score"] is not None]
    utility_score = _avg(task_scores) if task_scores else None
    
    incremental_utility_tasks = sum(1 for t in task_rows if t["scoring_path"] == "incremental_utility")
    both_success_tasks = sum(1 for t in task_rows if t["scoring_path"] == "both_succeed")
    skill_failed_tasks = sum(1 for t in task_rows if t["scoring_path"] == "skill_failed")
    
    # 计算安全汇总
    security_passed = sum(1 for t in security_tasks if _task_is_pass(t))
    security_total = len(security_tasks)
    security_score = (security_passed / security_total * 100) if security_total > 0 else None
    
    # 安全维度细分
    security_by_dimension: dict[str, dict[str, int]] = {}
    for t in security_tasks:
        dim = t.get("security_dimension", "unknown")
        if dim not in security_by_dimension:
            security_by_dimension[dim] = {"passed": 0, "total": 0}
        security_by_dimension[dim]["total"] += 1
        if _task_is_pass(t):
            security_by_dimension[dim]["passed"] += 1

    # 评审完成度自检：静默遗留 pending 会绕过「全部单元评审」完成标准
    _pending_security = [t["task_id"] for t in security_tasks if str(t.get("state") or "").strip().lower() == "pending"]
    _pending_functional = [t["task_id"] for t in task_rows if str(t.get("state") or "").strip().lower() == "pending"]
    if _pending_security:
        print(f"⚠️ 警告: 以下安全探测仍为 pending（未完成评审）: {_pending_security}")
    if _pending_functional:
        print(f"⚠️ 警告: 以下功能任务仍为 pending（未完成评审）: {_pending_functional}")

    return {
        "schema_version": "1.0",
        "skill_name": display_name,
        "source": source,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_tasks": total_tasks,
            "valid_tasks": valid_tasks,
            "utility_score": _round(utility_score),
            "incremental_utility_tasks": incremental_utility_tasks,
            "both_success_tasks": both_success_tasks,
            "skill_failed_tasks": skill_failed_tasks,
            "security_tasks": security_total,
            "security_passed": security_passed,
            "security_score": _round(security_score),
        },
        "tasks": task_rows,
        "security_tasks": security_tasks,
        "security_summary": {
            "total_probes": security_total,
            "passed_probes": security_passed,
            "security_score": _round(security_score),
            "by_dimension": {
                dim: {
                    "passed": counts["passed"],
                    "total": counts["total"],
                    "score": _round(counts["passed"] / counts["total"] * 100) if counts["total"] > 0 else None,
                }
                for dim, counts in security_by_dimension.items()
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="从 ExecAgent 功能证据和 SpecAgent 安全产物生成 Tasks.json。"
    )
    parser.add_argument("--skill-dir", type=Path, help="SOURCE_DIR 路径。脚本从 basename 推导 skill_name。")
    parser.add_argument("--skill-name", help="可选显式 skill 名称。覆盖 basename(skill-dir)。")
    parser.add_argument("--sample-dir", type=Path, help="{RESULTS_ROOT}/{skill_name}/sample 路径")
    parser.add_argument("--exec-dir", type=Path, help="{RESULTS_ROOT}/{skill_name}/exec 路径")
    parser.add_argument("--spec-dir", type=Path, help="{RESULTS_ROOT}/{skill_name}/spec 路径")
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS_ROOT, help=f"开源布局的结果根目录（默认: {DEFAULT_RESULTS_ROOT}）")
    parser.add_argument(
        "--source",
        help="来源目录名（如 Anthropic、SkillSh）",
    )
    parser.add_argument(
        "--skill",
        help="Skill 目录名（如 pdf、docx）",
    )
    parser.add_argument(
        "--exec-root",
        type=Path,
        help="旧版 exec 根目录",
    )
    parser.add_argument(
        "--samples-root",
        type=Path,
        help="旧版 samples 根目录",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="输出文件路径（默认: spec/results/Tasks.json）",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="使用开源布局处理 results-root 下所有 skill",
    )
    
    args = parser.parse_args()

    def _write_tasks_outputs(base_output_path: Path, payload: dict[str, Any]) -> None:
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        base_output_path.parent.mkdir(parents=True, exist_ok=True)
        base_output_path.write_text(text, encoding="utf-8")

    if args.all:
        for skill_root in sorted(path for path in args.results_root.iterdir() if path.is_dir()):
            sample_dir = skill_root / "sample"
            exec_dir = skill_root / "exec"
            spec_dir = skill_root / "spec"
            if not sample_dir.exists() or not exec_dir.exists():
                continue
            try:
                result = generate_tasks_json(
                    exec_dir=exec_dir,
                    sample_dir=sample_dir,
                    spec_dir=spec_dir,
                    skill_name=skill_root.name,
                )
                output_path = spec_dir / "results" / "Tasks.json"
                _write_tasks_outputs(output_path, result)
                print(f"✅ 已生成: {output_path}")
            except FileNotFoundError as e:
                print(f"⚠️ 已跳过 {skill_root.name}: {e}")
            except Exception as e:
                print(f"❌ 错误 {skill_root.name}: {e}")
                import traceback
                traceback.print_exc()
    else:
        if args.sample_dir and args.exec_dir and args.spec_dir:
            skill_name = args.skill_name or (args.skill_dir.name if args.skill_dir else args.spec_dir.parent.name)
            source = args.source or ""
            sample_dir = args.sample_dir
            exec_dir = args.exec_dir
            spec_dir = args.spec_dir
        elif args.skill_dir:
            skill_name = args.skill_name or args.skill_dir.resolve().name
            source = args.source or ""
            run_root = args.results_root / skill_name
            sample_dir = run_root / "sample"
            exec_dir = run_root / "exec"
            spec_dir = run_root / "spec"
        elif args.source and args.skill and args.exec_root and args.samples_root:
            skill_name = args.skill
            source = args.source
            sample_dir = args.samples_root / args.source / args.skill
            exec_dir = args.exec_root / args.source / args.skill
            legacy_spec_root = (args.output.parent.parent if args.output and args.output.name == "Tasks.json" else None)
            spec_dir = legacy_spec_root or (args.results_root / args.source / args.skill)
        else:
            parser.error("请提供 --skill-dir，或同时提供 --sample-dir/--exec-dir/--spec-dir，或旧版 --source/--skill 及旧版根路径。")

        result = generate_tasks_json(
            exec_dir=exec_dir,
            sample_dir=sample_dir,
            spec_dir=spec_dir,
            skill_name=skill_name,
            source=source,
        )

        if args.output:
            output_path = args.output
        else:
            output_path = spec_dir / "results" / "Tasks.json"

        _write_tasks_outputs(output_path, result)
        print(f"✅ 已生成: {output_path}")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
