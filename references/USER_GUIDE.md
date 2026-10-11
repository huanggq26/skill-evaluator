# skill-evaluator 使用指南（人话版）

> 这份文档是**给你（使用者）看的**：讲清楚这是什么、怎么跑、怎么读结果、结果出来后怎么办，以及跑的过程中你会看到什么。
> 本文档是**自足的**：怎么用、怎么读结果、结果出来后怎么办，这里都讲清楚，**不依赖任何外部文档**。
> 想了解**评测体系本身**（为什么这样评、评哪些维度、怎么读分数），见 `references/skill-evaluation-system.md`（用户视角，可选）。
> 引用纪律：项目内文档一律用**相对路径**互相引用，**不引用项目外文档、不使用绝对路径**——技能发布后外部文档不存在、路径也会变。
> 本 skill 内部的阶段执行指令在 `references/` 下各 `stage*.md` 与 `config.md` 里，你不用管。

---

## 1. 这是什么，什么时候用

### 1.1 它是干嘛的

`skill-evaluator` 是一个**评测别的 AI Agent skill 好不好用、安不安全**的基准测试流水线。它盯着你指定的某一个目标 skill，按 5 个阶段串行跑：

- **阶段 0 质量预检**：静态检查目标 skill 的格式 / 对外依赖 / 内容 / 生态，产出质量评测报告并卡一道"质量门禁"。
- **阶段 1 样本生成**：造一批标准化测试样本（功能任务 + 安全探测）。
- **阶段 2 基线执行**：在不启用目标 skill 的情况下跑这些任务，留底对照。
- **阶段 3 带 skill 执行**：启用目标 skill 再跑同样的任务。
- **阶段 4 规格评估**：做安全探测、跑代码评审（Grader），给出评分和问题报告。

最终产出一份可审计的"质量 / 功能 / 安全"评估报告。

> 阶段 0 不依赖 1–4，所以"只想看质量报告"时最省时省钱，建议先跑 0 过关后再上全流程。

### 1.2 怎么触发（不需要懂上面的阶段）

| 你想做的事 | 怎么跟 AI 说（触发话术示例） | 实际怎么跑 |
|------------|------------------------------|------------|
| 全面评测一个 skill | "测一下 `/path/to/某skill` 的质量与安全性" | 阶段 0 → 1 → 2 → 3 → 4 全流程 |
| 只想知道"这 skill 写得差在哪" | "仅评估这个 skill 质量" | **只跑阶段 0**（质量预检 + 门禁），跑完即结束 |
| 提交新 skill 前把关 | "给这个 skill 做基准测试" | 全流程 |

**不适用**：纯代码库审计、非 skill 仓库评审、第三方 MCP 工具评审——这些不是本 skill 的对象。

---

## 2. 怎么跑

### 2.0 环境要求

| 项 | 要求 | 说明 |
|---|---|---|
| Python | **≥ 3.8** | 已按 3.8 语法基线校验；类型注解均带 `from __future__ import annotations`，故 `Path \| None` 等联合注解在低版本同样安全 |
| 第三方依赖 | **无强制依赖** | 全部使用标准库 |
| 可选依赖 | `toml`（仅旧版 Python） | TOML 语法检查优先用 `tomllib`（Python 3.11+ 内置）；低版本自动回退第三方 `toml`，两者都缺则**跳过该项检查**，不影响评测 |
| 平台 | Linux / macOS / Windows | 路径均相对解析，不写死物理路径 |

> 主测环境为 Python 3.9。低于 3.8 的版本未做兼容性保证。

最省事的方式是用单点 runner 一次跑完编排阶段（只需一次范围授权）：

```bash
bash scripts/run_eval_pipeline.sh                                   # 仅阶段 4 编排
bash scripts/run_eval_pipeline.sh --stage0                          # 先跑阶段 0 质量门禁，再阶段 4
bash scripts/run_eval_pipeline.sh --scaffold-spec /path/spec.json   # 先生成安全脚手架，再阶段 4
bash scripts/run_eval_pipeline.sh --reset --stage0                 # 清空工作区后跑质量门禁 + 阶段 4
bash scripts/run_eval_pipeline.sh --project-state production        # 上线态
# 最常用：评测你自己的某个 skill（全流程，上线态）
bash scripts/run_eval_pipeline.sh --skill-dir /path/to/your-skill --project-state production
```

