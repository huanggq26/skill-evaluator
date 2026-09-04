# ExecAgent 阶段工作流程（共享权威流程）

> 本文件是 ExecAgent `baseline` 与 `with_skill` 两阶段的**唯一共享流程权威来源**。
> 两阶段是同一流程的两次运行实例，除「是否引入 skill」这一自变量外，流程、步骤、约束、验证**完全一致**。
>
> **本流程不含任何 skill 专属逻辑**。skill 相关行为（是否读取 skill 源、skill 调用字段、相关验证项）由对应薄封装声明，本流程仅在相关位置以指针指路，不做条件分支。
> **本文件由你当前阶段的薄封装（`references/<stage>/workflow.md`）引用，不是入口。** 请从你当前阶段的薄封装进入；抵达本文件后，应用该封装声明的 `MODE`/`{STAGE_OUTPUT_DIR}` 替换即可。**严禁读取另一阶段的薄封装**（当前为 baseline 时切勿读取 `withskill/workflow.md`，反之亦然），以免跨阶段污染。

---

## 运行参数（由薄封装声明并注入）

| 参数 | 取值 | 说明 |
|------|------|------|
| `MODE` | `baseline` 或 `with_skill` | 本阶段标识，用于脚本 `--mode` 与日志 |
| `{STAGE_OUTPUT_DIR}` | `{BASELINE_DIR}` 或 `{WITHSKILL_DIR}` | 本阶段输出根目录（→ `references/config.md`） |

> 所有跨阶段全局变量的**唯一定义源**为 `references/config.md`「跨阶段输出路径变量」表。禁止重定义，仅引用。

---

## ✅ 完成标准（Definition of Done）

> 以下产出全部生成并通过验证后，本阶段才算完成。缺少任何一项，任务不算完成。

| # | 产出物 | 位置 | 对应步骤 |
|---|--------|------|---------|
| 1 | 执行日志条目（本阶段摘要 + 异常）写入 `{EXEC_LOG}`；运行计划本阶段节（`{RUN_PLAN}`）步骤已全勾 | `{EXEC_LOG}` / `{RUN_PLAN}` | 步骤 0 + 4 |
| 2 | `stage_start_timestamp.json` | `{STAGE_OUTPUT_DIR}/` | 步骤 1 |
| 3 | 全部 functional_tasks 的产出（每任务 6 项：`results/` + `output_contract` 主结果物、`task_metrics.json`、`worklog.log`、`start_timestamp.json`、`end_timestamp.json`；缺失任一即视为未完成） | `{STAGE_OUTPUT_DIR}/tasks/{实际功能任务 ID}/` | 步骤 2 |
| 4 | `metrics.json` | `{STAGE_OUTPUT_DIR}/` | 步骤 3 |
| 5 | 5 项结果验证全部通过 | — | 结果验证 |

### 📊 进度跟踪

```
任务进度: [ ] [ ] [ ] ...  ← 按 manifest `functional_tasks` 实际数量
收尾步骤: [ ] metrics.json   [ ] 日志摘要   [ ] 停止确认
验证检查: [ ] [ ] [ ] [ ] [ ]  ← 全部打勾 = 阶段完成
```

**每完成一个任务，立即在对应位置标记 `[x]`，并同步勾选 `{RUN_PLAN}` 本阶段节对应项。全部 functional_tasks 完成后必须执行步骤 3→4→5。**（任务级清单为常驻锚点，持久化计划见 `{RUN_PLAN}`）

### 🗺️ 阶段地图（你在这里 / 还剩什么 / 终点）

| 阶段 | 步骤 | 细节小节 | 增量读取（仅到该步时打开，阶段入口不预读） |
|------|------|----------|--------------------------------------------|
| A 准备 | 0 运行计划+执行日志 / 1 阶段时间戳 | §步骤 0-1 | — |
| B 逐任务 | 2（functional_tasks × 2a-2f） | §步骤 2 | 每任务仅读其 `TaskDescription.md` + `WorkSpace/` + manifest 行；**禁止**读 `Grader/` |
| C 收尾 | 3 metrics / 4 日志摘要 / 5 停止 | §步骤 3-5 | 步骤 3 才读 `metrics.spec.md` |

