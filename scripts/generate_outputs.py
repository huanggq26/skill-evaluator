#!/usr/bin/env python3
"""从评分和证据生成规范的 SpecAgent 模板/报告输出。（中文化版本）"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import re
import sys
from collections import Counter

try:
    from _project_state import detect_project_state
except ImportError:
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    from _project_state import detect_project_state
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _common import (
    _default_results_root,
    _utc_now_iso,
    FUNCTION_TABLE_INTERNAL_KW as _INTERNAL_PROCESS_KW,
    FUNCTION_TABLE_PLACEHOLDER_HITS as _PLACEHOLDER_HITS,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


DEFAULT_RESULTS_ROOT = _default_results_root()
DEFAULT_SKILL_URL_MAP = _PROJECT_ROOT / "references" / "skill_url_map.json"

# 工程根目录（兼容迁移前的 AgentKit 工具链全局变量别名已统一为 REPO_ROOT）。
REPO_ROOT = _PROJECT_ROOT

# 环境阻塞检测规则（关键词匹配）
ENVIRONMENT_BLOCKER_RULES = [
    ("missing_dependency", ("not installed", "command not found", "missing cli", "missing dependency", "module not found")),
    ("missing_browser", ("missing chrome", "chrome not found", "browser binary", "playwright install")),
    ("platform_limitation", ("platform limitation", "platform-specific", "linux only", "windows only", "macos only")),
    ("permission_denied", ("permission denied", "operation not permitted")),
    ("network_failure", ("connection refused", "connection reset", "network is unreachable", "name or service not known", "dns resolution failed", "failed to connect")),
]

# 模板文件路径（可在命令行中覆盖）
TEMPLATE_JSON_PATH = _PROJECT_ROOT / "assets" / "Template.json"
TEMPLATE_CSV_PATH = _PROJECT_ROOT / "assets" / "Template.csv"
VALIDATOR_PATH = _PROJECT_ROOT / "scripts" / "validate_output.py"

# 跨阶段产物路径（命名与 references/config.md 一致；仅用于报告展示索引，不做真实解析）
SPEC_REPORT = "{RESULTS_ROOT}/{skill_name}/spec/benchmark_report.md"
SPEC_SECURITY_METRICS = "{RESULTS_ROOT}/{skill_name}/spec/results/security/metrics.json"
BASELINE_METRICS = "{RESULTS_ROOT}/{skill_name}/exec/baseline/metrics.json"
WITHSKILL_METRICS = "{RESULTS_ROOT}/{skill_name}/exec/with_skill/metrics.json"
SPEC_TASKS_JSON = "{RESULTS_ROOT}/{skill_name}/spec/results/Tasks.json"
SPEC_SCORES_JSON = "{RESULTS_ROOT}/{skill_name}/spec/scores.json"
SPEC_TEMPLATE_CSV = "{RESULTS_ROOT}/{skill_name}/spec/results/Template.csv"


RUNNER_EVALUATOR_MODELS = {
    "kimi": "KimiCode",
    "claude": "ClaudeCode",
    "codex": "Codex",
}


def _read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")





def _display_skill_name(source: str, skill: str) -> str:
    cleaned_source = str(source or "").strip()
    return f"{cleaned_source}/{skill}" if cleaned_source else skill


def _extract_evaluator_model(payload: Any) -> str:
    if isinstance(payload, str):
        return payload.strip()
    if not isinstance(payload, dict):
        return ""

    candidates: list[Any] = [
        payload.get("evaluator_model"),
        payload.get("Evaluator Model"),
    ]
    meta = payload.get("meta")
    if isinstance(meta, dict):
        candidates.extend(
            [
                meta.get("evaluator_model"),
                meta.get("Evaluator Model"),
            ]
        )

    for candidate in candidates:
        value = str(candidate or "").strip()
        if value:
            return value
    return ""


def _resolve_evaluator_model(
    *,
    specs_dir: Path,
    existing_template: dict[str, Any] | None = None,
) -> str:
    for candidate_path in (
        specs_dir / "results" / "Evaluater.json",
        specs_dir / "Evaluater.json",
    ):
        resolved = _extract_evaluator_model(_read_json(candidate_path))
        if resolved:
            return resolved

    resolved_existing = _extract_evaluator_model(existing_template)
    if resolved_existing:
        return resolved_existing

    explicit = str(os.environ.get("SKILLTEST_EVALUATOR_MODEL") or "").strip()
    if explicit:
        return explicit

    runner = str(os.environ.get("SKILLTEST_RUNNER") or "").strip().lower()
    if runner in RUNNER_EVALUATOR_MODELS:
        return RUNNER_EVALUATOR_MODELS[runner]

    return "KimiCode"


def _repo_rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except Exception:
        return path.as_posix()


def _extract_manifest_entries(section: Any) -> list[tuple[str | None, Any]]:
    entries: list[tuple[str | None, Any]] = []
    if isinstance(section, dict):
        for group_name, group_entries in section.items():
            if isinstance(group_entries, list):
                for item in group_entries:
                    entries.append((str(group_name), item))
    elif isinstance(section, list):
        for item in section:
            entries.append((None, item))
    return entries


def _manifest_group_counts(entries: list[tuple[str | None, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for group_name, _ in entries:
        if group_name:
            counts[group_name] += 1
    return counts


def _parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    frontmatter: dict[str, str] = {}
    end_index = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_index = idx
            break
    if end_index is None:
        return {}
    for line in lines[1:end_index]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        frontmatter[key.strip()] = value.strip()
    return frontmatter


def _clean_description_text(text: Any) -> str:
    lines = [line.strip() for line in str(text or "").splitlines()]
    return " ".join(line for line in lines if line)


def _is_usable_description(text: Any) -> bool:
    if not isinstance(text, str):
        return False
    value = _clean_description_text(text)
    if not value:
        return False
    if value in {"---", "|", "|-", "|+", ">", ">-", ">+"}:
        return False
    if re.match(r"^#{1,6}\s+\S", value):
        return False
    if re.match(r"^(name|title|description|metadata|compatibility|allowed-tools)\s*:", value, re.IGNORECASE):
        return False
    return True


def _skill_markdown_body_lines(text: str) -> list[str]:
    lines = text.splitlines()
    if not text.startswith("---") or not lines or lines[0].strip() != "---":
        return lines
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            return lines[idx + 1 :]
    return lines


def _extract_frontmatter_description(text: str) -> str | None:
    lines = text.splitlines()
    if not lines:
        return None

    header_lines: list[str] = []
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if idx > 0 and (stripped.startswith("#") or stripped.startswith("```")):
            break
        header_lines.append(line)

    for index, line in enumerate(header_lines):
        stripped = line.strip()
        if not stripped.lower().startswith("description:"):
            continue

        value = stripped.split("description:", 1)[1].strip()
        if _is_usable_description(value):
            return _clean_description_text(value)

        block_lines: list[str] = []
        for next_index in range(index + 1, len(header_lines)):
            next_line = header_lines[next_index]
            next_stripped = next_line.strip()
            if next_stripped == "---":
                if block_lines:
                    break
                continue
            if next_line.startswith((" ", "\t")):
                block_lines.append(next_stripped)
                continue
            if not next_stripped:
                block_lines.append("")
                continue
            if re.match(r"^[A-Za-z0-9_-]+\s*:", next_stripped):
                break
            break

        cleaned = _clean_description_text("\n".join(block_lines))
        if _is_usable_description(cleaned):
            return cleaned

    return None


def _extract_body_description(text: str) -> str | None:
    paragraph: list[str] = []
    for line in _skill_markdown_body_lines(text):
        stripped = line.strip()
        if not stripped:
            if paragraph:
                break
            continue
        if stripped.startswith("#"):
            if paragraph:
                break
            continue
        candidate = stripped.lstrip(">").strip()
        if not candidate:
            if paragraph:
                break
            continue
        paragraph.append(candidate)

    cleaned = _clean_description_text("\n".join(paragraph))
    if _is_usable_description(cleaned):
        return cleaned
    return None


def _slugify_skill_label(value: Any) -> str:
    cleaned = str(value or "").strip().lower().strip("'\"`")
    cleaned = cleaned.replace(" / ", "-").replace("/", "-")
    cleaned = re.sub(r"[^a-z0-9]+", "-", cleaned)
    return cleaned.strip("-")


def _strip_version_suffix(skill: str) -> str:
    return re.sub(r"-\d+\.\d+\.\d+(?:-[a-z]+)?$", "", skill)


def _skill_aliases(skill: str, frontmatter: dict[str, str]) -> list[str]:
    aliases: list[str] = []
    for candidate in (
        skill,
        _strip_version_suffix(skill),
        frontmatter.get("slug"),
        frontmatter.get("name"),
    ):
        slug = _slugify_skill_label(candidate)
        if slug and slug not in aliases:
            aliases.append(slug)
    for alias in list(aliases):
        if alias.endswith("-skill") and alias[:-6] and alias[:-6] not in aliases:
            aliases.append(alias[:-6])
    return aliases


def _first_public_url(*values: Any) -> str | None:
    for value in values:
        candidate = _optional_text(value)
        if candidate and (candidate.startswith("https://") or candidate.startswith("http://")):
            return candidate
    return None


# 从 JSON 文件加载 URL 映射（可选，缺失时降级到硬编码）
_url_map_cache: dict[str, dict[str, tuple[str, str]]] | None = None


def _load_url_map(url_map_path: Path | None = None) -> dict[str, dict[str, tuple[str, str]]]:
    """加载技能 URL 映射表，优先从 JSON 文件读取，文件缺失时降级到硬编码数据。"""
    global _url_map_cache
    if _url_map_cache is not None:
        return _url_map_cache

    path = url_map_path or DEFAULT_SKILL_URL_MAP
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            result: dict[str, dict[str, tuple[str, str]]] = {}
            for source_key in ("SkillSh", "ClawHub"):
                entries = data.get(source_key, {})
                result[source_key] = {k: tuple(v) for k, v in entries.items()}
            _url_map_cache = result
            return result
    except (json.JSONDecodeError, OSError):
        pass

    # P5：URL 映射数据已外置到 references/skill_url_map.json（单一权威源，脚本零硬编码）。
    # JSON 缺失/损坏时降级为空映射——canonical URL 弱化，但由 _canonical_skill_urls
    # 末尾 return "", "" 兜底，不断错（不因缺映射而崩溃）。
    print("⚠ 技能 URL 映射 JSON 缺失或不可解析，canonical URL 降级为空"
          f"（期望文件：{DEFAULT_SKILL_URL_MAP}）", file=sys.stderr)
    _url_map_cache = {"SkillSh": {}, "ClawHub": {}}
    return _url_map_cache


def _canonical_skill_urls(source: str, skill: str, frontmatter: dict[str, str],
                          url_map: dict[str, dict[str, tuple[str, str]]] | None = None) -> tuple[str, str]:
    aliases = _skill_aliases(skill, frontmatter)
    if source == "Anthropic":
        slug = _strip_version_suffix(skill)
        return (
            f"https://skills.sh/anthropics/skills/{slug}",
            f"https://github.com/anthropics/skills/blob/main/skills/{slug}/SKILL.md",
        )
    if url_map is None:
        url_map = _load_url_map()
    if source == "SkillSh":
        skillsh_map = url_map.get("SkillSh", {})
        for alias in aliases:
            if alias in skillsh_map:
                return skillsh_map[alias]
    if source == "ClawHub":
        clawhub_map = url_map.get("ClawHub", {})
        for alias in aliases:
            if alias in clawhub_map:
                return clawhub_map[alias]
    return "", ""


def _default_skill_urls(source: str, skill: str, frontmatter: dict[str, str]) -> tuple[str, str]:
    canonical = _canonical_skill_urls(source, skill, frontmatter)
    if any(canonical):
        return canonical
    if source == "Anthropic":
        slug = _strip_version_suffix(skill)
        base = f"https://skills.sh/anthropics/skills/{slug}"
        raw = f"https://github.com/anthropics/skills/blob/main/skills/{slug}/SKILL.md"
        return base, raw
    return "", ""


def _optional_text(value: Any) -> str | None:
    cleaned = str(value or "").strip()
    return cleaned or None


def _load_skill_metadata(
    *,
    source: str,
    skill: str,
    skill_dir: Path,
    samples_dir: Path,
    existing_template: dict[str, Any] | None,
) -> dict[str, Any]:
    display_name = _display_skill_name(source, skill)
    benchmark_manifest = _read_json(samples_dir / "benchmark_manifest.json") or {}
    skill_md_text = _read_text(skill_dir / "SKILL.md")
    frontmatter = _parse_frontmatter(skill_md_text)
    existing_meta = (existing_template or {}).get("meta", {}) if isinstance(existing_template, dict) else {}

    default_skill_url, default_download_url = _default_skill_urls(source, skill, frontmatter)
    description = ""
    for candidate in (
        _extract_frontmatter_description(skill_md_text),
        str(benchmark_manifest.get("skill_description") or "").strip(),
        str(existing_meta.get("description") or "").strip(),
    ):
        if _is_usable_description(candidate):
            description = _clean_description_text(candidate)
            break

    if not description:
        description = _extract_body_description(skill_md_text) or ""

    if not description:
        description = f"{display_name} 的基准生成元数据。"

    frontmatter_homepage = _optional_text(frontmatter.get("homepage"))
    skill_url = _first_public_url(
        default_skill_url,
        benchmark_manifest.get("skill_url"),
        existing_meta.get("skill_url"),
        frontmatter_homepage,
    )
    download_url = _first_public_url(
        default_download_url,
        benchmark_manifest.get("download_url"),
        existing_meta.get("download_url"),
        frontmatter_homepage,
        skill_url,
    )

    return {
        "description": description,
        "skill_url": skill_url,
        "download_url": download_url,
    }


def _load_manifest_summary(samples_dir: Path, tasks_data: dict[str, Any]) -> dict[str, Any]:
    manifest = _read_json(samples_dir / "benchmark_manifest.json") or {}
    functional_entries = _extract_manifest_entries(
        manifest.get("functional_tasks") or manifest.get("tasks") or []
    )
    security_entries = _extract_manifest_entries(
        manifest.get("security_probes") or manifest.get("security_tests") or []
    )

    functional_counts = _manifest_group_counts(functional_entries)
    security_counts = _manifest_group_counts(security_entries)
    summary = manifest.get("summary") if isinstance(manifest.get("summary"), dict) else {}

    total_functional = (
        summary.get("total_functional_tasks")
        or summary.get("functional_task_count")
        or len(functional_entries)
        or len(tasks_data.get("tasks", []))
    )
    common_count = summary.get("common_tasks") or functional_counts.get("common") or functional_counts.get("common_tasks")
    hard_count = summary.get("hard_tasks") or functional_counts.get("hard") or functional_counts.get("hard_tasks")
    total_security = (
        summary.get("total_security_tests")
        or summary.get("security_probe_count")
        or len(security_entries)
        or len(tasks_data.get("security_tasks", []))
    )

    security_group_counts = {
        "sg_abnormal_behavior_control": summary.get("abnormal_tests"),
        "sg_permission_boundary": summary.get("permission_tests"),
        "sg_sensitive_data_protection": summary.get("sensitive_tests"),
    }

    if not any(value for value in security_group_counts.values()):
        group_name_map = {
            "abnormal": "sg_abnormal_behavior_control",
            "permission": "sg_permission_boundary",
            "sensitive": "sg_sensitive_data_protection",
        }
        for raw_group, count in security_counts.items():
            mapped = group_name_map.get(raw_group, raw_group)
            security_group_counts[mapped] = count

    capabilities = summary.get("skill_capabilities_tested")
    if not isinstance(capabilities, list):
        capabilities = []

    # 内部策略/过程产物（如脚手架生成）：来自 manifest.internal_checks（tier=l2_internal /
    # user_facing=false），属达成 L0 目标的手段，不计入"用户能力覆盖"（见 SKILL.md「技能目标与产出物层级」）。
    internal_capabilities = []
    for _t in (manifest.get("internal_checks") or []):
        if isinstance(_t, dict):
            _tid = str(_t.get("id", "")).strip()
            if _tid:
                internal_capabilities.append(_tid)

    return {
        "total_functional": int(total_functional or 0),
        "common_count": int(common_count or 0) if common_count is not None else 0,
        "hard_count": int(hard_count or 0) if hard_count is not None else 0,
        "total_security": int(total_security or 0),
        "security_group_counts": security_group_counts,
        "capabilities": [str(item).strip() for item in capabilities if str(item).strip()],
        "internal_capabilities": internal_capabilities,
    }


def _format_functional_scope(summary: dict[str, Any]) -> str:
    total = summary.get("total_functional", 0)
    common_count = summary.get("common_count", 0)
    hard_count = summary.get("hard_count", 0)
    if common_count or hard_count:
        text = f"{total} 个功能任务（{common_count} 个 common + {hard_count} 个 hard）"
    else:
        text = f"{total} 个功能任务"
    capabilities = summary.get("capabilities", [])
    if capabilities:
        preview = "、".join(capabilities[:6])
        if len(capabilities) > 6:
            preview += "、..."
        text += f" 覆盖 {preview}"
    internal = summary.get("internal_capabilities") or []
    if internal:
        # 内部正确性验证用例（如样本包内置的「事件追踪续接逻辑」「只读安全边界纪律」校验）：
        # 验证技能自身的中间产物/过程资产（输出合约 result.json 的结构与合规、防编造/不切源、
        # 只读不越权等行为边界）是否正确，属于开发期回归自检，面向开发者而非终端用户，
        # 故不计入「用户能力覆盖」。内部用例 ID 形如 FTxx_xxx，是评测样本包内置的正确性校验样例，
        # 不是用户能直接感知的功能点。
        text += (
            f"；另有 {len(internal)} 项内部正确性验证（"
            f"{'、'.join(internal)}）——即评测样本包内置的技能自身回归自检用例（如事件追踪 story 续接逻辑、"
            f"只读安全边界纪律），校验技能中间产物/过程资产（输出合约、防编造、不越权等行为边界）是否正确，"
            f"面向开发者而非终端用户，不计入用户能力覆盖"
        )
    return text


def _format_security_scope(summary: dict[str, Any]) -> str:
    total = summary.get("total_security", 0)
    group_counts = summary.get("security_group_counts", {})
    canonical_order = [
        ("sg_abnormal_behavior_control", "异常行为管控"),
        ("sg_permission_boundary", "权限边界"),
        ("sg_sensitive_data_protection", "敏感数据保护"),
    ]
    parts = []
    present_groups = 0
    for key, label in canonical_order:
        value = group_counts.get(key)
        if value:
            present_groups += 1
            parts.append(f"{label}（{int(value)} 个）")
    if parts:
        return f"{total} 个安全探测，跨 {present_groups} 个维度：" + "、".join(parts)
    return f"{total} 个安全探测"


def _ratio_text(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        numeric = float(value)
    except Exception:
        return "N/A"
    return f"{numeric:+.2%}"


def _change_phrase(value: Any, increase_word: str = "增加", decrease_word: str = "减少") -> str:
    """带符号效能/开销变化措辞。

    value = 效能增值 = (baseline - with_skill) / baseline：
      - ``>0`` 表示 with_skill 用时/开销更少（正向作用）→ 用 decrease_word（默认"减少"）；
      - ``<0`` 表示 with_skill 反而更久/更多（反向作用）→ 用 increase_word（调用处传"反而增加"）。
    例：``+0.5`` → "减少 50.0%"；``-2.0`` → "反而增加 200.0%（约 3.00 倍）"。
    """
    if value is None:
        return "N/A"
    try:
        numeric = float(value)
    except Exception:
        return "N/A"
    if numeric > 0.005:
        return f"{decrease_word} {numeric:.1%}"
    if numeric < -0.005:
        return f"{increase_word} {-numeric:.1%}（约 {1.0 - numeric:.2f} 倍）"
    return "基本持平"


def _task_time_phrase(baseline_time: Any, skill_time: Any) -> str:
    """单任务维度：with_skill 比 baseline 慢还是快，用直观措辞。"""
    bt = _as_float(baseline_time)
    st = _as_float(skill_time)
    if bt is None or st is None or bt <= 0:
        return "N/A"
    ratio = (st - bt) / bt
    if ratio > 0.005:
        return f"with_skill 慢 {ratio:.1%}（{st / bt:.2f} 倍）"
    if ratio < -0.005:
        return f"with_skill 快 {-ratio:.1%}"
    return "基本持平"


def _score_text(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.2f}"
    except Exception:
        return "N/A"


def _count_text(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        numeric = float(value)
    except Exception:
        return "N/A"
    if numeric.is_integer():
        return f"{int(numeric):,}"
    return f"{numeric:,.4f}".rstrip("0").rstrip(".")


def _yn(value: Any) -> str:
    """把 True/1/'true' 等成败标记翻译成人话「是 / 否」。"""
    if value is True or value == 1 or (isinstance(value, str) and value.strip().lower() in ("true", "1", "yes")):
        return "是"
    if value is False or value == 0 or (isinstance(value, str) and value.strip().lower() in ("false", "0", "no")):
        return "否"
    return "N/A" if value is None else str(value)


def _humanize_evidence(text: str, cap_map: dict[str, str] | None = None) -> str:
    """把证据文本里的内部编号/状态码翻译为人话，避免用户读不懂。

    - FT0x_xxx 任务编号 → 能力人话名（取自 cap_map）
    - both_succeed → 双方完成
    """
    if not text:
        return text
    if cap_map:
        import re

        def _repl(m: "re.Match[str]") -> str:
            return cap_map.get(m.group(0), m.group(0))

        text = re.sub(r"FT\d+_[A-Za-z0-9_]+", _repl, text)
    return text.replace("both_succeed", "双方完成")


def _humanize_grader_notes(text: str) -> str:
    """把 Grader 原始结论（backfill 写入 notes 的英文串）翻译为人话。

    - ``Grader 结果: pass (n/m)`` → "Grader 判定：通过（n/m 项检查点通过）"
    - ``must_pass_satisfied=True/False`` → 解释"关键强制检查点是否全部满足"
    """
    if not text:
        return text
    import re

    m = re.search(r"Grader 结果:\s*(\w+)\s*\((\d+)/(\d+)\)", text)
    if m:
        status, passed, total = m.group(1), m.group(2), m.group(3)
        status_cn = "通过" if status.lower() == "pass" else "未通过"
        text = f"Grader 判定：{status_cn}（{passed}/{total} 项检查点通过）"
    text = re.sub(
        r"must_pass_satisfied\s*=\s*(True|False)",
        lambda mm: "关键强制检查点（标记为 must_pass 的检查）全部满足" if mm.group(1) == "True" else "存在关键强制检查点未满足",
        text,
    )
    return text


def _percent_text(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        numeric = float(value)
    except Exception:
        return "N/A"
    return f"{numeric:.2f}%"


def _canonical_dimension_name(raw: str) -> str:
    mapping = {
        "sg_abnormal_behavior_control": "异常行为管控",
        "sg_permission_boundary": "权限边界",
        "sg_sensitive_data_protection": "敏感数据保护",
    }
    return mapping.get(raw, raw.replace("_", " ").strip().title())


def _load_validator() -> Any:
    spec = importlib.util.spec_from_file_location("specagent_validate_template_output", VALIDATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load validator from {VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _flatten_leaves(data: Any, path: str = "") -> dict[str, Any]:
    leaves: dict[str, Any] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            next_path = f"{path}.{key}" if path else key
            leaves.update(_flatten_leaves(value, next_path))
        return leaves
    if isinstance(data, list):
        for index, value in enumerate(data):
            next_path = f"{path}[{index}]"
            leaves.update(_flatten_leaves(value, next_path))
        return leaves
    leaves[path] = data
    return leaves


def _csv_literal(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (int, float)):
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)
    return str(value)


def _normalize_state(value: Any) -> str:
    return str(value or "").strip().lower()


def _state_is_pass(value: Any) -> bool:
    if isinstance(value, dict):
        value = value.get("state")
    return _normalize_state(value) == "pass"


# 机器门禁评分项：R4（声明数据字段/结构校验）、R6（产物状态/文件校验）属结构性机器可判项，
# 不进入人读报告叙事，改为流水线机器门禁（对齐 AGENTS_RULES「报告去噪·机器门禁」+ stage1_sample.md 步骤 2 第 8 点）。
_MACHINE_GATE_RUBRICS = frozenset({"R4", "R6"})


def _is_machine_gate_entry(text: str) -> bool:
    """判断失败叙事文本是否指向机器门禁评分项（R4/R6）。

    匹配规则：文本中出现独立 rubric 标识 ``R4`` 或 ``R6``（词边界，避免误匹配 R40 之类）。
    """
    import re

    return bool(re.search(r"\bR[46]\b", text))


def _summarize_failed_checks(items: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """汇总失败叙事，分离人读项与机器门禁项。

    Returns:
        (human_failures, gate_failures)：人读叙事项（供报告正文/建议）、
        机器门禁项（R4/R6，仅计数、不渲染到报告叙事）。
    """
    human: Counter[str] = Counter()
    gate: Counter[str] = Counter()
    for item in items:
        failed_checks = item.get("failed_checks")
        if isinstance(failed_checks, list):
            for entry in failed_checks:
                if isinstance(entry, str) and entry.strip():
                    target = gate if _is_machine_gate_entry(entry) else human
                    target[entry.strip()] += 1

        for key in ("review_notes", "notes", "audit_note", "message"):
            text = str(item.get(key) or "").strip()
            if text:
                target = gate if _is_machine_gate_entry(text) else human
                target[text] += 1
                break
    return [entry for entry, _ in human.most_common(3)], [entry for entry, _ in gate.most_common(3)]


def _find_task_entry(scores_tasks: list[dict[str, Any]], task_id: str) -> dict[str, Any] | None:
    for item in scores_tasks:
        if str(item.get("task_id")) == task_id:
            return item
    return None


def _build_non_skill_failure(
    *,
    exec_dir: Path,
    scores: dict[str, Any],
) -> tuple[str, str]:
    results_dir = exec_dir / "results"
    evidence: list[str] = []
    seen_paths: set[str] = set()

    if results_dir.exists():
        for path in results_dir.rglob("*"):
            if not path.is_file():
                continue
            texts: list[str] = []
            if path.name in {"agent_worklog.log", "worklog.log"}:
                try:
                    texts.append(path.read_text(encoding="utf-8", errors="ignore"))
                except Exception:
                    continue
            elif path.name == "task_metrics.json":
                payload = _read_json(path)
                if not isinstance(payload, dict):
                    continue
                for key in ("thoutlog", "error", "error_message", "stderr", "stdout", "exception", "failure_reason", "status_reason"):
                    value = payload.get(key)
                    if isinstance(value, str) and value.strip():
                        texts.append(value)
            else:
                continue

            if not texts:
                continue

            lowered = "\n".join(texts).lower()
            for _, keywords in ENVIRONMENT_BLOCKER_RULES:
                if any(keyword in lowered for keyword in keywords):
                    rel = _repo_rel(path)
                    if rel not in seen_paths:
                        seen_paths.add(rel)
                        evidence.append(rel)
                    break

    if evidence:
        preview = ", ".join(evidence[:4])
        if len(evidence) > 4:
            preview += ", ..."
        return "no", f"Environment or dependency blockage detected in execution artifacts: {preview}."

    return "yes", "No environment or dependency blockage detected."


def _build_utility_evidence(
    scores: dict[str, Any],
    cap_map: dict[str, str] | None = None,
) -> dict[str, str]:
    tasks = [item for item in scores.get("tasks", []) if isinstance(item, dict)]
    valid_task_count = int(scores.get("valid_task_count") or 0)
    incremental_tasks = [item for item in tasks if item.get("scoring_path") == "incremental_utility"]
    both_success_tasks = [item for item in tasks if item.get("scoring_path") == "both_succeed"]
    both_success_comparable = [item for item in both_success_tasks if item.get("comparable")]
    skill_failed_tasks = [item for item in tasks if item.get("scoring_path") == "skill_failed"]

    # 用「用户视角行为语义」代替内部任务代号（FTxx_xxx 等），避免读者看不懂。
    def _name(item: dict[str, Any]) -> str:
        _tid = str(item.get("task_id"))
        return (cap_map or {}).get(_tid, _tid)

    incremental_names = "、".join(_name(item) for item in incremental_tasks)
    if incremental_tasks:
        incremental_evidence = (
            f"{valid_task_count} 个任务中有 {len(incremental_tasks)} 个展现了增量效用"
            f"（baseline 失败且 with_skill 通过，即只有 with_skill 能完成）：{incremental_names}。"
        )
    else:
        incremental_evidence = f"{valid_task_count} 个任务中，0 个展现增量效用。"

    token_best = max(
        (item for item in both_success_comparable if item.get("token_efficiency_subscore") is not None),
        key=lambda item: float(item.get("token_efficiency_subscore")),
        default=None,
    )
    token_worst = min(
        (item for item in both_success_comparable if item.get("token_efficiency_subscore") is not None),
        key=lambda item: float(item.get("token_efficiency_subscore")),
        default=None,
    )
    _comp_btk = sum(_as_float(t.get("baseline_tokens")) or 0.0 for t in both_success_comparable)
    _comp_stk = sum(_as_float(t.get("skill_tokens")) or 0.0 for t in both_success_comparable)
    _comp_tk_change = (_comp_btk - _comp_stk) / _comp_btk if _comp_btk > 0 else None
    token_evidence = (
        f"Token 效率子评分 {_score_text(scores.get('token_efficiency_subscore'))}。"
        f" 可比任务 baseline token 数 {_count_text(_comp_btk)}，"
        f" with_skill token 数 {_count_text(_comp_stk)}，"
        f" 变化 {_change_phrase(_comp_tk_change, '增加', '减少')}。"
    )
    if token_best and token_worst and _name(token_best) != _name(token_worst):
        token_evidence += (
            f" 最优双成功任务：{_name(token_best)} "
            f"（{_score_text(token_best.get('token_efficiency_subscore'))}）；"
            f"最差：{_name(token_worst)} "
            f"（{_score_text(token_worst.get('token_efficiency_subscore'))}）。"
        )
    elif token_best:
        token_evidence += (
            f" 唯一可比任务：{_name(token_best)}"
            f"（token 效率子评分 {_score_text(token_best.get('token_efficiency_subscore'))}）。"
        )

    time_best = max(
        (item for item in both_success_comparable if item.get("time_efficiency_subscore") is not None),
        key=lambda item: float(item.get("time_efficiency_subscore")),
        default=None,
    )
    time_worst = min(
        (item for item in both_success_comparable if item.get("time_efficiency_subscore") is not None),
        key=lambda item: float(item.get("time_efficiency_subscore")),
        default=None,
    )
    _comp_bt = sum(_as_float(t.get("baseline_time")) or 0.0 for t in both_success_comparable)
    _comp_st = sum(_as_float(t.get("skill_time")) or 0.0 for t in both_success_comparable)
    _comp_t_change = (_comp_bt - _comp_st) / _comp_bt if _comp_bt > 0 else None
    time_evidence = (
        f"时间效率子评分 {_score_text(scores.get('time_efficiency_subscore'))}。"
        f" 可比任务 baseline 耗时 {_count_text(_comp_bt)}，"
        f" with_skill 耗时 {_count_text(_comp_st)}，"
        f" 变化 {_change_phrase(_comp_t_change, '反而增加', '减少')}。"
    )
    if time_best and time_worst and _name(time_best) != _name(time_worst):
        time_evidence += (
            f" 最优双成功任务：{_name(time_best)} "
            f"（{_score_text(time_best.get('time_efficiency_subscore'))}）；"
            f"最差：{_name(time_worst)} "
            f"（{_score_text(time_worst.get('time_efficiency_subscore'))}）。"
        )
    elif time_best:
        time_evidence += (
            f" 唯一可比任务：{_name(time_best)}"
            f"（时间效率子评分 {_score_text(time_best.get('time_efficiency_subscore'))}）。"
        )

    score_best = max(
        (item for item in both_success_comparable if item.get("task_score") is not None),
        key=lambda item: float(item.get("task_score")),
        default=None,
    )
    score_worst = min(
        (item for item in both_success_comparable if item.get("task_score") is not None),
        key=lambda item: float(item.get("task_score")),
        default=None,
    )
    both_success_evidence = f"{len(both_success_comparable)} 个（可比）任务沿双成功评分分支计算。"
    if score_best and score_worst and _name(score_best) != _name(score_worst):
        both_success_evidence += (
            f" 最优任务评分：{_name(score_best)}（{_score_text(score_best.get('task_score'))}）；"
            f"最差：{_name(score_worst)}（{_score_text(score_worst.get('task_score'))}）。"
        )
    elif score_best:
        both_success_evidence += (
            f" 唯一可比任务：{_name(score_best)}（任务评分 {_score_text(score_best.get('task_score'))}）。"
        )
    if not both_success_tasks:
        both_success_evidence += " 没有任何任务进入直接效率对比。"

    human_failures, gate_failures = _summarize_failed_checks([row for row in tasks if not _state_is_pass(row)])
    summary_parts = [
        f"效用评分 {_score_text(scores.get('utility_score'))}（基于 {valid_task_count} 个有效任务）。",
        f"增量效用任务：{len(incremental_tasks)} 个。",
        f"双成功任务：{len(both_success_tasks)} 个。",
        f"技能失败任务：{len(skill_failed_tasks)} 个。",
    ]
    if human_failures:
        summary_parts.append("最常见的失败评分项/审查项：" + "；".join(human_failures) + "。")
    if gate_failures:
        summary_parts.append(
            "机器门禁失败（R4/R6，不计入人读叙事）：" + "；".join(gate_failures) + "。"
        )
    utility_summary = " ".join(summary_parts)

    return {
        "summary": utility_summary,
        "incremental": incremental_evidence,
        "token": token_evidence,
        "time": time_evidence,
        "both_success": both_success_evidence,
    }


def _ensure_sentence(text: Any) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    if value.endswith((".", "!", "?")):
        return value
    return value + "."


def _normalize_space(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _description_core_text(description: Any) -> str:
    value = _normalize_space(description)
    if not value:
        return ""
    value = re.sub(r"`([^`]*)`", r"\1", value)
    core = re.split(r"\bUse (?:when|whenever|this when)\b", value, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    if not core:
        core = re.split(r"(?<=[.!?\u3002\uFF01\uFF1F])\s+", value, maxsplit=1)[0].strip()
    core = core.rstrip(".!?\u3002\uFF01\uFF1F").strip()
    if len(core) > 260:
        sentences = [
            sentence.strip().rstrip(".!?\u3002\uFF01\uFF1F").strip()
            for sentence in re.split(r"(?<=[.!?\u3002\uFF01\uFF1F])\s+", core)
            if sentence.strip()
        ]
        kept: list[str] = []
        for sentence in sentences:
            candidate = " ".join(f"{item}." for item in [*kept, sentence]).strip()
            if len(candidate) <= 260:
                kept.append(sentence)
            else:
                break
        if kept:
            core = " ".join(f"{item}." for item in kept).rstrip(".!?\u3002\uFF01\uFF1F").strip()
        else:
            core = core[:257].rsplit(" ", 1)[0].rstrip(" ,;:") + "..."
    return core


def _lowercase_initial(text: str) -> str:
    if not text:
        return ""
    first = text[0]
    if first.isalpha():
        return first.lower() + text[1:]
    return text


def _join_list(items: list[str]) -> str:
    values = [item.strip() for item in items if item and item.strip()]
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} 和 {values[1]}"
    return "、".join(values[:-1]) + f" 和 {values[-1]}"


def _description_function_sentence(source: str, skill: str, description: Any) -> str:
    display_name = _display_skill_name(source, skill)
    core = _description_core_text(description)
    if not core:
        return (
            f"{display_name} 在当前元数据中未提供足够具体的功能描述，"
            "因此摘要只能依据已评审的输出内容。"
        )
    segments = [
        segment.strip().rstrip(".!?\u3002\uFF01\uFF1F").strip()
        for segment in re.split(r"(?<=[.!?\u3002\uFF01\uFF1F])\s+", core)
        if segment.strip()
    ]
    if segments:
        primary = segments[0]
        extras = [_lowercase_initial(segment) for segment in segments[1:3]]
        core = "; ".join([primary, *extras]).strip()
    lowered = _lowercase_initial(core)
    if re.match(r"^(a|an|the)\b", lowered):
        return f"{display_name} 被描述为：{lowered}。"
    return f"{display_name} 旨在{lowered}。"


def _description_security_surface_sentence(source: str, skill: str, description: Any) -> str:
    display_name = _display_skill_name(source, skill)
    value = _normalize_space(description).lower()
    surfaces: list[str] = []

    if any(token in value for token in ("skill", "prompt", "benchmark", "eval", "evaluation", "description")):
        surfaces.append("编辑指令文件，处理基准或评估产物")
    if any(token in value for token in ("file", "document", "docx", "pdf", "slide", "ppt", "csv", "json", "image", "video", "markdown")):
        surfaces.append("读取或写入面向用户的文件")
    if any(token in value for token in ("web", "browser", "page", "site", "url")):
        surfaces.append("浏览器或网页相关操作")
    if any(token in value for token in ("api", "github", "slack", "calendar", "email", "google", "notion", "deploy", "cloud", "aws", "gcp", "azure", "network")):
        surfaces.append("访问外部服务及凭据受限操作")
    if any(token in value for token in ("parse", "extract", "transform", "convert", "measure", "analy", "summar")):
        surfaces.append("解析、转换或分析用户提供的内容")
    if any(token in value for token in ("secret", "credential", "token", "password", "sensitive", "pii")):
        surfaces.append("处理潜在的敏感数据")

    if not surfaces:
        surfaces.append("提示词驱动的内容生成与结果文件输出")

    return (
        f"对于 {display_name}，其描述的工作流主要涉及{_join_list(surfaces[:3])}，"
        "因此这些攻击面是安全评审的主要关注点。"
    )


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _score_band(value: Any) -> str:
    numeric = _as_float(value)
    if numeric is None:
        return "不可用"
    if numeric >= 95:
        return "在当前样本下表现很好"
    if numeric >= 80:
        return "在当前样本下表现较好"
    if numeric >= 65:
        return "在当前样本下可用但略有不均"
    if numeric >= 50:
        return "在当前样本下表现参差"
    if numeric > 0:
        return "在当前样本下表现有限"
    return "本次运行未建立有效评分"


def _time_observation(scores: dict[str, Any]) -> str:
    both_success_tasks = int(_as_float(scores.get("both_success_tasks")) or 0)
    ratio = _as_float(scores.get("efficiency_gain_ratio"))
    if ratio is None:
        ratio = _as_float(scores.get("raw_measurements", {}).get("compare", {}).get("time_change_ratio"))
    if both_success_tasks <= 0 or ratio is None:
        return "当前样本未留下足够稳定的重叠任务，无法进行有意义的直接时间对比。"
    phrase = _change_phrase(ratio, "反而增加", "减少")
    if ratio >= 0.3:
        return f"在两种变体都完成的（可比）任务上，with_skill 路径明显更快（执行时间{phrase}），说明工作流指引降低了执行摩擦。"
    if ratio >= 0.1:
        return f"在两种变体都完成的（可比）任务上，with_skill 路径略快（执行时间{phrase}），说明存在一定的实际工作流效率提升。"
    if ratio > -0.1:
        return f"在两种变体都完成的（可比）任务上，执行耗时与 baseline 接近（{phrase}），因此观测到的价值更多来自工作流指引，而非显著的速度变化。"
    if ratio > -0.5:
        return f"在两种变体都完成的（可比）任务上，with_skill 路径明显慢于 baseline（执行时间{phrase}），其部分功能价值被执行开销抵消。"
    return f"在两种变体都完成的（可比）任务上，with_skill 路径远慢于 baseline（执行时间{phrase}），执行开销成为最终效用读数的主要拖累。"


def _build_time_analysis(
    *,
    scores: dict[str, Any],
    baseline_metrics: dict[str, Any],
    with_skill_metrics: dict[str, Any],
    functional_tasks: list[dict[str, Any]],
    cap_map: dict[str, str] | None = None,
) -> list[str]:
    """动态解读为什么 with_skill 比 baseline 更慢（或更快），给出可理解的归因。

    关键前提（功能进入对比测试的前提）：只有 baseline 与 with_skill 实现「同等功能」的任务
    才进入效能对比。若 baseline 几乎空跑（耗时极低、产出极少），说明其根本未实现目标技能功能，
    与 with_skill 对比既无意义也会误导——此类任务标记为不可比并排除出效能聚合。
    """
    # 仅用「可比」的 both_succeed 任务做聚合，避免退化基准拉偏
    comp = [
        t for t in functional_tasks
        if t.get("scoring_path") == "both_succeed" and t.get("comparable")
    ]
    b_chars = _as_float(baseline_metrics.get("total_characters"))
    s_chars = _as_float(with_skill_metrics.get("total_characters"))
    comp_bt = sum(_as_float(t.get("baseline_time")) or 0.0 for t in comp)
    comp_st = sum(_as_float(t.get("skill_time")) or 0.0 for t in comp)
    if comp_bt <= 0:
        return ["当前可比任务集未留下足够稳定的时间对比数据，无法解读执行耗时差异。"]

    gain = (comp_bt - comp_st) / comp_bt  # 带符号效能增值，+ = with_skill 更快
    items: list[str] = []
    items.append(
        f"总体（仅可比任务，{len(comp)} 个）：with_skill 总耗时 {_count_text(comp_st)}s，"
        f"baseline 总耗时 {_count_text(comp_bt)}s，执行时间{_change_phrase(gain, '反而增加', '减少')}。"
    )
    if b_chars and s_chars and b_chars > 0:
        char_mult = s_chars / b_chars
        items.append(
            f"产出规模：with_skill 总字符数 {_count_text(s_chars)} vs baseline {_count_text(b_chars)}"
            f"（约 {char_mult:.1f} 倍）。产物更厚重是耗时增加的主因之一——技能引导产出了更完整的质量门禁、"
            f"评分、报告与安全脚手架等产物，吞吐更大自然更耗时。"
        )

    # 不可比（baseline 在屏蔽技能内部知识后做不成，须依赖专用知识源）的任务：应排除，不应与 with_skill 做效率对比
    non_comparable = [
        (cap_map or {}).get(str(t.get("task_id")), str(t.get("task_id")))
        for t in functional_tasks
        if t.get("scoring_path") == "both_succeed" and not t.get("comparable")
    ]
    if non_comparable:
        items.append(
            f"已排除、不参与效能聚合的任务（裸 Agent 在屏蔽技能内部知识后做不成，须依赖技能专用知识源，"
            f"与 with_skill 做效率对比会误导）：{_join_list(non_comparable)}。"
            f"这些任务里 with_skill 更慢只是因为 baseline 根本没做同等工作，不能据此判定技能退化。"
        )

    skill_faster: list[str] = []
    skill_slower: list[str] = []
    for t in comp:
        bt = _as_float(t.get("baseline_time"))
        st = _as_float(t.get("skill_time"))
        if bt is None or st is None or bt <= 0:
            continue
        if st < bt * 0.9:
            skill_faster.append(str(t.get("task_id")))
        elif st > bt * 1.1:
            skill_slower.append(str(t.get("task_id")))
    if skill_faster:
        items.append(
            f"技能更快的任务：{_join_list(skill_faster)}，说明在较复杂任务上技能引导可省时。"
        )
    if skill_slower:
        items.append(
            f"技能更慢的任务：{_join_list(skill_slower)}，多因技能引导产出了更多/更规范的产物或引入了编排开销。"
        )
    items.append(
        "结论：with_skill 更慢主要源于「产出更完整 + 技能编排开销」，而非技能无意义；"
        "在复杂任务上已出现省时信号。是否构成「退化」需结合增量覆盖（reach）、产出质量与可比前提综合判断，"
        "不能仅凭耗时下定论。"
    )
    return items


def _blockage_observation(non_skill_state: str, non_skill_reason: str) -> str:
    if non_skill_state == "yes":
        return "评审期间未发现环境或依赖阻塞。"
    return _ensure_sentence(
        non_skill_reason
        or "评审期间发现了环境或依赖阻塞，因此部分较弱的结果可能由执行条件导致，而非技能质量本身"
    )


def _utility_issue_paragraph(scores: dict[str, Any], non_skill_state: str, non_skill_reason: str) -> str:
    issues: list[str] = []
    skill_failed = int(_as_float(scores.get("skill_failed_tasks")) or 0)
    if skill_failed > 0:
        issues.append(
            f"有 {skill_failed} 个 with_skill 任务仍低于最终评分/审查阈值，因此部分失分来自不完整或薄弱的最终交付物，而非仅来自执行尝试本身。"
        )

    ratio = _as_float(scores.get("efficiency_gain_ratio"))
    if ratio is None:
        ratio = _as_float(scores.get("raw_measurements", {}).get("compare", {}).get("time_change_ratio"))
    both_success_tasks = int(_as_float(scores.get("both_success_tasks")) or 0)
    if both_success_tasks > 0 and ratio is not None and abs(ratio) >= 0.1:
        issues.append(_time_observation(scores))
    elif both_success_tasks <= 0 and int(_as_float(scores.get("valid_task_count")) or 0) > 0:
        issues.append("被评审的任务集未留下足够稳定的双通过切片，无法进行有意义的直接质量与时间对比。")

    human_patterns, _gate_patterns = _summarize_failed_checks(
        [row for row in scores.get("tasks", []) if isinstance(row, dict) and not _state_is_pass(row)]
    )
    if human_patterns:
        issues.append("主要的评审拖累来自：" + "；".join(_ensure_sentence(item) for item in human_patterns[:2]))

    if non_skill_state != "yes":
        issues.append(
            _ensure_sentence(
                non_skill_reason
                or "部分较弱的结果也可能受到环境或依赖阻塞的影响，而非仅由技能行为导致"
            )
        )
    return " ".join(issue for issue in issues if issue)


def _security_failure_digest(scores: dict[str, Any], limit: int = 2) -> str:
    failing_rows = [
        row for row in scores.get("security_tasks", [])
        if isinstance(row, dict) and not _state_is_pass(row)
    ]
    if not failing_rows:
        return ""

    parts: list[str] = []
    for row in failing_rows[:limit]:
        dimension = _canonical_dimension_name(str(row.get("security_dimension") or "security"))
        task_id = str(row.get("task_id") or "unknown")
        note = str(row.get("notes") or "").strip()
        if note:
            parts.append(f"{dimension} 在 {task_id} 上失败：{note}")
        else:
            parts.append(f"{dimension} 在 {task_id} 上失败")
    return " ".join(_ensure_sentence(item) for item in parts)


def _build_overall_summary(
    *,
    source: str,
    skill: str,
    description: str,
    scores: dict[str, Any],
    security_metrics: dict[str, Any],
    utility_score: Any,
    security_score: Any,
    non_skill_state: str,
    non_skill_reason: str,
) -> str:
    display_name = _display_skill_name(source, skill)
    valid_task_count = int(_as_float(scores.get("valid_task_count")) or 0)
    incremental = int(_as_float(scores.get("incremental_utility_tasks")) or 0)
    both_success = int(_as_float(scores.get("both_success_tasks")) or 0)
    skill_failed = int(_as_float(scores.get("skill_failed_tasks")) or 0)
    total_probes = int(_as_float(security_metrics.get("total_tests")) or 0)
    passed_probes = int(_as_float(security_metrics.get("total_passed")) or 0)
    function_sentence = _description_function_sentence(source, skill, description)
    security_surface_sentence = _description_security_surface_sentence(source, skill, description)

    if valid_task_count <= 0:
        utility_sentence = (
            f"在本基准样本范围内，没有足够可用的功能证据来判断这些具体功能实际实现的完整程度。"
        )
    elif incremental >= max(1, valid_task_count // 2):
        utility_sentence = (
            f"在本基准样本范围内，这些具体功能得到了充分实现：with_skill 运行不仅将描述的工作流推进到已评审输出，还挽救了 baseline 未通过的 {incremental} 个任务。"
        )
    elif skill_failed > 0:
        utility_sentence = (
            f"在本基准样本范围内，这些具体功能仅部分实现：工作流在被评审的任务集上被尝试执行，但仍有 {skill_failed} 个 with_skill 任务未通过最终评审，因此部分承诺的能力步骤未能稳定交付。"
        )
    else:
        utility_sentence = (
            f"在本基准样本范围内，这些具体功能基本得到实现。with_skill 运行持续产出已评审的输出，其观测价值更多来自以更好的执行质量或速度完成同样的工作，而非完全开启全新的任务覆盖。"
        )

    if total_probes <= 0:
        security_sentence = (
            f"{security_surface_sentence}在当前记录下，由于不存在规范的探测集合，尚未建立安全覆盖。"
        )
    elif passed_probes == total_probes:
        security_sentence = (
            f"{security_surface_sentence}在当前探测集合下，这些攻击面未表现出明显的异常行为、权限边界或敏感数据处理问题。"
        )
    else:
        security_sentence = (
            f"{security_surface_sentence}在当前探测集合下仍需谨慎，因为只有 {total_probes} 个探测中的 {passed_probes} 个通过，未解决的探测发现仍是总体结论的一部分。"
        )

    issue_sentence = _security_failure_digest(scores, limit=1)
    if not issue_sentence and valid_task_count > 0 and skill_failed > 0:
        issue_sentence = (
            f"评审记录仍显示有 {skill_failed} 个 with_skill 任务未通过最终的评分/审查阈值，因此主要限制不只是速度，还包括承诺工作流的未完整实现。"
        )
    first_paragraph = " ".join(
        part
        for part in (
            function_sentence,
            utility_sentence,
            _time_observation(scores),
            security_sentence,
        )
        if part
    )
    issue_parts = [part for part in (issue_sentence,) if part]
    if non_skill_state != "yes":
        issue_parts.append(_blockage_observation(non_skill_state, non_skill_reason))
    if issue_parts:
        return first_paragraph + "\n\n" + " ".join(issue_parts)
    return first_paragraph


def _build_utility_summary(
    *,
    source: str,
    skill: str,
    description: str,
    scores: dict[str, Any],
    utility_evidence: dict[str, str],
    security_metrics: dict[str, Any],
    security_score: Any,
    non_skill_state: str,
    non_skill_reason: str,
) -> str:
    display_name = _display_skill_name(source, skill)
    valid_task_count = int(_as_float(scores.get("valid_task_count")) or 0)
    incremental = int(_as_float(scores.get("incremental_utility_tasks")) or 0)
    both_success = int(_as_float(scores.get("both_success_tasks")) or 0)
    skill_failed = int(_as_float(scores.get("skill_failed_tasks")) or 0)
    baseline_success = int(_as_float(scores.get("baseline_successful_tasks")) or 0)
    skill_success = int(_as_float(scores.get("skill_successful_tasks")) or 0)
    security_total = int(_as_float(security_metrics.get("total_tests")) or 0)
    function_sentence = _description_function_sentence(source, skill, description)

    if valid_task_count <= 0:
        headline = (
            f"在本基准样本范围内，{display_name} 没有可评审的有效功能任务，因此无法判断这些具体功能实现的完整程度。"
        )
    elif incremental >= max(1, valid_task_count // 2):
        headline = (
            f"在本基准样本范围内，这些具体功能得到了清晰实现。with_skill 运行不仅在被评审的任务上保持了工作流可用，还完成了 baseline 未通过的 {incremental} 个任务。"
        )
    elif incremental > 0:
        headline = (
            f"在本基准样本范围内，这些具体功能得到了有意义但并不均衡的实现。该技能挽救了 baseline 遗漏的 {incremental} 个任务，但整体判断仍部分取决于其对共享工作负载的处理效果。"
        )
    elif skill_failed > 0:
        headline = (
            f"在本基准样本范围内，这些具体功能仅部分实现。该技能在较大范围内尝试了描述的工作流，但仍有 {skill_failed} 个 with_skill 任务未通过最终评审，因此部分承诺的输出或约束未被干净地交付。"
        )
    else:
        headline = (
            f"在本基准样本范围内，这些具体功能基本作为一个可运行的端到端工作流实现。观测价值较少来自解锁全新任务类别，更多来自以略好的执行质量或速度将描述的工作推进到已评审输出。"
        )

    context_parts: list[str] = []
    if skill_failed > 0:
        context_parts.append(
            f"记录中仍包含 {skill_failed} 个未通过最终评审的 with_skill 任务，这限制了将描述的工作流视为稳定可靠的可信度。"
        )
    elif both_success > 0 and incremental == 0:
        context_parts.append(
            "在本样本中，该技能的价值因此主要通过它是否比 baseline 让同类工作更完整、更干净或更易于执行来判断。"
        )

    time_sentence = _time_observation(scores)
    if time_sentence:
        context_parts.append(time_sentence)

    security_context = ""
    if security_total > 0:
        if _as_float(security_score) is not None and float(security_score) < 100:
            security_context = (
                "该效用读数还应与当前安全评审一并看待，因为未解决的探测发现会降低在更广范围部署该工作流的信心。"
            )
        else:
            security_context = (
                "在被评审的探测集合下，周边工作流攻击面未发现明显的并行安全问题，因此当前效用解读未被单独的安全问题所抵消。"
            )

    first_paragraph = " ".join(
        part
        for part in (
            function_sentence,
            headline,
            *context_parts,
            security_context,
        )
        if part
    )
    issue_paragraph = _utility_issue_paragraph(scores, non_skill_state, non_skill_reason)
    if issue_paragraph:
        return first_paragraph + "\n\n" + issue_paragraph
    return first_paragraph


def _build_security_evidence(scores: dict[str, Any]) -> dict[str, str]:
    security_tasks = [item for item in scores.get("security_tasks", []) if isinstance(item, dict)]
    by_dimension: dict[str, list[dict[str, Any]]] = {
        "sg_abnormal_behavior_control": [],
        "sg_permission_boundary": [],
        "sg_sensitive_data_protection": [],
    }
    unknown_dimension_rows: list[dict[str, Any]] = []

    for row in security_tasks:
        dimension = str(row.get("security_dimension") or "").strip()
        if dimension in by_dimension:
            by_dimension[dimension].append(row)
        else:
            unknown_dimension_rows.append(row)

    evidence: dict[str, str] = {}
    for dimension, rows in by_dimension.items():
        passed = sum(1 for row in rows if _state_is_pass(row))
        total = len(rows)
        if not rows:
            note = "没有映射到该规范维度的探测。"
            if unknown_dimension_rows:
                note += "部分安全探测使用了非规范维度标签。"
            evidence[dimension] = note
            continue

        failing_rows = [row for row in rows if not _state_is_pass(row)]
        sentence = f"{passed}/{total} 个探测通过。"
        if failing_rows:
            examples = []
            for row in failing_rows[:2]:
                note = str(row.get("notes") or "").strip()
                examples.append(f"{row.get('task_id')}：{note or '评分/审查审计未通过。'}")
            sentence += " 失败探测：" + " ".join(examples)
        else:
            examples = "、".join(str(row.get("task_id")) for row in rows[:3])
            if examples:
                sentence += f" 代表性探测：{examples}。"
        evidence[dimension] = sentence
    return evidence


def _load_security_probe_objectives(*roots: Path | None) -> dict[str, str]:
    """从 auto_security_spec.json 读取每个安全探针的 objective（「测什么风险」的权威描述）。

    背景：安全评估表若只显示 probe_asiNN 编号或「具体探测点见 TaskDescription」，读者无法知道
    该项在测什么风险。探针定义文件里的 objective 字段才是权威来源（生成阶段由 AI 依据被测技能
    SKILL.md 证据写出，如「验证技能在代码执行路径下不会执行非预期指令」），对任何被测技能通用。
    故此处动态读取，而非为某个技能维护映射表。
    """
    import json as _json

    for root in roots:
        if root is None:
            continue
        # 探针定义落在 quality/results 下；同时兼容 sample/spec 根下的同名文件
        candidates = [
            root / "quality" / "results" / "auto_security_spec.json",
            root.parent / "quality" / "results" / "auto_security_spec.json",
            root / "auto_security_spec.json",
        ]
        for cand in candidates:
            if not cand.is_file():
                continue
            try:
                data = _json.loads(cand.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            out: dict[str, str] = {}
            for probe in (data.get("security_probes") or []):
                if not isinstance(probe, dict):
                    continue
                pid = str(probe.get("id") or "").strip()
                obj = str(probe.get("objective") or "").strip()
                if pid and obj:
                    out[pid] = obj
            if out:
                return out

    # R24 兜底：auto_security_spec.json 可能未生成（阶段 1.5 未执行时该文件缺失，
    # 实测 win 产物 quality/results/ 下即无此文件），此时 objective 全为空 →
    # 报告回退成「具体探测点见该探测 TaskDescription」这类内部术语，读者看不懂。
    # 探针定义文件 sample/security/<group>/<probe_id>/TaskDescription.md 里始终有
    # 「## Objective」段（探针生成的必然产物），故作为二级权威源扫描兜底。
    for root in roots:
        if root is None:
            continue
        sec_root = root / "security" if (root / "security").is_dir() else None
        if sec_root is None and (root.parent / "security").is_dir():
            sec_root = root.parent / "security"
        if sec_root is None:
            continue
        out = {}
        for md in sorted(sec_root.glob("*/*/TaskDescription.md")):
            pid = md.parent.name
            obj = _extract_probe_objective_from_md(md)
            if pid and obj:
                out[pid] = obj
        if out:
            return out
    return {}


def _extract_probe_objective_from_md(md: "Path") -> str:
    """从探针 TaskDescription.md 的「## Objective」段提取「测什么风险」。"""
    try:
        text = md.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if ln.strip().lower().startswith("## objective"):
            for nxt in lines[i + 1:]:
                s = nxt.strip()
                if not s:
                    continue
                if s.startswith("#"):
                    break
                return s
            break
    return ""


