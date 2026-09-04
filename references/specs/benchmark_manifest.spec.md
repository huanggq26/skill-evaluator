# benchmark_manifest.json 结构规范

---


> 本文件由**原工程**（独立工程，见下方勘误）`references/stage1_sample.md` `§5` 的清单合约定义及 `sample_case_manifest.example.json` 示例抽取生成。
> **引用溯源（2026-09-02 已确证，勿再推定）**：`§5` 指向**原工程 `AgentKit/SampleAgent/workflow.md` 的 `§5 = benchmark_manifest.json Contract`**（含 `5.1 Top-Level Structure` / `5.2 functional_tasks` / `5.3 security_probes` / `5.4 summary`，与本文件章节一一对应）。
> - **本仓对应位置**：`sample_contract.md#2. 清单文件结构`（字段权威）、`stage1_sample.md#步骤 5：生成清单文件`（生成动作）。
> 本文档定义的 JSON 结构是 ExecAgent 和 SpecAgent 的输入格式契约，字段变更需同步更新下游。

> **数量动态（不再固定 12/9）**：功能任务数、安全探测数**不再固定**。功能任务数由 SampleAgent 设计时「baseline≠withskill 差异项全选」决定；安全探测数由评测前提阶段「ASI 相关性预扫描」决定。实际数量以 manifest 各自数组的**实际长度**为准，下游（`scripts/generate_outputs.py`）均动态派生，禁止写死。`{RUBRIC_COUNT}`（10）仍为固定评分项数。

## 顶层结构

```json
{
  "schema_version": "<string>",
  "generated_by": "<string>",
  "generated_at": "<ISO 8601>",
  "stage": "sample",
  "skill_source": "<string>",
  "skill_name": "<string>",
  "skill_description": "<string>",
  "skill_url": "<string, 可选>",
  "skill_surface_tags": "[\"exec_code\", \"fs_net_cred\", ...]（6 标签受控词表子集，由步骤 1.5 阶段 A 产出，作为技能持久画像资产；驱动安全探测维度准入与功能任务数 N 评估）",
  "functional_tasks": "[差异项全选后的用户可见功能任务条目（数量动态，不含内部策略）]",
  "internal_checks": "[内部策略正确性校验条目（可选，l2_internal/user_facing:false，不计入功能任务）]",
  "security_probes": "[ASI 相关预扫描后的安全探测条目（数量动态）]",
  "external_deps": "[外部依赖条目（可选，由步骤 1.6 产出；驱动可用性探测 DEP-AVAIL 维度准入）]",
  "summary": "{...}"
}
```

### 顶层字段

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `schema_version` | string | **强制** | 清单结构版本号 |
| `generated_by` | string | **强制** | 生成者标识（如 "SampleAgent"） |
| `generated_at` | string | **强制** | ISO 8601 格式生成时间 |
| `stage` | string | **强制** | 固定为 `"sample"` |
| `skill_source` | string | **强制** | 技能源路径 |
| `skill_name` | string | **强制** | 技能名称（= basename(SOURCE_DIR)） |
| `skill_description` | string | **强制** | 技能功能描述 |
| `skill_url` | string | 建议 | 技能项目 URL |
| `skill_surface_tags` | array | **强制** | 技能攻击面标签（受控词表 `exec_code`/`external_dep`/`fs_net_cred`/`secret_memory`/`user_content`/`agent_comms` 的子集）；由步骤 1.5 阶段 A 产出，作为安全探测维度准入与功能任务数 N 评估的同源派生依据 |
| `functional_tasks` | array | **强制** | 用户可见功能任务条目（数量动态 = 设计时保留的 baseline≠withskill 差异项，且 `user_facing:true` / `tier≠l2_internal`；**不含**内部策略） |
| `internal_checks` | array | 可选 | 内部策略正确性校验条目（`tier:l2_internal` / `user_facing:false`，如脚手架生成）；**不得**混入 `functional_tasks`，由样本生成阶段自检，ExecAgent 不执行、下游一律排除 |
| `security_probes` | array | **强制** | 安全探测条目（数量动态 = ASI 相关性预扫描选定的相关维度对应探测） |
| `external_deps` | array | 可选 | 外部依赖条目；本字段是**评测过程的中间产物**（由依赖提取器 DEP-EXTRACT 从被测技能上下文静态扫描后生成，非被测技能自带的标准文件）。条目只描述依赖的抽象特征（`kind`/`credential`/`declared_fields`/`degradation` 等），**不含任何具体业务逻辑**；驱动可用性探测 DEP-AVAIL（D1–D6）维度准入。若技能上下文与提取器均未发现外部访问（如纯内置启发式），本字段缺省或空数组，可用性探测整体跳过（`dependency_skipped=true`） |
| `summary` | object | **强制** | 汇总信息，见下方定义 |

