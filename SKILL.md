---
name: skill-evaluator
description: "当用户需要（1）对某个 AI Agent 技能/skill 进行端到端基准测试（质量预检 + 功能任务 + 安全探测 + 代码评审 + 评分报告），或（2）咨询本评测器自身的使用方法 / 报告解读 / 结果含义（FAQ）时使用。典型触发语：'测一下这个 skill 的质量/安全性'、'评估这个 skill 写得好不好'、'给这个 skill 做基准测试'、'skill-evaluator 怎么用'、'这个评测报告怎么读'、'它会不会改我的 skill'、'评测结果里的那些代号/分数什么意思'。注意：FAQ 类问题只答疑、不触发评测执行。"
version: 1.0.0
author: skill-evaluator
license: MIT
tags: [benchmark, skill-evaluation, safety, quality, agent]
agent_compatibility: [opencode, hermes, openclaw, claude-code, codebuddy]
platforms: [linux, macos, windows]
---

# Skill Evaluator — AI Agent Skill 基准测试

## Overview

对单个目标 skill 做 5 阶段（0–4）串行基准测试，产出可审计的质量 / 功能 / 安全评估报告。本 skill 兼容 opencode / hermes / openclaw / Claude Code / CodeBuddy 多平台运行。

## When to Use

- 提交新 skill 前做质量 + 安全双评测
- 评估某 skill 是否"真的有用、是否安全"
- 对现有 skill 进行同行评审（peer review）
- 仅想做预检（静态质量 + 可用性，快速、零功能执行）以改进技能 → 只跑阶段 0
- 在进行 skill 优化前获取评测报告，并基于报告进行修改
- （反向）Do NOT Use：非 skill 仓库评审、纯代码库审计、第三方 MCP 工具评审

## FAQ 服务（使用者问答模式，不触发评测）

当用户问本评测器"怎么用 / 报告怎么读 / 结果里那些代号分数什么意思 / 会不会改我的 skill"等咨询类问题时，进入 FAQ 模式（只读答疑、不跑评测、不写工作区）。详细触发识别、回答纪律（唯一权威源 = `references/USER_GUIDE.md`、无据不编、角色分流）与问题→答案锚点索引表，见 **`references/faq_service.md`**（按需加载，不占用本文件上下文）。

**文档直达**（用户想自己阅读而非听转述时）：提供文档的绝对路径与 `file://` 链接，由用户自行打开；
**不代为执行打开命令**（那属运行范围外命令，需单独授权）。
- 想了解**设计思路 / 原理** → `references/skill-evaluation-system.md`
- 想了解**怎么使用本评测技能** → `references/USER_GUIDE.md`

> 规格内**只写相对路径**，运行时解析为 `<本技能目录>/references/…` 的绝对路径（可移植性硬约束，严禁写死绝对路径）。

## 单独调用阶段 0（预检：静态 + 可用性）— 质量报告数据态流程

若用户仅要求预检（如"评估这个 skill 质量""写得不好在哪"），只执行阶段 0。阶段 0 是**快速预检闸门组**，由两步组成，均在耗时测试（阶段 1–4）之前完成。

> **核心原则（定义只在一处）**：`assets/report.template.md` 是报告格式的**唯一真相源**。脚本只产出**客观格式数据**（JSON），不再拼 markdown；LLM 依据模版标注的字段生成**主观格式数据**，二者合并为唯一 `report_data.json`，经 schema 校验后回填模版生成最终报告。报告渲染逻辑不写在代码里。

- **0A 静态质量预检**（必跑，纯静态、零执行）：`python3 scripts/extract_stats.py <SOURCE_DIR>` → `quality/extract_stats.json`；再 `python3 scripts/build_objective_data.py --stats ... --out quality/objective_data.json` 把客观事实映射为 objective 维度级格式数据（字段严格对应模版 `objective` 标注）。
- **0B 可用性预检**（条件步）：当被测技能存在外部依赖时执行 `dep_probe.py` → `dependency_probe.json`（纯 JSON），再跑一次 `build_objective_data.py --probe ...` 把可用性客观维度并入 `objective_data.json`；无外部依赖则 `dependency_skipped=true` 跳过、不否决。

**AI 回填（报告生成，由本 agent 执行）**：
1. 真实 `read_file` 模版 `assets/report.template.md`，依据其 `<!-- dim/field -->` 标注 + `objective_data.json` 事实基座，生成 `subjective.json`（只填 `subjective` 字段；客观字段不碰）。
2. 合并：`python3 scripts/merge_report_data.py --objective quality/objective_data.json --subjective subjective.json --template assets/report.template.md --out quality/report_data.json`（客观优先；未知字段/缺失客观维度报错）。
3. 校验：`python3 scripts/validate_quality_report.py --data quality/report_data.json --template assets/report.template.md`（schema 基准：字段对齐、客观维度必含、评分不进报告）。
4. 回填：`python3 scripts/render_report.py --template assets/report.template.md --data quality/report_data.json --out quality/<SKILL_NAME>评测.md --skill-name <SKILL_NAME>`。

