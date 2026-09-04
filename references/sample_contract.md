# SampleAgent 基准合约

> 来源：原 `references/benchmark_spec.md` SampleAgent 章节 + `references/benchmark_spec_detail.md` 第 2 节合并。

本文档定义 Stage 1（SampleAgent）的输出合约与样本结构规范。

路径定义：→ 见 `references/config.md`（唯一权威来源）。  

---

## 1. 样本产物包

> **权威结构定义**：下方目录树是 Stage 1 输出目录的**唯一权威结构**，从根目录一直展开到每个叶子文件。`workflow.md`「步骤 4」**引用本树，不得另行内联重定义**，以避免结构漂移。

阶段 1 的样本产物包保存在 `{SAMPLES_DIR}`（路径变量定义见 `references/config.md`、`references/stage1_config.md`）：

```
{SAMPLES_DIR}/
├── benchmark_manifest.json          # 清单文件 → §2 / benchmark_manifest.spec.md
├── samples_description.md           # 样本覆盖说明 → 步骤 6
├── timer.log                        # 计时日志 → 步骤 6
├── worklog.log                      # 工作日志 → 步骤 6
├── common/C_xx/                      # common 功能任务（数量动态，按差异项全选）
├── hard/H_xx/                        # hard 功能任务（数量动态，同 common）
└── security/{abnormal,permission,sensitive}/{probe_dirs}/   # 安全探测（数量动态，由 ASI 相关预扫描决定）
```

**每个 case 目录（common / hard / security 通用）的内部结构**（→ 详见 §3、§4、§5 与对应 `.spec.md`）：

```
{case_dir}/
├── TaskDescription.md               # → §4 / task_description.spec.md
├── WorkSpace/                       # 任务输入文件（步骤 4 创建，内容由步骤 2/3 设计决定）
└── Grader/                          # → §3、§5
    ├── grader_manifest.json         # → §5 / grader.spec.md「grader_manifest.json 结构」
    ├── run.py                       # 汇总运行器 → §5 / grader.spec.md「汇总运行器（run.py）合约」
    └── R1.py ~ R10.py               # 每个评分 ID 对应一个代码评分器 → §5 / grader.spec.md
```

> 任务 ID 编号（`C_01`~`C_nn`、`H_01`~`H_nn`，n 不固定）定义见 `references/stage1_config.md`（按实际数量顺序）。

## 2. 清单文件结构

> 字段级结构（顶层字段、`functional_tasks`/`security_probes` 条目、`outcome`/`output_contract`/`environment`/`verifier` 结构）的**唯一权威来源**为 `references/specs/benchmark_manifest.spec.md`，禁止在此内联重定义。

本阶段生成约束（spec 未覆盖的产出侧义务）：

- 所有路径字段均为相对于 `SAMPLES_DIR`（即 `{RESULTS_ROOT}/{SKILL_NAME}/sample/`，→ 见 `references/config.md`）的相对路径，禁止以容器目录名 `sample/` 开头——应写为 `common/C_01/...`，而非 `sample/common/C_01/...` 或 `{RESULTS_ROOT}/{SKILL_NAME}/sample/common/C_01/...`

## 3. 功能任务命名与目录合约

功能任务 ID 按实际数量顺序编号（数量动态，不再固定 8+4）：

- `common`：`C_01` 起顺序编号至实际 common 任务数
- `hard`：`H_01` 起顺序编号至实际 hard 任务数

> 任务 ID 编号规则定义见 `references/stage1_config.md`。

每个 case 目录的**完整内部结构**（含 `TaskDescription.md` / `WorkSpace/` / `Grader/` 及其内部的 `grader_manifest.json` / `run.py` / `R1.py`~`R10.py`）以本文 [§1 样本产物包](#1-样本产物包) 的目录树为唯一权威来源，此处不再重复定义。

## 4. TaskDescription.md 结构

> 章节规范与 Rubric 评分项约定（必需章节、`Outcome`/`Rubric` 原子性、`Output Contract`、`Environment`、`Grader Contract`、`Pass Policy` 等）的**唯一权威来源**为 `references/specs/task_description.spec.md`，禁止在此内联重定义。本阶段仅要求每个 `TaskDescription.md` 包含该规范列出的全部必需章节。

## 5. Outcome 评分与代码评分器合约

> Rubric 原子性/可评分性规则、评分项与代码评分器的映射约定 → 见 `references/specs/task_description.spec.md`；评分器输出 JSON 结构 → 见 `references/specs/grader.spec.md`（两者均为唯一权威来源，禁止在此内联重定义）。

评分阈值常量（如 `{RUBRIC_COUNT}`、`{RUBRIC_PASS_THRESHOLD}`）定义见 `references/config.md`。

> `Grader/` 目录的**完整内部结构**（`grader_manifest.json` / `run.py` / `R1.py`~`R10.py`）以 `references/specs/grader.spec.md`「目录结构」章节为**唯一权威来源**，禁止在此内联重定义；其字段结构、运行器合约、评分器输出格式分别见该 spec 对应章节（→ 见 §6）。

## 6. 评分器输出规范

每个评分器输出可解析 JSON，字段定义（含 `rubric_id`/`passed`/`score`/`reason`/`evidence`）及汇总运行器输出 `grading_result.json` 结构，唯一权威来源为 `references/specs/grader.spec.md`（「评分器输出格式」「grading_result.json 结构」章节）。

## 7. 清单记录字段

> 每条清单记录（`functional_tasks`/`security_probes` 条目）的 `outcome`/`output_contract`/`environment`/`verifier`/`unsupported_rules` 字段定义 → 见 `references/specs/benchmark_manifest.spec.md` 的 functional_tasks 条目结构（唯一权威来源，禁止在此内联重定义）。

## 8. 当前设计要求

当前设计方向为确定性验证：新任务和探测必须定义 Anthropic 风格的 `Outcome`，将模型输出转化为可解析证据，并通过一对一映射到评分 ID 的代码评分器进行审查。
