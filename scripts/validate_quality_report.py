#!/usr/bin/env python3
"""PreflightAgent 结果检查机器门禁（对标 SafeTest 的 validate_output.py + verify_findings.py）。

两层：
  A 层（结构门禁，硬约束，对标 validate_output.py）：
    纯文本/结构解析质量评估报告（{QUALITY_REPORT}），机器判定 v2.2.0 红线：
      - 报告存在且非空
      - 四大质量子类齐全（### 格式检查 / ### 对外依赖 / ### 内容验证 / ### 生态适配）
      - 禁项：无"安全合规"节、无"评分"/"score"节
      - 无孪生 .json（{SKILL_NAME}评测.json 不得存在）
      - 定位器格式 / 级别合法性 / 模板骨架一致（后两者为警告级，需 LLM 兜底）
  B 层（事实锚点，对标 verify_findings.py 的客观子集）：
    --stats 提供 Phase 0 extract_stats.json 客观真值基座，对"客观类"事实做反幻觉核对：
      对 extract_stats 中判定为 clean（应无问题）的字段，若报告出现对应客观矛盾关键词，
      标 needs_llm_review（防客观幻觉；语义字段代码不可核对，留 LLM 复核，理由同 verify_findings.py）。

输入：
  --report    {QUALITY_REPORT} Markdown 报告路径
  --stats     可选 extract_stats.json（Phase 0 产物）用于 B 层事实锚点
  --template  可选 assets/report.template.md 用于 A 层骨架一致性（警告级）
  --source    可选 SOURCE_DIR，用于 A 层定位器"文件真实存在"校验（否则只校验格式）
  --plan      可选 {PF_EVAL_PLAN} 评测计划（Plan-First 工作产物）；
              传入则做"断点续评闭环"硬约束：计划不得残留未完成任务 '[ ]'（须全部 [x]/[~]），
              否则 success=false + 退出码 1（机器强制替代 Step 8 人工/LLM 闭环）。
  --allow-twin-json  关闭"无孪生 JSON"硬约束（仅调试用）

输出：JSON {success, errors[], warnings[], objective_anchor[], plan_stats{}} + 退出码（errors 非空则 1）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# ───────────────────────────── A 层：结构门禁常量 ─────────────────────────────

REQUIRED_SUBCLASSES = ["格式检查", "对外依赖", "内容验证", "生态适配"]
FORBIDDEN_HEADING_KEYWORDS = {"安全合规", "评分"}  # v2.2.0 红线：不输出该两节

# 功能表（对外能力清单）禁项：L2 过程策略/内部脚手架不得作为对外功能列出。
# 与 _common.FUNCTION_TABLE_INTERNAL_KW（内部过程分类黑名单，同源）一致，此处为该分类下的
# 具体词守卫；与被评技能 SKILL.md「L0 技能目标为唯一权威源、L2 不得并列」一致；
# 也是本轮修复"样本生成被误列为功能"的机器守卫（原仅靠 LLM 自觉，已漏过一次）。
FORBIDDEN_FUNCTION_TABLE_TERMS = [
    "样本生成", "样本准备", "脚手架生成", "探测脚手架",
    "generate_probe_scaffolds", "gen_functional", "assemble_manifest",
    "阶段 1", "阶段1", "stage 1", "stage1",
]
ALLOWED_FONT_COLORS = {"red", "goldenrod"}  # 严重 / 警告；提醒无 font 标签
# 三档可定位格式：① `文件:行号` ② `文件#章节`（章节级，如缺章节类问题）
# ③ 纯文件路径（文件级属性，如 CRLF 行尾——该文件整体即问题所在，无行号可给）
# 定位后缀三选一：`:行号`（可带范围 `56-58`）/ `#章节`（章节名允许空格，故用 [^|]）/ 无后缀（文件级）。
# 路径允许反斜杠：Windows 产物常见 `scripts\query_x.py`，属合法路径而非不合规值。
POSITION_RE = re.compile(
    r"^(SKILL\.md|[A-Za-z0-9_./\\-]+\.[A-Za-z0-9]+)(:\d+(?:-\d+)?|#[^|]+)?$",
    re.IGNORECASE,
)
# 明确不可定位的模糊表述（R47：**阻断**级）——读者拿着报告根本找不到地方改
_VAGUE_LOCATION = ("全文", "整体", "多处", "参见文档", "参见", "未知", "n/a", "tbd", "待定", "略")
# 内部维度 key 前缀（R47：**阻断**级）——原由 build_objective_data 拼进位置列，
# 产出 `structure_org/SKILL.md` 这类既非路径、又暴露内部实现的脏值
_DIM_KEY_PREFIXES = (
    "frontmatter_quality/", "structure_org/", "eco_portability/",
    "dependency_availability/", "internal_integrity/",
)
# 评测侧能力局限的特征表述：这类是**框架做不到**，不是被测技能有缺陷。
# v12 实证：AI 把「技能为交互式 CLI 类型，无 HTTP 端点，自动化测试困难」写进了
# 「警告（影响逻辑解读或执行）」，读者会误判为技能问题。检出后告警，交 AI 复核。
_FRAMEWORK_LIMIT_KW = (
    "自动化测试困难", "无法自动化", "难以自动化", "评测器无法", "评测框架无法",
    "框架无法", "本评测无法", "无法自动执行", "难以自动执行", "不支持自动",
)

# ───────────────────────────── B 层：客观事实锚点 ─────────────────────────────
# 键 = extract_stats.json 字段；值为该字段"clean（应无问题）"时，报告里不应出现的矛盾关键词。
# 仅做反幻觉（negative）核对：clean 却出现关键词 ⇒ 疑似编造客观问题，需 LLM 复核。
CONTRADICTION_KEYWORDS: dict[str, list[str]] = {
    "code_fence_balanced": ["代码围栏", "未闭合", "围栏闭合", "开闭"],
    "code_blocks_missing_lang": ["代码块", "缺少语言", "无语言标签", "语言标签"],
    "broken_file_links": ["损坏链接", "无效链接", "链接失效", "路径不可达", "文件不存在"],
    "duplicate_anchor_slugs": ["重复锚点", "slug", "锚点碰撞", "锚点歧义"],
    "invalid_embedded_formats": ["嵌入格式", "内联格式", "json 解析失败", "yaml 解析失败", "toml 解析失败"],
    "invalid_external_formats": ["外联格式", "格式文件解析失败", "schema 非法"],
    "missing_requirements_txt": ["requirements.txt", "缺少依赖清单", "缺清单"],
    "undeclared_python_imports": ["未声明", "隐式依赖", "未声明 import"],
    "missing_package_json": ["package.json", "缺少依赖清单"],
    "undeclared_node_imports": ["未声明", "隐式依赖"],
    # ── 新增 9 字段（2026-08-20 接入）：6 结构直接判级 + 3 可移植性候选 ──
    # 结构类（格式检查）：clean = 无问题时报告不应声称对应问题
    "name_format_valid": ["名称格式", "命名非法", "名称不合规", "非法 name", "命名不规范"],
    "frontmatter_valid": ["frontmatter 解析失败", "front matter 损坏", "头部 YAML 非法", "YAML 语法错误", "frontmatter 缺失", "frontmatter 损坏"],
    "missing_frontmatter_fields": ["缺少字段", "缺失字段", "缺 name", "缺 description", "必需字段"],
    "name_dir_mismatch": ["目录名", "目录与 name", "目录不一致", "目录不匹配", "名称与目录"],
    "missing_sections": ["缺少章节", "缺失章节", "章节不全", "标准章节缺失", "缺 Overview", "缺 When to Use", "缺 Common Pitfalls", "缺 Verification Checklist"],
    "duplicate_headings": ["重复标题", "重复同级标题", "同级标题重复"],
    # 可移植性类（生态适配·可移植性）：设计为候选、LLM 复核；
    # 此处兜底逻辑以"候选为空（确无命中）却声称问题"为 clean 判定，
    # 与结构上"无问题却声称问题"同源，可防 LLM 漏判/编造（误报仍靠 LLM 复核消误）。
    "machine_absolute_paths": ["硬编码绝对路径", "机器特定路径", "硬编码 /Users/", "硬编码 /home/", "硬编码用户目录"],
    "script_shebang": ["shebang", "解释器声明", "非 env", "硬编码解释器", "首行解释器"],
    "crlf_scripts": ["CRLF", "行尾", "回车换行", "换行符", "跨平台行尾"],
}


from _common import load_json


def parse_tables(text: str) -> list[tuple[list[str], list[list[str]]]]:
    """极简 Markdown 表格解析：返回 [(headers, rows)]。"""
    tables: list[tuple[list[str], list[list[str]]]] = []
    lines = text.splitlines()
    n = len(lines)
    i = 0
    while i < n:
        line = lines[i].strip()
        if (
            line.startswith("|")
            and i + 1 < n
            and lines[i + 1].strip().startswith("|")
            and set(lines[i + 1].replace("|", "")) <= set("-: ")
        ):
            headers = [c.strip() for c in lines[i].strip().strip("|").split("|")]
            rows: list[list[str]] = []
            j = i + 2
            while j < n and lines[j].strip().startswith("|"):
                cells = [c.strip() for c in lines[j].strip().strip("|").split("|")]
                rows.append(cells)
                j += 1
            tables.append((headers, rows))
            i = j
            continue
        i += 1
    return tables


def collect_headings(text: str) -> list[str]:
    """提取所有 #/##/###/#### 标题文本（去 # 号与首尾空白）。"""
    out: list[str] = []
    for ln in text.splitlines():
        m = re.match(r"^#{1,6}\s+(.*?)\s*#*\s*$", ln)
        if m:
            out.append(m.group(1).strip())
    return out


