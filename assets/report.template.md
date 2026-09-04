<!--
  本模板是「质量评估报告」格式的唯一真相源（定义只在一处）。
  下列 HTML 注释为机器可读标注，渲染报告时不可见，仅供 schema 抽取器解析：

  ① 列结构声明（全局唯一，同构表格共用）：
     `<!-- columns: 位置,原因,改进建议 -->`
     所有"问题类"表格列结构一致，仅维度名不同；列名改此处即全局生效。

  ② 维度标注（每个表格维度一个）：
     `<!-- dim: <维度名> type: <objective|subjective> -->`
     - objective : 该维度数据由脚本(extract_stats/dep_probe)产出，AI 不生成。
     - subjective: 该维度需 AI 基于事实基座主观评测生成。
     系统层"是否客观"以「客观 JSON 实际是否含该字段」唯一裁定；
     合并时客观存在即优先，AI 误填亦被覆盖。本标注仅为 AI/读者提示。

  ③ 非表格维度（如技能摘要、功能表）以文本字段标注：
     `<!-- field: <字段名> type: <objective|subjective> -->`
-->

# 技能质量评估报告: <skill-name>

> **模板说明（生成报告时删除本段）**：
> - 每个检查类型/子类型小节二选一：**有问题** → 输出下述表格（一行一个问题）；**无问题** → 不输出空表头，小节标题下直接写"无"。
> - 「对外依赖」中某类调用为空、「关键问题汇总」某级别为空，同样写"无"。
> - 问题行级别标记：严重 `<font color="red">…</font>`、警告 `<font color="GoldenRod">…</font>`、提醒为普通字体；同一小节按 严重 → 警告 → 提醒 排序。
> - 「问题位置」必须为可定位的 `资源文件:行号`（如 `scripts/run.py:12`、`SKILL.md:80`）。

<!-- columns: 位置,原因,改进建议 -->

## 技能摘要
字数统计（客观，脚本提取）：
<!-- field: stat_chars type: objective -->
目录结构（客观，脚本遍历技能目录生成）：
<!-- field: dir_tree type: objective -->
多模态能力（主观，AI 基于 SKILL.md 归纳）：
<!-- field: modalities type: subjective -->

功能表（用户服务场景，AI **语义归纳**「技能为用户做什么」；**不是产出物清单**，产出物见下节）：
> **模板说明**：列该 skill 的**对外服务场景**（用户能怎么用、用它做什么），**不是产出物清单**
> （产出物由下方「产出物清单」客观解析，两者互补不重复）。
> 严禁把 L2 过程策略/内部脚手架当作服务场景，如样本生成、安全探测脚手架生成、generate_probe_scaffolds、
> gen_functional、assemble_manifest 等。表格格式：`| 服务场景 | 用户意图 | 触发方式 | 产出（见产出物清单） |` + 数据行。生成报告时删除本段（含下方表头）。
<!-- field: function_table type: subjective -->
| 服务场景 | 用户意图 | 触发方式 | 产出（见产出物清单） |
|------|------|------|--------|

产出物清单（客观，脚本静态解析 SKILL.md「L1 产生物」声明，**不运行被测技能**）：
> **模板说明**：列出技能对外交付的产物文件及其消费方。来源为 SKILL.md「L1 产生物」声明；
> 消费方按扩展名判定（.md/.csv/.html → 人阅读；.json/.jsonl/.yaml → 程序解析；含 template → 人复用）。
> 本清单仅供阅读与核对，**不在后续流程中做产出物验证**（评测不可能真正运行被测技能并验证其产出物）。
<!-- field: artifact_manifest type: objective -->

> **填写总则（两类维度，切勿混淆）**：
> - **清单类**（功能表、产出物清单）：任务是**列全**，即使没问题也要完整列出（有信息价值）。
> - **问题列表类**（内容正确/完整/对齐/冗余/不明确、分类与关联、身份与触发、多模态能力、
>   调用其他 Tools/Skills/系统命令等）：任务是**记问题**。
>   **无问题 → rows 留空（渲染为「无」），严禁填充「未发现问题 / 保持现状」这类条目**——
>   没有内容的表格是冗余信息。仅当发现**风险或问题**时才填行，并写明风险意见与改进建议。
> - 特别地，「调用其他 Tools / 系统命令」的客观候选已在本节正文列出；主观表格**只填风险**，
>   无风险则留空（不要把候选重抄一遍）。

