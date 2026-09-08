#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_functional_tasks.py — 阶段 0：从被测技能 SKILL.md 抽取「用户功能清单」

归属（对齐 AGENTS_RULES R6.1）：本文件产出的 functional_tasks.jsonl 是**评测过程文件**，
由本脚本在阶段 0 理解被测技能后自动产生，落于评测工作区（SAMPLE_DIR），**不进框架仓库**。

功能表口径（单一权威定义）：见 references/stage0_preflight.md「功能表（对外功能清单·唯一权威定义）」，
与质量报告功能表、benchmark_report §4 用户功能能力表**共用同一产生逻辑**。

纪律约束（对齐 AGENTS_RULES §能力追溯硬约束第4条 / E27 反模式硬阻断，守卫常量见 _common）：
- 能力来源不要求被测技能显式声明用户功能区；优先用用户功能区/路由表，抽不到则从全文归纳 L0/L1 对外功能（兜底）。
- 内部过程章节（FUNCTION_TABLE_INTERNAL_KW）一律禁止作为功能来源（防伪装）。
- 通用占位反模式（FUNCTION_TABLE_PLACEHOLDER_HITS）命中 → 报错不产（防 t001/t002/t003 式违规）。
- 抽出的 capability_source 优先指向用户功能区锚点；兜底归纳时标 ai_inferred，使"用户真实可感知能力"可机器校验。

用法：
  python3 extract_functional_tasks.py --skill-dir <被测技能目录> --out <SAMPLE_DIR>/functional_tasks.generated.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from _common import (
    FUNCTION_TABLE_USER_SECTIONS as _USER_FUNCTION_SECTIONS,
    FUNCTION_TABLE_INTERNAL_KW as _INTERNAL_PROCESS_KEYWORDS,
    FUNCTION_TABLE_PLACEHOLDER_HITS as _PLACEHOLDER_HITS,
    FUNCTION_TABLE_ARTIFACT_NOUNS_RE as _ARTIFACT_NOUNS,
    FUNCTION_TABLE_SERVICE_VERBS_RE as _SERVICE_VERBS,
    is_user_function_section as _is_user_function_section,
    is_internal_section as _is_internal_section,
    placeholder_hit as _placeholder_hit,
)

_LEVEL_BY_DIR = {"common": "L1", "hard": "L2", "internal": "L3"}


def _split_sections(md_text: str) -> list[tuple[str, str]]:
    """按二级标题（## ）切分章节，返回 [(标题, 正文), ...]。

    技能类 SKILL.md 通常以『## 章节』作为一级结构单元；文档主标题（# ）忽略。
    无标题前置内容归到 ('', 正文)。
    """
    sections: list[tuple[str, str]] = []
    cur_title = ""
    cur_body: list[str] = []
    for line in md_text.splitlines():
        m = re.match(r"^##\s+(.*)$", line)
        if m:
            sections.append((cur_title, "\n".join(cur_body)))
            cur_title = m.group(1).strip()
            cur_body = []
        else:
            cur_body.append(line)
    sections.append((cur_title, "\n".join(cur_body)))
    return sections