def section_block(text: str, heading: str) -> str:
    """截取整段：从首个含 heading 的标题起，到下个同级/更高级标题或文件尾。"""
    lines = text.splitlines()
    start = None
    level = None
    for idx, ln in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+(.*?)\s*$", ln)
        if m and heading in m.group(2):
            start = idx
            level = len(m.group(1))
            break
    if start is None:
        return ""
    for j in range(start + 1, len(lines)):
        m = re.match(r"^(#{1,6})\s+", lines[j])
        if m and len(m.group(1)) <= level:
            return "\n".join(lines[start:j])
    return "\n".join(lines[start:])


# ───────────────────────────── A 层：结构门禁 ─────────────────────────────

def run_structural(report: Path, template: Path | None, source: Path | None,
                   allow_twin_json: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if not report.exists():
        return [f"报告不存在: {report}（请先由 AI 依据 extract_stats.json 事实基座生成质量报告，再跑门禁校验）"], warnings
    text = report.read_text(encoding="utf-8")
    if not text.strip():
        return [f"报告为空: {report}（AI 生成报告时内容缺失，请补全后再校验）"], warnings

    headings = collect_headings(text)

    # 1) 四大子类齐全（硬）
    for sub in REQUIRED_SUBCLASSES:
        if not any(sub in h for h in headings):
            errors.append(f"缺少质量子类章节: ### {sub}")

    # 2) 禁项章节（硬）：v2.2.0 红线
    for h in headings:
        for kw in FORBIDDEN_HEADING_KEYWORDS:
            if kw in h:
                errors.append(f"报告含禁止章节（v2.2.0 红线）: '{h}'（不应含{kw}节）")
    # 评分节也用正文兜底：若整篇出现独立"评分"小节标题式写法
    if re.search(r"^#{1,4}\s*评分", text, re.MULTILINE):
        errors.append("报告含禁止章节（v2.2.0 红线）: 独立'评分'小节")

    # 3) 孪生 .json（硬，除非 --allow-twin-json）
    if not allow_twin_json:
        twin = report.with_suffix(".json")
        if twin.exists():
            errors.append(f"不得生成 .json 孪生文件（v2.2.0 规则）: {twin} 已存在")

    # 4) 定位器格式（警告级）：校验"问题位置"列
    tables = parse_tables(text)
    for headers, rows in tables:
        # 表头兼容：模板 columns 实为 `位置,原因,改进建议`，历史文案曾写「问题位置」。
        # 此前**只认「问题位置」**，而真实报告表头是「位置」→ 定位器校验被整体 continue
        # 跳过，**从未生效过**（v12 实证：`SKILL.md全文` 进入报告，校验器仍报
        # success=true / quality_score=100）。故两种表头都认。
        idx = None
        for _hdr in ("问题位置", "位置"):
            if _hdr in headers:
                idx = headers.index(_hdr)
                break
        if idx is None:
            continue
        for r in rows:
            if idx >= len(r):
                continue
            cell = r[idx].strip()
            if not cell:
                continue
            # 去掉可能存在的 font 标签干扰
            cell_clean = re.sub(r"<[^>]+>", "", cell).strip()
            low = cell_clean.lower()
            # R47 升级：此前「SKILL.md全文」这类只给警告，AI 照填不误（v12 实证：
            # 提示词已明令禁止，仍被写入）。这类值让报告彻底失去可操作性，
            # 故不可定位的模糊表述与内部维度前缀一律 **阻断**（errors），
            # 格式不合规但尚可辨识的仍为警告。
            if any(v in low for v in _VAGUE_LOCATION) or any(p in low for p in _DIM_KEY_PREFIXES):
                errors.append(
                    f"问题位置不可定位（R47）：'{cell_clean}' —— 须为 `文件:行号`"
                    f"（如 `SKILL.md:124`）或 `文件#章节`；禁止「全文/整体/多处」及维度 key 前缀"
                )
            elif not POSITION_RE.match(cell_clean):
                warnings.append(f"问题位置格式不合规（应为 资源文件:行号）: '{cell_clean}'")

        # 框架局限误记检测：把评测侧能力缺口写成被测技能的问题
        if "原因" in headers:
            _ci = headers.index("原因")
            for r in rows:
                if _ci >= len(r):
                    continue
                _c = re.sub(r"<[^>]+>", "", r[_ci]).strip()
                if _c and any(k in _c for k in _FRAMEWORK_LIMIT_KW):
                    warnings.append(
                        f"疑似评测侧局限被记为技能问题：'{_c[:60]}'"
                        f"（框架做不到 ≠ 技能有缺陷，请复核是否应从技能问题中移除）"
                    )

    # 5) 级别合法性（警告级）：<font color> 仅 red/GoldenRod
    for m in re.finditer(r"<font\s+color=[\"']?([^\"'>]+)[\"']?>", text, re.IGNORECASE):
        color = m.group(1).strip().lower()
        if color not in ALLOWED_FONT_COLORS:
            warnings.append(f"非法级别颜色标签: <font color='{m.group(1)}'>（仅允许 red/GoldenRod）")

    # 6) 关键问题汇总不得含"提醒"（警告级）
    block = section_block(text, "关键问题汇总")
    if block and "提醒" in block:
        warnings.append("'关键问题汇总'不应含'提醒'级别（提醒级不进汇总）")

    # 7) 模板骨架一致（警告级，需 --template）
    if template and template.exists():
        tpl_headings = collect_headings(template.read_text(encoding="utf-8"))
        for h in tpl_headings:
            if h in ("质量评测报告：<skill-name>",):
                continue
            # 模板含占位符（如 `<skill-name>`）的标题无法与实际报告逐字匹配，跳过骨架比对
            if "<" in h or ">" in h:
                continue
            if h not in headings and any(h == x for x in headings):
                continue
            # 仅核对三级/四级结构锚点是否缺失
            if h not in headings:
                warnings.append(f"报告相对模板缺少章节: '{h}'（模板骨架一致性，警告级）")

    # 8) 功能表守卫（警告级）：仅列 L0 对外交付物，禁列 L2 过程/内部脚手架
    warnings.extend(_function_table_guard(text))

    return errors, warnings


def _function_table_guard(report_text: str) -> list[str]:
    """扫描「功能表」节，拦截 L2 过程/内部脚手架被误列为对外功能。

    填写来源必须是被评 skill 的 L0 技能目标，而非其阶段路线图。
    命中 FORBIDDEN_FUNCTION_TABLE_TERMS 即告警（不阻断门禁，但暴露给 LLM/复核）。

    注：「功能表」在模板中是普通行（非 # 标题），故不能用 section_block（只匹配标题），
    改为按"功能表"标记行定位，截取到下一个三级标题（###）或文件尾。
    """
    warnings: list[str] = []
    lines = report_text.splitlines()
    start = None
    for idx, ln in enumerate(lines):
        if "功能表" in ln and not ln.lstrip().startswith("#"):
            start = idx
            break
    if start is None:
        return warnings
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].lstrip().startswith("### "):
            end = j
            break
    block = "\n".join(lines[start:end])
    for headers, rows in parse_tables(block):
        if not any("实现功能" in h for h in headers):
            continue
        for r in rows:
            row_text = " ".join(r)
            for term in FORBIDDEN_FUNCTION_TABLE_TERMS:
                if term in row_text:
                    warnings.append(
                        f"功能表含 L2 过程/内部项（违反 SKILL.md L0 权威源，不应作为对外功能列出）: '{term}'"
                    )
                    break
    return warnings


