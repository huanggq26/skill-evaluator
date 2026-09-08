#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_function_table.py — 校验功能表是否为「用户服务场景」视角

背景（错误档案 ERR-021 / ERR-018）：功能表由 AI 主观归纳，此前无机制防止
产出物/过程构件混入——benchmark §4 就曾把「质量门禁 JSON / 报告生成 / 评分聚合」
当功能。本脚本提供归纳后的机械校验，与 merge_report_data 的占位提醒（源头）
构成双保险。

三层校验：
  1. 产物黑名单（违规，exit 1）：条目含产出物/过程构件名词，且无用户动作词
  2. 服务视角（警告）：条目缺少用户动作动词，提示人工复核
  3. 同源检查（警告）：功能表整体与 frontmatter description 无任何内容词交集

用法：
  python3 validate_function_table.py --report <quality/xx评测.md> \\
                                     --skill-dir <被测技能目录>

退出码：0 通过或仅有警告 / 1 有违规 / 2 用法错误
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# 词表从 _common 导入（ERR-018 治本：与 extract_functional_tasks 兜底过滤共用同一把尺子，
# 单一权威来源在 _common.py，禁止两处各自内联维护）
try:
    from _common import FUNCTION_TABLE_INTERNAL_KW as _INTERNAL_KW
    from _common import FUNCTION_TABLE_ARTIFACT_NOUNS_RE as _ARTIFACT_NOUNS
    from _common import FUNCTION_TABLE_SERVICE_VERBS_RE as _SERVICE_VERBS
except Exception:  # 守卫常量缺失时不阻断黑名单校验
    _INTERNAL_KW = ()
    _ARTIFACT_NOUNS = None
    _SERVICE_VERBS = None

_CJK_WORD = re.compile(r"[\u4e00-\u9fff]{2,4}")


def _extract_table_rows(report: Path) -> list:
    """提取质量报告中「功能表」的数据行（不含表头与分隔行）。

    逐行解析：从以「功能表」开头的行起，到以「产出物清单」开头的行止，
    收集其间所有表格行。不能用单个正则跨段匹配——功能表标题行自身就含
    「不是产出物清单」字样（实测踩坑），前瞻会在第一行就截断。
    """
    lines = report.read_text(encoding="utf-8", errors="replace").splitlines()
    in_ft = False
    rows: list[str] = []
    for line in lines:
        s = line.strip()
        if not in_ft:
            if s.startswith("功能表"):
                in_ft = True
            continue
        if s.startswith("产出物清单"):
            break
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if not cells or not cells[0]:
            continue
        if set(cells[0]) <= set("-: "):              # 分隔行
            continue
        if cells[0] in ("服务场景", "用户关注的功能"):  # 表头
            continue
        rows.append(" | ".join(cells))
    return rows


def _load_description(skill_dir: Path) -> str:
    sk = skill_dir / "SKILL.md"
    if not sk.is_file():
        return ""
    m = re.search(r"description:\s*[\"']?(.*?)[\"']?\s*\n\s*\w+:",
                  sk.read_text(encoding="utf-8", errors="replace"), re.S)
    return (m.group(1) if m else "").strip()


def main() -> int:
    ap = argparse.ArgumentParser(description="校验功能表是否为用户服务场景视角")
    ap.add_argument("--report", required=True, type=Path, help="质量报告 md 路径")
    ap.add_argument("--skill-dir", required=True, type=Path, help="被测技能目录")
    args = ap.parse_args()
    if not args.report.is_file():
        print(f"[validate_ft] 报告不存在: {args.report}", file=sys.stderr)
        return 2

    rows = _extract_table_rows(args.report)
    if not rows:
        print("[validate_ft] 未找到功能表数据行（仍为占位或未归纳）——跳过校验")
        return 0

    desc = _load_description(args.skill_dir)
    desc_words = set(_CJK_WORD.findall(desc)) if desc else set()

    violations: list[str] = []
    warns: list[str] = []
    table_words: set = set()

    for r in rows:
        has_artifact = bool(_ARTIFACT_NOUNS and _ARTIFACT_NOUNS.search(r))
        has_internal = any(kw and kw in r for kw in _INTERNAL_KW)
        has_service = bool(_SERVICE_VERBS and _SERVICE_VERBS.search(r))
        table_words |= set(_CJK_WORD.findall(r))

        if (has_artifact or has_internal) and not has_service:
            violations.append(f"疑似产出物/过程构件（且无用户动作词）: {r[:90]}")
        elif has_artifact or has_internal:
            warns.append(f"含产物/内部词但同时有用户动作词，请复核: {r[:90]}")
        elif not has_service:
            warns.append(f"缺少用户动作动词，请复核是否为服务场景: {r[:90]}")

    # 同源检查（整体级，避免对同义改写误报）
    if desc_words and not (desc_words & table_words):
        warns.append("功能表与 frontmatter description 无内容词交集，"
                     "疑似偏离权威来源，请对照 description 复核")

    print(f"[validate_ft] 功能表共 {len(rows)} 条")
    if violations:
        print(f"\n❌ 违规 {len(violations)} 条（产出物混入，必须整改）:")
        for v in violations:
            print(f"   - {v}")
    if warns:
        print(f"\n⚠️ 警告 {len(warns)} 条（请人工复核）:")
        for w in warns:
            print(f"   - {w}")
    if not violations and not warns:
        print("✓ 全部通过：条目均为用户服务场景视角，且与 description 同源")

    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
