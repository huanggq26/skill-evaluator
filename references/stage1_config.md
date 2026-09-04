# SampleAgent 阶段配置

> 本文档定义 Stage 1（SampleAgent）专属的路径和常量。
> 跨阶段共享配置 → 见 `references/config.md`。

---

## Stage 1 任务计数（动态，不再固定 8+4）

> 功能任务数**不再固定 12（8 common + 4 hard）**。SampleAgent 在**设计时按「baseline ≠ with_skill 差异项全选」**组织候选任务池并过滤：仅保留预期 baseline 与 with_skill 行为有客观差异的任务；非差异候选任务丢弃。common / hard 为难度分层标签，其各自数量随技能实际能力边界浮动，不预设上限。

## Stage 1 任务 ID（编号按实际数量顺序）

| 常量 | 语义 |
|------|-----|
| `COMMON_TASK_IDS` | `C_01` 起顺序编号，直到 common 层实际任务数（`C_01`..`C_nn`，n 不固定） |
| `HARD_TASK_IDS` | `H_01` 起顺序编号，直到 hard 层实际任务数（`H_01`..`H_nn`，n 不固定） |

## Stage 1 输出路径

| 变量名 | 路径模板 | 说明 |
|--------|------|------|
| `SAMPLE_DESCRIPTION` | `{RESULTS_ROOT}/{SKILL_NAME}/sample/samples_description.md` | 样本覆盖说明 |

> 其余跨阶段路径变量（`SAMPLES_DIR`、`SAMPLE_COMMON_DIR` 等）定义见 `references/config.md`。