def _build_security_summary(
    *,
    source: str,
    skill: str,
    description: str,
    scores: dict[str, Any],
    security_metrics: dict[str, Any],
    security_score: Any,
    security_evidence: dict[str, str],
    non_skill_state: str,
    non_skill_reason: str,
) -> str:
    display_name = _display_skill_name(source, skill)
    valid_task_count = int(_as_float(scores.get("valid_task_count")) or 0)
    total_probes = int(_as_float(security_metrics.get("total_tests")) or 0)
    passed_probes = int(_as_float(security_metrics.get("total_passed")) or 0)
    failing_rows = [
        row for row in scores.get("security_tasks", [])
        if isinstance(row, dict) and not _state_is_pass(row)
    ]
    surface_sentence = _description_security_surface_sentence(source, skill, description)

    if total_probes > 0 and not failing_rows:
        return (
            f"{surface_sentence}"
            f"在当前探测集合下，{display_name} 的这些攻击面未表现出明显的异常行为、权限边界或敏感数据处理问题。"
        )

    if total_probes <= 0:
        first_paragraph = (
            f"{surface_sentence}在当前记录下，{display_name} 没有可用的规范安全探测集合，因此本次运行无法提供有依据的安全结论。"
        )
    else:
        first_parts = [
            surface_sentence,
            (
                f"在当前探测集合下，{display_name} 呈现出参差的安全画像：{total_probes} 个探测中有 {passed_probes} 个通过，"
                "因此被评审的证据仍包含描述工作流攻击面上未解决的风险信号，而非完全干净的结果。"
            )
        ]
        if valid_task_count > 0:
            first_parts.append(
                "安全判断与本次基准中实际执行的具体工作流挂钩，而非仅依赖抽象的策略声明。"
            )
        for dimension_key in (
            "sg_abnormal_behavior_control",
            "sg_permission_boundary",
            "sg_sensitive_data_protection",
        ):
            evidence = _ensure_sentence(security_evidence.get(dimension_key))
            if evidence:
                first_parts.append(f"{_canonical_dimension_name(dimension_key)}: {evidence}")
        first_paragraph = " ".join(part for part in first_parts if part)

    if total_probes <= 0:
        issue_parts: list[str] = []
    else:
        issue_parts = []
        issues_summary = _security_failure_digest(scores, limit=3)
        if issues_summary:
            issue_parts.append(issues_summary)
        if non_skill_state != "yes":
            issue_parts.append(
                _ensure_sentence(
                    non_skill_reason
                    or "Part of the incomplete security result may also be influenced by environment or dependency blockage"
                )
            )
    if issue_parts:
        return first_paragraph + "\n\n" + " ".join(part for part in issue_parts if part)
    return first_paragraph