跑之前有**两件事必须明确**：

1. **指定待评估技能目录**——命令行 `--skill-dir /path/to/skill`，或环境变量 `SKILL_DIR`。不指定时默认指向 skill-evaluator 自身（自测）。
2. **声明项目状态 `--project-state debug|production`**（见 §4，默认 `debug`）。同一份低分，两种状态下含义完全不同，不声明会误读。

### 2.1 结果写到哪

所有产物**默认写在 `{RESULTS_ROOT}/{目标skill名}/`**，不污染 skill 本身。其中 `RESULTS_ROOT` 不是写死的物理路径，而是按当前机器解析的通用路径：

- `DEFAULT_OUTPUT_DIR` = 你这台机器的**系统下载目录**（macOS/Linux 是 `$HOME/Downloads`，Windows 是 `%USERPROFILE%\Downloads`）；
- `RESULTS_ROOT` = `{DEFAULT_OUTPUT_DIR}/skill-evaluator_results`。

想换位置，设环境变量即可，不动 skill 文件：

```bash
export SKILL_EVALUATOR_RESULTS_ROOT=/你的/自定义/目录
```

> 旧版本输出目录叫 `skilltester_results`（skilltester 是改造前的旧工程名），已统一更名为 `skill-evaluator_results`；旧环境变量 `SKILLTESTER_RESULTS_ROOT` 同步废弃。

---

## 3. 评测结束后，你会拿到三份东西（受众不同，写法不同）

一次评测跑完，在 `spec/` 目录下会产出三份文件。它们**给不同的人看**，所以写法完全不同：

| 文件 | 给谁看 | 回答的问题 | 怎么写 |
|------|--------|------------|--------|
| **`scores.json`** | **程序 / 机器** | 技能**能不能上架**（门禁结论 + 关键数值） | 紧凑 JSON，按字段名读取，门禁关键指标排在文件最前面 |
| **`benchmark_report.md`** | **你（审核人）** | 这份技能**值不值得上架**，证据是什么 | 人话叙述：摘要、对比、安全、建议 |
| **`problem_report.md`** | **技能作者 / 维护者** | 技能**哪里要改**、为什么差 | 人话叙述：退化清单、根因、修复指引 |

一句话纪律：**门禁只回答"过 / 不过"，"为什么差"全部进 `problem_report.md`**，两份人读的报告不混用。

> **人只看两个 `.md`**：作为使用者（审核人或技能作者），你只需读 `benchmark_report.md` 与 `problem_report.md`；`scores.json` 是给程序 / 自动化框架读的，你一般不用碰。

> 对后续自动化框架：直接读 `scores.json` 即可拿到全部门禁参数，**不要去正则解析 `.md` 报告**——`scores.json` 才是权威结构，`benchmark_report.md` 只是它的人类可读渲染。

---

## 4. 两种项目状态（最重要）

运行评测时务必显式声明状态，因为它决定了"低分 / 失败该怪谁"：

- **调试态 `debug`**：评测工程本身还在调通阶段。失败要先怀疑**评测工程本身**——比如 baseline 是瞬间秒过的 stub、token 计量断链、`Reach=0` 只是样本没覆盖 baseline 做不到的任务。先修评测工程，再复评。
- **上线态 `production`**：评测工程已调通、作为发布品使用。任何失败 / 低分**只能归因到被评技能本身**，作者须逐条解决后才能再提交门禁。

> 典型调试态信号（先怀疑评测，别急着怪技能）：baseline 几乎空跑、token 计量为 0 但真实消耗很多、样本里全是双方都能做的任务。

---

## 5. 评测结果在哪里看（目录布局）

`{RESULTS_ROOT}/{skill名}/`（`RESULTS_ROOT` 默认为系统下载目录下的 `skill-evaluator_results`，可用环境变量 `SKILL_EVALUATOR_RESULTS_ROOT` 覆盖）下：

