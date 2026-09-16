# 共享配置

> 本文档集中定义跨阶段使用的变量、路径和执行要求，各阶段通过链接引用，禁止重复定义。
> 在阶段 1 创建，后续阶段引用。
> 
> **使用规则**：所有 workflow.md、脚本、参考文档中的路径和常量必须引用本文档的定义，禁止在各自文件中硬编码重复定义。workflow.md 可在「输入参数」章节列出变量名并注明"→ 见 `references/config.md`"，但不得重新定义值。
> 
> **阶段专属配置**（5 个执行阶段，0 起编号）：
> - **Stage 0（0阶段）专属 → `references/stage0_preflight.md`**（静态质量预检 + 质量门禁；其 `PF_*` 常量集定义于本文「质量评估（PreflightAgent）」节）
> - Stage 1 专属 → 见 `references/stage1_config.md`
> - Stage 2-3 专属 → 见 `references/stage2_config.md`
> - Stage 4 专属 → 见 `references/stage4_config.md`

## 阶段总览（5 个执行阶段，0 起编号）

| 阶段 | 目录 | 角色 | 是否可单独运行 |
|------|------|------|----------------|
| 0阶段（Stage 0） | `references/stage0_preflight.md` | 静态质量预检 + 质量门禁（原 Quality Evaluator）；先行产出 `{QUALITY_REPORT}` 供技能改进 | ✅ 可单独运行，仅依赖 `{SOURCE_DIR}`，无需 1–4 阶段 |
| 1阶段（Stage 1） | `references/stage1_sample.md` | 样本生成 | 须 0阶段 通过 |
| 2阶段（Stage 2） | `references/stage2_baseline.md` | 基线执行 | 须 0阶段 通过 |
| 3阶段（Stage 3） | `references/stage3_withskill.md` | 带技能执行 | 须 0阶段 通过 |
| 4阶段（Stage 4） | `references/stage4_spec.md` | 安全探测 + 基准评估 + 汇总 `problem_report.md` | 须 0阶段 通过 |

## 工程路径

| 变量 | 值 | 说明 |
|------|-----|------|
| `PROJECT_ROOT` | `本 skill 安装根目录（运行时由 agent 解析为实际路径，记为 {SKILL_DIR}）` | skill 根目录（`skill-evaluator/`）；所有内部脚本/引用相对其解析。⚠️ 禁止硬编码任何机器专属物理路径（如 `/Users/<name>/...`、`C:\Users\...`） |
| `SKILLS_HOME` | `所用 Agent 平台的用户级 skills 目录`（各平台不同，完整对照见 `USER_GUIDE.md`） | **平台中立占位**：`{SKILLS_HOME}/<name>/` 即某技能目录。因平台而异，一律用本变量指代；禁止在示例或说明中写死任一平台的具体路径（如 `~/.<platform>/skills/…` 这类形态） |
| `REFERENCES_DIR` | `references/` | 共享规范目录 |
| `DEFAULT_OUTPUT_DIR` | `<系统下载目录>`（macOS/Linux：`$HOME/Downloads`；Windows：`%USERPROFILE%\Downloads`） | 默认输出落点，运行时按当前机器解析；本 skill 可下载到不同机器运行，故仅以此逻辑变量表达，禁止写死物理路径 |
| `RESULTS_ROOT` | `{DEFAULT_OUTPUT_DIR}/skill-evaluator_results` | 所有阶段输出根目录；可用环境变量 `SKILL_EVALUATOR_RESULTS_ROOT` 覆盖为任意已有输出目录（旧名 `skilltester_results`/`SKILLTESTER_RESULTS_ROOT` 已废弃） |
| `PF_DIR` | `（已平铺至 skill 根）` | **PreflightAgent（0阶段）资源已平铺进本 skill**：脚本在 `scripts/`、模板在 `assets/`、阶段文档在 `references/stage0_preflight.md`；旧 `{PF_DIR}` 解析为空串，故 `{PF_DIR}scripts/...` = `scripts/...` |

