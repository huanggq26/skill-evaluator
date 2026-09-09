#!/usr/bin/env python3
"""校验规格文件的声明块是否含 `自检锚点` 字段。

治理脚本（派生）：存在理由派生于 `project_spec_maintenance.md#开发态自检锚点（防约束未激活）`
的"机械校验（条件项）"条款。该条款被删或被上游脚本接管 → 删除本脚本。

用法（显式入参，无隐式路径）：
    python3 check_spec_anchors.py <规格文件> [<规格文件> ...]

退出码：0 = 全部通过；1 = 存在缺失/错误（阻断）；2 = 用法错误。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

DECL_TITLE = "规格声明"
ANCHOR_FIELD = "自检锚点"
REQUIRED_FIELDS = (
    "编写/维护者",
    "使用者",
    "编写牵引目标",
    "作用",
    "生成物",
    "层级/归属",
    ANCHOR_FIELD,
    "整理日期",
)

# 声明块行：以 "> " 开头的 blockquote 行
QUOTE_LINE = re.compile(r"^\s*>\s?(.*)$")


def parse_decl_block(text: str) -> tuple[bool, list[str]]:
    """抽取首个 `规格声明` 块内的字段名列表。返回 (是否找到声明块, 字段名列表)。"""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if DECL_TITLE in line and QUOTE_LINE.match(line):
            start = i
            break
    if start is None:
        return False, []

    fields: list[str] = []
    for line in lines[start + 1 :]:
        m = QUOTE_LINE.match(line)
        if not m:
            # blockquote 结束（声明块须连续，遇空行/非引用行即止）
            if line.strip() == "" and fields:
                break
            if fields:
                break
            continue
        body = m.group(1).strip()
        fm = re.match(r"^-\s*([^：:]+)\s*[：:]", body)
        if fm:
            fields.append(fm.group(1).strip())
    return True, fields


def check_file(path: Path) -> tuple[list[str], list[str]]:
    """返回 (缺失字段列表, 错误列表)。"""
    errors: list[str] = []
    if not path.is_file():
        return [], [f"文件不存在：{path}"]
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [], [f"读取失败：{path}（{exc}）"]

    found, fields = parse_decl_block(text)
    if not found:
        # 缺声明块 = 未规范化，属规范化欠账（不阻断，须登记）
        return [], [f"缺规格声明块（未规范化，须登记欠账）：{path}"]

    missing = [f for f in REQUIRED_FIELDS if f not in fields]
    return missing, errors


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("用法：check_spec_anchors.py <规格文件> [<规格文件> ...]", file=sys.stderr)
        return 2

    missing_map: dict[Path, list[str]] = {}
    errors: list[str] = []

    for arg in argv[1:]:
        path = Path(arg)
        missing, errs = check_file(path)
        errors.extend(errs)
        if missing:
            missing_map[path] = missing

    if errors:
        print("【规范化欠账 / 错误】")
        for e in errors:
            print(f"  ⚠ {e}")

    if missing_map:
        print(f"\n【阻断】{len(missing_map)} 个文件声明块缺必需字段：")
        for path in sorted(missing_map):
            print(f"  ✗ {path} → 缺：{', '.join(missing_map[path])}")
        return 1

    print(f"✅ 通过：{len(argv) - 1} 个规格文件声明块字段齐全（含 `{ANCHOR_FIELD}`）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