### 格式检查
#### Frontmatter 质量
<!-- dim: frontmatter_quality type: objective -->

#### 结构与组织
<!-- dim: structure_org type: objective -->

#### 文法和语法
<!-- dim: grammar type: subjective -->

### 对外依赖

> **模板说明**：以下候选由脚本静态扫描 SKILL.md/references 提取，AI 复核是否真实依赖。生成报告时删除本段。
> **结构硬规则**：三类调用各由下方一个 `####` 子小节承载，**客观候选（field）与 AI 结论（dim）都填在该子小节内**；
> 不要再出现「调用其他 Tools：」这类冒号行——冒号行与子小节双写会导致内容错位（值落在冒号行、子小节却是"无"）。
> **填写口径**：子小节内先呈现客观候选，紧随其后给出 AI 复核结论。**候选非空时，dim 必须给出复核判断**
> （如"经复核均为真实依赖"或"其中 X 非真实依赖，理由…"），**不得只写"无"**——
> 否则会出现「候选列表 + 无」自相矛盾的呈现（读者无法判断到底有没有依赖）。
> 仅当候选与 AI 复核均为空时，整节写"无"。

#### 调用其他Tools
<!-- field: deps_tools_candidates type: objective -->
<!-- dim: deps_tools type: subjective -->

#### 调用其他Skills
<!-- field: deps_skills_candidates type: objective -->
<!-- dim: deps_skills type: subjective -->

#### 调用系统命令
<!-- field: deps_commands_candidates type: objective -->
<!-- dim: deps_commands type: subjective -->

### 内容验证
#### 内容正确
<!-- dim: content_correct type: subjective -->
> **模板说明**：表述约束——只用用户能看懂的话说明结论，不得暴露技能内部文件名/路径（如 `references/api.md`、`errors.md` 这类内部文档路径）、内部变量名或程序代号。生成报告时删除本段。

#### 内容完整
<!-- dim: content_complete type: subjective -->
#### 评测目标与技能范围对齐
<!-- dim: content_scope_alignment type: subjective -->
#### 内容冗余
<!-- dim: content_redundant type: subjective -->
#### 内容不明确
<!-- dim: content_ambiguous type: subjective -->

### 生态适配
#### 分类与关联（Placement & Relations）
<!-- dim: eco_placement type: subjective -->
> **模板说明**：检查项——分类放置正确、关联 skill 有用、与同行无重复、关联依赖健康（依赖无环 + 与关联 skill 内容不冲突）。生成报告时删除本段。

#### 身份与触发（Identity & Trigger）
<!-- dim: eco_identity type: subjective -->
> **模板说明**：检查项——同名命名唯一、触发不过宽、触发边界清晰、用户表达缺失。生成报告时删除本段。

#### 可移植性（跨机器/跨平台）
<!-- dim: eco_portability type: objective -->
> **模板说明**：检查项——① 不得把技能文件写死在某台电脑的固定路径上（如 `/Users/...`、`/home/...`、`C:\...`、网络共享路径、`/tmp`、写死的安装目录等）；② 脚本开头的解释器声明须规范（统一用 `#!/usr/bin/env ...` 形式）；③ 脚本换行格式须兼容多系统（不得用 Windows 风格换行符）。判级说明：上述候选由评测工具自动提取，由人工/模型复核（排除文档举例路径）后判定，工具不自动判级。生成报告时删除本段。

### 外部依赖可用性
> **模板说明**：本技能若需访问外部网站/服务才能工作，会自动检测这些外部依赖当前能否正常连通，检测结果并入本章节。问题性质说明：① 技能自身缺陷（须修正，属结构性否决）；② 运行环境或网络临时问题（不否决，仅报告）；③ 配置缺失（须由用户或运行环境提供，不否决）。探测状态：若技能声明了外部依赖则已执行探测；若无外部依赖则跳过本章节，不参与否决。生成报告时删除本段。

<!-- dim: dependency_availability type: objective -->

### 关键问题汇总
#### 严重（影响正常加载运行）
客观检查项：
<!-- field: objective_critical type: objective -->
AI 评估补充：
<!-- field: subjective_critical type: subjective -->
#### 警告（影响逻辑解读或执行）
客观检查项：
<!-- field: objective_warning type: objective -->
AI 评估补充：
<!-- field: subjective_warning type: subjective -->
