#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_report_completeness.py — 报告**内容级**完整性校验（产出物标的的机器化）。

为什么需要它：
    此前验收标准只到「文件是否生成」这一层。执行者据此逐项打勾均为 ✅，
    却无人发现报告**内容**存在缺陷——实证（table_column_relations v5）：
      · 多模态能力单元格渲染为字面值 `text`
      · 文法和语法一行的「原因」列只有裸级别词「警告」，「改进建议」列空白
      · §6 安全评估整节为 `N/A`
      · §4.1 功能能力总览降级为「未完成 AI 归纳」
    这些在『文件清单』视角下全部不可见，因为文件确实存在、字节数非零。
    根因是**标的本身缺失**：未定义「一份合格的报告必须含有什么」。

本校验器把产出物标的固化为机器可判项，覆盖三类报告的**内容**而非文件：
    1. 必要章节存在且非空
    2. 表格单元格不得为空、不得为占位字面值
    3. 主观槽位不得遗留「未检查」
    4. 各报告间的同源项须一致

用法：
    python3 scripts/validate_report_completeness.py --results-dir <结果根>/<技能名>
退出码：
    0 = 内容完整
    1 = 存在内容缺陷（逐条输出到 stderr）
    2 = 参数或产物缺失
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import List, Tuple

# 占位字面值：出现即视为「没填」，而非「结论为无」。
# 注意「—」「-」「N/A」**不在**其中——它们是合法的「不适用」标记
# （如「—（未实测）」表示评测侧未覆盖而非没填），计入会造成大量误报（v5 实测误报 22 项）。
PLACEHOLDER_VALUES = {
    "text", "待填", "待 AI", "TODO", "TBD", "无内容",
}

_TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")
_SEP_ROW_RE = re.compile(r"^\s*\|[\s:|-]+\|\s*$")


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8-sig")
    except OSError:
        return ""


def _table_rows(text: str) -> List[List[str]]:
    """提取 markdown 表格的数据行（跳过表头与分隔行）。"""
    rows: List[List[str]] = []
    in_table = False
    for ln in text.splitlines():
        m = _TABLE_ROW_RE.match(ln)
        if not m:
            in_table = False
            continue
        if _SEP_ROW_RE.match(ln):
            continue
        cells = [c.strip() for c in m.group(1).split("|")]
        if not in_table:  # 第一行是表头
            in_table = True
            continue
        rows.append(cells)
    return rows


def _bad_cells(rows: List[List[str]]) -> List[Tuple[int, int, str]]:
    """返回（行号, 列号, 问题）列表：空单元格或占位字面值。"""
    bad: List[Tuple[int, int, str]] = []
    for i, row in enumerate(rows, start=1):
        for j, cell in enumerate(row, start=1):
            c = cell.strip()
            if not c:
                bad.append((i, j, "空白"))
            elif c in PLACEHOLDER_VALUES:
                bad.append((i, j, f"占位字面值「{c}」"))
    return bad


def check_quality_report(path: Path) -> List[str]:
    issues: List[str] = []
    text = _read(path)
    if not text:
        return ["质量报告缺失或为空"]

    # 1) 主观槽位遗留「未检查」
    n_unchecked = text.count("未检查")
    if n_unchecked:
        issues.append(f"质量报告存在 {n_unchecked} 处「未检查」（主观槽位未裁定）")

    # 1b) 正文里独立成行的占位字面值（表格之外，如「多模态能力：\ntext」）
    #     实证：v5 的 modalities 被填成字面值 text，因不在表格内而逃过表格检查。
    for ph in sorted(PLACEHOLDER_VALUES):
        if re.search(rf"^[ \t]*{re.escape(ph)}[ \t]*$", text, re.M):
            issues.append(f"正文存在独立成行的占位字面值「{ph}」（该槽位未填写真实结论）")

    # 2) 关键问题汇总必须有实质内容
    m = re.search(r"###\s*关键问题汇总(.*?)(?=\n##\s|\Z)", text, re.S)
    if not m:
        issues.append("质量报告缺少「关键问题汇总」章节")
    else:
        seg = m.group(1)
        has_data = any(
            "<font" in ln for ln in seg.splitlines() if ln.strip().startswith("|")
        )
        if not has_data:
            issues.append("「关键问题汇总」无任何问题行（严重/警告节均为空）")

    # 3) 全报告表格单元格质量
    rows = _table_rows(text)
    bad = _bad_cells(rows)
    if bad:
        sample = "；".join(f"第{r}行第{c}列{v}" for r, c, v in bad[:5])
        issues.append(f"质量报告表格存在 {len(bad)} 个空白/占位单元格（例：{sample}）")
    return issues


