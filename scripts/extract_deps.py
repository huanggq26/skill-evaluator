#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""依赖提取器（DEP-EXTRACT）：从被测技能上下文静态扫描外部依赖。

设计定位（见 references/dependency_availability.md §1.1）：
  • 【改动前置】修改提取规则 / source 标注 / 覆盖度或一致性核对逻辑前，
    必须先 read_file references/dependency_availability.md 并与之保持一致；未读不得改。
  • benchmark_manifest.json 是评测过程的中间产物，不是被测技能标准文件；
  • external_deps 不是可用性探测的「前提权威」，而是本提取器的产出（承载格式）；
  • 依赖来自被测技能真实上下文（SKILL.md + scripts/ + 配置），分两类：
      - explicit（显式定义）：技能明示要访问的资源（SKILL.md 写明调用某 API / MCP manifest 声明 server）；
      - implicit（隐式使用）：脚本/配置中硬编码的域名、连接串、外部 host:port。
  • 提取为纯静态扫描（无副作用、可复现），不发起任何网络请求、不消耗凭证；
    AI/上游仅负责把本产物整理进 benchmark_manifest.json 并做语义核对。

本脚本只抽取「形式特征」，不做语义理解——URL 是 http(s) 即视为外部端点候选，
域名为 host:port 即视为候选，连接串 scheme:// 即视为候选。框架后续只消费其抽象特征。

