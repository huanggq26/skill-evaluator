#!/usr/bin/env python3
"""回归测试（治理态·开发态专用）：守护 backfill_reviews 的 2 项静默失败风险。

运行：python3 .project/tmp/test_backfill_reviews.py
不依赖 pytest，失败时以非零退出码结束。

  回归#1  run_grader 必须显式双传 --task-root / --result-root
          （旧实现单位置参数导致所有 grader 被「静默跳过」，不报错、结果错，
            是本项目最危险的一类失败；无其它脚本覆盖，故本文件保留）
  回归#2  Python 3.9 下模块导入不得因 Path | None 联合注解崩溃
          （须保留 from __future__ import annotations；项目最低版本 3.8+）

回归#3（hard 优先于 common）已于 2026-09-04 并入
.project/tmp/validate_downstream_discovery.py 的 D1b，避免两处重复守护。
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

# 让脚本层可被导入
_REPO = next(p for p in Path(__file__).resolve().parents
             if (p / "scripts" / "run_eval_pipeline.sh").exists())
_SCRIPTS = _REPO / "scripts"
sys.path.insert(0, str(_SCRIPTS))

import backfill_reviews as br


def _fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def test_import_no_pep604_crash():
    """回归#2：Python 3.9 下模块导入不得因 Path | None 注解崩溃。

    之前缺 ``from __future__ import annotations``，函数定义时 PEP 604 联合注解
    (``Path | None``) 直接抛 TypeError。此处导入成功即为证明；再确认带联合注解的
    函数可被访问、其注解可正常 eval。
    """
    if not hasattr(br, "run_grader"):
        _fail("run_grader 未导出")
    if not hasattr(br, "_resolve_func_grader_dir"):
        _fail("_resolve_func_grader_dir 未导出")
    # 含联合返回注解的函数可正常解析（有 __future__ 时为字符串，无则原生对象）
    ann = br._resolve_func_grader_dir.__annotations__.get("return")
    if ann is None:
        _fail("_resolve_func_grader_dir 缺返回注解")
    print("  [ok] 回归#2 模块导入 + 联合注解未崩溃")


def test_run_grader_passes_dual_params():
    """回归#1：run_grader 必须显式传 --task-root / --result-root 双参数。

    旧实现 ``python3 run.py <result_dir>``（单位置），而 run.py 要求双必填参数
    且两树无法反推，导致所有 grader 被静默跳过。
    """
    captured = {}

    def fake_run(*args, **kwargs):
        captured["cmd"] = list(args[0])
        captured["cwd"] = kwargs.get("cwd")

        class _R:
            stdout = json.dumps(
                {"status": "pass", "passed": 10, "total": 10, "must_pass_satisfied": True}
            )
            stderr = ""
            returncode = 0

        return _R()

    grader_dir = Path("/x/sample/hard/H_01/Grader")
    result_dir = Path("/x/spec/results/security/probes/H_01/results")
    with mock.patch.object(subprocess, "run", fake_run):
        out = br.run_grader(grader_dir, result_dir)

    cmd = captured["cmd"]
    if str(grader_dir / "run.py") not in cmd:
        _fail("命令未包含 grader 的 run.py")
    run_idx = cmd.index(str(grader_dir / "run.py"))
    # run.py 之后的第一个参数必须是 --task-root（不再是单位置 result_dir）
    if cmd[run_idx + 1] != "--task-root":
        _fail("run.py 后应紧跟 --task-root，旧单位置契约未修复")
    if "--task-root" not in cmd or "--result-root" not in cmd:
        _fail("缺少 --task-root / --result-root 双参数")
    if str(grader_dir.parent) not in cmd:
        _fail("--task-root 应传 Grader 的父目录（探针/任务根）")
    if str(result_dir) not in cmd:
        _fail("--result-root 应传结果目录")
    if captured["cwd"] != str(grader_dir):
        _fail("cwd 应为 grader 目录")
    if out.get("status") != "pass":
        _fail("grader 输出未正确解析")
    print("  [ok] 回归#1 run_grader 显式双传 --task-root/--result-root")


if __name__ == "__main__":
    print("运行 backfill_reviews 回归测试 ...")
    test_import_no_pep604_crash()
    test_run_grader_passes_dual_params()
    print("\nALL REGRESSION TESTS PASSED")
