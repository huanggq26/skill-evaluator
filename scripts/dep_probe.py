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
                      message="manifest 未给出 target/url，无法探测")
        result["retry"] = "补 manifest external_deps.target"
        return result
    url = _probe_url_for(dep)
    result["probe_url"] = url
    if urllib is None:
        result.update(status="error", category="env_issue",
                      message="运行环境缺少 urllib，无法发起探测")
        return result
    try:
        req = urllib.request.Request(url, method="GET",
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
            # 模板化端点（含 {）或仅到版本基路径（如 /api/v1）——缺少具体实例/动作，
            # 404 属于「manifest 目标不够具体」，归 config_defect（不否决），提示补具体示例。
            _templated = "{" in (dep.get("target") or "")
            _u = urlparse(url)
            _base_only = _u.path.rstrip("/") in ("", "/api", "/api/v1", "/v1")
            if _templated or _base_only:
                result.update(status="skip", category="config_defect", score=None,
                              message=f"HTTP {code}（模板化/基路径端点，需具体实例才能探测，非技能缺陷）")
                result["retry"] = "在 manifest 为该依赖提供可探测的具体示例端点"
            else:
                # 4xx 多为结构性契约问题（端点不存在/权限），标记 contract_defect 以便否决路径
                result.update(status="fail", category="contract_defect", score=0,
                              message=f"依赖返回客户端错误 HTTP {code}，疑似端点/权限契约缺陷")
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
            if _templated or _base_only:
                result.update(status="skip", category="config_defect", score=None,
                              message=f"HTTP {code}（模板化/基路径端点，需具体实例才能探测，非技能缺陷）")
                result["retry"] = "在 manifest 为该依赖提供可探测的具体示例端点"
            else:
                result.update(status="fail", category="contract_defect", score=0,
                              message=f"依赖返回客户端错误 HTTP {code}，疑似端点/权限契约缺陷")
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
    dims = [_probe_one(d) for d in deps]
    _skill_dir = str(manifest.get("skill_source") or "")
    dims += [_probe_internal_one(r, _skill_dir) for r in internal]
    passed = sum(1 for d in dims if d.get("status") == "pass")
    failed = sum(1 for d in dims if d.get("status") == "fail")
    # 结构性否决：存在 contract_defect（外部端点契约缺陷）或 internal_missing（随包缺失）且失败
    structural_fail = any(d.get("category") in ("contract_defect", "internal_missing")
                          and d.get("status") == "fail" for d in dims)
    declared = deps + internal
    score = 100 if (dims and failed == 0) else (0 if structural_fail else (50 if dims else None))

    out = {
        "expected": bool(declared),
        "declared_count": len(declared),
        "external_count": len(deps),
        "internal_count": len(internal),
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
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[dep_probe] 已探测 {len(dims)} 项依赖（外部 {len(deps)} / 内部 {len(internal)}）→ {args.output} "
          f"(通过 {passed}，失败 {failed}，结构性否决={structural_fail})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