> **增量阅读协议**：进入本阶段后，先读上方「完成标准 + 阶段地图 + 进度跟踪」作为常驻锚点；
> 各 spec 文件按上表「增量读取」列，在对应步骤开始时再打开。每完成一步回本表打勾，
> 阶段终点为步骤 5 的停止门禁（须先过结果验证）。本阶段完成后**停止当前终端**。

---

## 角色边界

> 本小节仅作职责描述，所有「禁止 / 必须」类约束以文末「硬约束」为唯一权威来源，此处不重述。

1. **本终端仅负责 ExecAgent 的 `{MODE}` 阶段**
2. 仅处理 functional_tasks（common + hard，数量动态，由 manifest 决定）；**不处理** `internal_checks`（内部策略校验，由样本生成阶段自检，ExecAgent 不执行）
3. `MODE=baseline`：本阶段是 ExecAgent 两次启动中的第一次；`MODE=with_skill`：可与 baseline 并行启动（由薄封装说明）
4. 禁止处理另一阶段的任务，禁止写入另一阶段目录

## 输入参数

> 本阶段引用的所有跨阶段全局变量，其**唯一定义源**为 `references/config.md`「跨阶段输出路径变量」表。禁止重新定义，仅引用。

| 变量 | 类型 | 说明 |
|------|------|------|
| `{SAMPLE_MANIFEST}` | 路径 | 任务清单（阶段 1 产出，本阶段输入） |
| `{SAMPLES_DIR}` | 路径 | 样本输出根目录 |
| `{SAMPLE_COMMON_DIR}` | 路径 | common 任务目录（数量动态，由 manifest 决定） |
| `{SAMPLE_HARD_DIR}` | 路径 | hard 任务目录（数量动态，由 manifest 决定） |
| `{SAMPLE_SECURITY_DIR}` | 路径 | 安全探测目录（数量动态，由 SpecAgent 处理，本阶段禁止读取） |
| `{STAGE_OUTPUT_DIR}` | 路径 | 本阶段输出目录（`{BASELINE_DIR}` 或 `{WITHSKILL_DIR}`） |
| `{SPEC_DIR}` | 路径 | SpecAgent 输出根目录（定义见 `references/stage4_config.md`，本阶段仅引用） |
| `{EXEC_LOG}` | 路径 | 结构化执行日志（跨阶段追加，自优化语料） |
| `{RUN_PLAN}` | 路径 | 跨阶段统一运行计划（本阶段节） |

## 输入

### 必须读取

| 输入项 | 来源 | 说明 |
|--------|------|------|
| `benchmark_manifest.json` | 阶段 1 产出 `{SAMPLES_DIR}` | 任务清单，含 functional_tasks 数组 |
| `common/` 目录下各任务 | 阶段 1 产出 | 功能任务样本 |
| `hard/` 目录下各任务 | 阶段 1 产出 | 困难任务样本 |

> 路径变量定义见 `references/config.md`。

### 每个任务仅读取

- `TaskDescription.md` — 任务描述
- `WorkSpace/` — 工作空间
- Manifest 行的 `outcome`、`output_contract`、`environment`、`verifier`、`unsupported_rules` 字段

### 禁止读取

> 禁止读取范围以文末「硬约束」第 9、10 条为唯一权威定义，此处仅作汇总指路：
> - `Grader/` 目录（Grader 由 SpecAgent 执行）→ 硬约束 #9
> - `{SAMPLE_SECURITY_DIR}`（安全探测目录，由 SpecAgent 处理）→ 硬约束 #10
>
> skill 源目录的读取权限**不在本流程内置**，由对应薄封装声明（baseline 禁止 / with_skill 允许按规则）。

## 输出边界

### 允许写入

