#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_stage0_dod.py — 阶段 0 交付标准（DoD）检查：主观维度是否已裁定。

为什么需要它（R13）：
    阶段 0 的 15 个主观槽位（内容正确性、生态适配、文法、功能表…）依法纪律
    **只能由执行评测的 AI 语义裁定**，脚本不得代填。但一键流水线在跑完脚本后
    **立即合并+渲染**，于是「AI 还没裁定」的报告就被当成成品产出：缺失项一律
    渲染为「无」（现为「未检查」），读者无法分辨「查过没问题」与「根本没判」。

    实证：table_column_relations v4 的 28 个槽位中 15 个为空，报告却照样生成、
    照样上报「✅ 开始阶段测评完成」并自动接续阶段 1–4。

本检查器的作用：把「主观维度已裁定」变成**可机器判定的 DoD 条目**，未满足时
以非 0 退出码阻断流水线，使其不得宣告阶段完成、不得进入下一阶段
（对齐 SKILL.md 既有纪律：前一阶段 DoD 满足才进下一阶段 / DoD 验证后再发完成播报）。

用法：
    python3 scripts/check_stage0_dod.py --data <report_data.json> [--template <report.template.md>]
退出码：
    0 = 通过（无未裁定主观槽位）
    1 = 未通过（存在未裁定主观槽位）
    2 = 参数或数据错误
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

# 汇总槽位不计入 DoD：它们由客观 rows 派生，空值属正常「无」
SUMMARY_FIELDS = frozenset({
    "objective_critical", "subjective_critical",
    "objective_warning", "subjective_warning",
})


def _slot_origin(template_path: Path | None) -> Dict[str, str]:
    """从模板的 field/dim 标注派生每个槽位的归属（objective / subjective）。"""
    origin: Dict[str, str] = {}
    if not template_path or not template_path.is_file():
        return origin
    import re
    text = template_path.read_text(encoding="utf-8", errors="replace")
    for m in re.finditer(
        r"<!--\s*(?:field|dim):\s*([a-z_]+)\s+type:\s*(objective|subjective)\s*-->", text
    ):
        origin[m.group(1)] = m.group(2)
    return origin


# R37：占位字面值——填了等于没填。
# 实证（v5）：AI 把 modalities 填成 `{"text": "text"}`，把字段名当成了值；
# 该槽位 `skipped=false` 且 text 非空，任何"是否为空"的检查都会放行，
# 于是报告里出现「多模态能力：text」这种荒诞输出。
# 故显式列出占位值，命中即视为未裁定。
PLACEHOLDER_TEXTS = frozenset({
    "text", "待填", "待 AI", "待裁定", "TODO", "TBD", "无内容", "N/A", "n/a",
})


def _is_unadjudicated(entry: Any) -> bool:
    """判定一个槽位是否「未产出结论」。

    判定口径（按优先级）：
      1. `skipped` 为真 → 未裁定；
      2. `text` 为占位字面值（R37）→ 填了等于没填，视为未裁定；
      3. **其余一律视为已裁定**。

    第 3 条的依据：`skipped` 由脚本置为 True，执行者裁定后必须显式改为 False——
    因此 **False 本身就是「我已裁定」的声明**；此时 `rows` 为空表示结论是「无问题」。

    ⚠ 修复实证（v7）：AI 把 5 个槽位填为 `{"rows": [], "skipped": false}`（意为
    「已检查、无问题」），旧逻辑因 text/rows 皆空而**误判为未裁定** →
    DoD 门禁阻断 → 阶段 1–4 全部未执行 → 整轮评测只产出阶段 0 报告，
    spec/ 为空、benchmark_manifest 未生成。这是把「无问题」当成「没做」的语义倒置。
    """
    _placeholders = {p.lower() for p in PLACEHOLDER_TEXTS}
    if not isinstance(entry, dict):
        s = entry.strip() if isinstance(entry, str) else ""
        return (not s) or (s.lower() in _placeholders)
    if entry.get("skipped"):
        return True
    txt = str(entry.get("text") or "").strip()
    return bool(txt) and txt.lower() in _placeholders