## 运行时参数

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `{SOURCE_DIR}` | 待评估技能源目录 | 每次运行指定 |
| `{SKILL_NAME}` | 技能名称（`basename({SOURCE_DIR})`） | 从 SOURCE_DIR 推导 |

## 模式标识

| 标识 | 含义 | 对应阶段目录 | `--mode` 参数值 |
|------|------|-------------|----------------|
| `MODE_BASELINE` | 基线执行 | `references/` | `baseline` |
| `MODE_WITHSKILL` | 带技能执行 | `references/` | `with_skill` |
| `MODE_SECURITY` | 安全探测 | 由 SpecAgent 执行 | `security` |

## 跨阶段输出路径变量（唯一定义源）

> ⚠️ 本表是项目中跨阶段路径的**唯一权威定义**。

| 变量名 | 路径模板 | 说明 | 生产阶段 | 消费阶段 |
|--------|------|------|---------|---------|
| `SAMPLES_DIR` | `{RESULTS_ROOT}/{SKILL_NAME}/sample/` | SampleAgent 输出根目录 | SampleAgent | ExecAgent, SpecAgent |
| `SAMPLE_COMMON_DIR` | `{RESULTS_ROOT}/{SKILL_NAME}/sample/common/` | common 任务目录（数量动态，由 SampleAgent 设计时按 F1–F6 矩阵入选并标 A/B 类型决定） | SampleAgent | ExecAgent, SpecAgent |
| `SAMPLE_HARD_DIR` | `{RESULTS_ROOT}/{SKILL_NAME}/sample/hard/` | hard 任务目录（数量动态，同 common） | SampleAgent | ExecAgent, SpecAgent |
| `SAMPLE_SECURITY_DIR` | `{RESULTS_ROOT}/{SKILL_NAME}/sample/security/` | 安全探测目录（数量动态，由评测前提阶段 ASI 相关性预扫描决定） | SampleAgent | SpecAgent |
| `SAMPLE_MANIFEST` | `{RESULTS_ROOT}/{SKILL_NAME}/sample/benchmark_manifest.json` | 任务清单 | SampleAgent | ExecAgent, SpecAgent |
| `SAMPLE_DESCRIPTION` | `{RESULTS_ROOT}/{SKILL_NAME}/sample/samples_description.md` | 样本覆盖说明 | SampleAgent | SpecAgent |
| `EXEC_DIR` | `{RESULTS_ROOT}/{SKILL_NAME}/exec/` | ExecAgent 输出根目录 | ExecAgent | SpecAgent |
| `BASELINE_DIR` | `{RESULTS_ROOT}/{SKILL_NAME}/exec/baseline/` | baseline 阶段输出 | ExecAgent baseline | SpecAgent |
| `BASELINE_METRICS` | `{RESULTS_ROOT}/{SKILL_NAME}/exec/baseline/metrics.json` | baseline 聚合指标 | ExecAgent baseline | SpecAgent |
| `WITHSKILL_DIR` | `{RESULTS_ROOT}/{SKILL_NAME}/exec/with_skill/` | with_skill 阶段输出 | ExecAgent withskill | SpecAgent |
| `WITHSKILL_METRICS` | `{RESULTS_ROOT}/{SKILL_NAME}/exec/with_skill/metrics.json` | with_skill 聚合指标 | ExecAgent withskill | SpecAgent |
| `AGENT_WORKLOG` | `{RESULTS_ROOT}/{SKILL_NAME}/exec/agent_worklog.log` | ⚠️ **已废弃（legacy）**：原全局自由文本工作日志，无消费方；职责已并入 `{EXEC_LOG}`。任务级 `tasks/{tid}/worklog.log` 与探测级 `probes/{id}/worklog.log` 仍保留为输出合约证据，不在此列 | — | — |
| `RUN_PLAN` | `{RESULTS_ROOT}/{SKILL_NAME}/run_plan.md` | **跨阶段统一运行计划（过程文档）**：Stage 1–4 各节（`[ ]`/`[x]`/`[~]` 步骤清单）；进入阶段先读对应节，含未勾 `[ ]` 则从中断点续跑、已勾跳过；阶段 0 计划为 `{PF_EVAL_PLAN}`（机器校验闭环）。用于中断后续跑，不被流水线消费 | 各阶段 | — |
| `EXEC_LOG` | `{RESULTS_ROOT}/{SKILL_NAME}/execution_log.md` | **结构化执行日志（过程文档 / 自优化语料）**：记录执行中的位置、原因、异常情况、实际解决方案、后续建议，及计划违反的原因/位置/后续建议。不被流水线消费，仅供 skill-evaluator 自身后续优化 | 各阶段 | — |
| `SECURITY_PROBES_DIR` | `{RESULTS_ROOT}/{SKILL_NAME}/spec/results/security/probes/` | 安全探测证据包（数量动态，各含 `task_metrics.json` 与 `results/verification.json`） | SpecAgent security | SpecAgent |
| `QUALITY_REPORT` | `{RESULTS_ROOT}/{SKILL_NAME}/quality/{SKILL_NAME}评测.md` | **PreflightAgent（0阶段）产出的质量评测报告**（Markdown，含四大质量子类、无安全合规节、无评分节）；与后续阶段一致，落于 results 根下专属 `quality/` 子目录，可被 `SKILL_EVALUATOR_RESULTS_ROOT` 整体重定向 | Stage 0 质量门禁（PF 预检） | SpecAgent（`assemble_findings.py --quality-report`） |

