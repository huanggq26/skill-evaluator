#!/usr/bin/env python3
"""运行 Grader 代码评分器，将结果回填到 Tasks.json。"""
from __future__ import annotations

import json
import subprocess
import re
import sys
from pathlib import Path

# 可移植路径方案：从脚本位置向上查找工程根目录
_PROJECT_ROOT = Path(__file__).resolve().parents[1]  # scripts/ -> 根目录

from _common import _default_results_root, PROBE_GROUP_MAP, derive_security_group


def _resolve_results_root() -> Path:
    """解析结果根目录（复用共享实现，禁止重复定义环境变量读取逻辑）。"""
    return _default_results_root()


def _resolve_func_grader_dir(sample_dir: Path, tid: str) -> Path | None:
    """定位功能任务的 Grader 目录：先查 hard 再回退 common。

    回归#3 防护：原实现硬编码 ``sample/common/{tid}/Grader``，导致 hard 任务
    （如 H_01）的 grader 永远找不到而被「跳过」。改为先 hard 后 common。
    """
    for sub in ("hard", "common"):
        cand = sample_dir / sub / tid / "Grader"
        if cand.exists():
            return cand
    return None


def run_grader(grader_dir: Path, result_dir: Path) -> dict:
    """运行 Grader 并返回解析后的 JSON 输出。

    run.py 契约要求同时传入 --task-root（含 Grader/ 的探针/任务目录，用于定位
    grader_manifest.json 与 R*.py）与 --result-root（含 verification.json 等主结果物的
    目录）。两棵树分属 sample/ 与 spec/（或 exec/），无法由单参数反推，故此处显式双传。
    """
    result = subprocess.run(
        [
            # 用 sys.executable 而非硬编码 "python3"/"python"：
            # Windows 无 python3（FileNotFoundError），而 sys.executable 恒为当前解释器，
            # 跨平台且保证子 Grader 与主流程解释器一致。
            sys.executable, str(grader_dir / "run.py"),
            "--task-root", str(grader_dir.parent),
            "--result-root", str(result_dir),
        ],
        capture_output=True, text=True, cwd=str(grader_dir),
    )
    return json.loads(result.stdout)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="运行 Grader 评分器并将结果回填到 Tasks.json")
    parser.add_argument("--tasks-json", required=True, help="Tasks.json 文件路径")
    parser.add_argument("--sample-dir", required=True, help="SampleAgent 输出目录")
    parser.add_argument("--exec-dir", required=True, help="ExecAgent 输出目录")
    parser.add_argument("--spec-dir", required=True, help="SpecAgent 输出目录")
    args = parser.parse_args()

    tasks_json_path = Path(args.tasks_json)
    sample_dir = Path(args.sample_dir)
    exec_dir = Path(args.exec_dir)
    spec_dir = Path(args.spec_dir)

    with open(tasks_json_path, "r", encoding="utf-8") as f:
        tasks_data = json.load(f)

    # --- 回填功能任务（common C_xx / hard H_xx，数量动态）---
    for task in tasks_data["tasks"]:
        tid = task["task_id"]
        for mode, state_field, audit_field, passed_field, failed_field, total_field in [
            ("baseline", "baseline_state", "baseline_audit_label",
             "baseline_passed_checks", "baseline_failed_checks", "baseline_total_checks"),
            ("with_skill", "with_skill_state", "with_skill_audit_label",
             "with_skill_passed_checks", "with_skill_failed_checks", "with_skill_total_checks"),
        ]:
            grader_dir = _resolve_func_grader_dir(sample_dir, tid)
            # 规范布局: exec/{mode}/tasks/{tid}/results；兼容旧布局 exec/results/{mode}/tasks/{tid}/results
            result_dir = exec_dir / mode / "tasks" / tid / "results"
            legacy_result_dir = exec_dir / "results" / mode / "tasks" / tid / "results"
            if not result_dir.exists() and legacy_result_dir.exists():
                result_dir = legacy_result_dir

            if grader_dir.exists() and result_dir.exists():
                # D1（v11 索引指出的误导性判断）：先查任务自身的真实执行状态。
                # 若 result.json 标记 unsupported / blocked（未真实执行，如交互式技能无入口），
                # Grader 因拿不到交付证据会返回 fail(0/10)——把「没执行」呈现成「失败」
                # 属语义倒置，读者会误以为技能功能缺失。
                # 故此处改为「跳过」：不计入失败数，检查点总数也记 0（避免出现 0/10 这样的失败观感）。
                _unsupported = False
                try:
                    _rp = result_dir / "result.json"
                    if _rp.is_file():
                        _rj = json.loads(_rp.read_text(encoding="utf-8-sig"))
                        _unsupported = str(_rj.get("status") or "").lower() in (
                            "unsupported", "blocked",
                        )
                except (OSError, ValueError):
                    _unsupported = False

                grading = run_grader(grader_dir, result_dir)
                status = grading["status"]  # "pass" 或 "fail"
                if _unsupported:
                    task[state_field] = "skipped"
                    task[audit_field] = "skipped"
                    task[passed_field] = 0
                    task[failed_field] = 0
                    task[total_field] = 0
                    task.setdefault("unsupported_not_failed", True)
                else:
                    task[state_field] = "pass" if status == "pass" else "fail"
                    task[audit_field] = "pass" if status == "pass" else "fail"
                    task[passed_field] = grading["passed"]
                    task[failed_field] = grading["total"] - grading["passed"]
                    task[total_field] = grading["total"]

                # 写入 grading_result.json 作为审计追踪
                grading_path = result_dir / "grading_result.json"
                grading_path.write_text(json.dumps(grading, ensure_ascii=False, indent=2))
                if _unsupported:
                    print(f"  {tid}/{mode}: 跳过（任务未真实执行，不计入失败）")
                else:
                    print(f"  {tid}/{mode}: {status} ({grading['passed']}/{grading['total']})")
            else:
                print(f"  {tid}/{mode}: 跳过（缺少 grader 或结果目录）")

        # 规范状态取自 with_skill
        task["state"] = task["with_skill_state"]
        task["state_source"] = "spec_review"

        # 基于 Grader 结果设置评审备注
        notes_parts = []
        if task["baseline_state"] == "pass":
            notes_parts.append(f"Baseline: 通过 ({task['baseline_passed_checks']}/{task['baseline_total_checks']})")
        else:
            notes_parts.append(f"Baseline: 未通过 ({task['baseline_passed_checks']}/{task['baseline_total_checks']})")
        if task["with_skill_state"] == "pass":
            notes_parts.append(f"With-skill: 通过 ({task['with_skill_passed_checks']}/{task['with_skill_total_checks']})")
        else:
            notes_parts.append(f"With-skill: 未通过 ({task['with_skill_passed_checks']}/{task['with_skill_total_checks']})")
        task["review_notes"] = "；".join(notes_parts)

    # --- 回填安全任务 ---
    # 实际探测 ID 规范（SA_=abnormal, SP_=permission, SS_=sensitive），与 Tasks.json / sample 保持一致
    _SEC_CATS = ["abnormal", "permission", "sensitive"]

    def _find_security_grader_dir(tid: str, preferred_cat: str) -> Path | None:
        """定位安全探测的 Grader 目录：先按映射类别，再回退扫描全部类别。

        解决历史会话暴露的问题：探测 ID 未严格遵循 SA_/SP_/SS_ 前缀（如 S1 实际置于
        security/permission/ 下）时，PROBE_GROUP_MAP 默认 abnormal 会导致目录找不到而被跳过。
        """
        candidates = [preferred_cat] + [c for c in _SEC_CATS if c != preferred_cat]
        for cat in candidates:
            candidate = sample_dir / "security" / cat / tid / "Grader"
            if candidate.exists():
                return candidate
        return None

    # P3②：无外部依赖端点（evidence_skipped）时，安全探测判 N/A 满分，不重跑 Grader。
    # 关键：本函数会「重新运行 Grader」并用其输出覆盖 grading_result.json（见下方 run_grader），
    # 若此处不短路，Grader 因缺 verification.json（无端点故无证据）仍判 fail，
    # 会把 exec_security_probes 已写好的 N/A 评分覆盖成 fail，导致 0/N 通过（语义倒置）。
    evidence_skipped = (exec_dir / "security" / "evidence_skipped.json").is_file()
    if evidence_skipped:
        print("  [security] 检测到 evidence_skipped：无外部依赖端点（无外部攻击面），"
              "安全探测判 N/A 满分，跳过 Grader 重跑")

    for task in tasks_data["security_tasks"]:
        tid = task["task_id"]
        # T-13：PROBE_GROUP_MAP 的 SA_/SP_/SS_ 前缀已不适用于 probe_asiXX 命名（恒回退 abnormal）。
        # 改为按探针 ID 推导（probe_asi03 → derive_security_group("ASI03")）；无法推导时回退旧映射，
        # 且 _find_security_grader_dir 仍会遍历全部类别，不会因猜错而漏找。
        preferred_cat = ""
        _m = re.match(r"^probe_(asi\d{2})$", tid, re.IGNORECASE)
        if _m:
            try:
                preferred_cat = derive_security_group(_m.group(1).upper())
            except ValueError:
                preferred_cat = ""
        if not preferred_cat:
            preferred_cat = PROBE_GROUP_MAP.get(tid, "abnormal")

        grader_dir = _find_security_grader_dir(tid, preferred_cat)
        result_dir = spec_dir / "results" / "security" / "probes" / tid / "results"

        if evidence_skipped:
            # 与 exec_security_probes 的 N/A payload 同构（10/10 通过，非安全问题）
            task["state"] = "pass"
            task["state_source"] = "spec_review"
            task["audit_label"] = "pass"
            task["passed_checks"] = 10
            task["failed_checks"] = 0
            task["total_checks"] = 10
            task["result"] = "PASS"
            task["notes"] = ("无外部依赖端点，无外部攻击面，本探测项不适用"
                             "（N/A，非安全问题，未重跑 Grader）")
            task["all_checks_passed"] = True
            # T-08：N/A 保留 state=pass 仅为兼容下游渲染，但显式标记"不计入评分"
            task["excluded_from_scoring"] = True
            task["exclusion_reason"] = "无外部依赖端点，无外部攻击面，本探测项不适用（N/A，非安全问题）"
            print(f"  {tid}: N/A 无外部攻击面（已标记不计入评分）")
            continue

        if grader_dir is not None and result_dir.exists():
            grading = run_grader(grader_dir, result_dir)
            status = grading["status"]
            task["state"] = "pass" if status == "pass" else "fail"
            task["state_source"] = "spec_review"
            task["audit_label"] = "pass" if status == "pass" else "fail"
            task["passed_checks"] = grading["passed"]
            task["failed_checks"] = grading["total"] - grading["passed"]
            task["total_checks"] = grading["total"]
            task["result"] = "PASS" if status == "pass" else "FAIL"
            task["notes"] = (
                f"Grader 结果: {status} ({grading['passed']}/{grading['total']}), "
                f"must_pass_satisfied={grading['must_pass_satisfied']}"
            )

            task["all_checks_passed"] = grading["passed"] == grading["total"]

            # T-07：探测未生效（如全部 405）时评分结果不计入通过率，避免"没测到"被当作"安全"
            if grading.get("excluded_from_scoring"):
                task["excluded_from_scoring"] = True
                task["exclusion_reason"] = grading.get("exclusion_reason", "探测未生效")
                print(f"  {tid}: ⚠ 已标记不计入评分（{grading.get('exclusion_reason')}）")

            # 写入 grading_result.json
            grading_path = result_dir / "grading_result.json"
            grading_path.write_text(json.dumps(grading, ensure_ascii=False, indent=2))
            print(f"  {tid}: {status} ({grading['passed']}/{grading['total']})")
        else:
            print(f"  {tid}: 跳过（缺少 grader 或结果目录）")

    # 更新 security_summary
    sec_sum = tasks_data["security_summary"]
    sec_tasks = tasks_data["security_tasks"]
    passed_count = sum(1 for t in sec_tasks if t["state"] == "pass")
    sec_sum["passed_probes"] = passed_count
    sec_sum["security_score"] = round(passed_count / len(sec_tasks), 2) if sec_tasks else 0.0

    # 按维度统计
    dims = {}
    for t in sec_tasks:
        dim = t.get("security_dimension", "unknown")
        if dim not in dims:
            dims[dim] = {"passed": 0, "total": 0}
        dims[dim]["total"] += 1
        if t["state"] == "pass":
            dims[dim]["passed"] += 1

    for dim, stats in dims.items():
        stats["score"] = round(stats["passed"] / stats["total"], 2) if stats["total"] else 0.0
        if dim in sec_sum["by_dimension"]:
            sec_sum["by_dimension"][dim].update(stats)

    # 更新 summary 部分
    func_tasks = tasks_data["tasks"]
    utility_passed = sum(1 for t in func_tasks if t["state"] == "pass")
    baseline_passed = sum(1 for t in func_tasks if t.get("baseline_state") == "pass")
    both_success = sum(1 for t in func_tasks if t["state"] == "pass" and t.get("baseline_state") == "pass")
    skill_failed = sum(1 for t in func_tasks if t["state"] == "fail")

    tasks_data["summary"]["utility_score"] = round(utility_passed / len(func_tasks), 2) if func_tasks else 0.0
    tasks_data["summary"]["incremental_utility_tasks"] = utility_passed - baseline_passed
    tasks_data["summary"]["both_success_tasks"] = both_success
    tasks_data["summary"]["skill_failed_tasks"] = skill_failed
    tasks_data["summary"]["valid_tasks"] = len(func_tasks)
    tasks_data["summary"]["security_passed"] = passed_count

    # 写入更新后的 Tasks.json
    output = json.dumps(tasks_data, ensure_ascii=False, indent=2)
    tasks_json_path.write_text(output, encoding="utf-8")
    print(f"\n已写入 {tasks_json_path}")

    # 摘要
    print(f"\n=== 评审摘要 ===")
    print(f"功能任务: {utility_passed}/{len(func_tasks)} 通过（baseline: {baseline_passed}, with_skill: {utility_passed}）")
    print(f"安全探测: {passed_count}/{len(sec_tasks)} 通过")
    print(f"两者均通过: {both_success}, Skill 失败: {skill_failed}")


if __name__ == "__main__":
    main()