> **0B 触发条件（关键）**：仅当依赖提取器从被测技能上下文提取到 `external_deps` 非空才执行 0B；空则跳过。即"不是所有技能都需要可用性评测"。

步骤：1) 读 `references/stage0_preflight.md`；2) 跑 0A 客观提取 + `build_objective_data`；3) 条件跑 0B 提取/探测 + 二次 `build_objective_data` 并入可用性；4) AI 按上「AI 回填」四步生成最终报告；5) 跑 `validate_quality_report.py --data` 门禁；6) 按「阶段 0 交互闸门」处理结果。

## 阶段 0 交互闸门（开始阶段报告产出后的行为，依运行模式而定）

开始阶段（阶段 0）预检闸门（0A 静态门禁 `validate_quality_report.py` + 0B 可用性契约型缺陷 `dep_probe.py` 硬拦截）跑完后，按运行模式二选一执行：

- **未过**（退出码非 0 或 `success=false`）：向用户一次性给出三样东西后**停止**，不进入阶段 1–4：
  1. **失败原因**：逐条转述门禁 `errors`/`warnings` 与报告「关键问题汇总」的具体问题项；
  2. **解决方案**：逐项给出对应修复建议（指明要改被测 skill 的哪个文件、改什么；强调改的是被测对象，不是本评测工具），修完可让本 agent 重跑阶段 0；
  3. **产物文件位置**：报告 `{QUALITY_REPORT}`、客观统计 `{PF_STATS}`、评测计划 `{PF_EVAL_PLAN}` 的**绝对路径**，让用户可直接打开细看。
- **通过**：按「用户交互与进度播报规范」告知报告绝对路径 `{QUALITY_REPORT}`，再按模式分流：
  - `--mode start`：**必须显式说明"本次仅完成阶段 0（预检），阶段 1→4 尚未执行"**，并给出继续全流程的具体命令（`bash scripts/run_eval_pipeline.sh --mode resume`）——不得只说"完成"而不交代进度与下一步（历史实证：用户以为跑完了全流程，实为只产出阶段 0，且无任何提示）。
  - `--mode full` / `--mode resume`：**不询问用户**，自动接续阶段 1→2→3→4（full 从 0 之后、resume 从 1 起），连续执行直至全部完成或某阶段 DoD 验证失败；中途仅按「用户交互与进度播报规范」同步进度，不逐阶段征询。

## 总览与阶段路线图

| 阶段 | 入口 reference | 输入 | 输出 | 门禁 |
|------|----------------|------|------|------|
| 0 预检（静态 + 可用性） | `references/stage0_preflight.md` + `references/dependency_availability.md` | `{SOURCE_DIR}` | `…/quality/{SKILL_NAME}评测.md` + 可用性章节 | 0A：`validate_quality_report.py` 退出码 0；0B：契约型缺陷 `exit 1`（无外部依赖则跳过） |
| 1 样本生成 | `references/stage1_sample.md` | `{SOURCE_DIR}` | `…/sample/` | 11 项验证 |
| 2 基线执行 | `references/stage2_baseline.md` | `…/sample/` | `…/exec/baseline/` | 5 项验证 |
| 3 带 skill 执行 | `references/stage3_withskill.md` | `…/sample/` | `…/exec/with_skill/` | 6 项验证 |
| 4 规格评估 | `references/stage4_spec.md` | `…/sample/`+`…/exec/` | `…/spec/` | 7 项验证 |

> 各阶段输出默认落在 `{RESULTS_ROOT}/{SKILL_NAME}/`（可用环境变量 `SKILL_EVALUATOR_RESULTS_ROOT` 覆盖），不写入本 skill 目录。

## 技能目标与产出物层级（Capability Goals & Artifact Tiers）

本技能的能力定义以本节为**唯一权威源**。下游（样本生成、manifest 的 `skill_capabilities_tested`、评分报告"覆盖能力"行）均须从本节派生，不得自行造名或反推。

### L0 技能目标（对外产出目标 / 用户交付）
用户真正要的是以下交付物，每个目标可细化为多项 L1 产生物：
1. **质量门禁（Quality Gate）** — 阶段 0 门禁 JSON 判定 + 质量评测报告。
2. **报告生成（Reporting）** — 阶段 4 基准评分报告 + 问题改进报告 + 模板。
3. **评分聚合（Scoring）** — 阶段 4 确定性总分与多维度量。

### L1 产生物（L0 的子产物，效能对比候选）
- 质量门禁 → `quality_report.md` + `gate_result.json`
- 报告生成 → `benchmark_report.md` + `problem_report.md`
- 评分聚合 → `scores.json`（含 `overall_score` / `utility_score` / `dimensions` / `raw_measurements` / `tasks`）

> L1 产生物可进一步按"报告中的不同角度评审问题""评分中的不同关键指标"细化，作为**效能对比（time / token / 正确性）的候选选项**。

### L2 过程策略 / 中间产物（内部手段，非用户交付）
为达成 L0/L1 而存在的内部策略或脚手架，如 `generate_probe_scaffolds`（安全探测脚手架生成）。**不能与 L0 技能目标并列**，不计入"用户能力覆盖率"，不进入 `avg_multiplier` 效能倍率。

