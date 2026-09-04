#!/usr/bin/env python3
"""合并客观数据（脚本产出）与主观数据（AI 产出）为唯一 report_data.json。

方案 C+ 合并规则（定义只在一处 · 客观优先）：
  - 字段清单由 schema_from_template 从模版派生；
  - 客观字段来自 objective_data.json（脚本），主观字段来自 subjective.json（AI）；
  - 若某字段在双方都出现：客观优先（AI 误填被覆盖），并告警；
  - subjectve.json 出现未知字段（不在 schema）→ 报错（防 AI 自由发挥导致字段漂移）；
  - objective 字段缺失（脚本未产出）→ 报错（客观维度必须脚本兜底，哪怕空 rows）。

输入：
  --objective objective_data.json   （build_objective_data 产出）
  --subjective subjective.json      （AI 按 schema 填的主观维度）
  --template  assets/report.template.md
  --out       report_data.json
  --functional-tasks <sample>/functional_tasks.generated.jsonl
              （阶段 0C 功能清单产物；功能表 subjective 为空时以其回填，P6-A 统一产生源）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from _common import load_json
from schema_from_template import extract_schema


def merge(
    objective: dict[str, Any],
    subjective: dict[str, Any],
    schema: dict[str, Any],
    functional_tasks_text: str = "",
) -> dict[str, Any]:
    dim_names = {d["name"] for d in schema["dims"]}
    union: dict[str, Any] = {}

    # 1) 未知字段检查：主观数据不得含 schema 之外的字段
    unknown = set(subjective.keys()) - dim_names
    if unknown:
        raise SystemExit(f"[merge] 主观数据含未知字段（不在模版 schema）：{sorted(unknown)}")

    # 2) 客观字段必填（哪怕空 rows）；逐字段合并
    for d in schema["dims"]:
        name = d["name"]
        dtype = d["type"]
        if dtype == "objective":
            if name not in objective:
                # 客观维度脚本必须产出（即使空 rows）。缺失即报错。
                raise SystemExit(f"[merge] 客观维度缺失（脚本未产出）：{name}")
            union[name] = objective[name]
        else:  # subjective
            if name in subjective:
                # 主观字段：以 AI 数据为准；但若客观也含（异常），客观优先并告警
                if name in objective:
                    print(f"[merge][warn] 主观字段 {name} 同时出现在客观数据，客观优先覆盖", file=sys.stderr)
                    union[name] = objective[name]
                else:
                    union[name] = subjective[name]
            else:
                # 主观字段 AI 未填：允许空（回填时写"无"），不报错
                union[name] = {"rows": [], "skipped": False, "skip_reason": ""}

    # 3) 对外依赖：候选非空而 AI 结论为空时，抑制那个"无"。
    # 背景：模板把「客观候选（field）」与「AI 复核结论（dim）」放在同一个 #### 子小节内，
    # 若候选列了一串工具/命令、AI 结论却写"无"，呈现为「列表 + 无」自相矛盾，读者无法判断
    # 到底有没有依赖。此处在数据层标记，由 render_report 省略该"无"（保留候选即可）。
    _DEP_PAIRS = (
        ("deps_tools", "deps_tools_candidates"),
        ("deps_skills", "deps_skills_candidates"),
        ("deps_commands", "deps_commands_candidates"),
    )
    for dim_name, field_name in _DEP_PAIRS:
        dim_entry = union.get(dim_name)
        field_entry = union.get(field_name)
        if not isinstance(dim_entry, dict) or not isinstance(field_entry, dict):
            continue
        dim_rows = dim_entry.get("rows") or []
        if dim_rows:
            continue  # AI 有真实结论，正常渲染
        # 候选非空 → 抑制"无"
        field_text = str(field_entry.get("text") or "").strip()
        if field_text and field_text != "无":
            dim_entry["suppress_empty"] = True

    # 4) 功能表回填（P6-A）：统一功能清单产生源。
    # 背景：功能表（function_table）属 subjective 维度，而 auto_subjective 只产出 advisory
    # 「复核提示、不做裁定」，流水线里无人真实填写 → 质量报告功能表渲染为「无」，
    # 与 benchmark_report §4「被测技能功能能力」（来自 0C 产物）不一致。
    # 故此处以 0C 产出的 functional_tasks.generated.jsonl 为**功能清单唯一源**回填：
    # subjective 有真实裁定时以其为准，为空时回填 0C 结果，保证功能表不为空且与 §4 同源。
    _ft_entry = union.get("function_table")
    if isinstance(_ft_entry, dict):
        _ft_text = str(_ft_entry.get("text") or "").strip()
        _ft_rows = _ft_entry.get("rows") or []
        if _ft_entry.get("skipped") or (not _ft_text and not _ft_rows):
            # P9 修正：功能表是**服务场景**（技能为用户做什么），属**语义/主观**概念，
            # 必须由 AI 归纳。0C 产物是产出物/执行单元视角，**不能**拿来当服务场景
            # （此前回填导致功能表变成产出物清单，与产出物清单重复）。
            # 故主观未裁定时**不回填**，改为明确标注「待 AI 归纳」并指向依据材料
            # ——诚实留白优于填充错误内容（不臆造纪律）。
            union["function_table"] = {
                "rows": [],
                "text": ("_待 AI 语义归纳服务场景_（脚本不代为裁定）："
                         "依据层次为 ①frontmatter description → ②When to Use → ③过程中的服务声明，"
                         "完整材料见 `quality/results/subjective.json` 的 `function_table.skip_reason`"),
                "skipped": True,
                "skip_reason": str(_ft_entry.get("skip_reason") or ""),
            }

    return union


def _build_functional_tasks_text(path: Path | None) -> str:
    """把阶段 0C 的功能任务 jsonl 转成功能表文本（P6-A：功能清单统一产生源）。

    输出为 Markdown 表格（**服务场景 / 用户意图 / 触发方式 / 产出** 四列对齐模板表头），
    每行一项功能，供质量报告「功能表」直接呈现，保证与 benchmark §4 同源且不为空。

    P9：功能表是**用户服务场景**视角（用户能怎么用），不是产出物清单（产出物由
    `artifact_manifest` 客观解析，两者互补不重复）。
    服务场景名优先取「触发方式值」（如 `--mode start` → `start`）；无 CLI 声明的技能
    （走路由表/L0 归纳路径）回退用功能名，保证任何技能都有可读的场景名。
    """
    if path is None or not path.is_file():
        return ""
    rows: list[str] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if not isinstance(obj, dict):
                continue
            title = str(obj.get("title") or obj.get("id") or "").strip()
            obj_text = str(obj.get("objective") or "").strip()
            # objective 形如「用户场景：X；技能应…」，取用户场景部分作功能描述
            m = re.search(r"用户场景[:：]\s*(.+?)(?:；|;|$)", obj_text)
            desc = (m.group(1) if m else obj_text).strip()
            desc = desc.replace("|", "/")
            if len(desc) > 120:
                desc = desc[:120] + "…"
            # ── 服务场景名（P9）──────────────────────────────────────────────
            # 优先取「触发方式值」：设计注记里形如 "capability_source 指向 AI 归纳
            # (--mode start)" 或 title 含 "--opt value" 时，取 value 作为场景名（如 start），
            # 完整命令放「触发方式」列；否则回退功能名。
            # 回退时精简功能名：原始 title 常带序号、加粗与破折号后的说明
            # （如 "1. **质量门禁（Quality Gate）** — 阶段 0 门禁 JSON"），
            # 若原样填入会与「用户意图」列内容重复。仅按 em/en dash（— –）切分，
            # 不用普通连字符（避免误伤名称中的 -，如 "skill-evaluator"）。
            # trigger 由 extract_functional_tasks 在服务场景分支写入（形如 "--mode start"）；
            # 无 CLI 声明的技能该字段为空串 → 回退功能名。
            trigger = str(obj.get("trigger") or "").strip()
            if trigger:
                parts = trigger.split(None, 1)
                name = parts[1] if len(parts) > 1 else trigger
            else:
                name = re.sub(r"^\d+[.、)]\s*", "", title)      # 去序号
                name = name.replace("**", "").strip()           # 去加粗
                name = re.split(r"[—–]", name)[0].strip()       # 取破折号前的功能名
                name = name.replace("|", "/").strip() or title   # 兜底：切空则用原名
            name = name.replace("|", "/").strip()
            if not title:
                continue
            trigger_cell = f"`{trigger}`" if trigger else "按 SKILL.md 描述调用"
            rows.append(f"| {name} | {desc} | {trigger_cell} | 见产出物清单 |")
    except OSError:
        return ""
    if not rows:
        return ""
    header = "| 服务场景 | 用户意图 | 触发方式 | 产出（见产出物清单） |\n|---|---|---|---|"
    return "\n".join([header, *rows])


def main() -> None:
    ap = argparse.ArgumentParser(description="合并客观+主观数据为唯一 report_data.json")
    ap.add_argument("--objective", required=True)
    ap.add_argument("--subjective", required=True)
    ap.add_argument("--template", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--functional-tasks", default="",
                    help="阶段0C 功能清单 jsonl；功能表 subjective 为空时以其回填（P6-A）")
    args = ap.parse_args()

    schema = extract_schema(Path(args.template))
    objective = load_json(Path(args.objective))
    subjective = load_json(Path(args.subjective))
    ft_text = _build_functional_tasks_text(
        Path(args.functional_tasks) if args.functional_tasks else None
    )
    if ft_text:
        print(f"功能表回填源：阶段0C 功能清单（{args.functional_tasks}）")

    merged = merge(objective, subjective, schema, functional_tasks_text=ft_text)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report_data -> {args.out}  (维度数={len(merged)})")


if __name__ == "__main__":
    main()