- `{STAGE_OUTPUT_DIR}` — 本阶段执行结果
- `{EXEC_LOG}` — 结构化执行日志（追加）
- `{RUN_PLAN}` — 跨阶段统一运行计划（本阶段节，勾选推进）

### 禁止写入

> 以文末「硬约束」第 10 条为唯一权威定义，此处仅作指路：不得写入另一阶段目录（即 `baseline/` 或 `with_skill/`）或 `{SPEC_DIR}`（即 `spec/`）等越界目录。

---

## 执行步骤

### 阶段 A：准备

#### 步骤 0：建立运行计划与执行日志

1. 读取 `{RUN_PLAN}` 的 **Stage {N}** 节（`{N}` 为本阶段序号：baseline / with_skill 分别计入 Stage 2 / Stage 3 计划节）。
   - 若该节已存在且含未勾 `[ ]` 项 → **从中断点续跑**，已 `[x]`/`[~]` 跳过（支持中断后续跑）。
   - 若不存在 → 按本流程「进度跟踪」任务清单创建该节，逐项列 `[ ]`。
2. 确认 `{EXEC_LOG}` 存在，不存在则创建（仅首次）。
3. 向 `{EXEC_LOG}` 追加一条「阶段开始」条目（位置：步骤 0；原因：进入 {MODE} 阶段；计划违反：无）。

> 注：全局 `agent_worklog.log` 已废弃、职责并入 `{EXEC_LOG}`；任务级 `tasks/{tid}/worklog.log` 仍保留为输出合约证据（步骤 2f）。废弃映射与硬约束 → 见 `SKILL.md`「执行纪律」§3。

#### 步骤 1：记录阶段开始时间戳

```
python3 scripts/write_system_timestamp.py --output {STAGE_OUTPUT_DIR}/stage_start_timestamp.json
```

> `stage_start_timestamp.json` 结构见 `references/specs/timestamp.spec.md`

---

### 阶段 B：逐任务执行

#### 步骤 2：按序执行 functional_tasks

> ⚠️ **范围提醒**：本步骤是 `functional_tasks` 全部条目的循环体。全部功能任务执行完毕后，必须继续执行阶段 C（步骤 3→4→5）。任务执行不是阶段终点。

按 `benchmark_manifest.json` 中 `functional_tasks` 数组的顺序，逐一处理每个任务（**仅** `functional_tasks`；`internal_checks` 数组内的内部策略校验不在此执行）。

> 📊 **任务门禁**：每完成一个任务，必须在对话中报告：**"任务 {task_id}（N/{functional_tasks 总数}）已完成。进度：[x] 个已完成，[ ] 个待执行。继续下一个任务。"**

**每个任务严格按以下子步骤执行：**

##### 2a. 记录任务开始时间戳（在读取 TaskDescription.md 之前）

```
python3 scripts/write_system_timestamp.py --output {STAGE_OUTPUT_DIR}/tasks/{task_id}/start_timestamp.json
```

> ⚠️ 必须在读取任务描述**之前**执行

##### 2b. 生成 task_metrics.json 骨架

```
python3 scripts/generate_task_metrics.py --output {STAGE_OUTPUT_DIR}/tasks/{task_id}/task_metrics.json --task-id {task_id} --mode {MODE}
```

> `task_metrics.json` 结构见 `references/specs/task_metrics.spec.md`

##### 2c. 读取任务描述并执行

1. 读取 `<任务目录>/TaskDescription.md`
2. 读取 `<任务目录>/WorkSpace/` 下所有文件
3. 从 manifest 行读取 `outcome`、`output_contract`、`environment`、`verifier`、`unsupported_rules`
4. **严格按任务要求执行**，产出到 `{STAGE_OUTPUT_DIR}/tasks/{task_id}/results/`

> skill 调用行为（如适用）由薄封装在步骤 2c 追加，本流程不内置。

##### 2d. 记录任务结束时间戳

```
python3 scripts/write_system_timestamp.py --output {STAGE_OUTPUT_DIR}/tasks/{task_id}/end_timestamp.json
```

