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
# 报告节标注（阶段 4 两份报告模板用）：<!-- section: <标识> role: <scoring|problem> [optional: <true|false>] -->
SECTION_RE = re.compile(
    r"<!--\s*section:\s*(?P<name>[\w]+)\s+role:\s*(?P<role>scoring|problem)"
    r"(?:\s+optional:\s*(?P<optional>true|false))?\s*-->",
    re.IGNORECASE,
)

VALID_TYPES = {"objective", "subjective"}


def extract_sections(template: Path) -> list[dict[str, str]]:
    """派生报告节的职能标注（供阶段 4 职能红线门禁使用）。

    返回 [{"name": <节标识>, "role": "scoring"|"problem", "optional": bool}]。
    一份报告的 role 应**唯一**——出现异职能节即属职能混淆。
    """
    text = _strip_top_comment_block(template.read_text(encoding="utf-8"))
    out: list[dict[str, str]] = []
    for m in SECTION_RE.finditer(text):
        out.append({
            "name": m.group("name"),
            "role": m.group("role").lower(),
            "optional": (m.group("optional") or "false").lower() == "true",
        })
    return out


def _strip_top_comment_block(text: str) -> str:
    """剥离首个顶部 HTML 注释块（模板元信息 / 示例区）。

    实证：模板顶部注释块内若含合法形态的示例标注，`COLUMNS_RE.search`（取首个匹配）
    会先命中示例，导致**正文的正式 columns 声明改了不生效**（静默失效，无报错）。
    故扫描 schema 前先剥离该块，使正文声明成为唯一生效点。
    """
    # `-->` 必须**独占行尾**才算块尾：否则块内若含内嵌注释示例（如 `<!-- section: … -->`），
    # 非贪婪匹配会在内嵌的 `-->` 处提前终止，导致注释块剥离不完整——
    # 实证：阶段 4 模板顶部注释块含内嵌示例，剥离后残留注释正文，污染后续扫描。
    return re.sub(r"^<!--.*?-->[ \t]*$", "", text, count=1,
                  flags=re.DOTALL | re.MULTILINE)


def extract_schema(template: Path) -> dict[str, Any]:
    """扫描模版文本，派生 schema。"""
    text = _strip_top_comment_block(template.read_text(encoding="utf-8"))

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

    # 2) 逐行扫描标注，同时跟踪「最近上级标题」作为规则锚点（rule_anchor）。
    #    背景：模板用英文 ID 定义槽位、规则文档用中文小节名定义检查项，二者**无绑定**，
    #    对应关系只存在于 LLM 理解中，改任一侧都不会报错（静默错位）。
    #    此处从模板自身的小节标题自动派生锚点——零标注维护，且可供门禁与规则文档比对。
    heading_re = re.compile(r"^#{2,6}\s+(.*\S)\s*$")
    section = ""
    for line in text.split("\n"):
        mh = heading_re.match(line.strip())
        if mh:
            title = mh.group(1).strip()
            # 「严重（…）」「警告（…）」是汇总节下的级别小标题，不是规则小节——
            # 不作锚点，沿用其上级「关键问题汇总」，否则汇总类槽位锚点会错位。
            if not re.match(r"^(严重|警告|提醒)（", title):
                section = title
            continue
        dm = DIM_RE.search(line)
        if dm:
            name = dm.group("name").strip()
            dtype = dm.group("type").strip().lower()
            if name not in seen:
                seen.add(name)
                dims.append({"name": name, "type": dtype,
                             "kind": "table", "rule_anchor": section})
            continue
        fm = FIELD_RE.search(line)
        if fm:
            name = fm.group("name").strip()
            dtype = fm.group("type").strip().lower()
            if name not in seen:
                seen.add(name)
                dims.append({"name": name, "type": dtype,
                             "kind": "text", "rule_anchor": section})

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