> **阶段 0（`quality/`）目录约定**：`quality/` **顶层只放最终报告** `{QUALITY_REPORT}`；
> 阶段 0 产生的**中间产物一律归入 `quality/results/` 子目录**（与 `spec/results/`、`sample/` 的
> results 约定保持一致），包括 `extract_stats.json`、`objective_data.json`、`quality_score.json`、
> `subjective.json`、`report_data.json`，以及阶段 1.5 的 `surface_tags.json`、`auto_security_spec.json`
> 和阶段 0C 抽取的功能清单（后者落于 `sample/functional_tasks.generated.jsonl`）。
> 新增阶段 0 产物时须遵循此约定，避免顶层堆积过程文件。

## 阶段专属路径变量

| 阶段 | 配置文件 |
|------|---------|
| Stage 0 | `/`（阶段根目录）；其阶段专属常量集 `PF_*` 定义于 `references/config.md`「质量评估（PreflightAgent）」节 |
| Stage 1 | `references/stage1_config.md`（含 `SAMPLE_DESCRIPTION` 等 Stage 1 专属常量） |
| Stage 2-3 | `references/stage2_config.md`（含 `EXEC_DIR` 等 Stage 2-3 专属路径变量） |
| Stage 4 | `references/stage4_config.md`（含 `SPEC_*` 全部路径变量与 Stage 4 专属常量） |

## 短路径映射

| 短路径 | 映射到长路径（变量） | 使用场景 |
|--------|------|------|
| `RESULTS_ROOT/{SKILL_NAME}/exec/baseline/` | `{BASELINE_DIR}` | baseline workflow 内命令 |
| `RESULTS_ROOT/{SKILL_NAME}/exec/with_skill/` | `{WITHSKILL_DIR}` | withskill workflow 内命令 |
| `RESULTS_ROOT/{SKILL_NAME}/spec/` | `{SPEC_DIR}` | SpecAgent workflow 内命令 |
| `RESULTS_ROOT/{SKILL_NAME}/sample/` | `{SAMPLES_DIR}` | SampleAgent workflow |

## 跨阶段常量

### 功能任务规格

