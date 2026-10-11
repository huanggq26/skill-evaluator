<!--
  本模板是「问题改进报告」格式的唯一真相源（定义只在一处）。
  下列 HTML 注释为机器可读标注，渲染报告时不可见，仅供 schema 抽取器解析：

  ① 节标注（每节一个）：
     `<!-- section: <节标识> role: <problem> optional: <true|false> -->`
     - role     : 本节职能归属。问题报告全部节 role 一律为 problem（面向开发者 / 下游 skill-doctor）。
     - optional : true = 条件节，无内容时整节不输出；false = 固定节，必须输出。

  ② 数据槽位：
     `<!-- field: <字段名> -->`  由脚本回填结构化内容。

  ③ 职能红线（由门禁机器校验，严禁违反）：
     - 本节 role=problem，**不得**写入：分值、评分结论、上架裁决（verdict）、门禁通过与否。
     - 报告内**不得**出现 role=scoring 的节。

  ④ 标题纪律（强制）：
     - 报告标题**不得**出现内部字段名、代码标记、英文代号（如 `verified=true`、`SafeTest`、
       `with_skill`、`Functional Grading Failures` 等）——读者看不懂。
     - 此类信息一律移入本节注释或「填写口径」块（渲染时剥离），不进报告正文。

  ④ 与前置报告的关系：
     阶段 0 静态质量报告为**前置报告**，其「关键问题汇总」段落由本节四转录汇总，
     不另起评分、不与安全问题双计。

  ⑤ 措辞统一：本报告的「未检查」与阶段 0 质量报告的「未检查」同义——
     指未产出确定结论，而非「查过没问题」。
-->

# 问题报告：<skill-name>

> **模板说明（生成报告时删除本段）**：
> - 节编号由本模板固定（一 ~ 六），脚本不得动态计算。
> - 条件节仅当 `optional: true` 且无内容时整节省略。
> - 问题类小节无内容时写该节既定空态文案（斜体「无…」句），**不输出空表头**。
> - 本节职能为**问题**：只给可整改的问题与定位，分值 / 裁决一律见 `benchmark_report.md`。
> - 标题不得含内部字段名与英文代号。

<!-- section: summary role: problem optional: false -->

## 摘要

### 已确认问题 · 按严重度
<!-- field: confirmed_by_severity -->

### 功能任务问题 · 按任务
<!-- field: functional_by_task -->

<!-- section: security role: problem optional: false -->

## 一、已确认安全问题
<!-- field: security_confirmed -->

> **填写口径**：本节只列**已通过证据核对、确认成立**的安全问题（对应内部 `verified=true`）。
> 未通过核对者不得混入本节。

<!-- section: efficiency role: problem optional: false -->

## 二、效能退化
<!-- field: efficiency_degradation -->

> **填写口径**：来源为「两种模式都能完成、且产出相同可比较」的任务中，
> 装了本技能反而更慢或更耗者——「做对了但更慢」。

### 被排除的不可比变慢任务（任务范围不同，不计为效能退化）
<!-- field: excluded_incomparable -->

> **填写口径**：效能维度不参加门禁决策（不导致 REJECT），仅作改进定位的软指标。
> 范围相同而真实变慢者计入上节；范围不同者列于本节，不得污名化为退化。

<!-- section: functional role: problem optional: false -->

## 三、功能任务问题（仅装了本技能的运行）
<!-- field: functional_failures -->

> **填写口径**：只列**装了本技能**时未通过的功能项——这些才是本技能自身需整改的缺陷。
> 裸 Agent（未装本技能）的失败属预期对照结果，不计入待整改问题，仅作对照说明。

<!-- section: quality role: problem optional: false -->

## 四、质量评估（前置质量报告）
<!-- field: quality_preflight -->

> **填写口径**：转录阶段 0 静态质量报告的「关键问题汇总」段落。
> 质量 findings 不评分、不作为安全项、不与安全问题双计。

<!-- section: scope role: problem optional: false -->

## 五、评估范围与可信度
<!-- field: scope_confidence -->

<!-- section: unverified role: problem optional: true -->

## 六、未检查
<!-- field: unverified_findings -->

> **填写口径（关键）**：本节**默认不输出**，标题与内容一并省略。
> 触发条件：仅当出现「证据不足、未通过证据核对」的条目（内部 `verified=false`）时才生成整节。
> 按阶段完成门禁，流程完整执行时此类条目应已被核实或排除，
> 故**正常交付物中不存在本节**；本格式保留仅作异常兜底。
> 措辞与阶段 0 质量报告的「未检查」统一，均指未产出确定结论。

---

<!-- field: cross_reference -->
