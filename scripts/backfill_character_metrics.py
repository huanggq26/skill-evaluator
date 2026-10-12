#!/usr/bin/env python3
"""从已有产物回填 ExecAgent 字符/token 指标的修复工具。

⚠️ 可选脚本，不进入流水线主流程。

用途：修复历史运行中 task_metrics.json 存在但字符相关字段为空/null/损坏的情况。

功能：
1. 以容错方式加载 task_metrics.json（含已知损坏模式修复）
2. 从样本/任务元数据和 with-skill worklog 提示推断输入文件
3. 从任务级 results/ 目录推断输出文件
4. 用 worklog.log 作为缺失 thoutlog 的历史代理
5. 重新计算 input/output/thoutlog/total 字符数和估算 token 数
6. 刷新 baseline / with_skill 的阶段级 metrics.json

用法：
    # 修复单个 skill
    python3 scripts/backfill_character_metrics.py \\
        --skill skill_name

    # 修复所有 skill
    python3 scripts/backfill_character_metrics.py --all
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from _common import (
    _default_results_root,
    _sanitize_task_metrics_text,
    _relative_to_project,
    _task_success,
    _utc_now_iso,
)

# 工程根目录（向上两级：shared -> ExecAgent -> 工程根）
_PROJECT_ROOT = Path(__file__).resolve().parents[1]


_DEFAULT_RESULTS_ROOT = _default_results_root()

_TEXT_SUFFIXES = {
    ".c", ".cc", ".cpp", ".css", ".csv", ".go", ".graphql", ".h", ".hpp",
    ".html", ".java", ".js", ".json", ".jsx", ".mjs", ".cjs", ".kt", ".log",
    ".md", ".mermaid", ".php", ".prompt", ".ps1", ".py", ".rb", ".rs", ".scss",
    ".sh", ".sql", ".svg", ".tex", ".toml", ".ts", ".tsx", ".txt", ".xml",
    ".yaml", ".yml",
}

_BINARY_SUFFIXES = {
    ".7z", ".bin", ".bmp", ".class", ".doc", ".docx", ".eot", ".gif", ".gz",
    ".ico", ".jar", ".jpeg", ".jpg", ".mov", ".mp3", ".mp4", ".otf", ".pdf",
    ".png", ".ppt", ".pptx", ".pyc", ".ttf", ".wav", ".webm", ".webp",
    ".woff", ".woff2", ".xls", ".xlsx", ".zip",
}

_IGNORED_OUTPUT_DIRS = {".git", ".next", ".venv", "__pycache__", "build", "dist", "node_modules", "venv"}
_IGNORED_OUTPUT_FILES = {".package-lock.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "poetry.lock"}

_FILE_MENTION_PATTERN = re.compile(r"([A-Za-z0-9_./\\-]+\.[A-Za-z0-9]+)")
# 分隔符用 [/\\] 而非仅 "/": Windows 下 os.sep 为 "\\"，只认 "/" 会导致
# 全部 task_metrics.json 匹配失败 → 字符数/耗时回填为 0 → 效用与效率指标失真。
_TASK_ROOT_PATTERN = re.compile(
    r"[/\\](?P<skill>[^/\\]+)[/\\]exec[/\\](?P<mode>baseline|with_skill)[/\\]"
    r"(?P<kind>tasks)[/\\](?P<task_id>[^/\\]+)(?:[/\\]results)?[/\\]task_metrics\.json$"
)





def _dedupe_paths(paths: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    items: list[Path] = []
    for path in paths:
        try:
            key = str(path.resolve())
        except Exception:
            key = str(path)
        if key in seen:
            continue
        seen.add(key)
        items.append(path)
    return items


def _load_json_tolerant(path: Path) -> tuple[dict[str, Any] | None, bool]:
    if not path.exists():
        return None, False
    raw = path.read_text(encoding="utf-8", errors="ignore")
    decoder = json.JSONDecoder()
    try:
        data = json.loads(raw)
        return (data if isinstance(data, dict) else None), False
    except Exception:
        cleaned = _sanitize_task_metrics_text(raw)
        try:
            data = json.loads(cleaned)
            return (data if isinstance(data, dict) else None), cleaned != raw
        except Exception:
            try:
                data, _ = decoder.raw_decode(cleaned)
                return (data if isinstance(data, dict) else None), True
            except Exception:
                return None, False


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip().rstrip("s"))
        except ValueError:
            return None
    return None


def _to_int(value: Any) -> int | None:
    numeric = _to_float(value)
    if numeric is None:
        return None
    return int(numeric)


def _is_probably_text_file(path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix in _TEXT_SUFFIXES:
        return True
    if suffix in _BINARY_SUFFIXES:
        return False
    try:
        chunk = path.read_bytes()[:4096]
    except Exception:
        return False
    if b"\x00" in chunk:
        return False
    try:
        decoded = chunk.decode("utf-8", errors="ignore")
    except Exception:
        return False
    if not decoded:
        return False
    printable = sum(1 for ch in decoded if ch.isprintable() or ch in "\r\n\t")
    return printable / max(len(decoded), 1) >= 0.85


def _read_text_len(path: Path) -> int:
    if not path.exists() or not path.is_file() or not _is_probably_text_file(path):
        return 0
    try:
        return len(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return 0


def _resolve_candidate_path(
    raw_path: str, *, task_dir: Path, case_dir: Path | None, skill_dir: Path | None
) -> Path | None:
    value = str(raw_path or "").strip()
    if not value:
        return None

    direct = Path(value)
    candidates: list[Path] = []
    sample_skill_root: Path | None = None
    if case_dir is not None:
        parts = case_dir.parts
        if "security" in parts and len(case_dir.parents) >= 3:
            sample_skill_root = case_dir.parents[2]
        elif len(case_dir.parents) >= 2:
            sample_skill_root = case_dir.parents[1]

    if direct.is_absolute():
        candidates.append(direct)
    else:
        candidates.extend([
            _PROJECT_ROOT / value,
            task_dir / value,
            task_dir / "results" / value,
        ])
        if case_dir is not None:
            candidates.append(case_dir / value)
        if sample_skill_root is not None:
            candidates.append(sample_skill_root / value)
        if skill_dir is not None:
            candidates.append(skill_dir / value)

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _extract_skill_file_mentions(worklog_text: str, skill_dir: Path | None) -> list[Path]:
    if not worklog_text or skill_dir is None or not skill_dir.exists():
        return []
    resolved: list[Path] = []
    for line in worklog_text.splitlines():
        if "read" not in line.lower():
            continue
        for token in _FILE_MENTION_PATTERN.findall(line):
            token_path = Path(token)
            if token_path.is_absolute() and token_path.exists():
                resolved.append(token_path)
                continue
            direct = skill_dir / token_path
            if direct.exists():
                resolved.append(direct)
                continue
            by_name = list(skill_dir.rglob(token_path.name))
            if by_name:
                resolved.append(by_name[0])
    return _dedupe_paths(resolved)


def _locate_case_dir(samples_root: Path, source: str, skill: str, mode: str, task_id: str) -> Path | None:
    if source:
        skill_samples = samples_root / source / skill
    else:
        skill_samples = samples_root / skill / "sample"
    if not skill_samples.exists():
        return None
    if mode in {"baseline", "with_skill"}:
        for bucket in ("common", "hard"):
            candidate = skill_samples / bucket / task_id
            if candidate.exists():
                return candidate
        return None
    security_root = skill_samples / "security"
    if not security_root.exists():
        return None
    for candidate in security_root.rglob(task_id):
        if candidate.is_dir():
            return candidate
    return None


def _default_case_inputs(case_dir: Path | None, mode: str) -> list[Path]:
    if case_dir is None:
        return []
    candidates = [case_dir / "TaskDescription.md", case_dir / "task_description.md"]
    if mode == "security":
        for name in ("Grader/grader_manifest.json",):
            candidate = case_dir / name
            if candidate.exists():
                candidates.append(candidate)
    return [path for path in candidates if path.exists()]


def _collect_input_paths(
    metrics: dict[str, Any],
    *,
    task_dir: Path,
    case_dir: Path | None,
    skill_dir: Path | None,
    mode: str,
    worklog_text: str,
) -> list[Path]:
    paths: list[Path] = []
    raw_files = metrics.get("files_read")
    if isinstance(raw_files, list):
        for raw_path in raw_files:
            resolved = _resolve_candidate_path(
                str(raw_path), task_dir=task_dir, case_dir=case_dir, skill_dir=skill_dir
            )
            if resolved is not None and resolved.exists() and resolved.is_file():
                paths.append(resolved)
    if not paths:
        paths.extend(_default_case_inputs(case_dir, mode))
    if mode == "with_skill":
        skill_inputs = [
            path for path in paths
            if skill_dir is not None and skill_dir.resolve() in path.resolve().parents
        ]
        if not skill_inputs:
            paths.extend(_extract_skill_file_mentions(worklog_text, skill_dir))
            skill_inputs = [
                path for path in paths
                if skill_dir is not None and skill_dir.resolve() in path.resolve().parents
            ]
        if not skill_inputs and skill_dir is not None and (skill_dir / "SKILL.md").exists():
            paths.append(skill_dir / "SKILL.md")
    if mode == "security" and not raw_files:
        paths.extend(_default_case_inputs(case_dir, mode))
    filtered: list[Path] = []
    for path in _dedupe_paths(paths):
        try:
            if (task_dir / "results").resolve() in path.resolve().parents:
                continue
        except Exception:
            pass
        filtered.append(path)
    return filtered


def _collect_output_paths(task_dir: Path) -> list[Path]:
    results_dir = task_dir / "results"
    if not results_dir.exists():
        return []
    output_paths: list[Path] = []
    for path in results_dir.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _IGNORED_OUTPUT_DIRS for part in path.parts):
            continue
        if path.name in _IGNORED_OUTPUT_FILES:
            continue
        output_paths.append(path)
    return _dedupe_paths(output_paths)


def _normalize_time_value(metrics: dict[str, Any]) -> float | None:
    for key in ("total_time_seconds", "time"):
        value = _to_float(metrics.get(key))
        if value is not None:
            return round(value, 3)
    execution = metrics.get("execution")
    if isinstance(execution, dict):
        value = _to_float(execution.get("duration_seconds"))
        if value is not None:
            return round(value, 3)
    return None


def _refresh_stage_metrics(track_root: Path, mode: str) -> dict[str, Any] | None:
    children_dir = track_root / ("tasks" if mode != "security" else "probes")
    if not children_dir.exists():
        return None

    existing_metrics, _ = _load_json_tolerant(track_root / "metrics.json")
    stage_metrics = existing_metrics if isinstance(existing_metrics, dict) else {}
    stage_metrics.update({
        "schema_version": "exec_stage_metrics_v1",
        "generated_at": _utc_now_iso(),
        "execution_mode": mode,
        "aggregation_source": "task_metrics_bundles",
        "status": "completed",
        "task_metrics_scope": (
            f"skill-evaluator_results/<skill>/exec/{mode}/tasks/*/task_metrics.json"
            if mode != "security"
            else "skill-evaluator_results/<skill>/spec/results/security/probes/*/task_metrics.json"
        ),
    })

    task_ids: list[str] = []
    successful = 0
    failed = 0
    total_input = 0
    total_output = 0
    total_thoutlog = 0
    total_chars = 0
    total_tokens = 0
    total_time = 0.0
    probe_groups: Counter[str] = Counter()
    skill_invocation_attempts = 0
    skill_invocation_successes = 0
    end_timestamps: list[str] = []

    for child_dir in sorted(path for path in children_dir.iterdir() if path.is_dir()):
        metrics_file = child_dir / "results" / "task_metrics.json"
        if not metrics_file.exists():
            metrics_file = child_dir / "task_metrics.json"
        payload, _ = _load_json_tolerant(metrics_file)
        if not isinstance(payload, dict):
            continue
        task_ids.append(str(payload.get("task_id") or child_dir.name))
        success = _task_success(payload)
        if success is True:
            successful += 1
        elif success is False:
            failed += 1
        total_input += _to_int(payload.get("input_characters")) or 0
        total_output += _to_int(payload.get("output_characters")) or 0
        total_thoutlog += _to_int(payload.get("thoutlog_characters")) or 0
        total_chars += _to_int(payload.get("total_characters")) or 0
        total_tokens += _to_int(payload.get("estimated_total_tokens")) or 0
        total_time += _normalize_time_value(payload) or 0.0

        if payload.get("task_end_timestamp"):
            end_timestamps.append(str(payload.get("task_end_timestamp")))

        if mode == "with_skill":
            if bool(payload.get("skill_invocation_attempted")):
                skill_invocation_attempts += 1
            if bool(payload.get("skill_invocation_success")):
                skill_invocation_successes += 1
        if mode == "security":
            probe_group = str(payload.get("probe_group") or "").strip().lower()
            if probe_group:
                probe_groups[probe_group] += 1

    stage_metrics["total_tasks"] = len(task_ids)
    stage_metrics["successful_tasks"] = successful
    stage_metrics["failed_tasks"] = failed
    stage_metrics["total_input_characters"] = total_input
    stage_metrics["total_output_characters"] = total_output
    stage_metrics["total_thoutlog_characters"] = total_thoutlog
    stage_metrics["total_characters"] = total_chars
    stage_metrics["estimated_total_tokens"] = total_tokens
    stage_metrics["total_time_seconds"] = round(total_time, 4)
    stage_metrics["time"] = f"{stage_metrics['total_time_seconds']}s"
    stage_metrics["task_ids"] = task_ids
    stage_metrics.setdefault("notes", "")

    if mode == "with_skill":
        stage_metrics["skill_invocation_attempts"] = skill_invocation_attempts
        stage_metrics["skill_invocation_successes"] = skill_invocation_successes
        stage_metrics["skill_invocation_success_rate"] = (
            round(skill_invocation_successes / skill_invocation_attempts * 100, 4)
            if skill_invocation_attempts
            else 0.0
        )
    if mode == "security":
        stage_metrics["probe_groups"] = {
            "abnormal": probe_groups.get("abnormal", 0),
            "permission": probe_groups.get("permission", 0),
            "sensitive": probe_groups.get("sensitive", 0),
        }
    if end_timestamps:
        stage_metrics["stage_end_timestamp"] = max(end_timestamps)

    (track_root / "metrics.json").write_text(
        json.dumps(stage_metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return stage_metrics


def repair_skill(
    exec_root: Path,
    samples_root: Path,
    skills_root: Path | None,
    source: str,
    skill: str,
    *,
    skill_dir_override: Path | None = None,
    manifest_allow: set[str] | None = None,
) -> dict[str, Any]:
    """回填单个 skill 的字符/token 指标。

    Args:
        exec_root: 执行结果根目录
        samples_root: 样本根目录
        skills_root: skill 源文件根目录
        source: 来源标识
        skill: skill 名称
        skill_dir_override: 手动指定 skill 目录路径
        manifest_allow: 若提供，仅回填 manifest 中存在的功能任务（含性能标记任务），
            以 manifest 标记为唯一来源，不凭空补算非标记任务（对齐 AGENTS_RULES 性能标记派生）。
    """
    if source:
        skill_exec_root = exec_root / source / skill / "results"
        skill_dir = (skills_root / source / skill) if skills_root is not None else None
    else:
        # 开源布局：exec_root/<skill>/exec/<mode>/tasks/*/task_metrics.json
        skill_exec_root = exec_root / skill / "exec"
        skill_dir = skill_dir_override
    if not skill_exec_root.exists():
        raise FileNotFoundError(f"执行结果目录不存在：{skill_exec_root}")

    repaired_files = 0
    sanitized_files = 0
    changed_files = 0
    modes_touched: set[str] = set()

    for metrics_path in sorted(skill_exec_root.rglob("task_metrics.json")):
        match = _TASK_ROOT_PATTERN.search(str(metrics_path.resolve()))
        if not match:
            continue

        mode = match.group("mode")
        task_id = match.group("task_id")
        # manifest 白名单约束：仅回填 manifest 中存在的功能任务（以 manifest 标记为唯一来源）
        if manifest_allow is not None and task_id not in manifest_allow:
            continue
        task_dir = metrics_path.parent
        case_dir = _locate_case_dir(samples_root, source, skill, mode, task_id)

        payload, sanitized = _load_json_tolerant(metrics_path)
        if not isinstance(payload, dict):
            continue
        if sanitized:
            sanitized_files += 1

        worklog_path = task_dir / "worklog.log"
        worklog_text = worklog_path.read_text(encoding="utf-8", errors="ignore") if worklog_path.exists() else ""

        input_paths = _collect_input_paths(
            payload, task_dir=task_dir, case_dir=case_dir,
            skill_dir=skill_dir if mode == "with_skill" else None,
            mode=mode, worklog_text=worklog_text,
        )
        output_paths = _collect_output_paths(task_dir)

        thoutlog = str(payload.get("thoutlog") or "")
        thoutlog_source = "task_metrics"
        if not thoutlog and worklog_text:
            thoutlog = worklog_text
            thoutlog_source = "worklog.log_proxy"

        input_characters = sum(_read_text_len(path) for path in input_paths)
        output_characters = sum(_read_text_len(path) for path in output_paths)
        thoutlog_characters = len(thoutlog)
        total_characters = input_characters + output_characters + thoutlog_characters
        estimated_total_tokens = int(math.ceil(total_characters / 4.0))

        previous = {
            "files_read": payload.get("files_read"),
            "files_created": payload.get("files_created"),
            "thoutlog": payload.get("thoutlog"),
            "input_characters": payload.get("input_characters"),
            "output_characters": payload.get("output_characters"),
            "thoutlog_characters": payload.get("thoutlog_characters"),
            "total_characters": payload.get("total_characters"),
            "estimated_total_tokens": payload.get("estimated_total_tokens"),
        }

        payload["schema_version"] = str(payload.get("schema_version") or "exec_task_metrics_v1")
        payload["task_id"] = str(payload.get("task_id") or task_id)
        payload["mode"] = str(payload.get("mode") or mode)
        payload["files_read"] = [_relative_to_project(path, _PROJECT_ROOT) for path in input_paths]
        payload["files_created"] = [_relative_to_project(path, _PROJECT_ROOT) for path in output_paths]
        payload["thoutlog"] = thoutlog
        payload["input_characters"] = input_characters
        payload["output_characters"] = output_characters
        payload["thoutlog_characters"] = thoutlog_characters
        payload["total_characters"] = total_characters
        payload["estimated_total_tokens"] = estimated_total_tokens
        payload["token_estimate_basis"] = {
            "method": "ceil(total_characters / 4)",
            "scope": "task inputs + thoutlog + task outputs",
            "formula": "ceil(total_characters / 4)",
            "characters_per_token": 4,
            "evidence_path": _relative_to_project(metrics_path, _PROJECT_ROOT),
            "thoutlog_source": thoutlog_source,
        }

        current = {
            "files_read": payload.get("files_read"),
            "files_created": payload.get("files_created"),
            "thoutlog": payload.get("thoutlog"),
            "input_characters": payload.get("input_characters"),
            "output_characters": payload.get("output_characters"),
            "thoutlog_characters": payload.get("thoutlog_characters"),
            "total_characters": payload.get("total_characters"),
            "estimated_total_tokens": payload.get("estimated_total_tokens"),
        }

        if previous != current or sanitized:
            metrics_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            changed_files += 1
            modes_touched.add(mode)

        repaired_files += 1

    stage_updates: dict[str, dict[str, Any]] = {}
    for mode in ("baseline", "with_skill"):
        track_root = skill_exec_root / mode
        if track_root.exists():
            stage_payload = _refresh_stage_metrics(track_root, mode)
            if stage_payload is not None:
                stage_updates[mode] = stage_payload

    return {
        "source": source,
        "skill": skill,
        "repaired_task_metrics": repaired_files,
        "changed_task_metrics": changed_files,
        "sanitized_task_metrics": sanitized_files,
        "modes_touched": sorted(modes_touched),
        "stage_metrics_refreshed": sorted(stage_updates),
        "baseline_tokens": stage_updates.get("baseline", {}).get("estimated_total_tokens"),
        "with_skill_tokens": stage_updates.get("with_skill", {}).get("estimated_total_tokens"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="从已有产物回填 ExecAgent 字符/token 指标")
    parser.add_argument("--source")
    parser.add_argument("--skill")
    parser.add_argument("--skill-dir", type=Path, help="开源布局的 SOURCE_DIR 路径")
    parser.add_argument("--exec-root", type=Path, default=_DEFAULT_RESULTS_ROOT)
    parser.add_argument("--samples-root", type=Path, default=_DEFAULT_RESULTS_ROOT)
    parser.add_argument("--skills-root", type=Path)
    parser.add_argument("--all", action="store_true", help="处理 exec-root 下所有 skill")
    parser.add_argument("--manifest", type=Path, default=None,
                        help="benchmark_manifest.json 路径；若提供，回填仅处理 manifest 中的功能任务"
                             "（以 manifest 标记为唯一来源，不凭空补算非标记任务）")
    args = parser.parse_args()

    # 以 manifest 功能任务为唯一来源：仅回填 manifest 中出现的功能任务
    manifest_allow: set[str] | None = None
    if args.manifest is not None:
        if not args.manifest.exists():
            parser.error(f"--manifest 指定文件不存在：{args.manifest}")
        mdata, _ = _load_json_tolerant(args.manifest)
        ft = (mdata or {}).get("functional_tasks", []) if isinstance(mdata, dict) else []
        manifest_allow = {
            str(t.get("id")) for t in ft if isinstance(t, dict) and t.get("id")
        }
        if not manifest_allow:
            parser.error(f"--manifest 中未找到任何 functional_tasks.id：{args.manifest}")

    results: list[dict[str, Any]] = []
    if args.all:
        for skill_root in sorted(path for path in args.exec_root.iterdir() if path.is_dir()):
            if (skill_root / "exec" / "results").exists():
                try:
                    result = repair_skill(
                        args.exec_root, args.samples_root, args.skills_root, "", skill_root.name,
                        manifest_allow=manifest_allow,
                    )
                    results.append(result)
                    print(f"✅ 已修复 {skill_root.name}: baseline_tokens={result['baseline_tokens']}")
                except Exception as exc:
                    print(f"❌ 修复失败 {skill_root.name}: {exc}")
        print(json.dumps({"processed": len(results)}, ensure_ascii=False))
        return 0

    if args.skill_dir:
        skill_name = args.skill or args.skill_dir.resolve().name
        result = repair_skill(
            args.exec_root, args.samples_root, args.skills_root, "", skill_name,
            skill_dir_override=args.skill_dir, manifest_allow=manifest_allow,
        )
    elif args.source and args.skill:
        result = repair_skill(
            args.exec_root, args.samples_root, args.skills_root, args.source, args.skill,
            manifest_allow=manifest_allow,
        )
    else:
        parser.error("必须指定 --all、--skill-dir 或同时指定 --source 和 --skill")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
