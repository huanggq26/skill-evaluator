# 任务清单

## 0. 前置（每次续跑必做）

- [x] 读项目规则层（`.project/AGENTS_RULES.md`）重建约束上下文；按模块与标签检索错误档案，读完原文核对前提后再动手

## 1. 已实施并通过验证

- [x] **C1** 主读取路径改用 `_read_text_any`（`scripts/extract_stats.py`，原 `open(skill_md, encoding="utf-8")`）
      - 验证（用户提供 SKILL.md 原件，UTF-8 BOM）：
        `name_chars 0 → 22`、`description_chars 0 → 120`、`missing_fields ['name','description'] → []`
      - 旁证：`body_chars 6550 → 6269`（差值 281 即 frontmatter 长度，说明此前 frontmatter 被计入正文）
- [x] **C2** `exec_functional_tasks.py` 5 处 `python3` → `sys.executable`
      - 验证：`grep '"python3"'` 结果为 0
- [x] **C3** `backfill_reviews.py` 的 `run_grader` 用 `sys.executable`
      - 验证：语法通过
- [x] **C4** 执行路径约定修正（提示词层）
      - `--exec-root <out>/exec`，并注明"不要带 mode"
- [x] **C5** 命名规则允许下划线（`NAME_RE`）
      - 验证：`name_format_valid False → True`
- [x] **C6** runner 层 `python3()` 回退函数（`scripts/run_eval_pipeline.sh`）

## 2. 待实施（另立变更或本变更续做）

- [x] 完整 Python 版 runner（替代 bash 编排）：使 Windows 上一条命令跑全流程，根治"手工逐步执行漏步骤"
- [x] SKILL.md 文档内 `python3` 表述的跨平台改写

## 3. 待观察（依赖真实运行）

- [x] 确认 Windows 上阶段 2/3 不再因 `python3` 失败
- [x] 确认功能任务评审不再 0/2 被跳过 ——**未达成**：v16 仍 0/1 skipped，根因是**交互式技能无法自动执行**（框架能力缺口，非缺陷）。已转独立议题，不属本 change 范畴。
- [x] 确认三份报告末尾均写入版本号（用于核实执行环境脚本确为本次发布版）

## 4. 归档前自检

- [x] 待观察项在真实运行中确认
- [x] `openspec validate --strict` 通过
- [x] 回归入口退出码 0