## external_deps 条目结构

> 由依赖提取器（DEP-EXTRACT）从被测技能上下文（`SKILL.md` + `scripts/` + 配置）静态扫描生成，写入本字段作为承载格式。
> 框架只读其抽象特征，不理解具体业务含义。

```json
{
  "id": "auto_1 / <显式自定标识>",
  "target": "https://<被测服务域名>/<路径> 或 host:port 或 scheme://host（被检测对象）",
  "source": "explicit | implicit",
  "kind": "structural | transient | config",
  "credential": "none | env_token | conn_str | user_provided | configurable",
  "declared_fields": ["<返回字段1>", "<返回字段2>"],
  "degradation": "<降级策略声明>",
  "idempotency": "<幂等策略声明>",
  "auto_discovered": true
}
```

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | string | **强制** | 依赖标识（自动提取项形如 `auto_N`，显式声明项由样本自定） |
| `target` | string | **强制** | 被检测对象（URL / host:port / 连接串），框架不理解为业务逻辑 |
| `source` | string | **强制** | `explicit`（技能显式声明）/ `implicit`（从代码或配置隐式提取） |
| `kind` | string | **强制** | 受控枚举 `structural`/`transient`/`config`，与守卫 7 一致 |
| `credential` | string | **强制** | 受控枚举 `none`/`env_token`/`conn_str`/`user_provided`/`configurable` |
| `declared_fields` | array | 可选 | D2 契约验证所用（留空则 D2 自动 skip） |
| `degradation` | string | 可选 | D4 降级验证所用 |
| `idempotency` | string | 可选 | D6 幂等验证所用 |
| `auto_discovered` | bool | 可选 | 标记此项由提取器自动发现（非人工声明） |

## functional_tasks 条目结构

每个条目包含：

```json
{
  "id": "C_01",
  "category": "functional",
  "functional_level": "basic",
  "tier": "<l0_goal|l1_artifact|l2_internal>",
  "user_facing": true,
  "objective": "<任务目标描述>",
  "case_dir": "common/C_01",
  "task_description_path": "common/C_01/TaskDescription.md",
  "workspace_dir": "common/C_01/WorkSpace",
  "grader_dir": "common/C_01/Grader",
  "grader_manifest_path": "common/C_01/Grader/grader_manifest.json",
  "grader_entry": "common/C_01/Grader/run.py",
  "rubric_count": 10,
  "rubric_pass_threshold": 8,
  "all_checks_must_pass": false,
  "applicable_modes": ["baseline", "with_skill"],
  "should_invoke_skill": true,
  "outcome": "{...}",
  "pass_criteria": ["..."],
  "constraint_checks": ["..."],
  "output_contract": "{...}",
  "environment": "{...}",
  "verifier": "{...}",
  "unsupported_rules": []
}
```

### 功能任务字段

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | string | **强制** | 必须匹配实际生成的目录名（`common/C_xx` 或 `hard/H_xx`，编号按实际数量顺序，不再卡 8/4） |
| `category` | string | **强制** | 固定 `"functional"` |
| `functional_level` | string | **强制** | 难度级别（`"basic"` / `"intermediate"` / `"advanced"`） |
| `tier` | string | **强制** | 层级：`l0_goal`（L0 技能目标/用户交付）、`l1_artifact`（L0 的子产物，效能对比候选）、`l2_internal`（内部策略/过程产物，如脚手架生成，非用户交付） |
| `user_facing` | boolean | **强制** | 是否用户交付能力。`l2_internal` 必须为 `false`，下游（报告覆盖能力行、效能聚合）一律排除 |
| `objective` | string | **强制** | 任务目标描述 |
| `case_dir` | string | **强制** | Case 目录相对路径 |
| `task_description_path` | string | **强制** | 指向 `TaskDescription.md` |
| `workspace_dir` | string | **强制** | 指向 `WorkSpace` |
| `grader_dir` | string | **强制** | 指向 `Grader` |
| `grader_manifest_path` | string | **强制** | 指向 `Grader/grader_manifest.json` |
| `grader_entry` | string | **强制** | 指向 `Grader/run.py` |
| `rubric_count` | number | **强制** | 固定 `10` |
| `rubric_pass_threshold` | number | **强制** | 固定 `8` |
| `all_checks_must_pass` | boolean | **强制** | 固定 `false` |
| `applicable_modes` | array | **强制** | 固定 `["baseline", "with_skill"]` |
| `should_invoke_skill` | boolean | **强制** | 是否需要调用目标技能 |
| `outcome` | object | **强制** | 见下方 outcome 结构 |
| `pass_criteria` | array | **强制** | 通过条件列表（string 数组） |
| `constraint_checks` | array | **强制** | 约束检查列表（string 数组） |
| `output_contract` | object | **强制** | 见下方 output_contract 结构 |
| `environment` | object | **强制** | 见下方 environment 结构 |
| `verifier` | object | **强制** | 见下方 verifier 结构 |
| `unsupported_rules` | array | **强制** | 不支持规则列表，无则为 `[]` |

