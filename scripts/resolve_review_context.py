#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""resolve_review_context.py — 解析并校验每个安全探测的评审知识资产（T-06）。

背景
----
历史资产 `references/SafeTest/dimensions/<视角>/{Audit-Manual.md, Case-Library.md}`
此前**没有任何程序消费路径**：删掉、改名、内容清空，流水线仍退出码 0（悬空资产）。

本脚本的作用
------------
把"评审深化"从口头规程变成**可校验的程序路径**：

  · 按每个探测的 `primary_asi_category` 解析 ASI 规格文件；
  · 按 `supporting_dimensions` 解析各传统视角目录下的审计手册与案例库；
  · 校验文件**存在且非空**（缺失/为空即报错退出，使悬空资产可被自动发现）；
  · 输出 `review_context.json`，供阶段 4 评审直接消费。

用法
----
  python3 scripts/resolve_review_context.py \\
      --manifest <ws>/sample/benchmark_manifest.json \\
      --safetest references/SafeTest \\
      --output <ws>/spec/results/review_context.json

退出码
------
  0 = 全部评审资产齐备；1 = 存在缺失或为空的资产。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import lenses_for_asi  # noqa: E402

_REVIEW_FILES = ("Audit-Manual.md", "Case-Library.md")


def _resolve_asi_doc(safetest: Path, asi: str) -> Path | None:
    """按 ASI 编号解析规格文件（兼容 ASI01 与 ASI01-Agent-Goal-Hijack 两种写法）。"""
    d = safetest / "dimensions" / "owasp-agentic-top10"
    if not d.is_dir():
        return None
    base = str(asi).split("-")[0].strip().upper()
    if not base:
        return None
    for p in sorted(d.glob("*.md")):
        if p.name.upper().startswith(base):
            return p
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, type=Path, help="benchmark_manifest.json")
    ap.add_argument("--safetest", required=True, type=Path, help="references/SafeTest 目录")
    ap.add_argument("--output", required=True, type=Path, help="review_context.json 输出路径")
    args = ap.parse_args()

    if not args.manifest.is_file():
        print(f"[review-context] 缺少 manifest：{args.manifest}", file=sys.stderr)
        return 1

    data = json.loads(args.manifest.read_text(encoding="utf-8"))
    probes = [p for p in (data.get("security_probes") or []) if isinstance(p, dict)]
    dims_root = args.safetest / "dimensions"

    out, errors = [], []
    for p in probes:
        pid = p.get("id")
        asi = p.get("primary_asi_category") or ""
        # supporting_dimensions 为空时回退到反查表，保证评审上下文始终可解析
        lenses = p.get("supporting_dimensions") or lenses_for_asi(asi)

        asi_doc = _resolve_asi_doc(args.safetest, asi)
        if asi_doc is None:
            errors.append(f"[{pid}] 未找到 ASI 规格文件：{asi!r}")
        elif asi_doc.stat().st_size == 0:
            errors.append(f"[{pid}] ASI 规格文件为空（悬空资产）：{asi_doc}")

        assets: list[str] = []
        for lens in lenses:
            for fn in _REVIEW_FILES:
                f = dims_root / lens / fn
                if not f.is_file():
                    errors.append(f"[{pid}] 缺少评审资产：{f}")
                elif f.stat().st_size == 0:
                    errors.append(f"[{pid}] 评审资产为空（悬空资产）：{f}")
                else:
                    assets.append(str(f))

        out.append({
            "probe_id": pid,
            "primary_asi_category": asi,
            "supporting_dimensions": lenses,
            "asi_doc": str(asi_doc) if asi_doc else None,
            "review_assets": assets,
        })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({
        "manifest": str(args.manifest),
        "probe_count": len(out),
        "asset_count": sum(len(o["review_assets"]) for o in out),
        "probes": out,
        "errors": errors,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    total = sum(len(o["review_assets"]) for o in out)
    print(f"[review-context] 探测 {len(out)} 个，评审资产 {total} 份 → {args.output}")
    if errors:
        for e in errors:
            print(f"  ✗ {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
