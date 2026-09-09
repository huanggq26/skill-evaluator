#!/usr/bin/env python3
"""skill-evaluator 改造自验证（防漂移）。

作用：在真实技能上串跑「攻击面打标 → 自动安全探测 → 依赖提取 → 依赖探测」，
再用真实产物构造 benchmark_manifest，断言各守卫（E24/E25/E26/E27）不冲突且按预期放行；
并对报告去噪（机器门禁 R4/R6）做单元断言。供后续改动回归。

用法：
    python3 .project/tmp/selfcheck_refactor.py
退出码：0 = 全绿；非 0 = 存在回归。
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = next(p for p in Path(__file__).resolve().parents if (p / "scripts" / "run_eval_pipeline.sh").exists())
SCRIPTS = REPO / "scripts"


def _run(cmd, cwd=REPO):
    r = subprocess.run([sys.executable, *cmd], capture_output=True, text=True, cwd=str(cwd))
    if r.returncode != 0:
        raise RuntimeError(f"命令失败 {cmd}:\n{r.stdout[-400:]}\n{r.stderr[-400:]}")
    return r


def _step(name, fn):
    try:
        fn()
        print(f"✅ {name}")
    except Exception as exc:  # noqa: BLE001
        print(f"❌ {name}\n   >> {exc}")
        raise


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="selfcheck_"))
    sample = work / "sample"
    sample.mkdir()
    try:
        # 1) 真实提取链：攻击面打标 → 自动安全探测 → 依赖提取 → 依赖探测
        surface = work / "surface_tags.json"
        _run(["scripts/surface_tagging.py", "--skill-dir", str(REPO), "--output", str(surface)])
        auto_sec = work / "auto_security_spec.json"
        _run(["scripts/auto_security_spec.py", "--surface-tags", str(surface),
              "--out", str(auto_sec), "--sample-root", str(sample)])
        preflight = work / "preflight.json"
        _run(["scripts/extract_deps.py", "--skill-dir", str(REPO), "--manifest", str(preflight),
              "--output", work / "deps.json", "--write-manifest"])
        probe = work / "dependency_probe.json"
        _run(["scripts/dep_probe.py", "--manifest", str(preflight), "--output", str(probe)])

        # E25 读取约定：sample_root/dependency_probe.json
        shutil.copy(probe, sample / "dependency_probe.json")

        # 2) 组装真实产物
        surface_data = json.loads(surface.read_text())
        sec_data = json.loads(auto_sec.read_text())
        deps_data = json.loads(preflight.read_text())
        external_deps = deps_data.get("external_deps") or deps_data.get("deps") or []
        skill_surface_tags = surface_data.get("skill_surface_tags", [])
        security_probes = sec_data.get("security_probes", [])

        # 3) 构造功能任务（满足结构守卫 + 真实 capability_source + 性能标记派生）
        #   - A 类（reach）：skill_asset 指向真实脚本
        #   - B 类（efficiency）：带 performance_marker + efficiency_axis，skill_doc 锚点须存在于 SKILL.md
        skill_md = (REPO / "SKILL.md").read_text(encoding="utf-8", errors="ignore")
        # 取 SKILL.md 中一个真实存在的长词作为 skill_doc 锚点
        doc_anchor = "Skill Evaluation Report" if "Skill Evaluation Report" in skill_md else skill_md.split()[0]
        functional_tasks = [
            {
                "id": "C_01", "user_facing": True, "tier": "l1_user", "case_dir": "common/C_01",
                "outcome": "ok", "output_contract": "ok", "environment": "ok",
                "verifier": "ok", "unsupported_rules": "ok",
                "task_type": "A",
                "capability_source": "skill_asset:scripts/validate_manifest_contract.py",
            },
            {
                "id": "C_02", "user_facing": True, "tier": "l1_user", "case_dir": "common/C_02",
                "outcome": "ok", "output_contract": "ok", "environment": "ok",
                "verifier": "ok", "unsupported_rules": "ok",
                "task_type": "B", "performance_marker": True, "efficiency_axis": ["time"],
                "capability_source": f"skill_doc:{doc_anchor}",
            },
        ]

        manifest = {
            "skill_surface_tags": skill_surface_tags,
            "security_probes": security_probes,
            "external_deps": external_deps,
            "functional_tasks": functional_tasks,
            "internal_checks": [],
            "summary": {
                "total_functional_tasks": len(functional_tasks),
                "total_internal_checks": 0,
                "common_tasks": sum(1 for t in functional_tasks if t["case_dir"].startswith("common/")),
                "hard_tasks": sum(1 for t in functional_tasks if t["case_dir"].startswith("hard/")),
            },
        }
        manifest_path = sample / "benchmark_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        # 4) 运行守卫：断言真实数据下 E24/E25/E26/E27 全部放行（退出码 0）
        val = SCRIPTS / "validate_manifest_contract.py"
        r = subprocess.run(
            [sys.executable, str(val), "--manifest", str(manifest_path),
             "--sample-root", str(sample), "--skill-dir", str(REPO)],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, f"守卫未放行真实数据（退出码 {r.returncode}）：\n{r.stdout[-600:]}\n{r.stderr[-600:]}"

        # 5) 报告去噪单元断言（R4/R6 → 机器门禁，不进人人读）
        spec = importlib.util.spec_from_file_location("go", str(SCRIPTS / "generate_outputs.py"))
        go = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(go)
        human, gate = go._summarize_failed_checks([
            {"notes": "R4 字段缺失"}, {"review_notes": "R6 产物状态未通过"},
            {"notes": "R5 计算错误"}, {"notes": "R7 排序异常"},
        ])
        assert "R5 计算错误" in human and "R7 排序异常" in human, "R5/R7 应进入人读"
        assert all("R4" not in h and "R6" not in h for h in human), "R4/R6 不应出现在人读"
        assert any("R4" in g for g in gate) and any("R6" in g for g in gate), "R4/R6 应在机器门禁"

        print(f"   真实技能提取：surface_tags={len(skill_surface_tags)} "
              f"security_probes={len(security_probes)} external_deps={len(external_deps)}")
        print("   守卫 E24/E25/E26/E27：真实数据下全部放行 ✅")
        print("   报告去噪：R4/R6 正确分离到机器门禁 ✅")
        return 0
    except AssertionError as e:
        print(f"❌ 断言失败：{e}")
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"❌ 异常：{e}")
        return 1
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
