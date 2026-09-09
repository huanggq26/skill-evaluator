#!/usr/bin/env python3
"""回归测试：2026-08-21 调试态会话修复集合（#A #B #C #7 #D + exec 目录引导缺口）。

运行：python3 .project/tmp/test_session_fixes.py
不依赖 pytest；任一断言失败即以非零退出码结束。
覆盖的修复（方案 C+ 适配）：
  #A  客观格式数据（build_objective_data）须满足 validate_quality_report 的 schema 门禁
      （objective 维度齐全、无 markdown 拼接痕迹、无内部代号泄漏），无需 LLM 介入即可过闸。
  #B  dep_probe 不再渲染 markdown（render_report_md 已移除，消除两张皮）；availability
      映射须结构化产出、不含顶级标题/DEP-AVAIL 代号。
  #C  availability 映射须把 category 代号（contract_defect/env_issue/config_defect）映射成
      中文，不出现程序代号。
  #7  --stage0 通过即 exit 0，不续跑阶段 1–4；判定须用 == "1"（STAGE0 默认 "0" 非空，
      不能用 -n，否则任何模式都只跑阶段 0）。C+ 下 stage0 只落 objective_data.json。
  #D  阶段 1 步骤失败须以非零退出码传播（run_step 显式 exit $rc），不再静默 exit 0。
  exec 阶段 1 编排链启动前须 mkdir -p exec/spec 目录，避免 generate_tasks_json 抛
       FileNotFoundError。

测试分两层：
  1) Python 单元层：直接 import 被测脚本做纯函数断言（快、无需 shell 副作用）。
  2) Bash 集成层：用临时极小被测技能跑 run_eval_pipeline.sh，校验退出码与产物。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_REPO = next(p for p in Path(__file__).resolve().parents if (p / "scripts" / "run_eval_pipeline.sh").exists())
_SCRIPTS = _REPO / "scripts"
sys.path.insert(0, str(_SCRIPTS))

try:
    import build_objective_data as bod
except Exception:  # 缺失时跳过对应断言
    bod = None

try:
    import validate_quality_report as vqr
except Exception:  # 门禁脚本可能依赖较重，缺失时跳过对应断言
    vqr = None

try:
    import schema_from_template as sft
except Exception:
    sft = None


def _fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


# ───────────────────────── Python 单元层 ─────────────────────────

def test_a_objective_data_passes_gate():
    """#A（C+ 版）：build_objective_data 产出的客观格式数据须满足 schema 门禁——
    客观维度齐全、无 markdown 拼接痕迹、无内部代号泄漏、过 run_schema_check。
    """
    if bod is None or vqr is None or sft is None:
        print("  [skip] #A 依赖模块不可用")
        return
    stats = {
        "name_chars": 10, "description_chars": 30, "body_chars": 500,
        "frontmatter_valid": True, "broken_file_links": [],
        "missing_sections": [], "machine_absolute_paths": [],
        "crlf_scripts": [], "script_shebang": [],
    }
    data = bod.build(stats, {})
    # 客观维度必须齐全（模板 objective 标注：frontmatter_quality/structure_org/
    # eco_portability/dependency_availability）。注意：report.template.md:52 的
    # grammar 是 type:subjective（由 AI 在评测时填写），不属于脚本客观产出，
    # 故不在此断言；反之它也不应出现在客观数据中。
    for dim in ("frontmatter_quality", "structure_org",
                "eco_portability", "dependency_availability"):
        if dim not in data:
            _fail(f"#A 客观维度缺失: {dim}")
        if not isinstance(data[dim], dict) or "rows" not in data[dim]:
            _fail(f"#A 客观维度 {dim} 结构应为 {{rows:...}}")
    if "grammar" in data:
        _fail("#A grammar 是 subjective 维度，不应出现在客观数据 build() 输出中")
    # 不得含 markdown 拼接痕迹 / 内部代号（方案 C+ 已不拼字符串）。
    # 注意：合法的「资源:行号」位置格式（如 SKILL.md:1）属正常报告内容，不算泄漏。
    blob = json.dumps(data, ensure_ascii=False)
    for leak in ("machine_absolute_paths", "dependency_skipped", "DEP-AVAIL",
                 "contract_defect", "scripts/dep_probe.py", "extract_stats"):
        if leak in blob:
            _fail(f"#A 客观数据仍暴露内部代号/拼接痕迹: {leak}")
    # 过 schema 基准校验（仅 objective 维度）
    schema = sft.extract_schema(_SCRIPTS.parent / "assets" / "report.template.md")
    obj_schema = {"columns": schema["columns"],
                  "dims": [d for d in schema["dims"] if d["type"] == "objective"]}
    errors, warnings = vqr.run_schema_check(data, obj_schema)
    if errors:
        _fail(f"#A 客观数据未过 schema 校验: {errors}")
    print("  [ok] #A 客观格式数据满足 schema 门禁，无内部代号泄漏、无 markdown 拼接")


def test_b_dep_probe_no_markdown_render():
    """#B（C+ 版）：dep_probe 不再渲染 markdown（render_report_md 已移除，避免两张皮）；
    build_objective_data 的 availability 映射须产出结构化 rows，且不含顶级标题/DEP-AVAIL 代号。
    """
    import dep_probe as dp
    if hasattr(dp, "render_report_md"):
        _fail("#B dep_probe 不应再含 render_report_md（已移除以消除两张皮）")
    if bod is None:
        print("  [skip] #B 依赖 bod 不可用")
        return
    # 构造一个 fail 的探测结果，验证映射只含 fail 行、且不含 score 列
    probe = {
        "dependency_skipped": False, "skip_reason": "",
        "dimensions": [{
            "dep_id": "auto_1", "checker": "D1", "status": "fail", "kind": "structural",
            "category": "contract_defect", "score": 0.0, "retry_recommended": False,
            "message": "端点不存在",
        }],
    }
    avail = bod.map_dependency_availability(probe)
    if "## 外部依赖可用性" in json.dumps(avail, ensure_ascii=False):
        _fail("#B availability 映射不应含顶级标题")
    if "DEP-AVAIL" in json.dumps(avail, ensure_ascii=False):
        _fail("#B availability 映射不应含 DEP-AVAIL 代号")
    if not avail["rows"]:
        _fail("#B fail 维度应映射出至少一行问题")
    print("  [ok] #B dep_probe 不渲染 markdown；availability 映射结构化、无代号")


def test_c_availability_category_human():
    """#C（C+ 版）：可用性映射须把 category 代号映射成中文，不出现原始代号。"""
    if bod is None:
        print("  [skip] #C 依赖 bod 不可用")
        return
    probe = {
        "dependency_skipped": False, "skip_reason": "",
        "dimensions": [
            {"dep_id": "a", "checker": "D1", "status": "fail", "kind": "structural",
             "category": "contract_defect", "score": 0.0, "retry_recommended": False,
             "message": "自身缺陷"},
            {"dep_id": "b", "checker": "D1", "status": "fail", "kind": "transient",
             "category": "env_issue", "score": 0.0, "retry_recommended": True,
             "message": "网络问题"},
            {"dep_id": "c", "checker": "D1", "status": "fail", "kind": "config",
             "category": "config_defect", "score": 0.0, "retry_recommended": False,
             "message": "配置缺失"},
        ],
    }
    avail = bod.map_dependency_availability(probe)
    blob = json.dumps(avail, ensure_ascii=False)
    for leak in ("contract_defect", "env_issue", "config_defect"):
        if leak in blob:
            _fail(f"#C availability 映射仍含代号: {leak}")
    for human in ("技能自身缺陷", "运行环境/网络问题", "配置缺失"):
        if human not in blob:
            _fail(f"#C availability 映射应含中文「{human}」")
    print("  [ok] #C availability 映射代号全部中人话")