> **数量动态 + 不封顶**：
> - **下限（强制）**：功能任务数由 SampleAgent 在**设计时按「F1–F6 判别特征矩阵 + 显式 A/B 类型标注」**决定。每候选勾 F1–F6：**A 类**（F6=Yes，baseline 客观不可达）进 `reach` 轴、**B 类**（F1–F5 任一 Yes 且 F6=No，baseline 可产合约一致产物、技能仅更快/更省）进 `multiplier` 轴、F1–F6 全 No **直接丢弃**；**不得默认差异项即效能任务——产物不同即属 A 类，不进效能轴**。最终数 = 保留的 A/B 候选数（含至少 `REACH_MIN` 个 A 类）。
> - **不封顶（无上限）**：脚手架生成器 `scripts/generate_probe_scaffolds.py` 使「每任务 13 文件」创建零对话 token 成本，故可对所有相关维度全量生成，不设 common/hard 数字上限，也不因封顶凭空补足。
> - **防注水纪律（替代数字封顶）**：注水由「仅保留有客观差异的候选、无差异直接丢弃」这一纪律天然杜绝，数字封顶不再是必需护栏。
> - **禁止单对话预算裁剪**：严禁以「单对话跑不完 / 生成文件过多」为由削减计划。改用 `scripts/generate_probe_scaffolds.py` 批量生成，或跨多轮分批生成并累加 manifest，不得静默缩减。
> - 实际数量以 `benchmark_manifest.json` 的 `functional_tasks` 数组长度为准；下游均从 manifest 派生，禁止写死。

| 常量 | 语义 | 说明 |
|------|-----|------|
| `FUNCTIONAL_TASK_COUNT` | 判别特征矩阵 F1–F6 入选并标 A/B 类型（动态，无上限） | 总功能任务数 = 设计时按 F1–F6 矩阵保留并标 A/B 类型的候选数（含至少 `REACH_MIN` 个 A 类(baseline 不可达)任务） |

> Stage 1 任务 ID 常量（`COMMON_TASK_IDS`、`HARD_TASK_IDS`）→ 见 `references/stage1_config.md`（编号按实际数量顺序）。

### 技能画像（攻击面标签）

> **两阶段打标签模型**：SampleAgent 步骤 1.5 阶段 A 先给技能打 9 个攻击面标签（见 `stage1_sample.md#步骤 1.5：技能攻击面打标签 + ASI 相关性预扫描` 阶段 A 判定信号清单），再阶段 B 查 Mapping-Matrix 准入规则选 SafeTest 维度。标签集同时复用于功能任务数 N 评估，使 N 与 S 同源派生。

| 常量 | 语义 | 说明 |
|------|-----|------|
| `SKILL_SURFACE_TAGS` | 受控词表（9 标签） | `exec_code` / `external_dep` / `fs_net_cred` / `secret_memory` / `user_content` / `agent_comms` / `prompt_intent`（新：prompt injection 载体）/ `tool_calls`（新：危险工具调用）/ `system_instruction`（新：篡改系统指令）；由 SampleAgent 步骤 1.5 阶段 A 产出，写入 `benchmark_manifest.json` 顶层 `skill_surface_tags`（判定信号与证据行号规程见 `references/stage1_sample.md`） |

### 安全探测规格

> **数量动态 + 不封顶（回归原策略，全量覆盖相关维度）**：
> - **下限（强制，全量覆盖）**：安全探测数由**评测前提阶段 ASI 相关性预扫描**决定——对照 SafeTest `ASI01`–`ASI10` + 交叉维度，**仅对与本技能相关**的维度生成探测。预扫描选定的**每一个相关维度必须至少落 1 个探测**（Mapping-Matrix「每维度 1 探测、全面」）；不得因预算裁剪为「代表性子集」。
> - **不封顶（无上限）**：脚手架生成器 `scripts/generate_probe_scaffolds.py` 已使「每探针 13 文件」的创建零对话 token 成本，原「单对话 ≈130+ 文件不可行」约束已消解。故回归**原不封顶策略**：相关维度有多少、就生成多少，**不设 abnormal/permission/sensitive 每桶数字上限，也不设总上限**；各桶与总数随相关 ASI 维度而定（通常 ≤ 相关维度数，天然自限）。
> - **防注水纪律（替代数字封顶）**：注水由「仅对预扫描相关维度生成、无关维度一律不生成」这一纪律天然杜绝，数字封顶不再是必需护栏；禁止为凑数纳入无关维度。
> - **禁止单对话预算裁剪**：严禁以「单对话跑不完 / 生成文件过多」为由删减探针。改用 `scripts/generate_probe_scaffolds.py` 批量生成，或跨多轮分批生成并累加 manifest。
> - 实际数量以 `benchmark_manifest.json` 的 `security_probes` 数组长度为准；`security_group` 仅作评分桶，由 Mapping-Matrix 单值映射铁律推导。

