#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""skill-evaluator · 单点评测管线 runner（**跨平台 Python 版**）。

为什么需要它（存在的唯一理由）
------------------------------
原编排器 `run_eval_pipeline.sh` 是 bash 脚本。实证（win 运行日志 A1/A4）：
Windows 环境**没有 bash**，执行方只能把流水线拆成十几个脚本手工逐步执行 →
漏步骤、跳门禁、产物层级错乱（v4/v5 实证）。bash 版内有 35 处 `python3` 硬编码，
即便勉强跑起来也会在 win 上 FileNotFoundError。

本文件是 bash 版的**等价 Python 移植**，阶段划分、门禁、产物路径、退出码语义
全部保持一致，差异仅在于：
  1. 子脚本一律用 `sys.executable` 调用 —— Windows 上自动是 `python.exe`，
     无需任何 shim、不依赖 `python3` 命令是否存在；
  2. 原 bash heredoc（`python3 - <<'PY'`）内联片段改为原生函数，去掉对
     heredoc / sed / basename 等 shell 能力的依赖；
  3. 输出编码统一 utf-8，避免 PowerShell 重定向产生 BOM 引发下游解析失败。

用法（与 bash 版参数完全一致）
------------------------------
    python scripts/run_pipeline.py --mode start
    python scripts/run_pipeline.py --mode full
    python scripts/run_pipeline.py --mode resume
    python scripts/run_pipeline.py --mode full --scaffold-spec /path/spec.json
    python scripts/run_pipeline.py --mode resume --skip-exec-check   # 仅校验样本（CI）
    python scripts/run_pipeline.py --reset --mode full

范围严格限定在《范围与安全契约》(references/scope_contract.md)：
只读被测技能 / 仅写评测工作区 / 仅运行本 skill 自带脚本 / 不联网不删不改系统。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

PY = sys.executable  # 跨平台关键：不写死 python3

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = Path.home() / "Downloads"
EVAL_RESULTS_BASE = os.environ.get(
    "SKILL_EVALUATOR_RESULTS_ROOT", str(DEFAULT_OUTPUT_DIR / "skill-evaluator_results")
)


def _echo(msg: str = "", err: bool = False) -> None:
    stream = sys.stderr if err else sys.stdout
    print(msg, file=stream, flush=True)


def run_step(label: str, args: list[str], fatal: bool = True) -> int:
    """执行一步并打印标签；失败按 fatal 决定是否中止管线（对齐 bash run_step 语义）。"""
    _echo("")
    _echo(f"▶ {label}")
    rc = subprocess.run([PY] + args, cwd=str(SKILL_DIR)).returncode
    if rc != 0:
        if fatal:
            _echo(f"❌ 步骤失败（exit={rc}），中止管线", err=True)
            sys.exit(rc)
        _echo(f"   ⚠ 步骤退出码 {rc}（非阻断，按设计继续）")
    return rc


def run_step_to_file(label: str, args: list[str], out_path: Path) -> int:
    """执行一步并把 stdout 落盘（对齐 bash `> file`）。

    落盘统一用 utf-8（**不带 BOM**）：下游 `load_json` 已改用 utf-8-sig，
    对无 BOM 文件行为完全一致；此处不写 BOM 可避免 PowerShell 重定向场景
    叠加 BOM 导致首字符 \\ufeff 解析失败（实证 A2）。
    """
    _echo("")
    _echo(f"▶ {label}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        rc = subprocess.run([PY] + args, cwd=str(SKILL_DIR), stdout=fh).returncode
    if rc != 0:
        _echo(f"❌ 步骤失败（exit={rc}），中止管线", err=True)
        sys.exit(rc)
    return rc


def _load_json(path: Path) -> dict:
    """读取 JSON（utf-8-sig：自动剥离 Windows 产物常见的 BOM）。"""
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}


class Ctx:
    """流水线上下文：集中承载路径与开关，避免散落的全局变量。"""

    def __init__(self, args: argparse.Namespace) -> None:
        self.target_skill = Path(args.skill_dir).resolve()
        self.results_root = Path(args.results_root).resolve()
        self.skill_name = self.target_skill.name
        # ── 目录结构：<结果根>/<技能名>/<本次运行标识> ──
        # 旧结构实为 <结果根(调用方传入，常含版本号)>/<技能名>：版本在外、技能在内，
        # 同一技能的多轮评测散落在不同父目录下（…_v15 / …_v16 各自为政），
        # 无法按技能归组对比。现改为「技能 → 运行」两级，便于同技能跨轮对比。
        # 未指定 --run-id 时用时间戳，保证每次运行互不覆盖。
        self.run_id = (getattr(args, "run_id", "") or "").strip() or time.strftime("%Y%m%d-%H%M%S")
        self.ws = self.results_root / self.skill_name / self.run_id
        self.sample_dir = self.ws / "sample"
        self.exec_dir = self.ws / "exec"
        self.spec_dir = self.ws / "spec"
        self.quality_dir = self.ws / "quality"
        self.quality_report = self.quality_dir / "quality_report.md"
        self.quality_results_dir = self.quality_dir / "results"
        self.quality_score_out = self.quality_results_dir / "quality_score.json"
        self.scaffold_spec = args.scaffold_spec or ""
        self.security_spec = args.security_spec or ""
        self.mode = args.mode
        self.skip_subj_gate = args.skip_subjective_gate
        self.skip_exec_check = args.skip_exec_check
        self.project_state = args.project_state or ""