**模板类文件一律属 L2，不得列入 L1 交付物**：`Template.json` / `Template.csv`（过程中间数据载体，
`cacu_total_score` 写入、`generate_outputs` 读取后生成最终报告）、`report.template.md`（框架提供的报告模板资产）。
三者均非运行产出的对外交付物，用户消费的是由它们生成的报告，而非它们本身。

### 功能项选择策略（Selection Policy）
- 仅 **L0 / L1** 可作为功能任务与效能对比项；
- **L2** 仅做内部正确性验证，manifest 中标记 `tier: "l2_internal"`、`user_facing: false`，下游（cacu 效能倍率、报告覆盖能力行）一律排除；
- `skill_capabilities_tested` 仅列 L0 目标（本例 3 项），由 SampleAgent 读取本节填充，禁止反推自造。

## 执行约定（串行 + 增量）

- 严格 0 → 1 → 2 → 3 → 4；前一阶段 DoD 满足才进下一阶段（除非仅跑阶段 0）。阶段 0 内部顺序固定：0A 静态预检 → 0B 可用性预检（条件步，无外部依赖则跳过）。
- **开始阶段（0）报告产出后的唯一分流点**（规则见「阶段 0 交互闸门」）：0A 或 0B 任一未过即阻断；通过后在 `--mode start` 结束、在 `--mode full`/`resume` 自动接续 1–4 连续跑完，中途不再停下征询。
- 每阶段**只在该阶段开始时**读对应 `references/` 文档，禁止阶段入口一次性全读（防上下文膨胀）。
- 所有路径与常量唯一定义源：`references/config.md`（内部路径相对本 skill 根解析；`{SKILL_DIR}` 记为 skill 安装目录）。
- 阶段 0 可独立于全流程运行，仅依赖 `{SOURCE_DIR}`。

### 执行完整性总纲（硬约束）

- **禁止未实测的推断**：任何"依赖不可达 / 任务无法执行"的结论，**必须**以实际探测（0B）或实际尝试执行的证据为依据。**禁止**依据域名、环境名（如含 `uat` / `test` / 内网后缀）、网络位置、部署区域等特征推断不可达，更不得据此跳过阶段。
- **执行尝试优先**：先尝试执行，再据结果处理；不得在未尝试的情况下放弃。单个任务失败须记录原因并**继续**执行剩余任务，不得中止后续阶段。
- **阶段过渡强制**：阶段 0 门禁通过后**必须**进入阶段 1 并推进至阶段 4。依赖不可达、被测技能质量低、功能简单、执行环境差异等**均不得**作为跳过阶段的理由（详见 `references/dependency_availability.md`「可用性探测结果的阻断边界」：仅契约型缺陷阻断）。
- **未完成须可见**：若某阶段因故未实际执行，评测产物**必须**显式标注未执行及原因，禁止产出"看似完整"的结果。

## 脚本调用约定

- **环境**：Python **≥ 3.8**（无强制第三方依赖；TOML 检查在缺 `tomllib` 时自动回退或跳过）。使用者侧的环境说明见 `references/USER_GUIDE.md#2.0 环境要求`。
- 客观统计（阶段 0）：`python3 scripts/extract_stats.py <SOURCE_DIR>`
- 质量门禁（阶段 0）：`python3 scripts/validate_quality_report.py --report <R> --plan <P> --stats <S> --template assets/report.template.md`
- 其余脚本（时间戳 / metrics / 评分 / 报告生成 / 安全聚合等）见各阶段 reference 文档内的具体命令与 `references/config.md` 的 `PF_*` / 阶段专属常量。

## 授权与范围契约（减少打扰 + 知情授权）

评测链路长、脚本多。为减少「逐条弹看不懂的命令让你授权」的打断，并让授权真正知情，本 skill 采用**范围授权**而非**逐命令授权**（完整契约见 `references/scope_contract.md`）：

