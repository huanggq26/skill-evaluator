#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_function_table.py — 校验功能表是否为「用户服务场景」视角

背景（错误档案 ERR-021 / ERR-018）：功能表由 AI 主观归纳，此前无机制防止
产出物/过程构件混入——benchmark §4 就曾把「质量门禁 JSON / 报告生成 / 评分聚合」
当功能。本脚本提供归纳后的机械校验，与 merge_report_data 的占位提醒（源头）
构成双保险。

五层校验：
  1. 产物黑名单（违规，exit 1）：条目含产出物/过程构件名词，且无用户动作词
  2. 服务视角（警告）：条目缺少用户动作动词，提示人工复核
  3. 同源检查（警告）：功能表整体与 frontmatter description 无任何内容词交集
  4. 三方漂移（警告）：能力声明 / 用户指南 / 功能表 三处描述互不覆盖
     ——对应 ERR-021 修改策略第 4 条；只报告不阻断、不自动修复
  5. **F6 依据标注（违规，exit 1）**：每条须注明 SKILL.md 可定位出处
     （`SKILL.md:<行号>` 或 `SKILL.md §<章节名>`）；无出处即阻断。
     理由：归纳不可回溯即等同臆造（v5 实证：功能表跨轮漂移、与 §4 不同源）

用法：
  python3 validate_function_table.py --report <quality/quality_report.md> \\
                                     --skill-dir <被测技能目录>

退出码：0 通过或仅有警告 / 1 有违规 / 2 用法错误
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# 词表从 _common 导入（ERR-018 治本：与 extract_functional_tasks 兜底过滤共用同一把尺子，
# 单一权威来源在 _common.py，禁止两处各自内联维护）
try:
    from _common import FUNCTION_TABLE_INTERNAL_KW as _INTERNAL_KW
    from _common import FUNCTION_TABLE_ARTIFACT_NOUNS_RE as _ARTIFACT_NOUNS
    from _common import FUNCTION_TABLE_SERVICE_VERBS_RE as _SERVICE_VERBS
except Exception:  # 守卫常量缺失时不阻断黑名单校验
    _INTERNAL_KW = ()
    _ARTIFACT_NOUNS = None
    _SERVICE_VERBS = None

_CJK_WORD = re.compile(r"[\u4e00-\u9fff]{2,4}")
# ── L0 语言自适应（语义漂移治理方案）────────────────────────────────
# 原只支持中文分词：英文技能/英文功能表产出**空词集**，进而被判
# 「缺失能力词」或「零交集 → 疑似漂移」——属语言假设导致的误报。
# 现按中英**并集**取词：中文分支行为完全不变，仅新增英文分支，故既有四层校验不回退。
# 不预设主语言阈值（避免未实测阈值）：两种词表同时生效，交集只会更容易命中、不会更严。
_EN_WORD = re.compile(r"\b[A-Za-z]{3,}\b")
_EN_STOP = frozenset("""
the and for with that this from your you are can will not all any has have been
its our their when what which who how why use using used uses able into out over
under more most other some such only than then there here these those about after
before between during through also each may might must should would could
""".split())

# ── 三方漂移检测（ERR-021 修改策略第 4 条）────────────────────────
# 无区分度通用词：任何技能的描述里都会出现，不构成能力差异，比对前剔除
_STOP_WORDS = frozenset({
    "可以", "支持", "使用", "进行", "通过", "这个", "什么", "怎么", "以及",
    "一个", "我们", "你的", "如果", "需要", "就是", "不是", "还有", "其他",
    "评测", "技能", "报告", "结果", "阶段", "过程",
})
_GUIDE_SECTION_RE = re.compile(r"^##\s+1[.\s]")

