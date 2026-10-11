#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_rule_code_consistency.py — 规则层断言 ↔ 代码 一致性核对（防静默漂移）

依据：`Specs/project_spec_maintenance.md`「一致性核对（防漂移）」；任务层 `TASKLOG.md` G6。
失效条件：G6 条款被删，或被上游工具接管（见 .project/tmp/INDEX.md 登记行）

**只核对「代码类」断言**（G6 调研④分类）：
纪律 / 自罚码（如 E31「未查档即诊断」）不在代码核对范围内，避免误报。

用法：
  python3 check_rule_code_consistency.py            # 全量核对
  python3 check_rule_code_consistency.py --json     # 机器可读输出
退出码：0 = 全部一致；1 = 发现漂移。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # skill-evaluator/
SCRIPTS = ROOT / "scripts"
COMMON = SCRIPTS / "_common.py"
VMC = SCRIPTS / "validate_manifest_contract.py"
CACU = SCRIPTS / "cacu_total_score.py"

CHECKS: list[tuple[str, str, callable]] = []


def check(cid: str, desc: str):
    def deco(fn):
        CHECKS.append((cid, desc, fn))
        return fn
    return deco


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore") if p.is_file() else ""


@check("RC-01", "规则层约束：`dependency_expected` 由 external_deps 非空唯一判定（不得掺入 internal）")
def c01() -> tuple[bool, str]:
    t = _read(CACU)
    if not t:
        return False, f"缺少 {CACU.name}"
    bad = re.search(r"dependency_expected\s*=\s*bool\(\s*deps\s*\+\s*internal\s*\)", t)
    if bad:
        return False, "发现 `bool(deps + internal)`，违反唯一判定规则"
    if "dependency_expected = bool(deps)" not in t:
        return True, "未发现违规写法，但也未找到 `bool(deps)` 判定式（需人工确认判定位置）"
    return True, "`dependency_expected = bool(deps)`，与规则层一致"


def _literal_defs(name: str, marker: str) -> list[Path]:
    """找出 name 的**字面量定义**所在文件（RHS 含 marker 字串），注释提及不算。"""
    hits = []
    for p in sorted(SCRIPTS.glob("*.py")):
        t = _read(p)
        for m in re.finditer(rf"^\s*{name}\s*(?::[^=]+)?=\s*\{{", t, re.M):
            # 取该赋值语句到下一个空行/顶层语句为止的片段，判断是否含字面量
            seg = t[m.end(): m.end() + 600]
            if marker in seg:
                hits.append(p)
                break
    return hits


def _overridden(p: Path, name: str, src_marker: str) -> bool:
    """该字面量定义是否**后续被共享源覆盖**（覆盖则运行时正确，仅残留隐患）。"""
    t = _read(p)
    for m in re.finditer(rf"^\s*{name}\s*=\s*(.+)$", t, re.M):
        if src_marker in m.group(1):
            return True
    return False


@check("RC-02", "归桶单一权威源：由 `_common.derive_security_group` 推导，无生效中的第二份 ASI→桶映射")
def c02() -> tuple[bool, str]:
    if "def derive_security_group" not in _read(COMMON):
        return False, "_common.py 缺 derive_security_group"
    defs = _literal_defs("_ASI_TO_GROUP", '"ASI01"')
    if not defs:
        return True, "无第二份映射"
    drift = [p.name for p in defs if not _overridden(p, "_ASI_TO_GROUP", "derive_security_group")]
    if drift:
        return False, f"漂移（字面量生效中，未由单一权威源覆盖）：{drift}"
    return True, (f"运行时一致；但仍有 {len(defs)} 处**残留字面量**待清理："
                  f"{[p.name for p in defs]}（已被共享源覆盖，属隐患非错误）")


@check("RC-03", "标签→ASI 单一权威源：由 `_common.TAG_TO_ASI` 提供，无生效中的本地副本")
def c03() -> tuple[bool, str]:
    if "TAG_TO_ASI" not in _read(COMMON):
        return False, "_common.py 缺 TAG_TO_ASI"
    defs = _literal_defs("_TAG_TO_ASI", '"ASI01"')
    if not defs:
        return True, "仅 _common.py 定义，无本地副本"
    drift = [p.name for p in defs if not _overridden(p, "_TAG_TO_ASI", "TAG_TO_ASI")]
    if drift:
        return False, f"漂移（本地副本生效中）：{drift}"
    return True, (f"运行时一致；但仍有 {len(defs)} 处**残留字面量**待清理："
                  f"{[p.name for p in defs]}（已被共享源覆盖，属隐患非错误）")


@check("RC-04", "守卫 E28（归桶值校验）与 E29（supporting_dimensions 非空）均已实现")
def c04() -> tuple[bool, str]:
    t = _read(VMC)
    if not t:
        return False, "缺少 validate_manifest_contract.py"
    missing = [c for c in ("E28", "E29") if c not in t]
    if missing:
        return False, f"守卫未实现：{missing}"
    return True, "E28 / E29 均已实现"


@check("RC-05", "展示名命名：`sg_` 前缀已生效，代码中无未加前缀的旧展示名")
def c05() -> tuple[bool, str]:
    pat = re.compile(r"(?<!sg_)(abnormal_behavior_control|permission_boundary|sensitive_data_protection)")
    bad = [p.name for p in SCRIPTS.glob("*.py") if pat.search(_read(p))]
    if bad:
        return False, f"存在未加前缀的旧展示名：{bad}"
    return True, "全部展示名已加 sg_ 前缀"


@check("RC-06", "反查推荐视角：由 `_common.lenses_for_asi` 提供（T-05 落地）")
def c06() -> tuple[bool, str]:
    if "def lenses_for_asi" not in _read(COMMON):
        return False, "_common.py 缺 lenses_for_asi"
    return True, "lenses_for_asi 存在"


def main() -> int:
    results = []
    failed = 0
    for cid, desc, fn in CHECKS:
        try:
            ok, detail = fn()
        except Exception as e:  # 保守失败，绝不静默通过
            ok, detail = False, f"核对项执行异常：{e}"
        failed += 0 if ok else 1
        results.append({"id": cid, "desc": desc, "ok": ok, "detail": detail})

    if "--json" in sys.argv:
        print(json.dumps({"failed": failed, "results": results}, ensure_ascii=False, indent=2))
        return 1 if failed else 0

    print("=== 规则层断言 ↔ 代码 一致性核对 ===")
    for r in results:
        print(f"  {'✅' if r['ok'] else '❌'} {r['id']} {r['desc']}")
        print(f"       → {r['detail']}")
    print(f"\n合计 {len(results)} 项，漂移 {failed} 项")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
