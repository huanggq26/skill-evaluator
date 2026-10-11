#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""benchmark_agreement.py — 标注一致性度量（Cohen's kappa）+ 真值合并。

定位：回答"这份人工真值**可信吗**"。

为什么必须在算召回率之前先算 kappa：召回率的对照基准是人工真值。若两个标注者的一致性
本身就低，说明**标签语义没定义清楚**，此时算出的召回率只是"扫描器对一份随机真值的拟合度"，
毫无意义，且会被高估。因此 kappa 是**准入闸门**，不是可选项。

判定（U1/U6 裁决）：**Cohen's kappa ≥ 0.8 才承认真值可用**；< 0.8 → 修订标注规程后重新标注，
**禁止**通过改标注结果把分歧抹平。

口径：
  * kappa 在**全部 (技能 × 标签) 判定对**上计算；
  * `unsure` 单独统计（**不强行归入 yes / no**），计入 `unsure_pairs` 并从 kappa 的
    yes/no 判定对中剔除，同时披露占比——占比过高说明规程仍不够清晰；
  * 逐标签 kappa 一并输出，用于定位"哪个标签的语义最含糊"。

退出码：0 = 成功（无论 kappa 是否达标）；1 = 参数 / IO 错误；
        2 = kappa < --min-kappa 且指定 --strict（供门禁使用）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TAGS = ["exec_code", "external_dep", "fs_access", "net_egress", "cred_access",
        "state_persist", "user_content", "agent_comms", "prompt_intent",
        "tool_calls", "system_instruction"]
VALUES = ("yes", "no")


def _load(path: Path) -> dict:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(d, dict) or "labels" not in d:
        raise SystemExit(f"❌ 标注文件格式非法（缺 labels）：{path}")
    return d["labels"]


def kappa(pairs: list[tuple[str, str]]) -> float:
    """Cohen's kappa（两个标注者、同一组类别）。"""
    n = len(pairs)
    if n == 0:
        return float("nan")
    po = sum(1 for a, b in pairs if a == b) / n
    pa = {v: sum(1 for a, _ in pairs if a == v) / n for v in VALUES}
    pb = {v: sum(1 for _, b in pairs if b == v) / n for v in VALUES}
    pe = sum(pa[v] * pb[v] for v in VALUES)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def main() -> int:
    ap = argparse.ArgumentParser(description="标注一致性度量（Cohen's kappa）")
    ap.add_argument("--a", required=True, help="标注者 A 的 truth json")
    ap.add_argument("--b", required=True, help="标注者 B 的 truth json")
    ap.add_argument("--min-kappa", type=float, default=0.8, help="一致性准入下限（默认 0.8）")
    ap.add_argument("--strict", action="store_true", help="未达下限时退出码 2（供门禁使用）")
    ap.add_argument("--merged-output", default=None, help="合并真值输出路径（仅合并一致项）")
    args = ap.parse_args()

    la, lb = _load(Path(args.a)), _load(Path(args.b))
    skills = sorted(set(la) & set(lb))
    only_a, only_b = sorted(set(la) - set(lb)), sorted(set(lb) - set(la))
    if not skills:
        print("❌ 两份标注无共同技能，无法计算一致性", file=sys.stderr)
        return 1

    all_pairs: list[tuple[str, str]] = []
    per_tag: dict[str, list[tuple[str, str]]] = {t: [] for t in TAGS}
    disagree: list[dict] = []
    unsure = 0
    total = 0

    for s in skills:
        for t in TAGS:
            va = (la[s] or {}).get(t)
            vb = (lb[s] or {}).get(t)
            if va is None or vb is None:
                continue
            total += 1
            if va == "unsure" or vb == "unsure":
                unsure += 1
                continue
            if va not in VALUES or vb not in VALUES:
                continue
            all_pairs.append((va, vb))
            per_tag[t].append((va, vb))
            if va != vb:
                disagree.append({"skill": s, "tag": t, "a": va, "b": vb})

    k_all = kappa(all_pairs)
    result = {
        "skills_compared": len(skills),
        "only_in_a": only_a,
        "only_in_b": only_b,
        "judgements_total": total,
        "unsure_pairs": unsure,
        "unsure_ratio": round(unsure / total, 4) if total else None,
        "kappa_overall": None if k_all != k_all else round(k_all, 4),
        "kappa_per_tag": {t: (round(kappa(v), 4) if v else None) for t, v in per_tag.items()},
        "disagreements": disagree,
        "min_kappa": args.min_kappa,
        "pass": (k_all == k_all and k_all >= args.min_kappa),
    }

    merged = None
    if args.merged_output:
        merged = {"set": "benchmark", "labels": {}}
        for s in skills:
            merged["labels"][s] = {}
            for t in TAGS:
                va, vb = (la[s] or {}).get(t), (lb[s] or {}).get(t)
                merged["labels"][s][t] = va if va == vb else "UNRESOLVED"
                merged["labels"][s].setdefault("note", f"a={la[s].get('note','')} | b={lb[s].get('note','')}")
        Path(args.merged_output).write_text(
            json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result["merged_output"] = args.merged_output

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["pass"]:
        print(f"⚠ kappa {result['kappa_overall']} < {args.min_kappa}：真值不可用，"
              f"应修订标注规程后重新标注（禁止改标注结果抹平分歧）", file=sys.stderr)
        if args.strict:
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
