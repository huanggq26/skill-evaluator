#!/usr/bin/env bash
# ============================================================
# skill-evaluator · 单点评测管线 runner
# 把阶段 0（质量门禁/开始阶段）与阶段 4（最后阶段聚合）编排合并为「一次范围授权」运行；
# 中间阶段 1/2/3（样本设计、基线执行、带技能执行）由 AI 评测执行者（同一会话）接续完成，
# runner 仅负责自动阶段 + 脚手架生成，并在缺中间产物时给出明确「下一步该做」指引。
#
# 范围严格限定在《范围与安全契约》(references/scope_contract.md)：
#   只读被测技能 / 仅写评测工作区 / 仅运行本 skill 自带脚本 / 不联网不删不改系统。
#
# 三种测评流程（顶层 --mode，默认 full）：
#   --mode start   只进行开始阶段（0）测评，输出开始阶段报告（质量预检报告）。
#   --mode full    全流程：自动跑 开始阶段→阶段1→阶段2/3(真实驱动被测技能)→阶段5(安全采集)→最后阶段聚合，
#                  产出 开始阶段报告 + 最后阶段报告（benchmark/problem）。阶段 2/3/5 由 exec_*.py 联网真实执行，
#                  仅当被测技能不可达等真实失败时 exit 1 报错（不再静默停等人工）。
#   --mode resume  已执行开始阶段，继续 阶段1→最后阶段，产出 最后阶段报告（断点续跑用）。
#
# 用法：
#   bash scripts/run_eval_pipeline.sh --mode start
#   bash scripts/run_eval_pipeline.sh --mode full
#   bash scripts/run_eval_pipeline.sh --mode resume
#   bash scripts/run_eval_pipeline.sh --mode full --scaffold-spec /path/spec.json
#   bash scripts/run_eval_pipeline.sh --mode resume --skip-exec-check   # 仅校验样本（CI）
#   bash scripts/run_eval_pipeline.sh --reset --mode full              # 清空工作区后跑全流程
# ============================================================
set -euo pipefail

# ---- 路径参数：可被环境变量或命令行覆盖，默认指向当前评测工作区 ----
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_SKILL="${TARGET_SKILL:-${SKILL_DIR}}"
DEFAULT_OUTPUT_DIR="${HOME}/Downloads"
EVAL_RESULTS_BASE="${SKILL_EVALUATOR_RESULTS_ROOT:-${DEFAULT_OUTPUT_DIR}/skill-evaluator_results}"
SCAFFOLD_SPEC="${SCAFFOLD_SPEC:-}"   # 可选：提供则先生成安全脚手架（阶段 1）
SECURITY_SPEC="${SECURITY_SPEC:-}"   # 可选：安全探测声明 JSON
MODE="${MODE:-full}"                 # start | full | resume
RESET="${RESET:-0}"
SKIP_EXEC_CHECK="${SKIP_EXEC_CHECK:-0}"
PROJECT_STATE="${PROJECT_STATE:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skill-dir)     TARGET_SKILL="$2"; _EXPLICIT_SKILL_DIR=1; shift 2;;
    --results-root)  RESULTS_ROOT="$2"; shift 2;;
    --scaffold-spec) SCAFFOLD_SPEC="$2"; shift 2;;   # 指向 functional_tasks JSONL（build_sample_pack 主输入）
    --security-spec) SECURITY_SPEC="$2"; shift 2;;   # 可选：安全探测声明 JSON
    --mode)          MODE="$2"; shift 2;;
    --reset)         RESET=1; shift;;
    --skip-exec-check) SKIP_EXEC_CHECK=1; shift;;
    --project-state) PROJECT_STATE="$2"; shift 2;;
    *) echo "未知参数: $1" >&2; exit 2;;
  esac
done

# 校验 mode
case "$MODE" in
  start|full|resume) ;;
  *) echo "❌ 非法 --mode=$MODE（应为 start|full|resume）" >&2; exit 2;;
esac

