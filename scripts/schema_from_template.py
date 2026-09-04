#!/usr/bin/env python3
"""从 report.template.md 抽取报告 schema（方案 C+ 唯一派生源）。

设计原则（定义只在一处）：
  - 报告格式的唯一真相 = assets/report.template.md 里的 HTML 注释标注。
  - 本脚本是「消费者」，扫描模版产出 schema；不另存为权威文件，不硬编码字段。
  - 列结构（columns）、维度名（dim）、字段（field）及其客观/主观归属，
    全部由模版标注单向派生。

标注语法（模版内 HTML 注释，渲染不可见）：
  <!-- columns: 位置,原因,改进建议 -->          全局唯一，所有同构问题表格共用
  <!-- dim: <维度名> type: objective|subjective -->   每表格维度一个
  <!-- field: <字段名> type: objective|subjective --> 非表格文本字段（摘要/功能表/汇总）

输出 JSON 结构：
{
  "columns": ["位置","原因","改进建议"],
  "dims": [
    {"name":"frontmatter_quality","type":"objective","kind":"table"},
    {"name":"summary","type":"subjective","kind":"text"},
    ...
  ]
}

用法：
  python schema_from_template.py --template assets/report.template.md
  python schema_from_template.py --template assets/report.template.md --out schema.json
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from _common import load_json

# ── 标注正则（与模版注释语法严格对应）──
COLUMNS_RE = re.compile(r"<!--\s*columns:\s*([^>]+?)\s*-->", re.IGNORECASE)
DIM_RE = re.compile(
    r"<!--\s*dim:\s*(?P<name>[\w]+)\s+type:\s*(?P<type>objective|subjective)\s*-->",
    re.IGNORECASE,
)
FIELD_RE = re.compile(
    r"<!--\s*field:\s*(?P<name>[\w]+)\s+type:\s*(?P<type>objective|subjective)\s*-->",
    re.IGNORECASE,
)

VALID_TYPES = {"objective", "subjective"}


def extract_schema(template: Path) -> dict[str, Any]:
    """扫描模版文本，派生 schema。"""
    text = template.read_text(encoding="utf-8")

    # 1) 列结构：全局唯一，取第一个声明
    cols: list[str] = []
    m = COLUMNS_RE.search(text)
    if m:
        cols = [c.strip() for c in m.group(1).split(",") if c.strip()]
    if not cols:
        # 兜底默认（不应触发，模版必声明）
        cols = ["位置", "原因", "改进建议"]

    dims: list[dict[str, str]] = []
    seen: set[str] = set()

    # 2) 表格维度 dim:
    for dm in DIM_RE.finditer(text):
        name = dm.group("name").strip()
        dtype = dm.group("type").strip().lower()
        if name in seen:
            continue
        seen.add(name)
        dims.append({"name": name, "type": dtype, "kind": "table"})

    # 3) 文本字段 field:
    for fm in FIELD_RE.finditer(text):
        name = fm.group("name").strip()
        dtype = fm.group("type").strip().lower()
        if name in seen:
            continue
        seen.add(name)
        dims.append({"name": name, "type": dtype, "kind": "text"})

    return {"columns": cols, "dims": dims}


def main() -> None:
    ap = argparse.ArgumentParser(description="从报告模版抽取 schema（方案 C+ 唯一派生源）")
    ap.add_argument("--template", required=True, help="assets/report.template.md 路径")
    ap.add_argument("--out", default="", help="可选，写出 schema JSON 路径")
    args = ap.parse_args()

    schema = extract_schema(Path(args.template))

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(
            json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"schema -> {args.out}")
    else:
        print(json.dumps(schema, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
