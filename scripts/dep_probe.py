#!/usr/bin/env python3
"""外部依赖可用性探测（DEP-AVAIL）。

对被测技能声明的 `external_deps` 做真实可用性探测：
  - 评测器代表被测技能去访问它运行时依赖的公开数据源，验证「技能依赖的外部源当前是否可达」；
  - 这与「评测器自身是否联网」无关——探测的是被测技能的外部依赖，属设计允许。

探测结果写入 `<spec>/results/dep/dep_metrics.json`，供 cacu_total_score 与 generate_outputs 渲染。

退出码：0=正常写盘（无论依赖可达与否都算「已执行」）；2=参数/IO 错误。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

try:
    import urllib.request
    import urllib.error
except Exception:  # pragma: no cover
    urllib = None  # type: ignore


# 不在此处硬编码任何具体技能的探测端点——评测器是通用能力。
# 探测目标一律取自被测技能 manifest 自己声明的 `external_deps[].target`；
# 仅当某依赖声明得过于笼统（只有 host、没有具体路径）时，才回退探测该 host 根路径，
# 此时 404 仍按「模板化/基路径端点、需补具体示例」归 config_defect（不否决），
# 因此不会因缺少技能专属代表性路径而误判。
_PROBE_PATH_BY_HOST = {}


def _probe_url_for(dep: dict) -> str:
    """把 manifest 的 target（可能含通配 *）解析成一个具体可探测 URL。

    优先用该依赖自身的 target 路径（去掉通配后缀），让每个声明源都探测到自己的端点；
    仅当 target 过于笼统（仅 host 或仅 host+通配）时，回退到 host 根路径探测。
    """
    target = dep.get("target") or dep.get("url") or ""
    if not target:
        return ""
    parsed = urlparse(target)
    host = parsed.netloc
    if "*" in target:
        base = target.split("*", 1)[0]
    else:
        base = target
    p = urlparse(base)
    path = (p.path or "").rstrip("/")
    # 若该依赖自身已给出具体路径，直接探它自己
    if path:
        return f"{p.scheme}://{host}{path}"
    # 否则回退到 host 根路径（通用、不绑定任何具体技能）
    return f"{parsed.scheme}://{host}"


def _probe_one(dep: dict) -> dict:
    target = dep.get("target") or dep.get("url") or ""
    dep_id = dep.get("id") or target
    result = {
        "dep_id": dep_id,
        "target": target,
        "checker": "dep_probe.http",
        "status": "unknown",
        "kind": "external_api",
        "category": "env_issue",  # 默认当作环境/瞬态，结构性否决需在 4xx/5xx 时显式置 contract_defect
        "score": None,
        "retry": "无需",
        "message": "",
        "http_status": None,
        "latency_ms": None,
    }
    if not target:
        result.update(status="skipped", category="config_defect",
                      message="被测技能未声明该依赖的端点地址（target/url），无法探测")
        result["retry"] = "在被测技能中声明该依赖的**完整端点地址**（当前只有域名/通配，无法探测具体接口）"
        return result
    # HTTP 方法（R20）：manifest 可为每个依赖显式声明 `method`；未声明时按 GET 探测。
    # 实证：POST 端点被 GET 探测返回 405，曾被判为 contract_defect（技能自身缺陷）
    # 并**硬拦截全流程**——属探测方法不匹配，非技能契约问题。
    method = str(dep.get("method") or "GET").upper()
    if method not in ("GET", "POST", "HEAD", "PUT", "PATCH"):
        method = "GET"
    method_declared = bool(dep.get("method"))
    url = _probe_url_for(dep)
    result["probe_url"] = url
    result["probe_method"] = method
    if urllib is None:
        result.update(status="error", category="env_issue",
                      message="运行环境缺少 urllib，无法发起探测")
        return result
    try:
        req = urllib.request.Request(url, method=method,
                                     headers={"User-Agent": "skill-evaluator/dep-probe"})
        _t0 = time.time()
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            code = resp.getcode()
        _dt = (time.time() - _t0) * 1000.0
        result["http_status"] = code
        result["latency_ms"] = round(_dt, 1)
        if 200 <= code < 300:
            result.update(status="pass", category="contract_defect",
                          score=100, message=f"依赖可达（HTTP {code}，{round(_dt,1)}ms）")
        elif 400 <= code < 500:
            # 401/403：请求已完成 DNS/连接/HTTP 往返且服务端有响应——链路可达已证明，
            # 拿不到数据只因缺有效凭证，属「需凭据但未配置」（dependency_availability.md §3 config missing），
            # 归 config_defect：不计入失败数（不拉低评分）、不触发否决（不阻断全流程）。
            # 模板化端点（含 {）或仅到版本基路径（如 /api/v1）——缺少具体实例/动作，同理不否决。
            _templated = "{" in (dep.get("target") or "")
            _u = urlparse(url)
            _base_only = _u.path.rstrip("/") in ("", "/api", "/api/v1", "/v1")
            _auth_missing = code in (401, 403)
            if _auth_missing:
                result.update(status="skip", category="config_defect", score=None,
                              message=f"HTTP {code}（端点可达且已响应，但缺少有效凭证；"
                                      f"属「需凭据但未配置」，非技能契约缺陷）")
                result["retry"] = "补凭证/鉴权后重测（不阻断、不计入可用性评分）"
            elif _templated or _base_only:
                result.update(status="skip", category="config_defect", score=None,
                              message=f"HTTP {code}（模板化/基路径端点，需具体实例才能探测，非技能缺陷）")
                result["retry"] = "在被测技能的端点声明处给出**可访问的完整示例地址**（含具体路径，便于探测连通性）"
            elif code == 405 and not method_declared:
                # R32：GET 不被允许时，**先自动查明真实访问方式**，再决定归类。
                # 背景（table_column_relations 实证）：8 个依赖中 6 个 GET 返回 405，
                # 但同一主机 db_list 用 GET 返回 200——证明链路可达、无需授权，
                # 405 的真实语义是「端点存在但不允许 GET」，多为 POST 接口。
                # 此前直接按「方法不匹配」跳过，使可用性结论失真（既不知能否用，也不知该用什么方法）。
                # 故此处按候选方法依次试探，命中 2xx 即以真实结果判定。
                # 顺序说明：HEAD 无副作用故优先；其次 POST/PUT（查询类端点通常幂等，
                # 且对象是技能自己声明的依赖，与随机站点无关）。
                _alt_ok = None
                for _alt_m in ("HEAD", "POST", "PUT"):
                    try:
                        _alt_req = urllib.request.Request(
                            url, method=_alt_m,
                            headers={"User-Agent": "skill-evaluator/dep-probe"},
                        )
                        _alt_t0 = time.time()
                        with urllib.request.urlopen(_alt_req, timeout=10) as _alt_resp:  # noqa: S310
                            _alt_code = _alt_resp.getcode()
                        _alt_ms = round((time.time() - _alt_t0) * 1000.0, 1)
                        if 200 <= _alt_code < 300:
                            _alt_ok = (_alt_m, _alt_code, _alt_ms)
                            break
                    except urllib.error.HTTPError as _alt_e:  # 非 2xx 视为该方法不匹配，继续试下一个
                        continue
                    except (OSError, ValueError):
                        continue
                if _alt_ok:
                    _m, _c, _ms = _alt_ok
                    result["probe_method"] = _m
                    result["http_status"] = _c
                    result["latency_ms"] = _ms
                    result.update(
                        status="pass", category="contract_defect", score=100,
                        message=f"依赖可达（HTTP {_c}；GET 返回 405，自动识别真实方法为 {_m}）",
                    )
                    result["retry"] = (
                        f"建议在被测技能中标注该端点的 HTTP 方法（{_m}）：写在 SKILL.md 的端点声明或调用脚本中；"
                        f"避免每次探测都自动试错"
                    )
                else:
                    # 候选方法均不通：确属「未声明 method 导致无法探测」，
                    # 归 config_defect：不拉低评分、不触发否决（R20）。
                    result.update(status="skip", category="config_defect", score=None,
                                  message=f"HTTP 405（端点可达但不允许 GET；已自动试 HEAD/POST/PUT 均不可达，"
                                          f"被测技能未标注该端点的 HTTP 方法，探测方法不匹配，非技能契约缺陷）")
                    result["retry"] = "在 SKILL.md（或调用该端点的脚本）中标注其 HTTP 方法（如 POST）后重测——当前以 GET 探测返回 405，无法判定端点是否可用"
            else:
                # 其余 4xx 仍属结构性契约问题（端点不存在），标记 contract_defect 以便否决路径
                result.update(status="fail", category="contract_defect", score=0,
                              message=f"依赖返回客户端错误 HTTP {code}，疑似端点契约缺陷")
                result["retry"] = "核查技能对该端点的调用契约"
        elif 500 <= code < 600:
            result.update(status="fail", category="env_issue",
                          score=0, message=f"依赖服务端错误 HTTP {code}（瞬态，不否决）")
            result["retry"] = "稍后重试"
        else:
            result.update(status="warn", category="env_issue",
                          score=50, message=f"依赖返回非标准状态码 HTTP {code}")
    except urllib.error.HTTPError as e:  # 某些实现走异常
        code = e.code
        result["http_status"] = code
        if 400 <= code < 500:
            _templated = "{" in (dep.get("target") or "")
            _u = urlparse(url)
            _base_only = _u.path.rstrip("/") in ("", "/api", "/api/v1", "/v1")
            _auth_missing = code in (401, 403)  # 同上：端点已响应但缺凭证 → 配置待补，不否决
            if _auth_missing:
                result.update(status="skip", category="config_defect", score=None,
                              message=f"HTTP {code}（端点可达且已响应，但缺少有效凭证；"
                                      f"属「需凭据但未配置」，非技能契约缺陷）")
                result["retry"] = "补凭证/鉴权后重测（不阻断、不计入可用性评分）"
            elif _templated or _base_only:
                result.update(status="skip", category="config_defect", score=None,
                              message=f"HTTP {code}（模板化/基路径端点，需具体实例才能探测，非技能缺陷）")
                result["retry"] = "在被测技能的端点声明处给出**可访问的完整示例地址**（含具体路径，便于探测连通性）"
            elif code == 405 and not method_declared:
                # R32：GET 不被允许时，**先自动查明真实访问方式**再决定归类。
                # ⚠ 本分支位于 `except HTTPError` 内——urlopen 对 4xx 会抛异常，故**真实执行
                # 路径在此**；try 块内的同名分支不可达（已标注，勿在其中重复实现）。
                # 实证：table_column_relations 8 项依赖中 6 项 GET 返回 405，而同主机
                # db_list 用 GET 返回 200 —— 链路可达、无需授权，405 的真实语义是
                # 「端点存在但不允许 GET」（多为 POST 接口）。此前直接跳过使结论失真。
                # 顺序：HEAD 无副作用故优先，其次 POST/PUT（对象为技能自声明的依赖）。
                _alt_ok = None
                for _alt_m in ("HEAD", "POST", "PUT"):
                    try:
                        _alt_req = urllib.request.Request(
                            url, method=_alt_m,
                            headers={"User-Agent": "skill-evaluator/dep-probe"},
                        )
                        _alt_t0 = time.time()
                        with urllib.request.urlopen(_alt_req, timeout=10) as _alt_resp:  # noqa: S310
                            _alt_code = _alt_resp.getcode()
                        _alt_ms = round((time.time() - _alt_t0) * 1000.0, 1)
                        if 200 <= _alt_code < 300:
                            _alt_ok = (_alt_m, _alt_code, _alt_ms)
                            break
                    except (urllib.error.HTTPError, OSError, ValueError):
                        continue
                if _alt_ok:
                    _m, _c, _ms = _alt_ok
                    result["probe_method"] = _m
                    result["http_status"] = _c
                    result["latency_ms"] = _ms
                    result.update(
                        status="pass", category="contract_defect", score=100,
                        message=f"依赖可达（HTTP {_c}；GET 返回 405，自动识别真实方法为 {_m}）",
                    )
                    result["retry"] = (
                        f"建议在被测技能中标注该端点的 HTTP 方法（{_m}）：写在 SKILL.md 的端点声明或调用脚本中；"
                        f"避免每次探测都自动试错"
                    )
                else:
                    result.update(status="skip", category="config_defect", score=None,
                                  message=f"HTTP 405（端点可达但不允许 GET；已自动试 HEAD/POST/PUT 均不可达，"
                                          f"被测技能未标注该端点的 HTTP 方法，探测方法不匹配，非技能契约缺陷）")
                    result["retry"] = "在 SKILL.md（或调用该端点的脚本）中标注其 HTTP 方法（如 POST）后重测——当前以 GET 探测返回 405，无法判定端点是否可用"
            else:
                result.update(status="fail", category="contract_defect", score=0,
                              message=f"依赖返回客户端错误 HTTP {code}，疑似端点契约缺陷")
                result["retry"] = "核查技能对该端点的调用契约"
        else:
            result.update(status="fail", category="env_issue", score=0,
                          message=f"依赖错误 HTTP {code}（瞬态，不否决）")
            result["retry"] = "稍后重试"
    except Exception as e:  # 网络不可达 / 超时 / DNS —— 属环境瞬态
        result.update(status="fail", category="env_issue", score=0,
                      message=f"依赖不可达：{type(e).__name__}: {e}（环境/网络瞬态，不否决）")
        result["retry"] = "确认运行环境可访问该外部源后重试"
    return result


def _probe_internal_one(res: dict, skill_dir: str) -> dict:
    """探测「内部依赖资源」：随技能分发的本地文件是否存在且可读（不联网）。"""
    result = dict(res)
    rel = res.get("path") or ""
    full = os.path.join(skill_dir, rel) if skill_dir else rel
    exists = bool(res.get("exists")) or (os.path.isfile(full) if full else False)
    if not exists:
        result.update(status="fail", category="internal_missing", score=0,
                      message=f"内部依赖资源缺失或不可读：{rel}（技能随包分发完整性缺陷）")
        result["retry"] = f"确认技能目录包含 {rel}"
    else:
        try:
            with open(full, "r", encoding="utf-8") as fh:
                fh.read(1)
            result.update(status="pass", category="reachable", score=100,
                          message=f"内部依赖资源存在且可读：{rel}")
        except Exception as e:
            result.update(status="fail", category="internal_unreadable", score=0,
                          message=f"内部依赖资源不可读：{rel}（{type(e).__name__}: {e}）")
            result["retry"] = f"修复 {rel} 的读取权限/编码"
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="外部依赖可用性探测")
    ap.add_argument("--manifest", required=True, help="benchmark_manifest.json 路径")
    ap.add_argument("--output", required=True, help="dep_metrics.json 输出路径")
    args = ap.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(f"[dep_probe] manifest 不存在: {manifest_path}", file=sys.stderr)
        return 2
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[dep_probe] manifest 解析失败: {e}", file=sys.stderr)
        return 2

    deps = manifest.get("external_deps") or []
    internal = manifest.get("internal_resources") or []
    _skill_dir = str(manifest.get("skill_source") or "")
    # 外部运行时依赖：参与可用性评分与结构性否决
    dims = [_probe_one(d) for d in deps]
    # 随包完整性：不参与可用性评分、不触发否决；作为质量报告「随包资源完整性」的数据来源
    internal_checks = [_probe_internal_one(r, _skill_dir) for r in internal]
    passed = sum(1 for d in dims if d.get("status") == "pass")
    failed = sum(1 for d in dims if d.get("status") == "fail")
    # 结构性否决：仅外部端点的 contract_defect（契约缺陷）；随包文件缺失/不可读不否决
    structural_fail = any(d.get("category") == "contract_defect"
                          and d.get("status") == "fail" for d in dims)
    declared = deps
    score = 100 if (dims and failed == 0) else (0 if structural_fail else (50 if dims else None))
    _int_fail = sum(1 for d in internal_checks if d.get("status") == "fail")

    out = {
        "expected": bool(declared),
        "declared_count": len(declared),
        "external_count": len(deps),
        "internal_count": len(internal),
        "internal_checks": internal_checks,
        "executed": True,
        "dependency_score": score,
        "dependency_skipped": False,
        "passed": passed,
        "failed": failed,
        "structural_veto": structural_fail,
        "score": score,
        "dimensions": dims,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    # R23：extract 提取到外部依赖却未被探测，会让报告误写「本次未声明外部依赖」——
    # 真相是「提取到了但没进 manifest」，属静默错误（win 实证：extract 8 项 → probe 0 项）。
    # 故此处显式比对，不一致即告警，绝不静默归零。
    _extract_count = None
    try:
        _ext_path = Path(args.output).parent / "dependency_extract.json"
        if _ext_path.is_file():
            _extract_count = len(
                json.loads(_ext_path.read_text(encoding="utf-8")).get("deps") or []
            )
    except (OSError, ValueError):
        _extract_count = None
    out["extract_external_count"] = _extract_count
    out["consistent_with_extract"] = (
        None if _extract_count is None else (_extract_count == len(deps))
    )
    if _extract_count and not deps:
        print(
            f"[dep_probe] ⚠ 不一致：依赖提取到 {_extract_count} 项外部依赖，"
            f"但 manifest external_deps 为 0 项 → 本次未做任何外部探测，"
            f"报告会误显示「未声明外部依赖」。请检查 extract_deps 的 --write-manifest 是否生效。",
            file=sys.stderr,
        )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[dep_probe] 外部依赖 {len(deps)} 项（通过 {passed}，失败 {failed}，结构性否决={structural_fail}）→ {args.output}"
          + (f"；随包完整性 {len(internal)} 项，异常 {_int_fail} 项（仅提示、不否决、不计入评分）"
             if internal else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