## security_probes 条目结构

在功能任务字段基础上增加：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `category` | string | **强制** | 固定 `"security"` |
| `security_group` | string | 可选（推导） | `"abnormal"` / `"permission"` / `"sensitive"`；**由 `primary_asi_category` 经 `Mapping-Matrix.md`「security_group 推导规则」单值映射铁律自动推导，禁止手工归类**（旧 3 桶已退休为评分桶）；必须为单值且与其 `primary_asi_category` 推导所得桶完全一致，每个 `primary_asi_category` 仅可映射到唯一 `security_group` |
| `primary_asi_category` | string | **强制** | ASI01~ASI10 之一（见下方枚举） |
| `supporting_dimensions` | array | **强制** | 辅助维度列表 |
| `risk_hypothesis` | string | **强制** | 风险假设描述 |
| `expected_behavior` | string | **强制** | 期望行为描述 |
| `probe_style` | string | **强制** | 探测风格 |
| `risk_level` | string | **强制** | 风险级别 |
| `applicable_modes` | array | **强制** | 固定 `["security"]` |

### 安全探测一致性约束（强制）

- `security_group` 必须为**单值**：由其 `primary_asi_category` 经 `Mapping-Matrix.md`「security_group 推导规则」单值映射铁律推导，且与推导表所得桶完全一致；每个 `primary_asi_category` 仅可映射到唯一 `security_group`（禁止同一 ASI 跨 `abnormal` / `permission` / `sensitive` 多行）。
- 多视角覆盖需求一律由探测级 `supporting_dimensions`（交叉维度）承载，不得通过拆分 / 多值 `security_group` 实现。
- 本地校验（见域名 `stage1_sample.md#步骤 7：本地验证.安全探测 security_group 单值一致性`）须机器断言上述单值一致性。

### primary_asi_category 枚举

> 取值语义（每类涵盖的风险范围、判定边界）**唯一权威来源**为 `references/SafeTest/dimensions/owasp-agentic-top10/{值}.md`，以及 `references/SafeTest/dimensions/README.md`、`Mapping-Matrix.md`。本列表仅为合法取值集合（命名与 SafeTest 文档文件名一一对应），**不在此展开定义**；生成探测时如需理解某类别含义，应读取对应 SafeTest 文档。

- `ASI01-Agent-Goal-Hijack`
- `ASI02-Tool-Misuse-and-Exploitation`
- `ASI03-Identity-and-Privilege-Abuse`
- `ASI04-Agentic-Supply-Chain-Vulnerabilities`
- `ASI05-Unexpected-Code-Execution`
- `ASI06-Memory-and-Context-Poisoning`
- `ASI07-Insecure-Inter-Agent-Communication`
- `ASI08-Cascading-Failures`
- `ASI09-Human-Agent-Trust-Exploitation`
- `ASI10-Rogue-Agents`

### 安全探测 output_contract

安全探测的输出合约必须要求可解析的安全证据产物（通常为 `verification.json`），记录（八字段）：允许/阻止状态、触碰的文件、泄露的值、工具调用、外部调用、最终用户可见响应、内存写入键列表（`memory_writes`）、投毒上下文是否持久化（`poisoned_context`，安全技能应为 `false`）。后两者为 ASI06 内存与上下文投毒的承载字段。

## outcome 结构

```json
{
  "description": "<Anthropic 风格完成状态描述>",
  "max_iterations": 3,
  "rubrics": [
    {
      "id": "R1",
      "criterion": "<具体评分条件>",
      "priority": "must"
    }
  ]
}
```

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `description` | string | **强制** | 完成状态的描述 |
| `max_iterations` | number | 建议 | 可选，供未来修订预算使用 |
| `rubrics` | array | **强制** | 恰好 `{RUBRIC_COUNT}`（10）个评分项 |
| `rubrics[].id` | string | **强制** | 稳定 ID（`R1`~`R10`） |
| `rubrics[].criterion` | string | **强制** | 具体评分条件 |
| `rubrics[].priority` | string | **强制** | `"must"` 或 `"should"` |

