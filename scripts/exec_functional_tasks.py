#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
exec_functional_tasks.py — 通用 ExecAgent 驱动（阶段 2/3）

归属（对齐 AGENTS_RULES R6.1）：本脚本属评测框架通用执行驱动，**不绑定任何被测技能**。
它读取 benchmark_manifest.json 的 functional_tasks（阶段1产物）与每个任务的 TaskDescription.md，
真实驱动被测技能执行各功能任务，产出规范 ExecAgent 产物包（result.json / 时间戳 / task_metrics / worklog）。

通用性保证：
- endpoint / 调用方式从 TaskDescription.md 的『默认请求』（反引号包裹的 /api/...）解析，
  该信息来自被测技能自身声明（阶段0抽取结果），脚本不硬编码某技能域名或路径。
- baseline 模式按 exec_contract 硬约束 #12 屏蔽被测技能私有 API：若任务依赖私有 endpoint，
  如实记录 status=unsupported（原因：baseline 屏蔽私有 API，任务不可比），**不伪造**。

用法：
  # with_skill：真实执行全部功能任务
  python3 exec_functional_tasks.py --mode with_skill \
      --manifest <ws>/sample/benchmark_manifest.json \
      --exec-root <ws>/exec --skill-name aihot
  # baseline：屏蔽私有 API，诚实记录不可比任务
  python3 exec_functional_tasks.py --mode baseline \
      --manifest <ws>/sample/benchmark_manifest.json \
      --exec-root <ws>/exec --skill-name aihot
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

VALID_MODES = ("baseline", "with_skill")


def _norm_base(url: str) -> str:
    """从 external_deps target 提取 scheme+host 作为 API base。"""
    m = re.match(r"^(https?://[^/]+)", url)
    return m.group(1) if m else url.rstrip("/")


def _run(cmd: list[str]) -> int:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
    return r.returncode


def _parse_endpoint(task_dir: Path, checks: list[str] | None = None) -> str | None:
    """解析可调用的 endpoint。

    优先从被测技能声明的功能清单 checks 文本提取（来源：阶段0抽取的『默认请求：xxx』，
    即被测技能路由表声明的入口，属被测技能自身信息，脚本不硬编码）。
    其次回退到 TaskDescription.md 反引号包裹的 /api/...（若有）。
    返回相对路径（如 /api/v1/items?mode=selected）或带域名的完整 URL。
    """
    # 统一清理：去掉反引号与尾部中英文括号（Markdown 行内代码与说明文字的残留）
    def _clean(u: str) -> str:
        return u.strip().strip("`").rstrip(")）】").strip()

    if checks:
        for c in checks:
            if "默认请求" in c:
                # 候选选择（通用，可执行性优先）：
                # 1) 优先选**不含占位符**的可直接调用路径（如 `/api/v1/dailies/latest`
                #    优于 `/api/v1/dailies/{YYYY-MM-DD}`）；
                # 2) 若都含占位，取最后一个——链式说明的最终调用通常写在末尾
                #    （如 "先查 hot-topics；再调 /api/v1/stories/{publicId}"）。
                cands = [_clean(x) for x in re.findall(r"(/api/[^\s`\)】）]+)", c) if x.strip()]
                if cands:
                    ready = [x for x in cands if not _has_placeholder(x)]
                    return ready[0] if ready else cands[-1]
    td = task_dir / "TaskDescription.md"
    if not td.is_file():
        return None
    txt = td.read_text(encoding="utf-8")
    cands = [_clean(x) for x in re.findall(r"(/api/[^\s`\)】）]+)", txt) if x.strip()]
    if cands:
        ready = [x for x in cands if not _has_placeholder(x)]
        return ready[0] if ready else cands[-1]
    return None


def _parse_local_file(checks: list[str] | None) -> str | None:
    """解析「本地文件读取」型能力的相对路径（通用，与被测技能无关）。

    部分用户能力的『默认请求』不是 HTTP 调用，而是读取技能包内文件
    （如"读取 [完整精选同步](references/sync.md)"）。此处提取 Markdown 链接或
    裸文本中的相对文件路径，供执行时读取验证。
    """
    if not checks:
        return None
    for c in checks:
        if "默认请求" not in c:
            continue
        # Markdown 链接形式：[xxx](path/file.md)
        m = re.search(r"\]\(([^)]+\.(?:md|json|ya?ml|txt|csv))\)", c)
        if m:
            return m.group(1).strip()
        # 裸相对路径形式：references/xxx.md
        m = re.search(r"([A-Za-z0-9_./\-]+\.(?:md|json|ya?ml|txt|csv))", c)
        if m:
            return m.group(1).strip()
    return None