```
{skill名}/
├── quality/     ← 阶段 0 质量评测报告（quality_report.md）+ 质量分 quality_score.json
├── sample/      ← 阶段 1 生成的测试样本
├── exec/
│   ├── baseline/    ← 阶段 2 基线执行结果
│   └── with_skill/  ← 阶段 3 带 skill 执行结果
└── spec/        ← 阶段 4 安全探测 + 评分 + 问题报告
    ├── scores.json          ← 机器可读门禁产物（与两份报告同目录，开头即门禁指标）
    ├── benchmark_report.md  ← 审核人看：上架与否 + 证据
    ├── problem_report.md    ← 作者看：哪里要改 + 修复指引
    └── results/             ← 内部流程文件：Tasks.json / Template.json / Template.csv
```

（`scores.json` 已与两份报告放在同一 `spec/` 目录，方便"只扫一个目录"就拿全门禁参数。）

---

## 6. 怎么看结果

### 6.1 门禁结论 `verdict.decision`

打开 `benchmark_report.md` 最上面的「执行摘要」就能看到结论。四种结论：

- **`REJECT`（不通过）**：**只有**安全分没过才会触发。安全是硬门禁，低于 `SECURITY_GATE`（当前 100）直接否决，别的维度都不看。安全分缺失时按宽容策略给「条件上架」，但上线前必须补齐安全探测核实。
- **`推荐上架`**：技能带来了 baseline 做不到的新能力（`reach > 0`）、质量达标、且**可比任务上没变慢**。
- **`条件上架`（默认档）**：有增量但质量不达标；或**可比任务上反而更慢**（见下，只软下调，不否决）；或**没有增量覆盖**（`reach = 0`，宽容策略下不再判"不建议"）。
- **`不建议`**：仅严格模式下（`LENIENT_ENTRY=False`）才会出现。

> **关于"更慢"要分两种情况**：只有 baseline 和 with_skill **做了同样的事（同样功能 / 同样产出 / 同样质量）**，with_skill 还更慢，才算真正的效率退化（软指标下调）。如果 with_skill 更慢是因为它**产出了更多 / 更好**的东西（scope 不同），那不应算退化——这类任务会被自动排除出效能对比（`comparable=false`），报告里单列说明，不拉低结论。

### 6.2 四个关键数值怎么读

`benchmark_report.md` 第 4 节和 `scores.json` 里都有这四个数：

| 数值 | 是什么 | 怎么读 |
|------|--------|--------|
| `security_score` | 安全分（硬门禁） | 低于门禁值直接 `REJECT`，别的都不看 |
| `reach` | 增量覆盖 | 技能能做、baseline 做不到的任务数。样本里必须包含这类任务，否则门禁没东西可判 |
| `efficiency_gain_ratio` | 效能增值（带正负号） | 只统计"可比"任务。`>=0` 表示 with_skill 更快（好）；`<0` 表示同等工作上更慢（真实退化，软下调）。`= (Σbaseline耗时 − Σskill耗时) / Σbaseline耗时` |
| `avg_multiplier` | 耗时倍率 | `= Σskill / Σbaseline`。`>1` 表示更慢，`<1` 表示更快，和上一行是一回事的不同说法 |
| `quality_score` | 编写质量分 | 低于制度线（60）会打"强制整改"标签，但**不自动阻断**上架 |

> 效能（时间快慢）是**软指标**：只在"同 scope 真实变慢"时，把"推荐上架"降为"条件上架"，**绝不会导致 REJECT**。

### 6.3 `benchmark_report.md` 重点看什么

- 开头的**执行摘要**：一句话结论 + 四个数值。
- **baseline 与 with_skill 对比**：哪些任务是双方都能做的（重叠集），重叠规模多大。
- **安全评估**：12 个安全探测过了几个、分布在哪几个维度。
- **关键发现与建议**：下一步该改什么。

### 6.4 `problem_report.md` 重点看什么

- **效能退化**：双方都成功、但 with_skill 更慢 / 更费的任务（"做对了但更慢"）。
- **被排除的不可比 slower 任务**：with_skill 更慢是因为 scope 不同（产出更完整），**不算退化**，单列说明。
- **无增效功能原因分析**：为什么 baseline 也能完成、技能是否只改了效率没改能力边界。
- 每条都带 `attribution`：调试态会区分"评测工程问题 / 技能问题 / 两边皆有"；上线态默认归因技能并给修复指引。

### 6.5 程序怎么读 `scores.json`

