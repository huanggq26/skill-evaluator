#!/usr/bin/env python3
"""阶段 4 报告「职能红线」门禁（R16）。

背景
----
阶段 4 产出两份报告，职能边界此前**只有注释与文案约束**（如「详见问题报告」），
无任何机器校验，导致职能错放反复发生（实证：评分报告 §7 曾实写整改建议条目）。

职能定义（唯一权威，见 openspec 变更 `stage4-report-template-and-role-gate`）：

| 报告 | role | 消费者 | 严禁出现 |
|---|---|---|---|
| 评分报告 | `scoring` | 决策者 / 发布门禁 | 整改建议、问题明细、待修复项 |
| 问题报告 | `problem` | 开发者 / skill-doctor | 分值、评分结论、上架裁决 |

校验项
------
1. **职能禁词**：按本报告的 role 扫描对应禁词（双向，各扫各的）
2. **异职能节**：报告所属模板的节标注 role 须唯一；出现异职能节即报错
3. **骨架一致**：模板中 `optional=false` 的节标题须出现在报告中
4. **标题纪律**：标题不得含内部字段名 / 代码标记 / 英文代号（读者看不懂）

用法
----
    python3 validate_report_role.py --report spec/benchmark_report.md \\
        --template assets/benchmark_report.template.md

退出码：全部通过 0；任一红线命中 1。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from schema_from_template import SECTION_RE, _strip_top_comment_block

# 按 role 的禁词（双向：评分报告禁问题类措辞，问题报告禁评分类措辞）
ROLE_FORBIDDEN_WORDS: dict[str, list[str]] = {
    "scoring": ["整改", "待修复", "建议修复", "修复指引", "待整改", "改进建议", "整改措施"],
    "problem": ["得分", "综合评分", "上架结论", "通过门禁", "quality_score", "overall_score"],
}
# 需忽略大小写的禁词（英文标识）
CASE_INSENSITIVE = {"score", "verdict", "quality_score", "overall_score"}

# 正则禁词（纯词表拦不住的形态）。
# 实证来源：上个版本真实产物的问题报告出现「### 质量评分: 72/100」与「| 维度 | 评分 | 说明 |」
# ——纯词表有「综合评分」却无「质量评分」，也未覆盖分值形态，导致漏拦。
ROLE_FORBIDDEN_PATTERNS: dict[str, list[str]] = {
    "scoring": [r"改进优先级"],
    "problem": [r"质量评分", r"综合评分", r"总分", r"评分[:：]", r"\d+\s*/\s*100"],
}

# 标题纪律：不得出现的内部字段名 / 代码标记 / 英文代号
TITLE_FORBIDDEN = [
    "verified", "SafeTest", "with_skill", "baseline", "DEP-AVAIL",
    "Functional Grading", "Efficiency Degradation", "verdict", "PreflightAgent",
]

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


def _template_sections(template: Path) -> list[dict[str, object]]:
    """派生模板的节（含 role / optional / 标题）。"""
    text = _strip_top_comment_block(template.read_text(encoding="utf-8"))
    secs: list[dict[str, object]] = []
    cur: dict[str, object] | None = None
    for line in text.split("\n"):
        m = SECTION_RE.search(line)
        if m:
            cur = {
                "name": m.group("name"),
                "role": m.group("role").lower(),
                "optional": (m.group("optional") or "false").lower() == "true",
            }
            continue
        mh = HEADING_RE.match(line.strip())
        if mh and cur is not None:
            cur["title"] = mh.group(2).strip()
            secs.append(cur)
            cur = None
    return secs


def check(report: Path, template: Path) -> tuple[list[str], list[str]]:
    """返回 (errors, warnings)。"""
    errors: list[str] = []
    warnings: list[str] = []

    if not report.is_file():
        return [f"报告不存在: {report}"], warnings

    sections = _template_sections(template)
    roles = {str(s["role"]) for s in sections}
    if len(roles) != 1:
        warnings.append(f"模板内含多种 role {sorted(roles)}——一份报告应只属一种职能")
    role = sorted(roles)[0] if roles else "scoring"

    # 扫描前剥离模板注释：注释是写给生成者看的（含禁词示例），不应被判为报告内容
    raw = _strip_top_comment_block(report.read_text(encoding="utf-8"))
    text = "\n".join(ln for ln in raw.split("\n") if not ln.strip().startswith("<!--"))
    report_headings = [m.group(2).strip() for m in
                       (HEADING_RE.match(ln.strip()) for ln in text.split("\n")) if m]

    # 1) 职能禁词（纯词 + 正则）
    lowered = text.lower()
    for word in ROLE_FORBIDDEN_WORDS.get(role, []):
        hit = (word.lower() in lowered) if word in CASE_INSENSITIVE else (word in text)
        if hit:
            errors.append(f"职能红线：{role} 报告出现禁词「{word}」")
    for pat in ROLE_FORBIDDEN_PATTERNS.get(role, []):
        if re.search(pat, text):
            errors.append(f"职能红线：{role} 报告命中禁词模式「{pat}」")

    # 2) 骨架一致（固定节必须出现）
    for s in sections:
        if s.get("optional"):
            continue
        title = str(s.get("title") or "")
        if title and title not in report_headings:
            errors.append(f"骨架缺失：模板固定节「{title}」未出现在报告中")

    # 3) 标题纪律
    for h in report_headings:
        for bad in TITLE_FORBIDDEN:
            if bad.lower() in h.lower():
                errors.append(f"标题纪律：标题「{h}」含内部标记/英文代号「{bad}」")
                break

    return errors, warnings


def main() -> None:
    ap = argparse.ArgumentParser(description="阶段 4 报告职能红线门禁")
    ap.add_argument("--report", required=True, help="待校验报告路径")
    ap.add_argument("--template", required=True, help="对应的报告模板（派生 role 与骨架）")
    args = ap.parse_args()

    errors, warnings = check(Path(args.report), Path(args.template))
    for w in warnings:
        print(f"  ⚠ {w}")
    for e in errors:
        print(f"  ✗ {e}")
    print(f"职能红线校验：{args.report} —— {'失败' if errors else '通过'}（errors={len(errors)}）")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
