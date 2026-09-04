#!/usr/bin/env python3
"""功能任务通用评分断言库（functional_checks）。

本模块是「功能任务脚手架生成器」的复用检查内核，被生成到每个 case 的
Grader/_checks.py。它只实现**与具体被测技能无关的通用校验种类**（字段存在、
字段取值、JSON 合法性、产物文件存在、子串包含等），不内嵌任何技能业务逻辑、
不引用任何特定技能名或本评测器本身。所有具体断言由脚手架生成器写入
的 CHECK 字典（kind/字段路径/期望值）驱动，满足"脚本化不绑定特定被测技能"的
通用性前提。

CHECK 字典约定（由 generate_functional_scaffolds 写入每个 Rn.py 的 CHECK 变量）：
  {
    "kind": "field_exists" | "field_equals" | "json_valid" |
            "result_file_exists" | "contains_substring",
    "path": "$.status",            # json_pointer 风格（仅 $ 根 + .字段）
    "expected": "pass",            # field_equals 用
    "substring": "..."             # contains_substring 用
  }
"""

from __future__ import annotations

import json
from pathlib import Path


def _get_path(data: object, pointer: str):
    """极简 $.a.b 取值；不支持数组索引（功能产物多为扁平结构）。"""
    if not pointer.startswith("$"):
        return None
    cur = data
    for part in pointer[1:].split("."):
        if part == "":
            continue
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def run_check(check: dict, result_file: Path) -> dict:
    """对一个 CHECK 执行通用断言，返回标准评分结果字典。"""
    kind = check.get("kind", "custom")
    rid = check.get("rubric_id", "?")

    def _fail(reason: str) -> dict:
        return {"rubric_id": rid, "passed": False, "score": 0, "reason": reason, "evidence": {}}

    def _ok(reason: str, evidence: dict | None = None) -> dict:
        return {"rubric_id": rid, "passed": True, "score": 1, "reason": reason,
                "evidence": evidence or {}}

    try:
        if not result_file.exists():
            return _fail(f"主结果物缺失：{result_file}")
        raw = result_file.read_text(encoding="utf-8").strip()
        if not raw:
            return _fail("主结果物为空")
    except Exception as e:  # noqa: BLE001
        return _fail(f"读取主结果物异常：{e}")

    if kind == "result_file_exists":
        return _ok("主结果物存在")

    try:
        data = json.loads(raw)
    except Exception as e:  # noqa: BLE001
        if kind == "json_valid":
            return _fail(f"结果非合法 JSON：{e}")
        return _fail(f"结果非合法 JSON：{e}")

    if kind == "json_valid":
        return _ok("结果为合法 JSON")

    if kind == "field_exists":
        val = _get_path(data, check.get("path", ""))
        if val is None:
            return _fail(f"字段缺失：{check.get('path')}")
        return _ok(f"字段存在：{check.get('path')}", {"value": str(val)})

    if kind == "field_equals":
        val = _get_path(data, check.get("path", ""))
        exp = check.get("expected")
        if val is None:
            return _fail(f"字段缺失：{check.get('path')}")
        if str(val) != str(exp):
            return _fail(f"字段值不符：{check.get('path')}={val!r} 期望 {exp!r}")
        return _ok(f"字段值匹配：{check.get('path')}={val!r}")

    if kind == "contains_substring":
        sub = check.get("substring", "")
        if sub and sub in raw:
            return _ok(f"结果含子串：{sub!r}")
        return _fail(f"结果不含子串：{sub!r}")

    # 未知 kind：保守判失败，避免静默通过
    return _fail(f"未知校验种类：{kind}")
