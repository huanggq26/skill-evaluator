## Why

两处缺陷导致**不该报的问题被写进报告**，且可能触发错误的硬拦截：

- **R12**：静态评测没有区分「运行逻辑/代码」与「治理、开发态、辅助记录」内容。实测证据：对 `skill-doctor` 扫描时，`.gitignore:12` 的 `/tmp/`（忽略临时目录的正常写法）与 `.project/CONTEXT_HANDOVER.md` 的 `/Users/<用户名>`（治理区文件）被判为可移植性警告项写入报告。而项目 `SKILL.md` 早有纪律「发布包不含任何开发态文件」——**不发布的内容不该被评测**。
- **R20**：`dep_probe.py` 的探测请求硬编码 `method="GET"`；POST 端点被 GET 探测返回 405，被判为**契约型缺陷**（技能自身缺陷），进而触发硬拦截（中止后续阶段）并写入问题报告。上个版本于 Windows + opencode 环境实测即出现「6 项依赖探测失败（405），误判为 contract_defect」。

## 任务类别判定

- 判据：是否改变对外可观察行为 → **是**（改变报告收录范围、缺陷分类与是否硬拦截）
- 分流：**行为变更**，任务态由本变更承载，不登记 TASKLOG

## 历史错误（ERR 编号）

无。

## What Changes

| # | 变更 | 优先级 |
|---|---|---|
| R12 | 评测范围收敛为**随发布包分发的内容**；排除治理区 `.project/`、规范区 `openspec/`、平台机制目录 `.codebuddy/`、版本控制文件 `.gitignore` / `.gitattributes` / `.DS_Store` 等；报告中注明「未纳入评测的目录」清单 | P1 |
| R20 | 依赖探测支持 HTTP 方法声明（从 manifest 读取 GET/POST，或 OPTIONS 自动探测）；**方法不符导致的 405 判为配置类缺陷，不得判为契约型缺陷** | P1 |

R12 的排除依据：项目 `SKILL.md` 既有纪律「发布包不含任何开发态文件（治理区、治理入口、上级规格都不发布）」，`openspec/config.yaml` 第 4 条亦规定三者不随发布包分发。本变更是把既有纪律落到扫描器。

## Scope（范围）

- `scripts/extract_stats.py`（目录排除名单、扫描范围）
- `scripts/build_objective_data.py`（目录树遍历排除）
- `scripts/dep_probe.py`（HTTP 方法与分类）
- `references/dependency_availability.md`（分类规则）

## Non-goals（非目标）

- 不改报告模板与章节结构（另立变更）
- 不改门禁总体机制（另立变更「阶段 0 门禁可达性」）
- 不处理阶段 1–3 的样本生成（范围外）

## 待确认（实施时裁决）

| # | 事项 |
|---|---|
| Q9 | 治理入口文件（`AGENTS.md` / `CODEBUDDY.md` / `opencode.json`）是否一并排除（项目文档称其不发布，倾向排除） |
| Q10 | 排除后目录树（dir_tree）是否仍展示被排除目录（倾向不展示，改为注明） |

## Artifacts（产物清单）

| 产物 | 路径 |
|---|---|
| 改造后的扫描与探测脚本 | `scripts/extract_stats.py`、`scripts/build_objective_data.py`、`scripts/dep_probe.py` |
| 改造方案（工作文档） | 下载目录 `输出报告模板约束优化方案.md` |

## 关联依据

- 外部反思输入：`skill-evaluator-反思与改进建议.md` 问题 4 / 问题 5（实测于 Windows + opencode）
- spec 域：`dependency-availability`