# ---- 防误用守卫：默认被测技能指向自身时醒目提示 ----
# 根因：TARGET_SKILL 缺省 = SKILL_DIR（评测本技能自身）。在 cwd 为本技能目录（调试态）下
# 直接 --mode full 易误把"评测自己"当成"评测其他技能"，导致 0C 抽取失败（自身无用户意图路由表）。
# 显式传入 --skill-dir 即视为刻意评测自身，不再提示。
if [[ "$TARGET_SKILL" == "$SKILL_DIR" && -z "${_EXPLICIT_SKILL_DIR:-}" ]]; then
  echo "⚠️ 注意：未显式传入 --skill-dir，默认被测技能 = 本评测技能自身（$SKILL_DIR）。" >&2
  echo "   若你要评测【其他技能】，请加：--skill-dir <被测技能目录>。" >&2
  echo "   确认评测自身请忽略此提示（调试态自测场景）。" >&2
fi

# RESULTS_ROOT = 物理根（不含 skill_name），作为下游脚本 --exec-root / --samples-root 入参
# WS = 本技能评测工作区根 = RESULTS_ROOT/SKILL_NAME
RESULTS_ROOT="${RESULTS_ROOT:-${EVAL_RESULTS_BASE}}"

# ---- 运行状态自动判定 ----
if [[ -z "${PROJECT_STATE:-}" ]]; then
  PROJECT_STATE="$(python3 "$SKILL_DIR/scripts/_project_state.py" 2>/dev/null || echo production)"
fi
if [[ "$PROJECT_STATE" == "debug" ]]; then
  echo "▶ 运行状态：debug（调试态 · 以项目方式打开，允许自优化/记会话日志）"
else
  echo "▶ 运行状态：production（发布态 · 安装为技能，只读自身/不记会话日志）"
fi

SKILL_NAME="$(basename "$TARGET_SKILL")"
WS="$RESULTS_ROOT/$SKILL_NAME"

# ---- 可选：清空评测工作区（**仅本次评测对象的子目录 $WS**）----
# 重要：RESULTS_ROOT 下按技能名分子目录（$RESULTS_ROOT/<技能名>），各技能的评测结果并存。
# 故 --reset 只能删**本次被测技能**的子目录，**绝不可删整个 RESULTS_ROOT**——
# 否则评测 A 技能时会把 B、C 技能的既往评测结果一并清空（真实数据丢失，且不可再生）。
# 位置要求：必须在本段（SKILL_NAME/WS 定义之后）执行，才能拿到 $WS。
if [[ "$RESET" == "1" ]]; then
  echo "▶ --reset：清空本次评测对象的工作区子目录 $WS"
  echo "   （仅清 $SKILL_NAME 一个子目录；RESULTS_ROOT 下其他技能的评测结果**保留**；可重跑再生，不删被测技能/工作区外）"
  rm -rf "$WS"
fi
SAMPLE_DIR="$WS/sample"
EXEC_DIR="$WS/exec"
SPEC_DIR="$WS/spec"
QUALITY_DIR="$WS/quality"
QUALITY_REPORT="$QUALITY_DIR/${SKILL_NAME}评测.md"
# 阶段 0 中间产物统一归入 results/ 子目录（类比 spec/results），顶层仅留最终报告
QUALITY_RESULTS_DIR="$QUALITY_DIR/results"
QUALITY_SCORE_OUT="$QUALITY_RESULTS_DIR/quality_score.json"

[[ -d "$TARGET_SKILL" ]] || { echo "❌ 被测技能目录不存在: $TARGET_SKILL" >&2; exit 1; }
mkdir -p "$RESULTS_ROOT"

echo "=================================================="
echo " skill-evaluator 评测管线（单点授权运行）"
echo "--------------------------------------------------"
echo " 本次授权即确认以下《范围与安全契约》："
echo "   • 只读被测技能 : $TARGET_SKILL （不修改/不删除）"
echo "   • 仅写评测工作区: $RESULTS_ROOT （sample/exec/spec/quality）"
echo "   • 仅运行本 skill 自带脚本 + 被测技能自身"
echo "   • 不联网 / 不删用户文件 / 不改系统配置或凭据"
echo "   • 不写工作区外、不写被测技能目录"
echo "   • 运行模式 --mode=$MODE"
echo "   • --reset 时仅清空本次被测技能的子目录 $WS（可重跑再生），其他技能结果保留，不删工作区外/被测技能"
echo "   任何越界操作将被拒绝并报告"
echo "=================================================="

cd "$SKILL_DIR"

run_step() {
  local label="$1"; shift
  echo ""
  echo "▶ $label"
  "$@"
  local rc=$?
  if [[ $rc -ne 0 ]]; then
    echo "❌ 步骤失败（exit=$rc），中止管线" >&2
    exit $rc
  fi
  return 0
}