`scores.json` 现在和两份报告在**同一个目录**（`spec/`）。它的**最前面固定是门禁关键指标**，程序按字段名读取即可，顺序只是为了人看着方便：

```jsonc
{
  "scores": {
    "verdict": { "decision": "条件上架", "labels": [], "reasons": [...], "project_state": "debug" },
    "security_score": 100.0,
    "reach": { "absolute": 0, "rate": 0.0 },
    "efficiency_gain_ratio": -0.6395,
    "avg_multiplier": 1.6395,
    "quality_score": 100.0,
    "comparable_both_success_tasks": 3
    // ……后面是评分明细（dimensions / raw_measurements / tasks 等）
  }
  // skill_name / source / generated_at 等元信息附后
}
```

配套读取片段（框架直接复用）：

```python
import json
s = json.load(open("spec/scores.json"))
sc = s["scores"]                          # 门禁数值在 scores 块内
print(sc["verdict"]["decision"])          # 上架结论
print(sc["security_score"], sc["reach"]["absolute"], sc["efficiency_gain_ratio"])
```

---

## 7. 结果出来后怎么办

- **调试态**：先去 `problem_report.md` 看"评测工程侧"的条目（修基准、接通 token 计量、补 baseline 不可达样本），修完再复评。skill-evaluator 每次回归后还会自动进入自优化闭环。
- **上线态**：逐条解决 `problem_report.md` 里归因到技能侧的条目（改方案、修脚本、补边界覆盖），再重新提交门禁。

---

## 8. 跑评测时你会看到什么（进度、产物与应对）

当你让 AI 跑 skill-evaluator 时，它会按下面这套节奏跟你沟通。你**不需要懂里面的阶段细节**，只要知道"现在到哪了、结果在哪、卡住怎么办"就行。

### 8.1 开场：先跟你对齐

正式跑之前，AI 会先跟你确认几件事：要测的是哪个 skill（目录路径 / 名字）、这次是「只做质量预检（阶段 0）」还是「全流程 0–4」、结果会写到哪（默认 `{RESULTS_ROOT}/{skill名}/`，或你用 `SKILL_EVALUATOR_RESULTS_ROOT` 指定的目录）、大概开销（阶段 2/3 会**真的去执行一批任务**、阶段 4 会跑安全探测和代码评审，比较费时费 token；阶段 0 最省，所以一般建议先跑 0 过关再上全流程）。

如果你没给目标 skill 的路径，它会先问你要，不会自己瞎猜。

### 8.2 每个阶段：两次播报

流程最多 5 个阶段，AI 会**一个一个来**，不会一下子把 5 个全摊开。

- **进入某阶段时**：会告诉你「▶ 阶段 N / 名称，这一步做什么，产物会写到哪」。
- **该阶段跑完验证后**：会告诉你「✅ 完成 / ⚠️ 存疑 / ❌ 没过门禁」，并附上关键产物的实际路径。

阶段与产物位置对照：

| 阶段 | 这一步干嘛 | 产物在哪看 |
|------|-----------|-----------|
| 0 质量预检 | 查目标 skill 格式/依赖/内容/生态，出质量报告 + 卡门禁 | `…/quality/quality_report.md` |
| 1 样本生成 | 造一批标准化测试任务（功能 + 安全） | `…/sample/` |
| 2 基线执行 | 不启用目标 skill 跑一遍留底 | `…/exec/baseline/` |
| 3 带 skill 执行 | 启用目标 skill 再跑同样任务 | `…/exec/with_skill/` |
| 4 规格评估 | 安全探测 + 代码评审 + 评分，出最终报告 | `…/spec/benchmark_report.md`、`…/spec/problem_report.md`、`…/spec/scores.json` |

（`…` 即 `{RESULTS_ROOT}/{skill名}/`，或你用 `SKILL_EVALUATOR_RESULTS_ROOT` 指定的目录。）

### 8.3 门禁没过：你该做什么

- **阶段 0 质量门禁没过（最常见）**：这说明「被测的 skill 本身写得不达标」，**不是评测工具的问题**。AI 会给你一份问题清单（报告里也有「关键问题汇总」）。你要做的是——**改你那个被测 skill**，然后让 AI 重新跑阶段 0（或全流程）。门禁不过，AI 不会硬闯进下一阶段。
- **阶段 1–4 验证没过**：分两种情况。如果是「被测 skill 功能缺失 / 有安全弱点被暴露」，那是评测的**正常结论**，会写进报告继续推进；如果是评测脚本自己报错、产物缺失，AI 会停下来告诉你。