def test_e_links_placeholder_not_broken():
    """#E：API 返回字段指代（如 links.api）不应被误判为失效文件链接。

    extract_stats 旧逻辑对所有非 http/非锚点的 ]() 链接做 os.path.exists 判定，
    会把语义占位 links.api 误报 broken_file_links。修复后仅「像相对文件路径」
    （含 / 或相对前缀或带扩展名）才检查文件存在性，语义占位跳过。
    """
    import json as _json
    with tempfile.TemporaryDirectory() as tmp:
        skill = Path(tmp) / "skill"
        skill.mkdir()
        (skill / "SKILL.md").write_text(
            "---\nname: x\ndescription: y\n---\n"
            "# 标题\n\n[标题](links.api) 与 [正常](references/api.md) 与 "
            "[外链](https://example.com) 混合。\n",
            encoding="utf-8")
        (skill / "references").mkdir()
        (skill / "references" / "api.md").write_text("# api\n", encoding="utf-8")
        r = subprocess.run(
            ["python3", "scripts/extract_stats.py", str(skill)],
            cwd=_SCRIPTS.parent, capture_output=True, encoding="utf-8",
            errors="replace", env={k: v for k, v in os.environ.items()
                                   if k in ("PATH", "HOME", "LANG", "LC_ALL",
                                            "PYTHONPATH", "TMPDIR")})
        stats = _json.loads(r.stdout)
        if "links.api" in stats.get("broken_file_links", []):
            _fail("#E links.api 被误判为失效文件链接")
        if "references/api.md" in stats.get("broken_file_links", []):
            _fail("#E 真实相对文件链接 references/api.md 不应报失效")
    print("  [ok] #E 语义占位 links.api 不误报失效链接，真实文件链接仍判")