# ───────────────────────────── C 层：评测计划闭环（Plan-First） ─────────────────────────────

PLAN_CHECKBOX_RE = re.compile(r"^\s*[-*]\s*\[([ xX~])\]")  # 任务清单行：- [ ] / - [x] / - [~]


def run_plan_gate(plan: Path) -> tuple[list[str], dict[str, int]]:
    """校验评测计划无残留未完成任务（机器强制断点续评闭环）。

    Plan-First 约定：评测计划 (<skill-name>_eval_plan.md) 用 Markdown 任务清单
    枚举子任务，状态分三类：
      - [ ]  未完成（pending）   —— 评测未闭环，须硬失败
      - [x]  已完成（done）
      - [~]  不相关跳过（skipped）—— 合法终点
    重跑时只读 [ ] 项执行、已 [x]/[~] 跳过；故门禁时刻若仍残留 [ ]，
    说明评测过程中断/遗漏，不得进入整合。
    """
    errors: list[str] = []
    pending = done = skipped = 0
    if not plan.exists():
        errors.append(f"评测计划缺失（Plan-First 要求）: {plan}")
        return errors, {"pending": pending, "done": done, "skipped": skipped}
    for ln in plan.read_text(encoding="utf-8").splitlines():
        m = PLAN_CHECKBOX_RE.match(ln)
        if not m:
            continue
        st = m.group(1).lower()
        if st == " ":
            pending += 1
        elif st == "x":
            done += 1
        elif st == "~":
            skipped += 1
    if pending > 0:
        errors.append(
            f"评测计划存在 {pending} 项未完成子任务（残留 '[ ]'）：断点续评须全部 [x]/[~]，"
            f"评测未闭环不得整合（done={done}, skipped={skipped}）"
        )
    return errors, {"pending": pending, "done": done, "skipped": skipped}


