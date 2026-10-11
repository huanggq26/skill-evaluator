## Why

评测框架假定 Unix 环境（bash、`python3`），且对**文件编码**处理不完整，导致在 Windows 上出现一类"看起来是技能缺陷、实为框架问题"的误判。

实证：

| 现象 | 根因 | 后果 |
|---|---|---|
| `name` / `description` 字数均为 0，并报「缺少必需字段（严重）」 | SKILL.md 为 **UTF-8 带 BOM**(ef bb bf)，主读取路径用 `encoding="utf-8"` 未去 BOM → `\ufeff---` 匹配不到分隔符 → frontmatter 解析为空 | 误报严重级缺陷；`frontmatter_valid=True`（空串经 yaml 解析返回 `{}` 不算错误）**掩盖了真相**，把排查引向错误方向 |
| 阶段 2/3 执行失败 | `exec_functional_tasks.py` 5 处硬编码 `python3`，Windows 无此命令 | FileNotFoundError |
| 功能任务评审 0/2 被跳过 | 调用方传 `--exec-root <out>/exec/baseline`，而脚本内部再追加 mode → `exec/baseline/baseline/tasks/`；回填脚本按 `exec/<mode>/tasks` 定位不到 | 功能维度无评审结果 |
| `name` 格式被判不合规 | 命名规则只允许连字符，`table_column_relations`（下划线）被判违规 | 与目录名一致、语义清晰却被判错 |

**关键教训（须留档）**：编码修复此前已改了三处读取路径（walk_files 等扫描用），**唯独漏了读取 SKILL.md 的主路径**，导致"改了却一直不生效"。跨多个调用点的同类处理，必须枚举全部读写入口而非只改先发现的几处。

## 任务类别判定

- 判据：是否改变对外可观察行为 → **是**（改变静态检查结果、执行可用性、命名判定）
- 分流：**行为变更**，任务态由本变更承载，不登记进任务记录

## 历史错误（ERR 编号）

无。

## What Changes

| # | 变更 | 优先级 |
|---|---|---|
| C1 | 主读取路径改用 BOM 编码探测（`_read_text_any`：UTF-8 BOM / UTF-16 LE / UTF-16 BE / 无 BOM） | **P0** |
| C2 | `exec_functional_tasks.py` 5 处 `python3` → `sys.executable`（优于 `"python"`，后者在部分环境指向 Python 2） | **P0** |
| C3 | `backfill_reviews.py` 的 `python3` → `sys.executable`（`run_grader` 子进程） | **P0** |
| C4 | 执行路径约定：`--exec-root` 传 `<out>/exec`（**不带 mode**），脚本内部追加 | **P0** |
| C5 | 命名规则放宽：允许下划线（`^[a-z0-9][a-z0-9_-]*$`） | P1 |
| C6 | runner 层 `python3 → python` 回退（覆盖 bash 脚本内全部调用） | P1 |

## Non-goals（本次不做）

- **完整的 Python 版 runner**（替代 bash 编排）：工作量较大，另立变更。本变更只做必要兼容，使手工逐步执行可行。
- SKILL.md 文档内 `python3` 表述的改写（归上述 Python runner 变更一并处理）。
- `build_objective_data.py` 的 SyntaxWarning（低优先级，另立）。
