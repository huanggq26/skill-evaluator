#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""govkit.py — 治理写盘脚手架（派生脚本 · 条款失效即删）

依据：`Specs/project_spec_maintenance.md`
  · 「写盘通道与回退」「整文件重写的守卫（S1–S6）」「治理脚本（派生 · 有终期）」
失效条件：上述条款被删，或被上游工具接管（见 .project/tmp/INDEX.md 登记行）

子命令
------
  backup <file> [--why 说明]              编辑前备份（登记到 backup/INDEX.md）
  set <file> --pairs <json文件>           受检替换：断言命中 + 体积守卫 + 原子写 + 操作日志
  verify <file> [--anchor 关键字 ...]     写入前后校验：行数 / 非空行 / 关键锚点
  log --target <file> --action ...        追加操作日志（OPERATION_LOG.md）

pairs JSON 格式： [{"old": "...", "new": "..."}, ...]

设计约束（缺一即中止）
----------------------
  S1 每个替换断言命中（未命中立即退出，绝不静默跳过）
  S2 写入前置守卫：非空行或体积低于原文件 90% 即中止
  S3 原子写：临时文件 → 校验 → os.replace
  S4 写前自动备份
  S5 不使用循环残留变量（本脚本无整文件重写循环）
  S6 校验：写入后可选 --check 命令（如 python -m py_compile）
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