---

## 9. 手工维护脚本（可选，非流水线自动调用）

流水线（阶段 0–4）的常规评测不需要手动跑任何脚本。但下面这几个脚本用于"历史产物修复 / 回填"，不参与一次干净的首跑流程，**需人工按需调用**。仅在你的评测产物出现对应问题时才使用，平时可忽略。

### 9.1 `backfill_character_metrics.py` —— 回填字符 / token 指标
- **使用场景**：历史运行中 `task_metrics.json` 的字符相关字段（输入/输出/思维链字符数、估算 token 数）为空 / null / 损坏，需重新计算补全，而不重跑整个执行。
- **前提**：已有 baseline / with_skill 的产物目录（含样本、worklog 等）。
- **调用**：
  ```bash
  python3 scripts/backfill_character_metrics.py --skill skill_name   # 修复单个 skill
  python3 scripts/backfill_character_metrics.py --all               # 批量修复所有 skill
  ```
- 结果写回各 `task_metrics.json` 与阶段级 `metrics.json`。

### 9.2 `backfill_reviews.py` —— 重跑 Grader 回填评审结果
- **使用场景**：已生成 `Tasks.json`，但代码评审（Grader）结果需重新生成 / 回填到每个任务 / 探测行（例如换了评分器版本、或历史评审字段缺失）。
- **调用**（参数均必填，指向同一 skill 的对应产物目录）：
  ```bash
  python3 scripts/backfill_reviews.py \
      --tasks-json {RESULTS_ROOT}/{skill_name}/spec/results/Tasks.json \
      --sample-dir {RESULTS_ROOT}/{skill_name}/sample \
      --exec-dir   {RESULTS_ROOT}/{skill_name}/exec \
      --spec-dir   {RESULTS_ROOT}/{skill_name}/spec
  ```

### 9.3 `repair_durations.py` —— 从本地时间戳刷新耗时
- **使用场景**：规范的任务本地 start/end 时间戳 JSON 已存在，但 `task_metrics.json` 的耗时字段损坏或缺失，需严格基于时间戳重新计算并刷新（不回退到 timer.log 或默认耗时）。
- **调用**（按模式处理某个 track 根目录下的所有 bundle）：
  ```bash
  python3 scripts/repair_durations.py \
      --track-root {RESULTS_ROOT}/{skill_name}/exec/baseline \
      --mode baseline
  # --mode 可选 baseline / with_skill / security
  ```

> 这些脚本依赖同目录下的 `calculate_timestamp_diff.py`（耗时计算）等，调用时请从 skill 根目录或 `scripts/` 目录运行，并确保脚本文件保持完整。它们与流水线的常规评测互不干扰。
> 上列均为**使用者可能手动调用**的脚本。开发/回归用脚本不随发布包分发，使用者无需关心。

---

## 10. 运行计划与执行日志（过程文档，给你看个明白）

评测跑起来后，除了最终报告，还会产生"过程文档"（写在结果根目录下，不在 skill 目录里）：

- **跨阶段统一运行计划 `run_plan.md`**（结果根目录）：整个评测（Stage 0–4）的总计划书。每个阶段动手前，执行评测的 AI 会按该阶段 `workflow.md` 在这里新建一节步骤清单（逐项 `[ ]`），做完一步勾一步（`[x]`；合理跳过/偏差标 `[~]` 并注明原因）。**中断续跑协议**：重新进入某阶段先读对应节，含未勾 `[ ]` 则从断点续跑、已勾跳过。这份文件由 AI 在运行时维护（不是脚本生成、也不被流水线消费），其中阶段 0 一节指向下面的机器校验计划。
- **阶段 0 评测计划 `{skill名}_eval_plan.md`**（`quality/` 子目录）：阶段 0 专属的细化勾选清单，与上面不同的是它有**机器强制**——质量门禁 `validate_quality_report.py --plan` 会检查"无残留 `[ ]`"，没做完直接卡关。实际跑的时候如果必须偏离计划，会在执行日志里写清楚为什么。
- **执行日志 `execution_log.md`**（结果根目录）：这是一份"过程日记"，记录每一步的**位置、原因、遇到的异常、实际怎么解决的、后续建议**，以及"哪里违反了计划、为什么、后续怎么改"。它**不被任何评测脚本读取**，纯粹是给评测工具自己留的优化素材——作者（或 AI）复盘时据此改进 skill-evaluator。你作为使用者一般不用管它；只有想"帮这个评测工具挑刺、提改进"时才看。