> ⚠️ 禁止通过 `echo`、`date`、`touch` 等方式手动创建 end_timestamp.json

##### 2e. 回填耗时字段

```
python3 scripts/backfill_task_duration.py \
    --task-metrics {STAGE_OUTPUT_DIR}/tasks/{task_id}/task_metrics.json \
    --start {STAGE_OUTPUT_DIR}/tasks/{task_id}/start_timestamp.json \
    --end {STAGE_OUTPUT_DIR}/tasks/{task_id}/end_timestamp.json \
    --task-id {task_id} --mode {MODE}
```

> 该脚本内部使用 `calculate_timestamp_diff.py` 计算耗时并重写 task_metrics.json

##### 2f. 写入任务级日志

在每个任务的 `{STAGE_OUTPUT_DIR}/tasks/{task_id}/worklog.log` 中记录任务执行过程。

**任务级日志格式**（`worklog.log`）：

```
TIMESTAMP [LEVEL] [TYPE] key=value ... message="..."
```

- 每任务一个独立文件
- 使用规范任务 ID（如 `C_01`、`H_01`）

日志示例：

```
2026-03-23T09:00:00Z [INFO] [START] agent=ExecAgent mode={MODE} task_id=C_01 stage={MODE} status=begin message="任务执行开始。"
2026-03-23T09:02:44Z [INFO] [EXECUTE] agent=ExecAgent mode={MODE} task_id=C_01 command="python3 scripts/write_system_timestamp.py --output {STAGE_OUTPUT_DIR}/tasks/C_01/end_timestamp.json" exit_code=0 message="已写入结束时间戳。"
2026-03-23T09:02:46Z [INFO] [END] agent=ExecAgent mode={MODE} task_id=C_01 success=true message="任务执行完成。"
```

##### 2g. 回填字符 / token 指标

任务执行并产出 `results/` 后，运行字符统计回填脚本，计算 `input_characters` / `output_characters` / `thoutlog_characters` / `total_characters` / `estimated_total_tokens`（= `ceil(total_characters / 4)`），写回 `task_metrics.json`（同时刷新阶段级 `metrics.json` 的 token 汇总）。

```
python3 scripts/backfill_character_metrics.py --skill-dir {SKILL_DIR} --exec-root {RESULTS_ROOT} --samples-root {RESULTS_ROOT}
```

> ⚠️ token 估算只能由本脚本产出（遵守硬约束 #13）；禁止手动填写 `estimated_total_tokens`。
> 该脚本扫描 `{STAGE_OUTPUT_DIR}/tasks/*/task_metrics.json`，对已完成任务自动回填，缺失的输入/输出从 `TaskDescription.md` + `results/` + `worklog.log` 推断。

---

### 阶段 C：收尾

> ⛔ **全部 functional_tasks 执行完毕后，必须继续执行以下步骤 3→4→5。不得在步骤 2 结束后终止。**

#### 步骤 3：生成阶段级 metrics.json

全部任务执行完毕后：

```
python3 scripts/generate_stage_metrics.py --output {STAGE_OUTPUT_DIR}/metrics.json --mode {MODE}
```

> `metrics.json` 结构见 `references/specs/metrics.spec.md`

#### 步骤 4：向执行日志追加阶段摘要

向 `{EXEC_LOG}` 追加本阶段（`{MODE}`）小结条目（模板见 skill 根 `SKILL.md`「执行纪律」节）：

```
## <UTC时间戳> Stage 2/3 / {MODE} — 阶段小结
- 位置：步骤 4（收尾）
- 原因：{MODE} 阶段执行完毕
- 异常情况：<若有填写，否则"无">
- 实际解决方案：completed_tasks=N successful_tasks=S failed_tasks=F；metrics_path="{STAGE_OUTPUT_DIR}/metrics.json"
- 后续建议（自优化）：<给 skill-evaluator 的改进建议>
- 计划违反：<若违反计划写明，否则"无">
```

