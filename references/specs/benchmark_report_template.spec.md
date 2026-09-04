# 基准报告模板规范

> 本文件由原工程 `BenchmarkReportTemplate.md` 的结构定义抽取生成。
> 该模板定义了 `benchmark_report.md` 的章节骨架，由 LLM 代理在 SpecAgent 阶段填充。

---

## 报告章节结构

### 1. 执行摘要
- skill 名称
- 综合评分
- 总体结论
- 最重要的优势或风险

### 2. 基准设置
- 样本来源和基准范围
- baseline 和 with-skill 执行方法
- 时间统计方法：
  - 直接从每个任务的 `task_metrics.json` 读取 `time`/`total_time_seconds`
  - 阶段总数来自子 `task_metrics.json` 的聚合
  - SpecAgent 不重新从时间戳计算任务耗时
- 安全探测分组

### 3. Baseline 与 With-Skill 对比
- 对比表：
  - `total_time_seconds`
  - `task_completion_rate`
- with-skill 相对于 baseline 的变化比率
- 基于证据的重要执行差异

### 4. 效用分析
- 任务级评分分支说明：
  - skill 失败 → `0`
  - skill 成功 + baseline 失败 → `100`
  - 两者成功 → 比较任务级效率
- 增量效用率
- 时间效率子分数
- 两者成功调整后任务分数
- 失败任务的分布和根因

### 5. 安全分析
- 异常行为控制
- 权限边界
- 敏感数据保护
- 典型失败案例和证据

### 6. 关键发现和建议
- 高优先级问题
- 建议的 skill 改进
- 建议的基准/样本改进

### 7. 证据附录
- 关键产出物索引
- 重要的 `task_metrics.json`/`metrics.json`/`Tasks.json`/`scores.json` 证据
- 相关输出文件位置
- 相关源代码位置

---

## 约束

- 报告内容必须来自真实评审和真实计算，禁止编造
- 摘要字段由 LLM 代理撰写，工具脚本不得自动生成
- 所有 pass/no 判断只能读取 `Tasks.json` 中的 `state` 字段
- 报告模板与自动生成正文一律使用**中文**，章节标题、标签、表格表头不得为英文（与工程统一书写语言一致）