def check_benchmark_report(path: Path) -> List[str]:
    issues: List[str] = []
    text = _read(path)
    if not text:
        return ["基准报告缺失或为空"]

    # 1) 功能能力总览不得降级
    if "未完成 AI 归纳" in text:
        issues.append("§4.1 功能能力总览降级为「未完成 AI 归纳」（未与质量报告功能表同源）")

    # 2) 安全评估不得整节 N/A
    m = re.search(r"##\s*\d*\.?\s*安全评估(.*?)(?=\n##\s|\Z)", text, re.S)
    if not m:
        issues.append("基准报告缺少「安全评估」章节")
    else:
        seg = m.group(1)
        data_rows = [r for r in _table_rows(seg)]
        if not data_rows or all(all(c in ("N/A", "") for c in r) for r in data_rows):
            issues.append("「安全评估」无实质探测行（整节 N/A）")

    # 3) §4.2 与 §4.3 一致性
    if "技能未能交付该能力" in text and "未实测" in text:
        issues.append("§4.3 出现「技能未能交付该能力」，与 §4.2 的「未实测」表述自相矛盾")

    # 4) 表格单元格质量
    bad = _bad_cells(_table_rows(text))
    if bad:
        sample = "；".join(f"第{r}行第{c}列{v}" for r, c, v in bad[:5])
        issues.append(f"基准报告表格存在 {len(bad)} 个空白/占位单元格（例：{sample}）")
    return issues


def check_problem_report(path: Path) -> List[str]:
    issues: List[str] = []
    text = _read(path)
    if not text:
        return ["问题报告缺失或为空"]
    first = text.splitlines()[0] if text.splitlines() else ""
    if "（Problem Report）" in first or "Problem Report" in first:
        issues.append(f"问题报告标题未统一：「{first}」")
    if not re.match(r"^#\s*\S+[：:]\s*\S+", first):
        issues.append(f"问题报告标题格式不符（应为「# <中文职能名>：<技能名>」）：「{first}」")
    bad = _bad_cells(_table_rows(text))
    if bad:
        sample = "；".join(f"第{r}行第{c}列{v}" for r, c, v in bad[:5])
        issues.append(f"问题报告表格存在 {len(bad)} 个空白/占位单元格（例：{sample}）")
    return issues


def main() -> int:
    ap = argparse.ArgumentParser(description="报告内容级完整性校验（产出物标的）")
    ap.add_argument("--results-dir", required=True, help="<结果根>/<技能名> 目录")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    root = Path(args.results_dir)
    if not root.is_dir():
        print(f"[completeness] ❌ 目录不存在: {root}", file=sys.stderr)
        return 2

    targets = {
        "质量报告": (root / "quality" / "quality_report.md", check_quality_report),
        "基准报告": (root / "spec" / "benchmark_report.md", check_benchmark_report),
        "问题报告": (root / "spec" / "problem_report.md", check_problem_report),
    }
    all_issues: dict[str, List[str]] = {}
    for name, (path, fn) in targets.items():
        if not path.is_file():
            all_issues[name] = [f"文件缺失: {path.name}"]
            continue
        found = fn(path)
        if found:
            all_issues[name] = found

    if args.json:
        print(json.dumps({"passed": not all_issues, "issues": all_issues},
                         ensure_ascii=False, indent=2))
        return 0 if not all_issues else 1

    if not all_issues:
        print("[completeness] ✅ 通过：三份报告内容完整（章节/单元格/同源项均无缺陷）")
        return 0

    print(f"[completeness] ❌ 内容缺陷 {sum(len(v) for v in all_issues.values())} 项：",
          file=sys.stderr)
    for name, items in all_issues.items():
        print(f"  · {name}:", file=sys.stderr)
        for it in items:
            print(f"      - {it}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