- **默认范围（一次确认即可）**：只读 `{SOURCE_DIR}`（不改不删）+ 仅在 results 工作区（`SKILL_EVALUATOR_RESULTS_ROOT` 或 `{RESULTS_ROOT}/{SKILL_NAME}/`）内写 `sample/exec/spec/quality` + 仅运行本 skill 自带脚本与被测技能自身。不删用户文件、不改系统配置或凭据、不写 `{SOURCE_DIR}`、不写工作区外任何位置。
- **唯一的出网情形（已含在本次确认内，非越界）**：阶段 0B 可用性预检（`dep_probe.py`）会对**被测技能自身声明的外部依赖端点**做**只读 HTTP 探活**（D1–D6 checker，匿名 GET，不传凭据、不改远端）。这是「可用性预检」的本职——不探活就无法判断依赖是否存活。仅当被测技能提取到 `external_deps` 非空才触发；无外部依赖的技能 0B 整体跳过、完全不出网。**除此之外，本管线不访问任何其它网络资源**。
- **范围内免逐条授权**：上述范围内的操作合并为单次范围确认；不为每个 Python 脚本单独弹窗。
- **越界才单独授权**：仅当某步真要越界（写工作区外 / 删除 / 访问被测技能声明依赖之外的网络 / 改系统或凭据）时，才单独用大白话说明「做什么 / 读哪些 / 写哪些 / 风险等级」，再请你确认。
- **单点 runner**：`scripts/run_eval_pipeline.sh` 支持三种测评流程（`--mode`），合并为一次授权运行；启动时打印本契约范围摘要，让你知情：
  - `--mode start`：只跑开始阶段（0），输出开始阶段报告（质量预检报告）。
  - `--mode full`：全流程自动引导 0→1→2→3→4，无需用户参与，产出开始阶段报告 + 最后阶段报告（benchmark/problem）。full 模式下阶段 0 通过后不再停询用户，自动接续。
  - `--mode resume`：已跑过开始阶段，继续 1→4，产出最后阶段报告。阶段 1 脚手架可由 `--scaffold-spec` 自动生成；缺执行产物时打印「AI 评测执行者接续指引」而非崩溃。

> 透明性兜底：即便单次授权，runner 也会先打印范围摘要；任何脚本若试图越界，应立即停止并报告，不得静默执行。

## 运行状态策略：调试态 vs 发布态（按打开方式自动判定）

本 skill 的"是否记录会话日志 / 是否允许自我修改"由**运行状态**决定，而状态由**打开方式**自动判定（可用 `--project-state` 显式覆盖）：

- **调试态（debug）**：**以项目方式打开**本 skill —— 即本 skill 目录（记作 `{SKILLS_HOME}/<skill-name>/`，当前技能即 `{SKILLS_HOME}/skill-evaluator/`）被作为 IDE 工作区/项目根打开，目的是迭代本技能自身。等价 `--project-state debug`。
- **发布态（production / 非调试）**：**不以项目方式打开**，而是作为技能安装于 agent（位于 skills 目录）被调用去评测**其他** skill。等价 `--project-state production`。

> 判定启发式：当前工作区根目录 == 本 skill 安装目录 → 项目态（调试）；否则 → 发布态。若无法判定，按**发布态**处理（更安全：不写自身、不记日志）。`--project-state` 仅用于刻意调试一个"已安装的技能"这种罕见场景，通常应与打开方式判定一致。

### 两种状态的权限边界（硬规则）

| 能力 | 调试态 | 发布态 |
|------|--------|--------|
| 记录项目级会话日志（`.session_log/SESSION_LOG.md`） | ✅ 必须 | ❌ 不记 |
| 本技能自我修改（自优化闭环改 `scripts/`、`references/`、`SKILL.md`、`sample/`） | ✅ 允许 | ❌ 不允许 |
| 其他技能修改本技能目录 | ⚠️ 仅限本技能自优化触发 | ❌ 不允许（发布态本技能目录视为只读契约） |

1. **会话日志**：仅调试态向 `.session_log/SESSION_LOG.md` 追加；发布态**完全跳过**，既不写也不依赖该文件。
2. **自我修改**：仅调试态允许本技能在自优化闭环中写自身目录；发布态下本 skill **不得**对自身任何目录（`scripts/`、`references/`、`SKILL.md`、`sample/`、`assets/`）做写操作——只读取、只在 results 工作区产出评测结果。
3. **防御其他技能写入**：发布态下，本 skill 目录对其他技能应视为**只读契约**。本 skill 自身不写，也应避免/拒绝其他技能写入；若平台支持，建议安装目录设为只读。一旦检测到非本技能（其他技能或外部）发起的对本 skill 目录的写操作，应立即停止并向用户报告，不得静默放行。

### 发布态跳过规则（后备拦截 · 强制）

> **背景**：发布包不含任何开发态文件（治理区、治理入口、上级规格都不发布），故运行态文档中可能存在指向不存在文件的指针。本规则是**后备拦截**，保证这些指针永不被加载。

发布态下，遇到下列内容 → **一律不加载、不跳转、不报错，直接跳过**：

| 触发特征 | 例 |
|---|---|
| `【开发态】` 前缀标记 <!-- 发布隔离豁免 --> | 受【开发态】前缀标记的治理文件管辖 <!-- 发布隔离豁免 --> |
| 规格声明块内的 `层级/归属` / `自检锚点` 字段 <!-- 发布隔离豁免 --> | （发布区无规格文件，此条仅为兜底） |
| 指向治理区 / 治理入口的路径 <!-- 发布隔离豁免 --> | 治理区目录、以及仅维护期使用的项目入口文件 <!-- 发布隔离豁免 --> |
| 指向上级通用规格文档名 <!-- 发布隔离豁免 --> | 项目外的通用规格 / 元规格文档名 <!-- 发布隔离豁免 --> |

- **不因"文件不存在"而报错或中断评测**：开发态指针在发布态一律视为无效引用，静默跳过。
- **仅调试态**（或明确要修改本技能自身时）才加载上述内容。
- **运行逻辑校验只依赖源码**：核对实现行为是否一致时，以 `scripts/` 源码与 `SKILL.md` 为准，**不**依赖任何开发态规格文档。