def _has_placeholder(url: str) -> bool:
    """判断 URL 是否仍含未解析占位（尖括号/花括号/单大写字母参数值）。"""
    if "<" in url or ">" in url or "{" in url or "}" in url:
        return True
    return bool(re.search(r"[A-Za-z_]+=[A-Z](\s|&|$)", url))


def _parse_objective(task_dir: Path) -> str:
    """解析任务的能力描述（人话），用于报告中解释 FTxx 编码是什么能力。

    来源优先级（均为 TaskDescription 的通用结构，与被测技能无关）：
    1. `objective:` 行；
    2. 一级标题 `# <ID> — <能力名>` 分隔符后的能力名（build_sample_pack 生成的通用模板格式）；
    3. Description 段首行。
    """
    td = task_dir / "TaskDescription.md"
    if not td.is_file():
        return ""
    lines = td.read_text(encoding="utf-8").splitlines()
    for line in lines:
        if line.strip().startswith("objective:"):
            return line.split(":", 1)[1].strip()
    # 一级标题：# FT07 — 能力名（分隔符可能是 — / - / :）
    for line in lines:
        m = re.match(r"^#\s+\S+\s*[—\-–:]\s*(.+)$", line)
        if m:
            return m.group(1).strip()
    # Description 段首行
    for i, line in enumerate(lines):
        if line.strip() == "### Description" and i + 2 < len(lines):
            return lines[i + 2].strip()
    return ""


