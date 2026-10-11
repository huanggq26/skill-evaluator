# 任务清单

> 归档前自检项与初筛命令遵 `.project/AGENTS_RULES.md#治理执行清单（薄层）` C 小节。

## 0. 前置（每次续跑必做）

- [x] 读项目规则层（`.project/AGENTS_RULES.md`）重建约束上下文；按模块与标签检索错误档案（`.project/error_registry`），读完原文核对前提后再动手，禁止只读单一证据源

## 1. 已实施并通过验证

- [x] **P1** 未执行不判失败（`scripts/backfill_reviews.py`）
      - 回填前先读 `result_dir/result.json`，`status` 为 `unsupported`/`blocked` 时：
        `state=skipped`、`passed/failed/total` 均置 0，并打印「跳过（任务未真实执行，不计入失败）」
      - 验证：对 v10 产物重跑，4 个任务（FT01/FT02 × baseline/with_skill）全部输出跳过，
        `state=skipped`、`failed=0`、`total=0`（修复前为 `fail`、`0/10`）
- [x] **P2** §4.2/§4.3 与功能表同源（`scripts/generate_outputs.py`）
      - `task_map` 存在时，按任务 ID 反查服务场景名作为展示名（多场景用顿号连接）
      - 验证：重跑后 4.2 显示「服务场景 1：数据库列表查询」，与 §4 表格一致
- [x] **P3** 问题报告标题取 `manifest.skill_name`（`scripts/assemble_findings.py`）
      - `render_markdown` 增 `skill_name` 参数；main 从 manifest 读取后传入；路径推导仅作回退
      - 验证：语法通过；逻辑经代码审读确认（需下轮真实运行复核）
- [x] **P4** `assemble_findings.py` 写版本号
      - 与另两个脚本一致，写入 `> 评测器版本：<VERSION>`（读取用 `utf-8-sig`）
      - 验证：语法通过（下轮真实运行复核）

## 2. 待观察（依赖下轮真实运行）

- [x] 确认三份报告末尾均出现版本号，且标题为技能名而非目录名
- [x] 确认功能维度不再出现「0/10 失败」观感，改为「跳过 / 未实测」

## 3. 归档前自检

- [x] 待观察项在真实运行中确认通过
- [x] `openspec validate --strict` 通过
- [x] 回归入口退出码 0