# ── F6 依据标注（强约束，无出处即阻断）────────────────────────────
# 实证：功能表由 AI 归纳，若不要求出处，条目可凭印象生成——v5 实证功能表与
# benchmark §4 不同源、条目跨轮漂移（同一技能两次归纳结果不一致），读者无从
# 核证。故要求每条注明 SKILL.md 的**可定位**出处（行号或章节名）。
# 匹配：`SKILL.md:42` / `SKILL.md 第 42 行` / `SKILL.md §用户功能区` / `SKILL.md 用户功能区`；
# **不匹配**裸 `SKILL.md`（无定位信息，等同未标注）。
_SOURCE_RE = re.compile(
    r"SKILL\.md\s*(?:[:：#§]|第|L|l)?\s*[\w\u4e00-\u9fff][\w\u4e00-\u9fff\-.]*",
    re.IGNORECASE,
)
# 依据层次①：frontmatter description 亦为合法出处（技能摘要的权威声明）
_SOURCE_DESC_RE = re.compile(r"\bdescription\b", re.IGNORECASE)


def _load_guide_functions(skill_dir: Path) -> str:
    """提取用户指南「这是什么，什么时候用」章节正文（至下一同级标题止）。

    章节缺失或结构变化时返回空，由调用方按「缺失」告警——不静默跳过。
    """
    g = skill_dir / "references" / "USER_GUIDE.md"
    if not g.is_file():
        return ""
    in_sec = False
    buf: list[str] = []
    for line in g.read_text(encoding="utf-8", errors="replace").splitlines():
        if re.match(r"^##\s", line):
            if in_sec:
                break
            if _GUIDE_SECTION_RE.match(line):
                in_sec = True
            continue
        if in_sec:
            buf.append(line)
    return "\n".join(buf)


def _content_words(text: str) -> set:
    """文本 → 能力词集合（语言自适应：中英并集；各剔除本语言无区分度词）。

    中文分支与原实现一致（保证既有行为不回退）；英文分支为 L0 新增。
    """
    s = text or ""
    words: set = {w for w in _CJK_WORD.findall(s) if w not in _STOP_WORDS}
    words |= {w.lower() for w in _EN_WORD.findall(s) if w.lower() not in _EN_STOP}
    return words


def _check_three_way_drift(desc: str, guide: str, table: str) -> list:
    """三处功能描述比对，返回可读告警（警告级，不阻断、不自动修复）。

    只做两类**机械可靠**的判定：
      1. 缺项：某处无功能描述（或描述中无可区分能力词）；
      2. 零交集：两处之间没有任何共同能力词。

    **不判定「新增未同步」**：实测三处描述因视角与详略天然不同（定位声明 / 使用指南 /
    服务场景表），机械词缺失率恒在 68%–98%，且样例为「今日 vs 今天」「事件追踪 vs 事件」
    这类同义改写——词面无法区分「能力缺失」与「用词不同」，断言必然误报。
    该层级的漂移判定需要语义理解，交由 AI 裁定环节，不由本脚本承担。

    不内置任何被测技能专属词表，只做「声明了什么」与「描述了什么」的通用比对。
    """
    texts = {"能力声明": desc, "用户指南": guide, "功能表": table}
    words = {k: _content_words(v) for k, v in texts.items()}
    alerts: list[str] = []

    for name, ws in words.items():
        if not (texts[name] or "").strip():
            alerts.append(f"[三方漂移] 「{name}」缺失功能描述，无法参与三方比对（请补全后再校验）")
        elif not ws:
            alerts.append(f"[三方漂移] 「{name}」有描述但缺乏可区分的能力词，无法有效比对")

    for a, b in (("能力声明", "用户指南"), ("能力声明", "功能表"), ("用户指南", "功能表")):
        wa, wb = words[a], words[b]
        if not wa or not wb:
            continue                      # 缺项已单独告警，此处不重复
        if not (wa & wb):
            alerts.append(f"[三方漂移] 「{a}」与「{b}」无任何共同能力词，疑似描述漂移")
    return alerts


