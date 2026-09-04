#!/usr/bin/env python3
"""阶段 0 主观维度自动回填（启发式 advisory，非裁定）。

问题背景
--------
质量报告分 objective（脚本可判定）与 subjective（需 AI 语义裁定）两类维度。原流程
中 subjective.json 完全依赖 AI 手工填写，未回填时合并层把主观维度全部渲染为「无」，
既给读者造成"主观维度无问题"的误判，也让 AI 每次从零开始复核。

本工具的作用（通用、不绑定特定被测技能 / 本评测器）
------------------------------------------------
按 report.template.md 的 schema 派生出**所有 subjective 维度名**（定义只在一处，
不在本脚本硬编码），对每一个生成一份「复核提示（advisory）」写入 subjective.json：
  - 形状严格符合 merge_report_data.py 的契约：{"rows": [], "skipped": True, "skip_reason": "<提示>"}
  - skip_reason 仅含**可机械化抽取的客观证据 + "需 AI 语义复核"指引**，不以脚本结论
    冒充 AI 裁定，也不与 objective 维度重复记缺陷（避免"双计"）；
  - 渲染层对 skipped 维度写「无」（正确：脚本未确认缺陷），但 AI 复核者读取本文件即可
    拿到具体复核锚点，省去从零扫描。

通用性前提（强制）
-----------------
本脚本不引用任何被测技能名或本评测器自身名；维度名取自模板 schema，
证据取自 extract_stats.json（与被测技能无关），故对任何符合该模板的技能通用。

用法
----
  python auto_subjective.py --stats extract_stats.json \
      --template assets/report.template.md --out subjective.json
  （可选 --probe dependency_probe.json，为依赖维度补充可用性证据）
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from _common import load_json
from schema_from_template import extract_schema
# 复用 0C 的过程服务声明收集器（P9 层次 3 材料）与其章节切分工具。
# 两者都在 scripts/ 下、仅依赖 _common，无循环导入。
from extract_functional_tasks import _extract_service_scenarios, _split_sections


# ── 各 subjective 维度的 advisory 构造（仅客观证据 + 复核指引，不做裁定） ──────────

def _advisory_grammar(s: dict[str, Any]) -> str:
    n_lang = s.get("code_blocks_missing_lang") or 0
    n_dup = len(s.get("duplicate_headings") or [])
    n_anchor = len(s.get("dead_anchors") or [])
    bits = []
    if n_lang:
        bits.append(f"缺语言标签 {n_lang} 处（客观 structure_org 已列）")
    if n_dup:
        bits.append(f"重复同级标题 {n_dup} 处")
    if n_anchor:
        bits.append(f"死锚点 {n_anchor} 处")
    ev = ("；客观线索：" + "、".join(bits)) if bits else ""
    return f"文法/语法流畅度需 AI 语义复核{ev}（客观结构问题已由 structure_org 维度覆盖，勿重复计为缺陷）"


def _advisory_deps(s: dict[str, Any], probe: dict[str, Any], kind: str) -> str:
    # 候选清单由 build_objective_data 的 deps_*_candidates 客观提供；本维度是 AI 裁定是否真实依赖
    cand_field = {
        "deps_tools": "deps_tools_candidates",
        "deps_skills": "deps_skills_candidates",
        "deps_commands": "deps_commands_candidates",
    }[kind]
    # 注：本脚本只读 extract_stats，不读 objective_data；故此处仅提示 AI 去查客观候选字段
    base = f"{kind}：是否真实依赖需 AI 依据客观候选字段（{cand_field}）裁定，工具不自动判定"
    if probe and not probe.get("dependency_skipped"):
        fails = [d for d in (probe.get("dimensions") or []) if d.get("status") == "fail"]
        if fails:
            base += f"；可用性探测有 {len(fails)} 项失败（见 dependency_availability 维度）"
    return base


def _advisory_content(s: dict[str, Any], which: str) -> str:
    name = s.get("name_chars")
    desc = s.get("description_chars")
    body = s.get("body_chars")
    ev = f"字数线索：name {name} / description {desc} / 正文 {body}" if None not in (name, desc, body) else "字数线索：extract_stats 未产出"
    return f"{which}需 AI 语义复核（{ev}）"


def _advisory_eco(s: dict[str, Any], which: str) -> str:
    n_mach = len(s.get("machine_absolute_paths") or [])
    n_she = len(s.get("script_shebang") or [])
    n_crlf = len(s.get("crlf_scripts") or [])
    ev = ""
    if n_mach or n_she or n_crlf:
        ev = f"；可移植性客观线索：机器路径 {n_mach} / 非 env shebang {n_she} / CRLF {n_crlf}（已由 eco_portability 维度覆盖）"
    return f"{which}需 AI 语义复核{ev}"


def _advisory_field(s: dict[str, Any], which: str) -> str:
    body = s.get("body_chars")
    ev = f"正文 {body} 字" if body is not None else "extract_stats 未产出字数"
    return f"{which}需 AI 基于 SKILL.md 归纳（客观线索：{ev}）"


# ── P9：功能表的三层次服务场景材料（供 AI 语义归纳，脚本不做裁定） ──────────────
# 定位：服务名是**语义概念**（技能为用户做什么），必须由 AI 归纳。
# 脚本职责仅为**收集依据材料**并按层次呈现，不做形式提取、不臆造服务名。
# 层次按「权威度递减、覆盖度递增」排列（与用户确认的口径一致）：
#   层次1 = frontmatter description（Agent 加载技能的依据，服务语义最权威）
#   层次2 = When to Use（触发场景补充）
#   层次3 = 过程中插入的服务声明（复用 0C _extract_service_scenarios，避免遗漏）

# 触发语义提示词（用于「服务场景是否明确」的**提醒级**检测，仅提示 AI 判断模糊性，
# 不影响执行、不否决、不评分）
_TRIGGER_HINTS = ("when", "当", "用于", "use", "如果", "若", "场景", "适合", "需要")


def _parse_frontmatter_description(md_text: str) -> str:
    """层次1：解析 frontmatter 的 description 字段。

    description 是 Agent 决定是否加载该技能的依据，必然含「提供什么服务 / 什么时候用」，
    是服务场景语义**最权威**的来源。支持 YAML 多行（折叠 >- / 字面 | / 缩进续行）。
    """
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", md_text, re.S)
    if not m:
        return ""
    fm = m.group(1)
    # 取 description 到下一个顶层 key（行首无空白）或 frontmatter 结束
    m2 = re.search(r"^description\s*:\s*(.*?)(?=^\S|\Z)", fm, re.S | re.M)
    if not m2:
        return ""
    desc = m2.group(1).strip()
    # YAML 折叠/字面量指示符
    if desc in (">-", ">", "|", "|-"):
        desc = ""
    return desc.strip()


def _parse_when_to_use(md_text: str) -> list[str]:
    """层次2：解析 When to Use 章节的列表项（触发场景补充）。"""
    for title, body in _split_sections(md_text):
        if re.search(r"when\s+to\s+use|使用场景|何时使用|使用时机|触发", title, re.I):
            items = []
            for ln in body.splitlines():
                s = ln.strip()
                if s.startswith(("-", "*")):
                    items.append(s.lstrip("-* ").strip())
            if items:
                return items
    return []


def _advisory_function_table(skill_root: Path | None) -> str:
    """功能表维度的 advisory：三层次服务场景材料 + 服务场景明确性提醒。

    只**提供材料与提醒**，不产出服务名（那是 AI 语义裁定的职责）。
    """
    if skill_root is None:
        return ("功能表需 AI 语义归纳服务场景（未提供 --skill-root，无法收集依据材料）；"
                "依据层次：①frontmatter description → ②When to Use → ③过程中的服务声明")

    skill_md = skill_root / "SKILL.md"
    if not skill_md.is_file():
        return "功能表需 AI 语义归纳服务场景（未找到 SKILL.md，无法收集依据材料）"
    try:
        md_text = skill_md.read_text(encoding="utf-8")
    except OSError:
        return "功能表需 AI 语义归纳服务场景（SKILL.md 读取失败）"

    desc = _parse_frontmatter_description(md_text)
    when_items = _parse_when_to_use(md_text)
    # 层次3：复用 0C 的过程服务声明收集器（含其实测踩坑修正，不重复实现）
    proc = _extract_service_scenarios(md_text)

    parts = ["功能表需 AI **语义归纳服务场景**（脚本仅提供材料，不代为裁定）。",
             "依据层次（权威度递减、覆盖度递增，请综合归纳去重）："]
    # 层次1
    if desc:
        d = desc if len(desc) <= 400 else desc[:400] + "…"
        parts.append(f"① **frontmatter description**（最权威，Agent 加载依据）：{d}")
    else:
        parts.append("① frontmatter description：**缺失**（未能收集到加载依据）")
    # 层次2
    if when_items:
        parts.append("② **When to Use**（触发场景补充）：")
        for it in when_items[:8]:
            t = it if len(it) <= 160 else it[:160] + "…"
            parts.append(f"   - {t}")
    else:
        parts.append("② When to Use：**未找到该章节**（触发场景声明缺失）")
    # 层次3
    if proc:
        parts.append("③ **过程中的服务声明**（补充，防遗漏）：")
        for val, trigger, d in proc[:8]:
            t = d if len(d) <= 120 else d[:120] + "…"
            parts.append(f"   - `{trigger}`：{t}")
        parts.append("   （注意：`--mode start` 这类是**触发方式**，不是服务名；"
                     "服务名应归纳为「静态质量预检」这类语义描述）")
    else:
        parts.append("③ 过程中的服务声明：未收集到")

    # ── 提醒级检测：服务场景是否明确（仅提示 AI 判断的模糊性，不影响执行/不否决/不评分）──
    reminders = []
    if not desc:
        reminders.append("description 缺失 → 服务语义首要依据不足")
    elif not any(h in desc.lower() for h in _TRIGGER_HINTS):
        reminders.append("description 未见触发语义（当/用于/when 等）→ 服务触发条件可能模糊")
    if not when_items:
        reminders.append("无 When to Use 章节 → 触发场景未显式声明，服务边界可能模糊")
    if reminders:
        parts.append("**提醒（提醒级，不影响执行与评分，仅提示 AI 判断的模糊性）**："
                     + "；".join(reminders))

    return "\n".join(parts)


def _advisory_summary(s: dict[str, Any], which: str) -> str:
    return f"{which}为 AI 对严重/警告的额外补充，需 AI 复核（客观已聚合 objective_critical/objective_warning）"


_ADVISORS = {
    "grammar": lambda s, p: _advisory_grammar(s),
    "deps_tools": lambda s, p: _advisory_deps(s, p, "deps_tools"),
    "deps_skills": lambda s, p: _advisory_deps(s, p, "deps_skills"),
    "deps_commands": lambda s, p: _advisory_deps(s, p, "deps_commands"),
    "content_correct": lambda s, p: _advisory_content(s, "内容正确性"),
    "content_complete": lambda s, p: _advisory_content(s, "内容完整性"),
    "content_scope_alignment": lambda s, p: _advisory_content(s, "评测目标与技能范围对齐"),
    "content_redundant": lambda s, p: _advisory_content(s, "内容冗余"),
    "content_ambiguous": lambda s, p: _advisory_content(s, "内容不明确"),
    "eco_placement": lambda s, p: _advisory_eco(s, "分类与关联"),
    "eco_identity": lambda s, p: _advisory_eco(s, "身份与触发"),
    "modalities": lambda s, p: _advisory_field(s, "多模态能力"),
    "function_table": lambda s, p: _advisory_field(s, "功能表"),
    "subjective_critical": lambda s, p: _advisory_summary(s, "严重补充"),
    "subjective_warning": lambda s, p: _advisory_summary(s, "警告补充"),
}


def build(stats: dict[str, Any], probe: dict[str, Any], template: Path,
          skill_root: Path | None = None) -> dict[str, Any]:
    schema = extract_schema(template)
    subjective_names = [d["name"] for d in schema["dims"] if d["type"] == "subjective"]
    out: dict[str, Any] = {}
    for name in subjective_names:
        # 功能表改用三层次材料 advisory（需读被测技能 SKILL.md，故单独构造）
        if name == "function_table" and skill_root is not None:
            out[name] = {
                "rows": [],
                "skipped": True,
                "skip_reason": _advisory_function_table(skill_root),
            }
            continue
        advisor = _ADVISORS.get(name, lambda s, p: f"{name} 需 AI 语义复核（无可机械化判据）")
        out[name] = {
            "rows": [],
            "skipped": True,
            "skip_reason": advisor(stats, probe),
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="阶段 0 主观维度启发式回填（advisory，非裁定）")
    ap.add_argument("--stats", required=True, help="extract_stats.json 路径")
    ap.add_argument("--template", required=True, help="assets/report.template.md 路径")
    ap.add_argument("--probe", default="", help="可选 dependency_probe.json 路径")
    ap.add_argument("--skill-root", default="",
                    help="被测技能根目录；用于为功能表收集三层次服务场景材料（P9）")
    ap.add_argument("--out", required=True, help="subjective.json 输出路径")
    args = ap.parse_args()

    stats = load_json(Path(args.stats))
    probe = load_json(Path(args.probe)) if args.probe and Path(args.probe).exists() else {}
    skill_root = Path(args.skill_root) if args.skill_root else None
    data = build(stats, probe, Path(args.template), skill_root=skill_root)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"subjective(advisory) -> {args.out}  (主观维度数={len(data)})")
    for name, v in data.items():
        print(f"  {name}: skipped=True | {v['skip_reason'][:48]}...")


if __name__ == "__main__":
    main()
