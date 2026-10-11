#!/usr/bin/env python3
"""把 Phase 0 客观事实（extract_stats.json + dependency_probe.json）映射为
「objective 维度/字段级格式数据」，字段严格对应 report.template.md 的 objective 标注。

方案 C+ 落点：脚本只产出结构化客观数据，不拼报告 markdown。
输出 objective_data.json 形如：
{
  "frontmatter_quality": {"rows": [{"位置":..,"原因":..,"改进建议":..}, ...]},
  "structure_org":       {"rows": [...]},
  "eco_portability":     {"rows": [...]},
  "dependency_availability": {"rows": [...], "skipped": bool, "skip_reason": str},
  "stat_chars":  {"text": "name 有 .. 字，..."},
  "dir_tree":    {"text": "<技能目录树>"},
  "objective_critical": {"rows": [...]},
  "objective_warning":  {"rows": [...]}
}
每个维度 rows 为空 = 无问题（回填时写"无"）。

列结构（位置/原因/改进建议）与模版 <!-- columns --> 声明一致，不在此硬编码列名语义，
只复用 schema_from_template 抽取的维度清单做字段对齐校验。

用法：
  python build_objective_data.py --stats extract_stats.json --probe dependency_probe.json \
      --skill-root <被评技能根目录> --out objective_data.json
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from _common import load_json

# 目录树遍历时忽略的目录（与 extract_stats.SKIP_DIRS 保持一致）
_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".vscode", ".idea",
    # 与 extract_stats.SKIP_DIRS 保持一致：不随发布包分发的内容不入目录树（R12）
    ".project", "openspec", ".codebuddy", ".opencode",
}
# ── 级别：结构化取值（英文，机器判定唯一依据）+ 级别词（中文，仅用于报告呈现）──
# 实证：级别曾只存在于「原因」文本里，下游靠找「严重」二字反推——一旦级别词改写，
# 该项既不汇总也不着色，**静默丢失**。故改为生成时固化 level 字段，下游只读 level。
LEVEL_SEVERE = "SEVERE"
LEVEL_WARNING = "WARNING"
LEVEL_NOTICE = "NOTICE"

# 级别词（报告呈现用，与模板约定一致）
_SEVERE = "严重"
_WARNING = "警告"


def _level_from_text(reason: str) -> str:
    """级别词 → 结构化级别的**唯一映射处**（改级别词只需改本函数）。"""
    head = reason[:8]
    if _SEVERE in head:
        return LEVEL_SEVERE
    if _WARNING in head:
        return LEVEL_WARNING
    return LEVEL_NOTICE


def _row(loc: str, reason: str, advice: str, level: str = "") -> dict[str, str]:
    """构造问题行。level 缺省时由级别词派生一次并固化，不再留给下游反推。"""
    return {
        "位置": loc,
        "原因": reason,
        "改进建议": advice,
        "level": level or _level_from_text(reason),
    }


# ───────────────────────── 各 objective 维度映射 ─────────────────────────

def map_frontmatter_quality(s: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not s.get("frontmatter_valid"):
        rows.append(_row("SKILL.md:1", "严重：Frontmatter YAML 解析失败", "修正 YAML 语法：检查缩进是否一致、引号是否配对、冒号后是否漏了空格"))
    for f in s.get("missing_frontmatter_fields") or []:
        rows.append(_row("SKILL.md:1", f"严重：缺少必需字段 {f}", f"在 SKILL.md 顶部 frontmatter（两行 --- 之间）补充字段 {f}"))
    # description 无触发语义 → 警告级（非致命：技能仍可用，但服务场景归纳缺乏依据、AI 判断含糊）。
    # 与上方「description 字段缺失 = 严重级（格式错误）」区分。
    if s.get("description_trigger_semantics") is False:
        rows.append(_row("SKILL.md:1",
                         "警告：description 未见触发语义（when/当/用于/use/场景 等），服务场景可能含糊",
                         "在 description 中说明「什么时候用/提供什么服务」"))
    if not s.get("name_format_valid"):
        rows.append(_row("SKILL.md:1", "严重：name 格式不合规（须全小写连字符、≤64、不以-首尾）", "将 name 改为全小写连字符形式（如 my-skill），长度 ≤64，且不以 - 开头或结尾"))
    if s.get("name_dir_mismatch"):
        rows.append(_row("SKILL.md:1", "警告：目录名与 name 不一致", "将技能目录名改成与 frontmatter 的 name 完全一致（含连字符）"))
    return rows


def map_structure_org(s: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not s.get("code_fence_balanced"):
        rows.append(_row("SKILL.md", "严重：代码围栏未闭合", "检查 ``` 围栏是否成对（数量为奇数说明存在未闭合的代码块）"))
    if s.get("code_blocks_missing_lang"):
        # R47 可定位性：位置用首个缺标签块的行号，原因里列出全部行号 ——
        # 避免「N 处却不知在哪」这类读者无法动手的描述（v12 实证）。
        _ll = s.get("code_blocks_missing_lang_lines") or []
        _loc = f"SKILL.md:{_ll[0]}" if _ll else "SKILL.md"
        _tail = f"（行 {'/'.join(str(x) for x in _ll)}）" if _ll else ""
        rows.append(_row(_loc, f"警告：{s['code_blocks_missing_lang']} 处代码块缺语言标签{_tail}",
                         "为代码块标注语言（如 ```python）"))
    for b in s.get("broken_file_links") or []:
        rows.append(_row("SKILL.md", f"严重：损坏的相对文件链接：{b}", "修正该相对链接使其指向真实存在的文件，或直接删除该链接"))
    for a in s.get("duplicate_anchor_slugs") or []:
        rows.append(_row("SKILL.md", f"警告：重复锚点 slug：{a}", "修改其中一个标题的措辞，使两者生成的锚点不再重复"))
    for d in s.get("invalid_embedded_formats") or []:
        rows.append(_row(f"SKILL.md:{d.get('line')}", f"严重：内联{d['lang']}格式解析失败：{d.get('error')}", "修正该内联格式块，使其能被对应解析器解析（JSON/YAML 语法须合法）"))
    for d in s.get("invalid_external_formats") or []:
        rows.append(_row(d["path"], f"严重：外联格式解析失败：{d.get('error')}", "修正该格式文件内容，使其能被对应解析器解析"))
    for sec in s.get("missing_sections") or []:
        # 章节级定位 `文件#章节`：章节尚不存在、无行号可给，但读者知道要补哪一节
        rows.append(_row(f"SKILL.md#{sec}", f"警告：缺少标准章节：{sec}", f"补充 {sec} 章节：{_SEC_ADVICE.get(sec, '按该章节的常规内容补充')}"))
    for h in s.get("duplicate_headings") or []:
        rows.append(_row("SKILL.md", f"警告：重复同级标题：{h}", "合并或改写重复的标题，使同级标题不重复"))
    return rows


def map_eco_portability(s: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for p in s.get("machine_absolute_paths") or []:
        rows.append(_row(f"{p['path']}:{p['line']}", f"警告：硬编码机器相关路径（{p['kind']}）：{p['match']}",
                         "改为相对于技能目录的路径，或改为运行时解析——避免写死 /Users/xxx、C:\\xxx 这类机器相关路径"))
    for sh in s.get("script_shebang") or []:
        rows.append(_row(f"{sh['path']}:1", f"警告：脚本 shebang 非 env 形式：{sh['shebang']}",
                         "改为 #!/usr/bin/env <解释器>"))
    for c in s.get("crlf_scripts") or []:
        # 路径统一为正斜杠：Windows 产出的 `scripts\query_x.py` 在报告中显示反斜杠，
        # 既不像路径也不满足定位器格式（v12 实证）
        rows.append(_row(str(c["path"]).replace("\\", "/"),
                         "警告：脚本使用 CRLF 行尾（跨平台兼容风险）", "转为 LF 行尾（可执行：sed -i 's/\\r$//' <文件>，或在编辑器中另存为 LF）"))
    return rows


def map_dependency_availability(probe: dict[str, Any]) -> dict[str, Any]:
    """dependency_availability：objective 维度，rows 仅含失败/缺陷项（问题报告范畴）。
    评分（D1–D6 score）不进入问题报告，故只映射 fail 行，且不含 score 列。
    skipped 时整维度不参与（回填写"无"由合并层处理）。
    级别：contract_defect（技能自身缺陷）→ 严重；env_issue/config_defect → 警告。
    """
    if not probe:
        return {"rows": [], "skipped": False, "skip_reason": ""}
    if probe.get("dependency_skipped"):
        return {"rows": [], "skipped": True, "skip_reason": probe.get("skip_reason", "")}
    rows: list[dict[str, str]] = []
    cat_human = {"contract_defect": "技能自身缺陷", "env_issue": "运行环境/网络问题", "config_defect": "配置缺失"}
    for d in probe.get("dimensions") or []:
        if d["status"] != "fail":
            continue
        loc = f"{d['dep_id']} / {d['checker']}"
        cat = d.get("category")
        lvl = "严重" if cat == "contract_defect" else "警告"
        reason = f"{lvl}：{cat_human.get(cat, cat)}：{d['message']}"
        advice = "修正后重测" if cat == "contract_defect" else "仅报告，不否决"
        rows.append(_row(loc, reason, advice))
    return {"rows": rows, "skipped": False, "skip_reason": ""}


def map_internal_integrity(probe: dict[str, Any]) -> dict[str, Any]:
    """internal_integrity：随包文件完整性，rows 仅含异常项（缺失 / 不可读）。

    与 dependency_availability 的分工：本节验「包里带没带全」（静态完整性），
    不计入可用性评分、不触发上架否决，只提示改进——故 advice 一律注明不否决。
    级别：internal_missing（缺失，运行期行为残缺）→ 严重；
         internal_unreadable（不可读，多为编码/权限）→ 警告。
    """
    if not probe:
        return {"rows": [], "skipped": False, "skip_reason": ""}
    rows: list[dict[str, str]] = []
    cat_human = {"internal_missing": "随包文件缺失", "internal_unreadable": "随包文件不可读"}
    for d in probe.get("internal_checks") or []:
        if d.get("status") != "fail":
            continue
        loc = d.get("path") or d.get("dep_id") or ""
        cat = d.get("category")
        lvl = "严重" if cat == "internal_missing" else "警告"
        reason = f"{lvl}：{cat_human.get(cat, cat)}：{d.get('message', '')}"
        advice = "补全或修复后重测（不否决上架）"
        rows.append(_row(loc, reason, advice))
    return {"rows": rows, "skipped": False, "skip_reason": ""}


# ───────────────────────── 技能摘要段客观字段 ─────────────────────────

def map_stat_chars(s: dict[str, Any]) -> dict[str, Any]:
    """stat_chars 字段（objective）：字数统计文本。"""
    name = s.get("name_chars")
    desc = s.get("description_chars")
    body = s.get("body_chars")
    if name is None and desc is None and body is None:
        text = "无（extract_stats 未产出字数统计）"
    else:
        text = f"name 有 {name} 字，description 有 {desc} 字，正文有 {body} 字"
    return {"text": text}


def map_dir_tree(skill_root: Path) -> dict[str, Any]:
    """dir_tree 字段（objective）：遍历技能目录生成树形文本。"""
    root = Path(skill_root)
    if not root.exists():
        return {"text": f"无（技能根目录不存在：{root}）"}

    def _walk(d: Path, prefix: str) -> list[str]:
        lines: list[str] = []
        entries = sorted(
            [p for p in d.iterdir() if p.name not in _SKIP_DIRS],
            key=lambda p: (p.is_file(), p.name.lower()),
        )
        for i, p in enumerate(entries):
            last = i == len(entries) - 1
            conn = "└── " if last else "├── "
            lines.append(prefix + conn + p.name)
            if p.is_dir():
                ext = "    " if last else "│   "
                lines.extend(_walk(p, prefix + ext))
        return lines

    # 只输出技能目录名，不输出绝对路径。
    # 实证：报告里出现 D:\Source\test-skill\.testagent\skills\table_column_relations，
    # 而**评测机器与技能改进开发机器通常不是同一台**——该路径在开发机上不存在，
    # 既无法据以定位，还会误导读者以为技能装在这个位置。故一律相对化。
    tree = [root.name + "/"]
    tree.extend(_walk(root, ""))
    return {"text": "\n".join(tree)}


# ───────────────────────── 对外依赖候选（脚本静态扫描） ─────────────────────────

# 工具名白名单：技能运行环境可用的工具（出现即记为候选）
_TOOL_NAMES = {
    "read_file", "write_to_file", "replace_in_file", "delete_file", "execute_command",
    "web_fetch", "web_search", "search_content", "search_file", "list_dir",
    "ask_followup_question", "use_skill", "image_gen", "task", "send_message",
    "connect_cloud_service", "install_binary", "RAG_search", "update_memory",
    "automation_update", "team_create", "team_delete",
}
# 常见系统命令 token（小写），用于命令候选提取
_SHELL_CMDS = {
    "python", "python3", "pip", "pip3", "node", "npm", "npx", "yarn", "git", "bash",
    "sh", "zsh", "curl", "wget", "make", "go", "cargo", "rustc", "java", "ruby",
    "gem", "docker", "kubectl", "brew", "apt", "apt-get", "rm", "cp", "mv", "cat",
    "grep", "rg", "sed", "awk", "ls", "find", "mkdir", "chmod", "chown",
}
# 文档里"调用 X 技能 / X 技能"的 skill 名提取（宽松：含 - 的小写连字符名或已知 use_skill）
_SKILL_NAME_RE = re.compile(r"use_skill\(\s*['\"]?([\w-]+)", re.IGNORECASE)


def _collect_md_text(skill_root: Path) -> str:
    """拼接技能目录下所有 .md 文本（SKILL.md + references/...），用于静态扫描。"""
    parts: list[str] = []
    root = Path(skill_root)
    if not root.exists():
        return ""
    for p in sorted(root.rglob("*.md")):
        try:
            # B3：统一按 BOM 处理（utf-8-sig），与 extract_stats 保持一致的编码口径
            parts.append(p.read_text(encoding="utf-8-sig", errors="ignore"))
        except OSError:
            pass
    return "\n".join(parts)


def map_deps_candidates(skill_root: Path) -> dict[str, dict[str, Any]]:
    """扫描技能文档，提取 Tools/Skills/命令 候选清单（客观骨架，供 AI 复核裁定）。

    返回 {deps_tools_candidates, deps_skills_candidates, deps_commands_candidates}
    每个为 {"text": "候选1、候选2、..."}（空则"无"）。
    """
    text = _collect_md_text(skill_root)
    if not text:
        empty = {"text": "无（技能目录无 .md 文档）"}
        return {
            "deps_tools_candidates": empty,
            "deps_skills_candidates": empty,
            "deps_commands_candidates": empty,
        }

    # Skills 候选：use_skill(...) 名称集合
    skill_names = sorted(set(_SKILL_NAME_RE.findall(text)))

    # Tools 候选：白名单工具名出现集合（排除自身 use_skill 已在 skills 中）
    tool_hits: set[str] = set()
    for tool in _TOOL_NAMES:
        if re.search(rf"\b{re.escape(tool)}\b", text):
            tool_hits.add(tool)
    tool_hits.discard("use_skill")  # 归到 skills 候选

    # 命令候选：execute_command 段落 / 反引号命令首 token
    cmd_hits: set[str] = set()
    # 反引号内 `cmd ...` 或 ```lang\ncmd ...
    for m in re.finditer(r"`{1,3}([^`\n]+)", text):
        first = m.group(1).strip().split(maxsplit=1)[0] if m.group(1).strip() else ""
        base = first.split("/")[-1].lower()
        if base in _SHELL_CMDS:
            cmd_hits.add(base)
    # execute_command 段落后的代码块首 token
    for m in re.finditer(r"execute_command[^\n]*\n+(?:```[\w-]*\n)?([^\n`]+)", text):
        first = m.group(1).strip().split(maxsplit=1)[0] if m.group(1).strip() else ""
        base = first.split("/")[-1].lower()
        if base in _SHELL_CMDS:
            cmd_hits.add(base)

    def _fmt(items: list[str]) -> str:
        return "、".join(items) if items else "无（文档未提及）"

    return {
        "deps_tools_candidates": {"text": _fmt(sorted(tool_hits))},
        "deps_skills_candidates": {"text": _fmt(skill_names)},
        "deps_commands_candidates": {"text": _fmt(sorted(cmd_hits))},
    }


def map_artifact_manifest(skill_root: Path) -> dict[str, Any]:
    """artifact_manifest 字段（objective）：技能声明的**产出物清单**（纯静态分析，不运行被测技能）。

    来源优先级：
      ① SKILL.md「L1 产生物」声明行（权威）：形如
         `- 质量门禁 → `quality_report.md` + `gate_result.json``
      ② 无该章节时：标注"未声明产出物"，不做脚本推导（推导易混入内部中间产物，
         需 AI 复核才有意义，留待方案 §2.1 的回退路径再启用）。

    消费方按扩展名判定（客观规则）：
      .md/.csv/.html → 人（阅读）  |  .json/.jsonl/.yaml → 程序（解析）  | 含 template → 人（复用）

    返回 {"text": <Markdown 表格>}，供「技能摘要 → 功能表」之后呈现。
    """
    root = Path(skill_root)
    skill_md = root / "SKILL.md"
    if not skill_md.is_file():
        return {"text": "无（未找到 SKILL.md，无法提取产出物声明）"}

    try:
        # B3：同上，统一按 BOM 处理，避免与 extract_stats 结论不一致。
        lines = skill_md.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return {"text": "无（SKILL.md 读取失败）"}

    # 定位「L1 产生物」章节（措辞可能为「产生物」或「子产物」）
    start = None
    for i, ln in enumerate(lines):
        if re.match(r"^#{2,4}\s*L1\s*(产生物|子产物)", ln.strip()):
            start = i + 1
            break
    if start is None:
        return {"text": "未声明产出物（SKILL.md 无「L1 产生物」章节）"}

    # 归属功能 → 文件列表；分隔符 + 或 /；文件名以反引号包裹
    _ITEM_RE = re.compile(r"^[-*]\s*(.+?)\s*→\s*(.+)$")
    _FILE_RE = re.compile(r"`([^`]+)`")
    _ARTIFACT_EXT = (".md", ".json", ".jsonl", ".csv", ".yaml", ".yml", ".html", ".txt")
    # 排除模板类（不分大小写）：模板无论作为**输入格式**（assets/ 下的框架资产）还是
    # **过程中间格式**（如 Template.json 承载中间计算值、供下游脚本消费后生成最终报告），
    # 都不是「运行产出的对外交付物」。规格依据：L2 定义「中间产物（内部手段，非用户交付）
    # 不能与 L0 技能目标并列」。此规则按文件名的通用特征判定，不为任一技能定制。
    _TEMPLATE_MARK = "template"

    rows: list[list[str]] = []
    for ln in lines[start:]:
        s = ln.strip()
        # 遇到下一个同级/更高级标题即结束本节
        if s.startswith("#"):
            break
        m = _ITEM_RE.match(s)
        if not m:
            continue
        owner = re.sub(r"\*+", "", m.group(1)).strip()
        for raw in re.split(r"[+/]", m.group(2)):
            for cand in _FILE_RE.findall(raw):
                name = cand.strip()
                if "." not in name:
                    continue  # 纯字段名（如 overall_score）不是产出文件，跳过
                if not name.lower().endswith(_ARTIFACT_EXT):
                    continue
                low = name.lower()
                if _TEMPLATE_MARK in low:
                    continue  # 模板类非交付物，排除（详见 _TEMPLATE_MARK 注释）
                if low.endswith((".md", ".csv", ".html", ".txt")):
                    consumer = "人（阅读）"
                else:
                    consumer = "程序（解析）"
                rows.append([owner, name, consumer, "SKILL.md L1 声明"])

    if not rows:
        return {"text": "未声明产出物（「L1 产生物」章节未解析到产出文件）"}

    header = "| 归属功能（L0） | 产出文件 | 消费方 | 来源 |\n|---|---|---|---|"
    body = "\n".join(f"| {a} | `{b}` | {c} | {d} |" for a, b, c, d in rows)
    return {"text": "\n".join([header, body])}


# ───────────────────────── 关键问题汇总（客观聚合） ─────────────────────────

def _severity_of(row: dict[str, str]) -> str:
    """取级别：优先读结构化 `level` 字段；缺失时回退文本（兼容 LLM 填写的主观行）。"""
    lvl = str(row.get("level") or "").strip().upper()
    if lvl in (LEVEL_SEVERE, LEVEL_WARNING, LEVEL_NOTICE):
        return lvl
    reason = row.get("原因", "")
    if _SEVERE in reason:
        return LEVEL_SEVERE
    if _WARNING in reason:
        return LEVEL_WARNING
    return ""


def map_issue_summary(objective_dims: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """由各 objective 维度 fail 行聚合严重/警告汇总（objective_critical / objective_warning）。

    仅聚合 objective 维度（脚本能判级者），主观维度严重项由 AI 填 subjective_critical/warning。
    返回 (objective_critical, objective_warning)。
    """
    critical_rows: list[dict[str, str]] = []
    warning_rows: list[dict[str, str]] = []
    # 维度中文标签：用于把「维度归属」写进原因，从而让位置列保持纯净
    _DIM_LABEL = {
        "frontmatter_quality": "元信息",
        "structure_org": "结构组织",
        "eco_portability": "可移植性",
        "dependency_availability": "依赖可用性",
        "internal_integrity": "内部一致性",
    }
    for dim_name, entry in objective_dims.items():
        rows = entry.get("rows", []) if isinstance(entry, dict) else []
        for r in rows:
            lvl = _severity_of(r)
            # R47：位置列**不再**拼维度前缀。原实现产出 `structure_org/SKILL.md`，
            # 既不是 `文件:行号`，又让读者看到内部维度 key（v12 实证）。
            # 维度归属改为中文标签前缀写入「原因」，位置列保持纯净可定位。
            _label = _DIM_LABEL.get(dim_name, dim_name)
            if lvl == LEVEL_SEVERE:
                critical_rows.append({"位置": r.get("位置", ""), "原因": f"[{_label}] {r.get('原因', '')}", "改进建议": r.get("改进建议", ""), "level": lvl})
            elif lvl == LEVEL_WARNING:
                warning_rows.append({"位置": r.get("位置", ""), "原因": f"[{_label}] {r.get('原因', '')}", "改进建议": r.get("改进建议", ""), "level": lvl})
    return (
        {"rows": critical_rows, "skipped": False, "skip_reason": ""},
        {"rows": warning_rows, "skipped": False, "skip_reason": ""},
    )


# 缺章节类问题的「补什么」说明：只写「补充 XX 章节」读者仍不知该写什么内容，
# 执行方（含自动化改进工具）无从下手，故按章节给出具体内容要求。
_SEC_ADVICE = {
    "Overview": "用 1–2 段说明这个技能做什么、解决什么问题",
    "When to Use": "列出适合使用本技能的场景（可作为触发条件）",
    "Common Pitfalls": "列出常见误用方式与规避办法",
    "Verification Checklist": "列出交付前的自检项清单",
}

OBJECTIVE_DIMS = {
    "frontmatter_quality": map_frontmatter_quality,
    "structure_org": map_structure_org,
    "eco_portability": map_eco_portability,
}


def build(stats: dict[str, Any], probe: dict[str, Any], skill_root: Path | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for dim, mapper in OBJECTIVE_DIMS.items():
        out[dim] = {"rows": mapper(stats)}
    out["dependency_availability"] = map_dependency_availability(probe)
    out["internal_integrity"] = map_internal_integrity(probe)

    # 技能摘要段客观字段
    out["stat_chars"] = map_stat_chars(stats)
    if skill_root is not None:
        out["dir_tree"] = map_dir_tree(skill_root)
    else:
        out["dir_tree"] = {"text": "无（未提供 --skill-root，无法遍历目录）"}

    # 关键问题汇总：客观维度聚合
    out["objective_critical"], out["objective_warning"] = map_issue_summary(out)

    # 对外依赖候选（脚本静态扫描，供 AI 复核裁定）
    if skill_root is not None:
        out.update(map_deps_candidates(skill_root))
    else:
        empty = {"text": "无（未提供 --skill-root，无法扫描）"}
        out["deps_tools_candidates"] = empty
        out["deps_skills_candidates"] = empty
        out["deps_commands_candidates"] = empty

    # 产出物清单（纯静态：解析 SKILL.md「L1 产生物」声明，**不运行被测技能**）
    if skill_root is not None:
        out["artifact_manifest"] = map_artifact_manifest(skill_root)
    else:
        out["artifact_manifest"] = {"text": "无（未提供 --skill-root，无法提取）"}
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="客观事实 → objective 维度/字段格式数据")
    ap.add_argument("--stats", required=True, help="extract_stats.json 路径")
    ap.add_argument("--probe", default="", help="可选 dependency_probe.json 路径")
    ap.add_argument("--skill-root", required=True, help="被评技能根目录（用于生成 dir_tree）")
    ap.add_argument("--out", required=True, help="objective_data.json 输出路径")
    args = ap.parse_args()

    stats = load_json(Path(args.stats))
    probe = load_json(Path(args.probe)) if args.probe and Path(args.probe).exists() else {}
    data = build(stats, probe, Path(args.skill_root))

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"objective_data -> {args.out}")
    # 调试摘要（注：rows 为「待 AI 复核候选」，非已判定缺陷；与 validator 的 errors/warnings 口径不同）
    for dim, v in data.items():
        rows = v.get("rows", [])
        tag = " (skipped)" if v.get("skipped") else ""
        print(f"  {dim}: {len(rows)} 条待复核候选" + tag)


if __name__ == "__main__":
    main()