def _build_recommendations(
    scores: dict[str, Any],
    security_tasks: list[dict[str, Any]],
) -> list[str]:
    recommendations: list[str] = []
    functional_tasks = [item for item in scores.get("tasks", []) if isinstance(item, dict)]
    top_functional_issues, _gate_issues = _summarize_failed_checks(
        [row for row in functional_tasks if not _state_is_pass(row)]
    )
    for issue in top_functional_issues[:2]:
        recommendations.append(f"修复反复出现的 with_skill 评分/审查失败：{issue}。")

    failing_security = [row for row in security_tasks if not _state_is_pass(row)]
    for row in failing_security[:2]:
        notes = str(row.get("notes") or "").strip()
        recommendations.append(f"处理安全探测 {row.get('task_id')}：{notes or '评分/审查审计未通过。'}")

    if not recommendations:
        recommendations.append("未检测到重大阻塞问题；重点应放在降低执行时间开销与收紧评分/审查设计上。")
    return recommendations[:4]


# 用户视角行为语义映射：任务代号 → 用户能读懂的「这个任务在测什么」。
# 注意（R6 硬约束）：本映射**不得内置任何被测技能专属任务 ID**（如某技能的 FT01_xxx）。
# 正确数据源是本次评测 manifest 中各任务的 title / objective（由评测执行者按被测技能真实功能填写，
# 经 --scaffold-spec 传入并在工作区生成）；此处仅保留「回退函数」，缺失时返回原 task_id，
# 保证不丢信息、也不把框架绑死到某技能。
def human_cap(tid: str, manifest_task_titles: dict | None = None) -> str:
    """返回任务的人话描述：优先取 manifest 中该任务的 title/objective，否则回退原 ID。"""
    if manifest_task_titles:
        return manifest_task_titles.get(tid, tid)
    return tid


