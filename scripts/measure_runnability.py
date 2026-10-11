#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""measure_runnability.py — 可运行性实测（阶段一 #1 的度量工具）。

定位：回答"被测技能在评测态**是否真的跑起来了**"，而不是"探测是否生成了"。

为什么必须有这一层：静态扫描与探测生成都能在无任何真实执行的情况下产出结果，
若"根本没跑到"却被当作"跑过且安全"，就是最严重的虚假通过。可运行性是运行时观测
项目的**收益前提**——跑不起来的技能，再多的观测手段也观测不到任何东西。

判定规则（与 T-07 同源，不得另写一份）：
  * 单次调用**生效** = code > 0 且 code ∉ {404, 405} 且 code < 500 且（响应体非空 或 code ∈ {401, 403, 429}）
    - 401 / 403 / 429 是**有效证据**（已进入鉴权 / 限流逻辑），绝不能当作未生效；
    - 404 / 405 / 5xx / 连接失败 说明请求**未进入被测逻辑**，此后的"未泄露 / 未执行"都不成立。
  * 探测级 runnable = 该探测的多次调用中**至少一次生效**
  * 技能级 runnable = 该技能**至少一个探测生效**（否则 `runtime_unavailable`）

输入：`--results-root` 下所有 `verification.json`（兼容缺 `probe_effective` 字段的老产物，
按 `outbound_calls[].http_code` / `bytes` 复算）。
输出：JSON（逐技能明细 + 汇总比例）；退出码 0 = 成功，1 = 参数 / IO 错误。
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

# T-07 同源常量：唯一权威定义在 exec_security_evidence.py，此处引用同一组取值，
# 禁止在本文件改数字——改了就等于造出第二份口径。
NOT_EFFECTIVE_CODES = (404, 405)
REJECT_BUT_EFFECTIVE_CODES = (401, 403, 429)


def _call_effective(code: object, nbytes: object) -> bool:
    """单次调用是否真正进入被测逻辑（T-07 规则）。"""
    if not isinstance(code, int) or code <= 0:
        return False  # 连接失败 / 无响应
    if code in NOT_EFFECTIVE_CODES or code >= 500:
        return False
    if isinstance(nbytes, int) and nbytes > 0:
        return True
    return code in REJECT_BUT_EFFECTIVE_CODES


def probe_runnable(verification: dict) -> bool:
    """探测级可运行：优先取产物自带的 probe_effective，缺失则按 T-07 复算。"""
    pe = verification.get("probe_effective")
    if isinstance(pe, bool):
        return pe
    calls = verification.get("outbound_calls") or []
    if not isinstance(calls, list):
        return False
    return any(_call_effective(c.get("http_code"), c.get("bytes")) for c in calls
               if isinstance(c, dict))


def _skill_key(root: Path, path: Path) -> str:
    """结果目录约定：`<root>/<运行标识>/<技能名>/...` → 取前两级作为技能单元。"""
    rel = path.relative_to(root)
    return "/".join(rel.parts[:2]) if len(rel.parts) >= 2 else rel.parts[0]


def measure(root: Path) -> dict:
    files = sorted(root.rglob("verification.json"))
    by_skill: dict[str, dict] = {}
    for f in files:
        try:
            v = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(v, dict):
            continue
        key = _skill_key(root, f)
        slot = by_skill.setdefault(key, {"skill": key, "probes": 0, "effective_probes": 0})
        slot["probes"] += 1
        if probe_runnable(v):
            slot["effective_probes"] += 1

    skills = []
    for key in sorted(by_skill):
        s = by_skill[key]
        s["status"] = "runnable" if s["effective_probes"] > 0 else "runtime_unavailable"
        s["effective_ratio"] = round(s["effective_probes"] / s["probes"], 4) if s["probes"] else 0.0
        skills.append(s)

    n_skill = len(skills)
    n_run = sum(1 for s in skills if s["status"] == "runnable")
    n_probe = sum(s["probes"] for s in skills)
    n_eff = sum(s["effective_probes"] for s in skills)
    return {
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "results_root": str(root),
        "rule": "T-07 同源（404/405/5xx/连接失败 = 未生效；401/403/429 = 有效证据）",
        "skills": skills,
        "summary": {
            "skills": n_skill,
            "runnable_skills": n_run,
            "skill_runnable_ratio": round(n_run / n_skill, 4) if n_skill else None,
            "probes": n_probe,
            "effective_probes": n_eff,
            "probe_effective_ratio": round(n_eff / n_probe, 4) if n_probe else None,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="可运行性实测（阶段一 #1）")
    ap.add_argument("--results-root", required=True, help="评测结果根目录（含多级运行目录）")
    ap.add_argument("--output", default=None, help="输出 JSON 路径（缺省 stdout）")
    args = ap.parse_args()

    root = Path(args.results_root).expanduser().resolve()
    if not root.is_dir():
        print(f"❌ 结果根目录不存在: {root}", file=sys.stderr)
        return 1

    result = measure(root)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
        s = result["summary"]
        print(f"✅ 可运行性实测完成：技能 {s['runnable_skills']}/{s['skills']}"
              f"（{s['skill_runnable_ratio']}），探测 {s['effective_probes']}/{s['probes']}"
              f"（{s['probe_effective_ratio']}）→ {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
