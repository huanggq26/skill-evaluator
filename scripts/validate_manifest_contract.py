#!/usr/bin/env python3
# ============================================================
# validate_manifest_contract.py — 样本契约守卫（manifest contract guard）
#
# 定位：在 sample 生成之后、下游聚合（generate_tasks_json 等）之前运行，
#       确保 functional_tasks 不被 internal 项污染。
#
# 这是「防御性守卫」，不是「正向语义分类器」：
#   • 句法/正则做正向语义分类 → 不完备（目标含多层语义，句法无法理解语义）
#   • 本脚本只校验「结构化不变量」：标签(tier/user_facing) 与所在桶
#     (functional_tasks / internal_checks) 是否矛盾、计数是否自洽、ID 是否唯一
#     → 这些检查是完备的（比对结构化字段值，不依赖语义理解）
#
# 举证责任反转：进入 functional_tasks 的条目必须显式声明 user_facing:true，
#   否则一律视为「未确认」而 FAIL——即便 LLM 漏判/漏标，污染也进不了功能任务桶。
#
# 退出码：0 = 契约满足（可进下游）；1 = 契约违反（应阻断下游聚合）。
# ============================================================
import argparse
import json
import os
import re
import sys
from pathlib import Path

from _common import TAG_TO_ASI, derive_security_group, lenses_for_asi, MIN_ASI_COVERAGE

# RUBRIC_COUNT 权威值见 references/config.md（评分阈值节，=10）。
# 本守卫按 AGENTS_RULES「引用而非硬编码」纪律，以常量变量承载并注明来源。
RUBRIC_COUNT = 10  # ← 与 config.md RUBRIC_COUNT 一致；如需改请同步 config.md

# 启发式关键词（仅 WARNING，不阻断；明确告知不完备，供人工复核）
INTERNAL_HINTS = ["脚手架", "自检", "内部策略", "internal", "l2_internal", "生成探测", "scaffold"]

# 功能/内部任务条目的必填字段（stage1_sample.md 步骤 7 第 9 条硬约束）
_TASK_REQUIRED_FIELDS = ["outcome", "output_contract", "environment", "verifier", "unsupported_rules"]
# 安全探测条目的必填字段（benchmark_manifest.spec.md）
_SEC_REQUIRED_FIELDS = ["security_group", "primary_asi_category", "risk_hypothesis", "case_dir", "grader_manifest_path"]

# 内部编排脚本（Stage-4 聚合/协调步骤，非用户能力；用户说"做 X"不指向这些 .py）。
# 注意：阶段0 质量门禁的真实入口 extract_stats.py / validate_quality_report.py 是用户能力的一部分，
# 不在拒绝名单内——误伤会阻断真·用户能力，故采用精确拒绝名单而非宽泛前缀。
INTERNAL_ORCHESTRATION_SCRIPTS = [
    "generate_tasks_json.py",
    "cacu_total_score.py",
    "generate_outputs.py",
    "run_security_pipeline.py",
    "validate_output.py",
    "backfill_reviews.py",
    "assemble_manifest.py",
    "generate_probe_scaffolds.py",
]
INTERNAL_SCRIPT_RE = re.compile(
    r"(?:^|[\s（(])(" + "|".join(re.escape(s) for s in INTERNAL_ORCHESTRATION_SCRIPTS) + r")",
    re.IGNORECASE,
)