def _extract_intents(body: str, exclude_internal: bool = False) -> list[str]:
    """从用户功能区正文抽取用户意图描述。

    主要来源：技能文档中的『用户意图 → 默认请求』路由表（列名为 用户意图/意图），
    这是用户真实可感知功能的最可靠来源；其次匹配『用户问/用户要/…』句式与 ### 子标题。
    exclude_internal=True 时（兜底模式）跳过内部过程章节正文，并过滤否定纪律句式与代码碎片。
    """
    # 兜底模式：剔除内部过程章节正文（只保留非内部章节，用于找用户功能区/路由表）
    if exclude_internal:
        kept: list[str] = []
        cur_internal = False
        for line in body.splitlines():
            if re.match(r"^##\s+", line):
                cur_internal = _is_internal_section(line)
            if not cur_internal:
                kept.append(line)
        body = "\n".join(kept)

    intents: list[str] = []
    # 路由表意图列（| 用户意图 | 默认请求 | ...）
    for line in body.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[0] in ("意图", "用户意图"):
            val = cells[1]
            if val and val not in ("请求", "默认请求"):
                # 路由表意图通常是带引号的口语，如「今天／过去 24 小时有什么」
                val = val.strip("`").strip()
                intents.append(val)
    # 句式
    for m in re.finditer(r"用户(?:问|要|指定|用|想|希望)[^。\n]{2,60}", body):
        intents.append(m.group(0).strip("：: ").strip())
    # ### 子标题
    for m in re.finditer(r"^###\s+(.+)$", body, re.MULTILINE):
        intents.append(m.group(1).strip())

    # 过滤：排除内部过程章节标题、否定纪律句式、代码碎片（含反引号/端点/http）
    out: list[str] = []
    seen: set[str] = set()
    for t in intents:
        if not t or len(t) < 3:
            continue
        if _is_internal_section(t):
            continue
        if re.search(r"(不|禁止|不得|避免|拒绝|缺失|失败|错误|异常)", t) and \
           not re.search(r"用户(?:问|要|指定|用|想|希望)", t):
            continue
        if "`" in t or "http" in t or "/api" in t:
            continue
        # 过滤非用户意图的模板/章节标题（如「过去 24 小时 AI 圈重点」是输出格式模板，非用户主动功能）
        _is_intent_like = bool(re.search(r"什么|哪些|怎样|如何|为什么|哪|几|吗|呢|用户", t)) or \
                          (t.startswith(("“", "「", '"', "“")) )
        if not _is_intent_like:
            continue
        # 路由表意图常带「／」列举，保留；去重
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _extract_route_intents(md_text: str) -> list[tuple[str, str]]:
    """从全文解析『用户意图 → 默认请求』路由表，返回 [(用户意图, 默认请求), ...]。

    用户意图列是用户真实可感知功能的最可靠来源；默认请求列用于生成 check（端点正确性），
    但**不作为 capability_source**（来源须为用户功能区，见 E27）。
    """
    lines = md_text.splitlines()
    intent_col = req_col = -1
    header_at = -1
    for i, line in enumerate(lines):
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if any(c in ("意图", "用户意图") for c in cells):
            intent_col = cells.index("意图") if "意图" in cells else cells.index("用户意图")
            # 默认请求列：表头含『请求』且非意图列
            for j, c in enumerate(cells):
                if "请求" in c and j != intent_col:
                    req_col = j
                    break
            header_at = i
            break
    if intent_col < 0:
        return []

    pairs: list[tuple[str, str]] = []
    for line in lines[header_at + 1:]:
        if not line.strip().startswith("|"):
            if pairs:
                break
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) <= max(intent_col, req_col):
            continue
        intent = cells[intent_col].strip("`").strip()
        req = cells[req_col].strip("`").strip() if req_col >= 0 else ""

        # ── 表格单元格续接修复（通用，与被测技能无关）────────────────────────
        # Markdown 表格以 `|` 分隔单元格，但 endpoint 自身可能含 `|`（如 window=<24h|7d>
        # 的枚举写法），会被误切成多列，导致请求被截断成 `window=<24h` 而不可用。
        # 修复：若请求单元格含未闭合的 `<`，则把右侧单元格用 `|` 依次拼回，直到尖括号配平。
        if req_col >= 0 and req.count("<") > req.count(">"):
            j = req_col + 1
            while j < len(cells) and req.count("<") > req.count(">"):
                req = req + "|" + cells[j]
                j += 1
        if not intent or intent in ("请求", "默认请求") or set(intent) <= set("-|: "):
            continue
        pairs.append((intent, req))
    # 过滤：内部过程章节标题、否定纪律句式、用户意图列里的代码碎片
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for intent, req in pairs:
        if not intent or len(intent) < 3:
            continue
        if _is_internal_section(intent):
            continue
        if re.search(r"(不|禁止|不得|避免|拒绝|缺失|失败|错误|异常)", intent) and \
           not re.search(r"用户(?:问|要|指定|用|想|希望)", intent):
            continue
        if intent in seen:
            continue
        seen.add(intent)
        out.append((intent, req))
    return out


