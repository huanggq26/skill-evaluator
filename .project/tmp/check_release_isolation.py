#!/usr/bin/env python3
"""发布隔离门禁：校验发布区内无开发态残留。

治理脚本（派生）：存在理由派生于 `project_spec_maintenance.md#发布隔离（标签 \u9700打包发布）`
的校验条款。该条款被删或被上游脚本接管 → 删除本脚本。

背景：治理规格第 610 行早已要求「打包后 grep -rE 'AGENTS_RULES|TASKLOG|\\.project' 应为 0」，
但该校验从未落成脚本，实际有 57 处命中未被发现。本脚本把该死规则变成可执行门禁。

判据（按"运行时是否会被读取/执行"分类，非一刀切）：
  - .md（SKILL.md / references/**）：LLM 运行时会读 → 全部行计命中
  - .py / .sh：注释与 docstring 不参与执行 → 排除后，剩余行计命中

用法（显式入参，无隐式路径）：
    python3 check_release_isolation.py [--root <仓库根>]

退出码：0 = 无违规；1 = 有违规（阻断）；2 = 用法/环境错误。
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

# 开发态残留特征（指向治理区、治理入口、上级规格）
DEV_PATTERNS = re.compile(
    r"AGENTS_RULES"
    r"|TASKLOG"
    r"|\.project[/\s]"
    r"|project_spec_maintenance"
    r"|agent_spec_writing_standard"
    r"|\bCODEBUDDY\b"
    r"|opencode\.json"
)

# 发布区（会进发布包）— 治理区 .project/ 与治理入口不在此列
PUBLISH_DIRS = ("references", "scripts", "assets")
PUBLISH_FILES = ("SKILL.md",)

# 排除：本机/缓存噪声
EXCLUDE_SUFFIX = (".pyc",)
EXCLUDE_PARTS = ("__pycache__", ".git")

# 豁免哨兵：标注本行的"开发态特征"是规则描述（列举待跳过对象），非指向治理文件的指针
EXEMPT_MARK = "发布隔离豁免"


def docstring_lines(text: str) -> set[int]:
    """返回文件中所有 docstring 覆盖的行号集合（1-based）。"""
    lines: set[int] = set()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return lines
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
            # ast 行号为 1-based
            lines.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return lines


def scan_code(path: Path) -> list[tuple[int, str]]:
    """扫描代码文件，排除注释行与 docstring 行。"""
    text = path.read_text(encoding="utf-8", errors="replace")
    doc_lines = docstring_lines(text)
    hits: list[tuple[int, str]] = []
    for i, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):          # 行注释：不参与执行
            continue
        if i in doc_lines:                    # docstring：不参与执行
            continue
        if EXEMPT_MARK in line:               # 规则描述行，非指针
            continue
        if DEV_PATTERNS.search(line):
            hits.append((i, line.strip()[:120]))
    return hits


# 发布区文档中对本仓文件的引用（文件不存在即空指针）
REF_PATTERNS = re.compile(r"`?((?:scripts|references|assets)/[A-Za-z0-9_./-]+)`?")


def scan_doc(path: Path, root: Path | None = None) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """扫描文档文件：LLM 运行时会读，全部行计命中。

    返回 (errors, warns)：
      errors = 指向治理区 / 上级规格的开发态指针（**阻断**）
      warns  = 引用了本仓不存在的文件（**仅警告**，不阻断）
    warns 误报率高：格式举例（`scripts/run.py:12`）、反例（`scripts/x.py`）、
    历史来源标注（"来源：原 references/xxx.md"）都会命中，故只提示不阻断。
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    errors: list[tuple[int, str]] = []
    warns: list[tuple[int, str]] = []
    for i, line in enumerate(text.splitlines(), start=1):
        if EXEMPT_MARK in line:               # 规则描述行，非指针
            continue
        if DEV_PATTERNS.search(line):
            errors.append((i, line.strip()[:120]))
            continue
        if root is not None:
            for m in REF_PATTERNS.finditer(line):
                ref = m.group(1).rstrip("`.,;:)")
                if "/" in ref and not (root / ref).exists():
                    warns.append((i, f"疑似引用不存在的文件：{ref}"))
    return errors, warns


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="发布隔离门禁")
    ap.add_argument("--root", default=None, help="仓库根目录（默认：向上查找含 scripts/run_eval_pipeline.sh 的目录）")
    args = ap.parse_args(argv[1:])

    if args.root:
        root = Path(args.root).resolve()
    else:
        root = next(
            (p for p in Path(__file__).resolve().parents
             if (p / "scripts" / "run_eval_pipeline.sh").exists()),
            None,
        )
    if root is None or not root.is_dir():
        print("错误：未能定位仓库根（未找到 scripts/run_eval_pipeline.sh）", file=sys.stderr)
        return 2

    targets: list[Path] = []
    for name in PUBLISH_FILES:
        p = root / name
        if p.is_file():
            targets.append(p)
    for d in PUBLISH_DIRS:
        dd = root / d
        if dd.is_dir():
            targets.extend(sorted(dd.rglob("*")))

    violations: dict[Path, list[tuple[int, str]]] = {}
    warnings: dict[Path, list[tuple[int, str]]] = {}
    for p in targets:
        if not p.is_file():
            continue
        if p.suffix in EXCLUDE_SUFFIX:
            continue
        if any(part in EXCLUDE_PARTS for part in p.parts):
            continue
        if p.suffix in (".py", ".sh"):
            hits = scan_code(p)
            if hits:
                violations[p] = hits
        else:
            errors, warns = scan_doc(p, root)
            if errors:
                violations[p] = errors
            if warns:
                warnings[p] = warns

    scanned = len([t for t in targets if t.is_file()
                   and t.suffix not in EXCLUDE_SUFFIX
                   and not any(part in EXCLUDE_PARTS for part in t.parts)])
    print(f"扫描发布区文件：{scanned} 个（根={root}）")

    if warnings:
        total = sum(len(v) for v in warnings.values())
        print(f"\n【警告·不阻断】{len(warnings)} 个文件疑似引用不存在的文件，共 {total} 处")
        print("（格式举例 / 反例 / 历史来源标注均会命中，误报率高，仅提示人工判断）")
        for path in sorted(warnings):
            print(f"\n  ⚠ {path.relative_to(root)}")
            for lineno, text in warnings[path]:
                print(f"      {lineno}: {text}")

    if violations:
        total = sum(len(v) for v in violations.values())
        print(f"\n【阻断】{len(violations)} 个文件含开发态残留，共 {total} 处：")
        for path in sorted(violations):
            print(f"\n  ✗ {path.relative_to(root)}")
            for lineno, text in violations[path]:
                print(f"      {lineno}: {text}")
        return 1

    print("✅ 通过：发布区无开发态残留（无治理文件指针、无治理区路径）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