并将 `{RUN_PLAN}` 本阶段节全部步骤勾选为 `[x]`（偏离项标 `[~]` 并附理由）。

#### 步骤 5：停止

> ⛔ 停止前确认：步骤 3（metrics.json）和步骤 4（日志摘要）是否已完成？结果验证是否已执行？

本阶段（`{MODE}`）完成，**停止当前终端**。不要继续另一阶段。

---

### 🗂️ 产出文件清单与生成因果（集中索引）

> 本表统一列出本阶段**全部输出文件**、**由哪一步生成**、**结构/合约来源**、以及**生成顺序与因果依赖**。核对产出完整性时以本表 + 「完成标准」为准，无需再串联多处文档。

| 输出文件 | 生成步骤 | 结构 / 合约来源 | 因果依赖（前置） |
|----------|----------|----------------|------------------|
| `execution_log.md` 条目 | 步骤 0 + 4 | 结构化执行日志（见 `{EXEC_LOG}`） | 无（自优化语料） |
| `stage_start_timestamp.json` | 步骤 1 | `references/specs/timestamp.spec.md` | 无 |
| `tasks/{tid}/start_timestamp.json` | 步骤 2a | `timestamp.spec.md` | 任务开始前（读 TaskDescription 之前） |
| `tasks/{tid}/task_metrics.json` | 步骤 2b + 2e | `task_metrics.spec.md` | 依赖 2a 时间戳；2e 回填耗时依赖 start/end 时间戳 |
| `tasks/{tid}/results/` + 主结果物 | 步骤 2c | `output_contract`（来自 TaskDescription/manifest） | 依赖 TaskDescription + WorkSpace |
| `tasks/{tid}/worklog.log` | 步骤 2f | 自由文本（任务级日志格式） | 依赖 2c 执行过程 |
| `tasks/{tid}/end_timestamp.json` | 步骤 2d | `timestamp.spec.md` | 依赖 2c 完成 |
| `metrics.json` | 步骤 3 | `metrics.spec.md` | 依赖全部 functional_tasks 的 `task_metrics.json`（汇总） |

**生成顺序（因果链）**：步骤 0 建运行计划 + 执行日志 → 步骤 1 阶段时间戳 → 步骤 2 逐任务（2a 开始时间戳 → 2b 指标骨架 → 2c 执行产出 → 2d 结束时间戳 → 2e 回填耗时 → 2f 任务日志）→ 步骤 3 汇总 `metrics.json`（依赖全部任务指标）→ 步骤 4 向执行日志追加阶段摘要 → 步骤 5 停止（须过结果验证）。

---

## 硬约束（唯一权威约束源）

> 本文件所有「禁止 / 必须」类约束以本列表为唯一权威来源；顶部「角色边界 / 禁止读取 / 输出边界」仅作职责描述与指路，不得与本列表冲突或重述。
> skill 源读取权限**不在本列表内置**，由对应薄封装声明（baseline 禁止 / with_skill 允许按规则）。