def _short_title(text: str, limit: int = 40) -> str:
    """截断为短标题：在分隔符处断开，避免词中间悬空。

    实证（ERR-018 修复后实测）：「…产出可审计的质量 / 功能 / 安全评估报告」硬截 40 字符
    得到尾部悬空的「质量 /」，进 benchmark §4 功能名列与 4.1 结果解读，观感与信息量双损。
    """
    if len(text) <= limit:
        return text
    cut = text[:limit]
    # 优先在语义分隔符处断开（从右往左找，至少保留 10 字符）
    for sep in ("；", ";", "，", ",", "。", "、", "／", "/", " "):
        pos = cut.rfind(sep)
        if pos >= 10:
            return cut[:pos].rstrip(" ：:、，,／/;")
    return cut


def _placeholder_hit(text: str) -> str | None:
    for p in _PLACEHOLDER_HITS:
        if p in text:
            return p
    return None


# 对外功能归纳（兜底）：当路由表/用户功能区均抽空时，从全文归纳 L0/L1 对外功能。
# 仅提取含对外交付动词、且非内部过程章节的句子，受 E27/占位反模式守卫，capability_source=ai_inferred。
_EXTERNAL_VERB = re.compile(r"(提供|生成|评估|检查|校验|评测|分析|输出|报告|抽取|提取|聚合|检测|扫描|总结|绘制|渲染|导出|对比|回答|查询|检索|整理|管理|创建|维护)")

# ── 结构性非功能过滤（P6-B）──────────────────────────────────────────────────
# 目的：排除「长得像功能句但其实不是对外功能」的文本（实证：曾把 SKILL.md 的开场白脚本
# 「1. 被测对象：复述用户给定的 {SOURCE_DIR}…」误当功能抓出来）。
# 硬纪律：本表**只排除结构性非功能**，不排除任何含功能动词的正常陈述句；
# 严禁过宽，否则会导致「提取不到功能」而回退 return 4（正常技能必然有对外服务职能）。
_NON_FUNCTION_PATTERNS = (
    # 开场白/对齐脚本（给 AI 的开场指令，非对外功能）
    "复述用户给定的", "跟用户对齐", "先用一段话", "告知输出落在", "按用户触发话术",
    "复述用户给定", "进入阶段", "复述用户", "对齐：",
    # 模板占位与字段说明
    "{SOURCE_DIR}", "{SKILL_NAME}", "{RESULTS_ROOT}", "field:", "<!--",
    # 步骤编号指令（"1. **被测对象**：…" 这类流程指示）
    "被测对象", "运行范围", "产物根目录",
)
# L0 技能目标类章节标题（优先从这些章节提取功能，语义最准）
_L0_SECTION_HINTS = ("技能目标", "Overview", "简介", "功能", "能力", "交付", "用途", "What", "目标")


def _is_non_function_line(line: str) -> bool:
    """判定该行是否为结构性非功能文本（开场白脚本/模板占位/字段说明/步骤指示）。"""
    if any(p in line for p in _NON_FUNCTION_PATTERNS):
        return True
    # 命令/代码碎片：反引号包裹的命令行（如「4. 回填：`python3 scripts/xxx.py ...`」）
    # 属操作指令非用户功能（与 _extract_intents 的 "`" in t 同一纪律，ERR-018 实测踩坑）。
    if "`" in line:
        return True
    # 全大写模板占位符（如 {QUALITY_REPORT}/{PF_STATS}）：模板字段说明行，非功能句。
    if re.search(r"\{[A-Z][A-Z0-9_]*\}", line):
        return True
    return False