GOV = Path.home() / ".codebuddy/skills/skill-evaluator/.project"
BACKUP_DIR = GOV / "backup"
LOG = GOV / "OPERATION_LOG.md"
GUARD_RATIO = 0.9


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _stamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def _append_log(target: str, action: str, result: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    head = "# 治理操作日志（可据此回滚历史操作）\n\n" if not LOG.exists() else ""
    with LOG.open("a", encoding="utf-8") as f:
        if head:
            f.write(head)
        f.write(f"- `{_now()}` | `{target}` | {action} | {result}\n")


def cmd_backup(args) -> int:
    src = Path(args.file).expanduser()
    if not src.is_file():
        print(f"❌ 不存在：{src}", file=sys.stderr)
        return 1
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    dst = BACKUP_DIR / f"{src.stem}-pre-{args.tag}-{_stamp()}{src.suffix}"
    shutil.copy2(src, dst)
    idx = BACKUP_DIR / "INDEX.md"
    with idx.open("a", encoding="utf-8") as f:
        if not idx.exists() or idx.stat().st_size == 0:
            f.write("| 文件 | 备份时间 | 为哪个改动备份 | 预定删除条件 | 状态 |\n|---|---|---|---|---|\n")
        f.write(f"| `{dst.name}` | {_now()} | {args.why or args.tag} | 对应改动验证通过后 | 在用 |\n")
    _append_log(str(src), f"backup({args.tag})", f"→ {dst.name}")
    print(f"✅ 备份：{dst}")
    return 0


def cmd_set(args) -> int:
    src = Path(args.file).expanduser()
    if not src.is_file():
        print(f"❌ 不存在：{src}", file=sys.stderr)
        return 1
    pairs = json.loads(Path(args.pairs).read_text(encoding="utf-8"))
    orig = src.read_text(encoding="utf-8")
    orig_ne = sum(1 for l in orig.split("\n") if l.strip())

    # S4 写前备份
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    bak = BACKUP_DIR / f"{src.stem}-pre-set-{_stamp()}{src.suffix}"
    shutil.copy2(src, bak)

    # S1 断言命中
    content = orig
    for i, p in enumerate(pairs):
        old, new = p["old"], p.get("new", "")
        if old not in content:
            _append_log(str(src), "set", f"❌ 中止：第 {i+1} 处未命中")
            raise SystemExit(f"❌ 中止（S1）：第 {i+1} 处替换未命中 → {old[:60]!r}")
        content = content.replace(old, new, p.get("count", 1))

    # S2 写入前置守卫
    ne = sum(1 for l in content.split("\n") if l.strip())
    if ne < orig_ne * GUARD_RATIO or len(content) < len(orig) * GUARD_RATIO:
        _append_log(str(src), "set", f"❌ 守卫中止：非空行 {orig_ne}→{ne}")
        raise SystemExit(f"❌ 中止（S2）：非空行 {orig_ne} → {ne}，体积 {len(orig)} → {len(content)}，疑似破坏性写入")

    # S3 原子写
    tmp = src.with_suffix(src.suffix + ".govkit-tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, src)
    msg = f"✅ 非空行 {orig_ne} → {ne}，体积 {len(orig)} → {len(content)}；备份 {bak.name}"
    print(msg)

    # S6 可选校验命令
    if args.check:
        r = subprocess.run(args.check, shell=True, capture_output=True, text=True)
        if r.returncode != 0:
            _append_log(str(src), "set", f"⚠ 写入成功但校验失败：{args.check}")
            print(f"⚠ 校验未通过：{args.check}\n{r.stderr[:400]}", file=sys.stderr)
            return 2
        print(f"✅ 校验通过：{args.check}")

    _append_log(str(src), f"set({len(pairs)} 处)", msg)
    return 0


def cmd_verify(args) -> int:
    src = Path(args.file).expanduser()
    if not src.is_file():
        print(f"❌ 不存在：{src}", file=sys.stderr)
        return 1
    t = src.read_text(encoding="utf-8")
    lines = t.split("\n")
    ne = sum(1 for l in lines if l.strip())
    print(f"文件：{src}")
    print(f"  行数 {len(lines)} | 非空行 {ne} | 体积 {len(t)}")
    miss = [a for a in (args.anchor or []) if a not in t]
    for a in args.anchor or []:
        print(f"  锚点 {'✅' if a not in miss else '❌ 缺失'}：{a}")
    return 1 if miss else 0


def cmd_log(args) -> int:
    _append_log(args.target, args.action, args.result)
    print("✅ 已追加操作日志")
    return 0


CHANGE_TPL = """# {title}

## Why

<!-- 一句话：现状问题 + 实测证据（文件:行号 或 实测值）。不得写概括性描述 -->

## 任务类别判定

- 判据：是否改变对外可观察行为 → {behavior}
- 分流：{flow}

## What Changes

<!-- 逐条列出：改动前 → 改动后 -->

## 验收（改后自验证）

- [ ] 一键回归入口：{regress}
- [ ] 关键锚点仍存在（govkit verify）
- [ ] 产物/评分无意外变化（附实测对照值）
"""

TASKS_TPL = """## 1. 已实施

（无——本变更为立项阶段，尚未启动实施）

## 2. 待实施

- [ ] **#1** <!-- 任务描述 -->
      - 锚点：<!-- 文件:行号 -->
      - 验收：<!-- 可判定标准 -->

## 3. 待观察（依赖真实运行）

- [ ] <!-- 回归观察项 -->

## 4. 归档前自检

- [ ] proposal 的 Why 含实测证据
- [ ] 每条待实施项含锚点与验收
- [ ] 已跑回归且退出码 0
"""

TASK_BLOCK_TPL = """## [{status}] {tid}. {title}

**登记**：{date} ｜ **状态**：{state}

**目标**：<!-- 一句话 -->

**锚点**：<!-- 文件:行号 -->

**步骤**：

- [ ] <!-- 步骤 1 -->

**验收**：<!-- 可判定标准 -->

---
"""


def _slug(s: str) -> str:
    import re as _re
    s = _re.sub(r"[^\w\u4e00-\u9fff]+", "-", s.strip()).strip("-").lower()
    return s or "untitled"


def cmd_scaffold(args) -> int:
    """生成治理骨架：openspec change 或 TASKLOG 任务块（避免手工创建漏字段）。"""
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    if args.kind == "change":
        name = f"{today}-{_slug(args.name)}"
        root = Path(args.out).expanduser() / name
        if root.exists() and not args.force:
            print(f"❌ 已存在：{root}（如需覆盖加 --force）", file=sys.stderr)
            return 1
        root.mkdir(parents=True, exist_ok=True)
        (root / "proposal.md").write_text(
            CHANGE_TPL.format(title=args.name,
                              behavior=args.behavior,
                              flow="**行为变更** → 由规范区变更承载任务态，不登记 TASKLOG（避免双写）"
                                   if args.behavior == "是"
                                   else "**治理改造** → 不改变对外行为，登记 TASKLOG 任务层",
                              regress=args.regress or "<!-- 一键回归命令 -->"),
            encoding="utf-8")
        (root / "tasks.md").write_text(TASKS_TPL, encoding="utf-8")
        print(f"✅ 已生成 change 骨架：{root}")
        print("   proposal.md（Why/任务类别判定/What Changes/验收）")
        print("   tasks.md（已实施/待实施/待观察/归档前自检）")
        return 0

    # kind == task
    block = TASK_BLOCK_TPL.format(status=args.status, tid=args.id, title=args.title,
                                  date=today, state=args.state)
    if args.out:
        p = Path(args.out).expanduser()
        with p.open("a", encoding="utf-8") as f:
            f.write("\n" + block)
        print(f"✅ 已追加任务块到：{p}")
    else:
        print(block)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="govkit")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("backup"); b.add_argument("file"); b.add_argument("--tag", default="edit"); b.add_argument("--why"); b.set_defaults(func=cmd_backup)

    s = sub.add_parser("set"); s.add_argument("file"); s.add_argument("--pairs", required=True); s.add_argument("--check"); s.set_defaults(func=cmd_set)

    v = sub.add_parser("verify"); v.add_argument("file"); v.add_argument("--anchor", action="append"); v.set_defaults(func=cmd_verify)

    l = sub.add_parser("log"); l.add_argument("--target", required=True); l.add_argument("--action", required=True); l.add_argument("--result", required=True); l.set_defaults(func=cmd_log)

    sc = sub.add_parser("scaffold", help="生成治理骨架：change 或 TASKLOG 任务块")
    sc.add_argument("kind", choices=["change", "task"])
    sc.add_argument("--name", help="change 名称（kind=change 必填）")
    sc.add_argument("--out", help="输出目录（change）或追加文件（task）")
    sc.add_argument("--behavior", choices=["是", "否"], default="是", help="是否改变对外可观察行为")
    sc.add_argument("--regress", help="一键回归命令")
    sc.add_argument("--force", action="store_true")
    sc.add_argument("--id", help="任务号（kind=task，如 G16）")
    sc.add_argument("--title", help="任务标题（kind=task）")
    sc.add_argument("--status", default="治理·待办", help="任务块状态标记（kind=task）")
    sc.add_argument("--state", default="待实施", help="状态字段值（kind=task）")
    sc.set_defaults(func=cmd_scaffold)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
