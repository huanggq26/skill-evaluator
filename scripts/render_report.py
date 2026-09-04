#!/usr/bin/env python3
"""按模版 + 合并数据(report_data.json) 回填，产出最终质量评估报告 Markdown。

方案 C+ 落点：模版是唯一格式源，本脚本只做"字段→占位"的机械回填，不承载任何排版逻辑。
回填规则（与 assets/report.template.md 标注严格对应）：
  - <!-- dim: name type: x -->  ：表格维度。取 report_data[name].rows：
        rows 非空 → 渲染表格（表头=模版 columns 声明）；
        rows 空   → 该维度小节下写"无"（不输出空表头）。
        若 report_data[name].skipped=True → 写"无"（可用性跳过）。
  - <!-- field: name type: x -->：文本字段。取 report_data[name].text（主观字段由 AI 提供）；
        为空 → 写"无"。
  - 其余模版文本（标题/说明/模板说明块）原样保留；顶部 HTML 注释标注在输出中剥离（不可见，无害保留亦可，这里剥离保证干净）。

用法：
  python render_report.py --template assets/report.template.md \
      --data report_data.json --out <skill>评测.md
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from _common import load_json
from schema_from_template import extract_schema, COLUMNS_RE, DIM_RE, FIELD_RE

# 严重级别 → font 颜色（与模版约定一致）
SEVERITY_COLOR = {"严重": "red", "警告": "GoldenRod"}  # 提醒无 font 标签


def _severity_of(row: dict[str, str]) -> str:
    """从'原因'列推断级别（严重/警告/提醒），用于字体着色。"""
    reason = row.get("原因", "")
    for lvl in ("严重", "警告"):
        if lvl in reason:
            return lvl
    return ""


def _render_table(rows: list[dict[str, str]], columns: list[str]) -> str:
    head = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = []
    for r in rows:
        cells = []
        for c in columns:
            val = r.get(c, "")
            if c == "原因":
                lvl = _severity_of(r)
                if lvl:
                    color = SEVERITY_COLOR[lvl]
                    val = f'<font color="{color}">{val}</font>'
            cells.append(val)
        body.append("| " + " | ".join(cells) + " |")
    return "\n".join([head, sep, *body])


def _block_value(val: str) -> str:
    """块级内容（表格 / 列表 / 多行文本）回填时**前置一个空行**。

    Markdown 渲染要求：表格、列表等块级元素与其上方的文字之间必须有空行，
    否则整块会被当作同一段落而不渲染成表格（实证：功能表紧接「功能表（…）：」文字行后，
    表格未渲染）。故凡内容以 `|`（表格）、`-`/`*`（列表）、`#`（标题）开头，补前导空行。
    """
    s = str(val or "").strip("\n")
    if not s:
        return "无"
    first = s.lstrip()[0] if s.lstrip() else ""
    if first in ("|", "-", "*", "#"):
        return "\n" + s
    return s


def render(template: Path, data: dict[str, Any], schema: dict[str, Any], skill_name: str = "") -> str:
    text = template.read_text(encoding="utf-8")
    columns = schema["columns"]

    # 0) 清理模板里「紧邻 dim/field 标注行下方」的固定表头示例行（如 function_table 的
    #    | 名称 |...| / | --- |）——AI 填 text 时自带表头，模板固定表头冗余。
    #    **必须在 dim/field 回填之前执行**：否则该无差别正则会误删回填内容自带的表头
    #    （实证：功能表回填的 | 名称 |...| / |---| 被删，表格失去表头而不渲染）。
    #    此处限定「注释行紧邻下方」，只作用于模板固定表头，不伤任何回填内容。
    text = re.sub(r"(<!--\s*(?:dim|field):[^\n]*-->)\n\|[^\n]*\|\n\|[ \-|]*\|\n?", r"\1\n", text)

    # 1) dim 表格维度回填
    def _sub_dim(m: re.Match) -> str:
        name = m.group("name")
        entry = data.get(name, {})
        rows = entry.get("rows", []) if isinstance(entry, dict) else []
        skipped = entry.get("skipped", False) if isinstance(entry, dict) else False
        if skipped or not rows:
            # 功能表等 subjective 维度：report_data 里可能直接给了多行 Markdown 文本
            # （如 P6-A 用阶段0C 功能清单回填的功能表），此时以 text 为准渲染。
            if isinstance(entry, dict):
                txt = str(entry.get("text") or "").strip()
                if txt:
                    return _block_value(txt)
            # 对外依赖等场景：同小节内已有客观候选（非"无"），此时再写"无"会与候选矛盾
            # （呈现为「工具列表 + 无」），故按数据层标记省略该占位。
            if isinstance(entry, dict) and entry.get("suppress_empty"):
                return ""
            return "无"
        return _block_value(_render_table(rows, columns))

    text = DIM_RE.sub(_sub_dim, text)

    # 2) field 文本字段回填
    def _sub_field(m: re.Match) -> str:
        name = m.group("name")
        entry = data.get(name, {})
        if isinstance(entry, dict):
            val = entry.get("text", "")
        else:
            val = entry if isinstance(entry, str) else ""
        return _block_value(val) if val else "无"

    text = FIELD_RE.sub(_sub_field, text)

    # 3) 剥离机器标注注释：顶部 <!-- ... --> 元信息块 + 零散 dim/field/columns 注释行
    #    整段顶部注释块（首个 <!-- 到对应 -->）剥离
    text = re.sub(r"^<!--.*?-->\n", "", text, count=1, flags=re.DOTALL)
    text = COLUMNS_RE.sub("", text)
    text = DIM_RE.sub("", text)
    text = FIELD_RE.sub("", text)
    # 注：模板固定表头的清理已在步骤 0（回填之前）完成，此处不再执行——
    # 若在回填之后再跑无差别表头清理，会误删回填内容自带的表头。

    # 4) 剥离「给填写者的指引块」（模板说明 / 填写总则 / 填写口径 / 输出格式 等）。
    #    这些块是写给 AI/填写者看的**编写指引**，不是报告正文，不应出现在最终交付物中。
    #    统一按「> **<指引类标题>**」开头的连续引用块整段剥离（不逐一列举标题词，防遗漏）。
    _GUIDE_TITLES = ("模板说明", "填写总则", "填写口径", "输出格式", "结构硬规则", "填写说明")
    # 允许：① 前导空白（缩进）；② 加粗标题词后跟补充说明再闭合 **，
    # 如 "> **模板说明（生成报告时删除本段）**：" —— 若要求 `\*\*模板说明\*\*` 连续则会漏匹配。
    text = re.sub(
        r"^\s*> \*\*(?:" + "|".join(_GUIDE_TITLES) + r")[^*]*\*\*[^\n]*\n(?:\s*> .*\n)*",
        "", text, flags=re.M)

    # 5) 替换技能名占位
    if skill_name:
        text = text.replace("<skill-name>", skill_name)

    # 6) 统一换行为 LF 后压缩连续空行（保留单空行）。
    #    先归一化的原因：若模板/数据含 CRLF，行尾带 \r，会使上述依赖 \n 的正则
    #    （尤其指引块剥离的 (?:> .*\n)* 续行匹配）失效，导致指引块残留到最终报告。
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="按模版回填 report_data → 最终报告")
    ap.add_argument("--template", required=True)
    ap.add_argument("--data", required=True, help="合并后的 report_data.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--skill-name", default="", help="可选，替换模版中的 <skill-name> 占位")
    args = ap.parse_args()

    schema = extract_schema(Path(args.template))
    data = load_json(Path(args.data))
    md = render(Path(args.template), data, schema, args.skill_name)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(md, encoding="utf-8")
    print(f"报告 -> {args.out}")


if __name__ == "__main__":
    main()