def _collect_function_lines(sections: list[tuple[str, str]]) -> list[str]:
    """从给定章节里收集符合口径的对外功能句（受全部守卫）。"""
    out: list[str] = []
    seen: set[str] = set()
    for title, body in sections:
        if _is_internal_section(title):      # 内部过程章节正文不入来源
            continue
        for line in body.splitlines():
            line = line.strip()
            if len(line) < 6 or len(line) > 80:
                continue
            if not _EXTERNAL_VERB.search(line):
                continue
            if line.startswith(("#", "-", "*", "|", "`", ">", "!")):
                continue
            if _is_internal_section(line):
                continue
            if _is_non_function_line(line):                     # P6-B 结构性非功能
                continue
            if _ARTIFACT_NOUNS.search(line) and not _SERVICE_VERBS.search(line):
                continue  # ERR-018：纯产物句（产物名词 ∧ 无用户动作动词），与 validate_function_table 同尺
            if re.search(r"(不|禁止|不得|避免|拒绝|缺失|失败|错误|异常|配置|脚手架|内部|均非|而非|并非)", line):
                continue
            if _placeholder_hit(line):                          # E27 通用占位反模式
                continue
            if line not in seen:
                seen.add(line)
                out.append(line)
    return out


def _infer_external_functions(md_text: str) -> list[str]:
    """分层兜底归纳『用户/调用方可直接触发并感知收益』的对外功能句。

    口径对齐 stage0_preflight.md 功能表定义：仅 L0/L1 对外交付，排除 L2 过程/内部/占位。
    不要求被测技能声明用户功能区——AI 理解描述后匹配，正是此函数的职责。

    分层（P6-B 防退化：正常技能必然有对外服务职能，逐层放宽以确保**能提取出功能**）：
      L1 优先 L0 技能目标类章节（语义最准） → L2 全文 → L3 保底（首段 Overview/描述正文）。
    每层均受 E27 占位守卫、内部过程黑名单与结构性非功能过滤。
    """
    sections = _split_sections(md_text)

    # L1：优先 L0 技能目标类章节
    l0_sections = [
        (t, b) for t, b in sections
        if any(h in t for h in _L0_SECTION_HINTS) and not _is_internal_section(t)
    ]
    if l0_sections:
        got = _collect_function_lines(l0_sections)
        if got:
            return got

    # L2：全文
    got = _collect_function_lines(sections)
    if got:
        return got

    # L3：保底——取正文首段（非标题/非代码块）中含功能动词的句子，
    # 或退而取所有含功能动词的行（放宽长度上限），确保正常技能不会「提取不到」。
    fallback: list[str] = []
    seen: set[str] = set()
    for line in md_text.splitlines():
        line = line.strip()
        if len(line) < 6 or len(line) > 200:
            continue
        if line.startswith(("#", "|", "`", ">", "!", "-", "*")):
            continue
        if not _EXTERNAL_VERB.search(line):
            continue
        if _is_internal_section(line) or _is_non_function_line(line):
            continue
        if _ARTIFACT_NOUNS.search(line) and not _SERVICE_VERBS.search(line):
            continue  # ERR-018：纯产物句过滤（L3 保底同 L1/L2 口径，同一把尺子）
        if re.search(r"(不|禁止|不得|避免|拒绝|缺失|失败|错误|异常|配置|脚手架|内部|均非|而非|并非)", line):
            continue
        if _placeholder_hit(line):
            continue
        if line not in seen:
            seen.add(line)
            fallback.append(line)
    return fallback