# ───────────────────────────── B 层：事实锚点 ─────────────────────────────

# 符号/否定感知：同一行若含这些"干净/正面"标记，说明该处为正面陈述
# （如 "代码围栏完整✓"、"损坏链接 0"、"锚点无碰撞"、"外联格式可解析"、"依赖闭环 OK"），
# 而非客观问题声称，应跳过反幻觉核对（消解除 naive 关键词匹配的误报，见 self-check 2026-07-24）。
CLEAN_LINE_MARKERS = ["✓", "✔", "完整", "可解析", "OK", "正常", "齐", "无", "无问题", "通过", "合规", "一致"]
# 句级否定短语：行内含这些表述时，整行视为正面/否定陈述，不判客观幻觉
NEGATION_PHRASES = ["无", "没有", "不含", "未出现", "未发现", "不存在", "不缺失", "无问题", "无缺陷", "无需", "不须", "无硬编码", "无外部依赖"]


def _line_has_clean_marker(text_lower: str, pos: int) -> bool:
    """判断 pos 所在行是否含明确"干净/正面"标记（用于消除反幻觉误报）。"""
    line_start = text_lower.rfind("\n", 0, pos) + 1
    line_end = text_lower.find("\n", pos)
    if line_end == -1:
        line_end = len(text_lower)
    line = text_lower[line_start:line_end]
    if any(m in line for m in CLEAN_LINE_MARKERS):
        return True
    # 句级否定：整行以否定短语陈述"某项为无/未" → 正面陈述，非幻觉
    if any(p in line for p in NEGATION_PHRASES):
        return True
    return False