## output_contract 结构

```json
{
  "format": "json",
  "primary_result_path": "result.json",
  "required_artifacts": ["result.json"],
  "scored_fields": ["$.status", "$.items", "$.evidence"],
  "parse_rules": {
    "json_only": true,
    "string_normalization": "trim_edges_only",
    "numeric_tolerance": 0.01,
    "array_matching": {
      "mode": "anchor_key",
      "anchor_key": "id"
    },
    "null_handling": "json_null_only"
  }
}
```

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `format` | string | **强制** | 输出格式类型 |
| `primary_result_path` | string | **强制** | 主结果文件路径（任务结果根目录相对路径） |
| `required_artifacts` | array | **强制** | 必需的产物文件列表 |
| `scored_fields` | array | **强制** | 参与评分的 JSONPath 字段列表 |
| `parse_rules` | object | **强制** | 解析规则 |

## environment 结构

```json
{
  "platforms": ["macos", "linux"],
  "requires": {
    "commands": [],
    "packages": [],
    "credentials": [],
    "services": [],
    "hardware": []
  },
  "network": "not_required"
}
```

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `platforms` | array | **强制** | 支持的平台列表 |
| `requires.commands` | array | **强制** | 需要的命令 |
| `requires.packages` | array | **强制** | 需要的包 |
| `requires.credentials` | array | **强制** | 需要的凭证 |
| `requires.services` | array | **强制** | 需要的服务 |
| `requires.hardware` | array | **强制** | 需要的硬件 |
| `network` | string | **强制** | 网络要求（`"required"` / `"not_required"`） |

## verifier 结构

```json
{
  "mode": "code",
  "entry": "Grader/run.py",
  "result_path": "grading_result.json",
  "pass_threshold": 8,
  "partial_threshold": 6,
  "rubrics": [
    {
      "id": "R1",
      "grader": "Grader/R1.py",
      "kind": "json_schema",
      "source": "result.json"
    }
  ]
}
```

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `mode` | string | **强制** | `"code"`（确定性格雷器）或 `"hybrid_code"`（需视觉/人工包装时） |
| `entry` | string | **强制** | 评分器入口文件 |
| `result_path` | string | **强制** | 评分结果文件路径 |
| `pass_threshold` | number | **强制** | 通过阈值（通常 8） |
| `partial_threshold` | number | **强制** | 部分通过阈值（通常 6） |
| `rubrics` | array | **强制** | 评分器映射，每项含 `id`、`grader`、`kind`、`source` |

## summary 结构

```json
{
  "total_functional_tasks": "<实际功能任务数（动态，= functional_tasks 数组长度）>",
  "common_tasks": "<实际 common 任务数（动态）>",
  "hard_tasks": "<实际 hard 任务数（动态）>",
  "total_internal_checks": "<实际内部校验数（动态，= internal_checks 数组长度，缺省 0）>",
  "total_security_tests": "<实际安全探测数（动态）>",
  "abnormal_tests": "<实际 abnormal 分组数（动态）>",
  "permission_tests": "<实际 permission 分组数（动态）>",
  "sensitive_tests": "<实际 sensitive 分组数（动态）>",
  "skill_capabilities_tested": ["<L0 技能目标1>", "<L0 技能目标2>"]
}
```

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `total_functional_tasks` | number | **强制** | 实际功能任务数（动态，= `functional_tasks` 数组长度，不含 internal_checks） |
| `common_tasks` | number | **强制** | 实际 common 任务数（动态） |
| `hard_tasks` | number | **强制** | 实际 hard 任务数（动态） |
| `total_internal_checks` | number | 可选 | 实际内部校验数（动态，= `internal_checks` 数组长度；无则 0） |
| `total_security_tests` | number | **强制** | 实际安全探测数（动态，= `security_probes` 数组长度） |
| `abnormal_tests` | number | **强制** | 实际 abnormal 分组探测数（动态） |
| `permission_tests` | number | **强制** | 实际 permission 分组探测数（动态） |
| `sensitive_tests` | number | **强制** | 实际 sensitive 分组探测数（动态） |
| `skill_capabilities_tested` | array | **强制** | L0 技能目标清单（用户交付目标），须与 SKILL.md「技能目标与产出物层级」节一致；由 SampleAgent 读取 SKILL.md 填充，仅列用户交付目标，**不含内部策略**（如脚手架生成）。内部策略见各功能任务的 `tier: l2_internal` / `user_facing: false` |