## 项目级会话日志约定（开发态 · 已迁出）

> **本节属开发态治理内容**，仅调试态（以项目方式打开本技能）生效，**发布态完全跳过**。
> 完整约定见治理区规则文件（属维护期内容，不随发布包分发）。
> **评测流水线不读、不写、不依赖任何会话日志**。

## 关键决策点 / 门禁

- 阶段 0 未过门禁 → 阻断，先改 skill 再重跑。
- 阶段 1–4 的 DoD 见对应 reference 文档尾部 Verification Checklist / 结果验证。

## 执行纪律：运行计划 + 执行日志（过程文档）

每个阶段执行前必须先有可持久化的运行计划，执行中按计推进，并把"过程经验"沉淀为结构化日志，供**中断续跑**与 **skill-evaluator 自身优化**。两套工件均落在 results 根（跨中断持久），**不被流水线消费**，仅用于续跑与自优化。

### 1. 运行计划（RUN_PLAN / PF_EVAL_PLAN）
- **阶段 0**：计划即 `{PF_EVAL_PLAN}`，由 `{PF_VALIDATOR} --plan` **机器校验闭环**（残留 `[ ]` 即门禁失败）；重跑时仅执行未勾项。
- **阶段 1–4**：计划写入 `{RUN_PLAN}` 的对应节（`## Stage 1` … `## Stage 4`），格式为 `[ ]`/`[x]`/`[~]` 步骤清单（清单内容取自该阶段 reference 文档的「进度跟踪」/步骤）。
- **续跑协议**：进入某阶段时先读计划节。若已存在且含未勾 `[ ]` 项 → 从中断点续跑，已 `[x]`/`[~]` 跳过；若不存在 → 先创建该节清单再执行。
- **计划可被违反**：实际执行偏离计划时**允许**，但必须在执行日志写明违反项、位置与原因（见下）。

### 2. 执行日志（EXEC_LOG）
每个阶段在执行中 / 收尾时向 `{EXEC_LOG}` 追加条目，模板：

```text
## <UTC 时间戳> Stage N / <阶段名> — <事件：计划违反 | 异常 | 阶段小结 | 方法/脚本未定义·需推理生成>
- 位置：<具体步骤 / 文件 / 任务 ID>
- 原因：<为什么发生>
- 异常情况：<现象>
- 实际解决方案：<做了什么>
- 后续建议（自优化）：<给 skill-evaluator 自身的改进建议>
- 计划违反：<若违反计划，写明违反项 + 位置 + 后续建议；否则填"无">
```

- 阶段收尾必写一条「阶段小结」（做了什么、异常、后续建议）。
- **「方法/脚本未定义·需推理生成」类记录（自优化关键语料）**：执行某任务时，若被评工程（或评测工程自身）**未定义具体的任务完成方法/脚本**，执行过程中由 LLM **现推理方法或现生成脚本/脚手架**才得以推进，则必须追加一条该类型记录，且至少包含：
  - **缺位描述**：该任务原本缺什么（方法 / 脚本 / 脚手架）；
  - **现场产物**：LLM 现场推理出的方法 / 生成的脚本 / 脚手架概要（可附落盘路径）；
  - **可改进点（必填）**：该场景是否应固化进 skill-evaluator 的工程策略、被评技能的脚本、或评测脚手架，使其**可复跑、不必每次现推理**。
  - 目的：把"一次性即兴推理"沉淀为"可复用工程资产"，供「自优化闭环」自动采纳。
- 该文件仅供自优化，**不得**被任何流水线脚本 / 门禁读取或依赖。

### 3. 废弃日志的处理
- 全局 `agent_worklog.log`、样本根级 `timer.log` / `worklog.log` 原为自由文本、无消费方，已废弃 → 其内容职责并入 `{EXEC_LOG}`。
- **任务级 `tasks/{tid}/worklog.log` 与探测级 `probes/{id}/worklog.log` 必须保留**：它们是输出合约证据项，且 `backfill_character_metrics.py` 依赖任务级 `worklog.log` 做缺失代理，禁止删除或改为指向 EXEC_LOG。

### 4. 执行负载分级与子任务遗忘协议（加速 + 防爆窗）

> 目的：简单技能走最快直线路径（不做多余仪式），重负载技能用"流式遗忘 + 分会话续跑"消化上下文压力。与阶段 1 步骤 1.5 的探测预算上限（N=10）配套生效。