def _call_api(endpoint: str, timeout: int = 20) -> tuple[int, str]:
    try:
        req = urllib.request.Request(endpoint, headers={"User-Agent": "skill-eval-exec/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        return -1, f"ERROR: {e}"


def _write_result(task_dir: Path, payload: dict) -> None:
    (task_dir / "result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# 通用占位符解析（不绑定任何被测技能）
# ─────────────────────────────────────────────────────────────────────────────
# 被测技能路由表里常见三类占位：
#   1) 枚举占位：<24h|7d>            → 取枚举首项（文档已给出可选值）
#   2) 具名占位：<slug> / <关键词>    → 需在被测技能文档中找该参数的实际取值示例
#   3) 路径占位：{publicId}          → 需前序调用取 ID（链式，见 _chain_lookup）
# 解析一律基于「被测技能自身文档 / 前序调用响应」，脚本不内置任何技能专属取值表。

_PLACEHOLDER_RE = re.compile(r"<[^<>|]*(?:\|[^<>|]*)+>")  # 枚举占位 <A|B>
_NAMED_RE = re.compile(r"<([^<>|]+)>")                    # 具名占位 <X>
_PATH_RE = re.compile(r"\{([^{}]+)\}")                    # 路径占位 {X}


def _resolve_placeholders(endpoint: str, skill_doc: str) -> tuple[str, list[str]]:
    """按被测技能文档解析 endpoint 中的占位符，返回 (解析后的 endpoint, 未解决占位列表)。

    通用规则（与被测技能无关）：
    - 枚举占位 <A|B>：取首项 A；
    - 具名占位 <X>：在被测技能文档中搜索「同名参数 = 具体值」的示例（如 category=model），
      取首个匹配值；
    - 路径占位 {X}：留待链式调用解析（此处保留，交由 _chain_lookup 处理）。
    """
    unresolved: list[str] = []

    # 1) 枚举占位：<24h|7d> → 24h
    def _enum_sub(m):
        inner = m.group(0)[1:-1]
        return inner.split("|")[0].strip()
    endpoint = _PLACEHOLDER_RE.sub(_enum_sub, endpoint)

    # 2) 具名占位：<slug> / <关键词> → 在被测技能文档中找同名参数的实际取值
    endpoint_tmpl = endpoint  # 供「按参数名回退」定位 `param=<placeholder>`

    def _named_sub(m):
        name = m.group(1).strip()
        # 候选查找键（权威度递减）：
        #   ① 占位符名本身（如 <slug>）
        #   ② 该占位符所属的参数名（如 category=<slug> → category）——**关键回退**
        # ② 不可省略：被测技能文档普遍按「参数名=示例值」记录，
        #    而占位符名只是类型描述（slug 是"分类标识"的意思，并非真实参数名），
        #    只按 ① 查找会永远落空，进而被误判为「文档未给出参数取值」。
        keys = [name]
        pm = re.search(r"[?&]([A-Za-z_][A-Za-z0-9_]*)=<" + re.escape(name) + r">",
                       endpoint_tmpl)
        if pm:
            keys.append(pm.group(1))
        for k in keys:
            # 在文档中搜索该键作为参数出现的具体取值
            pat = re.compile(rf"\b{re.escape(k)}\b\s*[=:：]\s*([A-Za-z0-9_\-\u4e00-\u9fff]{{1,40}})")
            hit = pat.search(skill_doc)
            if hit:
                return hit.group(1)
            # 退而求其次：键附近有引号包裹的值
            pat2 = re.compile(rf"{re.escape(k)}\s*[=:：]\s*[\"'`]?([A-Za-z0-9_\-]{{1,40}})[\"'`]?")
            hit2 = pat2.search(skill_doc)
            if hit2:
                return hit2.group(1)
        unresolved.append(name)
        return m.group(0)

    endpoint = _NAMED_RE.sub(_named_sub, endpoint)
    return endpoint, unresolved


def _enum_values(ep_tmpl: str) -> list[str]:
    """提取 endpoint 模板中「枚举占位」的取值列表（须在占位符解析**前**调用）。

    仅处理「恰好一个枚举占位」的情形——多个枚举占位会产生组合爆炸，
    且无法判断哪个组合才是"有数据的"，此时返回空（不做回退）。
    """
    ms = list(_PLACEHOLDER_RE.finditer(ep_tmpl))
    if len(ms) != 1:
        return []
    return [v.strip() for v in ms[0].group(0)[1:-1].split("|")]


def _enum_variants(resolved_ep: str, values: list[str], current: str) -> list[str]:
    """在**已解析**的 endpoint 上，把当前枚举值替换为其他候选值。

    背景：`_resolve_placeholders` 对枚举占位 `<24h|7d>` 按约定取**首项**，
    但首项未必有数据（实测 `window=24h` 返回 0 条，而 `window=7d` 返回 7 条），
    仅因取首项就判"无数据"，会把评测侧的取值策略问题误记为被测技能缺陷
    （见错误档案 ERR-015）。故保留其余候选供空结果时回退。

    ⚠️ 必须基于**已解析**的 endpoint 生成候选：
    若基于含占位的原始模板，候选会残留 `<slug>` 等未解析占位符，
    拼出的 URL 反而不可用（此为实现期实测到的缺陷）。

    通用性：不内置任何技能专属取值，候选完全来自被测技能文档声明的枚举。
    """
    out: list[str] = []
    if not values or not current:
        return out
    for v in values:
        if v == current:
            continue
        # 仅替换「参数值位置」的当前值，避免误伤 URL 其他部分
        for sep in ("=", "/"):
            pat = f"{sep}{current}"
            if pat in resolved_ep:
                out.append(resolved_ep.replace(pat, f"{sep}{v}", 1))
                break
    return out


def _resolve_bare_placeholders(endpoint: str, skill_doc: str) -> tuple[str, list[str]]:
    """解析「裸占位」：URL 参数值为单个大写字母的模板写法（如 limit=N、page=P）。

    通用约定（与被测技能无关）：
    - 值为单大写字母 → 视为模板占位（真实请求须给具体值）；
    - 数值语义参数（limit/count/size/top/num/per_page 等）→ 优先取被测技能文档中
      该参数的示例值，无则取最小可用正整数 1（数值参数的最小合法值）；
    - 其余参数名无法推断语义 → 保持未解决，由调用方诚实标注。
    """
    unresolved: list[str] = []
    numeric_names = ("limit", "count", "size", "top", "num", "per_page", "page", "length", "offset")

    def _sub(m):
        name, val = m.group(1), m.group(2)
        if not re.fullmatch(r"[A-Z]", val):
            return m.group(0)  # 非单大写字母，视为真实取值
        if name.lower() in numeric_names:
            # 优先从被测技能文档找该参数的实际示例值
            hit = re.search(rf"\b{re.escape(name)}\s*=\s*(\d{{1,6}})", skill_doc)
            if hit:
                return f"{name}={hit.group(1)}"
            return f"{name}=1"  # 数值参数的最小合法值
        unresolved.append(name)
        return m.group(0)

    endpoint = re.sub(r"([A-Za-z_]+)=([A-Z])(\s|&|$)", lambda m: _sub(m) + m.group(3), endpoint)
    return endpoint, unresolved


def _chain_lookup(endpoint: str, base_url: str, skill_doc: str) -> tuple[str, list[str]]:
    """解析路径占位 {publicId} 等：从上游列表接口取真实 ID 代入（通用链式调用）。

    通用做法（不绑定任何技能，完全依据被测技能文档声明的端点与字段名）：
    1. 在文档声明的列表端点响应中，找与该占位**同名**的字段；
    2. 若不同名（常见：字段叫 publicId，但响应里是资源链接 /story/<id>），
       则用「请求模板中的资源名」做单复数容错匹配——REST 惯例下
       集合路径 /stories/{id} 与资源链接 /story/<id> 指向同一资源。
    """
    names = _PATH_RE.findall(endpoint)
    if not names:
        return endpoint, []
    unresolved: list[str] = []
    for name in names:
        # 资源名提示：取占位所在路径段的前一段（如 /api/v1/stories/{publicId} → stories）
        res_hint = ""
        m_res = re.search(r"/([A-Za-z][A-Za-z0-9_\-]*)/\{" + re.escape(name) + r"\}", endpoint)
        if m_res:
            res_hint = m_res.group(1)
        id_val = _fetch_first_field(base_url, skill_doc, name, resource_hint=res_hint)
        if id_val:
            endpoint = endpoint.replace("{" + name + "}", str(id_val))
        else:
            unresolved.append(name)
    return endpoint, unresolved


def _fetch_first_field(base_url: str, skill_doc: str, field: str,
                       resource_hint: str = "") -> str | None:
    """从被测技能文档声明的列表端点中，取首个条目的指定字段值（通用）。"""
    if not base_url:
        return None
    # 文档中出现的候选列表端点（含 /api/ 且不含占位）
    cands = re.findall(r"`(/api/[^\s`]*)`", skill_doc)
    cands += re.findall(r"`(https?://[^`]*/api/[^\s`]*)`", skill_doc)
    for raw in cands:
        if "<" in raw or "{" in raw:
            continue  # 跳过本身含占位的端点
        url = raw if raw.startswith("http") else base_url.rstrip("/") + raw
        code, body = _call_api(url)
        if code != 200:
            continue
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else (
            data.get("items") or data.get("data") or data.get("topics") or [])
        if isinstance(items, list) and items:
            first = items[0]
            if isinstance(first, dict):
                # ① 直接字段
                if field in first:
                    return str(first[field])
                # ② 嵌套 dict（如 links.story 对象）
                for v in first.values():
                    if isinstance(v, dict) and field in v:
                        return str(v[field])
                # ③ 嵌套值是 REST 资源 URL 字符串（如 links.story = "/story/abc123"）：
                #    先按字段名匹配；字段名与 URL 段常不同名（字段 publicId vs 段 story），
                #    此时用请求模板的资源名做单复数容错匹配（stories ≈ story）——REST 惯例。
                seg_names = [s for s in (field.lower(), resource_hint.lower()) if s]
                # 单复数容错：stories ↔ story
                for s in list(seg_names):
                    if s.endswith("ies"):
                        seg_names.append(s[:-3] + "y")
                    elif s.endswith("s"):
                        seg_names.append(s[:-1])
                    else:
                        seg_names.append(s + "s")
                for v in first.values():
                    if isinstance(v, dict):
                        for sv in v.values():
                            if not isinstance(sv, str) or "/" not in sv:
                                continue
                            for seg in seg_names:
                                if not seg:
                                    continue
                                hit = re.search(rf"/{re.escape(seg)}/([^/?#]+)", sv, re.IGNORECASE)
                                if hit:
                                    return hit.group(1)
    return None


def exec_one(task_id: str, task_dir: Path, mode: str, skill_name: str,
             checks: list[str] | None = None, base_url: str = "",
             skill_doc: str = "", skill_dir: "Path | None" = None) -> int:
    """执行单个功能任务，产出规范产物包。返回 0 成功 / 非0 失败。

    产物布局（对齐 check_exec_artifacts 期望）：<mode>/tasks/<tid>/results/
      - result.json / task_metrics.json / start|end_timestamp.json / worklog.json
    """
    res_dir = task_dir / "results"
    res_dir.mkdir(parents=True, exist_ok=True)
    metric_mode = "with_skill" if mode == "with_skill" else "baseline"
    _rel = _parse_endpoint(task_dir, checks=checks)
    endpoint = (_norm_base(base_url).rstrip("/") + _rel) if (_rel and not _rel.startswith("http")) else _rel
    endpoint = endpoint or None
    objective = _parse_objective(task_dir)
    status = "success"
    notes: list[str] = []
    evidence: list[str] = []
    # 真实执行：用「被测技能文档 + 前序调用」解析占位符（通用机制，不内置任何技能专属取值）
    enum_fallback: list[str] = []
    if endpoint:
        # 枚举取值须在占位符解析「前」提取（解析后占位符已被替换为具体值）
        enum_vals = _enum_values(endpoint)
        endpoint, unresolved_named = _resolve_placeholders(endpoint, skill_doc)
        endpoint, unresolved_bare = _resolve_bare_placeholders(endpoint, skill_doc)
        endpoint, unresolved_path = _chain_lookup(endpoint, base_url, skill_doc)
        unresolved = unresolved_named + unresolved_bare + unresolved_path
        # 占位全部解析成功时，预计算枚举回退候选（首项无数据时改用其他合法取值）
        if not unresolved and enum_vals:
            enum_fallback = _enum_variants(endpoint, enum_vals, enum_vals[0])
        if unresolved:
            # 文档中未给出这些参数的取值、也无法从前序调用获得 →
            # 这是「被测技能文档未声明该能力的调用方式」，属**技能文档缺陷的真实信号**，
            # 不伪装成「评测未覆盖」。
            status = "unsupported"
            notes.append(
                "被测技能文档未给出参数取值，且无法从前序调用推导："
                + "、".join(unresolved)
                + "；属技能文档声明不完整（用户可感知能力未说明调用方式），非评测侧限制"
            )
            endpoint = None

    # 1) 生成 task_metrics 骨架
    tm_path = res_dir / "task_metrics.json"
    if _run(["python3", "scripts/generate_task_metrics.py",
             "--output", str(tm_path), "--task-id", task_id, "--mode", metric_mode]) != 0:
        return 1

    # 2) 时间戳：start
    start_ts = res_dir / "start_timestamp.json"
    if _run(["python3", "scripts/write_system_timestamp.py", "--output", str(start_ts)]) != 0:
        return 1

    t0 = time.time()

    if mode == "baseline":
        # 硬约束 #12：baseline 屏蔽被测技能私有 API。若任务依赖私有 endpoint → 如实记 unsupported
        if endpoint:
            status = "unsupported"
            notes.append("baseline 模式屏蔽被测技能私有 API；该任务依赖私有 endpoint，无法在屏蔽态可比执行")
            result_payload = {
                "status": "unsupported",
                "objective": objective,
                "summary": "（baseline 屏蔽态：任务依赖被测技能私有 API，未执行）",
                "items": [],
                "evidence": [],
                "notes": notes,
            }
        else:
            status = "unsupported"
            notes.append("baseline 屏蔽态：按纪律未执行依赖技能私有能力的任务")
            result_payload = {"status": "unsupported", "objective": objective,
                              "summary": "（baseline 屏蔽态未执行）", "items": [], "evidence": [], "notes": notes}
    else:
        # with_skill：真实执行
        if not endpoint:
            # 无 HTTP 端点时，尝试「本地文件读取」型能力（如读取技能包内的说明文件）。
            # 这类能力不依赖网络，属被测技能声明的真实用户能力，应真实执行而非跳过。
            _local_rel = _parse_local_file(checks)
            _local_path = (skill_dir / _local_rel) if (skill_dir and _local_rel) else None
            if _local_path and _local_path.is_file():
                try:
                    _content = _local_path.read_text(encoding="utf-8", errors="replace")
                    status = "success"
                    result_payload = {
                        "status": "success",
                        "objective": objective,
                        "summary": f"读取技能包内文件 {_local_rel} 成功，共 {len(_content)} 字符",
                        "items": [{"path": _local_rel, "chars": len(_content)}],
                        "evidence": [{"local_file": _local_rel, "chars": len(_content)}],
                        "notes": notes,
                    }
                    evidence.append(_local_rel)
                except OSError as e:
                    status = "failed"
                    result_payload = {"status": "failed", "objective": objective,
                                      "summary": f"读取 {_local_rel} 失败：{e}", "items": [],
                                      "evidence": [], "notes": [str(e)] + notes}
            else:
                status = "unsupported"
                notes.append("未从 TaskDescription 解析到可调用的 endpoint 或本地文件路径"
                             "（被测技能未声明该能力的调用方式）")
                result_payload = {"status": "unsupported", "objective": objective,
                                  "summary": "（无可用 endpoint/文件，未执行）", "items": [], "evidence": [], "notes": notes}
        else:
            code, body = _call_api(endpoint)
            if code == 200:
                try:
                    data = json.loads(body)
                    items = data if isinstance(data, list) else data.get("items", data.get("data", [data]))
                    # 空结果回退：枚举占位只取了首项，而首项未必有数据。
                    # 改用同枚举的其他合法取值重试，避免把「评测侧取值偏窄」
                    # 误记为被测技能缺陷（见错误档案 ERR-015）。
                    if (not items) and enum_fallback:
                        for cand in enum_fallback:
                            c2, b2 = _call_api(cand)
                            if c2 != 200:
                                continue
                            try:
                                d2 = json.loads(b2)
                            except json.JSONDecodeError:
                                continue
                            it2 = (d2 if isinstance(d2, list)
                                   else d2.get("items", d2.get("data", [d2])))
                            if it2:
                                notes.append(
                                    "枚举取值回退：首项取值返回空，改用同枚举的其他合法取值"
                                    f" → {cand}"
                                )
                                endpoint, body, items, code = cand, b2, it2, c2
                                break
                    result_payload = {
                        "status": "success",
                        "objective": objective,
                        "summary": f"调用 {endpoint} 成功，返回 {len(items) if isinstance(items, list) else '?'} 条数据",
                        "items": items if isinstance(items, list) else [items],
                        "evidence": [{"endpoint": endpoint, "http_code": code, "bytes": len(body)}],
                        "notes": notes,
                    }
                    evidence.append(endpoint)
                except json.JSONDecodeError:
                    status = "partial"
                    result_payload = {"status": "partial", "objective": objective,
                                      "summary": "返回非 JSON 文本", "items": [],
                                      "evidence": [{"endpoint": endpoint, "http_code": code, "bytes": len(body)}],
                                      "notes": ["响应非 JSON"] + notes}
            else:
                status = "failed"
                result_payload = {"status": "failed", "objective": objective,
                                  "summary": f"调用 {endpoint} 失败 HTTP {code}",
                                  "items": [], "evidence": [{"endpoint": endpoint, "http_code": code}],
                                  "notes": [f"HTTP {code}"] + notes}

    _write_result(res_dir, result_payload)

    # 3) 时间戳：end
    end_ts = res_dir / "end_timestamp.json"
    if _run(["python3", "scripts/write_system_timestamp.py", "--output", str(end_ts)]) != 0:
        return 1

    # 4) 回填耗时
    if _run(["python3", "scripts/backfill_task_duration.py",
             "--task-metrics", str(tm_path), "--start", str(start_ts),
             "--end", str(end_ts), "--task-id", task_id, "--mode", metric_mode]) != 0:
        return 1

    # 5) worklog
    elapsed = time.time() - t0
    worklog = {
        "task_id": task_id, "mode": mode, "skill": skill_name,
        "endpoint": endpoint, "status": status,
        "elapsed_sec": round(elapsed, 2),
        "objective": objective,
    }
    (res_dir / "worklog.json").write_text(json.dumps(worklog, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[exec] {task_id} [{mode}] status={status} endpoint={endpoint or 'N/A'}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=VALID_MODES)
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--exec-root", required=True, type=Path)
    ap.add_argument("--skill-name", required=True)
    ap.add_argument("--sample-root", required=True, type=Path, help="含各 FT 任务 TaskDescription 的 sample 目录")
    ap.add_argument("--skill-dir", default=None, type=Path,
                    help="被测技能目录（读取其 SKILL.md 用于通用占位符解析，不绑定具体技能）")
    args = ap.parse_args()

    # 读取被测技能文档：用于解析 endpoint 占位符（枚举/具名参数的取值均从该文档搜索，
    # 脚本不内置任何技能专属取值表，保证通用性）。
    skill_doc = ""
    if args.skill_dir:
        # 占位符的取值示例常声明在子文档（如 references/*.md），
        # 仅读 SKILL.md 会漏掉这些材料，导致占位符无法解析。
        # 顺序固定：SKILL.md 优先，其后按路径排序追加（保证结果可复现）；
        # 不绑定任何具体技能的目录结构（通用性硬约束）。
        parts = []
        main_doc = args.skill_dir / "SKILL.md"
        if main_doc.is_file():
            parts.append(main_doc.read_text(encoding="utf-8", errors="replace"))
        ref_dir = args.skill_dir / "references"
        if ref_dir.is_dir():
            for p in sorted(ref_dir.rglob("*.md")):
                try:
                    parts.append(p.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    continue
        skill_doc = "\n".join(parts)
        if not skill_doc:
            print("[exec] 警告：未在被测技能目录找到 SKILL.md，占位符解析将受限", file=sys.stderr)

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    tasks = manifest.get("functional_tasks", [])
    if not tasks:
        # ERR-018 治本：空功能清单是**合法状态**（阶段0按功能表口径过滤后为空，
        # 如工具型技能全文仅有产出物句）。无任务可执行 ≠ 错误；返回 0 让管线继续，
        # 安全/质量维度照常评测（此前 return 2 会让 runner 硬中止，连其他维度都评不了）。
        print("[exec] manifest 功能任务为空（阶段0按功能表口径未抽到用户功能，"
              "功能维度不适用）：本模式无事可做，跳过执行，不视为失败。", file=sys.stderr)
        return 0

    # 从被测技能 manifest 的 external_deps 提取 API base（通用，不硬编码某技能域名）
    base_url = ""
    for dep in manifest.get("external_deps", []):
        tgt = dep.get("target", "")
        if "/api/" in tgt or tgt.startswith("http"):
            base_url = _norm_base(tgt)
            break

    # 从阶段0产物 functional_tasks.generated.jsonl 加载 <tid> → checks（含默认请求 endpoint）
    ft_checks: dict[str, list[str]] = {}
    gen_ft = args.sample_root / "functional_tasks.generated.jsonl"
    if gen_ft.is_file():
        for line in gen_ft.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            ft_checks[d.get("id")] = d.get("checks", [])

    # 按 tier 分组目录（与 build_sample_pack 一致）：l0_goal→common, l1_artifact→hard, l2_internal→internal
    tier_dir = {"l0_goal": "common", "l1_artifact": "hard", "l2_internal": "internal"}

    exec_mode_dir = args.exec_root / args.mode
    failures = 0
    for t in tasks:
        tid = t.get("id")
        tier = t.get("tier", "l0_goal")
        grp = tier_dir.get(tier, "common")
        # sample 任务目录：<sample-root>/<grp>/<tid>/
        task_dir = args.sample_root / grp / tid
        if not task_dir.is_dir():
            print(f"[exec] 跳过 {tid}：sample 任务目录不存在 {task_dir}", file=sys.stderr)
            failures += 1
            continue
        # 输出目录：<exec-root>/<mode>/tasks/<tid>/（产物在 results/ 子目录）
        out_dir = exec_mode_dir / "tasks" / tid
        out_dir.mkdir(parents=True, exist_ok=True)
        # 复制 TaskDescription 到执行工作区（保持契约）
        import shutil
        shutil.copyfile(task_dir / "TaskDescription.md", out_dir / "TaskDescription.md")
        if exec_one(tid, out_dir, args.mode, args.skill_name,
                    checks=ft_checks.get(tid), base_url=base_url,
                    skill_doc=skill_doc, skill_dir=args.skill_dir) != 0:
            failures += 1

    # 生成阶段级 stage_metrics 骨架
    stage_metrics = exec_mode_dir / "stage_metrics.json"
    _run(["python3", "scripts/generate_stage_metrics.py",
          "--output", str(stage_metrics), "--mode", args.mode])

    print(f"[exec] 完成 {args.mode}：{len(tasks)-failures}/{len(tasks)} 成功，{failures} 失败")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
