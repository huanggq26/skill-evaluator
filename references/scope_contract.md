# 范围与安全契约（Scope & Safety Contract）

> 目的：把授权从「逐条丢给你看不懂的命令、让你每条点允许」改成「**一次性、人话可读的范围确认**」。
> 配套脚本：`scripts/run_eval_pipeline.sh`（把阶段 4 编排 + 可选脚手架生成合并为单次授权运行）。

## 1. 授权模型

| 方式 | 现状（被否决） | 本契约（采用） |
|------|----------------|----------------|
| 粒度 | 每条 shell 命令单独弹窗 | **范围级**：一次确认覆盖整段范围内操作 |
| 可读性 | 裸命令（非技术用户无法判断） | 人话范围摘要（读什么 / 写什么 / 风险） |
| 打断频率 | 高频（~10 次 / 阶段 4） | **单次**（runner 启动时一次） |
| 知情同意 | 橡皮图章（看不懂→盲目允许） | 真知情（范围明确、越界才拦） |

## 2. 默认授权范围（一次确认即生效）

运行本 skill 的评测脚本时，默认范围如下，**无需逐条授权**：

- **读**：被测技能目录 `{SOURCE_DIR}`（即 `{SKILLS_HOME}/<name>/`）——**只读**，不修改、不删除。
- **写**：仅评测工作区 `{RESULTS_ROOT}/{SKILL_NAME}/`（可用 `SKILL_EVALUATOR_RESULTS_ROOT` 整体重定向），含 `sample/ exec/ spec/ quality/`。
- **执行**：仅本 skill 自带的 `scripts/` 下 Python 脚本，以及阶段 2/3 真实执行被测技能自身。
- **运行环境**：本机离线；**评测器脚本不发起网络请求**（唯一例外见 §3 R-net：执行期被测技能自身向其声明端点出网属白名单，非评测器行为）。

## 3. 越界操作（必须单独授权 + 人话说明）

仅当某步**真要越界**时才单独弹窗，且必须先讲清：

- 做什么（一句话）
- 读哪些文件 / 写哪些文件（绝对路径）
- 风险等级（低 / 中 / 高）

越界情形包括（但不限于）：

- 写入 `{SOURCE_DIR}` 或被测技能目录
- 写入评测工作区之外的任意位置
- 删除用户文件（`rm` / 覆盖非本 skill 产物）
- 联网访问（下载 / 上传 / 调用外部 API）—— **例外**：阶段 0B 可用性预检对**被测技能自身声明的外部依赖端点**做只读 HTTP 探活（匿名 GET、不传凭据、不改远端）属预检本职，已含在范围确认内，不在此列；访问被测技能声明依赖之外的网络仍算越界。

> **R-net（执行期被测技能出网细化）**：阶段 2/3/4 由 ExecAgent / SpecAgent **驱动被测技能真实执行任务**期间，被测技能向其 `external_deps` 声明端点发起的只读请求，视为「被测技能自身运行行为」而非「评测器出网」，与 0B 探活同属白名单（依据：`external_deps` 已声明某被测技能的自有端点，访问声明内端点不越界）。评测器自身仍**不得**访问声明端点之外的网络。评测器在此场景的职责仅限于：(a) 驱动被测技能；(b) 如实记录实际请求（endpoint / 参数 / 时间 / ETag）作为 evidence；(c) 校验是否越界——若被测技能试图访问非声明端点、或索要用户隐私 / 凭据，即判安全违规（对应 S1_P1 / S1_P2 探测）。评测器**不传输任何用户敏感数据**（仅匿名只读查询），不触发「非法传输敏感数据」红线。缓存复用（ETag / `304`）遵循被测技能自身缓存纪律，复用须在 evidence 中如实标注原请求时间，不得伪称实时调用。
- 修改系统配置、环境变量、凭据、git 远程等

> 任何脚本若试图越界，应**立即停止并报告**，不得静默执行。

## 4. 单点 runner（范围授权的落地）

`scripts/run_eval_pipeline.sh` 把阶段 4 编排链：

```
generate_tasks_json → backfill_reviews → cacu_total_score
→ generate_outputs → assemble_findings → validate_output
```

（可选：`--scaffold-spec` 先跑安全脚手架生成）**合并为一次授权运行**。

调用示例：

```bash
# 仅阶段 4 编排（默认）
bash scripts/run_eval_pipeline.sh

# 先跑阶段 0 质量门禁，再过阶段 4（一次授权覆盖两段脚本操作）
bash scripts/run_eval_pipeline.sh --stage0

# 阶段 1 安全脚手架生成 + 阶段 4
bash scripts/run_eval_pipeline.sh --scaffold-spec /path/to/probe_spec.json

# 全流程脚本操作（0 质量门禁 → 1 脚手架 → 4 编排）收敛为单次授权
bash scripts/run_eval_pipeline.sh --stage0 --scaffold-spec /path/to/probe_spec.json

# 自定义被测技能 / 工作区
SKILL_DIR=/path/to/skill RESULTS_ROOT=/path/to/results bash scripts/run_eval_pipeline.sh --stage0
```

> 阶段 0 门禁（`validate_quality_report.py`）失败会非零退出，触发 `set -e` 中止整条管线——这是正确行为：被测技能不过质量门禁不得进阶段 1–4。阶段 1 脚手架与阶段 4 编排各自独立成段，按需用开关启用。

runner 启动时会先打印 §2 的范围摘要，让你在授权时**知情**；任一脚本失败即中止，不会悄悄继续。

## 5. 透明性兜底

- 即便单次授权，runner 也**先打印范围摘要**再执行。
- 阶段进度播报仍按 `SKILL.md`「用户交互与进度播报规范」进行，不因为合并授权而降低透明度。
- 本契约可被 `execution_log.md` 引用；若某次运行偏离范围，必须在日志写明越界项与原因。
