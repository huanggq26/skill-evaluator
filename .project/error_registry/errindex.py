#!/usr/bin/env python3
"""errindex — 错误档案检索索引服务

设计原则
--------
1. **md 是权威源（唯一真值），SQLite 是派生索引**，可随时 rebuild 重建。
2. **索引与内容同生命周期**：rebuild 采用「全量清空 + 重扫」，
   md 被删除 / 归档后，其索引项随之消失或标记 archived，
   保证检索出来的路径始终符合实际（无悬空引用）。
3. **检索只回答「去哪读」**，诊断时仍须按 file_path 打开 md 读原文——
   避免把摘要当结论（这正是 E01「证据不全断言」的病根）。

用法
----
    errindex rebuild                      全量重建索引（幂等）
    errindex q --tag E01 --tag E02        组合标签（AND 交集）
    errindex q --tag E01 --any            组合标签（OR 并集）
    errindex q --module exec_functional_tasks            仅模块（函数可选）
    errindex q --module exec_functional_tasks --func exec_one   精确到函数
    errindex q --module X --tag E01       模块 + 标签组合
    errindex q --status active            按状态过滤
    errindex stats                        标签分布，浮现 #系统性
    errindex check                        一致性校验（悬空 / 遗漏）
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "errindex.db"
BY_MODULE = ROOT / "by_module"
ARCHIVE = ROOT / "_archive"

SCHEMA = """
CREATE TABLE IF NOT EXISTS errors (
    id         TEXT PRIMARY KEY,
    stage      TEXT,
    module     TEXT,
    func       TEXT,
    title      TEXT,
    status     TEXT,
    found_date TEXT,
    tags       TEXT,
    premise    TEXT,
    cause      TEXT,
    strategy   TEXT,
    verify     TEXT,
    revise     TEXT,
    file_path  TEXT NOT NULL,
    archived   INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_errors_module ON errors(module);
CREATE INDEX IF NOT EXISTS idx_errors_func   ON errors(func);
CREATE INDEX IF NOT EXISTS idx_errors_status ON errors(status);
CREATE INDEX IF NOT EXISTS idx_errors_arch   ON errors(archived);

CREATE TABLE IF NOT EXISTS error_tags (
    err_id TEXT NOT NULL,
    tag    TEXT NOT NULL,
    PRIMARY KEY (err_id, tag)
);
CREATE INDEX IF NOT EXISTS idx_et_tag ON error_tags(tag);

CREATE TABLE IF NOT EXISTS error_relations (
    from_id TEXT NOT NULL,
    to_id   TEXT NOT NULL,
    rel     TEXT NOT NULL,
    derived INTEGER DEFAULT 0,
    PRIMARY KEY (from_id, to_id, rel)
);
CREATE INDEX IF NOT EXISTS idx_er_from ON error_relations(from_id);
CREATE INDEX IF NOT EXISTS idx_er_to   ON error_relations(to_id);
"""

FIELD_RE = r"^-\s*\*\*{name}\*\*\s*[:：]\s*(.+?)\s*$"

# 关联关系的反向映射：只需在「新记录」声明一侧，另一侧由 rebuild 自动推导，
# 避免双向手工维护导致的漂移。
REL_REVERSE = {
    "caused-by": "caused",
    "caused": "caused-by",
    "supersedes": "superseded-by",
    "superseded-by": "supersedes",
    "root-of": "caused-by",
    "related": "related",
}


def _field(block: str, name: str) -> str:
    m = re.search(FIELD_RE.format(name=re.escape(name)), block, re.M)
    return m.group(1).strip() if m else ""


def _tags(block: str) -> list:
    raw = _field(block, "标签")
    return re.findall(r"`([^`]+)`", raw)


def _rels(block: str) -> list:
    """解析「关联」字段：`ERR-006（caused-by）` → [(to_id, rel)]

    只接受 REL_REVERSE 中已定义的关系类型——否则散文式提及
    （如「根因见 ERR-005（取证流程缺陷）」）会被误判为关联声明。
    """
    raw = _field(block, "关联")
    out = []
    for m in re.finditer(r"(ERR-\d+)\s*[（(]([^）)]+)[）)]", raw):
        rel = m.group(2).strip()
        if rel in REL_REVERSE:
            out.append((m.group(1), rel))
    return out


def parse_file(path: Path, archived: bool) -> list:
    """解析一个 md 档案文件，返回记录列表。"""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []

    # 一级标题： "S3 / exec_functional_tasks" 或 "跨阶段公共问题"
    stage, module = "", ""
    m = re.search(r"^#\s+(.+)$", text, re.M)
    if m:
        head = m.group(1).strip()
        if "/" in head:
            stage, module = [x.strip() for x in head.split("/", 1)]
        else:
            module = head

    rel = path.relative_to(ROOT).as_posix()
    records = []
    # 以 ## 切块
    for block in re.split(r"^##\s+", text, flags=re.M)[1:]:
        lines = block.strip().splitlines()
        if not lines:
            continue
        title = lines[0].strip()

        # 函数可选：标题形如 `exec_one() — 描述` 才解析出函数
        func = ""
        fm = re.match(r"^([\w_]+\([^)]*\))\s*[—–-]{1,2}\s*(.+)$", title)
        if fm:
            func, title = fm.group(1).strip(), fm.group(2).strip()

        rid = _field(block, "ID")
        if not rid:
            continue  # 无 ID 的块视为说明文字，不入库

        records.append({
            "id": rid,
            "stage": stage,
            "module": module,
            "func": func,
            "title": title,
            "status": _field(block, "状态") or "active",
            "found_date": _field(block, "发现"),
            "tags": _tags(block),
            "premise": _field(block, "前提/依赖"),
            "cause": _field(block, "归因"),
            "strategy": _field(block, "修改策略"),
            "verify": _field(block, "验证方式"),
            "revise": _field(block, "修订"),
            "rels": _rels(block),
            "file_path": rel,
            "archived": 1 if archived else 0,
        })
    return records


def scan_sources() -> list:
    """扫描全部权威源：by_module/（在用）+ _archive/（已退出）。"""
    out = []
    for d, archived in ((BY_MODULE, False), (ARCHIVE, True)):
        if not d.exists():
            continue
        for p in sorted(d.rglob("*.md")):
            if p.name.lower() in ("index.md", "readme.md"):
                continue
            out.extend(parse_file(p, archived))
    return out


def cmd_rebuild(args) -> int:
    recs = scan_sources()
    if DB_PATH.exists():
        DB_PATH.unlink()  # 全量重建：旧索引随之消失，保证与内容同生命周期
    con = sqlite3.connect(str(DB_PATH))
    con.executescript(SCHEMA)
    for r in recs:
        con.execute(
            "INSERT OR REPLACE INTO errors "
            "(id,stage,module,func,title,status,found_date,tags,premise,"
            " cause,strategy,verify,revise,file_path,archived) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (r["id"], r["stage"], r["module"], r["func"], r["title"],
             r["status"], r["found_date"], ",".join(r["tags"]), r["premise"],
             r["cause"], r["strategy"], r["verify"], r["revise"],
             r["file_path"], r["archived"]),
        )
        for t in r["tags"]:
            con.execute("INSERT OR REPLACE INTO error_tags VALUES (?,?)",
                        (r["id"], t))
        # 关联：单向声明 + 自动推导反向（避免双向维护漂移）
        for to_id, rel_type in r["rels"]:
            # derived=0：md 中显式声明；derived=1：系统自动推导的反向
            con.execute("INSERT OR REPLACE INTO error_relations VALUES (?,?,?,0)",
                        (r["id"], to_id, rel_type))
            rev = REL_REVERSE.get(rel_type)
            if rev:
                con.execute("INSERT OR REPLACE INTO error_relations VALUES (?,?,?,1)",
                            (to_id, r["id"], rev))
    con.commit()
    con.close()
    n_arch = sum(1 for r in recs if r["archived"])
    print(f"[rebuild] 索引已重建：{len(recs)} 条记录"
          f"（在用 {len(recs) - n_arch} / 已归档 {n_arch}）")
    print(f"[rebuild] 数据库：{DB_PATH}")
    return 0


def _alive(r: dict) -> bool:
    """路径校验：保证检索结果指向真实存在的文件。"""
    return (ROOT / r["file_path"]).exists()


def query(args) -> list:
    if not DB_PATH.exists():
        print("[error] 索引不存在，请先运行：errindex rebuild", file=sys.stderr)
        return []
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    sql = "SELECT * FROM errors WHERE 1=1"
    params: list = []

    if not args.include_archived:
        sql += " AND archived = 0"
    if args.status:
        sql += " AND status = ?"
        params.append(args.status)
    if args.module:
        sql += " AND module LIKE ?"
        params.append(f"%{args.module}%")
    if args.func:
        sql += " AND func LIKE ?"
        params.append(f"%{args.func}%")

    rows = [dict(r) for r in con.execute(sql, params)]

    # 组合标签：AND（交集）或 OR（并集）
    if args.tag:
        ids_and, ids_or = None, set()
        for t in args.tag:
            cur = {r["err_id"] for r in con.execute(
                "SELECT err_id FROM error_tags WHERE tag = ?", (t,))}
            ids_or |= cur
            ids_and = cur if ids_and is None else (ids_and & cur)
        keep = ids_or if args.any else (ids_and or set())
        rows = [r for r in rows if r["id"] in keep]

    if args.meta:
        rows = [r for r in rows
                if args.meta in (r["tags"] or "").split(",")]

    con.close()

    # 生存期校验：过滤悬空引用
    alive = [r for r in rows if _alive(r)]
    dangling = len(rows) - len(alive)
    if dangling:
        print(f"[warn] 已过滤 {dangling} 条悬空记录"
              f"（md 已删除但索引未同步，请运行 rebuild）", file=sys.stderr)
    return alive


def cmd_query(args) -> int:
    rows = query(args)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    if not rows:
        print("（无匹配记录）")
        return 0
    print(f"命中 {len(rows)} 条：\n")
    for r in rows:
        loc = r["module"] or "-"
        if r["func"]:
            loc += f" / {r['func']}"
        tag_s = " ".join(f"`{t}`" for t in (r["tags"] or "").split(",") if t)
        flag = " [已归档]" if r["archived"] else ""
        print(f"  {r['id']}  [{r['status']}]{flag}  {r['title']}")
        print(f"      位置：{loc}   标签：{tag_s}")
        print(f"      档案：{r['file_path']}")
        if args.verbose:
            if r["premise"]:
                print(f"      前提：{r['premise']}")
            if r["cause"]:
                print(f"      归因：{r['cause']}")
            if r["strategy"]:
                print(f"      策略：{r['strategy']}")
        print()
    return 0


def cmd_stats(args) -> int:
    if not DB_PATH.exists():
        print("[error] 请先 rebuild", file=sys.stderr)
        return 1
    con = sqlite3.connect(str(DB_PATH))
    print("════ 标签分布（>=3 模块复现 → #系统性）════\n")
    rows = con.execute(
        "SELECT tag, COUNT(DISTINCT err_id) c FROM error_tags "
        "GROUP BY tag ORDER BY c DESC").fetchall()
    for tag, c in rows:
        mods = con.execute(
            "SELECT DISTINCT e.module FROM errors e "
            "JOIN error_tags t ON e.id = t.err_id WHERE t.tag = ?", (tag,)
        ).fetchall()
        n_mod = len([m for m in mods if m[0]])
        sysflag = "  ← #系统性（流程病，非单点）" if n_mod >= 3 else ""
        print(f"  {tag:<22} {c} 条 / {n_mod} 模块{sysflag}")
    con.close()
    return 0


def cmd_check(args) -> int:
    """一致性校验：悬空（索引有/文件无）与遗漏（文件有/索引无）。"""
    if not DB_PATH.exists():
        print("[error] 请先 rebuild", file=sys.stderr)
        return 1
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    indexed = [dict(r) for r in con.execute("SELECT * FROM errors")]
    con.close()

    dangling = [r for r in indexed if not _alive(r)]
    on_disk = {r["id"] for r in scan_sources()}
    in_db = {r["id"] for r in indexed}
    missing = sorted(on_disk - in_db)   # md 有、索引无
    ghost = sorted(in_db - on_disk)     # 索引有、md 无

    print("════ 索引—内容 一致性 ════")
    print(f"  索引记录数：{len(indexed)}    磁盘记录数：{len(on_disk)}")
    print(f"  悬空引用（路径失效）：{len(dangling)}")
    for r in dangling:
        print(f"      ✗ {r['id']} → {r['file_path']}（文件不存在）")
    print(f"  遗漏（未入库）：{len(missing)}  {missing if missing else ''}")
    print(f"  幽灵（已删未同步）：{len(ghost)}  {ghost if ghost else ''}")
    if not dangling and not missing and not ghost:
        print("\n  ✓ 索引与内容生存期一致")
        return 0
    print("\n  修复：errindex rebuild")
    return 1


_ERRCODE_TPL = '''# 错误类型标签表（唯一权威）

> 标签制：一条错误可贴 1~N 个标签。**新标签须先在此登记再用**。

## 类型标签（必选，1~N 个）

### E0x 认知判断
| 标签 | 名称 | 定义 |
|---|---|---|
| `E01` | 证据不全断言 | 未交叉验证即下结论 |
| `E02` | 归因摇摆 | 同一现象多次改归因，未收敛 |
| `E03` | 前提未校验 | 依赖条件未确认就使用 |

### E1x 工程实现
| 标签 | 名称 | 定义 |
|---|---|---|
| `E11` | 契约/字段解析错 | 凭印象猜结构，未读实际 |
| `E12` | 副作用回归 | 修 A 引出 B |
| `E13` | 边界/异常未处理 | 边界状态被当普通失败处理 |

### E2x 环境与可观测
| 标签 | 名称 | 定义 |
|---|---|---|
| `E21` | 产物新鲜度失效 | 复用旧产物 / 未清工作区 |
| `E22` | 可观测性缺失 | 输出截断 / 无进度播报 |
| `E23` | 环境/依赖差异 | 路径、平台、版本差异 |

### E3x 流程规范
| 标签 | 名称 | 定义 |
|---|---|---|
| `E31` | 未查档即诊断 | 违反本区规范（自罚码） |
| `E32` | 范围低估 | 单路检索，遗漏影响面 |
| `E33` | 静默跳过/失败未停 | 含「约束已写但未激活」 |

## 元标签（可选）

| 标签 | 含义 | 为何重要 |
|---|---|---|
| `#误判史` | 含被推翻的归因 | **最高优先级**：防重蹈同一条错路 |
| `#误报` | 假阳性：把非问题判为问题 | 修误报**最易反向引入漏检** |
| `#待验证` | 结论建立在未验证数据上 | 阻断在此结论上继续推理 |
| `#证伪` | 本记录的**结论或改动策略经证明错误** | 教训密度最高：收录「我以为改对了，其实改错了」 |
| `#系统性` | 同标签跨 >=3 模块复现 | 流程病，须改流程非改单点 |

## 纪律
1. 标签必须来自本表，新标签先登记再用（防同义标签分裂）
2. 至少 1 个类型标签
3. 标签不可替代「前提/依赖」字段：标签答"什么错"，前提答"何时成立"
4. `#误判史` 永不删除
'''

_README_TPL = '''# 错误档案区（error_registry）

> `project_spec_maintenance.md` 治理方案的**补充件**。
> 归属判定（内容归属三问）：E2（会无限递增）= True → **独立成区，不进规则层**。

## 为何存在

LLM 上下文易失，导致两类失效：

| 失效模式 | 本区对策 |
|---|---|
| **遗忘修改史 → 错误轮回** | 强制查档，历史外置持久化 |
| **证据不全就断言** | 强制写「前提/依赖」，前提不成立不得结论 |

**核心：把「我犯过的错」变成可检索资产，不再依赖我这次记不记得。**

## 目录

- `by_module/` 【纵】阶段–模块–函数，答「**哪里**错了」
- `_archive/`   退出区（按时间分卷 `ERRLOG_YYYY-MM.md`）
- `errindex.py` 检索服务（md 权威，`errindex.db` 派生）
- `ERRCODE.md`  标签表（唯一权威）

## md 记录格式（权威源，须严格遵循）

    # <阶段> / <模块>

    ## <函数名>() — 一句话现象

    - **ID**: ERR-001
    - **标签**: `E01` `#误判史`
    - **状态**: active
    - **发现**: YYYY-MM-DD
    - **现象**: 具体表现
    - **前提/依赖**: 该结论成立所依赖的条件
    - **归因**: 根因
    - **修改策略**: 怎么改
    - **验证方式**: 如何确认修好了
    - **关联**: ERR-006（caused-by）
    - **修订**: ERR-013（本策略经证伪）
    - **误判史**:
      - ✗ 曾误判为……（推翻的理由）

**函数可选**：无具体函数时标题直接写现象，不写 `()`。

## 关联与修订（改动溯源）

> 改动之后又出问题：新问题如何挂到旧改动上？旧改动被证伪如何留教训？

**关系类型**（单向声明，反向自动生成）：

| 关系 | 写法 | 含义 | 自动生成反向 |
|---|---|---|---|
| 引发 | `关联: ERR-006（caused-by）` | 本问题由那次改动引入 | ERR-006 显示 `caused` |
| 取代 | `关联: ERR-006（supersedes）` | 本记录取代那次结论 / 策略 | ERR-006 显示 `superseded-by` |
| 根因 | `关联: ERR-005（root-of）` | 本记录是那问题的根因 | ERR-005 显示 `caused-by` |
| 相关 | `关联: ERR-002（related）` | 一般关联 | 双向对称 |

查看关联链：`errindex show <ID>`

**旧改动被证伪时——历史不改写，只追加修订**：

1. **不动**旧记录的「归因」「修改策略」——它记录**当时**的判断，抹掉即失去教训
2. 旧记录补 `修订: ERR-013（本策略经证伪）` + 贴 `#证伪` 标签，状态转 `superseded`
3. 新记录写 `关联: ERR-006（supersedes）`，「归因」说明**旧改动错在哪**

> 改写后只看到"现在正确的版本"，看不到"曾经错在哪"——后者才是防重蹈的关键。
> `#证伪` 可一次检索出所有「我以为改对了、其实改错了」，是全库教训密度最高的集合。

## 读写纪律（强制 · 双向）

### 读：诊断前必查档（阻断式）

    1. errindex q --module <模块> [--func <函数>]     # 纵：定位
    2. 从命中记录提取 tags
    3. errindex q --tag <每个标签>                     # 横：同类跨模块
    4. 按 file_path 打开 md 读原文（含「误判史」）
    5. 逐条核对「前提/依赖」是否仍成立
    assert 已完成 1-5, "未完成查档 → 停止，不得诊断下结论"

效率让位于正确性。违反记 `E31`。

### 写：问题解决时必须同步建档

| 时机 | 写什么 |
|---|---|
| 定位到根因 | 补「归因」「修改策略」「验证方式」 |
| 实施修复后 | 补验证结果，状态转 `fixed` |
| **归因被推翻** | **追加「误判史」一行**（最高价值） |
| 前提失效 | 标记退出并归档 |
| 发现新错误 | 新建记录（新 ID） |

**不写档案 = 任务未完成**，不得标 `DONE`；
写完须 `errindex rebuild` + `check` 通过。

> **读档防重蹈，写档防遗忘**——只做一半等于没做。

## 检索命令

    errindex rebuild                      全量重建（幂等）
    errindex q --module X                 仅模块（函数可选）
    errindex q --module X --func fn       精确到函数
    errindex q --tag E01 --tag E02        组合标签 AND
    errindex q --tag E01 --tag E02 --any  组合标签 OR
    errindex q --meta '#误判史'            元标签
    errindex stats                        标签分布，浮现 #系统性
    errindex check                        一致性校验

## 索引—内容 生存期管理（强制）

**md 是权威源，SQLite 是派生索引，二者生命周期必须一致。**

- `rebuild` 全量重建：md 删除后索引项随之消失
- 查询时校验 `file_path`，悬空记录自动过滤并告警
- `check` 报告悬空 / 遗漏 / 幽灵
- **不单独删索引项**：要删就删 md，再 rebuild

## 退出条件（防无限膨胀）

| 条件 | 判定 | 动作 |
|---|---|---|
| 已修复稳定 | 连续 3 次未复现 | 转 `fixed`，移入 `_archive/ERRLOG_YYYY-MM.md` |
| 前提失效 | 函数删 / 模块重构 / 依赖下线 | 归档留痕 |
| 被更优方案覆盖 | 更根本修复包含它 | 合并后删旧 |
| **误报** | 问题本身不存在 | ⚠️ **压缩成「误判史」一行，不整体删** |
| 超期 | 30 天未复现 | 归档 |

**误判史不删**：它记的不是"系统哪坏了"，而是"**我会怎么想错**"，
删掉它错误轮回必然重演——**这是本区最值钱的资产**。

膨胀控制：归档精简 · 按时间分卷 · 单卷 >400 行细分 · 维护 INDEX。
'''

_INDEX_TPL = '''# 错误档案全量索引

> 一行一条，供快速扫读。检索请用 `errindex q`。
> 维护：新增/变更记录后须同步本表，并执行 `errindex rebuild`。

## 在用（active）

| ID | 状态 | 标签 | 位置 | 一句话 |
|---|---|---|---|---|
| （暂无） | — | — | — | — |

## 已退出

| ID | 归档去向 | 退出原因 |
|---|---|---|
| （暂无） | — | — |
'''

_CROSS_TPL = '''# 跨阶段公共问题

> 不归属单一模块、跨阶段复现的问题。诊断时**必查本文件**。

## （暂无记录）

发现跨阶段问题时，按 README 第三节格式在此追加。
'''

_ARCH_INDEX_TPL = '''# 归档索引（已退出记录）

> `archive/` 只追加不修改；确需更正时追加勘误，不改写原文。
> 退出条件见 `../README.md` 第七节。

## 卷目

| 卷 | 时间范围 | 主题 | 条数 |
|---|---|---|---|
| （暂无） | — | — | 0 |

## 归档纪律

- **归档时精简**：只留 目标 + 结果 + 关键教训，删步骤细节
- **按时间分卷**：`ERRLOG_YYYY-MM.md`（月度）
- **超阈值细分**：单卷 > 400 行 → `-1.md` / `-2.md`
- **误判史不删**：压缩为「误判史」一行保留
'''


def cmd_init(args) -> int:
    """在任意项目初始化错误档案区脚手架（幂等，不覆盖已存在文件）。"""
    BY_MODULE.mkdir(parents=True, exist_ok=True)
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    targets = {
        ROOT / "ERRCODE.md": _ERRCODE_TPL,
        ROOT / "README.md": _README_TPL,
        ROOT / "INDEX.md": _INDEX_TPL,
        BY_MODULE / "_cross_cutting.md": _CROSS_TPL,
        ARCHIVE / "INDEX.md": _ARCH_INDEX_TPL,
    }
    made = []
    for p, content in targets.items():
        if p.exists():
            continue
        p.write_text(content, encoding="utf-8")
        made.append(p.name)
    print(f"[init] 档案区：{ROOT}")
    if made:
        print(f"[init] 已生成：{', '.join(made)}")
    else:
        print("[init] 脚手架已存在，未覆盖任何文件（幂等）")
    print("[init] 下一步：errindex rebuild")
    return 0


def cmd_show(args) -> int:
    """显示一条记录详情及其完整关联链（正向声明 + 反向推导）。"""
    if not DB_PATH.exists():
        print("[error] 请先 rebuild", file=sys.stderr)
        return 1
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM errors WHERE id = ?", (args.id,)).fetchone()
    if not row:
        print(f"（无记录 {args.id}）")
        con.close()
        return 1
    r = dict(row)
    loc = r["module"] or "-"
    if r["func"]:
        loc += f" / {r['func']}"
    print(f"{r['id']}  [{r['status']}]  {r['title']}")
    print(f"  位置：{loc}")
    print(f"  标签：{r['tags']}")
    print(f"  档案：{r['file_path']}")
    for label, key in (("前提", "premise"), ("归因", "cause"),
                       ("策略", "strategy"), ("验证", "verify"),
                       ("修订", "revise")):
        if r.get(key):
            print(f"  {label}：{r[key]}")
    print("\n  关联链：")
    has = False
    # 只展示 md 中显式声明的关系（derived=0），
    # 自动推导的反向关系用于可达性查询，不重复展示
    for rr in con.execute(
            "SELECT to_id, rel FROM error_relations "
            "WHERE from_id=? AND derived=0", (args.id,)):
        print(f"     → {rr['to_id']}  ({rr['rel']})")
        has = True
    for rr in con.execute(
            "SELECT from_id, rel FROM error_relations "
            "WHERE to_id=? AND derived=0", (args.id,)):
        print(f"     ← {rr['from_id']}  ({rr['rel']})")
        has = True
    if not has:
        print("     （无）")
    con.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="错误档案检索索引服务")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="初始化脚手架（幂等，不覆盖）").set_defaults(fn=cmd_init)
    sh = sub.add_parser("show", help="显示记录详情与关联链")
    sh.add_argument("id", help="记录 ID，如 ERR-006")
    sh.set_defaults(fn=cmd_show)
    sub.add_parser("rebuild", help="全量重建索引").set_defaults(fn=cmd_rebuild)
    sub.add_parser("stats", help="标签分布").set_defaults(fn=cmd_stats)
    sub.add_parser("check", help="一致性校验").set_defaults(fn=cmd_check)

    q = sub.add_parser("q", help="检索")
    q.add_argument("--tag", action="append", default=[],
                   help="标签，可重复（默认 AND 交集）")
    q.add_argument("--any", action="store_true", help="标签改为 OR 并集")
    q.add_argument("--module", help="模块名（模糊匹配）")
    q.add_argument("--func", help="函数名（可选，模糊匹配）")
    q.add_argument("--status", help="状态过滤，如 active")
    q.add_argument("--meta", help="元标签筛选，如 #误判史")
    q.add_argument("--include-archived", action="store_true",
                   help="包含已归档记录（默认排除）")
    q.add_argument("-v", "--verbose", action="store_true", help="显示归因/策略")
    q.add_argument("--json", action="store_true", help="JSON 输出")
    q.set_defaults(fn=cmd_query)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
