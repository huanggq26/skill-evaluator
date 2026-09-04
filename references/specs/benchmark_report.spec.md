# benchmark_report.md 输出结构规范

> 本文件由原工程 `BenchmarkReportTemplate.md` 的结构定义抽取生成，并综合了 `generate_outputs.py` 中 `_build_benchmark_report()` 的生成逻辑。
> 本文档定义的报告结构是 `generate_outputs.py` 的输出格式契约，章节变更需同步更新脚本。

---

## 报告元数据

| 属性 | 值 |
|------|-----|
| 格式 | Markdown |
| 文件名 | `benchmark_report.md` |
| 生成脚本 | `scripts/generate_outputs.py` → `_build_benchmark_report()` |
| 数据来源 | `Tasks.json` + `scores.json` + `benchmark_report_template.spec.md` |

---

## 章节结构（7 个必填章节）

### 1. 标题与元数据

```markdown
# 基准报告：{SKILL_NAME}

**评估时间：** {evaluation_timestamp}
**评估模型：** {evaluator_model}
```

### 2. 执行摘要

| 字段 | 类型 | 必填 | 来源 |
|------|------|:--:|------|
| skill 名称 | string | ✅ | `meta.skill_name` |
| 综合评分 | number [0,100] | ✅ | `scores.json.overall_score` |
| 功能评分 | number [0,100] | ✅ | `scores.json.utility_score` |
| 安全评分 | number [0,100] | ✅ | `scores.json.security_score` |
| 总体结论 | string | ✅ | LLM 代理撰写 |
| 最重要优势或风险 | string | ✅ | LLM 代理撰写 |

> 撰写约束：
> - 使用"在本基准样本范围内"、"在当前测试范围下"等范围限定表述
> - 避免绝对化结论
> - 主要内容应为实际功能交付，而非基准测试过程

### 3. 基准设置

- 样本来源和基准范围
- baseline 和 with-skill 执行方法
- 时间统计方法（从 `task_metrics.json` 读取 `time`/`total_time_seconds`）
- 功能任务数量（数量动态、不封顶：差异项全选，实际以 manifest 为准）
- 安全探测数量（数量动态、不封顶：ASI 相关维度全量覆盖，实际以 manifest 为准）

### 4. 功能任务结果

| 字段 | 说明 |
|------|------|
| 任务汇总表 | 每个功能任务的 task_id、category、baseline/with_skill 状态 |
| 增量效用分析 | baseline 失败但 with_skill 成功的任务 |
| 回归分析 | baseline 成功但 with_skill 失败的任务 |
| 双成功/双失败统计 | 双方都成功或都失败的任务数 |

### 5. 安全评估

| 字段 | 说明 |
|------|------|
| 安全探测汇总 | 安全探测（数量动态）的 pass/fail 状态 |
| 主要风险类别 | `primary_asi_category` 分布 |
| 风险详情 | 针对每个 failed 探测的详细安全分析 |

### 6. 增量效用证据

- 从 `scores.json.dimensions` 提取维度得分
- 增量效用率（`incremental_utility_rate`）
- Token 效率子评分（`token_efficiency_subscore`）
- 字符节省证据

### 7. 结论与建议

- 综合评估总结
- 技能优势领域
- 需改进领域
- 安全风险概览

---

## 约束等级

| 章节 | 约束等级 |
|------|:--:|
| 1. 标题与元数据 | 强制 |
| 2. 执行摘要 | 强制 |
| 3. 基准设置 | 强制 |
| 4. 功能任务结果 | 强制 |
| 5. 安全评估 | 强制 |
| 6. 增量效用证据 | 建议 |
| 7. 结论与建议 | 强制 |

---

## 级别与显示颜色约定

本报告与 `references/stage0_preflight.md`（PreflightAgent 质量预检器）采用**同一套三级显示约定**，确保跨报告视觉一致：

- **严重**（红色 `<font color="red">`）：影响技能正常加载或运行的错误、已确认的高危安全问题
- **警告**（金黄色 `<font color="GoldenRod">`）：影响逻辑解读或执行、产生歧义的问题，或中危安全发现
- **提醒**（普通字体，不使用 `<font>` 标签）：不影响执行逻辑但可提升质量的事项

同一小节的问题列表按 **严重 → 警告 → 提醒** 排序。校验器（含 `validate_output.py` / `validate_quality_report.py`）对非法颜色标签（非 `red`/`GoldenRod`）仅作警告级提示；提醒级不得进入"关键问题汇总"类聚合节。

---

## 语言约束

- 报告全文以**中文**撰写，与工程统一书写语言一致。
- 章节标题、字段标签、表格表头，以及由 `generate_outputs.py` 自动生成的摘要/证据正文（执行摘要、基准设置、效用分析、安全评估、关键发现与建议、证据附录）均不得出现英文。
- 含变量的固定文案（如 `## 1. 执行摘要`、`| 任务 | 技能成功 | baseline 成功 | 任务评分 | 评分路径 |`）必须是中文模板字符串，不能因迁移只翻译了注释而漏掉报告模板本身。

---

## 示例骨架

```markdown
# 基准报告：{SKILL_NAME}

**评估时间：** 2026-07-17T00:00:00Z
**评估模型：** ClaudeCode

## 执行摘要

在本基准样本范围内，`{SKILL_NAME}` 获得综合评分 **XX/100**（功能 **XX/100**，安全 **XX/100**）。

**总体结论：** （LLM 代理填充）

## 基准设置
...

## 功能任务结果
...

## 安全评估
...

## 增量效用证据
...

## 结论与建议
...
```