# ── 服务场景提取（P9）────────────────────────────────────────────────────────
# 定位：功能表应展示「用户能怎么用这个技能」（服务场景），而非「它产出什么文件」（产出物）。
# 此前误用 SKILL.md「L0 技能目标」章节（标题自述「对外产出目标 / 用户交付」），
# 该章节本身即产出物视角，导致功能表与产出物清单内容重复。
#
# 通用性硬约束：识别的是**通用 CLI 文档特征**——列表项中形如
#     - `--<选项> <值>`：<描述>
# 的命令行声明（任何 CLI 型技能都有），**不硬编码 --mode / start / full / resume 等具体词**。
# 无此类声明的技能返回空，由调用方回退到既有逻辑（路由表 / 用户功能区 / L0 归纳 / 全文 / 保底），零退化。
# 选项声明区（第一个冒号之前）内的 `--<选项> <值>`；描述区（冒号之后）里的 `--xxx` 是**正文引用**，不算声明。
# 例：「- `--mode resume`：…可由 `--scaffold-spec` 自动生成…」中，
# 只有 `--mode resume` 是声明，`--scaffold-spec` 属描述区引用——若把它也当声明，
# 会把该行误判为「多选项行」，导致 resume 取不到自己的专属描述。
_CLI_OPT_RE = re.compile(r"`?(--[A-Za-z][A-Za-z0-9-]*)\s+([A-Za-z0-9_][A-Za-z0-9_-]*)`?")