def _extract_table_rows(report: Path) -> list:
    """提取质量报告中「功能表」的数据行（不含表头与分隔行）。

    逐行解析：从以「功能表」开头的行起，到以「产出物清单」开头的行止，
    收集其间所有表格行。不能用单个正则跨段匹配——功能表标题行自身就含
    「不是产出物清单」字样（实测踩坑），前瞻会在第一行就截断。
    """
    lines = report.read_text(encoding="utf-8", errors="replace").splitlines()
    in_ft = False
    rows: list[str] = []
    for line in lines:
        s = line.strip()
        if not in_ft:
            if s.startswith("功能表"):
                in_ft = True
            continue
        if s.startswith("产出物清单"):
            break
        if not s.startswith("|"):
            # 兼容 **md 列表**形式（提示词自 v9 起要求功能表用列表逐项呈现，
            # 渲染层再切分）：若此处只认表格行，列表形式会被判「未找到数据行」而
            # **整体跳过校验** —— 产物黑名单、服务视角、F6 依据全部失效。
            # 实证：table_column_relations v9/v10 功能表即为列表形式。
            if s.startswith("- ") or s.startswith("* "):
                rows.append(s[2:].strip())
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if not cells or not cells[0]:
            continue
        if set(cells[0]) <= set("-: "):              # 分隔行
            continue
        if cells[0] in ("服务场景", "用户关注的功能"):  # 表头
            continue
        rows.append(" | ".join(cells))
    return rows


def _load_description(skill_dir: Path) -> str:
    sk = skill_dir / "SKILL.md"
    if not sk.is_file():
        return ""
    m = re.search(r"description:\s*[\"']?(.*?)[\"']?\s*\n\s*\w+:",
                  sk.read_text(encoding="utf-8", errors="replace"), re.S)
    return (m.group(1) if m else "").strip()


def main() -> int:
    ap = argparse.ArgumentParser(description="校验功能表是否为用户服务场景视角")
    ap.add_argument("--report", required=True, type=Path, help="质量报告 md 路径")
    ap.add_argument("--skill-dir", required=True, type=Path, help="被测技能目录")
    args = ap.parse_args()
    if not args.report.is_file():
        print(f"[validate_ft] 报告不存在: {args.report}", file=sys.stderr)
        return 2

    rows = _extract_table_rows(args.report)
    if not rows:
        print("[validate_ft] 未找到功能表数据行（仍为占位或未归纳）——跳过校验")
        return 0

    desc = _load_description(args.skill_dir)
    desc_words = set(_CJK_WORD.findall(desc)) if desc else set()

    violations: list[str] = []
    warns: list[str] = []
    table_words: set = set()

    for r in rows:
        has_artifact = bool(_ARTIFACT_NOUNS and _ARTIFACT_NOUNS.search(r))
        has_internal = any(kw and kw in r for kw in _INTERNAL_KW)
        has_service = bool(_SERVICE_VERBS and _SERVICE_VERBS.search(r))
        table_words |= set(_CJK_WORD.findall(r))

        # F6：无出处即阻断 —— 归纳必须可回溯到权威来源，否则等同臆造
        if not (_SOURCE_RE.search(r) or _SOURCE_DESC_RE.search(r)):
            violations.append(
                f"缺少可定位出处（F6）：{r[:90]}"
                f"　→ 请在「依据」列填 `SKILL.md:<行号>` 或 `SKILL.md §<章节名>`"
            )

        if (has_artifact or has_internal) and not has_service:
            violations.append(f"疑似产出物/过程构件（且无用户动作词）: {r[:90]}")
        elif has_artifact or has_internal:
            warns.append(f"含产物/内部词但同时有用户动作词，请复核: {r[:90]}")
        elif not has_service:
            warns.append(f"缺少用户动作动词，请复核是否为服务场景: {r[:90]}")

    # 同源检查（整体级，避免对同义改写误报）
    if desc_words and not (desc_words & table_words):
        warns.append("功能表与 frontmatter description 无内容词交集，"
                     "疑似偏离权威来源，请对照 description 复核")

    # 三方漂移检查（ERR-021 第 4 条）：警告级，不阻断、不改变裁决
    guide_text = _load_guide_functions(args.skill_dir)
    warns.extend(_check_three_way_drift(desc, guide_text, " | ".join(rows)))

    print(f"[validate_ft] 功能表共 {len(rows)} 条")
    if violations:
        print(f"\n❌ 违规 {len(violations)} 条（产出物混入，必须整改）:")
        for v in violations:
            print(f"   - {v}")
    if warns:
        print(f"\n⚠️ 警告 {len(warns)} 条（请人工复核）:")
        for w in warns:
            print(f"   - {w}")
    if not violations and not warns:
        print("✓ 全部通过：条目均为用户服务场景视角，且与 description 同源")

    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