# ---- 功能表专项约束（视角 + 类别）----
# 实证（v8/v9/v10）：同一技能三轮归纳出三份不同的功能表，其中 v9/v10 写成了
# 「输入参数 / 输出格式 / 依赖脚本 / 支持数据库类型」这类**技能属性**，
# 读者看完不知道能用它做什么。
# 这里只约束**形式与语义类别**，不约束「这个技能有哪些功能」，故不定制：
#   1) 主语必须是客户/用户/使用者：把视角钉在「使用者能做成什么」
#   2) 禁止属性类与实现机制类表述
# 注：主语是「引导造句」的手段，保留在成稿中作为视角锚点，便于后续映射与复核。
FT_SUBJECT_RE = re.compile(
    r"^\s*[-*]\s*(客户|用户|你|使用者)\s*(可以|能够|能|可通过|通过|借助|使用)?"
)
FT_FORBIDDEN_PREFIXES = (
    "输入参数", "输出格式", "输出内容", "输出", "依赖脚本", "依赖", "适用范围",
    "支持数据库类型", "支持", "交互方式", "实现机制", "实现", "内部",
    "模块", "架构", "技术栈", "配置", "环境", "流程",
)


def validate_function_table(entry: Any) -> List[str]:
    """校验功能表：列表形式 + 客户主语 + 非属性/实现类表述。"""
    issues: List[str] = []
    if not isinstance(entry, dict):
        return issues
    text = str(entry.get("text") or "").strip()
    if not text:
        return issues  # 空值由「未裁定」判定处理，此处不重复报
    # 字面换行归一化：AI 写回 JSON 时可能把换行写成**字面的** "\n"（JSON 中为 \\n），
    # 解析后是反斜杠+n 两个字符而非换行 → 整份功能表被当成**一条**，
    # 逐条校验随之失效（实证：v10 功能表仅被识别出 1 条）。与渲染层处理保持一致。
    if "\\n" in text:
        text = text.replace("\\n", "\n")
    items = [ln.strip() for ln in text.splitlines() if ln.strip().startswith(("-", "*"))]
    if not items:
        return ["功能表不是列表形式（须每条以 `-` 开头，逐条列出客户可完成的事）"]
    for i, it in enumerate(items, 1):
        body = re.sub(r"^\s*[-*]\s*", "", it).strip()
        if not FT_SUBJECT_RE.match(it):
            issues.append(
                f"功能表第 {i} 条未以客户/用户为主语（视角不明，可能是技能内部流程）："
                f"「{body[:40]}」"
            )
        for w in FT_FORBIDDEN_PREFIXES:
            if body.startswith(w):
                issues.append(
                    f"功能表第 {i} 条是属性/实现描述，不是服务场景（须以客户为主语造句）："
                    f"「{body[:40]}」"
                )
                break
    return issues


# F6 依据标注后缀：`（依据：SKILL.md:56-86）` / `(依据：description)` 等
_EVIDENCE_SUFFIX_RE = re.compile(r"[（(]\s*依据\s*[:：].*?[)）]\s*$")


def _strip_evidence(s: str) -> str:
    """剥离条目末尾的依据标注，返回场景正文。

    F6 要求功能表每条带「（依据：…）」后，若 task_map 键须与**含依据的全文**逐字一致，
    键会变得冗长且脆弱（依据行号一改，键就失配）。故匹配前两侧都剥离依据后缀。
    """
    return _EVIDENCE_SUFFIX_RE.sub("", s or "").strip()


def validate_task_map(entry: Any) -> List[str]:
    """校验 `task_map`：服务场景 → 功能任务 ID 的映射必须存在且覆盖每条场景。

    实证（v9/v10）：`task_map` 连续两轮为 None，导致基准报告 §4 渲染成
    「功能能力总览」与「功能任务执行验证」两张互不相干的表——读者无法把
    「这个技能能做什么」和「做得成不成」对应起来。
    `generate_outputs.py` 本身支持 task_map（填了就渲染整合表），
    但两轮都没填，说明「靠提示词要求」不可靠，故在此强制。
    """
    issues: List[str] = []
    if not isinstance(entry, dict):
        return issues
    text = str(entry.get("text") or "").strip()
    if not text:
        return issues
    if "\\n" in text:
        text = text.replace("\\n", "\n")
    items = [ln.strip() for ln in text.splitlines() if ln.strip().startswith(("-", "*"))]
    if not items:
        return issues
    tm = entry.get("task_map")
    if not isinstance(tm, dict) or not tm:
        return [
            "function_table 缺少 `task_map`（服务场景 → 功能任务 ID 的映射）；"
            "缺失会让基准报告 §4 退化成「总览 + 验证」两张割裂的表，读者无法对应"
        ]
    # 两侧都剥离依据后缀（v13 实证：agent 起初只写场景正文，被判未覆盖；
    # 被迫把「（依据：SKILL.md:56-86）」也写进键才通过——既冗长又易失配）。
    covered = {_strip_evidence(str(k).strip()) for k in tm}
    for i, it in enumerate(items, 1):
        body = _strip_evidence(re.sub(r"^\s*[-*]\s*", "", it).strip())
        if body and body not in covered:
            issues.append(f"task_map 未覆盖第 {i} 条服务场景：「{body[:40]}」")
    return issues