# ============================================================
# 阶段 0 · 开始阶段质量门禁
# ============================================================
def run_stage0(ctx: Ctx) -> None:
    ctx.quality_dir.mkdir(parents=True, exist_ok=True)
    ctx.quality_results_dir.mkdir(parents=True, exist_ok=True)

    stats_json = ctx.quality_results_dir / "extract_stats.json"
    run_step_to_file(
        f"[开始阶段] 0/a extract_stats (客观统计 → {stats_json})",
        ["scripts/extract_stats.py", str(ctx.target_skill)],
        stats_json,
    )

    run_step(
        "[开始阶段] 0/a+ build_objective_data (客观维度级格式数据)",
        [
            "scripts/build_objective_data.py",
            "--stats", str(stats_json),
            "--skill-root", str(ctx.target_skill),
            "--out", str(ctx.quality_results_dir / "objective_data.json"),
        ],
        fatal=False,
    )

    tpl = SKILL_DIR / "assets" / "report.template.md"
    vargs = [
        "scripts/validate_quality_report.py",
        "--objective", str(ctx.quality_results_dir / "objective_data.json"),
        "--quality-score-out", str(ctx.quality_score_out),
    ]
    if tpl.is_file():
        vargs += ["--template", str(tpl)]
    plan = ctx.quality_results_dir / f"{ctx.skill_name}_eval_plan.md"
    if plan.is_file():
        vargs += ["--plan", str(plan)]
    # 0A 客观数据门禁：此前与 bash 版一样用「失败即忽略」（fatal=False / `|| true`），
    # 校验器的报错被**完全吞掉**，门禁形同虚设。
    # 收尾版策略：**可见但不阻断** —— 非 0 退出时把 errors 逐条打印出来，让执行方与
    # 读者看见问题；暂不中断流水线。理由：首次真正生效的门禁可能拦下历史遗留的客观数据
    # 瑕疵，导致整轮中断；先观察一轮真实报错量，再评估是否升级为阻断。
    _echo("")
    _echo("▶ [开始阶段] 0/b validate_quality_report (0A 客观数据门禁)")
    _gate = subprocess.run([PY] + vargs, cwd=str(SKILL_DIR),
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
    if _gate.returncode != 0:
        _gate_errs: list[str] = []
        try:
            _gj = json.loads(_gate.stdout or "{}")
            _gate_errs = [str(x) for x in (_gj.get("errors") or [])]
        except (ValueError, TypeError):
            _gate_errs = []
        if not _gate_errs:
            _gate_errs = [(_gate.stderr or _gate.stdout or "").strip()[:400] or "（无详情）"]
        _echo("⚠️ [0A 门禁] 客观数据校验未通过（**当前不阻断**，仅提示）：", err=True)
        for _e in _gate_errs[:10]:
            _echo(f"   ✗ {_e}", err=True)
        _echo("   上述问题已记录于 quality/results/；待评估后决定是否升级为阻断门禁。", err=True)
    else:
        # 成功时也要可见：否则执行方无从判断门禁是否真的跑过
        # （v16 实证：执行方在日志里写「validate_quality_report 不再输出 JSON，可能已移除或静默」）
        _echo("   ✅ 0A 门禁通过（客观数据校验无阻断项）")

    # ---- 阶段 0B 可用性预检 ----
    # 注：0B 探测用【临时预检 manifest】承载 external_deps，绝不写正式 benchmark_manifest.json
    # （正式 manifest 是阶段 1 产物，避免 start 模式污染导致后续 full/resume 误判"样本已存在"）。
    ctx.sample_dir.mkdir(parents=True, exist_ok=True)
    preflight_manifest = ctx.sample_dir / "_preflight_manifest.json"
    run_step(
        "[开始阶段] 0B/1 extract_deps (依赖提取)",
        [
            "scripts/extract_deps.py",
            "--skill-dir", str(ctx.target_skill),
            "--manifest", str(preflight_manifest),
            "--output", str(ctx.sample_dir / "dependency_extract.json"),
            "--write-manifest",
        ],
    )

    dep_probe_json = ctx.sample_dir / "dependency_probe.json"
    run_step(
        "[开始阶段] 0B/2 dep_probe (外部依赖可用性探测)",
        [
            "scripts/dep_probe.py",
            "--manifest", str(preflight_manifest),
            "--output", str(dep_probe_json),
        ],
    )

    if dep_probe_json.is_file():
        run_step(
            "[开始阶段] 0B/3 合并可用性客观数据 → objective_data.json",
            [
                "scripts/build_objective_data.py",
                "--stats", str(stats_json),
                "--probe", str(dep_probe_json),
                "--skill-root", str(ctx.target_skill),
                "--out", str(ctx.quality_results_dir / "objective_data.json"),
            ],
        )

    if dep_probe_json.is_file():
        if _load_json(dep_probe_json).get("blocking"):
            _echo("⛔ [开始阶段] 0B 可用性探测发现被测技能契约型结构性缺陷（技能自身问题），"
                  "按预检闸门拦截：中止后续阶段 1–4。", err=True)
            _echo(f"   客观数据已落盘：{ctx.quality_results_dir / 'objective_data.json'}", err=True)
            _echo(f"   开始阶段报告已落盘：{ctx.quality_report}", err=True)
            sys.exit(1)

    # ---- 主观维度 / P7 裁定检查点 ----
    subj_json = ctx.quality_results_dir / "subjective.json"
    if not subj_json.is_file():
        _echo("  ⚠ 未检测到 subjective.json（AI 未回填主观维度），自动生成 advisory 复核提示（非裁定）")
        run_step(
            "[开始阶段] auto_subjective (生成待裁定骨架)",
            [
                "scripts/auto_subjective.py",
                "--stats", str(stats_json),
                "--template", str(tpl),
                "--probe", str(dep_probe_json) if dep_probe_json.is_file() else "",
                "--skill-root", str(ctx.target_skill),
                "--out", str(subj_json),
            ],
            fatal=False,
        )
        # ── P7：AI 裁定检查点 ──────────────────────────────────────────────
        # 主观维度（含功能表的服务场景归纳）本质是**语义判断**，不可脚本化：
        # 脚本自动填充等同于编造结论（违反不臆造纪律），故必须由 AI 裁定。
        _write_pending_list(subj_json, ctx.quality_results_dir / "PENDING_AI_ADJUDICATION.md")
        _echo("  ℹ 主观维度需 AI 语义裁定（不可脚本化）；未裁定维度在报告中标注「待 AI 归纳」", err=True)

    # ---- 阶段 0C：自动抽取「被测技能用户功能清单」 ----
    gen_ft = ctx.sample_dir / "functional_tasks.generated.jsonl"
    if run_step(
        f"[开始阶段] 0/c+ extract_functional_tasks (自动抽取用户功能清单 → {gen_ft})",
        [
            "scripts/extract_functional_tasks.py",
            "--skill-dir", str(ctx.target_skill),
            "--out", str(gen_ft),
        ],
        fatal=False,
    ) != 0:
        _echo("⛔ 阶段0C 抽取用户功能清单失败。", err=True)
        _echo("   说明：走到此处意味着命中通用占位反模式（E27）等真实违规，"
              "按纪律闸门拦截：中止后续阶段 1–4。", err=True)
        _echo("   注意：兜底抽空**不再是失败**（ERR-018 治本）——脚本会写空清单并返回 0，", err=True)
        _echo("   功能维度不适用（报告 §4 会明确标注），安全/质量维度照常评测。", err=True)
        sys.exit(1)

    run_step(
        "[开始阶段] 0/c 渲染质量评测报告 (merge)",
        [
            "scripts/merge_report_data.py",
            "--objective", str(ctx.quality_results_dir / "objective_data.json"),
            "--subjective", str(subj_json),
            "--template", str(tpl),
            "--functional-tasks", str(gen_ft),
            "--out", str(ctx.quality_results_dir / "report_data.json"),
        ],
    )
    run_step(
        "[开始阶段] 0/c 渲染质量评测报告 (render)",
        [
            "scripts/render_report.py",
            "--data", str(ctx.quality_results_dir / "report_data.json"),
            "--template", str(tpl),
            "--skill-name", ctx.skill_name,
            "--out", str(ctx.quality_report),
        ],
    )
    if not ctx.quality_report.is_file():
        _echo(f"❌ 开始阶段评测报告未生成：{ctx.quality_report}", err=True)
        sys.exit(1)
    _echo(f"  ✔ 已开始阶段评测报告：{ctx.quality_report}")


def _write_pending_list(subj_path: Path, out_path: Path) -> None:
    """生成 PENDING_AI_ADJUDICATION.md（原 bash heredoc 片段的原生实现）。"""
    data = _load_json(subj_path)
    pending = [(n, v) for n, v in data.items() if isinstance(v, dict) and v.get("skipped")]
    lines = [
        "# 待 AI 裁定清单（P7）", "",
        "> 以下主观维度需 **AI 语义裁定**后写入 `subjective.json`。",
        "> 脚本只提供客观线索与依据材料，**不代为裁定**（自动填充等同编造结论）。",
        "> 功能表（function_table）须归纳**服务场景**（技能为用户做什么），",
        "> 依据层次：①frontmatter description → ②When to Use → ③过程中的服务声明；",
        "> 注意 `--mode start` 这类是**触发方式**，不是服务名。",
        "> **F6（依据标注）**：功能表每条必须注明可定位出处 —— `SKILL.md:<行号>` 或",
        "> `SKILL.md §<章节名>`；不得写「全文」「参见文档」。无出处将被",
        "> `validate_function_table.py` 判违规并阻断（归纳不可回溯即等同臆造）。", "",
        f"待裁定维度共 **{len(pending)}** 个：", "",
    ]
    for name, v in pending:
        lines.append(f"## `{name}`")
        for ln in str(v.get("skip_reason") or "").strip().splitlines():
            lines.append(f"> {ln}" if ln.strip() else ">")
        lines.append("")
    lines += [
        "---", "", "## 填写后如何生效", "",
        "裁定完成并写入 `subjective.json` 后，重跑合并与渲染即可（无需重跑评测）：", "",
        "```bash",
        "python scripts/merge_report_data.py \\",
        "  --objective <RESULTS>/quality/results/objective_data.json \\",
        "  --subjective <RESULTS>/quality/results/subjective.json \\",
        "  --template assets/report.template.md \\",
        "  --functional-tasks <RESULTS>/sample/functional_tasks.generated.jsonl \\",
        "  --out <RESULTS>/quality/results/report_data.json",
        "python scripts/render_report.py \\",
        "  --data <RESULTS>/quality/results/report_data.json \\",
        "  --template assets/report.template.md \\",
        "  --out <RESULTS>/quality/quality_report.md",
        "```",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _echo(f"  📋 待裁定清单已生成：{out_path}（{len(pending)} 个主观维度待 AI 裁定）")


# ============================================================
# 阶段 1 · 脚手架生成
# ============================================================
def run_scaffold(ctx: Ctx) -> None:
    if not ctx.scaffold_spec:
        return

    # ── 攻击面打标（阶段 1.5-A，强制，封死漏测）──
    # 无论是否显式传 --security-spec，都先对被测技能客观产物打标（通用扫描，不绑定技能）。
    # 这是安全维度的唯一开关：skill_surface_tags 非空 → 必须由下游生成对应探针。
    surface_out = ctx.quality_dir / "results" / "surface_tags.json"
    run_step(
        f"[阶段1.5-A] 攻击面打标 (surface_tagging --skill-dir {ctx.target_skill})",
        ["scripts/surface_tagging.py", "--skill-dir", str(ctx.target_skill), "--output", str(surface_out)],
    )

    surface_args: list[str] = []
    n_tags = len(_load_json(surface_out).get("skill_surface_tags") or []) if surface_out.is_file() else 0
    _echo(f"    攻击面命中标签数: {n_tags}")
    if n_tags > 0:
        surface_args = ["--surface-tags", str(surface_out)]

    if n_tags > 0 and not ctx.security_spec:
        auto_sec = ctx.quality_dir / "results" / "auto_security_spec.json"
        run_step(
            "[阶段1.5-B] 自动生成安全探测声明 (按攻击面映射 ASI)",
            [
                "scripts/auto_security_spec.py",
                "--surface-tags", str(surface_out),
                "--out", str(auto_sec),
                "--sample-root", str(ctx.sample_dir),
            ],
            fatal=False,
        )
        if auto_sec.is_file():
            ctx.security_spec = str(auto_sec)

    bsp_args = [
        "scripts/build_sample_pack.py",
        "--skill-name", ctx.skill_name,
        "--skill-dir", str(ctx.target_skill),
        "--functional-tasks", ctx.scaffold_spec,
        "--out", str(ctx.sample_dir),
    ]
    if ctx.security_spec:
        bsp_args += ["--security-spec", ctx.security_spec]
    bsp_args += surface_args
    run_step(
        f"[阶段1] 生成样本脚手架 (build_sample_pack --functional-tasks {ctx.scaffold_spec})",
        bsp_args,
    )


# ============================================================
# 执行产物预检（防静默 skip 全 0 分）
# ============================================================
def check_exec_artifacts(ctx: Ctx, manifest: Path) -> bool:
    if not manifest.is_file():
        _echo(f"❌ 预检失败：manifest 不存在 {manifest}", err=True)
        return False
    m = _load_json(manifest)
    missing: list[str] = []
    for t in m.get("functional_tasks") or []:
        tid = t.get("id", "?")
        for mode in ("baseline", "with_skill"):
            rd = ctx.exec_dir / mode / "tasks" / tid / "results"
            if not rd.is_dir():
                missing.append(f"functional/{mode}/{tid}  (缺 {rd})")
    for s in m.get("security_probes") or []:
        sid = s.get("id", "?")
        rd = ctx.exec_dir / "security" / "probes" / sid / "results"
        if not (rd / "grading_result.json").exists():
            missing.append(f"security/{sid}  (缺 {rd}/grading_result.json)")
    if missing:
        _echo("❌ 执行产物预检失败：以下任务尚未由 ExecAgent/SpecAgent 执行并落盘：", err=True)
        for x in missing:
            _echo(f"   - {x}", err=True)
        _echo(f"共缺失 {len(missing)} 项。请先按 references/exec_common.md 驱动被测技能执行各任务，", err=True)
        _echo("再重跑本管线（或加 --skip-exec-check 仅校验样本）。", err=True)
        return False
    _echo(f"✅ 执行产物预检通过：functional={len(m.get('functional_tasks') or [])} 项 × 2 模式, "
          f"security={len(m.get('security_probes') or [])} 项，结果齐全")
    return True


# ============================================================
# 阶段 4 · 最后阶段聚合
# ============================================================
def run_stage4(ctx: Ctx) -> None:
    ctx.exec_dir.mkdir(parents=True, exist_ok=True)
    ctx.spec_dir.mkdir(parents=True, exist_ok=True)
    (ctx.spec_dir / "results").mkdir(parents=True, exist_ok=True)

    manifest = ctx.sample_dir / "benchmark_manifest.json"
    if not manifest.is_file():
        _echo(f"❌ 进入最后阶段失败：缺样本清单 {manifest}（阶段1产物）。", err=True)
        _echo("   ▶ AI 评测执行者需按 references/stage1_sample.md 设计样本任务，", err=True)
        _echo("     并用 --scaffold-spec 生成脚手架，或运行 build_sample_pack.py 产出该 manifest。", err=True)
        sys.exit(1)

    run_step(
        "[阶段1] validate_manifest_contract (样本契约守卫)",
        ["scripts/validate_manifest_contract.py", "--manifest", str(manifest)],
    )

    if ctx.skip_exec_check:
        _echo("⚠️ 已 --skip-exec-check：跳过执行产物预检（仅校验样本，不保证已实测）")
    else:
        if not check_exec_artifacts(ctx, manifest):
            _echo("▶ 检测到执行产物缺失，自动驱动执行（ExecAgent/SpecAgent 职责，流程内完成）")
            for mode in ("baseline", "with_skill"):
                run_step(
                    f"[阶段2/3] exec_functional_tasks ({mode})",
                    [
                        "scripts/exec_functional_tasks.py",
                        "--mode", mode,
                        "--manifest", str(manifest),
                        "--exec-root", str(ctx.exec_dir),
                        "--skill-name", ctx.skill_name,
                        "--sample-root", str(ctx.sample_dir),
                        "--skill-dir", str(ctx.target_skill),
                    ],
                )
            run_step(
                "[阶段5] exec_security_evidence (真实对抗证据采集)",
                [
                    "scripts/exec_security_evidence.py",
                    "--sample-root", str(ctx.sample_dir),
                    "--exec-root", str(ctx.exec_dir),
                    "--manifest", str(manifest),
                    "--spec-root", str(ctx.spec_dir),
                ],
            )
            run_step(
                "[阶段5] exec_security_probes (安全探测评分)",
                [
                    "scripts/exec_security_probes.py",
                    "--sample-root", str(ctx.sample_dir),
                    "--exec-root", str(ctx.exec_dir),
                    "--spec-root", str(ctx.spec_dir),
                ],
            )
        if not check_exec_artifacts(ctx, manifest):
            _echo("", err=True)
            _echo("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", err=True)
            _echo(" ✖ 自动执行后执行产物仍缺失（真实失败，非预期等待）：", err=True)
            _echo("   阶段 2/3/5 已自动真实驱动被测技能；产物仍不全，说明被测技能当前不可达", err=True)
            _echo("   或执行异常（详见上方各 run_step 的报错日志）。", err=True)
            _echo("   排查后可重跑：python scripts/run_pipeline.py --mode resume", err=True)
            _echo("   （或仅校验样本不实测：--skip-exec-check，但不保证结果可信）", err=True)
            _echo("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", err=True)
            sys.exit(1)

    tasks_json = ctx.spec_dir / "results" / "Tasks.json"
    run_step(
        "1/6 generate_tasks_json",
        [
            "scripts/generate_tasks_json.py",
            "--sample-dir", str(ctx.sample_dir),
            "--exec-dir", str(ctx.exec_dir),
            "--spec-dir", str(ctx.spec_dir),
            "--skill-dir", str(ctx.target_skill),
            "--output", str(tasks_json),
        ],
    )
    run_step(
        "2/6 backfill_reviews",
        [
            "scripts/backfill_reviews.py",
            "--tasks-json", str(tasks_json),
            "--sample-dir", str(ctx.sample_dir),
            "--exec-dir", str(ctx.exec_dir),
            "--spec-dir", str(ctx.spec_dir),
        ],
    )

    cacu_cmd = [
        "scripts/cacu_total_score.py",
        "--tasks-json", str(tasks_json),
        "--output", str(ctx.spec_dir / "scores.json"),
        "--project-state", ctx.project_state or "production",
    ]
    if ctx.quality_score_out.is_file():
        qs = _load_json(ctx.quality_score_out).get("quality_score", "")
        if qs:
            cacu_cmd += ["--quality-score", str(qs)]
    run_step("3/6 cacu_total_score", cacu_cmd)

    run_step(
        "4/6 generate_outputs",
        [
            "scripts/generate_outputs.py",
            "--spec-dir", str(ctx.spec_dir),
            "--sample-dir", str(ctx.sample_dir),
            "--exec-dir", str(ctx.exec_dir),
            "--skill-dir", str(ctx.target_skill),
        ],
    )
    run_step(
        "5/6 安全 verify + assemble (run_security_pipeline)",
        ["scripts/run_security_pipeline.py", "--root", str(ctx.results_root)],
    )
    run_step(
        "6/6 validate_output",
        [
            "scripts/validate_output.py",
            "--template-json", "assets/Template.json",
            "--template-csv", "assets/Template.csv",
            "--output-json", str(ctx.spec_dir / "results" / "Template.json"),
            "--output-csv", str(ctx.spec_dir / "results" / "Template.csv"),
        ],
    )

    af_args = [
        "scripts/assemble_findings.py",
        "--verified-findings", str(ctx.spec_dir / "results" / "security" / "probes"),
        "--manifest", str(manifest),
        "--functional-grading", str(ctx.exec_dir),
        "--tasks-json", str(tasks_json),
    ]
    if ctx.quality_report.is_file():
        af_args += ["--quality-report", str(ctx.quality_report)]
    af_args += ["--project-state", ctx.project_state or "production",
                "--report-md", str(ctx.spec_dir / "problem_report.md")]
    run_step("7/6 聚合问题报告 (assemble_findings)", af_args)

    _echo("")
    _echo("==================================================")
    _echo(" ✅ 全部阶段完成（进度 5/5）——交付物清单")
    _echo("")
    _echo(" 【最终交付物】")
    _echo(f"   • 质量评测报告：{ctx.quality_report}")
    _echo(f"   • 基准评测报告：{ctx.spec_dir / 'benchmark_report.md'}")
    _echo(f"   • 问题改进报告：{ctx.spec_dir / 'problem_report.md'}")
    _echo(f"   • 机器可读评分：{ctx.spec_dir / 'scores.json'}")
    _echo("")
    _echo(" 【阶段卡点产物（流程逐级执行的证明）】")
    _echo(f"   • 阶段 0 预检：{ctx.quality_dir}/")
    _echo(f"   • 阶段 1 样本：{ctx.sample_dir}/")
    _echo(f"   • 阶段 2/3 执行：{ctx.exec_dir}/")
    _echo(f"   • 阶段 4 聚合：{ctx.spec_dir}/")
    _echo("==================================================")

    # ── 产物断言：阶段卡点缺失即显式标注流程未完整执行 ──
    missing_stage = []
    if not ctx.quality_report.is_file():
        missing_stage.append(f"阶段0 质量评测报告（{ctx.quality_report}）")
    if not ctx.sample_dir.is_dir():
        missing_stage.append(f"阶段1 样本目录（{ctx.sample_dir}）")
    if not ctx.exec_dir.is_dir():
        missing_stage.append(f"阶段2/3 执行目录（{ctx.exec_dir}）")
    if not (ctx.spec_dir / "benchmark_report.md").is_file():
        missing_stage.append(f"阶段4 基准报告（{ctx.spec_dir / 'benchmark_report.md'}）")
    if not (ctx.spec_dir / "problem_report.md").is_file():
        missing_stage.append(f"阶段4 问题报告（{ctx.spec_dir / 'problem_report.md'}）")
    if missing_stage:
        _echo("")
        _echo("⚠️ 流程未完整执行——下列阶段卡点产物缺失：")
        for m in missing_stage:
            _echo(f"   ✗ {m}")
        _echo("   存在缺失即不得视为评测完成；请补齐缺失阶段后重跑本节。")

    # ── AI 评测执行者完成清单（ERR-014：管线跑通 ≠ 评测完成）──
    _echo("")
    _echo("📋 AI 评测执行者完成清单（交付前逐项自查，全部通过才算评测完成）：")
    _echo("   1. 主观维度裁定：PENDING_AI_ADJUDICATION.md 各维度经 AI 裁定写入 subjective.json，重跑 merge+render")
    _echo(f"   2. 功能表校验：python scripts/validate_function_table.py --report '{ctx.quality_report}' "
          f"--skill-dir '{ctx.target_skill}' 通过")
    _echo("   3. 交叉对应：质量报告功能表 ↔ benchmark §4 条目应可对应（可测子集关系），口径差异须在报告中有说明")
    _echo("   4. 产物新鲜：两份报告时间戳均为本轮（防旧产物当新结果，ERR-001）")
    _echo("   —— 缺任何一项即未完成，不得向用户交付")

    # ---- R13：把清单第 1 项升级为**机器门禁** ----
    # 此前它只是一行文本提示：缺裁定照样打印「✅ 完成」并自动接续阶段 1–4，
    # 导致「主观槽位全空」的报告被当成成品交付（v4 实证）。
    # 逃生阀：确需跑通流水线（如框架调研）时显式追加 --skip-subjective-gate。
    dod = SKILL_DIR / "scripts" / "check_stage0_dod.py"
    if not ctx.skip_subj_gate and dod.is_file():
        _echo("")
        _echo("▶ [阶段0 DoD] 检查主观维度是否已裁定（R13 机器门禁）")
        rc = subprocess.run(
            [PY, str(dod),
             "--data", str(ctx.quality_results_dir / "report_data.json"),
             "--template", str(SKILL_DIR / "assets" / "report.template.md")],
            cwd=str(SKILL_DIR),
        ).returncode
        if rc == 0:
            _echo("   ✅ 主观维度已裁定，DoD 通过")
        else:
            _echo("", err=True)
            _echo("⛔ [阶段0 DoD 未满足] 存在未裁定的主观槽位 —— 阶段 0 未完成。", err=True)
            _echo("   按项目纪律：不得宣告阶段完成、不得提示查看成品报告、不得进入下一阶段。", err=True)
            _echo("   请依据 quality/results/subjective.json 的 skip_reason 材料补做 AI 裁定后重跑。", err=True)
            _echo("   确需跳过本门禁（仅建议框架调研场景）：追加 --skip-subjective-gate。", err=True)
            sys.exit(1)


# ============================================================
# 入口
# ============================================================
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_pipeline.py",
        description="skill-evaluator 评测管线 runner（跨平台 Python 版，等价替代 run_eval_pipeline.sh）",
    )
    p.add_argument("--skill-dir", default=os.environ.get("TARGET_SKILL", str(SKILL_DIR)),
                   help="被测技能目录（默认：本评测技能自身）")
    p.add_argument("--results-root", default=os.environ.get("RESULTS_ROOT", EVAL_RESULTS_BASE),
                   help="评测结果根目录（**不含技能名与版本**；下按 <技能名>/<运行标识> 两级组织）")
    p.add_argument("--run-id", default=os.environ.get("RUN_ID", ""),
                   help="本次运行标识（如 v17、2026-09-22-fix）；默认时间戳，保证不覆盖历史")
    p.add_argument("--scaffold-spec", default=os.environ.get("SCAFFOLD_SPEC", ""),
                   help="functional_tasks JSONL（build_sample_pack 主输入）")
    p.add_argument("--security-spec", default=os.environ.get("SECURITY_SPEC", ""),
                   help="安全探测声明 JSON（可选）")
    p.add_argument("--mode", default=os.environ.get("MODE", "full"), choices=["start", "full", "resume"])
    p.add_argument("--reset", action="store_true", help="显式清空工作区（full/start 本就默认清空）")
    p.add_argument("--skip-subjective-gate", action="store_true",
                   help="逃生阀：跳过阶段0「主观已裁定」门禁")
    p.add_argument("--skip-exec-check", action="store_true", help="跳过执行产物预检（仅校验样本，CI 用）")
    p.add_argument("--project-state", default=os.environ.get("PROJECT_STATE", ""), help="debug|production")
    return p


def main() -> int:
    args = build_parser().parse_args()
    ctx = Ctx(args)

    # 防误用守卫：默认被测技能指向自身时醒目提示
    if ctx.target_skill == SKILL_DIR and "--skill-dir" not in sys.argv:
        _echo(f"⚠️ 注意：未显式传入 --skill-dir，默认被测技能 = 本评测技能自身（{SKILL_DIR}）。", err=True)
        _echo("   若你要评测【其他技能】，请加：--skill-dir <被测技能目录>。", err=True)
        _echo("   确认评测自身请忽略此提示（调试态自测场景）。", err=True)

    if not ctx.target_skill.is_dir():
        _echo(f"❌ 被测技能目录不存在: {ctx.target_skill}", err=True)
        return 1

    # 运行状态自动判定
    if not ctx.project_state:
        try:
            out = subprocess.run([PY, str(SKILL_DIR / "scripts" / "_project_state.py")],
                                 cwd=str(SKILL_DIR), capture_output=True, text=True)
            ctx.project_state = (out.stdout or "").strip() or "production"
        except (OSError, subprocess.SubprocessError):
            ctx.project_state = "production"
    _echo(f"▶ 运行状态：{ctx.project_state}"
          f"（{'调试态 · 以项目方式打开' if ctx.project_state == 'debug' else '发布态 · 安装为技能'}）")

    ctx.results_root.mkdir(parents=True, exist_ok=True)

    # ---- R11：默认清空本次被测技能的子目录 ----
    # 实证：同一会话内重跑（如更新技能包后）会让新旧产物并存于不同层级，
    # 且由**不同版本**技能生成，造成「同一评测两份结论」的严重混淆。
    # 例外：resume 依赖已有阶段 0 产物，不得清空。
    if ctx.mode != "resume" or args.reset:
        _echo(f"▶ 清空本次评测对象的工作区子目录 {ctx.ws}（R11 默认清空；仅本技能子目录）")
        _echo(f"   （仅清 {ctx.skill_name} 一个子目录；RESULTS_ROOT 下其他技能的评测结果**保留**）")
        shutil.rmtree(ctx.ws, ignore_errors=True)
    else:
        _echo(f"▶ resume 模式：保留既有阶段 0 产物，不清空 {ctx.ws}")

    # ── 写 LATEST.json 指针 ──
    # 运行目录名在省略 --run-id 时是时间戳（如 20260922-153500），对下游消费者
    # （尤其 skill-doctor 这类**自动读取最新评测结果**的姊妹项目）不可预测。
    # 故在技能目录下留一个指针文件，明确给出最近一次运行的各报告绝对路径。
    try:
        _latest = ctx.results_root / ctx.skill_name / "LATEST.json"
        _latest.parent.mkdir(parents=True, exist_ok=True)
        _latest.write_text(json.dumps({
            "skill_name": ctx.skill_name,
            "run_id": ctx.run_id,
            "workspace": str(ctx.ws),
            "quality_report": str(ctx.quality_report),
            "benchmark_report": str(ctx.spec_dir / "benchmark_report.md"),
            "problem_report": str(ctx.spec_dir / "problem_report.md"),
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _echo(f"▶ 本次运行标识：{ctx.run_id} → {ctx.ws}")
        _echo(f"   最新结果指针：{_latest}")
    except OSError as _e:
        _echo(f"   ⚠ LATEST.json 写入失败（不影响主流程）: {_e}")

    _echo("==================================================")
    _echo(" skill-evaluator 评测管线（单点授权运行 · Python 版）")
    _echo("--------------------------------------------------")
    _echo(" 本次授权即确认以下《范围与安全契约》：")
    _echo(f"   • 只读被测技能 : {ctx.target_skill} （不修改/不删除）")
    _echo(f"   • 仅写评测工作区: {ctx.results_root} （sample/exec/spec/quality）")
    _echo("   • 仅运行本 skill 自带脚本 + 被测技能自身")
    _echo("   • 不联网 / 不删用户文件 / 不改系统配置或凭据")
    _echo("   • 不写工作区外、不写被测技能目录")
    _echo(f"   • 运行模式 --mode={ctx.mode}   解释器: {PY}")
    _echo("   任何越界操作将被拒绝并报告")
    _echo("==================================================")

    gen_ft = ctx.sample_dir / "functional_tasks.generated.jsonl"

    if ctx.mode == "start":
        run_stage0(ctx)
        _echo("")
        _echo("==================================================")
        _echo(" ✅ 开始阶段测评完成（进度 1/5：本次仅完成阶段 0 预检，阶段 1→4 尚未执行）")
        _echo(f"   报告位置: {ctx.quality_report}")
        _echo("")
        _echo(" ▶ 下一步（继续全流程，补全阶段 1→4）：")
        _echo(f"   python scripts/run_pipeline.py --mode resume --skill-dir '{ctx.target_skill}'")
        _echo("   注：若你要的是「全面 / 全流程评测」，直接改用 --mode full 即可一路跑至阶段 4，无需在此停顿。")
        _echo("==================================================")
        return 0

    if ctx.mode == "full":
        run_stage0(ctx)
        if not ctx.scaffold_spec and not (ctx.sample_dir / "benchmark_manifest.json").is_file():
            if gen_ft.is_file():
                _echo(f"▶ [阶段1] 未提供 --scaffold-spec，自动使用阶段0C产出的用户功能清单：{gen_ft}")
                ctx.scaffold_spec = str(gen_ft)
            else:
                _echo(f"⛔ 未提供 --scaffold-spec，且阶段0C未产出用户功能清单 {gen_ft}。", err=True)
                _echo("   阶段0C 应在 run_stage0 内自动抽取被测技能用户功能；"
                      "若失败通常因 SKILL.md 缺用户功能区/路由表。", err=True)
                _echo("   请先以 --mode start 单独跑阶段0确认抽取成功，再重跑 full。", err=True)
                return 1
        run_scaffold(ctx)
        run_stage4(ctx)
        if not (ctx.spec_dir / "benchmark_report.md").is_file() or not (ctx.spec_dir / "problem_report.md").is_file():
            _echo("⛔ 全流程未产出最终报告 —— 评测未完成，不得按成功交付。", err=True)
            _echo(f"   缺失产物：{ctx.spec_dir / 'benchmark_report.md'} 与/或 {ctx.spec_dir / 'problem_report.md'}", err=True)
            _echo("   请先看上述「AI 评测执行者接续指引」补齐阶段 2/3，再运行：", err=True)
            _echo(f"     python scripts/run_pipeline.py --mode resume --skill-dir '{ctx.target_skill}'", err=True)
            return 1
        _echo("")
        _echo("==================================================")
        _echo(" ✅ 全流程测评完成（阶段 1→4 已执行）。")
        _echo("   • 交付物清单见上方「阶段卡点产物」段（含各产物绝对路径）")
        _echo(f"   • 开始阶段报告: {ctx.quality_report}")
        _echo("==================================================")
        return 0

    # resume
    if not ctx.quality_report.is_file():
        _echo(f"⚠️ 未检测到开始阶段报告 {ctx.quality_report}，是否先跑开始阶段？", err=True)
        _echo("   如需先补开始阶段：python scripts/run_pipeline.py --mode start", err=True)
    if not ctx.scaffold_spec and not (ctx.sample_dir / "benchmark_manifest.json").is_file():
        if not gen_ft.is_file():
            _echo("▶ [阶段1] 未找到阶段0C产物，补跑 extract_functional_tasks")
            run_step("补跑 extract_functional_tasks", [
                "scripts/extract_functional_tasks.py",
                "--skill-dir", str(ctx.target_skill),
                "--out", str(gen_ft),
            ])
        if gen_ft.is_file():
            _echo(f"▶ [阶段1] 自动使用阶段0C产出的用户功能清单：{gen_ft}")
            ctx.scaffold_spec = str(gen_ft)
        else:
            _echo(f"⛔ 未提供 --scaffold-spec，且无法产出用户功能清单 {gen_ft}。", err=True)
            return 1
    run_scaffold(ctx)
    run_stage4(ctx)
    return 0


if __name__ == "__main__":
    sys.exit(main())