- **判级时机**：阶段 0 通过、制定 `{RUN_PLAN}` 时计算一次；判级结果与估算依据写入 RUN_PLAN 头部（`load_tier: L1|L2|L3` + `case_total=N`），可审计。
- **负载估算（确定性代理指标，不估 token）**：`case_total = 功能任务数 + 安全探测数`（每 case ≈13 个文件 + 功能任务 baseline/with_skill 各 1 次真实执行 + Grader 评审）。
- **L1 轻量（case_total ≤ 4）**：直线执行，**不启用**遗忘协议；尽量批量并行工具调用、每阶段集中勾选 RUN_PLAN 一次，减少往返以加速。
- **L2 流式（5 ≤ case_total ≤ 8）**：启用**子任务遗忘协议**——每完成一个 case：① 产物落盘；② RUN_PLAN 打 `[x]`；③ 丢弃该 case 的工作细节，仅保留父计划锚点；此后**禁止回读已完成 case 的文件**（确需查证时按需重读单个文件，禁止整目录回扫）。
- **L3 分会话（case_total ≥ 9）**：L2 全部纪律 + 在 RUN_PLAN 预置续跑断点（建议每完成 4 个 case 或每阶段末一处）。**断点仅是应急续跑锚点，不是停顿指令**：阶段 1–4 必须连续执行直至全部完成（同「阶段 0 交互闸门」），**只有当本轮对话上下文确实枯竭（命中动态升级哨兵②/③，或客观无法继续）时**，才允许收尾播报断点、留待下一轮续跑；不得在预算仍充足时主动停下等待用户说"继续"。
- **动态升级哨兵（运行时兜底，命中任一立即升一档并写 EXEC_LOG）**：① 本会话累计写入文件数 > 40；② 需要重读本会话自己刚写过的文件才能继续（上下文丢失信号）；③ 同一步骤因遗忘前文重复失败 ≥ 2 次。
- **防漂移铁律**：跨 case 共享约定（命名规则、评分规范、路径变量）一律以磁盘为准（RUN_PLAN / references），不依赖上下文记忆；"遗忘"仅指不再携带子任务细节，**先落盘再遗忘**，未落盘不得遗忘。

### 5. 自优化闭环（开发态 · 已迁出）

> **本节属开发态治理内容**，仅调试态（以项目方式打开本技能）触发；**发布态下本 skill 对自身目录完全只读**，不进入任何自优化流程、不改动自身任何文件（见「运行状态策略」权限边界）。
> 完整流程见治理区规则文件（属维护期内容，不随发布包分发）。

## 用户交互与进度播报规范（执行中必须遵循）

本 skill 评测链路长（最多 5 阶段）、可能真实执行任务并消耗较多时间与 token。执行 agent 在跑的过程中必须对用户保持**透明、可预期、可执行**的沟通。把下面几条当作硬规则，逐条执行。

### A. 开始前：方案对齐（仅一次）

进入阶段 0 之前，先用一段话跟用户对齐：

1. **被测对象**：复述用户给定的 `{SOURCE_DIR}` 与推导出的 `{SKILL_NAME}`（如来自用户输入直接复述即可）。
2. **运行范围与模式路由**：明确本次是「全流程 0→1→2→3→4」还是「仅阶段 0（质量预检）」，按用户触发话术判断。**路由硬要求**：用户表述为「全面 / 全流程 / 完整评测」时，必须执行至阶段 4，**全程不停顿**；只有用户明确只要预检，才可仅跑阶段 0——即便如此也须按 §阶段 0 交互闸门说明"仅预检"并给出继续命令。（见 When to Use / 单独调用阶段 0）。
3. **产物根目录**：告知输出落在 `{RESULTS_ROOT}/{SKILL_NAME}/`，并指出可被环境变量 `SKILL_EVALUATOR_RESULTS_ROOT` 整体重定向到自定义目录。
4. **开销预告**：提示阶段 2/3 会真实执行一批功能任务、阶段 4 会跑安全探测与代码 Grader 评审，可能消耗较多时间与 token；阶段 0 最轻量，建议先验 0 过关再上全流程（省时省钱）。

> 若用户未指定 `{SOURCE_DIR}`，**必须先问清路径**，不要臆测。

### B. 阶段级进度播报（每个阶段各两次）

进入任一阶段时，先发一条「阶段开始」播报；该阶段 DoD 验证完成后，再发一条「阶段完成」播报。不要在一开始把所有阶段一次性铺开，按"总览与阶段路线图"表顺序逐阶段推进。

**阶段开始播报**（统一格式）：

- 当前阶段编号与名称（如「▶ 阶段 1 / 样本生成」）
- 这一步做什么（一句话）
- 输入来自哪（引用产物路径，如 `{SAMPLES_DIR}`）
- 产物将写到哪（引用目标变量，如 `{BASELINE_DIR}`）

**阶段完成播报**（统一格式）：

- 该阶段 ✅ 完成 / ⚠️ 完成但存疑 / ❌ 未过门禁
- **进度**：已完成阶段序号 / 总阶段数（如「进度 2/5」）——让用户知道还有多少没跑
- 关键产物路径（让用户知道去哪看，见 C）
- 门禁 / 验证结论（退出码、`success` 字段、未过项数量）
- **下一步与命令**：接下来做什么，并给出可执行的具体命令（如 `--mode resume`）；若需用户确认，须**显式询问**
- **因故停下时（必答两项）**：① 用户该看哪个文件 / 哪段信息以判断原因；② 用户接下来要做什么。不得只说"停下了"

### C. 产物位置提示（贯穿全程）

