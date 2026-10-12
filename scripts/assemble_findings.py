#!/usr/bin/env python3
"""聚合已核实的 findings → 双报告（problem_report.md + problems.csv）。

设计目标（双报告结构）：
  - `verify_findings.py` 逐探针产出 `verified_findings.json`（JSON 数组，每条含
    verified / verification_notes / rule_severity / llm_reviewed 等字段）。
  - 本脚本把这些分散的核实结果**聚合成基准级问题报告**，并把「已确认问题」
    与「未核实 / 待 LLM 复核」**显式分层**——未核实项不计入确认问题数，
    仅作为附录标注，避免淹没真相（诚实边界，见 §8）。

输入：
  --verified-findings  可重复。每个可以是：
      · 单个 verified_findings.json 文件
      · 一个目录（递归扫描其中所有 verified_findings.json）
    默认：扫描 {SPEC_SECURITY_DIR}probes 下所有 verified_findings.json
  --manifest           可选，benchmark_manifest.json（用于补全探针的
                       asi_category / security_group 元数据，若 findings 缺字段）
  --report-md          输出 problem_report.md 路径
  --report-csv         输出 problems.csv 路径
  --quality-report     可选，quality_report.md 路径；提供则 problem_report.md 增加「四、质量评估（PreflightAgent）」章节
  --functional-grading 可选，功能任务 grading_result.json 文件或目录（可重复）；把 passed=false 的
                       rubric 提取为「二、功能任务问题」节（与门禁报告 benchmark_report.md 同源、不重复算分）
  --summary-json       可选，输出聚合统计 JSON 路径

输出：
  1) problem_report.md  —— 人读报告：分层（已确认 / 未核实 / 边界）+ 统计
  2) problems.csv       —— 机读：每条 finding 一行，字段齐全

用法：
  python3 scripts/assemble_findings.py \
      --verified-findings {RESULTS_ROOT}/<skill-name>/spec/results/security/probes \
      --manifest         {RESULTS_ROOT}/<skill-name>/sample/benchmark_manifest.json \
      --report-md       {RESULTS_ROOT}/<skill-name>/spec/problem_report.md \
      --report-csv      {RESULTS_ROOT}/<skill-name>/spec/problems.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

# 严重度排序（高 → 低）
SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "warning": 3, "info": 4, "unknown": 5}  # noqa


def _load_one(path: Path) -> List[dict]:
    """读取一个 verified_findings 文件，归一化为 list[dict]。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    if isinstance(data, dict) and "findings" in data:
        return [d for d in data["findings"] if isinstance(d, dict)]
    return []


def collect_inputs(paths: List[str]) -> List[dict]:
    """把 --verified-findings 的多个文件/目录展开并合并为 findings 列表。"""
    findings: List[dict] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            for f in sorted(p.rglob("verified_findings.json")):
                findings.extend(_load_one(f))
        elif p.is_file():
            findings.extend(_load_one(p))
    return findings


def _infer_mode(gf: Path) -> str:
    """从 grading_result.json 路径推断运行模式：.../exec/{mode}/tasks/{tid}/results/..."""
    parts = gf.parts
    if "exec" in parts:
        i = parts.index("exec")
        if i + 1 < len(parts):
            return parts[i + 1]
    return "unknown"


def _infer_task_id(gf: Path) -> str:
    """从 grading_result.json 路径推断 task_id：.../tasks/{tid}/results/..."""
    parts = gf.parts
    if "tasks" in parts:
        i = parts.index("tasks")
        if i + 1 < len(parts):
            return parts[i + 1]
    return gf.stem