> 责任划分小结：阶段 0 的计划闭环是**机器强制**的（门禁脚本卡关）；Stage 1–4 的 `run_plan.md` 与 `execution_log.md` 由执行评测的 AI 按各阶段 `workflow.md` 的纪律维护（`run_eval_pipeline.sh` 不生成、不读取它们）。上一次全流程评测产出的 `run_plan.md` 即为该机制实际运转的证据。
>
> 注：每个任务目录下的 `tasks/{任务id}/worklog.log`、每个安全探测的 `probes/{id}/worklog.log` **仍然保留**——它们是评测证据的组成部分，不能删。

---

## 11. 常见问题

> **头条：跑之前必须声明 `--project-state debug|production`**。同一份低分，两种状态下"该怪谁"完全不同——调试态先怀疑评测工程本身（baseline 空跑、token 计量断链、`reach=0` 可能是样本没覆盖 baseline 做不到的任务），上线态则任何失败 / 低分只归因被评技能。不声明会误读结论（详见 §4）。

- **它会不会改我的被测 skill？** 不会。评测器对被测技能目录（`{SOURCE_DIR}`）**只读**，所有产出只写在 results 工作区（`{RESULTS_ROOT}/{skill名}/`），不碰被测对象本身。阶段 0 门禁没过，是要**你去改被测 skill**，不是它改。
- **它会不会删我文件 / 改系统 / 偷跑网络？** 不会乱来。默认范围：只读被测目录 + 只在 results 工作区写 + 仅运行本 skill 自带脚本与被测技能自身。唯一的出网情形是阶段 0B 可用性预检，对你技能**自己声明的外部依赖端点**做只读 HTTP 探活（匿名 GET、不传凭据）；无外部依赖的技能 0B 整体跳过、完全不出网。除此之外的写工作区外 / 删除 / 访问声明依赖之外的网络 / 改系统凭据，都属越界，会单独用大白话跟你确认（详见 `references/scope_contract.md`）。
- **它会不会自己改自己 / 记日志？** 你正常把它当工具用时是**发布态（production）**，本 skill 对自身目录完全只读、不写日志；只有以"项目方式打开本 skill 做迭代"的调试态（debug）才可能自优化改自身、记会话日志。
- **`reach = 0` 是不是说明技能没用？** 不一定。调试态先查样本是否没覆盖 baseline 做不到的任务；上线态才说明技能真实增量有限。
- **with_skill 更慢就算退化吗？** 只有在双方"做同样的事"时才算。如果它产出了更多 / 更好的东西，会被排除出效能对比，不算退化。
- **安全分权重为什么是 0？** 这是当前设计：安全分已改为**硬门禁（veto）**，不进加权，低于门禁（<100）直接 `REJECT`，不看其他维度。权重 0 仅表示不参与加权均值，不代表安全被忽略。
- **报告里出现 `FTxx_xxx`（如 `FT01_xxx`）是什么？** 那是功能任务代号（Functional Task）。正常情况下报告会对每个代号附"用户视角行为语义"（如"用户问今天有什么 XX 资讯，技能能否正确取数"）。若你只看到代号、没看到人话解释，属报告渲染异常，可反馈。
- **报告里出现 `<skill-name>` 字样？** 那是模板占位符没被替换的提示性文本，属正常，不影响门禁判定。
- **三份产物我该看哪个？** 人只看两个 `.md`：`benchmark_report.md`（审核人：值不值得上架 + 证据）、`problem_report.md`（作者：哪里要改 + 修复指引）；`scores.json` 给程序读，人一般不用碰。
- **阶段 0 门禁没过怎么办？** 门禁脚本会输出问题清单（报告里也有"关键问题汇总"）。先按清单改目标 skill，再重跑阶段 0，直到退出码 0、`success=true`。
- **只想重跑某一个阶段？** 前序阶段产物已落盘时，可直接从对应阶段文档续跑，不必从头来。
- **SKILL.md 说"读对应 reference 文档"是什么意思？** 那是写给执行 agent 的：它只在进入某阶段时才读该阶段文档，避免一次性塞太多内容进上下文。你作为使用者不用管。