覆盖度核对：技能上下文出现外部访问点，但 external_deps 无对应条目 → coverage_gaps（提醒级）。
一致性核对：explicit 声明的 target 须真实出现在技能上下文，否则 consistency_issues（提醒级）。
"""
import argparse
import json
import os
import re
import sys
from typing import Optional

# ---- 形式特征正则（纯文本启发式，非业务理解）----
URL_RE = re.compile(r"https?://[^\s）），。\"'>`]+", re.IGNORECASE)
CONNSTR_RE = re.compile(r"\b[a-zA-Z][\w+.-]*://[^\s\"'`，。）)]+")   # scheme://host... 连接串（去尾引号/标点）
HOSTPORT_RE = re.compile(r"\b(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}\b:\d{2,5}")  # host:port
# 显式声明语境关键词（仅用于在 SKILL.md 中标记 explicit 而非 implicit）
EXPLICIT_CTX_RE = re.compile(
    r"(调用|访问|请求|接口|api|endpoint|endpoint\.|mcp|saas|外部服务|对接|连接.*?(数据库|服务|接口))",
    re.IGNORECASE,
)

SOURCE_CODE_EXT = {".py", ".js", ".ts", ".sh", ".rb", ".go", ".java", ".json", ".yaml", ".yml", ".toml", ".env"}
CONFIG_NAMES = {"skill.json", "mcp.json", "manifest.json", ".env", "config.json", "settings.json"}


def _norm_url(u: str) -> str:
    return u.rstrip(".,;）)。，、\"'`)")


def _collect_text(skill_dir: str):
    """收集技能上下文文本：SKILL.md + scripts/* + 配置文件。返回 (text, paths)。"""
    texts = {}
    skill_md = os.path.join(skill_dir, "SKILL.md")
    if os.path.isfile(skill_md):
        try:
            texts[skill_md] = open(skill_md, encoding="utf-8").read()
        except Exception:
            pass
    scripts_dir = os.path.join(skill_dir, "scripts")
    if os.path.isdir(scripts_dir):
        for fn in os.listdir(scripts_dir):
            p = os.path.join(scripts_dir, fn)
            if os.path.isfile(p) and os.path.splitext(fn)[1] in SOURCE_CODE_EXT:
                try:
                    texts[p] = open(p, encoding="utf-8", errors="ignore").read()
                except Exception:
                    pass
    # 配置类（技能根 + scripts）
    for base in (skill_dir, scripts_dir):
        if not os.path.isdir(base):
            continue
        for fn in os.listdir(base):
            if fn in CONFIG_NAMES or fn.endswith(".env") or fn.endswith(".mcp.json"):
                p = os.path.join(base, fn)
                if os.path.isfile(p):
                    try:
                        texts[p] = open(p, encoding="utf-8", errors="ignore").read()
                    except Exception:
                        pass
    return texts


def _collect_internal_resources(skill_dir: str):
    """收集被测技能自带的「内部依赖资源」：运行时必读、随技能分发的本地文件。

    与 external_api 不同，这些资源不联网、不打外部服务，而是技能目录内随包分发的
    只读资料（如 references/*.md、assets/、本地数据文件）。探测目标 = 文件是否存在且可读，
    用以验证「技能内部打包完整性」——若缺失会导致技能运行期行为残缺（如某技能的
    references/errors.md 决定失败降级话术、references/sync.md 决定同步机制）。

    返回 list[dict]：{id, path, kind, required, description}
    """
    skill_dir = str(skill_dir)
    resources = []
    rid = 0

    def _add(path_rel: str, description: str, required: bool = True):
        nonlocal rid
        full = os.path.join(skill_dir, path_rel)
        if not os.path.isfile(full):
            # 不存在也登记（供探测标记为不可达/缺失），但仅针对「约定应存在」的资源
            rid += 1
            resources.append({
                "id": f"internal_{rid}",
                "path": path_rel,
                "kind": "internal_resource",
                "required": required,
                "description": description,
                "exists": False,
            })
            return
        rid += 1
        resources.append({
            "id": f"internal_{rid}",
            "path": path_rel,
            "kind": "internal_resource",
            "required": required,
            "description": description,
            "exists": True,
        })

    # 约定应随技能分发的内部资源（按技能通用结构收集，存在才计入；不存在不误报）
    # 1) references/ 下所有 markdown（技能私有知识/话术/机制说明）
    refs_dir = os.path.join(skill_dir, "references")
    if os.path.isdir(refs_dir):
        for fn in sorted(os.listdir(refs_dir)):
            if fn.endswith(".md"):
                _add(f"references/{fn}", f"技能私有知识/机制说明：{fn}", required=True)
    # 2) assets/ 下资源（若有）
    assets_dir = os.path.join(skill_dir, "assets")
    if os.path.isdir(assets_dir):
        for fn in sorted(os.listdir(assets_dir)):
            if os.path.isfile(os.path.join(assets_dir, fn)):
                _add(f"assets/{fn}", f"技能自带资源：{fn}", required=False)
    # 3) 根目录关键文件
    for root_fn in ("SKILL.md", "README.md"):
        full = os.path.join(skill_dir, root_fn)
        if os.path.isfile(full):
            rid += 1
            resources.append({
                "id": f"internal_{rid}", "path": root_fn, "kind": "internal_resource",
                "required": True, "description": f"技能入口/说明：{root_fn}", "exists": True,
            })
    return resources


def extract_external_deps(skill_dir: str, existing: Optional[list] = None):
    """从技能上下文提取外部依赖。

    返回 dict：
      {
        "deps": [ {id, target, source, kind, credential, declared_fields, degradation, idempotency, ctx_hint} ],
        "coverage_gaps": [ "<在上下文中发现但未进入清单的访问点>" ],
        "consistency_issues": [ "<explicit 声明 target 未在上下文中出现>" ],
        "stats": {"explicit": n, "implicit": n, "scanned_files": n}
      }
    existing: 已存在于 benchmark_manifest.json 的 external_deps（用于覆盖度/一致性核对与去重合并）。
    """
    existing = existing or []
    texts = _collect_text(skill_dir)
    full_text = "\n".join(texts.values())

    found_targets = []  # (target, source, ctx_hint)
    seen = set()

    # 非外部端点判定（P3①）：本提取器只做「形式特征」提取，会把文档内相对路径/文件名
    # 误当外部依赖（实证：report.template.md、spec.md 被判 unknown url type，进而 0B 误出网探活）。
    # 过滤口径（禁止一刀切要求 http(s)，否则丢失 host:port 类真实依赖）：
    #   ① 含 "://" → 真实 scheme（http/https/连接串）→ 保留；
    #   ② 无 scheme 但形如 host.tld:port（HOSTPORT_RE 产出）→ 保留；
    #   ③ 无 scheme 且含路径分隔符或已知文件扩展名 → 是文档/文件路径，非外部服务 → 弃。
    _DOC_FILE_EXT = (".md", ".json", ".py", ".js", ".ts", ".sh", ".yaml", ".yml",
                     ".toml", ".csv", ".txt", ".html", ".css", ".xml", ".env")
    _HOSTPORT_FORM = re.compile(r"^(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}:\d{2,5}$")

    # 模板占位符：URL 含未填充的 {xxx} 属代码模板（如 .../skills/{slug}），非真实端点
    _TEMPLATE_PLACEHOLDER_RE = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")
    # RFC 2606 保留示例域名（example.com/.org/.net/.edu）— 文档/测试示例，非真实依赖
    _EXAMPLE_DOMAINS = ("example.com", "example.org", "example.net", "example.edu")
    # 字面占位 scheme（host 段非真实域名，如 scheme://host 常见于说明文字）
    _LITERAL_PLACEHOLDER_HOSTS = ("host", "hostname", "example", "your-host", "<host>")

    def _is_non_external(target: str) -> bool:
        low = target.lower()
        # ④ 模板占位 URL（含 {slug} 等未填充占位符）→ 代码模板，弃
        if _TEMPLATE_PLACEHOLDER_RE.search(target):
            return True
        # ⑤ RFC 保留示例域名 → 弃
        if any(d in low for d in _EXAMPLE_DOMAINS):
            return True
        if "://" in target:
            # ⑥ 字面占位 host（scheme://host 这类说明性写法）→ 弃
            host_part = target.split("://", 1)[1].split("/")[0].split(":")[0].strip().lower()
            if host_part in _LITERAL_PLACEHOLDER_HOSTS or "." not in host_part:
                return True
            return False  # ① 有 scheme 且 host 真实，保留
        # ⑦ 剥离 ":行号" 后缀后判定（如 "spec.md:119" 被 HOSTPORT 误匹配为 host:port）
        bare = re.sub(r":\d+$", "", target)
        if bare != target and ("/" in bare or "\\" in bare or bare.lower().endswith(_DOC_FILE_EXT)):
            return True
        if _HOSTPORT_FORM.match(target):
            return False  # ② host:port 形式，保留
        if "/" in target or "\\" in target:
            return True   # ③ 含路径分隔符 → 文件路径，弃
        if low.endswith(_DOC_FILE_EXT):
            return True   # ③ 纯文件名（无路径）但带文档扩展名 → 弃
        return False

    def _add(target, source, ctx_hint=""):
        target = _norm_url(target) if "://" in target else target
        if not target or target in seen:
            return
        if _is_non_external(target):
            return  # 文档路径/文件名误报，不计入外部依赖
        seen.add(target)
        found_targets.append((target, source, ctx_hint))

    for path, text in texts.items():
        is_skill_md = os.path.basename(path) == "SKILL.md"
        # URL
        for url in URL_RE.findall(text):
            url = _norm_url(url)
            if not url:
                continue
            if is_skill_md and EXPLICIT_CTX_RE.search(text):
                # SKILL.md 中处于显式语境 → explicit；否则 implicit（仍可能是声明，保守标 implicit）
                src = "explicit" if EXPLICIT_CTX_RE.search(
                    text[max(0, text.find(url) - 80):text.find(url) + len(url) + 80]) else "implicit"
            else:
                src = "implicit"
            _add(url, src, "URL in " + os.path.basename(path))
        # 连接串
        for cs in CONNSTR_RE.findall(text):
            cs = _norm_url(cs)
            if cs and cs not in seen:
                _add(cs, "implicit", "connstr in " + os.path.basename(path))
        # host:port
        for hp in HOSTPORT_RE.findall(text):
            if hp and hp not in seen:
                _add(hp, "implicit", "host:port in " + os.path.basename(path))

    # 合并已有 manifest 条目（保留其 richer 声明，source 标记以已有为准；若无则按上下文判定）
    existing_targets = {d.get("target") for d in existing if isinstance(d, dict)}
    deps = []
    for d in existing:
        if isinstance(d, dict) and d.get("target"):
            deps.append(d)
    # 上下文新增（manifest 未覆盖的）
    for target, src, hint in found_targets:
        if target in existing_targets:
            continue
        deps.append({
            "id": f"auto_{len(deps)+1}",
            "target": target,
            "source": src,
            "kind": "transient",       # 自动发现项默认瞬态，避免误否决
            "credential": "none",
            "declared_fields": [],
            "degradation": "",
            "idempotency": "",
            "ctx_hint": hint,
            "auto_discovered": True,
            # 模板/参数化标记：target 含通配 '*' 或路径参数 '{...}' → 不可直接请求，D1 跳过实探测
            "templated": ("*" in target) or ("{" in target and "}" in target),
            # 默认 method；只读匿名 GET 视为天然幂等（D6 可跳过），由探测器结合判定
            "method": "GET",
        })

    # 覆盖度核对：上下文中发现的访问点，是否都进了 deps
    dep_targets = {d.get("target") for d in deps}
    coverage_gaps = [t for (t, _, _) in found_targets if t not in dep_targets]

    # 一致性核对：explicit 声明的 target 须真实出现在上下文（防 AI 编造 / 声明脱节）
    consistency_issues = []
    for d in deps:
        if d.get("source") == "explicit" and d.get("target") and d["target"] not in full_text:
            consistency_issues.append(d["target"])

    stats = {
        "explicit": sum(1 for d in deps if d.get("source") == "explicit"),
        "implicit": sum(1 for d in deps if d.get("source") == "implicit"),
        "scanned_files": len(texts),
    }
    internal_resources = _collect_internal_resources(skill_dir)
    return {"deps": deps, "coverage_gaps": coverage_gaps,
            "consistency_issues": consistency_issues, "stats": stats,
            "internal_resources": internal_resources}


def main():
    ap = argparse.ArgumentParser(description="依赖提取器（DEP-EXTRACT）")
    ap.add_argument("--skill-dir", required=True, help="被测技能目录（上下文扫描源）")
    ap.add_argument("--manifest", default=None, help="可选，已有 benchmark_manifest.json（合并/核对用）")
    ap.add_argument("--output", default=None, help="可选，提取清单 JSON 输出路径")
    ap.add_argument("--write-manifest", action="store_true",
                    help="可选，将提取结果写回 manifest 的 external_deps（缺失时生成）")
    args = ap.parse_args()

    existing = []
    if args.manifest and os.path.isfile(args.manifest):
        try:
            existing = list(json.load(open(args.manifest, encoding="utf-8")).get("external_deps") or [])
        except Exception as e:
            print(f"⚠ 读取 manifest 失败: {e}", file=sys.stderr)

    result = extract_external_deps(args.skill_dir, existing)

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

    if args.write_manifest and args.manifest:
        m = {}
        if os.path.isfile(args.manifest):
            try:
                m = json.load(open(args.manifest, encoding="utf-8"))
            except Exception:
                pass
        m["external_deps"] = result["deps"]
        m["internal_resources"] = result["internal_resources"]
        m["skill_source"] = args.skill_dir
        # 保证 summary 契约有效（缺失时补默认计数为 0，避免样本契约守卫 E5/E7/E8 误阻断）
        if "summary" not in m or not isinstance(m.get("summary"), dict):
            m["summary"] = {}
        m["summary"].setdefault("total_functional_tasks", 0)
        m["summary"].setdefault("common_tasks", 0)
        m["summary"].setdefault("hard_tasks", 0)
        os.makedirs(os.path.dirname(args.manifest) or ".", exist_ok=True)
        with open(args.manifest, "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False, indent=2)
        print(f"✍ 已写回 external_deps（{len(result['deps'])} 项）到 {args.manifest}")

    s = result["stats"]
    print(f"✅ 依赖提取完成：扫描 {s['scanned_files']} 文件，显式 {s['explicit']} / 隐式 {s['implicit']}；"
          f"覆盖度缺口 {len(result['coverage_gaps'])}，一致性问题 {len(result['consistency_issues'])}")
    sys.exit(0)


if __name__ == "__main__":
    main()
