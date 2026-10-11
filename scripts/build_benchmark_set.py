#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_benchmark_set.py — 基准集分层抽样（攻击面标签改造 #1 的取样工具）。

定位：从技能源目录挑出一批**异质**技能作为基准集，供双人独立标注产出真值。

为什么必须分层而不能随机：
  随机抽样会从 295 个技能里抽出大量同质的"调某个 API"类技能，导致标签命中分布畸形，
  召回率被少数几类技能主导 → **覆盖率虚高**。分层抽样保证用途分布足够散，且自然带来阴性样本。

分层代理 vs 真值（重要）：
  本脚本用的六类判定是**粗糙的关键字代理**，只用于决定"抽谁进样本"，**不产出真值**。
  真值由人工按 `benchmark/annotation_guide.md` 独立标注产出，与扫描器、与本脚本的代理
  判定均无耦合——否则 Cohen's kappa 与召回率都会变成"自己对自己的一致度"，失去意义。

六类能力面（分层维度）：
  exec 代码执行 / dep 外部依赖 / fs 文件与持久化 / net 网络外联 / cred 凭证访问 / inter 交互与编排

输出：JSON（逐技能分层属性 + 约束达成情况）；退出码 0 = 成功，1 = 参数 / IO 错误。
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

# ── 分层维度：用途域（不是"是否命中能力面"）──
# 为什么不用能力面分层：实测按能力面关键字分层会退化——295 个技能里几乎全部命中全部 6 类
# （"API"/"接口"/".txt" 之类泛词到处都是），结果样本**全阳性、无阴性**，精确率根本无从计算。
# 用途域分层既能保证异质性，也会自然带来阴性样本（如纯内容生成类多半不碰凭证与执行）。
# ⚠ 本表是**抽样代理**，不是判定信号；严禁复用到打标逻辑。
_CLASS_PATTERNS: dict[str, str] = {
    "doc": r"\bpdf\b|\bdocx?\b|\bxlsx?\b|\bpptx?\b|文档|转换|翻译|解析|ocr|markdown|报告生成",
    "data": r"\bstock\b|股票|数据|data|分析|analy|报表|指标|行情|查询|query|统计",
    "web": r"browser|浏览器|crawl|爬虫|抓取|search|搜索|网页|web|fetch|site|网址",
    "dev": r"\bcode\b|代码|\bgit\b|deploy|部署|build|构建|test|测试|debug|sdk|\bapi\b|开发|工程",
    "gen": r"生成|创作|文案|写作|write|content|视频|图像|画图|设计|post|文案生成|创意",
    "sys": r"企业|oa\b|lark|飞书|wechat|微信|erp|crm|招聘|校园|云|cloud|工单|审批|协同",
}
_CLASSES = list(_CLASS_PATTERNS)
_COMPILED = {k: re.compile(v, re.IGNORECASE) for k, v in _CLASS_PATTERNS.items()}
_CJK = re.compile(r"[\u4e00-\u9fff]")


def _skill_text(skill_dir: Path) -> str:
    parts: list[str] = []
    for p in [skill_dir / "SKILL.md", *sorted((skill_dir / "scripts").rglob("*"))[:200]]:
        if p.is_file() and p.suffix in (".py", ".md", ".json", ".sh", ".txt"):
            try:
                parts.append(p.read_text(encoding="utf-8", errors="replace")[:20000])
            except Exception:
                continue
    return "\n".join(parts)


def _domain_text(skill_dir: Path) -> str:
    """域判定文本 = 目录名 + SKILL.md frontmatter 的 `description` 字段。

    为什么逐级收紧：实测过两级都**退化**——① 用整个技能语料（几万字）→ 每个技能命中全部域；
    ② 用 SKILL.md 开头 1200 字 → 仍几乎全部命中（描述里"数据/文档/开发"等泛词到处都是）。
    域回答的是"这个技能是干什么的"，只有 `description` 一句话能给出可判读的答案。
    """
    p = skill_dir / "SKILL.md"
    try:
        txt = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        txt = ""
    desc = ""
    m = re.search(r"^---\s*\n(.*?)\n---", txt, re.S)
    if m:
        dm = re.search(r"^description:\s*(.*(?:\n[ \t]+.*)*)", m.group(1), re.M)
        if dm:
            desc = dm.group(1)
    if not desc.strip():
        desc = txt[:400]
    return f"{skill_dir.name}\n{desc}"


def profile(skill_dir: Path) -> dict:
    """单个技能的分层属性（语言 / 有无 scripts / 主域 + 域命中分）。"""
    text = _skill_text(skill_dir)
    cjk = len(_CJK.findall(text))
    total = max(len(text), 1)
    lang = "zh" if cjk / total > 0.03 else "en"
    dtext = _domain_text(skill_dir)
    # 按**命中分**取主域，而非"命中即算"——后者会让泛描述技能同时属于所有域，分层再次退化。
    scores = {c: len(_COMPILED[c].findall(dtext)) for c in _CLASSES}
    primary = max(_CLASSES, key=lambda c: (scores[c], -_CLASSES.index(c)))
    return {
        "name": skill_dir.name,
        "path": str(skill_dir),
        "lang": lang,
        "has_scripts": (skill_dir / "scripts").is_dir(),
        "primary": primary if scores[primary] > 0 else "other",
        "class_scores": scores,
        "zh_ratio": round(cjk / total, 4),
    }