每个阶段的完成播报里，**必须带该阶段产物的实际绝对路径**，不要只说"已生成"。路径以 `references/config.md` 的跨阶段输出路径变量为准：

| 阶段 | 关键产物 | 变量 / 路径 |
|------|----------|-------------|
| 0 | 质量评测报告 | `{QUALITY_REPORT}` = `…/quality/{SKILL_NAME}评测.md` |
| 0 | 评测计划 / 客观统计 | `{PF_EVAL_PLAN}` / `{PF_STATS}`（同 `quality/` 下） |
| 1 | 测试样本 | `{SAMPLES_DIR}` = `…/sample/` |
| 2 | 基线执行结果 | `{BASELINE_DIR}` = `…/exec/baseline/` |
| 3 | 带 skill 执行结果 | `{WITHSKILL_DIR}` = `…/exec/with_skill/` |
| 4 | 问题改进报告 / 评分报告 | `{SPEC_DIR}/problem_report.md`、`{SPEC_DIR}/benchmark_report.md` |

运行结束后，再给一份「全部产物清单」汇总，便于用户直接打开查看。**该清单须含两类**：① 最终交付物（质量评测报告 / `problem_report.md` / `benchmark_report.md`）；② **各阶段卡点的中间产物**（上表 0–4 各行），并附文件名与绝对路径。

> 中间产物是**流程逐级执行的证明**：最终报告是人消费的对象，但过程正确才是结果可信的基础。缺任一阶段卡点产物即表明流程未完整执行，**必须明示缺失项并判定未完成**，不得因最终报告存在而视为跑完。

### D. 门禁 / 验证不过：给用户可执行的下一步

某阶段门禁或 DoD 验证未过时，必须做到：

1. **明确结论**：指出哪个阶段、哪道门禁没过（如阶段 0 `validate_quality_report.py` 退出码非 0）。
2. **问题清单**：转述门禁 / 验证输出的具体问题项（缺字段、格式不符、客观事实锚点不符、计划残留 `[ ]` 等）。
3. **记录位置**：告知这些问题同样写进了对应产物文件（如 `{QUALITY_REPORT}` 的"关键问题汇总"），用户可打开细看。
4. **下一步动作**（分两类）：
   - **阶段 0 质量门禁未过**：属被测 skill 本身质量不达标 → 明确告诉用户**先改被测 skill**，再让本 agent 重跑阶段 0（或全流程）。强调"要改的是被测对象，不是本评测工具"。
   - **阶段 1–4 验证未过**：先定位是样本/执行/探测产物问题，还是评测脚本问题。若是被测 skill 行为导致（功能缺失、安全弱点暴露），属**正常评测结论**，应记录在报告中继续推进，而非中断；若确属评测流程异常（脚本报错、产物缺失），再向用户报告并停止。
5. **不要静默跳过门禁**：未过门禁不得擅自进入下一阶段（阶段 0 阻断全流程；1–4 的 DoD 见各 reference 文档尾部）。

### E. 场景适配：主动提示用户"现在能做什么"

根据用户的真实意图与当前进度，主动提示可选路径：

- **阶段 0 已跑完且通过**：按「阶段 0 交互闸门」**必须主动询问**是否继续 1–4（附 `{QUALITY_REPORT}` 绝对路径）；用户确认后 1–4 连续执行到底，不再中途征询。
- **全流程中途想暂停 / 续跑**：告知"前序阶段产物已落盘在 `…/skill-evaluator_results/{SKILL_NAME}/`，可直接从某阶段续跑，不必从头来"，并指明续跑起点对应哪份 reference 文档（如从阶段 3 续跑 → `references/stage3_withskill.md`）。
- **想重跑某阶段**：告知前序产物已存在时可直接重跑该阶段，并提醒对应的 Verification Checklist 在哪份文档。
- **想换输出位置**：提示用环境变量 `SKILL_EVALUATOR_RESULTS_ROOT` 覆盖，不动 skill 文件。
- **历史产物指标 / 评审缺失或损坏**：提示有 3 个手工维护脚本（`backfill_character_metrics.py` / `backfill_reviews.py` / `repair_durations.py`），使用场景与方法见 `references/USER_GUIDE.md#9. 手工维护脚本（可选，非流水线自动调用）`，按需由用户手动调用（流水线常规评测不自动调用）。

### F. 结束：交付汇总

全流程或阶段 0 正常结束后，给一份收尾播报：

- **本次运行范围**：跑了哪些阶段。
- **最终报告位置**：
  - 阶段 0 → `{QUALITY_REPORT}`
  - 全流程 → `{SPEC_DIR}/problem_report.md`（问题改进报告）+ `{SPEC_DIR}/benchmark_report.md`（基准评分报告）
- **一句话结论**：是否通过、主要风险 / 亮点。
- **安全覆盖披露（若发生抽取）**：阶段 1 若因探测预算上限（N=10）对相关 ASI 维度做过优先级抽取，必须转述**未评测的相关维度清单**与落选理由（来自 `samples_description.md`），并建议"优化已有问题后，对未覆盖维度补测再评"。
- **后续建议**：阶段 0 未过 → 改被测 skill 后重跑；若进入优化闭环 → 基于报告修被测 skill 再评。