def run_fact_anchor(report: Path, stats: Path) -> list[dict[str, Any]]:
    """对 Phase 0 客观事实做反幻觉核对（clean 字段不应被报告声称有问题）。

    仅返回需 LLM 复核的疑似矛盾项；不计入硬 errors（语义留 LLM）。
    符号/否定感知：若矛盾关键词出现在含"干净"标记（✓/0/完整/可解析/OK/正常/齐）
    的同一行，视为正面陈述而非问题声称，跳过（消解除误报）。
    """
    anchor: list[dict[str, Any]] = []
    data = load_json(stats)
    # 报告缺失时 B 层直接跳过（缺失报告由 A 层结构门禁统一报错，不在此崩溃）
    if not report.exists():
        return anchor
    text = report.read_text(encoding="utf-8").lower()

    # 每个字段的"clean 判定"：返回 True 表示应无问题
    clean_predicates = {
        "code_fence_balanced": lambda d: bool(d.get("code_fence_balanced")),
        "code_blocks_missing_lang": lambda d: int(d.get("code_blocks_missing_lang") or 0) == 0,
        "broken_file_links": lambda d: not (d.get("broken_file_links") or []),
        "duplicate_anchor_slugs": lambda d: not (d.get("duplicate_anchor_slugs") or []),
        "invalid_embedded_formats": lambda d: not (d.get("invalid_embedded_formats") or []),
        "invalid_external_formats": lambda d: not (d.get("invalid_external_formats") or []),
        "missing_requirements_txt": lambda d: not bool(d.get("missing_requirements_txt")),
        "undeclared_python_imports": lambda d: not (d.get("undeclared_python_imports") or []),
        "missing_package_json": lambda d: not bool(d.get("missing_package_json")),
        "undeclared_node_imports": lambda d: not (d.get("undeclared_node_imports") or []),
        # ── 新增 9 字段（2026-08-20 接入）──
        # 6 结构类：字段本身即判定结果（True=无问题）
        "name_format_valid": lambda d: bool(d.get("name_format_valid")),
        "frontmatter_valid": lambda d: bool(d.get("frontmatter_valid")),
        "missing_frontmatter_fields": lambda d: not (d.get("missing_frontmatter_fields") or []),
        "name_dir_mismatch": lambda d: not bool(d.get("name_dir_mismatch")),
        "missing_sections": lambda d: not (d.get("missing_sections") or []),
        "duplicate_headings": lambda d: not (d.get("duplicate_headings") or []),
        # 3 可移植性候选：clean = 脚本确无命中（候选空列表）；
        # 设计上 LLM 复核排除文档示例路径，但"候选空却声称问题"属编造，机器兜底。
        "machine_absolute_paths": lambda d: not (d.get("machine_absolute_paths") or []),
        "script_shebang": lambda d: not (d.get("script_shebang") or []),
        "crlf_scripts": lambda d: not (d.get("crlf_scripts") or []),
    }

    for field, pred in clean_predicates.items():
        try:
            is_clean = pred(data)
        except Exception:
            is_clean = False
        if not is_clean:
            continue  # dirty：报告声称有问题属正常，跳过反幻觉
        kws = CONTRADICTION_KEYWORDS.get(field, [])
        hits = []
        for k in kws:
            kl = k.lower()
            pos = text.find(kl)
            if pos == -1:
                continue
            if _line_has_clean_marker(text, pos):
                continue  # 正面陈述（完整✓/计数0/可解析…），非幻觉
            hits.append(k)
        if hits:
            anchor.append({
                "fact": field,
                "expected_clean": True,
                "contradicting_keywords": hits,
                "needs_llm_review": True,
                "note": "Phase 0 客观事实为 clean，但报告出现对应客观问题关键词，疑似客观幻觉，须 LLM 复核",
            })
    return anchor