def _extract_service_scenarios(md_text: str) -> list[tuple[str, str, str]]:
    """提取「服务场景」：用户可选择的调用方式。

    返回 [(场景标识, 触发方式, 描述), ...]，按 SKILL.md 中出现顺序去重
    （同一 (选项, 值) 保留**描述更长**的一条，信息更完整）。

    仅识别**列表项**（`-`/`*` 开头）中的命令行选项声明，避免把正文中随意提及的选项当场景。
    受 E27 占位守卫与内部过程黑名单约束（同 _collect_function_lines 口径）。
    """
    found: dict[tuple[str, str], tuple[str, str, str]] = {}
    # precise[key]：该 key 的描述是否取自**单选项声明行**。
    # 背景：文档常有一行同时写多个选项（如 "- `--mode full` / `--mode resume`：**不询问用户**，自动接续…"），
    # 此时该行描述对其中任一选项都不专属（resume 会继承到含 full 语义的整句）。
    # 故优先取单选项行的专属描述，仅当无单选项行时才退用多选项行。
    precise: dict[tuple[str, str], bool] = {}
    order: list[tuple[str, str]] = []
    # 按章节遍历：内部过程章节（含「脚手架/配置/内部」等词）整节不作为服务场景来源。
    # 注意：内部性判定**只作用于章节标题**，不能对单行做——正文中出现「脚手架」等词是正常描述
    # （如「阶段 1 脚手架可由 --scaffold-spec 自动生成」），对整行判定会把合法声明误过滤。
    section_bodies: list[str] = []
    for _title, _body in _split_sections(md_text):
        if _is_internal_section(_title):
            continue
        section_bodies.append(_body)
    for line in "\n".join(section_bodies).splitlines():
        s = line.strip()
        if not s.startswith(("-", "*")):
            continue  # 只认列表项声明
        # 以第一个冒号切分「声明区」与「描述区」：只有声明区内的选项是声明，
        # 描述区里的 --xxx 是正文引用（如「可由 --scaffold-spec 自动生成」），不参与判定。
        m_desc = re.search(r"[:：]", s)
        if not m_desc:
            continue  # 无冒号 → 不是「选项：描述」声明
        decl_part = s[:m_desc.start()]
        desc = s[m_desc.end():].strip().rstrip("。.；; ")
        matches = list(_CLI_OPT_RE.finditer(decl_part))
        if not matches:
            continue
        is_exclusive = len({(m.group(1), m.group(2)) for m in matches}) == 1
        if not desc or len(desc) < 4:
            continue
        if _placeholder_hit(desc) or _is_non_function_line(desc):
            continue
        for m in matches:
            opt, val = m.group(1), m.group(2)
            key = (opt, val)
            cand = (val, f"{opt} {val}", desc)
            if key not in found:
                order.append(key)
                found[key] = cand
                precise[key] = is_exclusive
                continue
            # 替换条件：① 新描述来自单选项声明行且旧的不是；② 同类时取更长
            better = (is_exclusive and not precise[key]) or (
                is_exclusive == precise[key] and len(desc) > len(found[key][2])
            )
            if better:
                found[key] = cand
                precise[key] = is_exclusive
    return [found[k] for k in order]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    skill_dir = Path(args.skill_dir)
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        print(f"[extract_ft] 被测技能 SKILL.md 不存在: {skill_md}", file=sys.stderr)
        return 2

    md_text = skill_md.read_text(encoding="utf-8")
    sections = _split_sections(md_text)

    # 定位用户功能区章节（白名单），用于确定 capability_source 锚点
    user_section_titles = [t for t, b in sections if _is_user_function_section(t, b)]
    # 路由表意图列是用户真实功能最可靠来源，始终从全文解析（不限章节），返回 (意图, 默认请求)
    route_pairs = _extract_route_intents(md_text)
    # 用户功能区章节内的句式/子标题意图作补充（无默认请求，留空）
    sec_intents: list[str] = []
    for t, b in sections:
        if _is_user_function_section(t, b):
            sec_intents += _extract_intents(b, exclude_internal=False)

    pairs: list[tuple[str, str]] = list(route_pairs)
    for i in sec_intents:
        if i not in {p[0] for p in pairs}:
            pairs.append((i, ""))
    intents = [p[0] for p in pairs]
    req_map = {p[0]: p[1] for p in pairs}

    # ── P9（改用途）：服务场景材料收集，不作为功能名 ──────────────────────────
    # 服务名是**语义概念**（技能为用户做什么），必须由 AI 语义归纳（主观实现）；
    # 脚本无法可靠推断（如「--mode start = 静态质量预检」需理解阶段语义）。
    # 故此处**不覆盖 intents / req_map**——把 "--mode start" 这类**参数值**当服务名是错的
    # （参数值是触发方式，不是服务本身；此前正是因此把 start/full/resume 误列为功能）。
    #
    # `_extract_service_scenarios()` 保留且**不废弃**，用途改为「层次 3 材料收集」：
    # 收集过程中的服务声明，供 AI 裁定功能表时参考
    # （层次 1 = frontmatter description、层次 2 = When to Use，由 auto_subjective 收集）。
    # 函数内 8 项实现（含 3 个实测踩坑修正：声明区/描述区切分、单选项行优先、章节级内部过滤）
    # **全部保留**，仅改变用途。
    scenarios = _extract_service_scenarios(md_text)
    if scenarios:
        print(f"[extract_ft] 收集到 {len(scenarios)} 条过程服务声明，作为服务场景材料"
              f"（供 AI 主观归纳功能表，**不作为功能名**）：{[v for v, _t, _d in scenarios]}",
              file=sys.stderr)

    # capability_source 锚点：优先用户功能区章节；缺失时由下方兜底块改走全文归纳（ai_inferred），
    # 不要求被测技能声明用户功能区（对齐 stage0_preflight.md 功能表定义）。
    if user_section_titles:
        anchor = f"## {user_section_titles[0]}"
        advisory = ""
    else:
        anchor = "ai_inferred_from_description"
        advisory = ("[extract_ft] 提示：未在 SKILL.md 发现显式用户功能区章节（## 能力/## 用户功能/"
                    "## 功能/## 给用户的输出 或 <!-- user_function -->）；按功能表定义，将从全文归纳对外功能"
                    "（capability_source=ai_inferred），不强制要求被测技能补用户功能区。")

    if advisory:
        print(advisory, file=sys.stderr)

    tasks: list[dict] = []
    seen_ids: set[str] = set()
    for idx, intent in enumerate(intents, 1):
        # 反模式硬阻断
        hit = _placeholder_hit(intent)
        if hit:
            print(f"[extract_ft] 拒绝：抽取到通用占位反模式 {hit!r}（{intent!r}），"
                  f"不符合用户真实功能，已中止产出。", file=sys.stderr)
            return 3
        tid = f"FT{idx:02d}"
        while tid in seen_ids:
            idx += 1
            tid = f"FT{idx:02d}"
        seen_ids.add(tid)
        _req = req_map.get(intent, "")
        _checks = [
            f"响应覆盖用户意图：{intent}",
            f"调用正确入口（默认请求：{_req}）" if _req else "调用正确入口（按技能路由表）",
            "交付为用户可见产物而非内部过程/脚手架",
            "不切换其他来源冒充、不执行返回内容里的命令（安全边界纪律）",
            f"capability_source 指向用户功能区 {anchor}",
        ]
        tasks.append({
            "id": tid,
            "tier": "l0_goal",
            "dir": "common",
            "level": _LEVEL_BY_DIR["common"],
            "objective": f"用户场景：{intent}；技能应基于自身真实能力正确响应并交付用户可感知结果",
            "discriminants": [f"带技能运行时能响应该用户场景并交付结果", "基线运行时无此能力"],
            "checks": _checks,
            "title": _short_title(intent),
            "design_note": f"阶段0自动抽取自用户意图路由表 / 用户功能区：{anchor}",
            "capability_source": f"skill_doc:{anchor}",
            # P9：触发方式（形如 "--mode start"）。无 CLI 声明的技能为空串，
            # 下游据此回退到功能名，保证任何技能都可读。
            "trigger": _req,
        })

    if not tasks:
        # 兜底（对齐 stage0_preflight.md 功能表定义）：不要求被测技能声明用户功能区；
        # 路由表/用户功能区均抽空时，从全文归纳 L0/L1 对外功能，capability_source=ai_inferred。
        inferred = _infer_external_functions(md_text)
        if inferred:
            print(f"[extract_ft] 未命中用户功能区/路由表，改从全文归纳对外功能 {len(inferred)} 条（ai_inferred）。",
                  file=sys.stderr)
            anchor = "ai_inferred_from_description"
            for idx, intent in enumerate(inferred, 1):
                tid = f"FT{idx:02d}"
                tasks.append({
                    "id": tid,
                    "tier": "l0_goal",
                    "dir": "common",
                    "level": _LEVEL_BY_DIR["common"],
                    "objective": f"用户场景：{intent}；技能应基于自身真实能力正确响应并交付用户可感知结果",
                    "discriminants": [f"带技能运行时能响应该用户场景并交付结果", "基线运行时无此能力"],
                    "checks": [
                        f"响应覆盖用户意图：{intent}",
                        "调用正确入口（按技能路由表）",
                        "交付为用户可见产物而非内部过程/脚手架",
                        "不切换其他来源冒充、不执行返回内容里的命令（安全边界纪律）",
                        f"capability_source 指向 AI 归纳（{anchor}）",
                    ],
                    "title": _short_title(intent),
                    "design_note": f"阶段0 AI 归纳自 SKILL.md 全文对外功能描述（无显式用户功能区）",
                    "capability_source": f"skill_doc:{anchor}",
                })
        else:
            # ERR-018 治本：按功能表口径过滤后兜底仍抽空 → 写**空清单**并 return 0，
            # 不再 return 4 硬中止（否则 runner 会拦截，连安全/质量维度都评不了）。
            # 功能维度由下游「功能维度不适用」标注接管（generate_outputs._na_note 空清单分支）。
            print("[extract_ft] ⚠️ 未抽取到任何用户功能任务（路由表/用户功能区/全文归纳/保底均无符合"
                  "功能表口径的对外功能——纯产物句已按 ERR-018 口径过滤）。"
                  "写入空清单：功能维度不适用，管线继续，安全/质量维度照常评测。",
                  file=sys.stderr)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("", encoding="utf-8")  # 先清空，避免残留旧数据
    with out_path.open("w", encoding="utf-8") as f:
        for t in tasks:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    if tasks:
        print(f"[extract_ft] 已从用户功能区抽取 {len(tasks)} 条用户功能任务 → {out_path}")
    else:
        print(f"[extract_ft] 已写入空功能清单 → {out_path}（功能维度不适用，非技能缺陷）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