def collect_functional(inputs: List[str]) -> List[dict]:
    """从功能任务 grading_result.json 提取 `passed=false` 的 rubric → 同结构 Finding。

    `grading_result.json` 结构：{task_id, results:[{rubric_id, passed, reason, evidence}]}。
    每条失败 rubric 派生一条 eval_type=functional 的 Finding，finding_id = {task_id}@{mode}#{rubric}。
    """
    findings: List[dict] = []
    for raw in inputs:
        p = Path(raw)
        files: List[Path] = []
        if p.is_dir():
            files = sorted(p.rglob("grading_result.json"))
        elif p.is_file():
            files = [p]
        for gf in files:
            try:
                gr = json.loads(gf.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            task_id = gr.get("task_id") or _infer_task_id(gf)
            mode = _infer_mode(gf)

            # ── 区分「未真实执行」与「技能缺陷」────────────────────────────
            # 若同目录 result.json 表明任务未真实执行（status=unsupported，或 summary/notes
            # 含「未执行 / 无法自动确定」等评测侧限制说明），则该任务的失败 rubric 属
            # 「评测侧未实测」，**不是被测技能编写缺陷**，单列为 functional_untested，
            # 不进「已确认问题」，避免把评测过程问题伪装成技能问题。
            untested, untested_reason, untested_capability = _is_untested(gf)
            if untested:
                # 合并为一条结论：同一原因的 R1..R10 逐条罗列对读者没有意义，
                # 且会让「未验证」看起来像「10 项缺陷」。改为一条人话结论，
                # 读者一眼看懂「没测成 + 为什么 + 要不要管」。
                findings.append({
                    "finding_id": f"{task_id}@{mode}#untested",
                    "eval_type": "functional_untested",
                    "task_id": task_id,
                    "mode": mode,
                    "asi_category": "",
                    "security_group": "",
                    "evidence_field": "grading_result",
                    "rubric_id": "",
                    "rule_severity": "info",
                    "verified": False,
                    "llm_reviewed": False,
                    "content": (
                        f"（未完成验证，不计为技能缺陷）{untested_reason}"
                        f"；能力：{untested_capability or task_id}"
                    ),
                    "capability": untested_capability,
                    "evidence_strings": [],
                    "location": {
                        "task_id": task_id,
                        "mode": mode,
                        "skill_source": "",
                        "artifact": str(gf),
                    },
                })
                continue
            for r in gr.get("results", []):
                if r.get("passed", True):
                    continue
                rid = r.get("rubric_id")
                if not rid:
                    continue
                reason = r.get("reason", "")
                findings.append({
                    "finding_id": f"{task_id}@{mode}#{rid}",
                    "eval_type": "functional",
                    "task_id": task_id,
                    "mode": mode,
                    "asi_category": "",
                    "security_group": "",
                    "evidence_field": "grading_result",
                    "rubric_id": rid,
                    "rule_severity": "warning",
                    "verified": True,
                    "llm_reviewed": False,
                    "content": f"{rid} 未通过：{reason}",
                    "evidence_strings": [],
                    "location": {
                        "task_id": task_id,
                        "mode": mode,
                        "skill_source": "",
                        "artifact": str(gf),
                    },
                })
    return findings


_UNTESTED_MARKERS = ("未执行", "无法自动确定", "未伪造", "屏蔽态", "未真实执行")


def _is_untested(grading_path: Path) -> tuple[bool, str, str]:
    """判断该任务是否「未真实执行」（评测侧限制）。

    返回 (是否未实测, 未执行原因, 能力描述)。
    能力描述取自 result.json 的 objective（人话），用于在报告中解释任务编码是什么能力，
    避免只给 FTxx 编号让人看不懂。
    判定依据：result.json 的 status 为 unsupported / blocked / failed 且
    其 summary/notes 含评测侧限制说明（未执行 / 无法自动确定动态参数 / 屏蔽态等）。
    """
    rp = grading_path.parent / "result.json"
    if not rp.is_file():
        return False, "", ""
    try:
        res = json.loads(rp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, "", ""
    objective = str(res.get("objective", "") or "")
    status = str(res.get("status", "")).lower()

    # 「调用成功但未取到数据」：接口正常，只是数据源返回 0 条（或取值偏窄）。
    # 此时该能力**实际未被验证**——评测侧无法据此判定技能是否具备该能力，
    # 属「未完成验证」，不得伪装成技能缺陷：
    # 否则报告会把「查根因」的工作转嫁给读者，而读者看不到内部数据、做不到。
    items = res.get("items")
    if status == "success" and isinstance(items, list) and len(items) == 0:
        return True, (
            "接口调用成功，但数据源返回 0 条，本次未能验证该能力"
            "（调用本身正常，无数据属数据源侧；"
            "若同期其他数据源有内容，建议技能在此时回退其他来源）"
        ), objective

    if status not in ("unsupported", "blocked", "failed"):
        return False, "", objective
    blob = " ".join([
        str(res.get("summary", "")),
        " ".join(res.get("notes", []) or []),
    ])
    for marker in _UNTESTED_MARKERS:
        if marker in blob:
            return True, (res.get("summary") or f"评测侧限制：{marker}"), objective
    return False, "", objective


from _common import load_manifest_meta, add_project_state_arg


def enrich(fd: dict, meta: Dict[str, dict]) -> None:
    """用 manifest 元数据补全 findings 缺省的 asi_category / security_group。"""
    pid = (fd.get("location") or {}).get("probe_id") or fd.get("probe_id")
    if pid and pid in meta:
        if not fd.get("asi_category"):
            fd["asi_category"] = meta[pid].get("asi_category", "")
        if not fd.get("security_group"):
            fd["security_group"] = meta[pid].get("security_group", "")


def _manifest_functional_ids(manifest_path: str):
    """从 benchmark_manifest.json 取合法 functional task id 集合；无 manifest 返回 None（不过滤）。

    用途：排除 exec/ 下残留的孤儿/过期运行（如 C_02/C_03/H_01），只保留当前基准真正包含的用例。
    """
    if not manifest_path:
        return None
    p = Path(manifest_path)
    if not p.exists():
        return None
    try:
        m = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    ids = {t["id"] for t in m.get("functional_tasks", []) if t.get("id")}
    return ids or None


def asi_short(asi: str) -> str:
    """ASI03-Identity-and-Privilege-Abuse → ASI03。"""
    if not asi:
        return "—"
    return asi.split("-", 1)[0] if "-" in asi else asi


def fmt_list(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, list):
        return "; ".join(str(x) for x in v) if v else "—"
    return str(v)


def render_markdown(findings: List[dict], generated_at: str, quality_report: Optional[str] = None,
                    functional: Optional[List[dict]] = None, skill_name: str = "",
                    n_func_baseline: int = 0,
                    efficiency_degradations: Optional[List[dict]] = None,
                    incomparable_exclusions: Optional[List[dict]] = None,
                    functional_untested: Optional[List[dict]] = None,
                    project_state: str = "debug",
                    sample_dir: str = "") -> str:
    functional = functional or []
    functional_untested = functional_untested or []
    efficiency_degradations = efficiency_degradations or []
    incomparable_exclusions = incomparable_exclusions or []
    verified = [f for f in findings if f.get("verified")]
    unverified = [f for f in findings if not f.get("verified")]
    n_func = len(functional)
    func_task_counts: Dict[str, int] = {}
    for f in functional:
        t = (f.get("location") or {}).get("task_id", "?")
        func_task_counts[t] = func_task_counts.get(t, 0) + 1

    # ── 统计 ──
    total = len(findings)
    n_ver = len(verified)
    n_unver = len(unverified)
    n_eff = len(efficiency_degradations)
    n_excl = len(incomparable_exclusions)

    def sev_counts(items: List[dict]) -> Dict[str, int]:
        c: Dict[str, int] = {}
        for f in items:
            s = (f.get("rule_severity") or "unknown").lower()
            c[s] = c.get(s, 0) + 1
        return c

    ver_sev = sev_counts(verified)

    out: List[str] = []
    # R19：标题与另两份报告统一为「# <中文职能名>：<技能名>」——全角冒号、无英文副标题。
    # 原此处硬编码旧标题「# 问题报告（Problem Report）」，且本脚本为逐行拼接、**未读取模板**，
    # 导致 assets/problem_report.template.md 里的标题改动完全不生效（v4 实证）。
    # 技能名来源优先级（v11 实证修正）：
    #   1) 调用方显式传入的 skill_name（取自 manifest.skill_name，**最可靠**）
    #   2) 回退：从 quality_report 路径反推
    # 为何不能只靠路径反推：输出根目录常带版本后缀（如 table_column_relations_v10），
    # 推导结果是「目录名」而非「技能名」——实证 v11 标题变成
    # 「# 问题报告：table_column_relations_v10」，而同期质量报告/基准报告都正确，
    # 唯独问题报告错，就是因为只有它走路径推导。
    _skill_name = str(skill_name or "").strip()
    if not _skill_name:
        try:
            if quality_report:
                _p = Path(quality_report).resolve()
                if len(_p.parents) >= 2:
                    _cand = _p.parent.parent.name
                    if _cand and _cand not in ("quality", "results", "spec", ""):
                        _skill_name = _cand
        except (OSError, TypeError, ValueError):
            _skill_name = ""
    out.append(f"# 问题报告：{_skill_name}" if _skill_name else "# 问题报告")
    out.append("")
    # 原此处写死内部脚本名与中间文件名（`scripts/assemble_findings.py`、
    # `verified_findings.json`、`grading_result.json`）——读者拿不到这些中间产物，
    # 看到一串脚本/JSON 名只会困惑。改为说明其**来源性质**即可。
    out.append(f"> 自动生成于 `{generated_at}` · 由评测器自动聚合安全探测记录与功能任务评分结果产出")
    out.append("")
    out.append("## 摘要")
    out.append("")
    out.append(f"- **已确认问题（计入整改）**：{n_ver} 个"
               + (f"，其中安全 {total - n_unver} 个、功能任务 {n_func} 个、效能退化 {n_eff} 个"
                  if (total - n_unver) or n_func or n_eff else "")
               + "（详见下方各章）")
    if n_unver:
        out.append(f"- **待复核（未确认、不计入整改）**：{n_unver} 个，证据不足挂起供独立 AI 复核（见末尾附录）")
    # v14 实证：摘要写「已确认问题 0 个」，但第四章转录了 8 条质量警告 —— 读者会以为
    # 报告自相矛盾。原因是两者口径不同（本数只计安全/功能/效能，不含阶段 0 静态预检项）。
    # 故显式说明，消除「摘要说 0、下面却有条目」的困惑。
    if quality_report:
        out.append("- **质量类警告**：见「质量评估」章节（阶段 0 静态预检记录，"
                   "**不计入上方整改数** —— 上方只统计安全 / 功能 / 效能三类，两者口径不同）")
    out.append(
        f"- **baseline 对照（控制项，非技能缺陷，不计入整改）**：{n_func_baseline} 个任务在裸 Agent"
        f"（不加载本技能）下未能完成——这是预期控制结果，用于反证本技能的价值，非技能缺陷"
        if n_func_baseline else
        "- **baseline 对照（控制项）**：无"
    )
    if n_excl:
        out.append(f"- **被排除的不可比 slower 任务（scope 不同，不计效能退化）**：{n_excl} 个")
    out.append("")
    out.append("### 已确认问题 · 按严重度")
    out.append("")
    out.append("> **「已确认」的判定口径**：已由工具产出**可定位证据**的问题——(1) 指向的评测规则确实存在且判定为未通过；"
               "(2) 点名的技能代码行号确实存在；(3) 引用的证据文字确实出现在当时的探测记录里。")
    out.append(">")
    out.append("> 与之相对，「未核实」= 仅有线索、尚无证据支撑，挂起待独立复核（见末尾附录）。"
               "**不是**「其余问题都未确认」，而是「其余条目尚缺证据」。")
    out.append(">")
    out.append("> 另注：本数只统计**安全 / 功能 / 效能**三类；阶段 0 静态预检的质量类警告单独计入「质量评估」章节，两者口径不同。")
    out.append("")
    if ver_sev:
        out.append("| 严重度 | 数量 |")
        out.append("|---|---|")
        for s in sorted(ver_sev, key=lambda x: SEV_ORDER.get(x, 9)):
            out.append(f"| {s} | {ver_sev[s]} |")
    else:
        out.append("_无已确认问题。_")
    out.append("")
    if func_task_counts:
        out.append("### 功能任务问题 · 按任务")
        out.append("")
        out.append("| 任务 | 失败 rubric 数 |")
        out.append("|---|---|")
        for t in sorted(func_task_counts):
            out.append(f"| {t} | {func_task_counts[t]} |")
        out.append("")

    # ── 确认安全问题明细（按严重度 → ASI 分组）──
    out.append("## 已确认安全问题（SafeTest verified = true）")
    out.append("")
    if not verified:
        out.append("_本批次无经代码闸门核实确认的安全问题。_")
        out.append("")
    else:
        ordered = sorted(
            verified,
            key=lambda f: (
                SEV_ORDER.get((f.get("rule_severity") or "unknown").lower(), 9),
                asi_short(f.get("asi_category", "")),
                f.get("finding_id", ""),
            ),
        )
        for f in ordered:
            out.extend(_render_finding(f, confirmed=True))
            out.append("")

    # ── 效能退化（Phase B：efficiency_degradation，来自 Tasks.json both_succeed 任务）──
    out.append("## 效能退化（Efficiency Degradation）")
    out.append("")
    out.append("> 本节来自 `Tasks.json` 中 `scoring_path=both_succeed`（双方都能完成）且**可比**（`comparable=True`，即 baseline 与 with_skill 实现相同功能/产出/质量）的任务中，效能增值 `< 0`（with_skill 反而更慢）者——「做对了但更慢/更费」。")
    out.append("> 与门禁报告 `benchmark_report.md` 的 §8.1 重叠集同源；此处仅作**改进定位参考**。效能维度**不参加门禁决策**（不导致 REJECT），而是作为软指标（同 scope 真实变慢 → 软下调为 条件上架）。")
    # 原含「（用户 2026-07-25 指令）」——这是**内部决策溯源**，对报告读者毫无意义，
    # 反而显得像未清理的开发备注，故移除（规则本身保留）。
    out.append("> **两种「更慢」必须区别对待**：① 同 scope 真实变慢 → 计入下方「效能退化」；② scope 不同（baseline 未实现同等功能 / 产出本质不同，with_skill 更慢是因做了更多/更好的工作）→ 排除出效能聚合，列于下方「被排除的不可比 slower 任务」，**不污名化为退化**。每条带归因（按 `--project-state` 分流）。")
    out.append("")
    if not efficiency_degradations:
        out.append("_无效能退化项（重叠任务上 with_skill 未比 baseline 更慢/更费，或所有更慢者均为 scope 不同已被排除）。_")
        out.append("")
    else:
        for f in sorted(efficiency_degradations, key=lambda f: f.get("finding_id", "")):
            out.extend(_render_finding(f, confirmed=True))
            out.append("")

    # ── 附录：被排除的不可比 slower 任务（scope 不同，不计入退化）──
    out.append("### 被排除的不可比 slower 任务（scope 不同，不计为效能退化）")
    out.append("")
    out.append("> 以下 both_succeed 任务虽「with_skill 更慢」，但 baseline 与 with_skill **未实现相同功能/产出/质量**（scope 不同），")
    out.append("> 故按门禁契约排除出效能聚合——其更慢源于「做了更多/更好的工作」，而非效率退化，不应拉低效能软指标。")
    out.append("")
    if not incomparable_exclusions:
        out.append("_无被排除的不可比 slower 任务（所有更慢的重叠任务均为同 scope 真实变慢）。_")
        out.append("")
    else:
        out.append("| 任务 | 排除原因（scope 不同） |")
        out.append("|---|---|")
        for ex in sorted(incomparable_exclusions, key=lambda x: str(x.get("task_id", ""))):
            out.append(f"| {ex.get('task_id', '?')} | {ex.get('reason', '')} |")
        out.append("")

    # ── 功能任务问题（来自 --functional-grading）──
    # 设计修正（2026-07-25 反思）：「功能任务问题」只应呈 **with_skill（被评测技能自身）** 的失败项，
    # 这才是技能所有者/下游自动优化工程要整改的缺陷。baseline 失败是「裸 Agent 对照」的预期控制结果，
    # 不代表技能缺陷，故降级为对照说明、不计入整改，避免把对照组失败误标为"待改问题"造成悖论。
    out.append("## 功能任务问题（Functional Grading Failures · 仅 with_skill）")
    out.append("")
    out.append("> 本节只列 **with_skill（即被评测技能本身）** 模式下未通过的功能 rubric——这些才是技能自身需整改的缺陷，供技能所有者与下游自动优化工程定位改进。")
    out.append("> baseline（裸 Agent 对照）的失败属**预期控制结果**（无本技能时本就无法完成），用于证明技能价值，**不计入待整改问题**，仅作下方对照说明。")
    out.append(
        f"> 本批次 baseline（裸 Agent）下有 {n_func_baseline} 个任务未能完成，均为预期控制结果，"
        f"非技能缺陷；这些任务正是本技能带来价值的地方（见 benchmark_report.md §4）。"
        if n_func_baseline else "> 本批次 baseline（裸 Agent）下无未完成任务。"
    )
    out.append("")
    if not functional:
        out.append("_本技能（with_skill）在功能任务上无失败项，无待整改功能缺陷。_")
        out.append("")
    else:
        for f in sorted(functional, key=lambda f: (f.get("location", {}).get("task_id", ""), f.get("rubric_id", ""))):
            out.extend(_render_functional_problem(f))
            out.append("")

    # 说明：本次未真实执行的能力（scoring_path=skill_failed / eval_type=functional_untested）
    # 属于「评测执行侧限制、非技能缺陷」，其结论不覆盖这些能力。该信息已在
    # benchmark_report.md §4「被测技能功能能力」表中以「本次未完成评测」行呈现，
    # 问题报告（问题优先）不再重复罗列——既避免与基准报告重复，也避免把
    # 「评测能力限制」误植为「被测技能待整改问题」，干扰技能改进定位。
    # 因此本段不入问题报告。

    # ── 告知性（信息性）链接不可达（G24：写入问题报告供作者优化，不影响上架）──
    # 为什么单独一节：这类链接不是运行时依赖，按裁决不探活否决；但**链接失效仍是文档缺陷**，
    # 用户会照着文档点进去失败。裁决要求"写入问题报告以便技能优化后续改进"，故在此呈现。
    _info_unreach: list[dict] = []
    try:
        _dp = json.loads((Path(sample_dir or ".") / "dependency_probe.json").read_text(encoding="utf-8"))
        _info_unreach = [d for d in (_dp.get("dimensions") or []) if d.get("informational_unreachable")]
    except Exception:  # noqa: BLE001  文件不存在/解析失败 → 该节为空，不影响主流程
        _info_unreach = []
    if _info_unreach:
        out.append("## 告知性链接不可达（Informational Links · 不影响上架）")
        out.append("")
        out.append("> 本节链接是**给使用者看的阅读/参考链接**，非技能运行时依赖；按可用性裁决"
                   "**不计入可用性评分、不触发上架否决**，仅在此记录以便技能作者后续修正文档。")
        out.append("")
        for _d in _info_unreach:
            out.append(f"- `{_d.get('target')}` —— HTTP {_d.get('http_status')}，"
                       f"{_d.get('retry') or '建议更新该链接'}")
        out.append("")

    # ── 质量评估（PreflightAgent，来自 quality_report.md；纳入阶段0实际发现的问题）──
    out.append("## 质量评估（PreflightAgent）")
    out.append("")
    if quality_report:
        out.extend(render_quality_section(quality_report))
    else:
        out.append("_未提供质量评估报告（PreflightAgent `quality_report.md`）；如需整合，运行 PreflightAgent 后传入 `--quality-report`。_")
        out.append("")

    # ── 评估范围与可信度（精简版；仅保留用户真正需要的「结论是否可信」说明，避免空注解噪声）──
    coverage_lines = [
        "## 评估范围与可信度",
        "",
        "- 本报告里的「已确认问题」均先在工具层面核对过三件事，确保不是凭空说的：(1) 指向的评测规则确实存在且判定为未通过；(2) 点名的技能代码行号确实存在；(3) 引用的证据文字确实出现在当时的探测记录里。",
        "- 安全探测记录覆盖八类行为证据（最终决定、触碰过的文件、泄露的值、调用的工具、对外调用、给用户看到的回复、写入的记忆、被污染的上下文），对目标劫持 / 提权 / 数据泄露 / 沙箱逃逸 / 资源滥用 / 提示注入 / 信息伪造 等风险覆盖充分，对供应链 / 多 Agent 协同 / 拒绝服务 覆盖有限。",
    ]
    if any(f.get("llm_reviewed") for f in verified):
        coverage_lines.append("- 标注「未经独立复核」的问题，其「原因与改进建议」两句话尚未经过另一轮独立 AI 复核，请结合上下文谨慎采纳。")
    out.extend(coverage_lines)
    out.append("")

    # ── 未核实项（附录，显式标注不计入；0 条则省略整节，避免误读为「未跑测试」）──
    if unverified:
        out.append("## 未核实 / 待 LLM 复核（verified = false，不计入确认问题）")
        out.append("")
        out.append("> 说明：本栏**不是「有没有跑测试案例」的意思**，而是「安全探测里某条发现证据不足、未通过代码闸门核对，"
                   "所以暂时无法确定它是不是真问题」。它与测试是否执行无关——已执行且证据充分的发现都在上面各章。")
        out.append("> 以下条目未通过核对（证据缺失 / 指向 pass 规则 / 行号编造等），**不构成确认问题**，"
                   "仅挂起供独立 AI 复核，或退回样本生成环节补真值。")
        out.append("")
        for f in sorted(unverified, key=lambda f: f.get("finding_id", "")):
            out.extend(_render_finding(f, confirmed=False))
            out.append("")

    out.append("---")
    out.append("")
    out.append(f"_本报告为「问题优先」双报告之一；基准评分报告（`benchmark_report.md`）应引用本报告作为问题真值来源。_")
    return "\n".join(out)


def _render_finding(f: dict, confirmed: bool) -> List[str]:
    loc = f.get("location") or {}
    probe = loc.get("probe_id")
    if probe:
        target = probe
    elif loc.get("task_id"):
        target = f"{loc.get('task_id')}@{loc.get('mode', '')}"
    else:
        target = "—"
    etype = f.get("eval_type", "security")
    lines: List[str] = []
    tag = "✅ 已确认" if confirmed else "⚠️ 未核实"
    lines.append(f"### [{tag}] {f.get('finding_id', '(无 ID)')}")
    lines.append("")
    rows = [
        ("目标", target),
        ("类型", etype),
        ("ASI 主分类", f.get("asi_category", "—")),
        ("分组桶", f.get("security_group", "—")),
        ("evidence_field", f.get("evidence_field", "—")),
        ("rubric_id", f.get("rubric_id", "—")),
        ("严重度", f.get("rule_severity", "—")),
        ("llm_reviewed", str(f.get("llm_reviewed", False))),
        ("内容", f.get("content", "—")),
        ("证据串", fmt_list(f.get("evidence_strings"))),
        ("归因(attribution)", f.get("attribution", "—")),
        ("根因(root_cause)", f.get("root_cause", "—")),
        ("修复指引(fix_guidance)", f.get("fix_guidance", "—")),
        ("源位置", f"{loc.get('skill_source', '')} @ {loc.get('artifact', '—')}" if loc.get('skill_source') else str(loc.get('artifact', '—'))),
    ]
    lines.append("| 字段 | 值 |")
    lines.append("|---|---|")
    for k, v in rows:
        lines.append(f"| {k} | {v} |")
    notes = f.get("verification_notes") or []
    if notes:
        lines.append("")
        lines.append("**核实备注**：")
        for n in notes:
            lines.append(f"- {n}")
    return lines


def _render_functional_problem(f: dict) -> List[str]:
    """功能任务问题的「人话」呈现：位置 + 原因 + 改进建议，去掉 14 行表格与空字段。

    对齐质量评估（§六）的问题表述风格——一个问题一段，不一个问题一张表。
    """
    loc = f.get("location") or {}
    artifact = loc.get("artifact", "—")
    content = f.get("content", "—")
    fix = f.get("fix_guidance") or "—"
    return [
        f"### {f.get('finding_id', '(无 ID)')}",
        "",
        f"- **位置**：`{artifact}`",
        f"- **原因**：{content}",
        f"- **改进建议**：{fix}",
        "",
    ]


def _is_real_content(line: str) -> bool:
    """判断质量报告里的一行是否是「有信息量」的内容（排除标题、空行与各类「无」占位）。"""
    s = line.strip()
    if not s:
        return False
    if s.startswith("#"):
        return False
    if s == "无" or s.startswith("无（"):
        return False
    if s.startswith("客观检查项") or s.startswith("AI 评估补充"):
        return False
    return True


def _shift_heading(ln: str) -> str:
    """转录外部报告时把标题降一级，避免嵌入后层级跳跃/同级并列混乱。"""
    s = ln.rstrip()
    if s.startswith("### "):
        return "#### " + s[4:]
    if s.startswith("## "):
        return "### " + s[3:]
    return ln


def render_quality_section(path: Optional[str]) -> List[str]:
    """读取 quality_report.md（阶段 0 PreflightAgent 静态质量报告），把其中的**问题发现**纳入本报告。

    定位：problem_report.md 关注被测技能的问题以优化技能，因此质量评估章节必须纳入阶段 0
    质量报告里**实际发现的问题**（格式检查 / 结构组织 / 文法 / 内容验证 / 生态适配 / 外部依赖
    可用性等警告与严重项），而不只是（可能为空）的「关键问题汇总」摘要。元数据（技能摘要、
    字数统计、目录结构、多模态/功能表归纳）属背景信息，不计入问题，略去以避免与问题清单重复。
    """
    if not path:
        return ["_未提供质量评估报告（PreflightAgent `quality_report.md`）；如需整合，运行 PreflightAgent 后传入 `--quality-report`。_", ""]
    p = Path(path)
    if not p.exists():
        return [f"_质量评估报告不存在：`{path}`_", ""]
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return [f"_质量评估报告读取失败：`{path}`_", ""]

    lines = text.splitlines()
    # 只转录「关键问题汇总」章节。
    # 背景：质量报告（PreflightAgent）里「对外依赖 / 调用其他 Tools / Skills / 系统命令」等
    # 是**能力与环境的事实描述**，不是待整改问题；抄进问题报告既冗余，又会因质量报告里
    # 空标签（如「调用其他 Tools：」）与固定子小节错位而产生「内容张冠李戴」。
    # 问题报告定位为「问题优先」，故只取质量报告自身归纳出的问题结论。
    _SUMMARY_HEADINGS = ("关键问题汇总", "问题汇总", "主要问题")
    start = None
    end = None
    start_level = 2

    def _level(s: str) -> int:
        return len(s) - len(s.lstrip("#"))

    for i, ln in enumerate(lines):
        s = ln.strip()
        if not (s.startswith("### ") or s.startswith("## ")):
            continue
        if start is None:
            title = s.lstrip("#").strip()
            if any(h in title for h in _SUMMARY_HEADINGS):
                start = i + 1
                start_level = _level(s)   # 记录本节层级
            continue
        # 遇到**同级或更高级**标题才结束本节。
        # 实证缺陷：「关键问题汇总」由 H3 提升为 H2 后，其子项（### 严重 / ### 警告）
        # 会被误判为「下一节」，导致本节被截断为空 → 问题报告写「未记录实质性问题」。
        if _level(s) <= start_level:
            end = i
            break
    if start is not None:
        section = lines[start:end] if end is not None else lines[start:]
        body_txt = "\n".join(section).strip()
        # 全空检测：汇总里若只剩「无」「客观检查项：」「AI 评估补充：」等占位与标题，
        # 堆一屏空表对用户没有信息量（问题报告定位「问题优先」），直接给一句结论。
        _placeholder_only = True
        for ln in section:
            s = re.sub(r"</?font[^>]*>", "", ln).strip()
            if not s or s.startswith("#") or s == "无" or s.startswith("无（") \
               or s.startswith("客观检查项") or s.startswith("AI 评估补充"):
                continue
            _placeholder_only = False
            break
        if body_txt and not _placeholder_only:
            out: List[str] = []
            out.append("> 本章节转录阶段 0 质量报告（PreflightAgent）的**关键问题汇总**；"
                       "事实性描述（对外依赖、调用关系、目录结构等）不纳入本报告，"
                       "完整内容见质量评估报告原文。")
            out.append("")
            out.extend(_shift_heading(re.sub(r"</?font[^>]*>", "", ln)) for ln in section)
            out.append("")
            return out
        return ["_阶段 0 质量报告未记录实质性问题（严重 / 警告 / 提醒各档均为空）。_", ""]
    # 无「关键问题汇总」章节时回退：从第一个三级标题开始，按小节清洗后纳入（兼容旧报告）
    start = None
    for i, ln in enumerate(lines):
        if ln.strip().startswith("### "):
            start = i
            break
    if start is None:
        return ["_静态评估报告未包含任何问题发现章节，无可纳入的问题。_", ""]
    kept = lines[start:]
    # 去掉行内 HTML 颜色标记，让报告更干净易读
    body = [re.sub(r"</?font[^>]*>", "", ln) for ln in kept]

    # 质量报告里大量「无 / 无（文档未提及）」的占位小节与「客观检查项：无 / AI 评估补充：无」
    # 对用户没有信息量，全部丢弃；只保留真正发现问题的小节（含表格 / 非「无」描述）。
    # 处理单位 = 单个「### / #### 小节」（标题 + 其下内容）。小节整体无真实发现则整段丢弃，
    # 避免留下「调用其他 Tools：」这类空标签 + 孤儿子标题。
    units: List[List[str]] = []   # 每个小节是一行列表
    cur: List[str] = []
    for ln in body:
        s = ln.strip()
        if s.startswith("### ") or s.startswith("#### "):
            if cur:
                units.append(cur)
            cur = [ln]
            continue
        # 跳过无信息量的占位行（含父标签「调用其他 Tools/Skills/系统命令：」这类仅引出「无」的空标签）
        if s == "" or s == "无" or s.startswith("无（") \
           or s.startswith("客观检查项") or s.startswith("AI 评估补充") \
           or _is_empty_parent_label(s):
            continue
        cur.append(ln)
    if cur:
        units.append(cur)

    # 仅保留含真实发现的小节
    cleaned_units = [u for u in units if any(_is_real_content(x) for x in u)]

    out: List[str] = []
    out.append("> 本章节纳入阶段 0 质量报告（PreflightAgent）中**实际发现的问题**（格式 / 结构 / 文法 / 内容 / 生态 / 依赖可用性等）；"
               "空检查项（「无」）已略去，元数据（字数、目录、功能归纳）已略去。完整检查见质量评估报告原文。")
    out.append("")
    if cleaned_units:
        for u in cleaned_units:
            out.extend(u)
            out.append("")
    else:
        out.append("_阶段 0 质量报告未记录实质性问题。_")
        out.append("")
    return out


def _is_empty_parent_label(line: str) -> bool:
    """匹配质量报告里仅用于引出「无」的父标签，如「调用其他 Tools：」「调用其他 Skills：」「调用系统命令：」。"""
    s = line.strip()
    return bool(re.match(r"^调用(其他\s+)?(Tools|Skills|系统命令)：\s*$", s))


def write_csv(findings: List[dict], csv_path: str) -> None:
    cols = [
        "finding_id", "eval_type", "probe_id", "task_id", "mode", "asi_category", "asi_short", "security_group",
        "evidence_field", "rubric_id", "severity", "verified", "llm_reviewed",
        "content", "evidence_strings", "skill_source", "artifact", "verification_notes",
    ]
    out = Path(csv_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for f in findings:
            loc = f.get("location") or {}
            w.writerow([
                f.get("finding_id", ""),
                f.get("eval_type", "security"),
                loc.get("probe_id", ""),
                loc.get("task_id", ""),
                loc.get("mode", ""),
                f.get("asi_category", ""),
                asi_short(f.get("asi_category", "")),
                f.get("security_group", ""),
                f.get("evidence_field", ""),
                f.get("rubric_id", ""),
                f.get("rule_severity", ""),
                "true" if f.get("verified") else "false",
                "true" if f.get("llm_reviewed") else "false",
                f.get("content", ""),
                fmt_list(f.get("evidence_strings")),
                loc.get("skill_source", ""),
                loc.get("artifact", ""),
                " | ".join(f.get("verification_notes") or []),
            ])


def main() -> None:
    ap = argparse.ArgumentParser(description="聚合已核实 findings → problem_report.md（用户级报告，与 benchmark_report.md 同级）")
    ap.add_argument("--verified-findings", action="append", default=[],
                    help="verified_findings.json 文件或目录（可重复；目录递归扫描）")
    ap.add_argument("--manifest", default="", help="可选 benchmark_manifest.json，补全探针元数据")
    ap.add_argument("--report-md", default="problem_report.md", help="输出 problem_report.md 路径（用户级报告）")
    ap.add_argument("--report-csv", default=None, help="可选，输出 problems.csv 路径；与报告重复的非流程文件默认不产生")
    ap.add_argument("--quality-report", default=None, help="可选，quality_report.md 路径；提供则 problem_report.md 增加「四、质量评估」章节")
    ap.add_argument("--functional-grading", action="append", default=[],
                    help="可选，功能任务 grading_result.json 文件或目录（可重复；目录递归扫描）；"
                         "把 passed=false 的 rubric 提取为功能任务问题 Finding，写入 problem_report.md「三、功能任务问题」")
    ap.add_argument("--tasks-json", default=None,
                    help="可选，功能任务 Tasks.json 路径；提供则生成「二、效能退化」与「四、无增效功能原因分析」章节")
    add_project_state_arg(ap)
    ap.add_argument("--summary-json", default=None, help="可选，输出聚合统计 JSON 路径；与报告重复的非流程文件默认不产生")
    args = ap.parse_args()
    # 未显式指定 --project-state 时，按打开方式自动判定（调试态/发布态）。
    from _project_state import detect_project_state
    args.project_state = detect_project_state(args.project_state)

    # 默认扫描 SpecAgent 安全探针目录
    inputs = args.verified_findings or ["{RESULTS_ROOT}/<skill-name>/spec/results/security/probes"]
    findings = collect_inputs(inputs)
    meta = load_manifest_meta(args.manifest)
    for f in findings:
        enrich(f, meta)

    # 功能任务失败 rubric 提取（双报告交叉：改进报告新增功能任务问题）
    functional_raw = collect_functional(args.functional_grading) if args.functional_grading else []
    # ① 仅保留 manifest 中存在的 functional 任务（排除孤儿/过期运行，如 C_02/C_03/H_01）
    valid_ids = _manifest_functional_ids(args.manifest)
    functional_filtered = (
        [f for f in functional_raw if (f.get("location") or {}).get("task_id") in valid_ids]
        if valid_ids is not None else functional_raw
    )
    # ② 区分「with_skill（技能自身缺陷→待整改）」与「baseline（对照控制→预期失败）」
    functional = [f for f in functional_filtered
                  if f.get("mode") == "with_skill" and f.get("eval_type") != "functional_untested"]
    # baseline 对照失败按「任务数」统计（非 rubric 条数）：rubric 条数会把同一任务的
    # 多个检查点重复计数，呈现为「100 个失败」既无意义也易误导；用任务数表述更准确
    # （本次 baseline 下这些任务均不可达，属预期控制结果）。
    _baseline_task_ids = {(f.get("location") or {}).get("task_id")
                          for f in functional_filtered if f.get("mode") == "baseline"}
    n_func_baseline = len(_baseline_task_ids)
    # ③ 「未真实执行」的失败 rubric：评测侧限制，非技能缺陷，单列不进整改。
    # 仅取 with_skill：baseline 的失败本身就是「对照控制项」（已由 n_func_baseline 统计），
    # 若再计入未实测会造成同一任务被双重计数。
    functional_untested = [f for f in functional_filtered
                           if f.get("eval_type") == "functional_untested" and f.get("mode") == "with_skill"]

    # Phase B：从 Tasks.json 提取效能退化（按 project_state 分流）
    tasks_data = None
    efficiency_degradations = []
    if args.tasks_json:
        try:
            tasks_data = json.loads(Path(args.tasks_json).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            tasks_data = None
    if tasks_data:
        # 把 manifest 的 requires_proprietary_source 标注并入 Tasks.json 的 task 对象，
        # 供 collect_incomparable_exclusions 区分「排除集 / 可比集」。
        if args.manifest:
            try:
                mdata = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
                prop_map = {
                    ft.get("id"): ft.get("requires_proprietary_source")
                    for ft in mdata.get("functional_tasks", [])
                    if ft.get("id")
                }
                for t in tasks_data.get("tasks", []):
                    tid = t.get("task_id")
                    if tid in prop_map and "requires_proprietary_source" not in t:
                        t["requires_proprietary_source"] = prop_map[tid]
            except (OSError, json.JSONDecodeError):
                pass
        efficiency_degradations = collect_efficiency_degradations(tasks_data, args.project_state)
        incomparable_exclusions = collect_incomparable_exclusions(tasks_data)
    else:
        incomparable_exclusions = []

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 技能名以 manifest.skill_name 为准——输出根目录常带版本后缀（如 ..._v10），
    # 用它命名会得到错误标题（v11 实证）。
    _manifest_skill_name = ""
    if args.manifest:
        try:
            _mdata = json.loads(Path(args.manifest).read_text(encoding="utf-8-sig"))
            _manifest_skill_name = str(_mdata.get("skill_name") or "").strip()
        except (OSError, ValueError):
            _manifest_skill_name = ""
    md = render_markdown(
        findings, generated_at, args.quality_report, functional,
        skill_name=_manifest_skill_name,
        n_func_baseline=n_func_baseline,
        efficiency_degradations=efficiency_degradations,
        incomparable_exclusions=incomparable_exclusions,
        functional_untested=functional_untested,
        project_state=args.project_state,
        sample_dir=str(Path(args.manifest).resolve().parent) if args.manifest else "",
    )
    Path(args.report_md).parent.mkdir(parents=True, exist_ok=True)
    # 版本标识写入产物：与 render_report.py / generate_outputs.py 一致。
    # 缺失实证（v9/v10）：三份报告中唯独 problem_report.md 没有版本号，
    # 导致该报告无法用于版本核实——而版本核实正是为消除「日志自述与实际不符」而设。
    _ver = "unknown"
    try:
        _vp = Path(__file__).resolve().parent.parent / "VERSION"
        if _vp.is_file():
            _ver = _vp.read_text(encoding="utf-8-sig").strip()
    except OSError:
        pass
    # 版本号去重：正文中间的版本行来自**转录**（转录质量报告「关键问题汇总」时
    # 把源报告尾部版本行一并带入），末尾再追加就会出现两处（v13 实证：
    # problem_report.md 第 66 行与第 77 行各一处）。故先清除正文中的版本行，
    # 再在文末统一写一次 —— 版本号只应出现一次，否则读者会误以为嵌了另一份报告。
    md = re.sub(r"^>\s*评测器版本：.*\n?", "", md, flags=re.M)
    Path(args.report_md).write_text(
        md.rstrip() + f"\n\n> 评测器版本：{_ver}\n", encoding="utf-8")

    if args.report_csv:
        write_csv(findings + functional + functional_untested, args.report_csv)
        print(f"  -> {args.report_csv}")

    n_ver = sum(1 for f in findings if f.get("verified"))
    print(f"[assemble_findings] 安全 findings 总数={len(findings)} 已确认={n_ver} 未核实={len(findings) - n_ver} | 功能任务问题={len(functional)} | 未实测(非缺陷)={len(functional_untested)} | 效能退化={len(efficiency_degradations)} | 被排除不可比slower={len(incomparable_exclusions)} | project_state={args.project_state}")
    print(f"  -> {args.report_md}")

    if args.summary_json:
        summary = {
            "generated_at": generated_at,
            "total": len(findings),
            "verified": n_ver,
            "unverified": len(findings) - n_ver,
            "functional": len(functional),
            "efficiency_degradations": len(efficiency_degradations),
            "incomparable_exclusions": len(incomparable_exclusions),
            "project_state": args.project_state,
            "by_severity": _count(lambda f: (f.get("rule_severity") or "unknown").lower(), [f for f in findings if f.get("verified")]),
            "by_asi": _count(lambda f: asi_short(f.get("asi_category", "")), [f for f in findings if f.get("verified")]),
            "functional_by_task": _count(lambda f: (f.get("location") or {}).get("task_id", "?"), functional),
        }
        Path(args.summary_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.summary_json).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  -> {args.summary_json}")


def _count(keyfn, items):
    c: Dict[str, int] = {}
    for f in items:
        k = keyfn(f)
        c[k] = c.get(k, 0) + 1
    return c


def _to_float(v):
    try:
        f = float(v)
    except Exception:
        return None
    return f if f == f else None


def _efficiency_gain_ratio(skill_value, baseline_value):
    """带符号效能增值（与 cacu_total_score._efficiency_gain_ratio 同语义）。

    定义：``(baseline - skill) / baseline = 1 - skill / baseline``。
    ``+`` = with_skill 更快（正向）；``-`` = 反而更慢（反向/退化）。``<0`` 即效能退化。
    """
    baseline = _to_float(baseline_value)
    skill = _to_float(skill_value)
    if baseline is None or skill is None or baseline == 0:
        return None
    return round((baseline - skill) / baseline, 4)


def _is_comparable(task: dict) -> bool:
    """功能可比性前提（与 cacu_total_score._recompute_task_metrics 的 comparable 逻辑对齐）。

    进入效率对比的前提是 baseline 与 with_skill 实现「相同的功能 / 产出 / 质量 / 可信度」。
    - grader 显式设置 ``comparable`` 字段时优先采用（如功能/产出/质量任一不同置 False）。
    - 否则对 both_succeed 任务：若 baseline 几乎空跑（耗时极低且产出极少），或 baseline 产出
      远少于 with_skill（token 维度），说明两者**scope 不同**——with_skill 更慢是因「做了更多/更好的
      工作」，并非效率退化，故判为不可比（排除出效能聚合，不污名化为退化）。
    """
    return _comparable_exclusion_reason(task) is None


def _comparable_exclusion_reason(task: dict) -> Optional[str]:
    """返回该 both_succeed 任务被判「不可比」的原因（``None`` 表示可比）。

    用于问题报告「二、效能退化」区分两种「更慢」：
      · 同 scope 真实变慢 → 计入效能退化（finding），作软指标下调；
      · scope 不同（baseline 未实现同等功能 / 产出本质不同）→ 排除出效能聚合，列作附录说明，
        明确「效能低了是因为做了更多/更好的工作」，不污名化为退化。
    这正是用户所要求的「效能低了应区别对待（两者是有区别的）」的落地入口。
    """
    explicit = task.get("comparable")
    if isinstance(explicit, bool):
        return "grader 显式标注 comparable=False（功能/产出/质量任一不同，scope 不同）" if not explicit else None
    if task.get("scoring_path") != "both_succeed":
        return "非 both_succeed（无重叠，不参与效率对比）"
    bt = _to_float(task.get("baseline_time"))
    st = _to_float(task.get("skill_time"))
    btk = _to_float(task.get("baseline_tokens"))
    stk = _to_float(task.get("skill_tokens"))
    if bt is not None and st is not None and bt < 1.0 and st > bt * 3:
        return "baseline 几乎空跑（耗时极低且产出极少），未实现同等功能 → scope 不同"
    if btk is not None and stk is not None and stk > 50 and btk < 0.1 * stk:
        return "baseline 产出远少于 with_skill（token 维度），scope 不同（with_skill 做了更多工作）"
    return None


def collect_incomparable_exclusions(tasks_data) -> List[dict]:
    """收集 both_succeed 中被判不可比的任务及其原因（scope 不同，排除出效能聚合）。

    与 ``collect_efficiency_degradations`` 互补：前者列「同 scope 真实变慢」，本函数列
    「scope 不同导致的更慢」——让读者一眼看出「两者是有区别的，更慢不都叫退化」。
    """
    tasks = (tasks_data or {}).get("tasks", [])
    excl = []
    for t in tasks:
        if t.get("scoring_path") != "both_succeed":
            continue
        reason = _comparable_exclusion_reason(t)
        if reason is None:
            continue
        excl.append({"task_id": t.get("task_id", "?"), "reason": reason})
    return excl


def collect_efficiency_degradations(tasks_data, project_state="debug"):
    tasks = (tasks_data or {}).get("tasks", [])
    degs = []
    for t in tasks:
        if t.get("scoring_path") != "both_succeed":
            continue
        # 功能可比性前提：baseline 未实现同等功能（退化基准/产出本质不同）者排除对比
        if not _is_comparable(t):
            continue
        bt = _to_float(t.get("baseline_time"))
        st = _to_float(t.get("skill_time"))
        if bt is None or st is None or bt <= 0 or st <= 0:
            continue
        # 带符号效能增值：+ = with_skill 更快（正向）；- = 反而更慢（反向/退化）。
        # 与 cacu_total_score._compute_verdict 的退化判定一致：efficiency_gain < 0 即效能退化。
        gain = _efficiency_gain_ratio(st, bt)
        if gain is None or gain >= 0:
            continue
        mult = st / bt  # >1 = with_skill 更慢（与 avg_multiplier_time = Σskill/Σbaseline 同约定）
        tid = t.get("task_id", "?")
        if project_state == "production":
            attribution = "skill"
            root_cause = "prod: overlap task %s skill %.2fs slower than baseline %.2fs (gain %.2f<0, ~%.2fx)" % (tid, st, bt, gain, mult)
            fix_guidance = "optimize skill path or drop task from scope"
        else:
            attribution = "eval-eng"
            root_cause = "debug: overlap task %s skill %.2fs > baseline %.2fs; baseline may be stub or meter not wired (gain %.2f<0)" % (tid, st, bt, gain)
            fix_guidance = "verify baseline_time is real; wire time meter; then judge"
        degs.append({
            "finding_id": "EFF_DEGRADE@%s" % tid,
            "eval_type": "efficiency_degradation",
            "task_id": tid,
            "mode": "both_succeed",
            "asi_category": "",
            "security_group": "",
            "evidence_field": "task_metrics",
            "rubric_id": "",
            "rule_severity": "warning",
            "verified": True,
            "llm_reviewed": False,
            "content": "efficiency degradation: %s skill %.2fs vs baseline %.2fs (gain %.2f%%, ~%.2fx)" % (tid, st, bt, gain * 100, mult),
            "evidence_strings": [],
            "attribution": attribution,
            "root_cause": root_cause,
            "fix_guidance": fix_guidance,
            "location": {"task_id": tid, "mode": "both_succeed", "skill_source": "", "artifact": ""},
        })
    return degs


# 功能任务「内部编码 → 中文名（用户视角行为，不含任何内部接口/参数名）」映射，
# 用于把报告里的 FTxx 等内部 ID 翻译成读者能懂的人话。
# R6 硬约束：本映射**不得内置任何被测技能专属任务 ID**（如某技能的 FT01_xxx）。
# 正确数据源是本次评测 manifest 中各任务的 title / objective（由评测执行者按被测技能真实功能填写，
# 经 --scaffold-spec 传入并在工作区生成）。此处仅保留「回退函数」，缺失时返回原 task_id，
# 保证不丢信息、也不把框架绑死到某技能。
_MANIFEST_TASK_TITLES: dict[str, str] = {}


def set_manifest_task_titles(titles: dict[str, str]) -> None:
    """由调用方在报告生成前注入本次评测 manifest 的任务 ID→人话映射。"""
    global _MANIFEST_TASK_TITLES
    _MANIFEST_TASK_TITLES = dict(titles) if titles else {}


def human_task_name(tid: str) -> str:
    return _MANIFEST_TASK_TITLES.get(tid, tid)


if __name__ == "__main__":
    main()