# ============================================================
# 阶段 0 · 开始阶段质量门禁（独立函数，start/full 调用）
# ============================================================
run_stage0() {
  mkdir -p "$QUALITY_DIR" "$QUALITY_RESULTS_DIR"
  echo ""
  echo "▶ [开始阶段] 0/a extract_stats (客观统计 → $QUALITY_RESULTS_DIR/extract_stats.json)"
  python3 scripts/extract_stats.py "$TARGET_SKILL" > "$QUALITY_RESULTS_DIR/extract_stats.json"

  echo "▶ [开始阶段] 0/a+ build_objective_data (客观维度级格式数据)"
  python3 scripts/build_objective_data.py \
    --stats "$QUALITY_RESULTS_DIR/extract_stats.json" \
    --skill-root "$TARGET_SKILL" \
    --out "$QUALITY_RESULTS_DIR/objective_data.json" || true

  VALIDATE_ARGS=(--objective "$QUALITY_RESULTS_DIR/objective_data.json")
  VALIDATE_ARGS+=(--quality-score-out "$QUALITY_SCORE_OUT")
  TPL="$SKILL_DIR/assets/report.template.md"
  [[ -f "$TPL" ]] && VALIDATE_ARGS+=(--template "$TPL")
  PLAN="$QUALITY_RESULTS_DIR/${SKILL_NAME}_eval_plan.md"
  [[ -f "$PLAN" ]] && VALIDATE_ARGS+=(--plan "$PLAN")
  run_step "[开始阶段] 0/b validate_quality_report (0A 客观数据门禁)" \
    python3 scripts/validate_quality_report.py "${VALIDATE_ARGS[@]}" || true

  # 阶段 0B 可用性预检
  mkdir -p "$SAMPLE_DIR"
  # 注：0B 探测用【临时预检 manifest】承载 external_deps，绝不写正式 benchmark_manifest.json
  # （正式 manifest 是阶段 1 产物，避免 start 模式污染导致后续 full/resume 误判"样本已存在"）。
  PREFILE_MANIFEST="$SAMPLE_DIR/_preflight_manifest.json"
  run_step "[开始阶段] 0B/1 extract_deps (依赖提取)" \
    python3 scripts/extract_deps.py \
      --skill-dir "$TARGET_SKILL" \
      --manifest "$PREFILE_MANIFEST" \
      --output "$SAMPLE_DIR/dependency_extract.json" \
      --write-manifest

  DEP_PROBE_JSON="$SAMPLE_DIR/dependency_probe.json"
  run_step "[开始阶段] 0B/2 dep_probe (外部依赖可用性探测)" \
    python3 scripts/dep_probe.py \
      --manifest "$PREFILE_MANIFEST" \
      --output "$DEP_PROBE_JSON"

  if [[ -f "$DEP_PROBE_JSON" ]]; then
    echo "▶ [开始阶段] 0B/3 合并可用性客观数据 → objective_data.json"
    python3 scripts/build_objective_data.py \
      --stats "$QUALITY_RESULTS_DIR/extract_stats.json" \
      --probe "$DEP_PROBE_JSON" \
      --skill-root "$TARGET_SKILL" \
      --out "$QUALITY_RESULTS_DIR/objective_data.json"
  fi

  if [[ -f "$DEP_PROBE_JSON" ]]; then
    BLOCKING=$(python3 -c "import json,sys; d=json.load(open('$DEP_PROBE_JSON')); print('1' if d.get('blocking') else '0')" 2>/dev/null || echo 0)
    if [[ "$BLOCKING" == "1" ]]; then
      echo "⛔ [开始阶段] 0B 可用性探测发现被测技能契约型结构性缺陷（技能自身问题），按预检闸门拦截：中止后续阶段 1–4。" >&2
      echo "   客观数据已落盘：$QUALITY_RESULTS_DIR/objective_data.json" >&2
      echo "   开始阶段报告已落盘：$QUALITY_REPORT" >&2
      exit 1
    fi
  fi

  SUBJ_JSON="$QUALITY_RESULTS_DIR/subjective.json"
  if [[ ! -f "$SUBJ_JSON" ]]; then
    echo "  ⚠ 未检测到 subjective.json（AI 未回填主观维度），自动生成 advisory 复核提示（非裁定）"
    python3 scripts/auto_subjective.py \
      --stats "$QUALITY_RESULTS_DIR/extract_stats.json" \
      --template "$SKILL_DIR/assets/report.template.md" \
      --probe "${DEP_PROBE_JSON:-}" \
      --skill-root "$TARGET_SKILL" \
      --out "$SUBJ_JSON"

    # ── P7：AI 裁定检查点 ──────────────────────────────────────────────────
    # 主观维度（含功能表的服务场景归纳）本质是**语义判断**，不可脚本化：
    # 脚本自动填充等同于编造结论（违反不臆造纪律），故必须由 AI 裁定。
    # 此处生成待裁定清单，明确告知 AI 需填什么、依据材料在哪、填后如何重渲染。
    # 流程**不阻塞**（继续跑完），未裁定的维度在报告中标注「待 AI 归纳」。
    PENDING_LIST="$QUALITY_RESULTS_DIR/PENDING_AI_ADJUDICATION.md"
    python3 - "$SUBJ_JSON" "$PENDING_LIST" <<'PYEOF'
import json, sys
subj_path, out_path = sys.argv[1], sys.argv[2]
try:
    data = json.load(open(subj_path, encoding="utf-8"))
except Exception as e:
    print(f"读取 subjective.json 失败：{e}", file=sys.stderr); sys.exit(0)
pending = [(n, v) for n, v in data.items()
           if isinstance(v, dict) and v.get("skipped")]
lines = ["# 待 AI 裁定清单（P7）", "",
    "> 以下主观维度需 **AI 语义裁定**后写入 `subjective.json`。",
    "> 脚本只提供客观线索与依据材料，**不代为裁定**（自动填充等同编造结论）。",
    "> 功能表（function_table）须归纳**服务场景**（技能为用户做什么），",
    "> 依据层次：①frontmatter description → ②When to Use → ③过程中的服务声明；",
    "> 注意 `--mode start` 这类是**触发方式**，不是服务名。", "",
    f"待裁定维度共 **{len(pending)}** 个：", ""]
for name, v in pending:
    lines.append(f"## `{name}`")
    reason = str(v.get("skip_reason") or "").strip()
    if reason:
        for ln in reason.splitlines():
            lines.append(f"> {ln}" if ln.strip() else ">")
    lines.append("")
lines += ["---", "", "## 填写后如何生效", "",
    "裁定完成并写入 `subjective.json` 后，重跑合并与渲染即可（无需重跑评测）：", "",
    "```bash",
    "python3 scripts/merge_report_data.py \\",
    "  --objective <RESULTS>/quality/results/objective_data.json \\",
    "  --subjective <RESULTS>/quality/results/subjective.json \\",
    "  --template assets/report.template.md \\",
    "  --functional-tasks <RESULTS>/sample/functional_tasks.generated.jsonl \\",
    "  --out <RESULTS>/quality/results/report_data.json",
    "python3 scripts/render_report.py \\",
    "  --data <RESULTS>/quality/results/report_data.json \\",
    "  --template assets/report.template.md \\",
    "  --out <RESULTS>/quality/<技能名>评测.md",
    "```"]
open(out_path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
print(f"  📋 待裁定清单已生成：{out_path}（{len(pending)} 个主观维度待 AI 裁定）")
PYEOF
    echo "  ℹ 主观维度需 AI 语义裁定（不可脚本化）；未裁定维度在报告中标注「待 AI 归纳」" >&2
  fi
  # 阶段 0C：自动抽取「被测技能用户功能清单」（过程文件，落工作区，受 R6.1/E27 同源规则约束）
  # 这是评测过程文件，由本步理解被测技能后产生；删工作区重跑会在此重新正确产出，不依赖外部持久文件。
  run_step "[开始阶段] 0/c+ extract_functional_tasks (自动抽取用户功能清单 → $SAMPLE_DIR/functional_tasks.generated.jsonl)" \
    python3 scripts/extract_functional_tasks.py \
      --skill-dir "$TARGET_SKILL" \
      --out "$SAMPLE_DIR/functional_tasks.generated.jsonl" || {
        echo "⛔ 阶段0C 抽取用户功能清单失败。" >&2
        echo "   说明：抽取按序尝试 ①用户功能区/路由表 → ②L0 技能目标章节 → ③全文归纳 → ④保底提取；" >&2
        echo "   走到此处意味着上述四层均未产出合法功能（正常技能必然有对外服务职能，属异常）。" >&2
        echo "   常见原因：命中通用占位反模式（E27）、或 SKILL.md 正文完全无对外交付语义句。" >&2
        echo "   按纪律闸门拦截：中止后续阶段 1–4。" >&2
        exit 1
      }

  run_step "[开始阶段] 0/c 渲染质量评测报告 (merge+render)" \
    bash -c "python3 scripts/merge_report_data.py \
      --objective '$QUALITY_RESULTS_DIR/objective_data.json' \
      --subjective '$SUBJ_JSON' \
      --template '$SKILL_DIR/assets/report.template.md' \
      --functional-tasks '$SAMPLE_DIR/functional_tasks.generated.jsonl' \
      --out '$QUALITY_RESULTS_DIR/report_data.json' && \
    python3 scripts/render_report.py \
      --data '$QUALITY_RESULTS_DIR/report_data.json' \
      --template '$SKILL_DIR/assets/report.template.md' \
      --skill-name '$SKILL_NAME' \
      --out '$QUALITY_REPORT'"
  if [[ ! -f "$QUALITY_REPORT" ]]; then
    echo "❌ 开始阶段评测报告未生成：$QUALITY_REPORT" >&2
    exit 1
  fi
  echo "  ✔ 已开始阶段评测报告：$QUALITY_REPORT"
}

# ============================================================
# 阶段 1 脚手架生成（可选；full/resume 模式下若有 SCAFFOLD_SPEC 则自动生成）
# ============================================================
run_scaffold() {
  if [[ -z "$SCAFFOLD_SPEC" ]]; then
    return 0
  fi
  # ── 攻击面打标（阶段 1.5 阶段 A，强制，封死漏测）──
  # 无论是否显式传 --security-spec，都先对被测技能客观产物打标（通用扫描，不绑定技能）。
  # 这是安全维度的唯一开关：skill_surface_tags 非空 → 必须由下游生成对应探针，否则守卫10/E24 阻断。
  local surface_out="$QUALITY_DIR/results/surface_tags.json"
  run_step "[阶段1.5-A] 攻击面打标 (surface_tagging --skill-dir $TARGET_SKILL)" \
    python3 scripts/surface_tagging.py --skill-dir "$TARGET_SKILL" --output "$surface_out"
  local surface_tags=()
  if [[ -f "$surface_out" ]]; then
    local n_tags
    n_tags=$(python3 - "$surface_out" <<'PY' 2>/dev/null || echo 0
import json,sys
try: print(len(json.load(open(sys.argv[1])).get("skill_surface_tags") or []))
except Exception: print(0)
PY
)
    echo "    攻击面命中标签数: $n_tags"
    [[ "${n_tags:-0}" -gt 0 ]] && surface_tags=("--surface-tags" "$surface_out")
  fi

  # 若命中攻击面但未显式传 --security-spec，则自动生成最小安全探测声明（按映射 ASI），
  # 保证「有安全功能必生成探针」，杜绝 N/A 被宽容放行。
  if [[ ${#surface_tags[@]} -gt 0 && -z "$SECURITY_SPEC" ]]; then
    local auto_sec="$QUALITY_DIR/results/auto_security_spec.json"
    run_step "[阶段1.5-B] 自动生成安全探测声明 (按攻击面映射 ASI)" \
      python3 scripts/auto_security_spec.py --surface-tags "$surface_out" --out "$auto_sec" --sample-root "$SAMPLE_DIR" || \
      echo "    ⚠️ 自动安全探测生成失败，将交由 AI 评测执行者补充（守卫10 会校验落地）"
    [[ -f "$auto_sec" ]] && SECURITY_SPEC="$auto_sec"
  fi

  # --scaffold-spec 指向 functional_tasks JSONL（build_sample_pack 主输入）
  # --security-spec 可选，指向安全探测声明 JSON；--surface-tags 强制注入（即便为空也传递，保持事实源一致）
  local bsp_args=(
    --skill-name "$SKILL_NAME"
    --skill-dir "$TARGET_SKILL"
    --functional-tasks "$SCAFFOLD_SPEC"
    --out "$SAMPLE_DIR"
  )
  [[ -n "$SECURITY_SPEC" ]] && bsp_args+=(--security-spec "$SECURITY_SPEC")
  [[ ${#surface_tags[@]} -gt 0 ]] && bsp_args+=("${surface_tags[@]}")
  run_step "[阶段1] 生成样本脚手架 (build_sample_pack --functional-tasks $SCAFFOLD_SPEC)" \
    python3 scripts/build_sample_pack.py "${bsp_args[@]}"
}

# ============================================================
# 执行产物预检（防静默 skip 全 0 分）
# ============================================================
check_exec_artifacts() {
  local manifest="$1"
  [[ -f "$manifest" ]] || { echo "❌ 预检失败：manifest 不存在 $manifest" >&2; return 1; }
  python3 - "$manifest" "$EXEC_DIR" "$SPEC_DIR" <<'PY'
import json, sys
from pathlib import Path
manifest, exec_dir, spec_dir = sys.argv[1], sys.argv[2], sys.argv[3]
m = json.loads(Path(manifest).read_text(encoding="utf-8"))
missing = []
func = m.get("functional_tasks", [])
for t in func:
    tid = t.get("id", "?")
    for mode in ("baseline", "with_skill"):
        rd = Path(exec_dir) / mode / "tasks" / tid / "results"
        if not rd.is_dir():
            missing.append(f"functional/{mode}/{tid}  (缺 {rd})")
sec = m.get("security_probes", [])
for s in sec:
    sid = s.get("id", "?")
    # 安全探针执行产物约定落于 exec 目录（与功能任务同级结构），按 id 检索
    rd = Path(exec_dir) / "security" / "probes" / sid / "results"
    if not (rd / "grading_result.json").exists():
        missing.append(f"security/{sid}  (缺 {rd}/grading_result.json)")
if missing:
    print("❌ 执行产物预检失败：以下任务尚未由 ExecAgent/SpecAgent 执行并落盘：", file=sys.stderr)
    for x in missing:
        print(f"   - {x}", file=sys.stderr)
    print(f"共缺失 {len(missing)} 项。请先按 references/exec_common.md 驱动被测技能执行各任务，", file=sys.stderr)
    print("再重跑本管线（或加 --skip-exec-check 仅校验样本）。", file=sys.stderr)
    sys.exit(1)
print(f"✅ 执行产物预检通过：functional={len(func)} 项 × 2 模式, security={len(sec)} 项，结果齐全")
PY
}

# ============================================================
# 阶段 4 · 最后阶段聚合（独立函数，full/resume 调用）
# 进入前自动补齐缺失的执行产物（阶段 2/3 真实驱动被测技能 + 阶段 5 安全采集），
# 不再「停等人工」：阶段 2/3/5 本就由 exec_*.py 真实自动执行（联网调被测技能声明端点），
# 缺产物说明自动执行失败（被测技能不可达等真实错误），此时 exit 1 并明确报错（非静默等待）。
# ============================================================
run_stage4() {
  mkdir -p "$EXEC_DIR" "$SPEC_DIR" "$SPEC_DIR/results"

  # 样本契约守卫
  if [[ ! -f "$SAMPLE_DIR/benchmark_manifest.json" ]]; then
    echo "❌ 进入最后阶段失败：缺样本清单 $SAMPLE_DIR/benchmark_manifest.json（阶段1产物）。" >&2
    echo "   ▶ AI 评测执行者需按 references/stage1_sample.md 设计样本任务，" >&2
    echo "     并用 --scaffold-spec 生成脚手架，或运行 build_sample_pack.py 产出该 manifest。" >&2
    exit 1
  fi

  run_step "[阶段1] validate_manifest_contract (样本契约守卫)" \
    python3 scripts/validate_manifest_contract.py --manifest "$SAMPLE_DIR/benchmark_manifest.json"

  # 执行产物预检：缺则先自动执行（流程内可重跑），仍缺即真实失败退出
  if [[ "$SKIP_EXEC_CHECK" == "1" ]]; then
    echo "⚠️ 已 --skip-exec-check：跳过执行产物预检（仅校验样本，不保证已实测）"
  else
    if ! check_exec_artifacts "$SAMPLE_DIR/benchmark_manifest.json"; then
      echo "▶ 检测到执行产物缺失，自动驱动执行（ExecAgent/SpecAgent 职责，流程内完成）"
      # 功能任务：baseline + with_skill（真实驱动被测技能；--skill-dir 供通用占位解析）
      for _m in baseline with_skill; do
        run_step "[阶段2/3] exec_functional_tasks ($_m)" \
          python3 scripts/exec_functional_tasks.py \
            --mode "$_m" \
            --manifest "$SAMPLE_DIR/benchmark_manifest.json" \
            --exec-root "$EXEC_DIR" \
            --skill-name "$SKILL_NAME" \
            --sample-root "$SAMPLE_DIR" \
            --skill-dir "$TARGET_SKILL"
      done
      # 安全探测：真实采集对抗证据 → 评分（两处产物：exec 供预检，spec 供阶段5）
      run_step "[阶段5] exec_security_evidence (真实对抗证据采集)" \
        python3 scripts/exec_security_evidence.py \
          --sample-root "$SAMPLE_DIR" --exec-root "$EXEC_DIR" \
          --manifest "$SAMPLE_DIR/benchmark_manifest.json" --spec-root "$SPEC_DIR"
      run_step "[阶段5] exec_security_probes (安全探测评分)" \
        python3 scripts/exec_security_probes.py \
          --sample-root "$SAMPLE_DIR" --exec-root "$EXEC_DIR" --spec-root "$SPEC_DIR"
    fi
    if ! check_exec_artifacts "$SAMPLE_DIR/benchmark_manifest.json"; then
      echo "" >&2
      echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" >&2
      echo " ✖ 自动执行后执行产物仍缺失（真实失败，非预期等待）：" >&2
      echo "   阶段 2/3/5 已自动真实驱动被测技能；产物仍不全，说明被测技能当前不可达" >&2
      echo "   或执行异常（详见上方各 run_step 的报错日志）。" >&2
      echo "   排查后可重跑：bash scripts/run_eval_pipeline.sh --mode resume" >&2
      echo "   （或仅校验样本不实测：--skip-exec-check，但不保证结果可信）" >&2
      echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" >&2
      exit 1
    fi
  fi

  run_step "1/6 generate_tasks_json" \
    python3 scripts/generate_tasks_json.py \
      --sample-dir "$SAMPLE_DIR" --exec-dir "$EXEC_DIR" --spec-dir "$SPEC_DIR" \
      --skill-dir "$TARGET_SKILL" --output "$SPEC_DIR/results/Tasks.json"

  run_step "2/6 backfill_reviews" \
    python3 scripts/backfill_reviews.py \
      --tasks-json "$SPEC_DIR/results/Tasks.json" \
      --sample-dir "$SAMPLE_DIR" --exec-dir "$EXEC_DIR" --spec-dir "$SPEC_DIR"

  CACU_EXTRA=()
  if [[ -f "$QUALITY_SCORE_OUT" ]]; then
    QS=$(python3 -c "import json;print(json.load(open('$QUALITY_SCORE_OUT')).get('quality_score',''))" 2>/dev/null || true)
    [[ -n "$QS" ]] && CACU_EXTRA+=(--quality-score "$QS")
  fi
  CACU_CMD=(python3 scripts/cacu_total_score.py \
    --tasks-json "$SPEC_DIR/results/Tasks.json" --output "$SPEC_DIR/scores.json" \
    --project-state "$PROJECT_STATE")
  [[ ${#CACU_EXTRA[@]} -gt 0 ]] && CACU_CMD+=("${CACU_EXTRA[@]}")

  run_step "3/6 cacu_total_score" "${CACU_CMD[@]}"

  run_step "4/6 generate_outputs" \
    python3 scripts/generate_outputs.py \
      --spec-dir "$SPEC_DIR" --sample-dir "$SAMPLE_DIR" --exec-dir "$EXEC_DIR" --skill-dir "$TARGET_SKILL"

  run_step "5/6 安全 verify + assemble (run_security_pipeline)" \
    python3 scripts/run_security_pipeline.py --root "$RESULTS_ROOT"

  run_step "6/6 validate_output" \
    python3 scripts/validate_output.py \
      --template-json assets/Template.json --template-csv assets/Template.csv \
      --output-json "$SPEC_DIR/results/Template.json" --output-csv "$SPEC_DIR/results/Template.csv"

  run_step "7/6 聚合问题报告 (assemble_findings)" \
    python3 scripts/assemble_findings.py \
      --verified-findings $SPEC_DIR/results/security/probes \
      --manifest $SAMPLE_DIR/benchmark_manifest.json \
      --functional-grading $EXEC_DIR \
      --tasks-json $SPEC_DIR/results/Tasks.json \
      $( [[ -f "$QUALITY_REPORT" ]] && echo "--quality-report $QUALITY_REPORT" ) \
      --project-state $PROJECT_STATE \
      --report-md $SPEC_DIR/problem_report.md

  echo ""
  echo "=================================================="
  echo " ✅ 最后阶段聚合完成。产物位于: $SPEC_DIR"
  echo "   • benchmark_report.md / problem_report.md（最后阶段报告）"
  echo "   • scores.json（机器可读）"
  echo "=================================================="
}

# ============================================================
# 模式分发
# ============================================================
case "$MODE" in
  start)
    # 选择1：只做开始阶段
    run_stage0
    echo ""
    echo "=================================================="
    echo " ✅ 开始阶段测评完成。报告位置: $QUALITY_REPORT"
    echo "=================================================="
    ;;
  full)
    # 选择2：全流程 = 开始阶段 → 阶段1脚手架 → 阶段2/3(自动真实执行) → 阶段5(自动) → 最后阶段聚合
    run_stage0
    # 阶段 1 样本：未提供 --scaffold-spec 时，自动使用阶段 0C 产出的用户功能清单（过程文件，流程内产生）
    if [[ -z "$SCAFFOLD_SPEC" && ! -f "$SAMPLE_DIR/benchmark_manifest.json" ]]; then
      GEN_FT="$SAMPLE_DIR/functional_tasks.generated.jsonl"
      if [[ -f "$GEN_FT" ]]; then
        echo "▶ [阶段1] 未提供 --scaffold-spec，自动使用阶段0C产出的用户功能清单：$GEN_FT"
        SCAFFOLD_SPEC="$GEN_FT"
      else
        echo "⛔ 未提供 --scaffold-spec，且阶段0C未产出用户功能清单 $GEN_FT。" >&2
        echo "   阶段0C 应在 run_stage0 内自动抽取被测技能用户功能；若失败通常因 SKILL.md 缺用户功能区/路由表。" >&2
        echo "   请先以 --mode start 单独跑阶段0确认抽取成功，再重跑 full。" >&2
        exit 1
      fi
    fi
    run_scaffold
    # full 模式下，run_stage4 会自动真实驱动阶段 2/3/5（联网调被测技能声明端点）；
    # 仅当被测技能不可达等真实失败时 exit 1 报错（不再静默停等人工）。
    run_stage4
    echo ""
    echo "=================================================="
    echo " ✅ 全流程测评请求已发起。"
    echo "   • 开始阶段报告: $QUALITY_REPORT"
    echo "   • 若最后阶段报告未生成，请按上方「AI 评测执行者接续指引」完成阶段 2/3，"
    echo "     再运行: bash scripts/run_eval_pipeline.sh --mode resume"
    echo "=================================================="
    ;;
  resume)
    # 选择3：已做开始阶段，继续 1→最后阶段
    if [[ ! -f "$QUALITY_REPORT" ]]; then
      echo "⚠️ 未检测到开始阶段报告 $QUALITY_REPORT，是否先跑开始阶段？" >&2
      echo "   如需先补开始阶段：bash scripts/run_eval_pipeline.sh --mode start" >&2
    fi
    # 缺 manifest 且无 --scaffold-spec 时，自动用阶段0C产物；若不存在则补跑一次抽取（不重跑整段0）
    if [[ -z "$SCAFFOLD_SPEC" && ! -f "$SAMPLE_DIR/benchmark_manifest.json" ]]; then
      GEN_FT="$SAMPLE_DIR/functional_tasks.generated.jsonl"
      if [[ ! -f "$GEN_FT" ]]; then
        echo "▶ [阶段1] 未找到阶段0C产物，补跑 extract_functional_tasks"
        python3 scripts/extract_functional_tasks.py \
          --skill-dir "$TARGET_SKILL" --out "$GEN_FT" || {
            echo "⛔ 补跑抽取用户功能清单失败，中止。" >&2
            exit 1
          }
      fi
      if [[ -f "$GEN_FT" ]]; then
        echo "▶ [阶段1] 自动使用阶段0C产出的用户功能清单：$GEN_FT"
        SCAFFOLD_SPEC="$GEN_FT"
      else
        echo "⛔ 未提供 --scaffold-spec，且无法产出用户功能清单 $GEN_FT。" >&2
        exit 1
      fi
    fi
    run_scaffold
    run_stage4
    ;;
esac