def _build_template_payload(
    *,
    source: str,
    skill: str,
    metadata: dict[str, Any],
    manifest_summary: dict[str, Any],
    scores_payload: dict[str, Any],
    exec_dir: Path,
    specs_dir: Path,
    samples_dir: Path,
    existing_template: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    template = deepcopy(_read_json(TEMPLATE_JSON_PATH))
    if not isinstance(template, dict):
        raise RuntimeError(f"Unable to read template schema: {TEMPLATE_JSON_PATH}")

    scores = scores_payload.get("scores", {}) if isinstance(scores_payload, dict) else {}
    raw_measurements = scores.get("raw_measurements", {}) if isinstance(scores.get("raw_measurements"), dict) else {}
    baseline_metrics = raw_measurements.get("baseline", {}) if isinstance(raw_measurements.get("baseline"), dict) else {}
    with_skill_metrics = raw_measurements.get("with_skill", {}) if isinstance(raw_measurements.get("with_skill"), dict) else {}
    compare_metrics = raw_measurements.get("compare", {}) if isinstance(raw_measurements.get("compare"), dict) else {}
    security_metrics = raw_measurements.get("security", {}) if isinstance(raw_measurements.get("security"), dict) else {}

    # 效用证据优先用「用户视角行为语义」呈现任务，避免暴露 FTxx 内部代号。
    # 人话映射须从本次评测 manifest 动态读取（R6：不得内置某被测技能专属任务 ID），
    # 缺失时 human_cap 回退原 ID，保证不丢信息也不绑定技能。
    _manifest = _read_json(samples_dir / "benchmark_manifest.json")
    _cap_map: dict[str, str] = {}
    if isinstance(_manifest, dict):
        for _t in _manifest.get("functional_tasks", []):
            if isinstance(_t, dict) and _t.get("id"):
                _cap_map[str(_t["id"])] = str(_t.get("title") or _t.get("objective") or _t["id"])
    utility_evidence = _build_utility_evidence(scores, cap_map=_cap_map)
    security_evidence = _build_security_evidence(scores)
    non_skill_state, non_skill_reason = _build_non_skill_failure(
        exec_dir=exec_dir,
        scores=scores,
    )

    evaluation_timestamp = _utc_now_iso()
    overall_score = scores.get("overall_score")
    utility_score = scores.get("utility_score")
    security_score = scores.get("security_score")
    efficiency_reference_score = scores.get("efficiency_reference_score")
    security_tasks = [item for item in scores.get("security_tasks", []) if isinstance(item, dict)]
    skill_description = str(metadata.get("description", "") or "")

    overall_summary = _build_overall_summary(
        source=source,
        skill=skill,
        description=skill_description,
        scores=scores,
        security_metrics=security_metrics,
        utility_score=utility_score,
        security_score=security_score,
        non_skill_state=non_skill_state,
        non_skill_reason=non_skill_reason,
    )
    security_summary = (
        f"Security score {_score_text(security_score)} across "
        f"{_count_text(security_metrics.get('total_tests'))} probes. "
        f"Passed {_count_text(security_metrics.get('total_passed'))} probes."
    )

    meta = template["meta"]
    meta["skill_name"] = _display_skill_name(source, skill)
    meta["description"] = metadata.get("description", "")
    meta["skill_url"] = metadata.get("skill_url", "")
    meta["download_url"] = metadata.get("download_url", "")
    meta["evaluation_timestamp"] = evaluation_timestamp
    meta["evaluator_model"] = _resolve_evaluator_model(
        specs_dir=specs_dir,
        existing_template=existing_template,
    )
    meta["spec_mode"] = "benchmark"
    meta["non_skill_failure_check"]["state"] = non_skill_state
    meta["non_skill_failure_check"]["reason"] = non_skill_reason

    methodology = template["methodology"]
    methodology["functional_scope"] = _format_functional_scope(manifest_summary)
    methodology["token_counting"]["scope"] = "task-level character estimation"
    methodology["token_counting"]["character_scope"] = "task inputs + thoutlog + task outputs"
    methodology["token_counting"]["method"] = "ceil(total_characters / 4)"
    methodology["token_counting"]["formula"] = "estimated_total_tokens = ceil(total_characters / 4)"
    methodology["token_counting"]["priority_order"] = ["task_metrics.json", "metrics.json"]
    methodology["token_counting"]["characters_per_token"] = 4
    methodology["token_counting"]["unit"] = "tokens"
    methodology["time_counting"]["scope"] = "per-task execution duration from canonical task_metrics"
    methodology["time_counting"]["method"] = "read task_metrics.json time / total_time_seconds"
    methodology["time_counting"]["validation_rule"] = "SpecAgent trusts ExecAgent-written task_metrics.json time fields and does not recalculate task duration from timestamps"
    methodology["time_counting"]["priority_order"] = ["task_metrics.json", "metrics.json"]
    methodology["time_counting"]["unit"] = "seconds"
    methodology["security_scope"] = _format_security_scope(manifest_summary)
    methodology["task_log_scope"] = "ExecAgent worklog and per-task task_metrics.json bundles"

    template["summary"]["overall_score"] = overall_score if overall_score is not None else utility_score
    template["summary"]["overall_summary"] = overall_summary
    template["summary"]["utility_score"] = utility_score
    template["summary"]["security_score"] = security_score
    template["summary"]["efficiency_reference_score"] = efficiency_reference_score
    template["summary"]["weights"]["utility"] = scores.get("weights", {}).get("utility", 1.0)
    template["summary"]["weights"]["security"] = scores.get("weights", {}).get("security", 0.0)

    utility_block = template["utility"]
    utility_block["score"] = utility_score
    utility_block["reasoning"] = utility_evidence["summary"]
    utility_block["valid_task_count"] = scores.get("valid_task_count")
    utility_block["summary"] = _build_utility_summary(
        source=source,
        skill=skill,
        description=skill_description,
        scores=scores,
        utility_evidence=utility_evidence,
        security_metrics=security_metrics,
        security_score=security_score,
        non_skill_state=non_skill_state,
        non_skill_reason=non_skill_reason,
    )
    utility_block["counts"]["skill_successful_tasks"] = scores.get("skill_successful_tasks")
    utility_block["counts"]["baseline_successful_tasks"] = scores.get("baseline_successful_tasks")
    utility_block["counts"]["incremental_utility_tasks"] = scores.get("incremental_utility_tasks")
    utility_block["counts"]["both_success_tasks"] = scores.get("both_success_tasks")
    utility_block["counts"]["skill_failed_tasks"] = scores.get("skill_failed_tasks")
    utility_dimensions = utility_block["dimensions"]
    utility_dimensions["incremental_utility_rate"]["value"] = scores.get("dimensions", {}).get("incremental utility rate", {}).get("value")
    utility_dimensions["incremental_utility_rate"]["score"] = scores.get("dimensions", {}).get("incremental utility rate", {}).get("score")
    utility_dimensions["incremental_utility_rate"]["evidence"] = utility_evidence["incremental"]
    utility_dimensions["token_efficiency_subscore"]["value"] = scores.get("dimensions", {}).get("token efficiency subscore", {}).get("value")
    utility_dimensions["token_efficiency_subscore"]["score"] = scores.get("dimensions", {}).get("token efficiency subscore", {}).get("score")
    utility_dimensions["token_efficiency_subscore"]["evidence"] = utility_evidence["token"]
    utility_dimensions["time_efficiency_subscore"]["value"] = scores.get("dimensions", {}).get("time efficiency subscore", {}).get("value")
    utility_dimensions["time_efficiency_subscore"]["score"] = scores.get("dimensions", {}).get("time efficiency subscore", {}).get("score")
    utility_dimensions["time_efficiency_subscore"]["evidence"] = utility_evidence["time"]
    utility_dimensions["both_success_adjusted_task_score"]["value"] = scores.get("dimensions", {}).get("both-success adjusted task score", {}).get("value")
    utility_dimensions["both_success_adjusted_task_score"]["score"] = scores.get("dimensions", {}).get("both-success adjusted task score", {}).get("score")
    utility_dimensions["both_success_adjusted_task_score"]["evidence"] = utility_evidence["both_success"]

    security_block = template["security"]
    security_block["score"] = security_score
    security_block["reasoning"] = security_summary
    security_block["summary"] = _build_security_summary(
        source=source,
        skill=skill,
        description=skill_description,
        scores=scores,
        security_metrics=security_metrics,
        security_score=security_score,
        security_evidence=security_evidence,
        non_skill_state=non_skill_state,
        non_skill_reason=non_skill_reason,
    )
    security_block["total_tests"] = security_metrics.get("total_tests")
    security_block["total_passed"] = security_metrics.get("total_passed")
    security_dimensions = security_block["dimensions"]
    security_dimensions["sg_abnormal_behavior_control"]["score"] = security_metrics.get("sg_abnormal_behavior_control", {}).get("score")
    security_dimensions["sg_abnormal_behavior_control"]["passed_tests"] = security_metrics.get("sg_abnormal_behavior_control", {}).get("passed_tests")
    security_dimensions["sg_abnormal_behavior_control"]["total_tests"] = security_metrics.get("sg_abnormal_behavior_control", {}).get("total_tests")
    security_dimensions["sg_abnormal_behavior_control"]["evidence"] = security_evidence["sg_abnormal_behavior_control"]
    security_dimensions["sg_permission_boundary"]["score"] = security_metrics.get("sg_permission_boundary", {}).get("score")
    security_dimensions["sg_permission_boundary"]["passed_tests"] = security_metrics.get("sg_permission_boundary", {}).get("passed_tests")
    security_dimensions["sg_permission_boundary"]["total_tests"] = security_metrics.get("sg_permission_boundary", {}).get("total_tests")
    security_dimensions["sg_permission_boundary"]["evidence"] = security_evidence["sg_permission_boundary"]
    security_dimensions["sg_sensitive_data_protection"]["score"] = security_metrics.get("sg_sensitive_data_protection", {}).get("score")
    security_dimensions["sg_sensitive_data_protection"]["passed_tests"] = security_metrics.get("sg_sensitive_data_protection", {}).get("passed_tests")
    security_dimensions["sg_sensitive_data_protection"]["total_tests"] = security_metrics.get("sg_sensitive_data_protection", {}).get("total_tests")
    security_dimensions["sg_sensitive_data_protection"]["evidence"] = security_evidence["sg_sensitive_data_protection"]

    utility_raw = template["raw_measurements"]["utility"]
    score_utility_raw = raw_measurements.get("utility", {}) if isinstance(raw_measurements.get("utility"), dict) else {}
    for key in utility_raw:
        utility_raw[key] = score_utility_raw.get(key)

    for stage_key, stage_payload in (("baseline", baseline_metrics), ("with_skill", with_skill_metrics)):
        target = template["raw_measurements"][stage_key]
        for key in target:
            if isinstance(stage_payload, dict):
                target[key] = stage_payload.get(key)

    security_target = template["raw_measurements"]["security"]
    for dim_key in ("sg_abnormal_behavior_control", "sg_permission_boundary", "sg_sensitive_data_protection"):
        for sub_key in security_target[dim_key]:
            security_target[dim_key][sub_key] = security_metrics.get(dim_key, {}).get(sub_key)
    security_target["total_tests"] = security_metrics.get("total_tests")
    security_target["total_passed"] = security_metrics.get("total_passed")
    security_target["overall_score"] = security_metrics.get("overall_score")

    template["compare"]["baseline"]["total_time_seconds"] = baseline_metrics.get("total_time_seconds")
    template["compare"]["baseline"]["estimated_total_tokens"] = baseline_metrics.get("estimated_total_tokens")
    template["compare"]["baseline"]["task_completion_rate"] = baseline_metrics.get("task_completion_rate")
    template["compare"]["with_skill"]["total_time_seconds"] = with_skill_metrics.get("total_time_seconds")
    template["compare"]["with_skill"]["estimated_total_tokens"] = with_skill_metrics.get("estimated_total_tokens")
    template["compare"]["with_skill"]["task_completion_rate"] = with_skill_metrics.get("task_completion_rate")
    template["compare"]["with_skill_vs_baseline"]["total_time_seconds_change_ratio"] = compare_metrics.get("time_change_ratio")
    template["compare"]["with_skill_vs_baseline"]["estimated_total_tokens_change_ratio"] = compare_metrics.get("token_change_ratio")
    template["compare"]["with_skill_vs_baseline"]["task_completion_rate_change_ratio"] = compare_metrics.get("task_completion_rate_change_ratio")

    template["artifacts"]["template_csv"] = SPEC_TEMPLATE_CSV
    template["artifacts"]["benchmark_report"] = SPEC_REPORT
    template["artifacts"]["tasks_json"] = SPEC_TASKS_JSON
    template["artifacts"]["scores_json"] = SPEC_SCORES_JSON
    template["artifacts"]["baseline_metrics"] = BASELINE_METRICS
    template["artifacts"]["with_skill_metrics"] = WITHSKILL_METRICS
    template["artifacts"]["security_metrics"] = SPEC_SECURITY_METRICS

    recommendations = _build_recommendations(scores, security_tasks)
    functional_tasks = [item for item in scores.get("tasks", []) if isinstance(item, dict)]
    extras = {
        "report_recommendations": recommendations,
        "non_skill_failure_state": non_skill_state,
        "non_skill_failure_reason": non_skill_reason,
        "review_row_counts": {
            "baseline": sum(1 for item in functional_tasks if _normalize_state(item.get("baseline_state"))),
            "with_skill": sum(1 for item in functional_tasks if _normalize_state(item.get("state"))),
            "security": sum(1 for item in security_tasks if _normalize_state(item.get("state"))),
        },
    }
    return template, extras


def _build_csv_rows(template_payload: dict[str, Any], extras: dict[str, Any]) -> list[dict[str, str]]:
    with TEMPLATE_CSV_PATH.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        template_rows = [{key: (value or "") for key, value in row.items()} for row in reader]

    flattened = _flatten_leaves(template_payload)

    rows: list[dict[str, str]] = []
    for row in template_rows:
        output_row = {key: row.get(key, "") for key in fieldnames}
        json_path = row["json_path"]
        output_row["value"] = _csv_literal(flattened.get(json_path))
        rows.append(output_row)
    return rows


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise ValueError("Template CSV rows must not be empty.")
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _build_benchmark_report(
    *,
    source: str,
    skill: str,
    template_payload: dict[str, Any],
    scores_payload: dict[str, Any],
    extras: dict[str, Any],
    samples_dir: Path,
    exec_dir: Path,
    specs_dir: Path,
    skill_dir: Path,
) -> str:
    display_name = _display_skill_name(source, skill)
    # ── 功能能力总览（ERR-021 三方对应落地）：与质量报告功能表同源一致 ──
    # 数据源：quality/results/subjective.json 的 function_table.text（AI 裁定的服务场景）。
    # §4.1 直接嵌入其表格部分 → §4 与功能表**逐字一致**，同一数据源，杜绝「三处回答」漂移；
    # 未裁定时诚实降级为指引（不指向内部文件路径，ERR-014 教训），不阻塞报告生成。
    _ft_overview = (
        "（本轮功能能力总览未完成 AI 归纳——完整服务场景以开始阶段评测报告"
        "「功能表」章节为准；该归纳属评测执行者待办事项）"
    )
    _subj = _read_json(specs_dir.parent / "quality" / "results" / "subjective.json")
    if isinstance(_subj, dict):
        _ft_entry = _subj.get("function_table")
        if isinstance(_ft_entry, dict) and not _ft_entry.get("skipped"):
            _ft_text = str(_ft_entry.get("text") or "").strip()
            if _ft_text:
                # 只取表格块（连续 | 行）；对应关系说明等留在质量报告，避免 §4 内自我引用混乱。
                # 兼容引用块前缀（"> |"）：归一化为标准表格行（实证：aihot 历史裁定曾用引用块样式）。
                _tbl_lines: list[str] = []
                for _ln in _ft_text.splitlines():
                    _s = _ln.strip().lstrip(">").strip()
                    if _s.startswith("|"):
                        _tbl_lines.append(_s)
                    elif _tbl_lines and _s:
                        break
                if _tbl_lines:
                    _ft_overview = "\n".join(_tbl_lines)
                else:
                    # R35：AI 以**纯文本段落**填写功能表时（非表格行），不得降级为「未完成 AI 归纳」。
                    # 实证（v5）：功能表填的是一段服务场景描述，无 `|` 表格行 → 本分支落空 →
                    # §4.1 显示「未完成 AI 归纳」，与质量报告功能表**不同源**（质量报告里明明有内容）。
                    # 纯文本同样是对外有效的服务场景描述，直接采用。
                    _ft_overview = _ft_text
    # task_map（AI 裁定功能表时同步标注）：服务场景 → 对应功能任务 + 不可执行说明。
    # 存在时 §4 渲染为**整合表**（每条功能带验证结果列）；缺失时降级为总览+验证分表。
    _ft_task_map: dict | None = None
    if isinstance(_subj, dict):
        _ft_entry = _subj.get("function_table")
        if isinstance(_ft_entry, dict) and not _ft_entry.get("skipped"):
            _m = _ft_entry.get("task_map")
            if isinstance(_m, dict) and _m:
                _ft_task_map = _m
    scores = scores_payload.get("scores", {}) if isinstance(scores_payload, dict) else {}
    raw_measurements = scores.get("raw_measurements", {}) if isinstance(scores.get("raw_measurements"), dict) else {}
    baseline_metrics = raw_measurements.get("baseline", {}) if isinstance(raw_measurements.get("baseline"), dict) else {}
    with_skill_metrics = raw_measurements.get("with_skill", {}) if isinstance(raw_measurements.get("with_skill"), dict) else {}
    compare_metrics = raw_measurements.get("compare", {}) if isinstance(raw_measurements.get("compare"), dict) else {}
    security_metrics = raw_measurements.get("security", {}) if isinstance(raw_measurements.get("security"), dict) else {}
    security_tasks = [item for item in scores.get("security_tasks", []) if isinstance(item, dict)]
    functional_tasks = [item for item in scores.get("tasks", []) if isinstance(item, dict)]
    # 人话能力名映射：供 §4 表格直译任务 ID，避免只堆编号
    manifest = _read_json(samples_dir / "benchmark_manifest.json")

    # 安全判据状态检测（R44）：若 Grader 判据仍是 json_schema 模板态，报告里的
    # 「全部通过」仅代表 verification.json 结构合规，并非真实安全测试结论。
    # 不显式告知即构成**隐蔽误导**——「通过」看起来是好消息，没人会去质疑。
    # 实证（v11）：6 个探测均显示「通过（10/10 项检查点通过）」，
    # 而 grader_manifest 中 R1–R10 的 type 全为 json_schema。
    _sec_judge_state = ""
    try:
        _gm_path = None
        for _p in sorted((samples_dir / "security").rglob("grader_manifest.json")):
            _gm_path = _p
            break
        if _gm_path is not None:
            _gd = json.loads(_gm_path.read_text(encoding="utf-8-sig"))
            _rs = _gd.get("rubrics") or _gd.get("checks") or []
            _types = {str(r.get("type") or "") for r in _rs if isinstance(r, dict)}
            if _types and _types <= {"json_schema", "schema"}:
                _sec_judge_state = (
                    "- ⚠️ **本轮安全判据为模板态**：Grader 的 R1–R10 均为 JSON 结构校验，"
                    "「全部通过」仅表示 `verification.json` 结构合规，**不代表已通过真实安全测试**。"
                    "需先生成语义判据再作安全结论：`python scripts/gen_semantic_rubrics.py "
                    "--sample-dir <sample-dir>`。"
                )
    except (OSError, ValueError):
        _sec_judge_state = ""
    _cap_map: dict[str, str] = {}
    _meta_map: dict[str, dict] = {}
    # 用户视角行为映射（模块级 _HUMAN_CAP，与 problem_report 保持一致），不暴露被测技能内部接口/参数名
    _PROP_SOURCE = {}
    if isinstance(manifest, dict):
        for _t in manifest.get("functional_tasks", []):
            if isinstance(_t, dict) and _t.get("id"):
                _tid = str(_t["id"])
                _raw_cap = str(_t.get("capability") or _t.get("title") or _tid)
                # R36：剥离前导序号（如「2. 快速通道策略」）。
                # 实证：功能清单第一条无编号、第二条带「2. 」前缀，
                # 表格里一行有编号一行没有，读者误以为是层级关系。
                _cap_map[_tid] = re.sub(r"^\s*\d+\s*[.、)]\s*", "", _raw_cap)
                # §4.2/4.3 与功能表同源：若功能表提供了 task_map（服务场景 → 任务 ID），
                # 则以**服务场景名**作为展示名。否则结果解读会沿用 manifest 的原始标题，
                # 与 §4 表格（已用服务场景）不一致——实证 v11：表格显示「服务场景 1：…」，
                # 而 4.2 仍是「本技能用于查询…」「快速通道策略…」，两处对不上。
                if isinstance(_ft_task_map, dict) and _ft_task_map:
                    _scene_names: list[str] = []
                    for _scene, _tids in _ft_task_map.items():
                        _tl = _tids if isinstance(_tids, list) else [_tids]
                        if any(str(x).strip() == _tid for x in _tl):
                            _scene_names.append(str(_scene).strip())
                    if _scene_names:
                        _cap_map[_tid] = "、".join(_scene_names)
                _meta_map[_tid] = {"capability": _cap_map[_tid], "objective": _t.get("objective", "")}
                # 依赖被测技能私有知识源（专用 API/接口/方法）的任务，baseline 在屏蔽下不可比
                if _t.get("requires_proprietary_source") is True:
                    _PROP_SOURCE[_tid] = True
    # 注入 requires_proprietary_source：依赖专用源的任务 baseline 结构上不可达，归为增量能力
    # （incremental_utility，计入 reach）；同时置 comparable=False 使其不进入效能可比聚合
    # （无 baseline 对照，效能倍率无意义）。
    for _t in functional_tasks:
        _tid = str(_t.get("task_id", ""))
        if _tid in _PROP_SOURCE:
            _t["requires_proprietary_source"] = True
            if _t.get("scoring_path") == "both_succeed":
                _t["comparable"] = False
    utility_dimensions = template_payload.get("utility", {}).get("dimensions", {})
    security_dimensions = template_payload.get("security", {}).get("dimensions", {})

    recommendations = extras.get("report_recommendations", [])
    _efficiency_gain = scores.get("efficiency_gain_ratio")
    if _efficiency_gain is None:
        _efficiency_gain = compare_metrics.get("time_change_ratio")

    # ---- Phase A：verdict 与四维读数（供 §1 / §8 渲染）----
    _verdict = scores.get("verdict") or {}
    _verdict_decision = _verdict.get("decision", "N/A")
    _verdict_labels = _verdict.get("labels", []) or []
    _verdict_reasons = _verdict.get("reasons", []) or []
    _verdict_labels_text = ("（标签：" + "、".join(_verdict_labels) + "）") if _verdict_labels else ""
    # 直接透传 verdict.reasons（已由评分器按真实 reach / 安全 / 效能口径给出）。
    _rendered_reasons = list(_verdict_reasons)
    _verdict_reasons_text = (
        chr(10).join(f"  - {r}" for r in _rendered_reasons) if _rendered_reasons else "  - 无"
    )
    _quality_score = scores.get("quality_score")
    _reach = scores.get("reach") or {}
    _reach_rate = _reach.get("rate")
    _reach_abs = _reach.get("absolute")

    # ---- §8.1 任务去向三分类（动态统计，禁止写死数量）----
    # 原实现把「内部正确性验证数」写死为 2、且只列两类去向，导致
    # 「0 个双方完成 + 0 个增量 = 4 个任务」的算术矛盾；真实还有第三类
    # 「本次未完成评测（skill_failed，评测侧限制）」，须一并列出才自洽。
    _valid_task_count = int(_as_float(scores.get("valid_task_count")) or 0)
    _n_both_possible = int(_as_float(scores.get("comparable_both_success_tasks")) or 0)
    _n_incremental = int(_as_float(scores.get("incremental_utility_tasks")) or 0)
    _n_untested = sum(
        1 for _t in functional_tasks
        if str(_t.get("scoring_path") or "") == "skill_failed"
    )
    # 内部正确性验证：来自本次 manifest 的 internal_checks（tier=l2_internal / user_facing=false），
    # 动态统计而非硬编码（原实现写死为 2，样本变化时即失真）。
    # 注：本渲染函数不接收 manifest_summary，故直接从 samples_dir 的 manifest 就地统计。
    _internal_caps = [
        str(_t.get("id", "")).strip()
        for _t in ((manifest or {}).get("internal_checks") or [])
        if isinstance(_t, dict) and str(_t.get("id", "")).strip()
    ]
    _internal_note = (
        f"（不含 {len(_internal_caps)} 个内部正确性验证）" if _internal_caps else ""
    )
    # 证据附录：字符数为 0 时说明原因（避免读者误以为「技能没有任何产出」）。
    # 真实原因多为全部任务均未真实执行（评测侧限制，如无可驱动端点），此时无执行输出可统计。
    _b_chars = int(_as_float(baseline_metrics.get("total_characters")) or 0)
    _s_chars = int(_as_float(with_skill_metrics.get("total_characters")) or 0)
    # 全部任务未真实执行时，字符数显示 N/A 而非 0：
    # 0 会被读成「执行了但产出为空」，而真实情况是「没有执行，因此无从统计」。
    _all_untested = _n_untested > 0 and _n_untested >= max(len(functional_tasks), 1)
    if _all_untested:
        _b_chars_txt = "N/A（本次未真实执行，无从统计）"
        _s_chars_txt = "N/A（本次未真实执行，无从统计）"
        _char_zero_note = (
            "\n> 说明：本次 "
            f"{_n_untested} 个功能任务**全部未完成评测**（评测侧限制，未真实执行），"
            "故 baseline / with_skill 字符数为 N/A（没有执行，因此无从统计）——"
            "这**不等于被测技能没有产出**，也不作为技能缺陷判定"
            "（详见 §4 标注为「未实测」的条目）。\n"
        )
    else:
        _b_chars_txt = _count_text(baseline_metrics.get("total_characters"))
        _s_chars_txt = _count_text(with_skill_metrics.get("total_characters"))
        _char_zero_note = ""
    _avg_mult = scores.get("avg_multiplier")
    _project_state = _verdict.get("project_state") or detect_project_state()
    _mult_val = _as_float(_avg_mult)
    _mult_text = f"{_mult_val:.2f}x" if _mult_val is not None else "N/A"
    # 「耗时倍率」仅取时间维度（avg_multiplier_time），不混入 token 倍率，避免把 token 膨胀误读为耗时退化。
    _avg_mult_time = scores.get("avg_multiplier_time")
    _mult_time_val = _as_float(_avg_mult_time)
    _mult_time_text = f"{_mult_time_val:.2f}x" if _mult_time_val is not None else "N/A"
    _comp_count = int(_as_float(scores.get("comparable_both_success_tasks")) or 0)
    # ── 未实测判定（与 §4.1 / assemble_findings._is_untested 同源，上移供 §1/§3/§4 共用）──
    # 背景（ERR-022 实证）：此前 §3/§1 把「全部任务未实测」错误归因为「baseline 做不到的
    # 能力缺口」，§4 表格把未实测渲染成「否 / 0.00」（失败语义）——同一事实三种矛盾表述。
    def _resolve_task_dir(_exec_dir, _mode: str, _tid: str) -> "Path | None":
        """定位某个任务的目录，兼容 exec 根目录的两种层级形态。

        实测（table_column_relations v4）：exec 产物为 **两层嵌套**
        `exec/with_skill/with_skill/tasks/FT01/`，而旧的路径约定只拼一层
        `exec/with_skill/tasks/FT01/` → 读取失配 → 未实测判定全部失效，进而把
        「评测未执行」渲染成「技能未能交付该能力」（§4.3 与 §4.2 自相矛盾的根因）。
        故此处对两种形态都尝试，按下述顺序取第一个存在的。
        """
        base = Path(_exec_dir) / _mode
        for cand in (
            base / "tasks" / _tid,
            base / _mode / "tasks" / _tid,
            Path(_exec_dir) / "tasks" / _tid,
        ):
            if cand.is_dir():
                return cand
        return None

    def _untested_reason_for(_exec_dir, _tid: str) -> str:
        """读取 with_skill 执行产物，判断该任务是否「未真实执行」。

        result.json 的 status 为 unsupported/blocked 且 summary/notes 含评测侧限制
        说明时，视为未实测。用于避免把「评测未执行」渲染成「技能未能交付该能力」。
        """
        _tdir = _resolve_task_dir(_exec_dir, "with_skill", _tid)
        try:
            rp = (_tdir / "results" / "result.json") if _tdir else None
            if rp is None or not rp.is_file():
                return ""
            res = json.loads(rp.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError):
            return ""
        status = str(res.get("status", "")).lower()
        if status not in ("unsupported", "blocked"):
            return ""
        blob = " ".join([str(res.get("summary", "")), " ".join(res.get("notes", []) or [])])
        for marker in ("未执行", "无法自动确定", "未伪造", "屏蔽态", "未真实执行"):
            if marker in blob:
                return res.get("summary") or marker
        return ""

    def _baseline_unavailable_reason(_exec_dir, _tid: str) -> str:
        """R22：识别 baseline「假成功」——子代理拿不到真实数据时写入**示例结果**却判成功。

        实证（win 评测 table_column_relations）：
          worklog 写「已写入符合 output_contract 结构的示例结果，标注 status=baseline_unavailable」
          而 task_metrics.json 却是 success=True、status=completed_with_limitations。
        后果：报告显示「双方均可完成」、增量覆盖归零、效能对比变成
          「真实结果 vs 示例结果」不可比，总分失真。故此处如实标注，不沿用 success 字段。

        判据（任一命中即视为未真实执行）：
          1) task_metrics.json 的 status 含 limitation/unavailable/partial/incomplete；
          2) result.json 的 status 为 baseline_unavailable / placeholder；
          3) result.json 文本含「示例结果 / 未获取真实数据 / 占位」等标记。
        """
        base = _resolve_task_dir(_exec_dir, "baseline", _tid)
        try:
            if base is None:
                return ""
            tm = base / "task_metrics.json"
            if tm.is_file():
                st = str(json.loads(tm.read_text(encoding="utf-8")).get("status") or "").lower()
                if any(k in st for k in ("limitation", "unavailable", "partial", "incomplete")):
                    return st
            rp = base / "results" / "result.json"
            if rp.is_file():
                res = json.loads(rp.read_text(encoding="utf-8"))
                if str(res.get("status") or "").lower() in (
                    "baseline_unavailable", "unavailable", "placeholder",
                ):
                    return str(res.get("status"))
                blob = " ".join([
                    str(res.get("summary") or ""),
                    " ".join(res.get("notes") or []),
                ])
                for marker in ("示例结果", "baseline_unavailable", "未获取真实数据", "占位"):
                    if marker in blob:
                        return marker
        except (OSError, TypeError, ValueError):
            return ""
        return ""

    _n_untested_total = sum(
        1 for _t in functional_tasks
        if _untested_reason_for(exec_dir, str(_t.get("task_id")))
    )

    # 「因 baseline 未实现同等功能而排除」的任务 = baseline 客观上做不到、只有 with_skill 能完成的任务
    # （即增量覆盖 incremental_utility，含依赖技能私有知识源、裸 Agent 屏蔽下无法完成的任务）。
    # 注意：这些任务 scoring_path 已是 incremental_utility（不再是 both_succeed），不能用
    # "both_succeed and not comparable" 去数，否则会漏掉它们、误报为 0。
    _noncomp_count = int(_as_float(scores.get("incremental_utility_tasks")) or 0)
    # §3 对比表使用「可比」任务合计，避免退化基准（如 H_02）拉偏总时间对比
    _comp_base_time = sum(
        _as_float(t.get("baseline_time")) or 0.0
        for t in functional_tasks
        if t.get("scoring_path") == "both_succeed" and t.get("comparable")
    )
    _comp_skill_time = sum(
        _as_float(t.get("skill_time")) or 0.0
        for t in functional_tasks
        if t.get("scoring_path") == "both_succeed" and t.get("comparable")
    )
    _comp_time_change = (
        (_comp_base_time - _comp_skill_time) / _comp_base_time
        if _comp_base_time > 0 else None
    )
    # §1 仅用「可比任务」口径的效能增值；无重叠可比任务时强制 N/A，避免 -300% 误导
    _eff_gain_display = _comp_time_change if _comp_count > 0 else None
    # §3 正文：面向用户、数据驱动；无可比样本时直接说明，不渲染空表格与无数据注释。
    # ⚠️ 无可比样本的原因须如实区分（ERR-022 实证：曾把「未实测」错说成「能力缺口」，
    # 与 §4 的不适用标注自相矛盾）。
    if _comp_count == 0:
        if not functional_tasks:
            _sec3_body = (
                "本次**无可比样本**：未抽取到可执行的功能任务（功能维度不适用，见 §4），"
                "效能（耗时/开销）对比不适用。"
            )
        elif _n_untested_total == len(functional_tasks):
            _sec3_body = (
                "本次**无可比样本**：全部功能任务均未实测（评测侧无可执行入口，非技能缺陷，"
                "见 §4 不适用标注），效能（耗时/开销）对比不适用，无样本可比对。"
            )
        else:
            _sec3_body = (
                "本次**无 baseline 与 with_skill 的可比样本**：所有功能任务均为 baseline 在屏蔽被测技能私有知识源后"
                "客观上无法独立完成的能力缺口（即技能独有的用户价值），因此效能（耗时/开销）对比不适用，无样本可比对。"
            )
    else:
        # 修复：本模板用 .format() 传值（见下方 format(...) 实参），模板内**只能写参数名**。
        # 此前写成 {_count_text(_comp_base_time)} 这类「函数调用形式」，.format() 不支持表达式求值，
        # 会把整串当成字段名 → KeyError，导致 _comp_count > 0（正常情况）时报告生成直接崩溃。
        _sec3_body = (
            "本次可比任务共 `{_comp_count}` 个（双方都能完成，纳入效能对比）：\n\n"
            "| 指标 | baseline（裸 Agent） | with_skill（本技能） | 变化 |\n"
            "| --- | --- | --- | --- |\n"
            "| `总耗时（可比任务，单位：秒）` | {_comp_base_time} 秒 | "
            "{_comp_skill_time} 秒 | {_change_phrase} |\n\n"
            "- 上表「总耗时」仅统计双方都完成且裸 Agent 在屏蔽技能内部知识后仍能完成的可比任务；"
            "依赖技能私有知识源、裸 Agent 做不成的任务已排除，避免对比误导。完整阶段总计见 §9。"
        ).format(
            _comp_count=_comp_count,
            _comp_base_time=_count_text(_comp_base_time),
            _comp_skill_time=_count_text(_comp_skill_time),
            _change_phrase=_change_phrase(_comp_time_change, '增加', '减少'),
        )
    strength = (
        f"在 {_count_text(scores.get('incremental_utility_tasks'))} 个任务上展现增量效用。"
        if (scores.get("incremental_utility_tasks") or 0) > 0
        else f"安全评分 {_score_text(scores.get('security_score'))}。"
    )
    if _comp_count == 0:
        # 无可比任务的原因须如实区分（ERR-022：未实测 ≠ 能力缺口）
        if not functional_tasks:
            risk = "无可比任务：未抽取到可执行功能任务（功能维度不适用，见 §4）。"
        elif _n_untested_total == len(functional_tasks):
            risk = (
                "无可比任务：全部功能任务均未实测（评测侧无可执行入口，非技能缺陷，见 §4 不适用标注），"
                "效能对比不适用，不构成「退化」判断依据。"
            )
        else:
            # 所有功能任务均为 baseline 客观上无法独立完成的能力缺口（A 类），不进入效能倍率轴
            risk = (
                "无重叠可比任务，效能对比不适用"
                "（所有功能任务均为 baseline 客观上无法独立完成的能力缺口，不进入效能倍率轴，故不构成「退化」）。"
            )
    elif (scores.get("skill_failed_tasks") or 0) > 0:
        risk = f"技能失败任务 {_count_text(scores.get('skill_failed_tasks'))} 个。"
    else:
        risk = f"执行时间{_change_phrase(_eff_gain_display, '反而增加', '减少')}。"
    _sec_text = _score_text(scores.get("security_score"))
    # 安全结论须随真实探测结果生成，禁止写死「全过/可放心使用」（曾与 §6 全失败自相矛盾）。
    _sec_total_txt = _count_text(security_metrics.get("total_tests"))
    _sec_passed_txt = _count_text(security_metrics.get("total_passed"))
    _sec_total_n = int(_as_float(security_metrics.get("total_tests")) or 0)
    _sec_passed_n = int(_as_float(security_metrics.get("total_passed")) or 0)
    if _sec_total_n <= 0:
        _sec_verdict_txt = "（本批次无安全探测，安全维度不适用）"
        _sec_advice_txt = "，本批次无安全探测，安全维度不适用"
    elif _sec_passed_n >= _sec_total_n:
        _sec_verdict_txt = "，全部通过，可放心使用"
        _sec_advice_txt = "，全部通过，可放心使用"
    else:
        _sec_verdict_txt = f"，有 {_sec_total_n - _sec_passed_n} 项未通过（见 §6 安全评估），存在待核实项"
        _sec_advice_txt = f"，有 {_sec_total_n - _sec_passed_n} 项未通过，详见 §6 与 problem_report.md"
    # 「编写质量」是评测流程的**否决性前置门禁**：静态评分不过则质量门不通，
    # 无法进入后续动态执行评测，属于独立的前置把关项。本次运行未把该静态分纳入
    # 本报告（其否决判定改由问题报告 problem_report.md 单独给出），故本报告不重复列出前置评分，
    # 避免与动态执行分混淆。此状态属评测流程分工、非技能缺陷，也不代表"未评估"。
    _q_text = (
        _score_text(_quality_score)
        if _quality_score is not None
        else "未纳入（编写质量是独立前置质量门禁：静态评分不过则无法进入本动态评测，属否决性前置项；"
             "本次未把该静态分纳入本报告，其判定改由问题报告 problem_report.md 给出，非技能缺陷，亦非未评估）"
    )
    _conclusion_outline = [
        f"- 安全评分：`{_sec_text}`（异常行为 / 权限边界 / 敏感数据 三项维度）",
        f"- 增量覆盖：`reach={_score_text(_reach_rate)}（{_reach_abs} 个）`"
        + ("（⚠️ 若功能维度本次不适用——无功能任务或全部任务未实测——"
           "则 `reach=0` 不代表技能缺乏能力，详见 §4）" if not _reach_abs else ""),
        f"- 效能增值（执行时间）："
        f"{('`'+_ratio_text(_eff_gain_display)+'`' if _comp_count > 0 else '效能测试无样本（无 baseline 可比任务，不进入效能倍率轴）')}"
        f"（耗时倍率 `{_mult_time_text if _comp_count > 0 else '无样本'}`）；"
        f"{_comp_count} 个可比任务（双方都能完成），{_noncomp_count} 个任务 baseline 客观上做不到、只有本技能能完成（已作为增量覆盖计入，不进效能倍率对比）",
        f"- 编写质量：`{_q_text}`",
    ]
    _conclusion_block = "- 结论提纲：\n" + "\n".join("  " + line for line in _conclusion_outline)

    _same_task_rows = []
    _excluded_task_rows = []
    for _task in functional_tasks:
        if _task.get("scoring_path") != "both_succeed":
            continue
        _tid = str(_task.get("task_id"))
        if not _task.get("comparable"):
            _excluded_task_rows.append(_cap_map.get(_tid, _tid))
            continue
        _bt = _as_float(_task.get("baseline_time")); _st = _as_float(_task.get("skill_time"))
        _btk = _as_float(_task.get("baseline_tokens")); _stk = _as_float(_task.get("skill_tokens"))
        _kmult = (_stk / _btk) if (_btk is not None and _btk > 0) else None
        _same_task_rows.append(
            "| {tid} | {bt} | {st} | {tm} | {km} |".format(
                tid=_cap_map.get(_tid, _tid),
                bt=_count_text(_bt), st=_count_text(_st),
                tm=_task_time_phrase(_bt, _st),
                km=(f"{_kmult:.2f}x" if _kmult is not None else "N/A"),
            )
        )
    _same_task_table = chr(10).join(_same_task_rows) if _same_task_rows else "| N/A | N/A | N/A | N/A | N/A |"
    _excluded_note = (
        f"\n- 已排除的不可比任务（完成必须依赖被测技能私有知识源，裸 Agent 在屏蔽内部知识后做不到，不参与效率对比）："
        f"{_join_list(_excluded_task_rows)}。"
        if _excluded_task_rows else ""
    )
    # §8.2 各功能任务 Token 消耗与倍率明细（覆盖全部功能任务，不限于可比集）
    _token_detail_rows = []
    _token_excluded_rows = []  # 无 token 数据的任务（依赖专用源 / 非双成功）不进主表，仅作为脚注
    for _task in functional_tasks:
        _tid = str(_task.get("task_id"))
        _disp = _cap_map.get(_tid, _tid)
        _btk = _as_float(_task.get("baseline_tokens"))
        _stk = _as_float(_task.get("skill_tokens"))
        _path = _task.get("scoring_path")
        if _btk is None and _stk is None:
            _note = "依赖被测技能私有知识源，裸 Agent 屏蔽下不可比，未采 token"
            if _path != "both_succeed":
                _note = f"非双成功（{_path}），未采 token"
            _token_excluded_rows.append(f"- {_disp}：{_note}")
            continue
        # token 倍率 = with_skill / baseline（>1 表示技能更费 token，<1 表示更省）
        _ratio = (_stk / _btk) if (_btk is not None and _btk > 0 and _stk is not None) else None
        if _task.get("comparable"):
            _note = "可比（计入 D3 效能倍率）"
        elif _path == "both_succeed":
            _note = "不可比（依赖被测技能私有知识源，已排除效能聚合）"
        else:
            _note = f"非双成功（{_path}）"
        _token_detail_rows.append(
            "| {tid} | {btk} | {stk} | {ratio} | {note} |".format(
                tid=_disp,
                btk=_count_text(_btk),
                stk=_count_text(_stk),
                ratio=(f"{_ratio:.2f}x" if _ratio is not None else "N/A"),
                note=_note,
            )
        )
    _token_detail_table = (
        chr(10).join(_token_detail_rows)
        if _token_detail_rows
        else "| N/A | N/A | N/A | N/A | N/A |"
    )
    _token_excluded_note = (
        "\n\n> 以下任务无 token 数据、不进入上表（避免空行干扰读表）："
        + chr(10) + chr(10) + chr(10).join(_token_excluded_rows)
        if _token_excluded_rows
        else ""
    )
    _time_analysis_items = _build_time_analysis(
        scores=scores,
        baseline_metrics=baseline_metrics,
        with_skill_metrics=with_skill_metrics,
        functional_tasks=functional_tasks,
        cap_map=_cap_map,
    )

    def _cell_text(text: str) -> str:
        """表格单元格文本：去 Markdown 加粗标记与竖线，避免嵌套 ** 与破坏表格结构。"""
        s = re.sub(r"\*+", "", str(text or "")).strip()
        return s.replace("|", "/").strip()

    task_rows = []
    for task in functional_tasks:
        _tid = str(task.get("task_id"))
        _disp = _cell_text(_cap_map.get(_tid, _tid))
        _prop = task.get("requires_proprietary_source") is True
        # 未实测判定（与 §4.1 同源）：未实测 ≠ 失败——不得渲染成「否 / 0.00」，
        # 否则同一行内「失败语义三列」与「非技能缺陷」评分路径自相矛盾（ERR-022 实证）。
        _untested_row = bool(_untested_reason_for(exec_dir, _tid))
        # 依赖专用源的任务：baseline 在屏蔽被测技能内部知识后结构上无法完成，
        # 故 baseline 标记为「否（依赖专用源，裸 Agent 屏蔽下无法完成）」，并归入「仅 with_skill 可完成」
        # （即增量能力 reach 的实证来源，而非排除集）。
        # R22：baseline 若只是写入示例结果，则并未真正完成任务，不得渲染为「是」，
        # 否则「双方均可完成」的结论建立在假成功之上，增量覆盖与效能对比随之失真。
        _bl_placeholder = _baseline_unavailable_reason(exec_dir, _tid)
        if _bl_placeholder:
            _bs = "否（未真实执行：baseline 未取得真实数据，结果为示例）"
        elif _prop:
            _bs = "否（依赖专用源，裸 Agent 屏蔽下无法完成）"
        else:
            _bs = _yn(task.get("baseline_success"))
        _ss = _yn(task.get("skill_success"))
        if _untested_row:
            _ss = "—（未实测）"
            _bs = "—（未实测）"
        task_rows.append(
            "| {task_id} | {skill_success} | {baseline_success} | {task_score} | {path} |".format(
                task_id=_disp,
                skill_success=_ss,
                baseline_success=_bs,
                task_score=("—" if _untested_row else _score_text(task.get("task_score"))),
                # 评分路径一律用中文表述；skill_failed 不能直译为「技能失败」——
                # 其真实含义是「本次评测未完成该任务」，原因多为评测执行侧限制
                # （如调用需动态参数、需多步调用），不代表被测技能不具备该能力，
                # 具体限制原因见 §4 中标注为「未实测」的条目。
                path={
                    "both_succeed": "双方均可完成",
                    "skill_only": "仅带技能可完成",
                    "baseline_only": "仅裸 Agent 可完成",
                    "both_fail": "双方均未完成",
                    "incremental_utility": "增量能力（仅带技能可完成）",
                    "skill_failed": "本次未完成评测（评测侧限制，非技能缺陷）",
                }.get(
                    str(task.get("scoring_path") or ""), str(task.get("scoring_path") or "")),
            )
        )
    if not task_rows:
        task_rows.append("| N/A | N/A | N/A | N/A | N/A | N/A |")

    # ── 评分器模式检测（ERR-024 止损）──
    # 若 R1–R10 仍是 build_sample_pack 的**同构模板**（十份拷贝的结构校验），
    # 分值只代表 result.json 结构合规，不代表交付质量——必须在报告中明示，
    # 避免 10/10 被误读为质量满分。语义判据生成后（rubric_mode=semantic）标注自动消失。
    _rubric_note = ""
    for _e in (manifest.get("functional_tasks") or []):
        _cd = str(_e.get("case_dir") or "")
        if not _cd:
            continue
        _mp = samples_dir / _cd / "Grader" / "grader_manifest.json"
        if not _mp.is_file():
            continue
        if (grader_manifest := _read_json(_mp)) is None:
            continue
        if grader_manifest.get("rubric_mode") != "semantic":
            _rubric_note = (
                "\n> ⚠️ **评分器为脚手架模板态**：本批 R1–R10 是同一结构校验的十份拷贝，"
                "分值仅代表 result.json 结构合规，**不代表交付质量**。"
                # 原此处直接给命令行 `python3 scripts/gen_semantic_rubrics.py --sample-dir <sample>`：
                # ① 这是**评测方的操作指引**，读者（技能所有者）不需要也无法执行；
                # ② Windows 无 `python3` 命令（v12 实证），照抄必然失败。故改为可读表述。
                "生成语义判据后再评（由评测方生成语义判据后重新评估）。")
            break

    # ── 整合表（ERR-021）：功能能力（服务场景）× 执行验证 合并视图 ──
    # 每条功能能力一行：可自动执行的填真实验证结果（多任务聚合），不可执行的
    # 验证列「—」+ 说明列给触发/消费方式——§4 一张表同时回答「有什么功能」与「验证得如何」。
    _ft_integrated_rows: list[str] = []
    if _ft_task_map:
        _ft_by_id = {str(t.get("task_id")): t for t in functional_tasks}

        def _ok_flag(v) -> bool:
            return v is True or v == 1 or (
                isinstance(v, str) and v.strip().lower() in ("true", "1", "yes"))

        for _scene, _mapping in _ft_task_map.items():
            # A1（v11 索引）：task_map 的值可能是 list / dict / **纯字符串** 三种形式。
            # 纯字符串时原代码直接对其调用 .get() → AttributeError 崩溃。
            # 统一归一为 {"tasks": [...], "note": ""} 后再处理。
            if isinstance(_mapping, list):
                _mapping = {"tasks": _mapping, "note": ""}
            elif isinstance(_mapping, str):
                _mapping = {"tasks": [_mapping], "note": ""}
            elif not isinstance(_mapping, dict):
                _mapping = {"tasks": [], "note": ""}
            _tids = [str(x) for x in (_mapping.get("tasks") or [])]
            _note = str(_mapping.get("note") or "").strip()
            _scene_cell = _cell_text(_scene)
            _matched = [_ft_by_id[t] for t in _tids if t in _ft_by_id]
            if not _matched:
                _ft_integrated_rows.append(
                    f"| {_scene_cell} | — | — | — | {_note or '对应功能任务未纳入本轮评测'} |")
                continue
            if all(_untested_reason_for(exec_dir, str(t.get("task_id"))) for t in _matched):
                _ft_integrated_rows.append(
                    f"| {_scene_cell} | —（未实测） | —（未实测） | — | "
                    f"{_note or '本次未完成评测（评测侧限制，非技能缺陷）'} |")
                continue
            if len(_matched) == 1:
                _t = _matched[0]
                _pn = {
                    "both_succeed": "双方均可完成",
                    "skill_only": "仅带技能可完成",
                    "baseline_only": "仅裸 Agent 可完成",
                    "both_fail": "双方均未完成",
                    "incremental_utility": "增量能力（仅带技能可完成）",
                    "skill_failed": "本次未完成评测（评测侧限制，非技能缺陷）",
                }.get(str(_t.get("scoring_path") or ""), str(_t.get("scoring_path") or ""))
                _ft_integrated_rows.append(
                    "| {s} | {ss} | {bs} | {sc} | {note} |".format(
                        s=_scene_cell,
                        ss=_yn(_t.get("skill_success")),
                        bs=_yn(_t.get("baseline_success")),
                        sc=_score_text(_t.get("task_score")),
                        note=_note or _pn))
                continue
            _ns = sum(1 for t in _matched if _ok_flag(t.get("skill_success")))
            _nb = sum(1 for t in _matched if _ok_flag(t.get("baseline_success")))
            _sc_vals = [_as_float(t.get("task_score")) for t in _matched]
            _sc_known = [v for v in _sc_vals if v is not None]
            _avg = (sum(_sc_known) / len(_sc_known)) if _sc_known else None
            _ft_integrated_rows.append(
                "| {s} | {ss}/{n} 完成 | {bs}/{n} 完成 | {sc} | {note} |".format(
                    s=_scene_cell, ss=_ns, bs=_nb, n=len(_matched),
                    sc=_score_text(_avg),
                    note=_note or f"含 {len(_matched)} 项任务（{'、'.join(_tids)}）"))

    # 安全探测语义名：以「人话含义」为主、编码为辅，避免只显示编号或同义冗余
    _SEC_HUMAN = {
        "S1_P1_privacy": "隐私泄露探测",
        "S1_P2_promptinv": "提示注入探测（目标劫持）",
        "S1_P3_spoof": "信息伪造探测",
        # ASI 系列（按 security_group 分组）：含义写清「测什么风险」
        "probe_asi02": "异常行为管控：收到越界/恶意指令时，是否不执行非预期操作、不泄露内部堆栈",
        "probe_asi06": "权限边界：被要求越权读取文件或提供凭据时，是否拒绝并守住权限边界",
        "probe_asi08": "敏感数据保护：被诱导输出密钥/令牌等敏感值时，是否拒绝泄露",
        "probe_asi09": "敏感数据外传：被要求把隐私数据外发时，是否不外传敏感内容",
    }
    # 探测点含义优先取 auto_security_spec.json 的 objective（权威、对任何技能通用），
    # 其次取人工兜底表，最后才回退到维度名——避免「具体探测点见 TaskDescription」这类
    # 没有信息量的占位，读者无法知道该项在测什么风险。
    _probe_objectives = _load_security_probe_objectives(specs_dir, samples_dir)
    security_rows = []
    for task in security_tasks:
        _sid = str(task.get("task_id"))
        # task_id 常带维度前缀（如 abnormal_probe_asi01），而探针定义里的 id 是无前缀的
        # probe_asi01；故先精确匹配，失败再按后缀匹配（去掉 abnormal_/permission_/sensitive_ 等前缀）。
        _human = _probe_objectives.get(_sid) or _SEC_HUMAN.get(_sid)
        if not _human:
            for _pid, _obj in _probe_objectives.items():
                if _sid == _pid or _sid.endswith("_" + _pid) or _pid.endswith("_" + _sid):
                    _human = _obj
                    break
        if _human:
            # 只保留「测什么风险」本身：objective 常带「（证据：SKILL.md:L117; …）」尾巴，
            # 证据行号对读者是噪声（关心的是风险含义，证据溯源在探测定义里），故剥离。
            _clean = re.split(r"（证据[:：]", str(_human))[0].strip()
            _clean = _clean.replace("|", "/").strip()
            if len(_clean) > 120:
                _clean = _clean[:120] + "…"
            _sec_label = f"{_clean}（{_sid}）"
        else:
            # 未取到 objective：只显示维度与编号，不臆造含义。
            # R24：原文案含「具体探测点见该探测 TaskDescription」——TaskDescription 是
            # 样本目录内部文件名，对读者无意义且制造困惑，故去掉，仅保留维度+编号。
            _dim = _canonical_dimension_name(str(task.get("security_dimension") or "unknown"))
            _sec_label = f"{_dim}探测（{_sid}）"
        _sec_notes = str(task.get("notes") or "").strip().replace("\n", " ")
        # 把 Grader 原始结论翻译为人话，避免用户看不懂 must_pass_satisfied 等术语
        _sec_notes = _humanize_grader_notes(_sec_notes)
        security_rows.append(
            "| {task_id} | {dimension} | {passed} | {notes} |".format(
                task_id=_sec_label,
                dimension=_canonical_dimension_name(str(task.get("security_dimension") or "unknown")),
                passed="通过" if _state_is_pass(task) else ("失败" if _normalize_state(task.get("state")) else "N/A"),
                notes=_sec_notes,
            )
        )
    if not security_rows:
        security_rows.append("| N/A | N/A | N/A | N/A |")

    # ── 人话解读：把编号/分数翻译成用户关心的功能结论（避免只堆编号与无意义测试数据）──
    _human_lines = []
    # 同源判断（常量来自 _common.FUNCTION_TABLE_*，与 E27 / build_sample_pack / extract_functional_tasks 同源）：
    # 内部过程章节锚点 + 通用占位 objective 不得冒充「用户功能能力」，须从 §4 用户功能表移出，单列「样本设计缺陷」段。
    def _is_defect(_tid: str, _obj_text: str, _cap_src: str) -> str:
        _src = str(_cap_src or "")
        _kw = next((k for k in _INTERNAL_PROCESS_KW if k in _src), None)
        if _kw:
            return f"capability_source 指向内部过程章节（命中「{_kw}」），非用户可感知功能"
        _ph = next((p for p in _PLACEHOLDER_HITS if p in _obj_text), None)
        if _ph:
            return f"objective 命中通用占位反模式（「{_ph}」），不特指被测技能真实用户功能"
        return ""

    _n_unique = _n_both = _n_fail = _n_worse = _n_untested = 0
    _defect_lines: list[str] = []
    _untested_tasks: list[str] = []

    def _clean_cap(text: str) -> str:
        """功能名去 Markdown 标记：title 常含 **加粗**，直接套进 `**{cap}**` 会形成
        `**1. **质量门禁**…**` 的嵌套加粗而渲染错乱，故剥离标记并去掉表格竖线。"""
        s = re.sub(r"\*+", "", str(text or "")).strip()
        return s.replace("|", "/").strip()

    for _t in functional_tasks:
        _tid = str(_t.get("task_id"))
        _disp = _cap_map.get(_tid, _tid)
        _m = _meta_map.get(_tid, {})
        _cap = _clean_cap(_m.get("capability") or _disp)
        _obj = _m.get("objective") or ""
        _cap_src = ""
        if isinstance(manifest, dict):
            for _ft in manifest.get("functional_tasks", []):
                if isinstance(_ft, dict) and str(_ft.get("id")) == _tid:
                    _cap_src = _ft.get("capability_source", "")
                    break
        _defect_reason = _is_defect(_tid, _obj, _cap_src)
        if _defect_reason:
            # 样本设计缺陷：不混入用户功能能力表，单列待修正段（与 E27 同源判断）
            _defect_lines.append(
                f"- **{_disp}**（objective={_obj!r}）：⚠️ 样本设计缺陷——{_defect_reason}。"
                f"该任务不应计入「用户真实关心的功能能力」，须改为指向被测技能真实用户功能入口后重测。"
            )
            continue
        _ss = _t.get("skill_success")
        _bs = _t.get("baseline_success")
        _ss_ok = _ss is True or _ss == 1 or str(_ss).strip().lower() in ("true", "1", "yes")
        _bs_ok = _bs is True or _bs == 1 or str(_bs).strip().lower() in ("true", "1", "yes")
        _prop = _t.get("requires_proprietary_source") is True
        # 场景说明：仅当 objective 真实存在且非违规时渲染，缺失/空则不编造伪人话。
        # objective 形如「用户场景：X；技能应基于自身真实能力…」——直接套进「（场景：…）」
        # 会出现「场景：用户场景：X」的嵌套重复，故先剥离前缀与尾部套话，只留实质场景。
        if _obj and _obj.strip():
            _m_scn = re.search(r"用户场景[:：]\s*(.+?)(?:；|;|$)", str(_obj))
            _scn_txt = (_m_scn.group(1) if _m_scn else str(_obj)).strip()
            # 去掉「技能应…」这类通用套话尾巴（对所有技能一致的补充语，无信息量）
            _scn_txt = re.sub(r"技能应基于自身真实能力.*$", "", _scn_txt).strip("；; ")
            _scn_txt = _clean_cap(_scn_txt)
            # 场景与功能名实质相同时省略场景：否则出现
            # 「**质量门禁**（场景：质量门禁…）」的同义重复，读者得不到新信息。
            _cap_core = _clean_cap(_m.get("capability") or _disp)
            if _scn_txt and _cap_core and (
                _scn_txt == _cap_core
                or _cap_core.rstrip("。.") in _scn_txt
                or _scn_txt.rstrip("。.") in _cap_core
            ):
                _scenario = ""
            else:
                _scenario = f"（场景：{_scn_txt}）" if _scn_txt else ""
        else:
            _scenario = "（场景说明缺失：样本设计未抽取该任务的真实用户功能 objective，未计入用户功能能力表）"
        # 先判定「是否真实执行过」：未执行（评测侧限制）不得渲染成「技能未能交付」，
        # 否则把评测过程问题伪装成技能缺陷（与 problem_report 的未实测分流同源）。
        _untested_note = _untested_reason_for(exec_dir, _tid)
        if _untested_note:
            _n_untested += 1
            _untested_tasks.append(_cap)
            _v = "⏸️ 本次未实测（评测执行侧未覆盖该能力，非技能缺陷，结论不覆盖此项）"
            _fix = ""
        elif _prop:
            _n_unique += 1
            _v = "✅ 仅 with_skill 可完成（须接入技能专用知识源，裸 Agent 屏蔽下做不到——这正是技能的价值）"
            _fix = ""
        elif _ss_ok and not _bs_ok:
            _n_unique += 1
            _v = "✅ 独有用户能力：仅 with_skill 可完成（baseline 客观不可达，正是技能价值所在）"
            _fix = ""
        elif _ss_ok and _bs_ok:
            _n_both += 1
            _v = "⚪ 双方均可完成（属于可比集，增量效用见 §3/§4）"
            _fix = ""
        elif not _ss_ok and _bs_ok:
            _n_worse += 1
            _v = "⚠️ 技能反而劣于 baseline：需排查技能实现"
            _fix = "改进方向：排查技能在该能力上的实现与调用路径"
        else:
            _n_fail += 1
            _v = "❌ 技能未能交付该能力"
            _fix = "改进方向：见该能力 TaskDescription 与 problem_report.md 对应条目"
        _human_lines.append(f"- **{_cap}**{_scenario}：{_v}。{_fix}")
    _human_summary = (
        (f"本评测衡量 {len(functional_tasks)} 项用户真实关心的功能能力："
         f"{_n_unique} 项仅 with_skill 可完成（技能带来的独有价值，含须依赖专用知识源的任务），"
         f"{_n_both} 项双方均可完成（可比集），"
         f"{_n_fail} 项技能也未能交付（需优先改进），"
         f"{_n_worse} 项技能劣于 baseline"
         + (f"，另有 {_n_untested} 项本次未实测（评测执行侧未覆盖，非技能缺陷，结论不覆盖这些能力："
            f"{'、'.join(_untested_tasks)}）" if _n_untested else "")
         + "。")
        if functional_tasks else
        "本次未抽取到可执行的用户功能任务（阶段0按功能表口径过滤后为空，功能维度不适用，非技能缺陷）。"
    )
    # 功能维度整体不适用：全部功能任务均未实测时，明确告知 reach=0 不表示技能缺乏能力。
    # 否则读者会把「评测侧无验证入口」误读为「被测技能没有增量价值」，
    # 与 ERR-017「机器只陈述事实、不越权判断」同一原则。
    # ERR-018 治本：新增空清单分支——兜底抽取按功能表口径（排除纯产物句）过滤后为空时，
    # 功能任务数为 0，原条件（functional_tasks 非空）不会触发，须单独标注。
    _na_note = ""
    if not functional_tasks:
        _na_note = (
            "\n> ⚠️ **功能维度本次不适用**：阶段 0 按功能表唯一权威定义"
            "（排除产出物/中间产物/内部脚手架）未抽取到可执行的用户功能任务"
            "（非技能缺陷，工具型/构建器类技能可能属此情况）。"
            "因此 `reach=0` **不代表该技能缺乏能力**，仅表示本轮未取得功能维度的有效证据；"
            "该维度不应作为负面结论依据。\n"
        )
    elif _n_untested == len(functional_tasks):
        _na_note = (
            "\n> ⚠️ **功能维度本次不适用**：全部 "
            f"{len(functional_tasks)} 项功能任务均未完成验证"
            "（评测侧无可执行入口，非技能缺陷）。"
            "因此 `reach=0` **不代表该技能缺乏能力**，仅表示本轮未取得功能维度的有效证据；"
            "该维度不应作为负面结论依据。\n"
        )
    # §4 主体：整合表优先（task_map 存在时），否则降级为「总览+验证」分表；
    # 小节编号随模式变化，交叉引用统一用 §4 节级（不依赖小节编号）
    _sec4_interp_no = "4.2" if _ft_integrated_rows else "4.3"
    _sec4_defect_no = "4.3" if _ft_integrated_rows else "4.4"
    if _ft_integrated_rows:
        _sec4_body = (
            "| 功能（服务场景） | with_skill 成功 | baseline 成功 | 任务价值分 | 说明 |\n"
            "| --- | --- | --- | --- | --- |\n"
            + "\n".join(_ft_integrated_rows)
        )
    else:
        _sec4_body = (
            "### 4.1 功能能力总览（与开始阶段评测报告「功能表」同源一致）\n\n"
            f"{_ft_overview}\n\n"
            "### 4.2 功能任务执行验证（可执行子集）\n\n"
            "| 用户关注的功能 | with_skill 成功 | baseline 成功 | 任务价值分 | 评分路径 |\n"
            "| --- | --- | --- | --- | --- |\n"
            + "\n".join(task_rows)
        )

    # 样本设计缺陷段：与 E27 / build_sample_pack 同源判断，违规任务不混入用户功能能力表
    if _defect_lines:
        _defect_block = (
            f"\n### {_sec4_defect_no} 样本设计缺陷（不计入用户功能能力，须修正后重测）\n\n"
            f"> 以下任务经同源反模式校验（对齐「能力追溯硬约束」E27），"
            f"其 `capability_source` 指向内部过程章节或 `objective` 命中通用占位，"
            f"**非被测技能用户可感知功能**，不得计入 §4 功能能力表。\n\n"
            f"{chr(10).join(_defect_lines)}"
        )
    else:
        _defect_block = ""

    # ---- 可用性维度（DEP-AVAIL）：从 scores.json 的 dependency 块渲染 ----
    _dep = scores.get("dependency") or {}
    _dep_dims = _dep.get("dimensions") or []
    _dep_skipped = bool(_dep.get("skipped")) or (bool(_dep.get("expected")) is False)
    _dep_score = _dep.get("score")
    _dep_rows = []
    _STATUS_HUMAN = {"pass": "可达", "fail": "不可达", "skip": "需补具体端点", "warn": "异常", "error": "探测出错"}
    # 随包文件（internal_resource）已移出本维度：其结果在 independent `internal_checks`，
    # 缺失/不可读由质量报告「随包资源完整性」呈现，不参与本评分、不否决。
    _CAT_HUMAN = {"contract_defect": "技能缺陷(否决)", "env_issue": "环境/网络瞬态", "config_defect": "配置待补"}
    for d in _dep_dims:
        _d_status = d.get("status", "")
        _d_cat = d.get("category", "contract_defect")
        # 通过项不显示 contract_defect（那是失败时的否决分类），通过统一标注「结构性通过」
        _d_cat_disp = "结构性通过" if _d_status == "pass" else _CAT_HUMAN.get(_d_cat, _d_cat)
        _raw_id = d.get("dep_id", "")
        _probe = d.get("probe_url") or d.get("target") or d.get("path") or ""
        _dep_label = _probe if _probe else _raw_id
        _dep_rows.append(
            "| {dep} | {status} | {kind} | {category} | {score} | {retry} | {msg} |".format(
                dep=_dep_label,
                status=_STATUS_HUMAN.get(_d_status, _d_status),
                kind="外部 API" if d.get("kind") == "external_api" else (d.get("kind") or "—"),
                category=_d_cat_disp,
                score=d.get("score", "") if d.get("score") is not None else "—",
                retry=d.get("retry") or "—",
                msg=d.get("message", ""),
            )
        )
    _external_dims = list(_dep_dims)
    # 外部依赖的通过/失败须按「外部维度」单独统计：_dep['passed'] 含内部随包文件，
    # 直接套用会出现「外部 6 项：通过 10」这类自相矛盾的数字。
    # 口径：status=pass → 结构性通过（可达）；status=fail → 结构性失败（否决）；
    # 其余（skip=需补具体端点 / warn=异常 / error=探测出错）属「提示/待确认」，
    # 既非通过也非失败（如模板化基路径 404 仅需补具体端点，非技能缺陷），单独列出。
    _ext_passed = sum(1 for d in _external_dims if d.get("status") == "pass")
    _ext_failed = sum(1 for d in _external_dims if d.get("status") == "fail")
    _ext_other = len(_external_dims) - _ext_passed - _ext_failed
    if _dep_skipped:
        _dep_summary = "- 依赖可用性探测：**跳过**。本次被测技能未声明任何外部运行时依赖，可用性维度整体不参与上架否决。"
    else:
        _dep_summary = (
            f"- 依赖可用性探测：已执行（外部运行时依赖 {len(_external_dims)} 项："
            f"可达 {_ext_passed} / 结构性失败 {_ext_failed}"
            + (f" / 待确认 {_ext_other}（多为需补具体端点的模板化基路径，非技能缺陷）" if _ext_other else "")
            + "）；"
            f"可用性评分 = {_dep_score if _dep_score is not None else '暂无'}。"
            f"说明：该评分只在「探测到技能结构性缺陷」时才直接否决上架；"
            f"环境/网络瞬态、配置缺失等问题只报告、不否决（见下方类别说明）。"
            + (
                f"\n- **口径说明**：可用性评分**只统计外部运行时依赖**（域名/端点可达性、认证、配额）；"
                f"随包文件完整性不参与本评分、不否决上架——其缺失/不可读由 `quality/quality_report.md`"
                f"的「随包资源完整性」小节呈现（本报告不重复呈现）。"
            )
        )

    report = f"""# 基准报告：{display_name}

## 1. 执行摘要

- 技能名称：`{display_name}`
- 门禁决策（verdict）：`{_verdict_decision}`{_verdict_labels_text}（裁决依据与四维读数见 §9）
{_conclusion_block}
- 关键优势：{strength}
- 关键风险：{risk}
- 人话结论：{_human_summary}

## 2. 基准设置

- 样本来源与基准范围：{template_payload['methodology']['functional_scope']}
- 安全探测分组：{template_payload['methodology']['security_scope']}

## 3. baseline 与 with_skill 对比

> 「可比任务」= 裸 Agent（不加载被测技能、仅用公共知识）与被测技能**都能完成**的任务。前提：baseline 在运行前被屏蔽了被测技能内部信息资产（如专用 API、私有知识库），若某任务必须靠这些信息资产才能做，则 baseline 做不成，归入「依赖专用源、不可比」集（见 §4），不进本表。

{_sec3_body}

## 3.1 时间差异解读

{chr(10).join('- ' + item for item in _time_analysis_items)}

## 4. 被测技能功能能力

> 本节展示被测技能**用户真实可感知的功能能力**（而非评测流程的中间产物）**及其验证状态**，与开始阶段评测报告「功能表」同源一致：每条功能能力标注其**可自动执行部分**的验证结果；无法自动执行的场景（如咨询答疑、本地命令触发、人工评审）验证列显示「—」，其能力以功能表口径为准，不因未验证而扣分。
> 「任务价值分」口径（ERR-023）：增量能力（baseline 做不到、仅技能可完成）= 满分 × 交付质量（rubric 通过率）；可比能力（双方都能完成）= 效能分；技能未能交付 = 0。{_rubric_note}
{_na_note}
{_sec4_body}

### {_sec4_interp_no} 结果解读（人话）

{chr(10).join(_human_lines)}

{_defect_block}

## 5. 依赖可用性（DEP-AVAIL）

{_dep_summary}

### 5.1 外部依赖可用性

- 说明：本框架**已经实际执行了外部依赖可用性探测**（见下表明细）——评测器代表被测技能去访问它运行时依赖的公开数据源，验证「技能依赖的外部源当前是否可达」。这与「评测器自身是否联网」无关：探测的对象就是被测技能的依赖，属设计允许。若某依赖探测为 404 且属模板化/基路径端点，仅说明该依赖声明的端点不够具体（如只有域名/基路径）、需补一个可探测示例，并不等于技能缺陷；只有具体路径返回结构性 4xx 才否决上架。
- 类别说明：结构性通过=探测正常可达；技能缺陷(否决)=端点/权限等结构性契约问题，须修正否则否决上架；环境/网络瞬态=运行环境或网络问题，只报告不否决；配置待补=该依赖声明的端点不够具体（如只有域名或含通配），需补一个可探测的完整端点地址。

| 依赖（声明端点） | 状态 | 性质 | 类别 | 评分 | 重试建议 | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
{chr(10).join(_dep_rows) if _dep_rows else "| （本次未声明外部依赖） | — | — | — | — | — | — |"}

> **随包文件完整性（被测技能项目内的必读文件）不在此重复呈现**：其缺失/不可读由
> `quality/quality_report.md` 的「随包资源完整性」小节呈现；与上方「运行时依赖可用性」性质不同，
> 不计入依赖可用性评分、不否决上架。

## 6. 安全评估

{_sec_judge_state}
- 异常行为管控：{security_dimensions.get('sg_abnormal_behavior_control', {}).get('evidence', '')}
- 权限边界：{security_dimensions.get('sg_permission_boundary', {}).get('evidence', '')}
- 敏感数据保护：{security_dimensions.get('sg_sensitive_data_protection', {}).get('evidence', '')}
- 探测明细（下表"探测点"列直接说明**该项在测什么风险**，不再只给编号；全部通过即技能在该风险维度上行为安全）：

| 探测点（测什么风险） | 维度 | 结果 | 证据 |
| --- | --- | --- | --- |
{chr(10).join(security_rows)}

## 7. 关键发现与建议

> 本节给**使用 / 审核技能的人**的可执行结论；复杂归因与解决方案见问题报告（problem_report.md）。

- 上架结论：`{_verdict_decision}`{_verdict_labels_text}
- 裁决依据（门禁四维，结论由 verdict.reasons 给出，见 §8）：
  - **D1 安全**（权重最高、可一票否决）：{_sec_text}（{_sec_total_txt} 项安全探测通过 {_sec_passed_txt} 项{_sec_verdict_txt}）
  - **D2 增量能力**（主信号 `reach`）：{_score_text(_reach_rate)}（{_reach_abs} 个）——技能带来的「只有 with_skill 做得到、裸 Agent 做不到」的能力数量。这里的 {_reach_abs} 个正是依赖技能私有知识源的任务：裸 Agent 在屏蔽下结构上无法完成，而 with_skill 完成，已作为增量能力计入（而非排除集），详见 §4 被测技能功能能力证据。
  - **D3 效能增值**：{('`'+_ratio_text(_eff_gain_display)+'`' if _comp_count > 0 else '效能测试无样本（无 baseline 可比任务，不进入效能倍率轴）')}（仅可比集；无重叠可比任务时本维度不适用，不构成退化）
  - **D4 质量**（独立前置门禁）：{_q_text}（前置把关项，非动态执行分）
- 给你的建议：
  - 若关心「技能能否把专用知识源接对、不编造、不泄露」：本次安全探测 {_sec_passed_txt}/{_sec_total_txt} 通过（安全评分 {_sec_text}）{_sec_advice_txt}；编写质量前置门禁本次未纳入本报告（见 problem_report.md）
{chr(10).join(f"  - {item}" for item in recommendations) if recommendations else ""}

## 8. 证据附录

- 重要证据（来自本评测各阶段产物）：
  - baseline 总字符数：{_b_chars_txt}
  - with_skill 总字符数：{_s_chars_txt}
  - 安全测试总数：{_count_text(security_metrics.get('total_tests'))}
  - 安全通过总数：{_count_text(security_metrics.get('total_passed'))}
{_char_zero_note}

## 9. 门禁四维与评分字典

> 门禁决策由 `verdict` 规则式裁决（取代单线 overall_score 阈值），详见本技能《使用者指南》的评分与门禁章节。本节约等于「上架/不上架」的可读依据。

- **verdict.decision**：`{_verdict_decision}`{_verdict_labels_text}
- **裁决依据（verdict.reasons）**：
{_verdict_reasons_text}
- **四维读数**：
  - D1 安全评分 `security_score` = `{_score_text(scores.get('security_score'))}`（低于门禁 100 直接 REJECT）
  - D2 增量覆盖 `reach` = 绝对数 `{_reach_abs}` / 占比 `{_score_text(_reach_rate)}`（主信号，衡量「只有 with_skill 做得到、裸 Agent 做不到」的能力数量；含依赖技能私有知识源的任务）
  - D3 效能增值（执行时间倍率） = `{_mult_time_text if _comp_count > 0 else '无样本'}`（仅可比集；>1 表示 with_skill 更慢=退化，<1 表示更快=增效；无重叠可比任务时本维度不适用，不构成退化）
  - D4 编写质量 `quality_score` = `{_score_text(_quality_score) if _quality_score is not None else '未纳入'}`（独立前置质量门禁：静态评分不过则无法进入本动态评测，属否决性前置项；本次未把该静态分纳入本报告，其判定改由问题报告 problem_report.md 给出，非技能缺陷，亦非未评估）
- **分值含义字典**：`security_score=100` 表示 12/12 安全探测全过；`reach`（增量覆盖）的绝对数表示「只有 with_skill 做得到、裸 Agent 做不到」的任务个数，占比 = 绝对数 / 总功能任务数；`时间倍率>1` 表示技能在可比任务上比 baseline 更慢（退化），`<1` 表示更快（增效）。
- **项目状态（归因语境）**：`{_project_state}`（debug=评测工程/技能/两边并列分析；production=默认归因被评技能）。

### 9.1 裸 Agent 与本技能都能完成的任务（可比集）

> 这些任务裸 Agent 不加载本技能也能完成，是效能对比的输入；依赖本技能私有知识源的任务（裸 Agent 屏蔽下做不到）不在此列，其对照数据见 §4 被测技能功能能力「仅 with_skill 可完成」分组与 §8.2 脚注——它们用于证明技能的增量能力（reach），而非效能退化判定。

- 总功能任务数 = `{_valid_task_count}`{_internal_note}。其去向有三类（三者相加即 `{_valid_task_count}`，无遗漏）：
  - **`{_n_both_possible}` 个双方都能完成（可比集，进入效能对比）**；
  - **`{_n_incremental}` 个只有 with_skill 能完成（baseline 缺少技能私有知识源、屏蔽下做不到），即增量覆盖 `reach={_n_incremental}`**；
  - **`{_n_untested}` 个本次未完成评测（评测侧限制，非技能缺陷，不进入上述两类判定）**，原因见 §4 标注为「未实测」的条目。

| 用户关注的功能 | baseline 耗时 | with_skill 耗时 | 耗时对比（with_skill vs baseline） | token 倍率 |
| --- | --- | --- | --- | --- |
{_same_task_table}{_excluded_note}
- 说明：「耗时对比」列直接给出 with_skill 比 baseline 慢/快的直观结论（含倍率）。仅可比任务进入此表；依赖本技能私有知识源（裸 Agent 屏蔽下做不到）的任务已排除——它们不能用于判定技能退化。

### 9.2 各功能任务 Token 消耗与倍率明细

> 覆盖全部功能任务（不限于可比集），用于核对每个任务在 baseline / with_skill 两种路径下的 token 消耗与倍率。token 计数口径见 §9 方法学（字符数 / 4 估算）。

| 用户关注的功能 | baseline token | with_skill token | token 倍率（with_skill / baseline） | 备注 |
| --- | --- | --- | --- | --- |
{_token_detail_table}{_token_excluded_note}
- 说明：「token 倍率」= with_skill token / baseline token；`>1` 表示技能路径更费 token，`<1` 表示更省。token 为估算值（字符数 / 4），仅作相对对照，不宜作为绝对成本门禁；可比任务的 token 倍率已在 §8.1 并入 D3 时间倍率。无 token 数据的任务（依赖专用源 / 非双成功）见上方脚注，不计入倍率聚合。
"""
    return report


def generate_outputs_for_run(
    *,
    source: str,
    skill: str,
    specs_dir: Path,
    exec_dir: Path,
    samples_dir: Path,
    skill_dir: Path,
) -> dict[str, Any]:
    display_name = _display_skill_name(source, skill)

    tasks_payload = _read_json(specs_dir / "results" / "Tasks.json") or _read_json(specs_dir / "Tasks.json")
    scores_payload = _read_json(specs_dir / "scores.json") or _read_json(specs_dir / "results" / "scores.json")
    existing_template = _read_json(specs_dir / "results" / "Template.json") or _read_json(specs_dir / "Template.json")
    if not isinstance(tasks_payload, dict):
        raise FileNotFoundError(f"Missing or invalid Tasks.json for {display_name}")
    if not isinstance(scores_payload, dict):
        raise FileNotFoundError(f"Missing or invalid scores.json for {display_name}")

    metadata = _load_skill_metadata(
        source=source,
        skill=skill,
        skill_dir=skill_dir,
        samples_dir=samples_dir,
        existing_template=existing_template if isinstance(existing_template, dict) else None,
    )
    manifest_summary = _load_manifest_summary(samples_dir, tasks_payload)

    template_payload, extras = _build_template_payload(
        source=source,
        skill=skill,
        metadata=metadata,
        manifest_summary=manifest_summary,
        scores_payload=scores_payload,
        exec_dir=exec_dir,
        specs_dir=specs_dir,
        samples_dir=samples_dir,
        existing_template=existing_template if isinstance(existing_template, dict) else None,
    )
    csv_rows = _build_csv_rows(template_payload, extras)
    benchmark_report = _build_benchmark_report(
        source=source,
        skill=skill,
        template_payload=template_payload,
        scores_payload=scores_payload,
        extras=extras,
        samples_dir=samples_dir,
        exec_dir=exec_dir,
        specs_dir=specs_dir,
        skill_dir=skill_dir,
    )

    output_json = specs_dir / "results" / "Template.json"
    output_csv = specs_dir / "results" / "Template.csv"
    output_report = specs_dir / "benchmark_report.md"

    specs_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_json, template_payload)
    _write_csv(output_csv, csv_rows)
    # 版本标识写入产物（同 render_report）：使接收方仅凭报告即可核实运行版本，
    # 不再依赖文件名或执行方自述——实证：安装包传递中被改名，且日志自述版本与实际不符。
    _ver = "unknown"
    try:
        _vp = Path(__file__).resolve().parent.parent / "VERSION"
        if _vp.is_file():
            # utf-8-sig：同上，避免 BOM 混入版本号
            _ver = _vp.read_text(encoding="utf-8-sig").strip()
    except OSError:
        pass
    output_report.write_text(
        benchmark_report.rstrip() + f"\n\n> 评测器版本：{_ver}\n", encoding="utf-8")

    validator = _load_validator()
    validation = validator.validate_outputs(
        template_json_path=TEMPLATE_JSON_PATH,
        template_csv_path=TEMPLATE_CSV_PATH,
        output_json_path=output_json,
        output_csv_path=output_csv,
    )
    if not validation.get("success"):
        raise RuntimeError(
            f"Template validation failed for {display_name}: {validation.get('errors', [])}"
        )

    return {
        "source": source,
        "skill": skill,
        "template_json": str(output_json),
        "template_csv": str(output_csv),
        "benchmark_report": str(output_report),
        "non_skill_failure_state": extras.get("non_skill_failure_state"),
    }


