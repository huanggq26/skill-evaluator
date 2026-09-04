# ExecAgent with_skill 阶段

> 本阶段是 ExecAgent 的 **with_skill** 运行实例（引入 skill）。
> 基础流程、步骤、约束、验证均定义在 **`references/exec_common.md`**（两阶段共享的唯一流程权威来源，且不含任何 skill 逻辑）。
> 本文件在共享流程之上，**集中声明 with_skill 相对 baseline 的全部差异**；除下方「skill 差异声明」外，其余一律以共享流程为准，禁止另作内联重定义。

---

## 本实例运行参数

| 参数 | 取值 |
|------|------|
| `MODE` | `with_skill` |
| `{STAGE_OUTPUT_DIR}` | `{WITHSKILL_DIR}`（= `{RESULTS_ROOT}/{SKILL_NAME}/exec/with_skill/`） |
| `SKILL_SOURCE_PATH` | 目标 skill 源目录（**本阶段必填**） |

> 所有跨阶段全局变量的唯一定义源为 `references/config.md`「跨阶段输出路径变量」表。禁止重定义，仅引用。

派生值：

- `SKILL_NAME = basename(dirname({SAMPLES_DIR}))`
- `SKILL_SOURCE_NAME = basename(SKILL_SOURCE_PATH)`

---

## skill 差异声明（在共享流程之上的补充）

> 以下条款**仅适用于 with_skill**，覆盖/补充共享流程中对应位置。共享流程的指针项（如「skill 源读取权限见薄封装」）在此落地。

### 1. 硬约束补充（skill 源读取与调用）

- **允许读取 skill 源**：可读取 `SKILL_SOURCE_PATH` 下的实际 skill 文件，但仅允许在 `stage_start_timestamp.json` 写入后、进入具体任务时读取；禁止在阶段启动时预读整个 skill 源目录。
- **必须真实使用 skill**：每个任务必须真实调用/使用目标 skill，不得仅声明而未实际使用。
- **记录 skill 文件读取**：`files_read` 必须记录本任务实际读取的 skill 源文件；skill 文件的字符数必须计入 `input_characters`，并影响 `total_characters` 与 `estimated_total_tokens`。
- **回填 skill 调用字段**：`skill_invocation_attempted` 与 `skill_invocation_success` 必须回填到 `task_metrics.json`。

### 2. 步骤 2c 追加

在共享流程「步骤 2c」第 4 步之后追加：

- 在每个任务中**必须真实使用 skill**（skill 源文件已按上述规则读取）
- `files_read` 记录实际读取的 skill 源文件；其字符数计入 `input_characters`

### 3. 任务门禁补充

共享流程「任务门禁」报告语追加：`skill_invocation={attempted}/{success}。`

### 4. 完成标准 / 产物说明补充

- 每个 `task_metrics.json` **含 skill 调用字段**（`skill_invocation_attempted`、`skill_invocation_success`）
- 结果验证为 **6 项**（见下）

### 5. 结果验证补充（追加 2 项）

在共享流程「结果验证」5 项之外，追加：

- [ ] `skill_invocation_attempted` 和 `skill_invocation_success` 已回填
- [ ] `files_read` 记录了实际读取的 skill 文件

---

## 执行入口

请按 `references/exec_common.md` 的「完成标准 → 阶段地图 → 执行步骤 → 结果验证」顺序执行，应用以下替换与补充：

- 所有 `{MODE}` → `with_skill`
- 所有 `{STAGE_OUTPUT_DIR}` → `{WITHSKILL_DIR}`
- 应用上方「skill 差异声明」的全部补充条款

阶段终点为共享流程「步骤 5：停止」——with_skill 完成后停止当前终端。本阶段可与 baseline 并行启动，但本阶段内任务执行必须严格串行，且禁止处理 baseline 任务。本阶段遵循 `references/exec_common.md` 的统一约定：执行前读 `{RUN_PLAN}` 的 Stage 3 节（续跑 / 新建），执行中 / 收尾向 `{EXEC_LOG}` 追加条目；任务级 `tasks/{tid}/worklog.log` 仍按合约保留。

## 相关文件

| 文件 | 用途 |
|------|------|
| `references/exec_common.md` | **唯一流程权威来源**（本阶段基础执行依据）；其文末「相关文件」节为本阶段所需的全部 spec / 脚本 / 配置完整索引，请以该节为准，本封装不重复列举以免漂移 |
