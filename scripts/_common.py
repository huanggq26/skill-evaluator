"""skill-evaluator 公共 helper 集合（由多处脚本去重合并而来）。

仅供本 skill 的 ``scripts/`` 下脚本以 ``from _common import ...`` 复用。

合并原则：只收口**行为完全一致**的 helper；存在语义分歧的（如带
``rstrip("s")`` 的 ``_to_float``、解析失败返回 ``0`` 的 ``_to_int``/``_to_float``、
带额外修复正则的 ``_sanitize_task_metrics_text``）刻意保留在各原脚本本地，避免改变
既有运行行为。
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    """获取当前 UTC 时间的 ISO 8601 字符串（毫秒精度，Z 后缀）。"""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _default_results_root() -> Path:
    """默认结果根目录：放在系统下载目录下（{RESULTS_ROOT}）。

    可用环境变量 SKILL_EVALUATOR_RESULTS_ROOT 覆盖，指向已有的 `skill-evaluator_results` 输出目录。
    """
    env_root = os.environ.get("SKILL_EVALUATOR_RESULTS_ROOT", "")
    if env_root:
        return Path(env_root)
    return Path.home() / "Downloads" / "skill-evaluator_results"


def _to_int(value: Any, default: Any = None) -> int | None:
    """将看起来是数字的值转换为 int（无法解析时返回 default）。"""
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(text)
        except ValueError:
            try:
                return int(float(text))
            except ValueError:
                return default
    return default


def _to_float(value: Any, default: Any = None) -> float | None:
    """将值转换为浮点数（无法解析时返回 default）。"""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return default
    return default


def _task_success(metrics: dict[str, Any]) -> bool | None:
    """根据常见标签/布尔字段推断任务是否成功。"""
    for key in ("audit_label", "final_label", "reviewed_label", "exec_label", "probe_result", "result"):
        raw = str(metrics.get(key) or "").strip().upper()
        if raw in {"PASS", "PASSED", "SUCCESS", "SUCCEEDED", "OK", "COMPLETED", "TRUE"}:
            return True
        if raw in {"NO", "FAIL", "FAILED", "ERROR", "FALSE"}:
            return False
    for key in ("success", "passed", "test_passed"):
        if key in metrics and metrics.get(key) is not None:
            return bool(metrics.get(key))
    raw_status = str(metrics.get("status") or "").strip().lower()
    if raw_status in {"completed", "done", "pass", "passed", "success"}:
        return True
    if raw_status in {"failed", "error", "blocked", "denied"}:
        return False
    return None


def _relative_to_project(path: Path, root: Path) -> str:
    """计算 path 相对于 root 的路径（解析失败则返回 path 自身）。"""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return path.as_posix()


def load_json(path: Path) -> Any:
    """读取并解析 JSON 文件。"""
    return json.loads(path.read_text(encoding="utf-8"))


def load_manifest_meta(manifest_path: str) -> dict[str, dict]:
    """从 benchmark_manifest.json 抽取 probe_id -> {asi_category, security_group}。"""
    meta: dict[str, dict] = {}
    if not manifest_path:
        return meta
    try:
        m = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return meta
    for entry in m.get("security_probes", []) or []:
        pid = entry.get("id") or entry.get("probe_id")
        if pid:
            meta[pid] = {
                "asi_category": entry.get("primary_asi_category", ""),
                "security_group": entry.get("security_group", ""),
            }
    return meta


# 共享安全维度映射（单一权威源；脚本禁止各自硬编码同名但分散的常量）
SECURITY_CATEGORY_TO_DIMENSION: dict[str, str] = {
    "abnormal": "abnormal_behavior_control",
    "permission": "permission_boundary",
    "sensitive": "sensitive_data_protection",
}
# 探针 ID 前缀 -> security_group（与 benchmark_manifest 一致；动态探测亦按此兜底）
PROBE_GROUP_MAP: dict[str, str] = {
    "SA_01": "abnormal", "SA_02": "abnormal", "SA_03": "abnormal",
    "SP_01": "permission", "SP_02": "permission", "SP_03": "permission",
    "SS_01": "sensitive", "SS_02": "sensitive", "SS_03": "sensitive",
}


# ---------------------------------------------------------------------------
# 运行状态（调试态/发布态）参数声明收敛点
# 权威策略定义见 SKILL.md「运行状态策略」与 references/config.md「运行状态策略索引」；
# 此处仅收口 CLI 参数声明，避免各脚本分散重复定义 choices/help（防漂移）。
# 判定本身仍由 _project_state.detect_project_state 负责。
# ---------------------------------------------------------------------------
def add_project_state_arg(parser: "argparse.ArgumentParser") -> None:
    """为 argparse parser 追加统一的 --project-state 参数（debug/production）。

    未显式指定时由 _project_state.detect_project_state 按打开方式自动判定。
    """
    import argparse  # 局部导入，避免本模块顶层对 argparse 的硬依赖（其它 helper 不需要）

    parser.add_argument(
        "--project-state",
        choices=["debug", "production"],
        default=None,
        help="项目状态：debug=失败三方并列归因；production=默认归因被评技能；"
             "未指定时按打开方式自动判定（以项目方式打开本技能=debug，否则=production）。"
             "权威策略定义见 SKILL.md「运行状态策略」",
    )


def _sanitize_task_metrics_text(text: str) -> str:
    """清理 task_metrics.json 文本中的常见格式问题（如缺少逗号等）。"""
    cleaned = text.strip()
    if not cleaned:
        return cleaned
    cleaned = cleaned[cleaned.find("{") : cleaned.rfind("}") + 1]
    cleaned = re.sub(
        r'("total_time_seconds"\s*:\s*-?\d+(?:\.\d+)?)\s*.*?(\n\s*"time_estimate_basis"\s*:)',
        r"\1,\2",
        cleaned,
        flags=re.S,
    )
    cleaned = re.sub(r'("end_evidence_path"\s*:\s*"[^"]+")\s*(\n\s*"method"\s*:)', r"\1,\2", cleaned)
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
    return cleaned


# ─────────────────────────────────────────────────────────────────────────────
# 功能表（对外功能）守卫常量 · 唯一权威源
# 定义口径见 references/stage0_preflight.md「功能表（对外功能清单·唯一权威定义）」；
# 与 AGENTS_RULES.md「能力追溯硬约束」E27 同源。脚本只引用此处，禁止各自内联重复声明。
# ─────────────────────────────────────────────────────────────────────────────

# 用户功能区章节标题白名单（存在时作锚点辅助定位；非能力存在必要条件）
FUNCTION_TABLE_USER_SECTIONS = (
    "能力", "用户功能", "功能", "给用户的输出", "用户输出", "对外交付",
)

# 内部过程章节关键词黑名单（命中则禁止作为功能来源，防 L2 过程/中间产物/脚手架伪装）
FUNCTION_TABLE_INTERNAL_KW = (
    "安全边界", "请求", "核心工作流", "工作流", "过程", "中间件",
    "脚手架", "配置", "约束", "边界", "内部",
)

# 通用占位反模式（任何技能都适用、不特指本技能真实用户功能，命中即排除）
FUNCTION_TABLE_PLACEHOLDER_HITS = (
    "基础请求", "结构化结果", "边界输入不崩溃", "中间产物供复用", "通用代码",
    "通用总结", "处理边界", "异常输入而不崩溃", "产出中间产物", "正确响应用户",
    "返回结构化",
)

# 条目级产物名词 / 用户动作动词（ERR-018 治本：0C 兜底抽取与 validate_function_table
# 共用**同一把尺子**，单一权威来源，禁止两处各自维护）。
# 判定口径：句子含产物名词 **且** 不含用户动作动词 → 纯产物句，不作为对外功能。
# ⚠️ 硬纪律（extract L205-206）：词表严禁过宽——只拦「纯产物句」（如「质量门禁 JSON」
# 「报告生成」），任何含用户动作动词的正常陈述句（如「用户可查询评测报告」）不得被排除。
# ⚠️ 词表陷阱：_EXTERNAL_VERB（extract 本地）含「生成」，故「报告生成」会被当对外功能抽出；
# 但本动词表**不含**「生成」——过滤必须按「产物名词 ∧ ¬用户动作动词」判定，与校验脚本一致。
FUNCTION_TABLE_ARTIFACT_NOUNS_RE = re.compile(
    r"(JSON|json|文件|报告生成|评分聚合|质量门禁|门禁\s*JSON|中间产物|"
    r"流水线产物|产物清单|脚手架|数据文件|生成物|artifact)"
)

# 负向前瞻说明（实测踩坑，ERR-018）：「评测报告」「检查清单」中的动词是**名词定语**而非
# 用户动作——「质量评测报告」不能因为含「评测」就被当作用户服务场景。动词右邻紧跟
# 报告|文件|JSON|清单 时视为定语。权衡：负向集刻意不含「数据|结果」（「检查结果」
# 中「检查」仍是真实动作），也不追求区分「查询报告」（动宾）与「评测报告」（定语）——
# 误拦代价（兜底多层可由其他句补）远小于漏放代价（产出物混入功能表，正是 ERR-018 要治的病）。
FUNCTION_TABLE_SERVICE_VERBS_RE = re.compile(
    r"((?:查询|评测|评估|测试|检查|校验|解答|咨询|答疑|使用|触发|运行|执行|"
    r"获取|浏览|检索|同步|读取|把关|测一测|解读|归纳|看结果|续跑|跑|"
    r"发现|追踪|订阅|归档)(?!报告|文件|JSON|json|清单))"
)


def is_user_function_section(title: str, body: str = "") -> bool:
    """判定章节是否为用户功能区（白名单命中且非内部过程词）。"""
    if any(kw in title for kw in FUNCTION_TABLE_INTERNAL_KW):
        return False
    if any(name in title for name in FUNCTION_TABLE_USER_SECTIONS):
        return True
    if "<!-- user_function -->" in body:
        return True
    return False


def is_internal_section(title: str) -> bool:
    """判定章节是否为内部过程（黑名单命中）。"""
    return any(kw in title for kw in FUNCTION_TABLE_INTERNAL_KW)


def placeholder_hit(text: str) -> str | None:
    """返回命中通用占位反模式的词，未命中返回 None。"""
    for p in FUNCTION_TABLE_PLACEHOLDER_HITS:
        if p in text:
            return p
    return None