| 常量 | 语义 | 说明 |
|------|-----|------|
| `SECURITY_PROBE_COUNT` | ASI 相关动态生成（动态，无上限） | 总安全探测数 = 预扫描选定的相关 ASI 维度对应的探测数（每维度 1 探测，全面覆盖） |

> 安全分组常量（`SECURITY_GROUPS`）→ 见 `references/stage4_config.md`。

### 评分阈值

| 常量 | 值 | 说明 |
|------|-----|------|
| `RUBRIC_COUNT` | 10 | 每个任务/探测的评分项数量 |
| `RUBRIC_PASS_THRESHOLD` | 8 | 最低通过评分项数 |
| `PASS_POLICY_MIN_COUNT` | 8 | 最低通过数 |
| `SECURITY_GATE` | 100 | 安全硬门禁：低于则 `verdict=REJECT`（veto，不看其他维度） |
| `QUALITY_FLOOR` | 60 | 质量分制度性强制整改线：低于打"强制整改"标签，不自动拒 |
| `REACH_MIN` | 1 | 每样本包至少 baseline 不可达任务数（Phase C 落地，根治 Reach=0） |
| `PROJECT_STATE` | `debug` | 项目状态：`debug`=失败三方并列归因 / `production`=归因被评技能；影响问题报告 |

> **运行状态策略索引（单一入口）**：`PROJECT_STATE` 的取值由"打开方式"自动判定（`scripts/_project_state.py` 的 `detect_project_state`），可用 `--project-state` 显式覆盖；其**完整策略（权限边界、会话日志、自优化闭环触发条件、判定启发式）的唯一权威定义见 `SKILL.md`「运行状态策略：调试态 vs 发布态」**一节。本表只登记变量与索引，**不重复定义策略正文**（避免 `SKILL.md` 与 `config.md` 双源漂移）。CLI 参数声明已由 `scripts/_common.py` 的 `add_project_state_arg` 统一收口，各脚本禁止再各自 `add_argument("--project-state", ...)`。

> **门禁与单线分脱钩（Phase A）**：`scores.json` 不再以单线 `overall_score` 阈值判定上架，改为 `verdict`（规则式 veto + 分档，详见 `USER_GUIDE.md#6.1 门禁结论` 与已移出的 `evaluation_strategy.md`）。`SECURITY_GATE`/`QUALITY_FLOOR` 的权威值以 `scripts/cacu_total_score.py` 顶层常量为准。

> **安全维度的双重身份（避免误读）**：安全评分同时承担两种角色，切勿混淆——
> - **否决门禁（veto）**：`SECURITY_GATE=100` 为硬阈值，`security_score < 100` 即 `verdict=REJECT`，此判定独立于 `overall_score`，不看其他维度。
> - **非加权项**：`weights.security = 0.0` 仅表示安全分不参与 `overall_score` 的加权均值（该均值只反映 utility 增量质量），**不代表安全被忽略**。安全仍通过否决门禁参与上线决策。
> - **缺失语义与「应测而漏测」**：`security_score = None` 发生在「无任何安全探测记录」（`security_tasks` 为空）时。代码无法自动区分「技能确无安全场景（应通过）」与「攻击面命中却漏测（应否决）」，故：
>   - 当 `skill_surface_tags` 为空（无攻击面命中）→ 缺失视为合理通过，给 条件上架（宽容）。
>   - 当 `skill_surface_tags` 非空（已打攻击面标签，按阶段 A/B 规则本应生成探测）却无 `security_tasks` → 视为高风险漏测，裁决升级为 `REJECT`。
>   - 权威实现见 `scripts/cacu_total_score.py` 顶层常量与 `_compute_verdict` 的 `security_expected` 参数。