# ───────────────────────────── C+ 层：schema 基准校验（数据态） ─────────────────────────────
# 方案 C+：报告在"合并数据态"即被机器校验，回填模版前卡死格式问题，避免生成非法报告。
# 校验对象 = 合并后的 report_data.json（merge_report_data 产出），基准 = 模版派生的 schema。
#   结构层（机器硬约束）：
#     - report_data 字段集 == schema dims 字段集（无缺失、无多余）
#     - objective 维度必须存在（脚本必产出，哪怕空 rows）
#     - 评分字段（score / D1–D6 等）不得出现在问题报告数据（问题报告不关心评分）
#   语义层（机器硬约束）：
#     - 无问题维度 rows 为空；回填时写"无"（由 render 负责，这里不校验文本）
#     - 问题须进 rows（数组）；不在文本里散落
def run_schema_check(data: dict[str, Any], schema: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    dim_names = {d["name"] for d in schema["dims"]}

    # 1) 字段集对齐：无缺失、无多余
    data_keys = set(data.keys())
    missing = dim_names - data_keys
    extra = data_keys - dim_names
    if missing:
        errors.append(f"schema 字段缺失（合并数据未含）：{sorted(missing)}")
    if extra:
        errors.append(f"合并数据含 schema 外字段（漂移）：{sorted(extra)}")

    # 2) objective 维度必须存在（已在 merge 阶段保证，这里复查）
    for d in schema["dims"]:
        if d["type"] != "objective":
            continue
        if d["name"] not in data:
            errors.append(f"客观维度缺失：{d['name']}")

    # 3) 评分不得进入问题报告数据
    def _scan_score(obj: Any, path: str) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k.lower() in ("score", "d1", "d2", "d3", "d4", "d5", "d6") or re.search(r"\bscore\b", k, re.I):
                    errors.append(f"问题报告数据含评分字段（严禁）：{path}/{k}")
                _scan_score(v, f"{path}/{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                _scan_score(v, f"{path}[{i}]")
    _scan_score(data, "report_data")

    return errors, warnings


def main() -> None:
    ap = argparse.ArgumentParser(description="PreflightAgent 结果检查机器门禁（A 结构 + B 事实锚点 + C+ schema）")
    ap.add_argument("--report", default="", help="{QUALITY_REPORT} Markdown 报告路径（旧模式：校验 markdown）")
    ap.add_argument("--data", default="", help="方案 C+：合并后的 report_data.json（校验数据态，回填前卡死）")
    ap.add_argument("--objective", default="", help="方案 C+：客观数据 objective_data.json（旧管线 stage0 门禁用）")
    ap.add_argument("--stats", default="", help="可选 extract_stats.json（Phase 0 产物），启用 B 层事实锚点")
    ap.add_argument("--template", default="", help="可选 assets/report.template.md，启用 A 层模板骨架一致性 / C+ schema 派生")
    ap.add_argument("--source", default="", help="可选 SOURCE_DIR；提供时额外校验定位器文件真实存在")
    ap.add_argument("--plan", default="", help="可选 {PF_EVAL_PLAN} 评测计划；传入则做'无残留 [ ]'断点续评闭环硬约束")
    ap.add_argument("--allow-twin-json", action="store_true", help="关闭'无孪生 JSON'硬约束（仅调试）")
    ap.add_argument("--quality-score-out", default=None,
                    help="可选，输出质量分 JSON 路径；写入 {success, quality_score, errors, warnings} 供 cacu --quality-score 接入 scores.json")
    args = ap.parse_args()

    # ── 旧模式：校验 markdown 报告（A 结构 + B 事实锚点 + C 计划闭环）──
    # 历史缺陷：本分支曾位于 C+ 分支的 `return` **之后**，永不可达——下列校验长期不执行，
    # 且 `--report` 调用会直接 SystemExit 并给出自相矛盾的报错（要求提供已提供的 --report）。
    # 现已前置修复（R3）。与 C+ 分支的判定顺序：显式给了数据态参数就走 C+，否则走旧模式。
    if args.report and not (args.data or args.objective):
        report = Path(args.report)
        errors, warnings = run_structural(
            report, Path(args.template) if args.template else None,
            Path(args.source) if args.source else None, args.allow_twin_json,
        )

        objective_anchor: list[dict[str, Any]] = []
        if args.stats:
            sp = Path(args.stats)
            if sp.exists():
                objective_anchor = run_fact_anchor(report, sp)
                for a in objective_anchor:
                    warnings.append(
                        f"B层事实锚点疑似幻觉: {a['fact']} 命中 {a['contradicting_keywords']}（需 LLM 复核）"
                    )
            else:
                warnings.append(f"--stats 指定但文件不存在，跳过 B 层: {sp}")

        # C 层：评测计划闭环（Plan-First 断点续评）
        plan_stats: dict[str, int] = {}
        if args.plan:
            plan_errors, plan_stats = run_plan_gate(Path(args.plan))
            errors.extend(plan_errors)

        success = not errors
        quality_score = max(0, 100 - len(errors) * 10 - len(warnings) * 2)
        result = {
            "success": success,
            "quality_score": quality_score,
            "errors": errors,
            "warnings": warnings,
            "objective_anchor": objective_anchor,
            "plan_stats": plan_stats,
            "mode": "report_markdown",
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.quality_score_out:
            out = {
                "success": success,
                "quality_score": quality_score,
                "error_count": len(errors),
                "warning_count": len(warnings),
            }
            Path(args.quality_score_out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.quality_score_out).write_text(
                json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        if not success:
            raise SystemExit(1)
        return

    # ── 方案 C+ 分支：校验数据态 ──
    from schema_from_template import extract_schema
    if not args.template:
        raise SystemExit("[validate] C+ 模式必须提供 --template 以派生 schema")
    schema = extract_schema(Path(args.template))

    if args.data:
        # 全量校验（合并后）：所有 dim 字段必须齐全
        eff_schema = schema
        data = load_json(Path(args.data))
        mode = "schema_data"
    elif args.objective:
        # 客观门禁（stage0 仅客观数据）：只校验 objective 维度，不要求 subjective 维度存在
        eff_schema = {"columns": schema["columns"],
                      "dims": [d for d in schema["dims"] if d["type"] == "objective"]}
        data = load_json(Path(args.objective))
        mode = "schema_objective"
    else:
        raise SystemExit("[validate] 须提供 --data（C+ 全量）或 --objective（C+ 客观门禁）或 --report（旧模式）")

    errors, warnings = run_schema_check(data, eff_schema)
    success = not errors
    quality_score = max(0, 100 - len(errors) * 10 - len(warnings) * 2)
    result = {
        "success": success,
        "quality_score": quality_score,
        "errors": errors,
        "warnings": warnings,
        "mode": mode,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.quality_score_out:
        Path(args.quality_score_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.quality_score_out).write_text(
            json.dumps({"success": success, "quality_score": quality_score,
                        "error_count": len(errors), "warning_count": len(warnings)},
                       ensure_ascii=False, indent=2), encoding="utf-8")
    if not success:
        raise SystemExit(1)
    return


if __name__ == "__main__":
    main()