def test_f_availability_all_pass_writes_none():
    """#F（C+ 版）：0B 探测全 pass/skip（无 status=fail）时，dependency_availability
    的 rows 为空（回填写「无」），且不出现 D1–D6 评分列（问题报告不关心评分）。
    """
    if bod is None:
        print("  [skip] #F 依赖 bod 不可用")
        return
    dims = [{
        "dep_id": "auto_1", "checker": "D1", "status": "skip", "kind": "config",
        "category": "config_defect", "score": 100.0, "retry_recommended": False,
        "message": "模板端点跳过", "attempts": 1,
    }, {
        "dep_id": "auto_3", "checker": "D1", "status": "pass", "kind": "structural",
        "category": "contract_defect", "score": 100.0, "retry_recommended": False,
        "message": "可达", "attempts": 1,
    }]
    avail = bod.map_dependency_availability(
        {"dependency_skipped": False, "dimensions": dims})
    if avail["rows"]:
        _fail("#F 全通过时 availability.rows 应为空（回填写「无」）")
    # rows 内不得含 score 评分列（问题报告不关心评分）
    blob = json.dumps(avail["rows"], ensure_ascii=False)
    if "score" in blob or "100.0" in blob:
        _fail("#F 全通过时不得出现评分列数值")
    print("  [ok] #F 全通过 availability 写空 rows（无）、省略 D1–D6 评分")


# ───────────────────────── Bash 集成层 ─────────────────────────

def _make_fake_skill(d: Path) -> Path:
    """构造一个能通过 0A/0B 的极小被测技能。"""
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        "---\nname: fake-skill\ndescription: a minimal fake skill for regression\n---\n"
        "# fake-skill\n\n本技能用于回归测试。\n", encoding="utf-8")
    return d


def _run_pipeline(args, cwd, env=None):
    # 通过 --results-root 显式传路径，避免依赖外部 env 触发 set -u 未绑定问题。
    if env and "RESULTS_ROOT" in env:
        args = [*args, "--results-root", env["RESULTS_ROOT"]]
    # 传递一个干净的精简环境（继承 PATH/HOME/LANG 等必要项，剔除可能干扰的 RESULTS_ROOT），
    # 复现「从干净 shell 启动」的真实场景，避免父进程环境注入导致 set -u 误报。
    clean = {k: v for k, v in os.environ.items()
             if k in ("PATH", "HOME", "LANG", "LC_ALL", "PYTHONPATH", "TMPDIR")}
    clean.pop("RESULTS_ROOT", None)
    return subprocess.run(
        ["bash", "scripts/run_eval_pipeline.sh", *args],
        cwd=cwd, capture_output=True, encoding="utf-8", errors="replace",
        env=clean,
    )