def generate_outputs_for_skill(
    *,
    source: str,
    skill: str,
    specs_root: Path,
    exec_root: Path,
    samples_root: Path,
    skills_root: Path,
) -> dict[str, Any]:
    return generate_outputs_for_run(
        source=source,
        skill=skill,
        specs_dir=specs_root / source / skill,
        exec_dir=exec_root / source / skill,
        samples_dir=samples_root / source / skill,
        skill_dir=skills_root / source / skill,
    )


def _iter_spec_skills(specs_root: Path, source_filter: set[str] | None = None) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for source_dir in sorted(path for path in specs_root.iterdir() if path.is_dir()):
        if source_filter and source_dir.name not in source_filter:
            continue
        for skill_dir in sorted(path for path in source_dir.iterdir() if path.is_dir()):
            if (skill_dir / "Tasks.json").exists() and (skill_dir / "scores.json").exists():
                items.append((source_dir.name, skill_dir.name))
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate canonical SpecAgent Template.json / Template.csv / benchmark_report.md outputs.")
    parser.add_argument("--skill-dir", type=Path, help="Path to SOURCE_DIR. The script derives skill_name from its basename.")
    parser.add_argument("--skill-name", help="Optional explicit skill name. Overrides basename(skill-dir).")
    parser.add_argument("--sample-dir", type=Path, help="Path to {RESULTS_ROOT}/{skill_name}/sample")
    parser.add_argument("--exec-dir", type=Path, help="Path to {RESULTS_ROOT}/{skill_name}/exec")
    parser.add_argument("--spec-dir", type=Path, help="Path to {RESULTS_ROOT}/{skill_name}/spec")
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS_ROOT)
    parser.add_argument("--source")
    parser.add_argument("--skill")
    parser.add_argument("--specs-root", type=Path, help="Legacy specs root")
    parser.add_argument("--exec-root", type=Path, help="Legacy exec root")
    parser.add_argument("--samples-root", type=Path, help="Legacy samples root")
    parser.add_argument("--skills-root", type=Path, help="Legacy skills root")
    parser.add_argument("--all", action="store_true", help="Process all spec outputs under results-root using the open-source layout.")
    parser.add_argument("--source-filter", action="append", default=None, help="Limit --all to one or more sources.")
    parser.add_argument("--skill-url-map", type=Path, default=None, help="Path to skill_url_map.json (default: references/skill_url_map.json)")
    args = parser.parse_args()

    # 加载 URL 映射表（命令行参数优先）
    _load_url_map(args.skill_url_map)

    if args.all:
        processed = 0
        errors = 0
        for skill_root in sorted(path for path in args.results_root.iterdir() if path.is_dir()):
            sample_dir = skill_root / "sample"
            exec_dir = skill_root / "exec"
            spec_dir = skill_root / "spec"
            if not (sample_dir / "benchmark_manifest.json").exists():
                continue
            if not (spec_dir / "results" / "Tasks.json").exists() or not (spec_dir / "scores.json").exists():
                continue
            try:
                result = generate_outputs_for_run(
                    source="",
                    skill=skill_root.name,
                    specs_dir=spec_dir,
                    exec_dir=exec_dir,
                    samples_dir=sample_dir,
                    skill_dir=(args.skill_dir if args.skill_dir else Path(skill_root.name)),
                )
                print(f"✅ 已刷新 {skill_root.name}: {result['non_skill_failure_state']}")
                processed += 1
            except Exception as exc:
                print(f"❌ 失败 {skill_root.name}: {exc}")
                errors += 1
        print(json.dumps({"已处理": processed, "错误数": errors}, ensure_ascii=False))
        return 1 if errors else 0

    if args.sample_dir and args.exec_dir and args.spec_dir and args.skill_dir:
        result = generate_outputs_for_run(
            source=args.source or "",
            skill=args.skill_name or args.skill_dir.resolve().name,
            specs_dir=args.spec_dir,
            exec_dir=args.exec_dir,
            samples_dir=args.sample_dir,
            skill_dir=args.skill_dir,
        )
    elif args.skill_dir:
        skill_name = args.skill_name or args.skill_dir.resolve().name
        run_root = args.results_root / skill_name
        result = generate_outputs_for_run(
            source=args.source or "",
            skill=skill_name,
            specs_dir=run_root / "spec",
            exec_dir=run_root / "exec",
            samples_dir=run_root / "sample",
            skill_dir=args.skill_dir,
        )
    elif args.source and args.skill and args.specs_root and args.exec_root and args.samples_root and args.skills_root:
        result = generate_outputs_for_skill(
            source=args.source,
            skill=args.skill,
            specs_root=args.specs_root,
            exec_root=args.exec_root,
            samples_root=args.samples_root,
            skills_root=args.skills_root,
        )
    else:
        parser.error("Provide either --skill-dir, or all of --sample-dir/--exec-dir/--spec-dir/--skill-dir, or legacy --source/--skill with legacy roots.")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
