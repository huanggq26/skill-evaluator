#!/usr/bin/env python3
"""功能任务脚手架批量生成器（generate_functional_scaffolds）。

问题背景
--------
原流程中每个功能任务需 AI 逐 token 手写 Case 目录（TaskDescription.md + WorkSpace/
+ Grader/{grader_manifest.json, run.py, R1.py~RN.py}）。单个被测技能往往有数个至
十余个功能任务（数量动态、由"baseline≠withskill 差异项全选"决定），构成显著的
单对话 token 瓶颈，且易因预算耗尽而漏生成（违反"相关差异项全量覆盖"规则）。

本工具的作用（与安全探针生成器 generate_probe_scaffolds 同范式）
-------------------------------------------------------------
把"功能任务 → 具体脚手架"改为**声明式 JSON 描述**，由本脚本程序化产出每个任务的
完整可运行脚手架：
  - 文件创建由脚本完成，不再消耗对话 token → 消解脚手架瓶颈；
  - AI / 编排者只需编写一小段 `tasks_spec.json`（每个任务的目标、层级、评分项
    kind/字段描述），不必手写目录与 Grader；
  - 同时产出 `functional_tasks.generated.json`（manifest 片段），供合并进
    benchmark_manifest.json（plan-first）。

通用性前提（强制，见 AGENTS_RULES / 全局记忆）
-------------------------------------------
本脚本**不绑定任何特定被测技能，也不绑定本评测器自身**：
  - 不接受、不内嵌任何技能名 / 业务逻辑；技能相关的一切内容（objective、评分项
    描述、断言路径）全部来自输入的 tasks_spec.json；
  - 复用的通用断言内核 functional_checks.py 只实现与技能无关的校验种类
    （字段存在/取值/JSON 合法/产物存在/子串包含）；
  - 生成的 TaskDescription.md / run.py 均为**通用模板**，不含被测技能专有名词。
因此同一脚本可对任何符合 benchmark_manifest.spec.md 的功能任务结构生效。

用法
----
  python generate_functional_scaffolds.py --spec tasks_spec.json --out sample
  （--out 指向样本根目录，即承载 common/ 与 hard/ 的那一层；生成器在其下按
   {bucket}/{id}/ 建目录，bucket 取自 spec 每个任务的 "bucket" 字段，无需在
   --out 里重复写 common/）

spec 结构见本文件底部 EXAMPLE。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

# ── 通用常量（与 config.md / task_description.spec.md 保持一致；此处仅做生成默认，
#    不写死到产物语义里，manifest 片段按规范固定值填） ──────────────────────────
RUBRIC_DEFAULT = 10          # 评分项数固定（config.md {RUBRIC_COUNT}）
PASS_THRESHOLD = 8           # 最低通过数
MUST_PASS = ("R1", "R2")     # 硬通过项（基础合规 R1~R3 中取前两）
RESULT_PATH = "grading_result.json"


# ── 通用模板（无任何技能专有名词） ──────────────────────────────────────────────
RUN_PY = '''#!/usr/bin/env python3
"""___PID___ 汇总运行器（由 generate_functional_scaffolds 生成，通用模板）。"""
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--task-root", required=True); ap.add_argument("--result-root", required=True)
    args = ap.parse_args()
    task_root = Path(args.task_root); result_root = Path(args.result_root); result_root.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((task_root / "Grader" / "grader_manifest.json").read_text(encoding="utf-8"))
    results = []
    for r in manifest["rubrics"]:
        grader = task_root / "Grader" / r["grader"]
        proc = subprocess.run([sys.executable, str(grader), "--task-root", str(task_root), "--result-root", str(result_root)], capture_output=True, text=True)
        try:
            res = json.loads(proc.stdout)
        except Exception:
            res = {"rubric_id": r["id"], "passed": False, "score": 0, "reason": "评分器无有效 JSON", "evidence": {}}
        res.setdefault("rubric_id", r["id"]); results.append(res)
    passed = sum(1 for x in results if x.get("passed")); total = len(results)
    must = set(manifest["pass_policy"].get("must_pass", []))
    mp = all(any(x.get("rubric_id") == m and x.get("passed") for x in results) for m in must)
    status = "fail" if not mp else ("pass" if passed >= manifest["pass_policy"]["minimum_pass_count"] else ("partial" if passed > 0 else "fail"))
    out = {"task_id": task_root.name, "status": status, "outcome_status": "satisfied" if status in ("pass", "partial") else "failed", "passed": passed, "total": total, "must_pass_satisfied": mp, "results": results}
    (result_root / manifest["result_path"]).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False))

if __name__ == "__main__":
    main()
'''


def rubric_py(pid: str, r: dict, primary_result: str) -> str:
    check = dict(r.get("check", {"kind": "custom"}))
    check["rubric_id"] = r["id"]
    crit = r.get("criterion", r["id"])
    n = r["id"][1:] if r["id"].startswith("R") else r["id"]
    # 必须用 repr() 而非 json.dumps() 内联——json.dumps 会把布尔渲染成
    # true/false，生成的 Python 源码 NameError（与探针生成器同源修复）。
    check_literal = repr(check)
    return (
        "#!/usr/bin/env python3\n"
        f'"""{pid} R{n}: {crit}"""\n'
        "from __future__ import annotations\n"
        "import argparse, json\n"
        "from pathlib import Path\n"
        "from _checks import run_check\n"
        "\n"
        f"CHECK = {check_literal}\n"
        "\n"
        "def grade(task_root: Path, result_root: Path) -> dict:\n"
        f'    return run_check(CHECK, result_root / "{primary_result}")\n'
        "\n"
        "if __name__ == '__main__':\n"
        "    ap = argparse.ArgumentParser(); ap.add_argument('--task-root', required=True); ap.add_argument('--result-root', required=True)\n"
        "    a = ap.parse_args(); print(json.dumps(grade(Path(a.task_root), Path(a.result_root)), ensure_ascii=False))\n"
    )


def task_description_md(t: dict) -> str:
    tid = t["id"]
    bucket = t.get("bucket", "common")
    level = t.get("functional_level", t.get("level", "basic"))
    obj = t.get("objective", "")
    outcome = t.get("outcome_description", obj)
    pcs = t.get("pass_criteria", []) or ["（由 run_plan 填写）"]
    ccs = t.get("constraint_checks", []) or ["（无）"]
    rubrics = t.get("rubrics", [])
    lines = [
        f"# TaskDescription — {tid} 功能任务（{bucket}/{level}）",
        "",
        "## 1. Outcome",
        f"完成状态：{outcome}",
        "",
        "## 2. Output Contract",
        f"- 主结果物：`{t.get('primary_result', 'result.json')}`",
        "- 字段约定遵循 grader.spec.md 与 task_description.spec.md（status / summary / items / evidence / notes）。",
        "- JSON 输出不得包裹 Markdown 代码块。",
        "",
        "## 3. Environment And Dependencies",
        "- 平台：macos/linux/windows；命令：python3；网络：依任务声明；模式：code",
        "",
        "## 4. WorkSpace Inputs",
        "- `WorkSpace/` 含触发本任务的输入证据（如有）。",
        "",
        "## 5. Grader Contract",
        f"- `Grader/grader_manifest.json` 映射 R1~R{RUBRIC_DEFAULT}；评分器读取主结果物。",
        "",
        "## 6. Unsupported And Blocked Conditions",
        "- 环境无 python3：主结果物设 blocked=true，记为 unsupported。",
        "",
        "## 7. Pass Policy",
        f"- must_pass：{', '.join(MUST_PASS)}；最低 {PASS_THRESHOLD}/{RUBRIC_DEFAULT}",
        "",
        "## 通过条件（pass_criteria）",
    ]
    lines += [f"- {p}" for p in pcs]
    lines += ["", "## 约束检查（constraint_checks）"]
    lines += [f"- {c}" for c in ccs]
    lines += ["", f"## 评分项（共 {len(rubrics)} 项）"]
    for r in rubrics:
        lines.append(f"- {r['id']} [{r.get('priority', 'should')}]: {r.get('criterion', r['id'])}")
    return "\n".join(lines) + "\n"


def build_manifest_entry(t: dict, samples_dir: str) -> dict:
    tid = t["id"]
    bucket = t.get("bucket", "common")
    primary_result = t.get("primary_result", "result.json")
    rubrics = t.get("rubrics", [])
    # case_dir 相对 SAMPLES_DIR（即 sample/），不得带 "sample/" 前缀
    case_dir = f"{bucket}/{tid}"
    outcome_rubrics = [
        {"id": r["id"], "criterion": r.get("criterion", r["id"]), "priority": r.get("priority", "should")}
        for r in rubrics
    ]
    grader_rubrics = [
        {"id": r["id"], "grader": f"{r['id']}.py", "kind": "json_schema",
         "source": primary_result, "official": True, "weight": 1}
        for r in rubrics
    ]
    return {
        "id": tid,
        "category": "functional",
        "functional_level": t.get("functional_level", t.get("level", "basic")),
        "tier": t.get("tier", "l0_goal"),
        "user_facing": bool(t.get("user_facing", True)),
        "objective": t.get("objective", ""),
        "case_dir": case_dir,
        "task_description_path": f"{case_dir}/TaskDescription.md",
        "workspace_dir": f"{case_dir}/WorkSpace",
        "grader_dir": f"{case_dir}/Grader",
        "grader_manifest_path": f"{case_dir}/Grader/grader_manifest.json",
        "grader_entry": f"{case_dir}/Grader/run.py",
        "rubric_count": len(rubrics),
        "rubric_pass_threshold": PASS_THRESHOLD,
        "all_checks_must_pass": False,
        "applicable_modes": ["baseline", "with_skill"],
        "should_invoke_skill": bool(t.get("should_invoke_skill", True)),
        "outcome": {
            "description": t.get("outcome_description", t.get("objective", "")),
            "max_iterations": 3,
            "rubrics": outcome_rubrics,
        },
        "pass_criteria": t.get("pass_criteria", []),
        "constraint_checks": t.get("constraint_checks", []),
        "output_contract": {
            "format": "json",
            "primary_result_path": primary_result,
            "required_artifacts": [primary_result],
            "scored_fields": t.get("scored_fields", ["$.status", "$.items", "$.evidence"]),
            "parse_rules": {
                "json_only": True, "string_normalization": "trim_edges_only",
                "numeric_tolerance": 0.01,
                "array_matching": {"mode": "anchor_key", "anchor_key": "id"},
                "null_handling": "json_null_only",
            },
        },
        "environment": {
            "platforms": ["macos", "linux", "windows"],
            "requires": {"commands": ["python3"], "packages": [], "credentials": [],
                         "services": [], "hardware": []},
            "network": t.get("network", "not_required"),
        },
        "verifier": {
            "mode": "code", "entry": "Grader/run.py", "result_path": RESULT_PATH,
            "pass_threshold": PASS_THRESHOLD, "partial_threshold": max(PASS_THRESHOLD - 2, 0),
            "rubrics": grader_rubrics,
        },
        "unsupported_rules": [],
    }


def generate(spec: dict, out_dir: Path) -> list:
    checks_src = Path(__file__).with_name("functional_checks.py")
    if not checks_src.exists():
        raise SystemExit(f"找不到可复用检查库：{checks_src}")
    samples_dir = spec.get("samples_dir", "sample")
    primary_result = spec.get("primary_result", "result.json")
    entries = []
    for t in spec["tasks"]:
        tid = t["id"]
        bucket = t.get("bucket", "common")
        case_dir = out_dir / bucket / tid
        grader_dir = case_dir / "Grader"
        ws_dir = case_dir / "WorkSpace"
        grader_dir.mkdir(parents=True, exist_ok=True)
        ws_dir.mkdir(parents=True, exist_ok=True)

        # TaskDescription.md
        (case_dir / "TaskDescription.md").write_text(task_description_md(t), encoding="utf-8")

        # Grader/grader_manifest.json
        manifest = {
            "schema_version": "grader.v1",
            "entry": "run.py",
            "result_path": RESULT_PATH,
            "primary_result_path": primary_result,
            "pass_policy": {"minimum_pass_count": PASS_THRESHOLD, "must_pass": list(MUST_PASS)},
            "rubrics": [
                {"id": r["id"], "grader": f"{r['id']}.py", "type": "json_schema", "official": True, "weight": 1}
                for r in t.get("rubrics", [])
            ],
        }
        (grader_dir / "grader_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        # Grader/run.py（通用）
        (grader_dir / "run.py").write_text(RUN_PY.replace("___PID___", tid), encoding="utf-8")

        # Grader/_checks.py（复用通用内核）
        shutil.copyfile(checks_src, grader_dir / "_checks.py")

        # Grader/R1.py ~ RN.py
        for r in t.get("rubrics", []):
            (grader_dir / f"{r['id']}.py").write_text(rubric_py(tid, r, primary_result), encoding="utf-8")

        entries.append(build_manifest_entry(t, samples_dir))
        print(f"[ok] {bucket}/{tid}  ({len(t.get('rubrics', []))} rubrics)")
    return entries


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True, help="功能任务声明式规格 JSON")
    ap.add_argument("--out", required=True, help="目标 functional 目录根，如 sample/common")
    ap.add_argument("--manifest-out", default=None, help="可选：写出 functional_tasks.generated.json 的路径")
    args = ap.parse_args()

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    entries = generate(spec, out_dir)

    manifest_out = args.manifest_out or (out_dir / "functional_tasks.generated.json")
    Path(manifest_out).write_text(
        json.dumps({"functional_tasks": entries}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n生成 {len(entries)} 个功能任务脚手架；manifest 片段 → {manifest_out}")


if __name__ == "__main__":
    main()
