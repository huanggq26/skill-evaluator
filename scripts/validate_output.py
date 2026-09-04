#!/usr/bin/env python3
"""验证 SpecAgent 输出与 Template.json 和 Template.csv 的结构一致性。"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from _common import load_json


SKILL_ROOT = Path(__file__).resolve().parent.parent


def resolve_path(raw: str) -> Path:
    """解析用户输入路径：绝对或已存在的相对路径原样返回；否则回退到技能根目录再解析。

    解决从历史会话暴露的问题：在 scripts/ 子目录下以相对路径传入 assets/Template.json 会解析失败。
    """
    candidate = Path(raw)
    if candidate.is_absolute() or candidate.exists():
        return candidate
    alt = (SKILL_ROOT / raw).resolve()
    if alt.exists():
        return alt
    return candidate


def load_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]
        return list(reader.fieldnames or []), rows


def is_path_dynamic(path: str, dynamic_paths: set[str]) -> bool:
    """检查路径是否是动态路径或具有动态父路径。"""
    clean_path = path.lstrip("$.")
    clean_parts = clean_path.split(".") if clean_path else []

    for i in range(len(clean_parts), 0, -1):
        check_path = ".".join(clean_parts[:i])
        if check_path in dynamic_paths:
            return True
    return False


def compare_structure(
    template: Any, output: Any, path: str = "$", dynamic_paths: set[str] | None = None
) -> list[str]:
    errors: list[str] = []
    if dynamic_paths is None:
        dynamic_paths = set()

    is_dynamic = is_path_dynamic(path, dynamic_paths)

    if isinstance(template, dict):
        if not isinstance(output, dict):
            return [f"{path}: 期望对象类型，实际为 {type(output).__name__}"]
        template_keys = list(template.keys())
        output_keys = list(output.keys())
        if template_keys != output_keys:
            missing = [key for key in template_keys if key not in output]
            extra = [key for key in output_keys if key not in template]
            if missing:
                errors.append(f"{path}: 缺少键 {missing}")
            if extra:
                errors.append(f"{path}: 多余键 {extra}")
            if not missing and not extra and template_keys != output_keys:
                errors.append(f"{path}: 键顺序与模板不一致")
        for key in template_keys:
            if key in output:
                errors.extend(
                    compare_structure(template[key], output[key], f"{path}.{key}", dynamic_paths)
                )
        return errors

    if isinstance(template, list):
        if not isinstance(output, list):
            return [f"{path}: 期望数组类型，实际为 {type(output).__name__}"]
        if not is_dynamic and len(template) != len(output):
            errors.append(f"{path}: 期望数组长度 {len(template)}，实际为 {len(output)}")
            return errors
        if not is_dynamic and len(template) > 0:
            for index, item in enumerate(template):
                if index < len(output):
                    errors.extend(
                        compare_structure(item, output[index], f"{path}[{index}]", dynamic_paths)
                    )
        return errors

    return errors


def flatten_leaves(data: Any, path: str = "") -> dict[str, Any]:
    leaves: dict[str, Any] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            next_path = f"{path}.{key}" if path else key
            leaves.update(flatten_leaves(value, next_path))
        return leaves
    if isinstance(data, list):
        for index, value in enumerate(data):
            next_path = f"{path}[{index}]"
            leaves.update(flatten_leaves(value, next_path))
        return leaves
    leaves[path] = data
    return leaves


def validate_csv(
    template_rows: list[dict[str, str]],
    output_header: list[str],
    output_rows: list[dict[str, str]],
) -> list[str]:
    errors: list[str] = []
    expected_header = list(template_rows[0].keys()) if template_rows else []
    if output_header != expected_header:
        errors.append(f"Template.csv 表头不匹配: 期望 {expected_header}，实际 {output_header}")

    expected_paths = [row["json_path"] for row in template_rows]
    output_paths = [row.get("json_path", "") for row in output_rows]
    if output_paths != expected_paths:
        missing = [path for path in expected_paths if path not in output_paths]
        extra = [path for path in output_paths if path not in expected_paths]
        if missing:
            errors.append(f"Template.csv 缺少 json_path 行: {missing}")
        if extra:
            errors.append(f"Template.csv 有多余 json_path 行: {extra}")
        if not missing and not extra:
            errors.append("Template.csv 行顺序与模板不一致")

    seen = set()
    for row in output_rows:
        json_path = row.get("json_path", "")
        if json_path in seen:
            errors.append(f"Template.csv 重复的 json_path 行: {json_path}")
        seen.add(json_path)
        if row.get("value", "") == "":
            errors.append(
                f"Template.csv 中 {json_path} 的 value 为空；请使用字面值或字符串 'null'"
            )
    return errors


def validate_fixed_template_values(
    template_json: dict[str, Any],
    output_json: dict[str, Any],
    dynamic_paths: set[str],
) -> list[str]:
    errors: list[str] = []
    template_leaves = flatten_leaves(template_json)
    output_leaves = flatten_leaves(output_json)
    for path, template_value in template_leaves.items():
        if path in dynamic_paths:
            continue
        if template_value in (None, ""):
            continue
        if output_leaves.get(path) != template_value:
            errors.append(
                f"{path}: 期望固定模板值 {template_value!r}，实际为 {output_leaves.get(path)!r}"
            )
    return errors


def validate_outputs(
    *,
    template_json_path: Path,
    template_csv_path: Path,
    output_json_path: Path,
    output_csv_path: Path,
) -> dict[str, Any]:
    template_json = load_json(template_json_path)
    output_json = load_json(output_json_path)
    template_csv_header, template_csv_rows = load_csv(template_csv_path)
    output_csv_header, output_csv_rows = load_csv(output_csv_path)

    template_csv_rows = [
        {key: row.get(key, "") for key in template_csv_header} for row in template_csv_rows
    ]
    output_csv_rows = [
        {key: row.get(key, "") for key in output_csv_header} for row in output_csv_rows
    ]

    dynamic_paths = {row["json_path"] for row in template_csv_rows}
    errors = compare_structure(template_json, output_json, dynamic_paths=dynamic_paths)
    errors.extend(validate_csv(template_csv_rows, output_csv_header, output_csv_rows))
    errors.extend(validate_fixed_template_values(template_json, output_json, dynamic_paths))

    if errors:
        return {"success": False, "errors": errors}
    return {"success": True, "errors": []}


def validate_tasks_review_completeness(tasks_json_path: Path) -> list[str]:
    """校验 Tasks.json 评审完成度：安全/功能单元不得遗留 pending 状态。"""
    errors: list[str] = []
    try:
        data = load_json(tasks_json_path)
    except Exception as exc:  # noqa: BLE001
        return [f"Tasks.json 读取失败: {exc}"]
    if not isinstance(data, dict):
        return [f"{tasks_json_path}: Tasks.json 顶层应为对象"]

    for task in data.get("security_tasks", []) or []:
        if str(task.get("state") or "").strip().lower() == "pending":
            errors.append(f"security_tasks[{task.get('task_id')}]: 状态为 pending，安全探测未完成评审")
    for task in data.get("tasks", []) or []:
        if str(task.get("state") or "").strip().lower() == "pending":
            errors.append(f"tasks[{task.get('task_id')}]: 状态为 pending，功能任务未完成评审")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="验证 SpecAgent 的 Template.json 和 Template.csv 输出。")
    parser.add_argument("--template-json", required=True, help="规范 Template.json 路径。")
    parser.add_argument("--template-csv", required=True, help="规范 Template.csv 路径。")
    parser.add_argument("--output-json", required=True, help="生成的 Template.json 路径。")
    parser.add_argument("--output-csv", required=True, help="生成的 Template.csv 路径。")
    parser.add_argument("--tasks-json", default=None, help="可选: Tasks.json 路径，额外校验评审完成度（拒绝 pending）。")
    args = parser.parse_args()

    result = validate_outputs(
        template_json_path=resolve_path(args.template_json),
        template_csv_path=resolve_path(args.template_csv),
        output_json_path=resolve_path(args.output_json),
        output_csv_path=resolve_path(args.output_csv),
    )
    if args.tasks_json:
        completeness_errors = validate_tasks_review_completeness(resolve_path(args.tasks_json))
        if completeness_errors:
            result = result or {}
            result.setdefault("errors", []).extend(completeness_errors)
            result["success"] = False

    if result.get("success"):
        print("SpecAgent 输出验证通过。")
        return

    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(1)


if __name__ == "__main__":
    main()