def main() -> int:
    ap = argparse.ArgumentParser(description="阶段 0 DoD 检查：主观维度是否已裁定")
    ap.add_argument("--data", required=True, help="quality/results/report_data.json")
    ap.add_argument("--template", default=None, help="assets/report.template.md")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = ap.parse_args()

    data_path = Path(args.data)
    if not data_path.is_file():
        print(f"[check_stage0_dod] ❌ 数据文件不存在: {data_path}", file=sys.stderr)
        return 2
    try:
        data = json.loads(data_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"[check_stage0_dod] ❌ 数据解析失败: {e}", file=sys.stderr)
        return 2

    origin = _slot_origin(Path(args.template) if args.template else None)
    unadjudicated: List[str] = []
    for name, entry in data.items():
        if name in SUMMARY_FIELDS:
            continue
        # 未拿到模板时无法判断归属，此时退化为「全部检查」，宁严勿松
        if origin and origin.get(name) != "subjective":
            continue
        if _is_unadjudicated(entry):
            unadjudicated.append(name)

    # 功能表质量约束：即便「已裁定」，内容不合规同样阻断。
    # 实证：v9/v10 的 13 个槽位全部裁定通过，但功能表写成技能属性，报告仍不可用——
    # 只判「填没填」拦不住「填得对不对」。
    ft_issues = validate_function_table(data.get("function_table"))
    tm_issues = validate_task_map(data.get("function_table"))

    result = {
        "passed": not unadjudicated and not ft_issues and not tm_issues,
        "unadjudicated_count": len(unadjudicated),
        "unadjudicated_fields": sorted(unadjudicated),
        "function_table_issues": ft_issues,
        "task_map_issues": tm_issues,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["passed"] else 1

    if result["passed"]:
        print("[check_stage0_dod] ✅ 通过：主观维度已全部裁定，功能表视角与类别合规")
        return 0

    if ft_issues:
        print("[check_stage0_dod] ❌ 功能表不符合服务场景口径：", file=sys.stderr)
        for it in ft_issues:
            print(f"      - {it}", file=sys.stderr)
        print(
            "  → 功能表须逐条以「客户/用户」为主语造句，写清使用者能做成什么。\n"
            "  → 不得写成输入参数、输出格式、依赖脚本、适用范围等技能属性或实现机制。\n"
            "  → 主语是引导造句的手段；成稿保留主语作为视角锚点，仅做文法精简，不改语义。",
            file=sys.stderr,
        )

    if tm_issues:
        print("[check_stage0_dod] ❌ task_map 缺失或不完整：", file=sys.stderr)
        for it in tm_issues:
            print(f"      - {it}", file=sys.stderr)
        print(
            "  → 须为每条服务场景指定对应的功能任务 ID（如 FT01），形如：\n"
            "     \"task_map\": {\"客户可以查询可用的数据库与库名组合\": \"FT01\"}\n"
            "  → 填了它，基准报告 §4 才会渲染成整合表（场景与验证结果逐条对应）。",
            file=sys.stderr,
        )

    if unadjudicated:
        print(
            f"[check_stage0_dod] ❌ 阶段 0 DoD 未满足："
            f"{len(unadjudicated)} 个主观槽位未裁定 → "
            f"{', '.join(sorted(unadjudicated))}",
            file=sys.stderr,
        )
        print(
            "  → 这些槽位依法纪律须由**执行评测的 AI** 语义裁定（脚本不得代填、不得臆造）。\n"
            "  → 补做方式：依据 quality/results/subjective.json 的 skip_reason 材料填写\n"
            "    对应槽位到 quality/results/subjective.json，然后重跑：\n"
            "       python scripts/merge_report_data.py ... && python scripts/render_report.py ...\n"
            "  → 未完成前：不得宣告阶段完成、不得提示查看成品报告、不得进入下一阶段。",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
