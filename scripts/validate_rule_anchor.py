#!/usr/bin/env python3
"""校验报告模板的「槽位 → 规则锚点」绑定（R4 门禁）。

背景
----
模板以**英文 ID** 定义数据槽位（`frontmatter_quality`、`eco_portability` …），
规则文档以**中文小节名**定义检查项（`#### Frontmatter 质量`、`#### 可移植性…`）。
二者长期**无机器可校验的绑定**，对应关系只存在于 LLM 的理解中——
改任一侧都不会报错，只会静默错位（实证：模板「技能摘要」与规则文档「技能概要」
各自漂移而长期未被发现）。

`schema_from_template` 已能从模板小节标题**自动派生** `rule_anchor`（零标注维护）；
本脚本负责校验该锚点在规则文档中确实存在，未命中即报错。

用法
----
    python3 validate_rule_anchor.py --template assets/report.template.md \\
        --rule-doc references/stage0_preflight.md \\
        --rule-doc references/dependency_availability.md

退出码：全部命中 0；存在未命中 1。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from schema_from_template import extract_schema


def check(template: Path, rule_docs: list[Path]) -> tuple[list[str], int]:
    """返回 (未命中描述列表, 校验通过的槽位数)。"""
    schema = extract_schema(template)
    texts = [p.read_text(encoding="utf-8") for p in rule_docs if p.is_file()]

    missing: list[str] = []
    passed = 0
    for d in schema["dims"]:
        anchor = d.get("rule_anchor") or ""
        if anchor and any(anchor in t for t in texts):
            passed += 1
        else:
            missing.append(f"{d['name']} → 锚点 {anchor!r} 未在任何规则文档中命中")
    return missing, passed


def main() -> None:
    ap = argparse.ArgumentParser(description="校验模板槽位的规则锚点绑定（防静默错位）")
    ap.add_argument("--template", required=True, help="报告模板路径")
    ap.add_argument("--rule-doc", action="append", default=[],
                    help="规则文档路径，可重复传入多个")
    args = ap.parse_args()

    template = Path(args.template)
    rule_docs = [Path(p) for p in args.rule_doc]
    if not rule_docs:
        raise SystemExit("[validate-rule-anchor] 至少须提供一个 --rule-doc")

    missing, passed = check(template, rule_docs)
    total = passed + len(missing)
    print(f"规则锚点校验：{passed}/{total} 命中，未命中 {len(missing)}")
    for m in missing:
        print(f"  ✗ {m}")
    if missing:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
