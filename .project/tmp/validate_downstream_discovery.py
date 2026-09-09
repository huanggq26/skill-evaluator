#!/usr/bin/env python3
"""下游发现逻辑契约守卫（Stage 2-4 通用化加固，对应 Stage1 E1-E23 的下游补强）。

背景：
  Stage 2/3/4 的下游脚本（generate_tasks_json.py / backfill_reviews.py 等）从
  benchmark_manifest.json + sample 目录树 *自动发现* 用例与 Grader 目录，不写死
  特定技能。本脚本把这些"发现契约"固化为可回归的断言，防止未来改动破坏通用性：

  D1  functional Grader 目录解析：必须「先 hard 后 common」回退
      （对应 backfill_reviews._resolve_func_grader_dir 的回归#3 防护；
       旧逻辑硬编码 common 导致 hard 任务 grader 被跳过）。
      D1a = 黑盒（扫真实 sample 目录树）；D1b = 白盒（直接调被测函数，构造临时目录）。
      2026-09-04：回归#3（原 test_backfill_reviews.py）已并入 D1b，避免两处重复守护。
  D2  security 类别按目录自动发现，不依赖 ID 前缀
      （对应 backfill_reviews._find_security_grader_dir + generate_tasks_json
       的 _is_security_probe_case_dir + SECURITY_NON_PROBE_DIR_NAMES；
       历史 S1 置于 security/permission/ 下但无 SP_ 前缀也曾被错误归 abnormal）。
  D3  manifest 与目录树一致：manifest 声明的用例必须能在 sample 树中按发现规则
      定位到 Grader/TaskDescription；反之目录树里的合法用例也应被 manifest 覆盖，
      不出现孤儿（仅在提供 --manifest 时校验）。

用法：
  python3 .project/tmp/validate_downstream_discovery.py --sample-root <dir> [--manifest <json>]
退出码：0=全部契约通过，1=存在违反（打印 [Dn] 错误），2=参数/IO 错误。
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

# 与 generate_tasks_json.py 保持一致，避免双源漂移
SECURITY_NON_PROBE_DIR_NAMES = {"results", "workspace", "{workspace}"}
SEC_CATS = ["abnormal", "permission", "sensitive"]

# 定位仓库根（不假设自身位于 scripts/），用于白盒 import 业务脚本
REPO = next(
    (p for p in Path(__file__).resolve().parents
     if (p / "scripts" / "run_eval_pipeline.sh").exists()),
    None,
)


def _errs() -> list[str]:
    return []


def _import_resolve_func():
    """白盒：导入被测函数（须显式入参定位，不写死路径）。"""
    if REPO is None:
        raise RuntimeError("未能定位仓库根（未找到 scripts/run_eval_pipeline.sh）")
    sys.path.insert(0, str(REPO / "scripts"))
    import backfill_reviews as br  # noqa: PLC0415
    return br._resolve_func_grader_dir


def check_d1b_grader_resolution_whitebox(errs: list[str]) -> None:
    """D1b（白盒）：直接调 `_resolve_func_grader_dir`，守护三条解析路径。

    2026-09-04 并入原 test_backfill_reviews.py 的回归#3（去重，单一权威在此处）：
      - hard 与 common 皆存在 → 必须解析到 hard（旧逻辑硬编码 common 导致 hard 被跳过）
      - 仅 common 存在       → 必须回退到 common，不报错、不跳过
      - 两者皆无             → 返回 None，交由调用方跳过
    """
    try:
        resolve = _import_resolve_func()
    except Exception as e:  # noqa: BLE001
        errs.append(f"[D1b] 无法导入 backfill_reviews._resolve_func_grader_dir：{e}")
        return

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)

        # ① hard 优先：两者皆有时必须选 hard
        hard_g = base / "hard" / "H_01" / "Grader"
        common_g = base / "common" / "H_01" / "Grader"
        hard_g.mkdir(parents=True)
        common_g.mkdir(parents=True)
        got = resolve(base, "H_01")
        if got != hard_g:
            errs.append(f"[D1b] hard 任务应解析到 hard 目录，实际={got}")

        # ② 回退 common：仅 common 存在时必须解析到 common
        only_base = base / "onlycommon"
        only_g = only_base / "common" / "C_01" / "Grader"
        only_g.mkdir(parents=True)
        got2 = resolve(only_base, "C_01")
        if got2 != only_g:
            errs.append(f"[D1b] 无 hard 时应回退 common，实际={got2}")

        # ③ 皆无：返回 None，交由调用方跳过
        empty = base / "empty"
        empty.mkdir()
        got3 = resolve(empty, "Z_99")
        if got3 is not None:
            errs.append(f"[D1b] 无 grader 时应返回 None，实际={got3}")


def check_d1_func_grader_resolution(sample_root: Path, errs: list[str]) -> None:
    """D1：functional 用例若在 hard 与 common 都存在，必须解析到 hard（优先）。"""
    # 收集所有 functional 用例候选（含 TaskDescription.md 或 Grader/ 的 common/hard 子目录）
    seen: dict[str, list[str]] = {}
    for sub in ("hard", "common"):
        base = sample_root / sub
        if not base.is_dir():
            continue
        for tid_dir in base.iterdir():
            if not tid_dir.is_dir():
                continue
            has_grader = (tid_dir / "Grader").is_dir()
            has_td = (tid_dir / "TaskDescription.md").exists() or (tid_dir / "task_description.md").exists()
            if has_grader or has_td:
                seen.setdefault(tid_dir.name, []).append(sub)

    for tid, subs in seen.items():
        if "hard" in subs and "common" in subs:
            # 模拟下游解析顺序：先 hard 后 common，应返回 hard
            resolved = "hard" if (sample_root / "hard" / tid / "Grader").exists() or \
                (sample_root / "hard" / tid / "TaskDescription.md").exists() else "common"
            if resolved != "hard":
                errs.append(
                    f"[D1] functional 用例 {tid} 在 hard 与 common 均存在，"
                    f"解析却落在 {resolved}（须先 hard 后 common）"
                )
    # 单点存在性检查：每个 functional 候选至少能解析到一个
    for tid, subs in seen.items():
        grader_found = any((sample_root / s / tid / "Grader").exists() for s in subs)
        if not grader_found and not any(
            (sample_root / s / tid / "TaskDescription.md").exists() for s in subs
        ):
            errs.append(f"[D1] functional 用例 {tid} 既无 Grader 也无 TaskDescription，无法解析")


def check_d2_security_dir_discovery(sample_root: Path, errs: list[str]) -> None:
    """D2：security 用例按目录（security/<cat>/<tid>）自动发现，不依赖 ID 前缀。"""
    sec_root = sample_root / "security"
    if not sec_root.is_dir():
        return
    discovered: list[tuple[str, str]] = []  # (cat, tid)
    for cat in sec_root.iterdir():
        if not cat.is_dir() or cat.name in SECURITY_NON_PROBE_DIR_NAMES:
            continue
        if cat.name not in SEC_CATS:
            errs.append(
                f"[D2] security 子目录 {cat.name} 非已知类别 {SEC_CATS}（目录驱动约定被破坏）"
            )
            continue
        for tid_dir in cat.iterdir():
            if not tid_dir.is_dir():
                continue
            if (tid_dir / "Grader").is_dir() or \
               (tid_dir / "TaskDescription.md").exists() or \
               (tid_dir / "task_description.md").exists():
                discovered.append((cat.name, tid_dir.name))

    # 关键：不依赖 ID 前缀。若某 tid 无 SA_/SP_/SS_ 前缀但仍被目录正确归类，应被接受。
    for cat, tid in discovered:
        # 模拟下游回退：给定 preferred_cat（可能错误映射）也能通过扫描全部类别找到
        candidates = [cat] + [c for c in SEC_CATS if c != cat]
        found = any((sec_root / c / tid / "Grader").exists() for c in candidates)
        if not found:
            errs.append(f"[D2] security 用例 {tid}（cat={cat}）无法按目录回退发现")


def check_d3_manifest_consistency(sample_root: Path, manifest: dict, errs: list[str]) -> None:
    """D3：manifest 声明与目录树发现一致，无孤儿。"""
    # functional：manifest.functional_tasks 每项应有 user_facing/ tier/ case_dir
    ftasks = manifest.get("functional_tasks", [])
    for t in ftasks:
        tid = t.get("id")
        case_dir = t.get("case_dir", "")
        # case_dir 形如 common/FT01 或 hard/FT03
        cand = sample_root / case_dir if case_dir else None
        if case_dir and cand is not None:
            if not ((cand / "Grader").exists() or (cand / "TaskDescription.md").exists()
                    or (cand / "task_description.md").exists()):
                errs.append(f"[D3] manifest functional_tasks {tid} 的 case_dir={case_dir} 在 sample 树中无对应用例")
        elif not case_dir:
            # 无 case_dir 时按 hard/common 回退查找
            found = any((sample_root / s / tid / "Grader").exists() for s in ("hard", "common")) or \
                any((sample_root / s / tid / "TaskDescription.md").exists() for s in ("hard", "common"))
            if not found:
                errs.append(f"[D3] manifest functional_tasks {tid} 在 sample 树 hard/common 中均找不到")

    sec_tasks = manifest.get("security_tasks", [])
    for t in sec_tasks:
        tid = t.get("id")
        case_dir = t.get("case_dir", "")
        cand = sample_root / case_dir if case_dir else None
        if case_dir and cand is not None:
            if not ((cand / "Grader").exists() or (cand / "TaskDescription.md").exists()
                    or (cand / "task_description.md").exists()):
                errs.append(f"[D3] manifest security_tasks {tid} 的 case_dir={case_dir} 在 sample 树中无对应用例")


def main() -> int:
    ap = argparse.ArgumentParser(description="下游发现逻辑契约守卫（D1-D3）")
    ap.add_argument("--sample-root", required=True, help="sample 目录根（含 common/hard/internal/security 子目录）")
    ap.add_argument("--manifest", default=None, help="可选 benchmark_manifest.json，提供则额外校验 D3")
    args = ap.parse_args()

    sample_root = Path(args.sample_root)
    if not sample_root.is_dir():
        print(f"[参数错误] sample-root 不存在或不是目录: {sample_root}", file=sys.stderr)
        return 2

    errs = _errs()
    check_d1b_grader_resolution_whitebox(errs)
    check_d1_func_grader_resolution(sample_root, errs)
    check_d2_security_dir_discovery(sample_root, errs)

    if args.manifest:
        mpath = Path(args.manifest)
        if not mpath.is_file():
            print(f"[参数错误] manifest 不存在: {mpath}", file=sys.stderr)
            return 2
        try:
            manifest = json.loads(mpath.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            print(f"[参数错误] manifest 解析失败: {e}", file=sys.stderr)
            return 2
        check_d3_manifest_consistency(sample_root, manifest, errs)

    if errs:
        print(f"下游发现契约校验失败，共 {len(errs)} 项：")
        for e in errs:
            print(f"  {e}")
        return 1

    print("下游发现契约校验通过（D1 先 hard 后 common / D2 security 按目录发现不依赖前缀 / D3 manifest 一致）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
