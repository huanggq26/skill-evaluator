<!--
  本模板是「基准评分报告」格式的唯一真相源（定义只在一处）。
  下列 HTML 注释为机器可读标注，渲染报告时不可见，仅供 schema 抽取器解析：

  ① 节标注（每节一个）：
     `<!-- section: <节标识> role: <scoring> optional: <true|false> -->`
     - role     : 本节职能归属。评分报告全部节 role 一律为 scoring（面向决策者 / 发布门禁）。
     - optional : true = 条件节，无内容时整节不输出；false = 固定节，必须输出。

  ② 数据槽位：
     `<!-- field: <字段名> -->`  由脚本回填结构化内容。

  ③ 职能红线（由门禁机器校验，严禁违反）：
     - 本节 role=scoring，**不得**写入：整改建议、待修复项、问题明细、修复指引。
     - 出现上述内容一律指向问题报告 `problem_report.md`。
     - 报告内**不得**出现 role=problem 的节。

  ④ 标题纪律（强制）：
     - 报告标题**不得**出现内部字段名、代码标记、英文代号（如 `DEP-AVAIL`、`baseline`、
       `with_skill`、`verdict` 等）——读者看不懂。
     - 此类信息一律移入本节注释或「填写口径」块（渲染时剥离），不进报告正文。
-->

# 评分报告：<skill-name>

> **模板说明（生成报告时删除本段）**：
> - 节编号由本模板固定，脚本**不得**动态计算编号（历史缺陷：编号 `4.2/4.3` 随分支变化，导致下游引用漂移）。
> - 条件节仅当 `optional: true` 且无内容时整节省略；固定节无内容时写该节既定空态文案，不输出空表头。
> - 本节职能为**评分**：只给结论与分值依据，整改明细一律指向 `problem_report.md`。
> - 标题不得含内部字段名与英文代号。

<!-- section: summary role: scoring optional: false -->

## 1. 执行摘要
<!-- field: executive_summary -->

<!-- section: setup role: scoring optional: false -->

## 2. 基准设置
<!-- field: benchmark_setup -->

<!-- section: comparison role: scoring optional: false -->

## 3. 裸 Agent 与装了本技能的对比
<!-- field: baseline_vs_withskill -->

> **填写口径**：两种运行模式的对照——「裸 Agent」= 未装本技能；「装了本技能」= 本次被测对象。

### 3.1 时间差异解读
<!-- field: time_diff_interpretation -->

<!-- section: capability role: scoring optional: false -->

## 4. 被测技能功能能力
<!-- field: capability_overview -->

### 4.1 结果解读
<!-- field: capability_interpretation -->

<!-- section: sample_defect role: scoring optional: true -->

### 4.2 样本设计缺陷（不计入用户功能能力，须修正后重测）
<!-- field: sample_design_defects -->

<!-- section: dependency role: scoring optional: false -->

## 5. 依赖可用性

### 5.1 外部依赖可用性
<!-- field: dependency_availability -->

<!-- section: security role: scoring optional: false -->

## 6. 安全评估
<!-- field: security_assessment -->

> **填写口径**：本节只给**安全维度的评分结论**（探测通过数 / 维度结论）。
> 逐条探测明细与整改项属问题职能，写入 `problem_report.md`，此处仅作指向。

<!-- section: verdict role: scoring optional: false -->

## 7. 关键发现
<!-- field: key_findings -->

> **填写口径**：本节给**使用 / 审核技能的人**的可执行结论（上架结论 + 门禁四维裁决依据）。
> 复杂归因、整改建议与问题明细见问题报告 `problem_report.md`。

<!-- section: evidence role: scoring optional: false -->

## 8. 证据附录
<!-- field: evidence_appendix -->

<!-- section: gate role: scoring optional: false -->

## 9. 门禁四维与评分字典
<!-- field: gate_dimensions -->

### 9.1 裸 Agent 与本技能都能完成的任务（可比集）
<!-- field: comparable_tasks -->

### 9.2 各功能任务 Token 消耗与倍率明细
<!-- field: token_consumption -->