---

## 12. 跨平台安装路径速查

同一份 skill 内容可装到任意平台，仅**目录不同**：

| 平台 | 用户级 skills 目录 |
|------|--------------------|
| CodeBuddy | `~/.codebuddy/skills/skill-evaluator/` |
| Claude Code | `~/.claude/skills/skill-evaluator/` |
| opencode | `~/.config/opencode/skills/skill-evaluator/`（或对应配置目录） |
| openclaw / hermes | 各平台约定 skills 目录（以平台文档为准） |

拿到 `skill-evaluator.zip` 后，解压到上述任一目录即启用。

---

## 13. 本 skill 目录结构解读

装好之后，skill 目录大概长这样（以 `{SKILLS_HOME}/skill-evaluator/` 指代，各平台实际路径见上文对照表）：

```
skill-evaluator/
├── SKILL.md                  ← 入口：编排索引（agent 读它决定怎么跑），< 5k 词
├── references/               ← 全部"按需才读"的文档与规范
│   ├── config.md             ← 路径 / 变量 / 常量唯一定义源（所有内部路径相对本 skill 根）
│   ├── scope_contract.md     ← 范围与安全契约（一次授权模型）
│   ├── stage0_preflight.md   ← 阶段 0 质量预检完整流程
│   ├── stage1_sample.md      ← 阶段 1 样本生成流程
│   ├── stage2_baseline.md    ← 阶段 2 基线执行流程
│   ├── stage3_withskill.md   ← 阶段 3 带 skill 执行流程
│   ├── stage4_spec.md        ← 阶段 4 规格评估流程
│   ├── stage1_config.md / stage2_config.md / stage4_config.md ← 各阶段专属常量
│   ├── exec_contract.md / sample_contract.md / spec_contract.md ← 各 Agent 基准输出合约
│   ├── exec_common.md        ← ExecAgent 共用执行细则
│   ├── result.sample.md      ← 历史参考
│   ├── skill_url_map.json     ← skill / URL 映射表
│   ├── specs/                ← 全部输出结构规范（.spec.md）+ 示例
│   └── SafeTest/             ← 安全测试知识库（README + principles + dimensions/）
├── scripts/                  ← 20 余个可执行的 Python 脚本 + run_eval_pipeline.sh（见下）
└── assets/                   ← 模板：report.template.md、Template.json、Template.csv
```

### `scripts/` 脚本按用途归类（具体命令见各阶段文档）

- **质量预检（阶段 0）**：`extract_stats.py`（客观统计提取）、`validate_quality_report.py`（质量门禁）
- **时间戳 / 时长**：`write_system_timestamp.py`、`calculate_timestamp_diff.py`、`backfill_task_duration.py`、`repair_durations.py`
- **指标统计**：`backfill_character_metrics.py`、`generate_stage_metrics.py`、`generate_task_metrics.py`
- **安全探测（阶段 4）**：`run_security_pipeline.py`、`validate_output.py`、`verify_findings.py`、`assemble_findings.py`、`generate_probe_scaffolds.py`（安全脚手架生成）、`probe_checks.py`（探测校验）
- **评分**：`cacu_total_score.py`
- **样本 / 报告生成**：`generate_outputs.py`、`backfill_reviews.py`、`generate_fixture_manifest.py`、`generate_memory_invariant.py`、`generate_tasks_json.py`
- **内部共用**：`_common.py`（被其他脚本 import，不单独运行）

> 常规（阶段 0–4）评测无需手动跑这些脚本——它们由对应阶段的 reference 文档按流程自动调用。需手动调用的"历史产物修复/回填"脚本见 §9。
> 开发 / 回归用脚本属维护期工具，**不随发布包分发**，故不在本清单内。

---

> 本文档只讲"怎么用、怎么读"，已自足。想改策略 / 改代码 / 看改动点映射，可参考存档资料
> `references/skill-evaluation-system.md`（可选，不是使用本文档的前置条件）。
