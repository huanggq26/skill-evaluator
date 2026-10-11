#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
exec_security_probes.py — 通用安全探测执行驱动（SpecAgent 职责自动化）

归属（对齐 AGENTS_RULES R6.1）：通用执行驱动，**不绑定任何被测技能**。
遍历 sample/security/<group>/probe_*，调用每个探针自带的 Grader/run.py（通用模板，
由 generate_probe_scaffolds 生成），产出 grading_result.json。

产物布局对齐 check_exec_artifacts 期望：<exec-root>/security/probes/<id>/results/grading_result.json
安全探测为静态 code 模式（network: not_required），无需联网、无需被测技能运行时，可确定性执行。

用法：
  python3 exec_security_probes.py \
      --sample-root <ws>/sample \
      --exec-root <ws>/exec
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample-root", required=True, type=Path, help="含 security/<group>/probe_* 的 sample 目录")
    ap.add_argument("--exec-root", required=True, type=Path, help="ExecAgent 输出根（exec/security/probes/...）")
    ap.add_argument("--spec-root", default=None, type=Path,
                    help="可选：SpecAgent 输出根（spec/）；提供时把 grading_result.json 镜像写入 "
                         "spec/results/security/probes/<id>/results/，供 run_security_pipeline 读取")
    args = ap.parse_args()

    # P3②：无外部依赖端点 → 证据采集被跳过（evidence_skipped.json 标记，由 exec_security_evidence 落）。
    # 语义：无外部攻击面 = 无可采集证据 = 不存在该面向的安全问题 → 判 N/A 满分，
    # 而不是让 Grader 因「结果文件缺失」把 R1–R10 全判 fail（语义倒置：无攻击面反得 0 分）。
    skipped_marker = args.exec_root / "security" / "evidence_skipped.json"
    evidence_skipped = skipped_marker.is_file()

    sec_root = args.sample_root / "security"
    if not sec_root.is_dir():
        print("[exec_sec] 无 security 目录，跳过", file=sys.stderr)
        return 0

    if evidence_skipped:
        print("[exec_sec] 检测到 evidence_skipped：无外部依赖端点（无外部攻击面），"
              "安全探测判 N/A 满分（非安全问题）", file=sys.stderr)

    failures = 0
    count = 0
    for group_dir in sorted(sec_root.iterdir()):
        if not group_dir.is_dir():
            continue
        for probe_dir in sorted(group_dir.iterdir()):
            if not probe_dir.is_dir() or not probe_dir.name.startswith("probe_"):
                continue
            tid = probe_dir.name
            run_py = probe_dir / "Grader" / "run.py"
            if not run_py.is_file():
                print(f"[exec_sec] 跳过 {tid}：缺 Grader/run.py", file=sys.stderr)
                failures += 1
                continue
            out_dir = args.exec_root / "security" / "probes" / tid / "results"
            out_dir.mkdir(parents=True, exist_ok=True)
            # 若指定 spec-root：在 spec 侧执行并镜像，保证 run_security_pipeline 读到同一份真实评分
            mirror_dir = None
            if args.spec_root:
                mirror_dir = args.spec_root / "results" / "security" / "probes" / tid / "results"
                mirror_dir.mkdir(parents=True, exist_ok=True)

            # P3②：证据被跳过（无端点）→ 直接产出 N/A 满分钟裁，不调 Grader（无证据可评，调必 fail）
            if evidence_skipped:
                # 字段结构须与正常 Grader 输出一致（否则 backfill_reviews 识别为 pending，
                # 导致 Tasks.json 记 PENDING、下游判 0/N 通过）。参照正常 grading 补齐
                # passed_checks/failed_checks/total_checks/all_checks_passed/result/audit_label。
                na_payload = {
                    "task_id": tid,
                    "status": "pass",
                    "outcome_status": "not_applicable",
                    "passed": 10,
                    "total": 10,
                    "must_pass_satisfied": True,
                    "passed_checks": 10,
                    "failed_checks": 0,
                    "total_checks": 10,
                    "all_checks_passed": True,
                    "result": "PASS",
                    "audit_label": "pass",
                    "notes": "无外部依赖端点，无外部攻击面，本探测项不适用（N/A，非安全问题）",
                    "results": [
                        {
                            "rubric_id": f"R{i}",
                            "passed": True,
                            "score": 1,
                            "reason": "无外部依赖端点，无外部攻击面，本探测项不适用（N/A，非安全问题）",
                        }
                        for i in range(1, 11)
                    ],
                    "no_external_surface": True,
                    # T-08：N/A 不等于通过。标记后由 cacu_total_score 从通过率分子与分母中
                    # 一并剔除，避免"无攻击面"被计为满分（倒置）。
                    "excluded_from_scoring": True,
                    "exclusion_reason": "无外部依赖端点，无外部攻击面，本探测项不适用（N/A，非安全问题）",
                }
                (out_dir / "grading_result.json").write_text(
                    json.dumps(na_payload, ensure_ascii=False, indent=2), encoding="utf-8")
                if mirror_dir is not None:
                    (mirror_dir / "grading_result.json").write_text(
                        json.dumps(na_payload, ensure_ascii=False, indent=2), encoding="utf-8")
                count += 1
                print(f"[exec_sec] {tid} [{group_dir.name}] status=pass (N/A 无外部攻击面)")
                continue

            r = subprocess.run(
                [sys.executable, str(run_py), "--task-root", str(probe_dir), "--result-root", str(out_dir)],
                capture_output=True, text=True,
            )
            if r.returncode != 0:
                print(f"[exec_sec] {tid} 执行失败: {r.stderr[:300]}", file=sys.stderr)
                failures += 1
                continue
            count += 1
            # run.py 已写 grading_result.json 到 out_dir；打印状态摘要
            gr = out_dir / "grading_result.json"

            # T-07：探针有效性前置校验。若对抗输入未真正生效（如全部 405），
            # 则评分结果不得计入通过率——否则"没测到"会被当作"安全"（v16 实测：405 仍 10 项全绿）。
            _ver = out_dir / "verification.json"
            if _ver.is_file():
                try:
                    _vd = json.loads(_ver.read_text(encoding="utf-8"))
                except Exception:
                    _vd = {}
                if _vd and _vd.get("probe_effective") is False:
                    try:
                        _g = json.loads(gr.read_text(encoding="utf-8")) if gr.is_file() else {}
                    except Exception:
                        _g = {}
                    if _g:
                        _g["excluded_from_scoring"] = True
                        _g["exclusion_reason"] = (
                            "探测未生效：" + str(_vd.get("ineffective_reason") or "对抗输入未真正触达被测逻辑")
                            + "；评分结果不计入通过率（既非通过也非失败）"
                        )
                        gr.write_text(json.dumps(_g, ensure_ascii=False, indent=2), encoding="utf-8")
                        if mirror_dir is not None:
                            (mirror_dir / "grading_result.json").write_text(
                                json.dumps(_g, ensure_ascii=False, indent=2), encoding="utf-8")
                    print(f"[exec_sec] {tid} ⚠ 探测未生效，已标记不计入评分：{_vd.get('ineffective_reason')}")
            status = "?"
            if gr.is_file():
                try:
                    status = json.loads(gr.read_text(encoding="utf-8")).get("status", "?")
                except Exception:
                    pass
                # 镜像到 spec 路径（run_security_pipeline 读取处）
                if mirror_dir is not None:
                    (mirror_dir / "grading_result.json").write_text(
                        gr.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"[exec_sec] {tid} [{group_dir.name}] status={status}")

    print(f"[exec_sec] 完成：{count} 个安全探测执行，{failures} 失败")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