## Common Pitfalls

- **跳过阶段 0 直接上全流程 0→4**：阶段 2/3 会真实执行一批功能任务、阶段 4 跑安全探测与代码 Grader，token 与时间消耗大。应先跑阶段 0 质量门禁，过关再上全流程（省时省钱）。
- **`{SOURCE_DIR}` 指错或非 skill 目录**：本工具所有路径解析以 `{SOURCE_DIR}` 为根；若指向普通代码仓库（缺 `SKILL.md`/`references`/`scripts` 结构），样本生成与评测都会失败。开始前务必与用户对齐路径。
- **用 `search_content` 检索 skill 安装目录时路径被忽略**：该工具默认作用域常落到工作区根而非传入的绝对路径，导致"改了 skill 却搜不到 / 搜到的是源仓库副本"。核对 skill 文件务必用 `read_file` 直接读取绝对路径。
- **跨阶段产物路径与 `references/config.md` 命名漂移**：脚本里的产物路径常量（如 `SPEC_REPORT`/`BASELINE_METRICS`）必须与 config.md 单一权威源一致，否则报告索引错乱。任何改名须到 config.md 与所有脚本同步。
- **阶段未过门禁仍强行续跑**：阶段 0 未过阻断全流程；1–4 的 DoD 验证未过须先定位是样本/执行/探测问题还是脚本异常，不得静默跳过门禁。

## Verification Checklist

- 阶段 0 `{QUALITY_REPORT}` 经 `validate_quality_report.py` 退出码 0 且 `success=true`（含评测计划无残留 `[ ]`）。
- 阶段 1 样本落 `{SAMPLES_DIR}`，common/hard 与安全探测数量由 manifest 派生（不写死）。
- 阶段 2/3 各自 `{BASELINE_DIR}`/`{WITHSKILL_DIR}` 含 `metrics.json` 与逐任务 `task_metrics.json`、`worklog.log`、时间戳，且 baseline≠withskill 差异项被样本阶段全选。
- 阶段 4 `{SPEC_DIR}` 产出 `Tasks.json`/`scores.json`/`Template.json`/`Template.csv`/`benchmark_report.md`/`problem_report.md`，且经 `validate_output.py` 结构校验通过。
- 全程 `{RUN_PLAN}` / `{EXEC_LOG}` 按计划推进并追加阶段小结，供中断续跑与自优化。

## References 索引

- `references/USER_GUIDE.md` — **使用者指南（人话版）**：这是什么 / 怎么触发 / 三份产物受众区分 / 怎么跑与读结果 / 手工维护脚本 / 目录结构 / 跨平台安装 / 常见问题
- `references/skill-evaluation-system.md` — **体系原理讲解（概念层）**：为什么体系化评测 / 四个角度 / 三大深度评测（可用性 · 性能 · 安全）原理 / AI 与程序双线协作 / 五类产物角度 / 可进化闭环 / 总概念图。**定位**：原理讲解**非实现规范**，冲突以 `SKILL.md` 与 `scripts/` 源码为准（原理文档不覆盖实现）；用户问"设计思路/原理"时提供（含概念图，适合阅读器打开）
- `references/config.md` — 跨阶段路径、变量、常量（含 `PF_*` / `QUALITY_REPORT`）
- `references/stage0_preflight.md` — 阶段 0 质量预检全流程
- `references/dependency_availability.md` — **可用性探测（DEP-AVAIL）执行规格**：D1–D6 checker + category 裁决 + 依赖提取器（DEP-EXTRACT）规则。**改动前置（仅本技能作用域）**：修改 `scripts/dep_probe.py` / `scripts/extract_deps.py` / `run_eval_pipeline.sh` 的阶段 0B 步骤前，必须先 `read_file` 本规格并与之保持一致，未读不得改探测行为。
- `references/stage1_sample.md` / `stage2_baseline.md` / `stage3_withskill.md` / `stage4_spec.md` — 阶段 1–4 流程
- `references/stage1_config.md` / `stage2_config.md` / `stage4_config.md` — 阶段专属常量
- `references/scope_contract.md` — **范围与安全契约**（授权模型：范围授权 vs 逐命令授权；越界才单独人话授权）
- `scripts/run_eval_pipeline.sh` — **单点评测管线 runner**（合并阶段 4 编排为一次授权，启动打印范围摘要）
- `references/exec_contract.md` / `sample_contract.md` / `spec_contract.md` — 各阶段基准合约
- `references/exec_common.md` — ExecAgent 共用执行细则
- `references/specs/` — **输出数据结构定义**（运行态技能文档；`.spec.md` 指数据结构说明，非开发态规格）
- `references/SafeTest/` — 安全测试知识库（6 维度 + OWASP Agentic Top 10）
- `assets/report.template.md` — 质量评测报告模板；`assets/Template.json` / `Template.csv` — 报告模板
- `scripts/` — 全部运行时脚本（开发/回归用脚本不在此目录）
