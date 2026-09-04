# ExecAgent 基准合约

> 来源：原 `references/benchmark_spec.md` ExecAgent 章节 + `references/benchmark_spec_detail.md` 第 3-8 节合并。

本文档定义 Stage 2-3（ExecAgent baseline / withskill）的执行合约与证据规范。

输出目录结构：→ 见本文 [§0 完整输出目录树（权威定义）](#0-完整输出目录树权威定义)（唯一权威结构来源）。  
路径定义：→ 见 `references/config.md`（唯一权威来源）。  

---

## 0. 完整输出目录树（权威定义）

> **权威结构定义**：下方目录树是 Stage 2-3（ExecAgent baseline / withskill）输出目录的**唯一权威结构**，从根目录一直展开到每个叶子文件。`baseline/workflow.md` / `withskill/workflow.md` 的「输出文件清单」均**引用本树，不得另行内联重定义**，以避免结构漂移。

```text
{EXEC_DIR}/
├── agent_worklog.log                          # 全局执行工作日志（跨阶段追加）→ 步骤 0 + 收尾
├── baseline/                                   → {BASELINE_DIR}
│   ├── stage_start_timestamp.json             # 阶段开始时间戳 → 步骤 1 / timestamp.spec.md
│   ├── metrics.json                           # 阶段聚合指标 → 步骤 3 / metrics.spec.md
│   └── tasks/{task_id}/                        # 每功能任务（编号按实际数量，common C_xx / hard H_xx）
│       ├── results/                            # 任务产出物（output_contract 主结果）
│       ├── task_metrics.json                   # 任务指标 → 步骤 2b / task_metrics.spec.md
│       ├── worklog.log                         # 任务级日志 → 步骤 2f
│       ├── start_timestamp.json                # 任务开始时间戳 → 步骤 2a / timestamp.spec.md
│       └── end_timestamp.json                  # 任务结束时间戳 → 步骤 2d / timestamp.spec.md
└── with_skill/                                 → {WITHSKILL_DIR}
    ├── stage_start_timestamp.json             # 阶段开始时间戳 → 步骤 1 / timestamp.spec.md
    ├── metrics.json                           # 阶段聚合指标 → 步骤 3 / metrics.spec.md
    └── tasks/{task_id}/                        # 结构同 baseline（task_metrics.json 含 skill 调用字段）
        ├── results/
        ├── task_metrics.json
        ├── worklog.log
        ├── start_timestamp.json
        └── end_timestamp.json
```

> 安全探测的产物包结构与功能任务完全一致（仅目录位于 SpecAgent 的 `{SPEC_SECURITY_DIR}probes/{probe_id}/`，由 SpecAgent 阶段执行），详见 `references/spec_contract.md`「§0 完整输出目录树（权威定义）」。

---

## 1. ExecAgent 基本规则

- 每次启动仅处理一个 `{SOURCE_DIR}`
- 禁止跨多技能的批量 Exec 启动
- ExecAgent 拆分为两次启动：`baseline` 和 `with_skill`
- 两个 Exec 阶段可并行或串行运行
- 每个阶段内部禁止任务级并发
- 每个功能任务拥有独立目录 `skill-evaluator_results/<skill-name>/exec/<mode>/tasks/{task_id}/`（`<mode>` 取 `baseline` 或 `with_skill`，分别对应 `{BASELINE_DIR}` / `{WITHSKILL_DIR}`，→ 见 `references/config.md`）
- 安全探测由 `SpecAgent` 稍后执行
- 所有安全测试指导位于 `references/SafeTest/`

## 2. 功能任务隔离

- `baseline` 和 `with_skill` 两个阶段使用独立代码终端
- 每个任务有自己独立的目录
- 一个任务必须完全结束才能开始下一个
- 禁止在同一阶段终端内进行后台、异步、并行或交错的任务执行
- 禁止用阶段级摘要代替任务级证据

### 规范任务产物包

每个功能任务的产物包结构（含 `results/`、`task_metrics.json`、`worklog.log`、`start_timestamp.json`、`end_timestamp.json`）以本文 [§0 完整输出目录树（权威定义）](#0-完整输出目录树权威定义) 为唯一权威来源，此处不再重复定义。

## 3. 安全探测隔离

安全探测由 SpecAgent 在 Spec 阶段开始时执行，使用与功能任务相同的产物包模式（结构以 `references/spec_contract.md`「§0 完整输出目录树（权威定义）」为权威来源，此处不再重复定义）。

安全分类和审查指导来源：`references/SafeTest/`

## 4. 阶段级输出

每个 ExecAgent 阶段额外输出一个汇总文件：

- `{RESULTS_ROOT}/{SKILL_NAME}/exec/baseline/metrics.json` → `{BASELINE_METRICS}`
- `{RESULTS_ROOT}/{SKILL_NAME}/exec/with_skill/metrics.json` → `{WITHSKILL_METRICS}`

## 5. JSON 骨架规则

JSON 文件不能手工从头编写。必需的生成流程：

1. 调用 `generate_task_metrics.py` 创建每个 `task_metrics.json` 骨架 → 由当前阶段回填真实字段
2. 调用 `generate_stage_metrics.py` 创建阶段 `metrics.json` 骨架 → 由当前阶段回填汇总字段
3. 任务开始前，调用 `write_system_timestamp.py` 创建 `start_timestamp.json`
4. 任务最后一步，调用 `write_system_timestamp.py` 创建 `end_timestamp.json`
5. 两个时间戳文件存在后，调用 `calculate_timestamp_diff.py` 并回填 `time` 和 `total_time_seconds`

> 脚本均位于 `references/`，路径与角色见上方列表。

禁止行为：手写 `end_timestamp.json` 和 `start_timestamp.json`，纯文本时间戳字符串为非法格式。

## 6. 任务指标字段约定

> 每个 `task_metrics.json` 的**完整字段集、类型与约束**以 `references/specs/task_metrics.spec.md`「字段定义」为**唯一权威来源**（含 `baseline` / `with_skill` / `security` 三模式各自的强制字段与额外字段），此处不内联重定义；三模式必须包含该 `.spec.md` 中标记为**强制**的全部字段。

## 7. 阶段指标字段约定

> 每个阶段 `metrics.json` 的**完整字段集、类型与约束**以 `references/specs/metrics.spec.md`「字段定义」为**唯一权威来源**（含 `baseline` / `with_skill` / `security` 三模式各自的强制字段与额外字段），此处不内联重定义；三模式必须包含该 `.spec.md` 中标记为**强制**的全部字段。

规则：

- `aggregation_source` 必须表明阶段汇总来自任务/探测产物包
- 阶段汇总值必须从子 `task_metrics.json` 文件汇总得出
- 阶段 `metrics.json` 是汇总摘要，不是原始证据

## 8. Token 计算

### 范围

Token 估算以任务为单位，然后汇总。计入的内容包括：任务输入、任务 `thoutlog`、任务输出。

### 规范公式

```text
total_characters = input_characters + thoutlog_characters + output_characters
estimated_total_tokens = ceil(total_characters / 4)
```

报告要求：

- 每个任务将 Token 数据写入自己的 `task_metrics.json`
- 每个阶段将任务级值汇总到阶段 `metrics.json`
- `token_estimate_basis.scope` 语义等价于：任务输入 + thoutlog + 任务输出

## 9. 时间计算

### 功能任务

时间以任务为单位测量，然后汇总。唯一规范边界：当前任务的 `start_timestamp.json` + `end_timestamp.json`。

### 规范计算

`calculate_timestamp_diff.py` 是规范时间计算器，必须：

- 读取每个任务/探测自己的 `start_timestamp.json` 和 `end_timestamp.json`
- 将计算出的耗时写入 `task_metrics.json`
- 是 `time` 和 `total_time_seconds` 的唯一来源

可选修复脚本：`calculate_task_durations_from_end_timestamps.py`（须仅重放相同的规范计算逻辑）。

规范公式：

```text
task_time = 当前任务结束时间戳 - 当前任务开始时间戳
task_total_time_seconds = task_time
track_total_time_seconds = sum(task_total_time_seconds)
```

安全探测时间使用相同的任务级时间戳规则。

### 禁止的替代来源

以下方式均无效：

- `stage_start_timestamp.json`
- 前一个任务的 `end_timestamp.json`
- `timer.log`
- 默认值或手工计算

## 10. SpecAgent 交接

ExecAgent 不生成 `Tasks.json`。

交接边界：

- ExecAgent 产出完整的任务/探测产物包
- ExecAgent 产出阶段 `metrics.json`
- SpecAgent 消费这些产物并生成下游评分文件

SpecAgent 链：→ 见 `references/spec_contract.md`。