def select(cands: list[dict], n: int, min_scripts: int, min_en: int, min_zh: int,
           min_per_class: int) -> tuple[list[dict], dict]:
    """两阶段选择：先按域保底（每域不少于下限），再补语言与 scripts 约束。

    为什么不能一路贪心：实测单阶段贪心会先把名额用在"覆盖面最广"的技能上，
    结果某个域一个都没抽到（dev = 0），分层形同虚设——域分布是**硬约束**，必须优先满足。
    """
    picked: list[dict] = []
    remain = list(cands)

    def take(item: dict) -> None:
        picked.append(item)
        remain.remove(item)

    # 阶段 A：每个域先取满下限（域内按命中分降序，优先带 scripts 的，保证可执行性证据更丰富）
    for c in _CLASSES:
        pool = [x for x in remain if x["primary"] == c]
        pool.sort(key=lambda x: (-x["class_scores"].get(c, 0), not x["has_scripts"], x["name"]))
        for item in pool[:min_per_class]:
            if len(picked) >= n:
                break
            take(item)

    # 阶段 B：补齐 scripts / 英文 / 中文 下限，再按域分补足总数
    def deficit(item: dict) -> bool:
        """该技能是否命中"尚未满足"的约束维度。"""
        need_scripts = sum(1 for p in picked if p["has_scripts"]) < min_scripts
        need_en = sum(1 for p in picked if p["lang"] == "en") < min_en
        need_zh = sum(1 for p in picked if p["lang"] == "zh") < min_zh
        cnt = {c: sum(1 for p in picked if p["primary"] == c) for c in _CLASSES + ["other"]}
        # "other"（无任何域命中）不作为分层的必补维度，否则会强行拉入无法判读的技能
        need_class = (cnt[item["primary"]] < min_per_class
                      if item["primary"] != "other" else False)
        return ((need_scripts and item["has_scripts"])
                or (need_en and item["lang"] == "en")
                or (need_zh and item["lang"] == "zh")
                or need_class)

    while len(picked) < n and remain:
        # 先只在"能补约束"的候选里挑；都补不上时退回全体候选。
        # 同域内按**域命中分降序**取最具代表性的，避免取到边界样本。
        pool = [c for c in remain if deficit(c)] or remain
        pool.sort(key=lambda c: (-c["class_scores"].get(c["primary"], 0), c["name"]))
        best = pool[0]
        picked.append(best)
        remain.remove(best)

    check = {
        "n": len(picked),
        "has_scripts": sum(1 for p in picked if p["has_scripts"]),
        "en": sum(1 for p in picked if p["lang"] == "en"),
        "zh": sum(1 for p in picked if p["lang"] == "zh"),
        "per_class": {c: sum(1 for p in picked if p["primary"] == c) for c in _CLASSES},
    }
    check["ok"] = (check["n"] == n
                   and check["has_scripts"] >= min_scripts
                   and check["en"] >= min_en
                   and check["zh"] >= min_zh
                   and all(v >= min_per_class for v in check["per_class"].values()))
    return picked, check


def main() -> int:
    ap = argparse.ArgumentParser(description="基准集分层抽样（攻击面标签改造 #1）")
    ap.add_argument("--source", required=True, help="技能源目录（其下每个子目录为一个技能）")
    ap.add_argument("--n", type=int, default=15, help="第一批样本量（默认 15）")
    ap.add_argument("--min-scripts", type=int, default=8, help="含 scripts/ 的最少数量")
    ap.add_argument("--min-en", type=int, default=5, help="纯英文技能最少数量")
    ap.add_argument("--min-zh", type=int, default=5, help="纯中文技能最少数量")
    ap.add_argument("--min-per-class", type=int, default=2, help="每类能力面最少数量")
    ap.add_argument("--output", default=None, help="输出 JSON 路径（缺省 stdout）")
    args = ap.parse_args()

    src = Path(args.source).expanduser().resolve()
    if not src.is_dir():
        print(f"❌ 技能源目录不存在: {src}", file=sys.stderr)
        return 1

    cands = [profile(d) for d in sorted(src.iterdir()) if (d / "SKILL.md").is_file()]
    if len(cands) < args.n:
        print(f"❌ 候选技能不足：{len(cands)} < {args.n}", file=sys.stderr)
        return 1

    picked, check = select(cands, args.n, args.min_scripts, args.min_en, args.min_zh,
                           args.min_per_class)
    result = {
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": str(src),
        "candidates": len(cands),
        "constraints": {"n": args.n, "min_scripts": args.min_scripts, "min_en": args.min_en,
                        "min_zh": args.min_zh, "min_per_class": args.min_per_class},
        "check": check,
        "selected": picked,
        "note": "分层属性为**抽样代理**，不是真值；真值由人工按 annotation_guide.md 独立标注。",
    }
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
        print(f"✅ 基准集抽样完成：{check['n']} 个（约束达成={check['ok']}）→ {args.output}")
        print(f"   scripts {check['has_scripts']} / 英文 {check['en']} / 中文 {check['zh']}"
              f" / 每类 {check['per_class']}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