1. **只做本阶段**：本终端只处理 `{MODE}` 阶段，完成后停止，不进入另一阶段
2. **严格串行**：按 manifest 顺序逐一执行，禁止并行、后台、交错执行
3. **完整实现**：严格按 TaskDescription.md、Outcome、Output Contract、WorkSpace/ 要求实施，不改需求、不削弱约束、不跳过边界条件
4. **产出可解析主结果物**：必须产出 `output_contract` 声明的可解析主结果物；若因 `unsupported_rules` 限制无法完成，在结果物中设置 `status=unsupported` 或 `blocked` 并记录原因
5. **诚实失败**：若环境/依赖/权限/数据等条件不满足，如实记录阻塞原因，禁止伪装成功、使用占位文件/shell 结果/mock 结果/文字说明冒充实现
6. **时间戳规范生成**：`start_timestamp.json` 和 `end_timestamp.json` 必须由 `write_system_timestamp.py` 生成，禁止手动创建
7. **耗时仅来自脚本**：`time`/`total_time_seconds` 的唯一有效来源是 `backfill_task_duration.py`（内部通过 `calculate_timestamp_diff.py` 计算），禁止手动编辑或从其他来源推断
8. **不生成空壳**：`task_metrics.json` 和 `metrics.json` 必须先通过脚本生成骨架，再回填
9. **不读 Grader**：禁止读取或运行 `Grader/` 目录，评分由 SpecAgent 执行
10. **禁止越界写入与越界读取**：不得写入另一阶段目录（即 `baseline/` 或 `with_skill/`）或 `{SPEC_DIR}`（即 `spec/`）目录；不得读取 `{SAMPLE_SECURITY_DIR}`（安全探测目录，由 SpecAgent 处理）
11. **禁止启动子 Agent**：不得使用 Task 工具、子 agent、委托任务或并行 agent
12. **baseline 屏蔽被测技能内部知识（仅 baseline 模式生效）**：`MODE=baseline` 时，本终端**禁止读取被测技能源码 / SKILL.md / 任何内部文档**，也**禁止在推理中引用被测技能私有的数据源、接口地址、调用方法、降级策略或任何内部实现细节**。baseline 只能使用公共知识或通过公共搜索引擎可达的信息完成任务；若任务「正确完成」必须依赖被测技能私有知识源（如技能内部定义的专用 API 网址），则该任务对 baseline **不可比**，应如实记录「无法在屏蔽状态下完成」，不得假装完成、不得从任务描述里逆向出专用网址来凑出结果。with_skill 模式不受此条限制。
13. **token 指标仅由脚本填充**：`estimated_total_tokens` / `total_characters` 等字符统计字段的唯一有效来源是 `backfill_character_metrics.py`（公式 `ceil(total_characters / 4)`），禁止手动编辑或从其他来源推断；耗时字段仍遵守硬约束 #7（仅来自 `backfill_task_duration.py`）。

## 结果验证

> ⛔ 步骤 5（停止）之前，必须逐项完成以下检查。未全部通过不得停止。

执行完成后检查：

- [ ] `{STAGE_OUTPUT_DIR}/stage_start_timestamp.json` 存在且格式规范
- [ ] `{STAGE_OUTPUT_DIR}/metrics.json` 存在
- [ ] 每个 functional_task 的任务目录下包含 5 个规范文件：`results/`、`task_metrics.json`、`worklog.log`、`start_timestamp.json`、`end_timestamp.json`
- [ ] 每个 `task_metrics.json` 中的 `time`/`total_time_seconds` 字段由脚本路径填充（非 null、非手动值）
- [ ] 每个 `task_metrics.json` 中的 `estimated_total_tokens` / `total_characters` 由 `backfill_character_metrics.py` 填充（非 0，除非任务确为空产物）
- [ ] `{EXEC_LOG}` 中包含本阶段（`{MODE}`）小结条目，且 `{RUN_PLAN}` 本阶段节无残留 `[ ]`
- [ ] 未写入另一阶段目录或 `{RESULTS_ROOT}/{SKILL_NAME}/spec/` 目录

## 相关文件

| 文件 | 用途 |
|------|------|
| `references/config.md` | 共享路径与参数定义 |
| `references/stage2_config.md` | Stage 2-3 专属路径与常量 |
| `references/exec_contract.md` | Stage 2-3 基准执行合约 |
| `references/specs/timestamp.spec.md` | 时间戳 JSON 结构 |
| `references/specs/task_metrics.spec.md` | 任务指标 JSON 结构 |
| `references/specs/metrics.spec.md` | 阶段指标 JSON 结构 |
| `scripts/calculate_timestamp_diff.py` | 时长计算脚本 |
| `scripts/backfill_task_duration.py` | 时长回填脚本 |
| `references/specs/benchmark_manifest.spec.md` | benchmark_manifest.json 结构 |
| `references/specs/task_description.spec.md` | TaskDescription.md 结构 |