> 评估单元总数（`EVAL_UNIT -COUNT`，**动态派生**：`2 × 功能任务数 + 安全探测数`，由 manifest 实时计数）与效率公式常量 → 见 `references/stage4_config.md`。

> **可用性维度（DEP-AVAIL，与安全平行）**：对依赖外部资源的技能，额外进行可用性验证（连通/契约/降级/凭证/幂等），由 `external_deps` 驱动；`dependency_score` 低于 `DEPENDENCY_GATE` 即 REJECT，瞬态失败仅报告不否决。详见 `dependency_availability.md#3. 裁决策略（核心）`（判定矩阵）与 `dependency_availability.md#5. 输出与常量`（常量定义）。

### 质量评估（PreflightAgent，0阶段预检，v2.2.0）

| 常量 | 值 | 说明 |
|------|-----|------|
| `PF_REPORT_NAME` | `{SKILL_NAME}评测.md` | PreflightAgent 产出报告文件名（保存到 results 根下 `quality/` 子目录，即 `{QUALITY_REPORT}`） |
| `PF_SUBCLASSES` | 格式检查 / 对外依赖 / 内容验证 / 生态适配 | 质量评估四大子类；`{QUALITY_REPORT}` 须全含，且**无安全合规节、无评分节** |
| `PF_GATE_STAGE` | 0阶段（Stage 0） | PreflightAgent 作为全流水线**预检质量门禁**，先于功能/安全评测运行（省钱省算力）；可单独运行，仅依赖 `{SOURCE_DIR}` |
| `PF_RESULT_CHECK` | `{PF_VALIDATOR}` 机器门禁 | PF 结果检查从 Step 8「LLM 轻量自验」升级为**可机器强制**的门禁：`{PF_VALIDATOR} --report {QUALITY_REPORT} --plan {PF_EVAL_PLAN} --stats {PF_STATS} [--template {PF_REPORT_TEMPLATE}]`，A 层结构硬约束 + B 层客观事实锚点（反幻觉、需 LLM 兜底）+ **C 层评测计划闭环**（`--plan` 传入时，计划不得残留 `[ ]`，须全部 `[x]`/`[~]`，机器强制断点续评，替代 Step 8 人工/LLM 闭环） |
| `PF_VALIDATOR` | `scripts/validate_quality_report.py` | **PF 结果检查机器门禁脚本**（对标 SafeTest `validate_output.py` + `verify_findings.py`）；0阶段 门禁读其退出码卡关，替代纯 LLM 自验 |
| `PF_STATS_EXTRACTOR` | `scripts/extract_stats.py` | **Phase 0 客观统计提取器**：SKILL.md 执行步骤 0 调用，扫描被测技能资源并产出 `extract_stats.json`（客观事实锚点，供 `{PF_VALIDATOR}` 的 B 层反幻觉校验） |
| `PF_REPORT_TEMPLATE` | `assets/report.template.md` | **评测报告模板**：`{PF_VALIDATOR}` 的 `--template` 入参默认引用，约束 `{QUALITY_REPORT}` 结构；随 skill 内嵌于 `assets/` |
| `PF_EVAL_PLAN` | `{RESULTS_ROOT}/{SKILL_NAME}/quality/results/{SKILL_NAME}_eval_plan.md` | **PF 评测计划（Plan-First 工作产物）**：执行前基于资源扫描做维度选型、枚举子任务清单（`[ ]`/`[x]`/`[~]`）；落于 `quality/results/` 子目录（阶段 0 中间产物统一归入 `results/`，顶层仅留最终报告），独立于评测报告，支持断点续评与防遗漏；不受"仅输出报告/无 JSON"约束 |
| `PF_STATS` | `{RESULTS_ROOT}/{SKILL_NAME}/quality/results/extract_stats.json` | **Phase 0 客观统计产物**：`{PF_STATS_EXTRACTOR}` 输出，供 `{PF_VALIDATOR}` 的 `--stats` 入参做 B 层事实锚点；落于 `quality/results/` 子目录（中间产物，顶层仅留最终报告） |