def main():
    ap = argparse.ArgumentParser(description="样本契约守卫：functional_tasks 不得混入 internal 项 + 字段/文件完整性")
    ap.add_argument("--manifest", required=True, help="benchmark_manifest.json 路径")
    ap.add_argument("--sample-root", default=None,
                    help="样本根目录（含 common/ hard/ security/ 等）；缺省取 manifest 所在目录")
    ap.add_argument("--exec-root", default=None,
                    help="执行产物根目录（含 baseline/tasks/<id>/results/metrics.json 与 "
                         "with_skill/tasks/<id>/results/metrics.json）；缺省不校验性能标记落地")
    ap.add_argument("--skill-dir", default=None,
                    help="被测技能目录（含 SKILL.md 与自带资产）；提供时校验 functional_tasks 的 "
                         "capability_source 可追溯性（E27），缺省不校验")
    args = ap.parse_args()

    if not os.path.isfile(args.manifest):
        print(f"❌ manifest 不存在: {args.manifest}", file=sys.stderr)
        sys.exit(1)

    sample_root = Path(args.sample_root) if args.sample_root else Path(args.manifest).resolve().parent

    with open(args.manifest, encoding="utf-8") as f:
        d = json.load(f)

    errors = []
    warnings = []

    ft = d.get("functional_tasks") or []
    ic = d.get("internal_checks") or []
    summary = d.get("summary") or {}

    # ---- 守卫 1：举证责任反转 + 矛盾检测（functional_tasks 桶）----
    for t in ft:
        tid = t.get("id", "?")
        uf = t.get("user_facing", None)  # 故意用 is-not-True：None 与 False 都触发
        tier = str(t.get("tier", "")).lower()
        # 举证责任反转：必须显式 user_facing:true，否则视为未确认
        if uf is not True:
            errors.append(
                f"[E1] functional_tasks 条目 {tid} 未显式 user_facing:true"
                f"（举证责任反转：默认非 functional，须显式声明）"
            )
        if tier == "l2_internal":
            errors.append(f"[E2] functional_tasks 条目 {tid} tier=l2_internal，应移入 internal_checks")
        if uf is False:
            errors.append(f"[E3] functional_tasks 条目 {tid} user_facing=false，应移入 internal_checks")
        # 守卫 5：内部管道脚本不得冒充用户能力（F1 的反面）
        _obj_blob = " ".join(
            [str(t.get("objective", ""))]
            + [str(x) for x in (t.get("pass_criteria") or [])]
        )
        if INTERNAL_SCRIPT_RE.search(_obj_blob):
            errors.append(
                f"[E10] functional_tasks 条目 {tid} 的 objective/pass_criteria 含 Stage-4 内部编排脚本"
                f"（如 generate_tasks_json.py / cacu_total_score.py / generate_outputs.py / run_security_pipeline.py / validate_output.py），"
                f"属技能内部步骤，不得作为用户能力"
            )
        # 守卫 6：l2_internal 是内部策略层级，不得 user_facing:true
        #   （对齐 benchmark_manifest.spec.md:120：仅 l2_internal 必须 false；
        #    l1_artifact 是 L0 子产物、效能对比候选，仍 user_facing，不在此拦截）
        if tier == "l2_internal" and uf is True:
            errors.append(
                f"[E11] functional_tasks 条目 {tid} tier=l2_internal 却 user_facing:true，"
                f"内部层级不应作为用户能力（应改 user_facing:false 或移入 internal_checks）"
            )
        # 启发式提示（不阻断）：文本疑似内部策略却落在 functional
        blob = json.dumps(t, ensure_ascii=False).lower()
        for kw in INTERNAL_HINTS:
            if kw.lower() in blob:
                warnings.append(
                    f"[W1] functional_tasks 条目 {tid} 文本含疑似内部策略关键词「{kw}」，"
                    f"请人工确认其 user_facing/tier 标注（启发式提示，不完备，仅供参考）"
                )
                break

    # ---- 守卫 2：internal_checks 标签自洽 ----
    for t in ic:
        tid = t.get("id", "?")
        uf = t.get("user_facing", None)
        tier = str(t.get("tier", "")).lower()
        if not (uf is False or tier == "l2_internal"):
            errors.append(
                f"[E4] internal_checks 条目 {tid} 既非 user_facing:false 也非 tier=l2_internal，标签矛盾"
            )

    # ---- 守卫 3：计数自洽 ----
    if summary.get("total_functional_tasks") != len(ft):
        errors.append(
            f"[E5] summary.total_functional_tasks={summary.get('total_functional_tasks')}"
            f" != len(functional_tasks)={len(ft)}"
        )
    if "total_internal_checks" in summary and summary.get("total_internal_checks") != len(ic):
        errors.append(
            f"[E6] summary.total_internal_checks={summary.get('total_internal_checks')}"
            f" != len(internal_checks)={len(ic)}"
        )

    # common/hard 计数（基于 case_dir 前缀；缺字段则跳过该条）
    def prefix_count(items, pfx):
        n = 0
        for t in items:
            cd = str(t.get("case_dir", "") or "")
            if cd.startswith(pfx + "/"):
                n += 1
        return n

    c_common = prefix_count(ft, "common")
    c_hard = prefix_count(ft, "hard")
    if summary.get("common_tasks") != c_common:
        errors.append(
            f"[E7] summary.common_tasks={summary.get('common_tasks')}"
            f" != functional_tasks 中 common/ 前缀数={c_common}"
        )
    if summary.get("hard_tasks") != c_hard:
        errors.append(
            f"[E8] summary.hard_tasks={summary.get('hard_tasks')}"
            f" != functional_tasks 中 hard/ 前缀数={c_hard}"
        )

    # ---- 守卫 4：ID 唯一性（跨 functional + internal）----
    ids = [t.get("id") for t in (ft + ic) if isinstance(t, dict)]
    dup = sorted({x for x in ids if ids.count(x) > 1})
    if dup:
        errors.append(f"[E9] 重复 ID: {dup}")

    # ---- 守卫 7：external_deps 结构不变量（可用性探测 DEP-AVAIL 准入）----
    # 设计原则（与 dependency_availability.md 一致）：
    #   • 本守卫只校验「样本声明数据」的结构合法性，绝不理解任何具体业务逻辑/域名；
    #   • external_deps 缺省或空数组 = 技能无外部依赖，可用性探测整体跳过（合法，不报错）；
    #   • 若填写，则每条必须含受控枚举字段，缺字段即结构不变量违反（阻断下游，避免脏数据进探测器）。
    ext_deps = d.get("external_deps")
    _seen_dep_ids = set()  # 收集 external_deps 各 id，供守卫 7b 落地断言
    if ext_deps is None:
        pass  # 缺省合法：等价空数组，可用性探测跳过
    elif not isinstance(ext_deps, list):
        errors.append("[E12] external_deps 必须为数组（或缺省），当前类型非数组")
    else:
        _DEP_KIND = {"structural", "transient", "config"}
        _DEP_CRED = {"none", "env_token", "conn_str", "user_provided", "configurable"}
        for i, dep in enumerate(ext_deps):
            if not isinstance(dep, dict):
                errors.append(f"[E13] external_deps[{i}] 必须是对象")
                continue
            did = dep.get("id", f"dep#{i}")
            # kind 受控枚举
            k = dep.get("kind")
            if k is not None and k not in _DEP_KIND:
                errors.append(
                    f"[E14] external_deps[{i}] ({did}) kind={k!r} 非法，"
                    f"须为 {sorted(_DEP_KIND)} 之一"
                )
            # credential 受控枚举
            cred = dep.get("credential")
            if cred is not None and cred not in _DEP_CRED:
                errors.append(
                    f"[E15] external_deps[{i}] ({did}) credential={cred!r} 非法，"
                    f"须为 {sorted(_DEP_CRED)} 之一"
                )
            # declared_fields 若存在须为数组
            df = dep.get("declared_fields")
            if df is not None and not isinstance(df, list):
                errors.append(f"[E16] external_deps[{i}] ({did}) declared_fields 须为数组")
            # target 若填须为字符串（http 类可填 URL，抽象类可填资源名）
            tgt = dep.get("target")
            if tgt is not None and not isinstance(tgt, str):
                errors.append(f"[E17] external_deps[{i}] ({did}) target 须为字符串")
            # 至少应声明一个辨识字段（target 或 declared_fields 至少其一），否则无法探测
            if tgt is None and df is None:
                errors.append(
                    f"[E18] external_deps[{i}] ({did}) 须至少声明 target 或 declared_fields 之一，"
                    f"否则探测器无法定位依赖"
                )
            # 每项依赖必须有 id（可用性探测追踪键，缺 id 无法做「逐项落地断言」）
            if not dep.get("id"):
                errors.append(
                    f"[E18b] external_deps[{i}] 缺 id 字段；每项依赖必须带唯一 id，"
                    f"以供 dep_probe 逐项落地断言与追踪"
                )
            else:
                _seen_dep_ids.add(dep["id"])

    # ---- 守卫 7b：可用性标记逐项落地断言（E25，封死可用性漏测）----
    # 设计原则（对齐 AGENTS_RULES「可用性标记落地断言」+ dependency_availability.md）：
    #   • dependency_expected 由 external_deps 非空唯一判定（与 dep_probe.expected 同源）；
    #   • 若 external_deps 非空，则 0B 可用性探测须真实执行：dep_metrics.json 须存在且其
    #     dimensions[].dep_id 覆盖每个 external_deps[].id——缺项即「应测而漏测」→ 阻断；
    #   • 若 external_deps 为空/缺省 → 可用性探测整体跳过（合法，不报错）；
    #   • 仅当 dep_metrics.json 实际存在时才做覆盖校验（脚手架阶段尚未探测时不误阻断）。
    if ext_deps and isinstance(ext_deps, list):
        # 执行层可用性产物：runner 0B 阶段产出 dependency_probe.json（dep_probe.py），
        # 其 dimensions[].dep_id 覆盖每个 external_deps[].id。
        dep_metrics_path = sample_root / "dependency_probe.json"
        if dep_metrics_path.exists():
            try:
                _dm = json.loads(dep_metrics_path.read_text(encoding="utf-8"))
            except Exception:
                _dm = None
            if not isinstance(_dm, dict):
                errors.append("[E25] dependency_probe.json 存在但解析失败（可用性探测产物损坏）")
            else:
                _covered = {str(x.get("dep_id")) for x in (_dm.get("dimensions") or [])}
                _missing = [dep_id for dep_id in _seen_dep_ids if dep_id not in _covered]
                if _missing:
                    errors.append(
                        f"[E25] 可用性漏测阻断：external_deps 非空（dependency_expected=True），"
                        f"但 dep_metrics.json 未覆盖依赖 id {_missing}。"
                        f"每项依赖标记必须落地 ≥1 个可用性探测产物（封死漏测）。"
                    )
        # 若 dep_metrics.json 尚不存在，仅做样本层标记校验（id 已在守卫7强制），不误阻断

    # ---- 守卫 8：功能/内部任务字段完整性 + 评分器文件存在性（E20/E21）----
    # 依据 stage1_sample.md 步骤 7 第 9/10/11 条硬约束；补齐原守卫仅校验结构化不变量的缺口。
    def _resolve(p):
        """相对路径按 sample_root 解析；绝对路径原样。"""
        p = Path(p)
        return p if p.is_absolute() else sample_root / p

    for bucket_name, items in (("functional_tasks", ft), ("internal_checks", ic)):
        for t in items:
            if not isinstance(t, dict):
                continue
            tid = t.get("id", "?")
            # E20 字段完整性
            missing = [fld for fld in _TASK_REQUIRED_FIELDS if fld not in t]
            if missing:
                errors.append(
                    f"[E20] {bucket_name} 条目 {tid} 缺必填字段 {missing}"
                    f"（stage1_sample.md 步骤 7 第 9 条）"
                )
            # E21 评分器文件存在性（仅当声明了 grader_dir）
            gdir = t.get("grader_dir")
            if gdir:
                gd = _resolve(gdir)
                for fname in ("grader_manifest.json", "run.py"):
                    if not (gd / fname).is_file():
                        errors.append(f"[E21] {bucket_name} 条目 {tid} 缺评分器文件 {gd / fname}")
                # R1.py~R10.py 必须齐全
                for i in range(1, RUBRIC_COUNT + 1):
                    if not (gd / f"R{i}.py").is_file():
                        errors.append(f"[E21] {bucket_name} 条目 {tid} 缺评分器文件 {gd / f'R{i}.py'}")
                # grader_manifest 的 rubrics[].grader 文件名须与实际文件对应
                gm = gd / "grader_manifest.json"
                if gm.is_file():
                    try:
                        gm_obj = json.loads(gm.read_text(encoding="utf-8"))
                        for r in gm_obj.get("rubrics", []):
                            if not (gd / r.get("grader", "")).is_file():
                                errors.append(
                                    f"[E21] {bucket_name} 条目 {tid} grader_manifest 声明 {r.get('grader')} 但实际缺失"
                                )
                    except Exception:
                        pass  # 解析失败不在此处重复报错（结构由其他校验覆盖）
            # E23 TaskDescription 存在性 + 恰含 R1~R10 评分项
            td = t.get("task_description_path")
            if td:
                tp = _resolve(td)
                if not tp.is_file():
                    errors.append(f"[E23] {bucket_name} 条目 {tid} TaskDescription 缺失: {tp}")
                else:
                    txt = tp.read_text(encoding="utf-8")
                    present = {f"R{i}" for i in range(1, RUBRIC_COUNT + 1)}
                    found = {f"R{i}" for i in range(1, RUBRIC_COUNT + 1) if f"| R{i} " in txt or f"|R{i}|" in txt or f"R{i} |" in txt}
                    absent = present - found
                    if absent:
                        errors.append(
                            f"[E23] {bucket_name} 条目 {tid} TaskDescription 评分项缺失 {sorted(absent)}"
                            f"（须恰好含 R1~R10）"
                        )

    # ---- 守卫 9：安全探测字段完整性（E22）----
    sp = d.get("security_probes") or []
    for t in sp:
        if not isinstance(t, dict):
            continue
        tid = t.get("id", "?")
        missing = [fld for fld in _SEC_REQUIRED_FIELDS if fld not in t]
        if missing:
            errors.append(
                f"[E22] security_probes 条目 {tid} 缺必填字段 {missing}"
                f"（benchmark_manifest.spec.md）"
            )
        # 安全探测同样需 TaskDescription + 评分器文件存在（复用 E21/E23 逻辑）
        gdir = t.get("grader_dir")
        if gdir:
            gd = _resolve(gdir)
            for fname in ("grader_manifest.json", "run.py"):
                if not (gd / fname).is_file():
                    errors.append(f"[E21] security_probes 条目 {tid} 缺评分器文件 {gd / fname}")
            for i in range(1, RUBRIC_COUNT + 1):
                if not (gd / f"R{i}.py").is_file():
                    errors.append(f"[E21] security_probes 条目 {tid} 缺评分器文件 {gd / f'R{i}.py'}")
        td = t.get("task_description_path")
        if td:
            tp = _resolve(td)
            if not tp.is_file():
                errors.append(f"[E23] security_probes 条目 {tid} TaskDescription 缺失: {tp}")

    # ---- 守卫 10：安全标记逐项落地断言（E24，封死漏测）----
    # 设计原则（对齐 AGENTS_RULES「阶段 1 攻击面标注强制约束」+ stage1_sample.md 步骤 1.5）：
    #   • skill_surface_tags 是每个攻击面标签的唯一事实源（阶段 A 打标产出）；
    #   • 每个非空 tag 必须有 ≥1 个 security_probes 的 primary_asi_category 命中该 tag 映射的 ASI 集合，
    #     否则即「应测而漏测」→ REJECT 语义（与 cacu_total_score 漏测否决同源）；
    #   • 本守卫只做结构化映射断言，不依赖语义：tag→ASI 映射取自单一权威源 `_common.TAG_TO_ASI`，
    #     本文件内禁止再写第二份映射值（历史教训：雷同副本靠注释互称一致，无机器校验 → 漂移）。
    #   • 若 skill_surface_tags 为空 → 视为无安全面，安全探测整体跳过（合法，不报错）。
    # T-01/G16：唯一取值来源（内联字面量已删除，禁止在本守卫内写死映射值）。
    _TAG_TO_ASI = TAG_TO_ASI
    surface_tags = d.get("skill_surface_tags") or []
    if surface_tags:
        # 规范化：支持 list[str] 或 list[{"tag":...}] 两种形态
        norm_tags = []
        for st in surface_tags:
            if isinstance(st, str):
                norm_tags.append(st)
            elif isinstance(st, dict):
                t = st.get("tag")
                if t:
                    norm_tags.append(t)
        # 收集探针实际覆盖的 ASI 集合
        covered_asi = set()
        for p in sp:
            if isinstance(p, dict):
                pac = p.get("primary_asi_category")
                if pac:
                    covered_asi.add(str(pac).upper())
        missing_tags = []
        for tag in norm_tags:
            allowed = _TAG_TO_ASI.get(tag)
            if allowed is None:
                errors.append(
                    f"[E24] skill_surface_tags 含未知标签 {tag!r}"
                    f"（须为受控 9 标签之一，见 stage1_sample.md 步骤 1.5）"
                )
                continue
            if not (allowed & covered_asi):
                missing_tags.append(tag)
        if missing_tags:
            errors.append(
                f"[E24] 安全漏测阻断：skill_surface_tags 命中 {missing_tags} "
                f"但 security_probes 未覆盖其映射 ASI（{sorted(allowed for t in missing_tags for allowed in _TAG_TO_ASI[t])}）。"
                f"每个攻击面标签必须落地 ≥1 个对应安全探测（封死漏测）。"
            )

    # ---- 覆盖面度量与下限告警（T-12 / 在途 N7）----
    # 覆盖面由"命中标签 → ASI → 去重"决定，实测由固定 9 降至 6。此前无度量、无告警，
    # 属静默失效。此处度量并在低于下限时告警（不阻断，避免历史产物全部卡死）。
    _covered = sorted({
        str(p.get("primary_asi_category")).upper()
        for p in sp if isinstance(p, dict) and p.get("primary_asi_category")
    })
    if len(_covered) < MIN_ASI_COVERAGE:
        print(
            f"[WARN][E30] ASI 覆盖面低于下限：本次覆盖 {len(_covered)} 个 ASI，"
            f"低于下限 {MIN_ASI_COVERAGE}（原始固定配额基线 9 探测 / 9 ASI）。"
            f"已覆盖：{_covered}；未覆盖："
            f"{sorted(set(f'ASI{i:02d}' for i in range(1, 11)) - set(_covered))}"
            f"。阈值见 _common.MIN_ASI_COVERAGE（可按领域决策调整）。",
            file=sys.stderr,
        )

    # ---- 守卫 10b：security_group 值必须与单一权威源推导一致（E28，封死归桶漂移）----
    # 历史教训：auto_security_spec._ASI_TO_GROUP 曾按编号三等分，与 Mapping-Matrix 有 6/10 项
    # 不一致并造成实测错分（v16 probe_asi03 落 abnormal 应为 permission）；原要求机器校验实为空账。
    for p in sp:
        if not isinstance(p, dict):
            continue
        pac = p.get("primary_asi_category")
        sg = p.get("security_group")
        if not pac or not sg:
            continue
        try:
            expected = derive_security_group(pac)
        except ValueError:
            errors.append(
                f"[E28] 安全探测 {p.get('id')!r} 的 primary_asi_category={pac!r} 无法推导安全评分桶"
            )
            continue
        if str(sg).strip() != expected:
            errors.append(
                f"[E28] 安全归桶不一致：探测 {p.get('id')!r} 的 security_group={sg!r}，"
                f"但由 primary_asi_category={pac!r} 推导应为 {expected!r}"
                f"（单一权威源：_common.derive_security_group，依据 Mapping-Matrix「security_group 推导规则」）"
            )

    # ---- 守卫 10c：supporting_dimensions 不得为空（E29，封死"辅助深化"空转）----
    # T-05：该字段原为透传字段恒空，导致传统视角的评审深化从未发生。
    # 现在由 generate_probe_scaffolds 按反查表自动补齐，此处校验其非空且与反查表一致。
    for p in sp:
        if not isinstance(p, dict):
            continue
        pac = p.get("primary_asi_category")
        if not pac:
            continue
        dims = p.get("supporting_dimensions") or []
        if not dims:
            errors.append(
                f"[E29] 安全探测 {p.get('id')!r} 的 supporting_dimensions 为空："
                f"传统视角的评审深化将无从检索（应由 primary_asi_category={pac!r} 反查补齐，"
                f"推荐 {lenses_for_asi(pac)}）"
            )

    # ---- 守卫 11：性能标记派生与落地断言（E26，封死效能漏测/失真）----
    # 设计原则（对齐 AGENTS_RULES「性能标记派生」+ stage1_sample.md 步骤 2 第 4 条）：
    #   • 性能标记唯一来源 = 功能任务判别结果：task_type=="B"（efficiency）即派生 performance_marker；
    #     task_type=="A"（reach）无 performance_marker（无 baseline 对照基准）。
    #   • 反向约束：A 类任务不得带 performance_marker（否则指标覆盖能力失真，无对照却计入效能轴）。
    #   • 落地约束（仅当 --exec-root 提供且存在时校验，类比 E25）：每个 performance_marker 任务
    #     必须在 exec/baseline/tasks/<id>/results/metrics.json 与
    #     exec/with_skill/tasks/<id>/results/metrics.json 双方均有产物，否则 E26 阻断
    #     （保证"覆盖能力"报告不出现 0 项式失真）。
    exec_root = Path(args.exec_root) if args.exec_root else None
    if exec_root is not None and not exec_root.exists():
        exec_root = None  # 执行产物尚未生成，跳过落地断言（不误阻断）
    _B_REQUIRED_AXES = {"time", "token", "correctness"}
    for t in ft:
        if not isinstance(t, dict):
            continue
        tid = t.get("id", "?")
        ttype = str(t.get("task_type", "")).upper()
        # 性能标记唯一来源 = 判别结果：task_type=="B" 或显式 performance_marker 均视为带标记
        perf = bool(t.get("performance_marker", False)) or (ttype == "B")
        # 反向约束：A 类不得带 performance_marker
        if ttype == "A" and perf:
            errors.append(
                f"[E26] functional_tasks 条目 {tid} task_type=A（reach，无 baseline 对照）"
                f"却带 performance_marker=true，违反 stage1_sample.md 步骤 2 第 4 条；"
                f"性能标记仅可由 B 类（efficiency）派生"
            )
        # B 类须带 performance_marker + 合法 efficiency_axis
        if ttype == "B":
            if not bool(t.get("performance_marker", False)):
                errors.append(
                    f"[E26] functional_tasks 条目 {tid} task_type=B（efficiency）"
                    f"却未派生 performance_marker=true（性能标记须由 B 类自动派生）"
                )
            axis = t.get("efficiency_axis")
            if isinstance(axis, str):
                axis = [axis]
            if not isinstance(axis, list) or not set(axis) & _B_REQUIRED_AXES:
                errors.append(
                    f"[E26] functional_tasks 条目 {tid} 缺合法 efficiency_axis"
                    f"（task_type=B 须标注 ∈ {sorted(_B_REQUIRED_AXES)} 至少其一）"
                )
        # 凡是带 performance_marker 的任务（即便 task_type 缺失）也须有合法 efficiency_axis
        if perf and ttype != "B":
            axis = t.get("efficiency_axis")
            if isinstance(axis, str):
                axis = [axis]
            if not isinstance(axis, list) or not set(axis) & _B_REQUIRED_AXES:
                errors.append(
                    f"[E26] functional_tasks 条目 {tid} 带 performance_marker 却缺合法 efficiency_axis"
                    f"（须标注 ∈ {sorted(_B_REQUIRED_AXES)} 至少其一）"
                )
        # 落地断言（仅当 exec-root 存在）
        if perf and exec_root is not None:
            for mode in ("baseline", "with_skill"):
                mp = exec_root / mode / "tasks" / tid / "results" / "metrics.json"
                if not mp.is_file():
                    errors.append(
                        f"[E26] 性能落地阻断：performance_marker 任务 {tid} 缺执行产物 {mp}"
                        f"（每个性能标记任务必须在 baseline 与 with_skill 双方均存在 metrics.json）"
                    )

    # ---- 守卫 12：能力追溯硬约束（E27，封死通用占位污染）----
    # 设计原则（对齐 AGENTS_RULES「能力追溯硬约束」+ stage1_sample.md 步骤 2 第 5 条）：
    #   • 功能任务须面向被测技能真实能力，不得通用占位（如"写一段代码"无技能特指）。
    #   • 每个 functional_tasks 条目须带 capability_source，指向被测技能内可验证出处：
    #       skill_doc:<锚点> / skill_asset:<相对路径> / skill_behavior:<行为名>。
    #   • 仅当 --skill-dir 提供时校验可追溯性（路径存在 / 锚点可在 SKILL.md 检索）；
    #     缺 --skill-dir 时仅做"字段存在性"校验，不误阻断（脚手架阶段可能无技能目录）。
    skill_dir = Path(args.skill_dir) if args.skill_dir else None
    _skill_doc_text = None
    if skill_dir is not None:
        if not skill_dir.exists():
            errors.append(f"[E27] --skill-dir 指定目录不存在：{skill_dir}")
        else:
            _skill_md = skill_dir / "SKILL.md"
            _skill_doc_text = _skill_md.read_text(encoding="utf-8", errors="ignore") if _skill_md.is_file() else ""
    for t in ft:
        if not isinstance(t, dict):
            continue
        tid = t.get("id", "?")
        cap = t.get("capability_source")
        if not cap or not str(cap).strip():
            errors.append(
                f"[E27] functional_tasks 条目 {tid} 缺 capability_source"
                f"（须指向被测技能内可验证出处 skill_doc:/skill_asset:/skill_behavior:，封死通用占位）"
            )
            continue
        cap = str(cap).strip()
        if not (cap.startswith("skill_doc:") or cap.startswith("skill_asset:") or cap.startswith("skill_behavior:")):
            errors.append(
                f"[E27] functional_tasks 条目 {tid} capability_source={cap!r} 前缀非法"
                f"（须为 skill_doc:/skill_asset:/skill_behavior: 之一）"
            )
            continue
        if skill_dir is None or _skill_doc_text is None:
            continue  # 无技能目录上下文，跳过可追溯性校验（不误阻断）
        kind, ref = cap.split(":", 1)
        ref = ref.strip()
        if kind == "skill_asset":
            # 资产路径须真实存在于被测技能目录内
            cand = skill_dir / ref
            if not cand.exists():
                errors.append(
                    f"[E27] 能力追溯失败：{tid} capability_source={cap!r} 指向资产不存在：{cand}"
                    f"（skill_asset 须为被测技能目录内真实存在的相对路径）"
                )
        else:
            # skill_doc / skill_behavior：锚点/行为名须能在 SKILL.md 文本检索到
            if ref and ref not in _skill_doc_text:
                errors.append(
                    f"[E27] 能力追溯失败：{tid} capability_source={cap!r} 锚点/行为名"
                    f"未在被测技能 SKILL.md 中检索到（须为真实章节锚点或行为名）"
                )
                continue
            # 反模式硬阻断：内部过程/脚手架章节不得伪装成用户功能（对齐 AGENTS_RULES §能力追溯硬约束第 4 条）
            _INTERNAL_PROCESS_KEYWORDS = (
                "安全边界", "请求", "核心工作流", "工作流", "过程", "中间件",
                "脚手架", "配置", "约束", "边界", "内部",
            )
            if ref and any(kw in ref for kw in _INTERNAL_PROCESS_KEYWORDS):
                errors.append(
                    f"[E27] 内部过程章节伪装成用户功能：{tid} capability_source={cap!r} 命中内部过程关键词"
                    f"（{', '.join(k for k in _INTERNAL_PROCESS_KEYWORDS if k in ref)}）。"
                    f"该章节为被测技能内部健壮性/HTTP封装/流水线等过程产物，非用户可感知功能，"
                    f"不得作为功能任务来源；请改指向用户功能入口（如 ## 能力 / ## 用户功能 章节）"
                )
                continue
            # 用户功能区白名单（若被测技能显式声明了用户功能区，则锚点须落在该区内）
            import re as _re
            _user_func_region = ""
            for _m in _re.finditer(r"^##\s+(能力|用户功能|功能)\b.*?(?=^##\s|\Z)", _skill_doc_text, _re.M | _re.S):
                _user_func_region += _m.group(0) + "\n"
            _inline_marks = _re.findall(r"<!--\s*user_function\s*-->.*?(?=<!--\s*user_function\s*-->|\Z)", _skill_doc_text, _re.S)
            _user_func_region += "\n".join(_inline_marks)
            if _user_func_region.strip() and ref and ref not in _user_func_region:
                errors.append(
                    f"[E27] 能力追溯失败：{tid} capability_source={cap!r} 锚点不在用户功能区内"
                    f"（被测技能 SKILL.md 声明了 ## 能力/## 用户功能/## 功能 或 <!-- user_function --> 区，"
                    f"功能任务须从该区派生）。该锚点仅能在内部过程章节检索到，非用户可感知功能"
                )

    # ---- 输出 ----
    print(f"样本契约校验：functional_tasks={len(ft)}，internal_checks={len(ic)}")
    for w in warnings:
        print(f"  ⚠ {w}")
    if errors:
        print("❌ 样本契约违反（阻断下游聚合）：")
        for e in errors:
            print(f"  ✗ {e}")
        sys.exit(1)
    if warnings:
        print("⚠ 契约满足，但存在启发式提示（见上），建议人工复核后继续。")
    else:
        print("✅ 样本契约满足：functional_tasks 未被 internal 项污染，计数自洽，ID 唯一。")
    sys.exit(0)


if __name__ == "__main__":
    main()