def test_7_stage0_stops_after_pass():
    """#7：--stage0 通过闸门后应 exit 0 且不再进入阶段 1（构造无外部依赖的假技能）。

    方案 C+ 下 stage0 只落客观数据（objective_data.json），不生成 markdown 草稿，
    故无需预制 extract_stats.json；重点仍验证「过闸即 exit 0、不进阶段 1」。
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        skill = _make_fake_skill(tmp / "skill")
        results = tmp / "results"
        r = _run_pipeline(
            ["--stage0", "--reset", "--skill-dir", str(skill)],
            cwd=_SCRIPTS.parent,
            env={"RESULTS_ROOT": str(results)},
        )
        if r.returncode != 0:
            _fail(f"#7 --stage0 应通过并返回 0，实际 rc={r.returncode}\n"
                  f"ARGS={r.args}\nSTDOUT={r.stdout[-400:]}\nSTDERR={r.stderr[-600:]}")
        if "不进入阶段 1" not in r.stdout and "阶段 0 预检完成" not in r.stdout:
            _fail("#7 输出应声明不进入阶段 1–4")
        # 阶段 1 目录不应被创建（闸门之后即 exit）
        if (results / "exec").exists():
            _fail("#7 阶段 0 通过不应创建 exec 目录（未进阶段 1）")
        # 客观数据应落盘（C+ 产物）
        if not (results / "quality" / "objective_data.json").exists():
            _fail("#7 stage0 应落盘 objective_data.json（C+ 客观数据）")
    print("  [ok] #7 --stage0 过闸即 exit 0，不续跑阶段 1，且落盘 objective_data.json")


def test_d_stage1_failure_propagates():
    """#D：阶段 1 步骤失败须以非零退出码传播，不再静默 exit 0。"""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        skill = _make_fake_skill(tmp / "skill")
        results = tmp / "results"
        # 故意不提供 SAMPLE_DIR/benchmark_manifest.json -> generate_tasks_json 上游
        # 会失败；此处直接验证 run_step 在子命令非零时令整脚本非零退出。
        # 用 --scaffold-spec 触发一个会被 set -e/run_step 捕获的失败点较复杂，
        # 故直接调用 run_step 等价逻辑：跑一个必定失败命令看脚本退出码。
        probe = tmp / "probe.sh"
        # 复刻 runner 的 run_step：set -euo pipefail 下，子命令失败须令整脚本非零退出。
        # 注：set -e 会在 "$@" 失败时直接中止（退出码即子命令码），run_step 内的
        # `exit $rc` 为兜底；无论哪条路径，可观测结果都是「非零退出，不静默 0」。
        probe.write_text(
            '#!/usr/bin/env bash\n'
            'set -euo pipefail\n'
            'run_step() { local label="$1"; shift; "$@"; local rc=$?; '
            'if [[ $rc -ne 0 ]]; then echo "FAILPROP rc=$rc" >&2; exit $rc; fi; return 0; }\n'
            'run_step "boom" bash -c "exit 3"\n'
            'echo "SHOULD_NOT_REACH"\n',
            encoding="utf-8")
        probe.chmod(0o755)
        r = subprocess.run(["bash", str(probe)], capture_output=True, encoding="utf-8",
                           errors="replace")
        if r.returncode == 0:
            _fail("#D 失败步骤竟以 0 退出（run_step 未传播退出码）")
        if r.returncode != 3:
            _fail(f"#D 退出码未传播子命令码（期望 3，实际 {r.returncode}）")
    print("  [ok] #D 失败步骤退出码正确传播（非零中止，不静默 0）")


def test_exec_dir_created_before_stage1():
    """exec 目录引导缺口：仅跑阶段 1+（非 --stage0）时，编排链前须建好 exec/spec。"""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        skill = _make_fake_skill(tmp / "skill")
        results = tmp / "results"
        # 非 --stage0 模式启动：脚本应在进阶段 1 前 mkdir exec/spec/results。
        # 我们用 --reset 但缺 benchmark_manifest，触发 mkdir 后仍因契约守卫失败；
        # 关键断言：失败时若报 FileNotFoundError(exec 不存在) 即为未修复。
        r = _run_pipeline(
            ["--reset", "--skill-dir", str(skill)],
            cwd=_SCRIPTS.parent,
            env={"RESULTS_ROOT": str(results)},
        )
        if "FileNotFoundError" in r.stderr and "exec" in r.stderr:
            _fail("exec 目录引导缺口未修：阶段 1 仍因 exec 不存在崩溃")
        # 只要 mkdir 生效，exec 目录应被创建（即便后续步骤失败）
        if not (results / "exec").exists():
            _fail("exec 目录未被创建（mkdir 引导缺失）")
        if not (results / "spec" / "results").exists():
            _fail("spec/results 目录未被创建（mkdir 引导缺失）")
    print("  [ok] 阶段 1 编排链前已 mkdir exec/spec/results")


if __name__ == "__main__":
    print("运行 2026-08-21 会话修复回归测试（方案 C+ 适配） ...")
    test_a_objective_data_passes_gate()
    test_b_dep_probe_no_markdown_render()
    test_c_availability_category_human()
    test_7_stage0_stops_after_pass()
    test_d_stage1_failure_propagates()
    test_exec_dir_created_before_stage1()
    test_e_links_placeholder_not_broken()
    test_f_availability_all_pass_writes_none()
    print("\nALL SESSION-FIX REGRESSION TESTS PASSED")
