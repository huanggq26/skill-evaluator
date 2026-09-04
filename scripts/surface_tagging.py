#!/usr/bin/env python3
"""surface_tagging.py — 通用技能攻击面打标签（阶段 1.5 阶段 A，不绑定任何被测技能）。

定位：依据 references/stage1_sample.md 步骤 1.5「受控词表 9 标签 + 判定信号」，
      扫描被测技能 SKILL.md / scripts/ 客观产物，逐标签按信号判定，产出 skill_surface_tags。

本脚本是「安全探测数量的唯一来源」前置于阶段 B（ASI 维度选择）的纯通用扫描器：
  • 不引用任何具体被测技能名或本评测器自身名（通用性前提，硬约束）；
  • 判定仅基于词表信号（subprocess/os.system/requests/...）与文件事实，不含业务语义；
  • 每个标签命中须记录证据（文件:行号），供下游审计与「逐项落地断言」追溯。

输出（JSON 到 --output，缺省 stdout）：
  {
    "skill_surface_tags": [            # 受控 9 标签子集（命中 Yes 的）
      {"tag": "exec_code", "evidence": ["SKILL.md:L42", "scripts/run.py:L7"], "mapped_asi": ["ASI01","ASI05"]}
    ],
    "evidence_index": {...}            # tag -> 证据行列表
  }

退出码：0 = 成功（无论是否命中标签）；1 = 参数/IO 错误。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ── 受控词表（与 stage1_sample.md 步骤 1.5 完全一致；扩展须同步该文档与 config.md）──
# 每个标签：判定信号（正则，行级匹配，大小写不敏感）+ 主要映射 ASI（仅作输出备注，非逻辑依赖）。
_SURFACE_TAGS: dict[str, dict] = {
    "exec_code": {
        "signals": [r"subprocess", r"os\.system", r"\bshell\b", r"\bexec\b", r"\beval\b",
                    r"__import__", r"pickle", r"动态加载", r"importlib"],
        "mapped_asi": ["ASI01", "ASI05"],
    },
    "external_dep": {
        "signals": [r"pip install", r"\bnpm\b", r"\byarn\b", r"requirements\.txt", r"package\.json",
                    r"MCP server", r"\b插件\b", r"import .*第三方", r"\bimportlib\b"],
        "mapped_asi": ["ASI02", "ASI08"],
    },
    "fs_net_cred": {
        "signals": [r"open\(", r"os\.remove", r"requests\.", r"urllib", r"httpx", r"\bfetch\b",
                    r"读 env", r"getenv", r"os\.environ", r"~/\.ssh", r"~/\.aws", r"令牌", r"token"],
        "mapped_asi": ["ASI03", "ASI07", "ASI10"],
    },
    "secret_memory": {
        "signals": [r"写日志", r"\.json", r"\.md", r"memory", r"print.*密钥", r"缓存 token",
                    r"持久化", r"跨进程", r"管道"],
        "mapped_asi": ["ASI06", "ASI09"],
    },
    "user_content": {
        "signals": [r"读取用户对话", r"遵循.*instructions", r"面向用户内容", r"模板渲染", r"用户输入"],
        "mapped_asi": ["ASI04", "ASI07"],
    },
    "agent_comms": {
        "signals": [r"spawn.*agent", r"send_message", r"\bteam\b", r"多 agent", r"编排", r"mailbox"],
        "mapped_asi": ["ASI09", "ASI10"],
    },
    "prompt_intent": {
        "signals": [r"条件分支", r"占位", r"指令式", r"可被.*改写", r"用户输入的引用", r"外部输入"],
        "mapped_asi": ["ASI04", "ASI07"],
    },
    "tool_calls": {
        "signals": [r"read_file", r"write_to_file", r"execute_command", r"web_fetch", r"\bsearch\b",
                    r"function.?calling", r"MCP tool", r"\bSkills\b", r"工具调用"],
        "mapped_asi": ["ASI01", "ASI02", "ASI03"],
    },
    "system_instruction": {
        "signals": [r"system prompt", r"忽略先前指令", r"隐藏规则", r"覆盖安全策略", r"注入.*system",
                    r"修改.*指令"],
        "mapped_asi": ["ASI04", "ASI10"],
    },
}

# 预编译（大小写不敏感）
_COMPILED = {
    tag: [re.compile(s, re.IGNORECASE) for s in spec["signals"]]
    for tag, spec in _SURFACE_TAGS.items()
}


def _candidate_files(skill_dir: Path) -> list[Path]:
    """扫描被测技能客观产物：SKILL.md + scripts/ 下的 .py/.md/.json/.sh（不递归未知深目录，限定合理范围）。"""
    out: list[Path] = []
    skill_md = skill_dir / "SKILL.md"
    if skill_md.is_file():
        out.append(skill_md)
    scripts = skill_dir / "scripts"
    if scripts.is_dir():
        for p in scripts.rglob("*"):
            if p.is_file() and p.suffix in (".py", ".md", ".json", ".sh", ".txt"):
                out.append(p)
    return out


def _scan_one(path: Path) -> dict[str, list[str]]:
    """返回 tag -> 证据行号列表（文件:行）。"""
    hits: dict[str, list[str]] = {tag: [] for tag in _SURFACE_TAGS}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return hits
    rel = path.name
    for ln, text in enumerate(lines, 1):
        for tag, regs in _COMPILED.items():
            for rg in regs:
                if rg.search(text):
                    hits[tag].append(f"{rel}:L{ln}")
                    break  # 一行命中该 tag 一次即记录，避免噪声
    return hits


def tag_skill(skill_dir: Path) -> dict:
    tags_out = []
    evidence_index = {}
    for f in _candidate_files(skill_dir):
        for tag, evs in _scan_one(f).items():
            if evs:
                evidence_index.setdefault(tag, [])
                evidence_index[tag].extend(evs)
    for tag, spec in _SURFACE_TAGS.items():
        evs = evidence_index.get(tag)
        if evs:
            tags_out.append({
                "tag": tag,
                "evidence": sorted(set(evs)),
                "mapped_asi": spec["mapped_asi"],
            })
    return {"skill_surface_tags": tags_out, "evidence_index": evidence_index}


def main() -> None:
    ap = argparse.ArgumentParser(description="通用技能攻击面打标签（阶段 1.5 阶段 A）")
    ap.add_argument("--skill-dir", required=True, help="被测技能源目录（只读其 SKILL.md / scripts/）")
    ap.add_argument("--output", default=None, help="输出 JSON 路径（缺省 stdout）")
    args = ap.parse_args()

    skill_dir = Path(args.skill_dir).resolve()
    if not skill_dir.is_dir():
        print(f"❌ 被测技能目录不存在: {skill_dir}", file=sys.stderr)
        sys.exit(1)

    result = tag_skill(skill_dir)

    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
        n = len(result["skill_surface_tags"])
        print(f"✅ 攻击面打标完成：命中 {n} 个标签（共 {len(_SURFACE_TAGS)} 受控标签）"
              f"→ {args.output}")
    else:
        print(payload)


if __name__ == "__main__":
    main()
