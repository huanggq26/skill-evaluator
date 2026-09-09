# skill-evaluator 项目级规则

> **规格声明**（LLM 自消费规格 · 强制）
> - 编写/维护者：LLM（自写自维护，含未来自己）
> - 使用者：运行中的 LLM（唯一目标读者；人可读非目标）
> - 编写牵引目标：token 最少、性能最优、不确定性最低
> - 作用：本仓项目级规则入口；规定 LLM 修改本仓时须先读的设计契约、目录/文件规划与改动纪律；含质量报告流水线的协作契约（原独立契约文件已并入此处，以一处为准）
> - 生成物：无（自身即约束）
> - 层级/归属：项目级规格（受 agent_spec_writing_standard.md 与 project_spec_maintenance.md 共同约束）
> - 自检锚点：改本文件前后 → 递归过 `层级/归属` 链上全部规格文件的对应自检清单，逐项核对，禁止跳过
> - 整理日期：2026-08-22

## 能力标签

> 标签决定哪些通用条款适用；**不打项目类型**（如"技能项目"），只打可组合能力。
> 依据：`project_spec_maintenance.md#能力标签（个性化管理）`；条款适用性见其「条款适用性索引」。
> **项目形态**：`技能开发`（识别依据：存在技能入口文件 `SKILL.md`）——形态仅为标签预设，**条款适用由标签决定**。

| 标签 | 说明 |
|---|---|
| `需打包发布` | 发布包过滤 `.project/` 治理区整目录 + 治理入口文件（机制：`.gitattributes` 的 `export-ignore`，与版本控制解耦）；发布隔离条款适用 |
| `子系统契约` | 输出结构定义 `references/specs/*.spec.md`（**运行态**技能文档）+ 开发态契约 `.project/specs/*.contract.md`；主文件以索引指针引用 |
| `SDD工作流` | 已启用规范驱动开发（`openspec/` 工作区 + 命令行工具可用）；变更生命周期按 `openspec_governance_spec.md` 执行。**未打此标签时**相关条款一律不适用，按原治理条款原样执行（双环境防冲突） |

- **不适用**：`远端编译`（无编译，仅 Python）、`多子项目`（单项目）、`无发布`（需发布）。

> **约束链（传递性）**：本文件 → `project_spec_maintenance.md` → `agent_spec_writing_standard.md`（元规格）。链上全为规格文件，修改本文件前须回扫链上**全部**规格文件（见 `agent_spec_writing_standard.md#规则分层与边界.约束传递性（递归约束）`）。

> **作用边界（强制）**：本文件及 `.project/specs/*`（开发态契约）**不参与运行时逻辑**，脚本/流水线不加载；仅在本仓文件**需要修改时**由 LLM 读取。
> 注：`references/specs/*.spec.md` 属**运行态技能文档**（执行时由 LLM 读取，定义输出数据结构），**不在**本"不参与运行时"边界内。

## 上级规格约束（层级/归属）

本仓所有 LLM 自消费规格（本文件、`.project/specs/*` 开发态契约）均受头部声明块 `层级/归属` 中列出的上级规格共同约束（声明即生效，正文不重复声明，修改时按 上级规格一致性纪律（强制） 核对）。编写/修订规格前先读 `agent_spec_writing_standard.md` 与 `project_spec_maintenance.md`；"项目级规则文件如何建立/维护"的通用治理规则见 `project_spec_maintenance.md`（通用规格，独立于本仓）。

**技能入口文件 `SKILL.md` 不是规格文件**：它是运行态流程文件（被加载执行），不约束任何规格的维护；约束其**编写**的规范属开发态规范（见 开发态自检锚点映射表（唯一权威））。

## 开发态自检锚点映射表（唯一权威）

> 依据：`project_spec_maintenance.md#开发态自检锚点（防约束未激活）`。运行态文件**不写**自检锚点，其触发由本表 + 项目入口共同承载。

| 被改文件 | 文件时态 | 改后须过 |
|---|---|---|
| `.project/AGENTS_RULES.md`（本文件）、`.project/specs/*.contract.md` | **开发态**（规格文件） | `agent_spec_writing_standard.md#自检清单.规格文件自检清单` |
| `SKILL.md` | **运行态**（被加载执行） | `agent_spec_writing_standard.md#自检清单.技能文件自检清单` |
| `references/**`（含 `references/specs/*.spec.md`） | **运行态**（执行时由 LLM 读取，属技能文档） | 无规格清单适用；须跑 `.project/tmp/check_release_isolation.py`（发布区无开发态残留） |
| `scripts/*.py`、`scripts/*.sh` | **运行态** | 须跑 `.project/tmp/selfcheck_refactor.py`（退出码 0）+ 遵守 `agent_spec_writing_standard.md#标识外置` |

> **时态判据**：执行时会被读取/加载 → 运行态（技能文档，不带规格声明块）；仅"修改代码前"读取 → 开发态（规格文件，须带声明块且置于治理区）。

- 递归：本表之外的规格文件，另沿 `层级/归属` 链回扫 `project_spec_maintenance.md` → `agent_spec_writing_standard.md`。
- 本表**全仓仅一份**；平台入口（`AGENTS.md`、`CODEBUDDY.md`、`opencode.json`）只写指针，不复制本表。

## 目录与文件规划

本仓固定结构（修改前先读此段，新增文件须归入对应类）：

| 路径 | 用途 | 是否运行时加载 |
|------|------|----------------|
| `SKILL.md` | 技能入口说明（LLM 被加载执行） | 是 |
| `AGENTS_RULES.md` | 项目级规则入口（本文件） | 否 |
| `scripts/` | 运行脚本（`.py`）与流水线壳（`run_*.sh`）；`_common.py`/`_project_state.py` 为共享模块 | 是 |
| `assets/` | 模版与静态资源：`report.template.md`（质量报告模版·唯一真相源）、`Template.csv`/`Template.json`（样本/任务模版） | 模版被读取，非加载 |
| `references/` | 阶段流程/用户指南/配置说明等非数据规格文档（`stage*.md`、`USER_GUIDE.md`、`config.md` 等） | 否 |
| `references/specs/` | **仅数据规格定义文件**（`.spec.md`，如 `benchmark_manifest.spec.md`、`scores.spec.md`）；不放协作契约/流程契约 | 否 |
| `.project/error_registry/` | **错误档案区**：md 为权威源 + `errindex.db` 派生索引；**诊断前必查**（纵：模块-函数 / 横：组合标签） | 否（主动检索） |
| `openspec/` | **规范区（开发态）**：行为说明书 `specs/` + 变更 `changes/`（含归档 `changes/archive/`）+ 项目约定 `config.yaml`。**纳入版本管理**（长期资产，须备份）；发布时由 `.gitattributes` 的 `export-ignore` 过滤 | 否（开发期读取） |
| `.codebuddy/` | **平台机制目录**：由规范工具生成的命令（`.codebuddy/commands/opsx/`）与技能（`.codebuddy/skills/openspec-*/`）；可重建，**不进版本控制** | 否（平台按需加载） |

约束：
- **发布隔离与版本控制解耦（2026-09-09 变更）**：治理区 `.project/` 与规范区 `openspec/` 属**无法重建的长期资产**，一律**纳入版本管理**做备份；其**发布过滤**改由 `.gitattributes` 的 `export-ignore` 承担（`git archive` 打包时自动排除），不再依赖 `.gitignore`。二者各管一件事：`.gitignore` 决定「是否入库备份」，`.gitattributes` 决定「是否进发布包」——解耦前，二者被同一份 `.gitignore` 承担，导致「要备份就必须进发布包」的两难。
- `.codebuddy/` 由工具生成、可重建，既不入库也不进包（保持 `.gitignore` 排除）。
- 校验：`git ls-files openspec` 应**有**条目而 `git ls-files .codebuddy` 为 0；`git archive HEAD | tar -t` 应**不含** `.project/` 与 `openspec/` 路径。
- `openspec/specs/` 只收**行为契约**（需求 + 场景），不复制 `references/` 正文；两者只留指针，防双写漂移。
- `references/specs/` 只收数据规格定义（字段/结构契约）；流程类、协作类契约并入本文件或 `references/` 对应文档。
- 协作契约（如质量报告流水线）**不单独成文件**，直接写入本文件，以一处为准（防重复/两张皮）。

## 修改纪律（硬序）

本文件是项目所有「需修改时先读」逻辑的总锚点入口，覆盖全部子系统，非仅质量报告。任何触及下列文件的修改，均须先 `read_file` 本文件对应段重建上下文（无对话上下文时尤其）：

> 通用执行方法（先读重建上下文 / 不凭记忆推断 / 改后自验证）见 `project_spec_maintenance.md#修改执行纪律（硬序 · 通用）`。**本节只列本项目子系统锚点**。

1. **质量报告流水线**：模版 `assets/report.template.md`、`scripts/build_objective_data.py`、`merge_report_data.py`、`render_report.py`、`validate_quality_report.py`、`schema_from_template.py` → 见「质量报告流水线协作契约」。修改模版字段（增/删/改名/改 type）→ 同步 字段归属锚点（当前裁决） 归属 + 一致性核对手段（防漂移）；发现缺漏填 待办任务表。客观维度/字段：`build_objective_data.py` 必须产出（含空），merge/validate 强制校验存在（核心不变量 I4）。
2. **可用性预检（阶段 0B）**：`scripts/extract_deps.py`、`scripts/dep_probe.py`、`run_eval_pipeline.sh` 的 0B 步骤 → 见「可用性预检（0B）架构契约」。改这些文件前先读本段 + 其指向的 `references/dependency_availability.md`（细节逻辑所在）。
3. LLM 只消费 schema + objective_data.json（核心不变量 I3，同样适用于上述各子系统）。
4. **报告输出**：`scripts/generate_outputs.py`、`scripts/assemble_findings.py`、`scripts/cacu_total_score.py`、`scripts/dep_probe.py` 及质量报告渲染链（`gen_quality_report.py`/`render_report.py`/`build_objective_data.py`）→ 先读「报告使用者、用途与内容边界（总约束）」（C1–C3 内容取舍 + 使用者/用途边界铁律），再读「报告输出要求（benchmark_report / problem_report 通用契约）」（R1–R14）。确保报告只承载对使用者有用的发现、文案数据驱动、去代号、不绑定被测技能、problem_report 聚焦技能问题。
5. **错误诊断（通用前置 · 强制）**：诊断任何错误/异常前，**必须先查错误档案** `.project/error_registry/`：① 纵检索 `errindex q --module <模块> [--func <函数>]`；② 从命中记录取标签，横检索 `errindex q --tag <标签>`；③ 按 `file_path` **打开 md 读原文**（含「误判史」）；④ 逐条核对「前提/依赖」是否仍成立。未完成上述四步**不得下结论**（效率让位于正确性）。违反即记 `E31` 入档。**写入侧（对称强制）**：定位根因 / 实施修复 / 归因被推翻 / 前提失效时，须**同步写档案**（补归因·策略·验证方式；被推翻则追加「误判史」），并 `errindex rebuild` + `check` 通过。**不写档案 = 任务未完成**，不得标 `DONE`。命令与规范见 `error_registry/README.md`。
6. **行为变更走规范流程**（标签 `SDD工作流` 适用）：新增/修改/移除**对外行为**时，先建变更（提案 → 行为契约 → 设计 → 任务）再改代码；改前仍须读本文件对应段重建上下文。
   - **不建变更**的情形：纯文档、内容填写（如主观维度裁定）、工具脚本且不改变对外行为。
   - 变更过程中沿用第 5 条查档与建档纪律（诊断前查档、解决后建档）。
   - 归档后同步本文件**当前结论**（行为类结论进 `openspec/specs/`）；**不回写 TASKLOG**、**不留逐条依据指针**（只保留一条固定指引），防双写。
   - 无 `SDD工作流` 标签的项目不适用本条，按原流程执行。细则见 `openspec_governance_spec.md`。
7. **删除一律走废纸篓（硬 · 用户 2026-09-09 定）**：任何删除文件/目录的动作**禁止用 `rm`**，一律改用 `trash <路径>...`（`~/.codebuddy/bin/trash`，已在 PATH）：移入 `~/.Trash` 并按 `时间戳 | 原路径 | 篓内路径` 记入 `~/.codebuddy/trash.log`，同名自动加时间戳后缀不覆盖；`trash --list` 查记录、`trash --undo` 恢复最近一条到原路径。
   - **禁止绕过安全拦截**：批量删除被安全机制拦截时（如超批量阈值），**不得**改写为等效删除方式（删父目录 / 逐个删 / 换命令或脚本）绕过，须立即停止并向用户说明、等指令。
   - 已知环境事实：macOS 下 `~/.Trash` 权限 700 且**禁止列目录**（`Operation not permitted`，TCC 保护），但 `mv` 写入与按全路径访问正常——脚本不依赖列目录，属预期行为，非缺陷。

## 质量报告流水线协作契约

> 作用边界（强制）：本段**不参与运行时逻辑**，流水线/脚本/渲染均不加载；仅在本仓质量报告相关文件**需要修改时**由 LLM 读取与维护。细节逻辑在源码，本段只做锚点记录。

### 核心不变量（违反即错）

| # | 规则 | 违反后果 |
|---|------|----------|
| I1 | 模版 `assets/report.template.md` 是唯一真相源；字段标注经 `schema_from_template.py` 单向派生 schema | 定义两张皮 |
| I2 | 客观归属最终裁定权在系统层：某要素客观 ⟺ `objective_data.json` 实际含该字段；模版标注仅作 LLM 提示 | 标注与产物错位 |
| I3 | LLM 只消费 schema + `objective_data.json`，不读 `build_objective_data.py` 源码推断逻辑 | 耦合脚本实现 |
| I4 | 合并客观优先：`merge_report_data.py` 以客观产物为准；schema 标 objective 的节点必须在 objective_data 存在，否则报错 | 客观维度漏覆盖 |
| I5 | 本规格为锚点记录，不在正文复述源码实现细节；源码改而本规格未同步属缺陷 | 规格漂移 |

### 数据流与阶段责任

输入 → 脚本客观产出 → LLM 主观回填 → 合并 → 校验 → 渲染。各阶段生产者、产物、门禁：

| 阶段 | 生产者 | 产物 | 门禁 |
|------|--------|------|------|
| 统计 | 脚本 `extract_stats.py` | `extract_stats.json` | 文件存在非空 |
| 依赖探测 | 脚本 `dep_probe.py` | `dependency_probe.json` | 文件存在 |
| 客观聚合 | 脚本 `build_objective_data.py` | `objective_data.json` | `--skill-root` 必参 |
| 回填 | LLM | `subjective_data.json` | 仅填 subjective 节点 |
| 合并 | 脚本 `merge_report_data.py` | `report_data.json` | objective 节点强制存在 |
| 校验 | 脚本 `validate_quality_report.py` | stdout JSON | `--objective`/`--data` 退出码 |
| 渲染 | 脚本 `render_report.py` | `quality_report.md` | 模版标注块剥离 |

### 模版标注语法（真相源）

| 标注 | 格式 | 消费者 |
|------|------|--------|
| 全局列 | `<!-- columns: 位置,原因,改进建议 -->` | `schema_from_template.py` |
| 表格维度 | `<!-- dim: <名> type: objective|subjective -->` | 同上 |
| 文本字段 | `<!-- field: <名> type: objective|subjective -->` | 同上 |

`schema_from_template.py` 把 `dim`/`field` 统一收进 `dims`（带 `kind`: table/text、`type`）。下游遍历此列表。

### 字段归属锚点（当前裁决）

> 锚点：字段名 → 节点类型 → 脚本来源函数。细节在源码，此处不复述实现。

#### 客观（脚本产出，LLM 不填）

| 字段 | 节点 | 脚本函数 |
|------|------|----------|
| `frontmatter_quality` | dim/table/objective | `map_frontmatter_quality` |
| `structure_org` | dim/table/objective | `map_structure_org` |
| `eco_portability` | dim/table/objective | `map_eco_portability` |
| `dependency_availability` | dim/table/objective | `map_dependency_availability` |
| `stat_chars` | field/text/objective | `map_stat_chars` |
| `dir_tree` | field/text/objective | `map_dir_tree` |
| `objective_critical` | dim/table/objective | `map_issue_summary` |
| `objective_warning` | dim/table/objective | `map_issue_summary` |
| `deps_tools_candidates` | field/text/objective | `map_deps_candidates` |
| `deps_skills_candidates` | field/text/objective | `map_deps_candidates` |
| `deps_commands_candidates` | field/text/objective | `map_deps_candidates` |

级别词约定（客观 `原因` 列嵌入 `严重`/`警告`，供聚合与渲染着色）：
- `contract_defect` → 严重；`env_issue`/`config_defect` → 警告
- 机器路径/CRLF/缺章节/非 env shebang → 警告
- frontmatter 解析失败/缺字段/name 格式错/链接损坏/格式解析失败 → 严重
- 关键词语义须与 `render_report._severity_of` 及 `build_objective_data._severity_of` 一致（一致性核对手段（防漂移） 核对）

#### 主观（LLM 填，脚本不产客观值）

| 字段 | 节点 | LLM 责任 |
|------|------|----------|
| `modalities` | field/text/subjective | 多模态能力归纳 |
| `function_table` | field/table/subjective | L0 对外交付物功能表 |
| `grammar` | dim/table/subjective | 文法语义判断 |
| `deps_tools` | dim/table/subjective | 裁定 `deps_tools_candidates` 真实依赖+原因 |
| `deps_skills` | dim/table/subjective | 裁定 `deps_skills_candidates` |
| `deps_commands` | dim/table/subjective | 裁定 `deps_commands_candidates` |
| `content_correct`/`content_complete`/`content_scope_alignment`/`content_redundant`/`content_ambiguous` | dim/table/subjective | 内容验证 5 维 |
| `eco_placement`/`eco_identity` | dim/table/subjective | 生态分类与身份触发 |
| `subjective_critical`/`subjective_warning` | dim/table/subjective | 汇总主观维度严重/警告项 |

#### 混合（脚本抽骨架 + LLM 裁定）

对外依赖三件套：`..._candidates`(objective 文本，脚本扫) → 对应 `deps_*`(subjective 维度，LLM 裁定)。脚本不替 LLM 做语义裁定。

### 合并/校验/渲染契约

| 脚本 | 模式 | 行为 |
|------|------|------|
| `merge_report_data.py` | `--objective --subjective --template` | objective 节点必存；subjective 缺省写"无" |
| `validate_quality_report.py` | `--objective` | 仅校验 objective 节点全存在且结构合法 |
| 同上 | `--data` | 全量 schema 校验 |
| 同上 | `--report` | 兼容渲染后 markdown 校验 |
| `render_report.py` | `--template --data --out` | 按 schema 正则替换；同小节多 field 顺序展开；空 rows 渲染"无"；剥离标注块与模板说明段 |

### 一致性核对手段（防漂移）

| 检查项 | 核对手段 |
|--------|----------|
| 模版 objective 节点 ⊆ objective_data 键 | `validate_quality_report.py --objective` 退出码 0 |
| 级别词语义两处一致 | grep `严重`/`警告` 于 `build_objective_data.py` 与 `render_report.py` 的 `_severity_of` |
| 标注语法变更同步解析 | 改 `report.template.md` 标注后跑 `schema_from_template.py` 比对 |
| 本规格字段清单 ≡ 源码产出 | grep 字段名于 `build_objective_data.build()` 与 字段归属锚点（当前裁决） |

### 维护触发（强制）

LLM 在以下任一动作前**必须先读本段**，动作后**同步维护**：

1. 修改 `assets/report.template.md` 字段（增/删/改名/改 type）→ 同步 字段归属锚点（当前裁决） 归属 + 一致性核对手段（防漂移） 核对手段
2. 修改 `scripts/build_objective_data.py` 映射 → 同步 字段归属锚点（当前裁决）.客观（脚本产出，LLM 不填） 脚本函数指针
3. 修改 `merge_report_data.py`/`render_report.py`/`validate_quality_report.py`/`schema_from_template.py` 流程 → 同步 数据流与阶段责任/合并/校验/渲染契约
4. 读项目文档时发现**规格未记录的在役逻辑** → 填入 规格外逻辑待补表，下次维护时锚定入 字段归属锚点（当前裁决）

### 决策锚点（当前归属结果，非理由）

| 决策 | 当前状态 |
|------|----------|
| `grammar` 由 objective 降 subjective | 已落地（文法需语义判断，无客观探测器） |
| `summary` 拆 `stat_chars`/`dir_tree`(obj)+`modalities`/`function_table`(subj) | 已落地 |
| 关键问题汇总拆 `objective_critical`/`objective_warning`(聚合)+`subjective_*` | 已落地 |
| 对外依赖候选化（`..._candidates` obj + `deps_*` subj 裁定） | 已落地 |

## 可用性预检（0B）架构契约

> 作用边界（强制）：本段**不参与运行时逻辑**，脚本不加载；仅在本仓 0B 探测相关文件**需要修改时**由 LLM 读取与维护。细则（checker 实现、裁决矩阵、输出字段结构）在 `references/dependency_availability.md`，本段只锚定架构原则，不在正文复述细节，避免与细节文档重复定义。

### 架构原则（唯一权威，细节不在此展开）

1. **归属与门禁位**：0B 是阶段 0 第二步，位于 0A 静态预检之后、阶段 1 之前，是性能/安全耗时测试的总前置闸门。
2. **条件触发**：仅当依赖提取器从被测技能上下文（`SKILL.md` + `scripts/` + 配置）提取到 `external_deps` 非空才执行；为空则 `dependency_skipped=true`、自然跳过，不否决。
3. **真相源是技能上下文，非手填中间文件**：`external_deps` 是依赖提取器的产出（承载于 `benchmark_manifest.json`），不是可用性测试的前提权威；探测器只做「声明 Expect X，验证返回有没有 X」的通用比对，不预设业务含义。
4. **维度族分层**：D1 存活 / D2 契约 / D3 参数生效 / D4 降级契约 / D5 凭证可用 / D6 幂等；每个 checker 输出 `kind ∈ {structural, transient, config}` 描述**失败性质**。
5. **裁决核心（结构性否决，瞬态不否决）**：`structural fail`（契约永久不成立、凭证校验失败）→ 计入 `dependency_score`，`< DEPENDENCY_GATE` → REJECT；`transient fail`（超时/5xx/429）→ 重试 `DEP_RETRY_MAX` 次，不否决，仅报告「瞬态观测」；`config missing` → 记为「未配置」，条件上架。
6. **失败归属**：`category ∈ {contract_defect（技能缺陷，否决）, env_issue（环境/网络，不否决）, config_defect（未配置，不否决）}`；`kind` 描性质、`category` 描归属，二者经 `dep_probe.py` 关联。
7. **与安全边界**：安全管「行为合规」（`sensitive-info-leak` / `permission-boundary`），可用性管「依赖可达与契约成立」（DEP-AVAIL）；凭证泄露归安全、凭证可用归可用性。该边界以本段为准，`config.md` 不重复定义。
8. **常量与 verdict 分流**：新增 `DEPENDENCY_GATE`、`DEP_RETRY_MAX`；`scores.json` 增 `dependency_score`/`dependency_skipped`/`dependency.dimensions`；`_compute_verdict` 新增 `dependency_expected` 分流"有依赖却无探测=REJECT"。

### 维护触发（强制）

LLM 在以下任一动作前**必须先读本段 + `references/dependency_availability.md`**，动作后同步维护：

1. 修改 `scripts/extract_deps.py`（DEP-EXTRACT 提取器）→ 同步 架构原则 3（真相源与两类依赖定义）
2. 修改 `scripts/dep_probe.py`（D1–D6 探测与裁决）→ 同步 架构原则 4–6（维度族 / 裁决核心 / 失败归属）
3. 修改 `run_eval_pipeline.sh` 的 0B 步骤或 `scripts/cacu_total_score.py` 的常量/verdict → 同步 架构原则 7–8
4. 读文档发现规格未记录的 0B 在役逻辑 → 填入 规格外逻辑待补表 并锚定本段

## 报告使用者、用途与内容边界（总约束）

> 作用边界（强制）：本段**不参与运行时逻辑**，脚本不加载；仅在报告生成相关文件**需要修改时**由 LLM 读取。本段定义三份报告的使用者/用途，并据此划定「什么能进报告、什么不能进」。本段优先级高于「报告输出要求（benchmark_report / problem_report 通用契约）」中各 R 规则——凡与本段冲突，以本段为准。

### 一、三份报告的使用者与用途（定义即边界）

| 报告 | 生成阶段 | 使用者 | 用途 | 在评测中的角色 |
|------|---------|--------|------|----------------|
| 质量报告（`<skill-name>评测.md`） | 阶段 0（Preflight） | 人 + LLM | 技能优化（静态问题清单） | 问题报告的**静态部分**，阶段 4 聚合时纳入 |
| 问题报告（`problem_report.md`） | 阶段 4 | 人 + LLM | 技能优化（全阶段问题汇总） | 整轮评测的问题汇总出口 |
| 基准报告（`benchmark_report.md`） | 阶段 4 | 人 + LLM | 评估技能**能否使用**（上架/否决裁决依据） | 可用性裁决出口 |

**边界铁律**：一切与上述使用者 / 用途**不相关**的内容，**一律不得放入报告**。典型禁入项（非穷举）：
- 给报告生成者（LLM/脚本作者）自己看的过程性纪要、中间推导、调试备注；
- 评测器自身的「质量要求」「评分口径说明」「本工具使用说明」等元信息；
- 与"技能优化"或"能否使用"无关的方法论自述。

### 二、内容取舍规则

- **C1 通用业务规则不进报告，进用户手册**：面向被测技能领域的通用业务规则、评测器通用使用说明，属 `references/USER_GUIDE.md`（或对应用户文档）范畴，**禁止作为说明文字贴入报告**。报告只承载「本次评测针对该技能的实际发现与数据」。
- **C2 规则说明须贴合数据，不贴无关规则**：需要解释某条数据/裁决时，**只抽取贴合该数据的规则说明**，或**直接把解释插入到数据行/数据块中**（如分值旁注语义、表格内联说明），**禁止在报告中铺设与该次数据无关的通则、条款、定义性长文**。
- **C3 过程性内容不落盘为报告章节**：阶段产物（json 字段映射、评分中间量、探测原始返回）只服务于生成报告，**不得作为独立章节/附录写入报告**；确需呈现的，只呈现其「结论性、对使用者有用」的部分。

### 三、与下段的衔接

「报告输出要求（benchmark_report / problem_report 通用契约）」中的 R1–R14 是本段边界下的具体文案/逻辑纪律；R8（problem_report 不重复 benchmark 评分解读）、R9（丢弃空占位与噪声标签）、R12（质量评估纳入阶段 0 真实发现）即为本段「角色不越界、只承载对使用者有用的发现」的直接落地。

## 报告输出要求（benchmark_report / problem_report 通用契约）

> 作用边界（强制）：本段**不参与运行时逻辑**，脚本不加载；仅在本仓报告生成相关文件（`scripts/generate_outputs.py`、`scripts/assemble_findings.py`、`scripts/cacu_total_score.py`、`scripts/dep_probe.py` 等）**需要修改时**由 LLM 读取与维护。本段由 2026-08 多轮报告评审中暴露的缺陷反推沉淀，是报告文案/逻辑的硬约束。

### 一、数据驱动，禁止自相矛盾（最高优先级）

- **R1 文案必须随真实计算值走**：报告里出现的每一个数字、排除数、reach 值、裁决词，都必须直接来自 `scores.json` / 评分器真实产出，**不得凭空写死或反推成相反结论**。凡出现「排除集=0」却另有 N 个增量任务、「reach=0」却已知 baseline 做不到私有源、「未评估」却实为前置门禁未纳入 等反向陈述，即违反本规则。
- **R2 裁决与结论透传评分器**：上架/否决/条件上架等结论词一律取 `_compute_verdict` 真实输出，**禁止在报告里硬编码固定结论或编造触发条件**（如写死「条件上架」而不看真实 verdict；自创「reach=0 在调试态先查…」规则式文字）。
- **R3 不截断、不隐去数据**：列举类（增量效用任务、可比任务去向、问题项）必须列全，**禁止 `[:N]` 截断**；凡「N 个 / 总 M 个」式表述必须显式拆解出 N 的构成（如 1 可比 + 5 增量覆盖），不得留模糊总数。

### 二、去内部代号，讲人话

- **R4 内部代号零外泄**：功能任务代号（如 `FT01_xxx` 等内部 ID）、维度代号（`D1`–`D6`）、原始 Grader 笔记（`must_pass_satisfied=True`、`pass (10/10)`）**一律在报告呈现前转译为用户视角语义**。`FT*` 须配「用户问『…』技能能否…」行为语义；Grader 笔记须译「通过（10/10 项检查点通过）+ 关键强制检查点全部满足」。**语义映射须从本次评测 manifest 的 title/objective 动态读取**（由评测执行者按被测技能真实功能填写），**禁止在框架脚本内硬编码某被测技能专属任务 ID**（如某技能的 `FT01_xxx`）——缺失时回退原 ID，保证不丢信息也不绑定技能。
- **R5 首现即解释**：样本包内置的自检用例代号（如 `FTxx_xxx`）**首次出现时即用一句话说明其业务含义**（技能自身回归自检逻辑），不假设读者懂内部命名。

### 三、评测器通用性，禁止绑定被测技能

- **R6 不绑定具体被测技能**：探测端点、样本来源、结论样例**一律取被测技能 manifest 声明的 `external_deps` 与运行产物**，禁止硬编码某技能域名、禁止假设某特定技能的样本/行为、禁止在框架的规格/脚本/目录中写入任何被测技能特有信息、规则或文件。
- **R6.1 过程文件归属（硬）**：`functional_tasks.jsonl` 等评测过程文件是**本项目运行时要求、由评测执行者理解被测技能后在工作区产生**的输入，**只存在于评测工作区（如 `~/Downloads/skill-evaluator_results/<skill>/`），不得写入本框架工程的规格/脚本/目录**，不得进框架 git 仓库。框架仓库仅保留通用骨架模板（`references/stage1_functional_template.jsonl`，无技能名、纯占位、靠 A/B/C 闸门拦截）。任何把被测技能特性固化进本项目的做法均违反 R6/R6.1。
- **R7 不写用户不可操作项**：报告只陈述评测器实际能做的事，**禁止建议用户去「补充样本 / 填空 / 改配置后重试」等用户侧不可直接操作的动作**（评测器自采样本，用户无法补）。

### 四、problem_report 严格聚焦「被测技能问题以优化技能」

- **R8 不重复 benchmark 的评分解读**：problem_report 只承载「已确认问题 + 未核实项 + 评估范围与可信度」，**禁止复述基准评分报告的分数/比例/效用率解读**；凡与 benchmark 重叠的「原因分析 / 增效解读」小节一律删除（曾误设 §四 无增效功能原因分析）。
- **R9 丢弃空占位与噪声标签**：渲染前丢弃「无（文档未提及）」「客观检查项：无 / AI 评估补充：无」等空标签；`调用其他Tools/Skills/系统命令：` 后无内容者整小节丢弃；按小节整体判断是否有真实发现，无则整节不输出。
- **R10 摘要去双零混乱**：已确认问题合并为单计数「已确认问题：N 个」；未核实项仅当 >0 时显示，不制造「0 个已确认 / 0 个未核实」式双零噪声。
- **R11 覆盖与边界精简**：评估范围与可信度压缩为 2 条以内的精简陈述，不展开成噪声段。
- **R12 质量评估纳入阶段 0 真实发现**：problem_report 质量评估小节须纳入阶段 0 质量报告（`<skill-name>评测.md`）全部实际发现问题（格式/结构/文法/内容/生态/依赖），不得只留空「无」。

### 五、工程纪律

- **R13 执行序自查**：报告函数引用的模块级常量（如 `cap_map`）**必须在调用点之前构建/定义**，防止 `NameError`（曾因 `_cap_map` 定义在调用点之后触发）。
- **R14 自核对两文件**：修改报告逻辑后，代理须自行 `read_file` 交叉核对 `benchmark_report.md` 与 `problem_report.md` 无 R1–R12 残留矛盾/噪声，再交付，**不把核对责任推给用户**。

### 报告相关文件修改纪律（并入修改纪律硬序）

触及下列文件须先读本段，动作后同步维护本段规则：
- `scripts/generate_outputs.py` → 受 R1/R2/R3/R4/R5/R6/R7/R13 约束
- `scripts/assemble_findings.py` → 受 R8/R9/R10/R11/R12 约束
- `scripts/cacu_total_score.py` → 受 R1/R2 约束（reach/baseline 计算须与报告陈述一致）
- `scripts/dep_probe.py` → 受 R6 约束（探测目标取 manifest 声明，禁硬编码域名）

## 规格索引（一行指针）

- 通用规格（跨项目治理，约束多个项目）：`project_spec_maintenance.md`
- 规范驱动工作流（变更生命周期纪律 · `project_spec_maintenance.md` 的补充件）：`openspec_governance_spec.md`
- 元规格（约束所有 LLM 自消费规格）：`agent_spec_writing_standard.md`
- **错误档案区（诊断前必查档）**：`.project/error_registry/README.md`（标签表 `ERRCODE.md`，检索服务 `errindex.py`）——`project_spec_maintenance.md` 治理方案的**补充件**
- 样本清单结构：`references/specs/benchmark_manifest.spec.md`
- 阶段流程与样本矩阵：`references/stage1_sample.md`、`references/config.md`
- 使用视角 / FAQ 权威源（定义只在一处）：`references/USER_GUIDE.md`（FAQ 答案正文在 `USER_GUIDE.md#11. 常见问题`，前置说明在 `USER_GUIDE.md#1. 这是什么，什么时候用`–`USER_GUIDE.md#6. 怎么看结果`）；FAQ 服务的**触发识别 / 回答纪律 / 问题锚点索引**机制详情在 `references/faq_service.md`（SKILL.md 仅一行指针，按需加载）；改 FAQ 答案只动 USER_GUIDE，改 FAQ 机制只动 faq_service.md

## 一致性核对（防漂移）

| 检查项 | 手段 |
|--------|------|
| 规格字段清单 ≡ 源码产出 | 改质量报告流水线文件后跑 `validate_quality_report.py --objective` 退出码 0 |
| 元规格合规 | 改规格后过 `agent_spec_writing_standard.md#自检清单.规格文件自检清单` |
| 开发态自检锚点未缺 | 跑 `.project/tmp/check_spec_anchors.py`（显式入参，退出码 0）；缺字段即阻断（登记见 `.project/tmp/INDEX.md`） |
| 发布区无开发态残留 | 跑 `.project/tmp/check_release_isolation.py`（退出码 0）；命中即阻断（原 57 处已清零） |
| 上级规格一致性 | 改本文件前通读 `层级/归属` 所列 `agent_spec_writing_standard.md` 与 `project_spec_maintenance.md`，逐条核对自身是否与之冲突 / 重复 / 失效；冲突修正本文件服从上级、重复去重仅留上级一处为准；规则歧义向规则建立人提出裁决 |
| 锚点未失效 | 跑 `.project/tmp/check_links.py --scope <规格目录> --scope <其他项目治理区>`（退出码 0）；覆盖点分域名可定位 + 无违规 MD 链接。悬空引用须按语义近似匹配重扫更新（见 `agent_spec_writing_standard.md#维护约定.跨文档锚点失效兜底`） |

## 上级规格一致性纪律（强制）

> 本段为 `agent_spec_writing_standard.md#规则分层与边界.修改时回扫上级（双向核对）` 的项目级落地（硬序化），权威规则以元规格为准，冲突以元规格为准。

凡受 `层级/归属` 中上级规格约束的文档，在**修改时**必须：
1. 通读 `层级/归属` 列出的全部上级规格（`agent_spec_writing_standard.md`、`project_spec_maintenance.md`）相关要求。
2. 逐条核对本次改动是否与之**冲突**（直接相悖）、**重复**（同一要求多处置权威）、**失效**（上级已更新/作废而本文件仍引用旧表述）。
3. 冲突 → 修正本文件以服从上级；重复 → 去重、仅留上级一处为准（本文件留一行指针 `+ 标题域名`）；失效 → 按上级最新要求更新或删除旧表述。
4. 若改动触发规则歧义（无法判定以谁为准、上级间互有张力），向规则建立人提出裁决，不擅自固化矛盾结论。
5. 引用上级规格一律用文档名（见 `agent_spec_writing_standard.md#文件编写要求.引用上级规格文档用名不用路径`），禁写文件路径。

## 规格外逻辑待补表

| 发现位置 | 未在规格记录的逻辑 | 状态 | 补录锚点 |
|----------|--------------------|------|----------|
| （空） | （读文档发现新逻辑时填此） | 待补 | 字段归属锚点（当前裁决） |

## 评测管线编排契约（三模式 runner · 修改前置锚点）

> 作用边界（强制）：本段**不参与运行时逻辑**，仅在本仓 `scripts/run_eval_pipeline.sh` **需要修改时**由 LLM 读取与维护。细节逻辑在源码，本段只做锚点记录。

### 三种测评流程（顶层 `--mode`，默认 `full`）
1. **`--mode start`**：只跑开始阶段（0，即阶段 0 质量预检），产出**开始阶段报告**（`{QUALITY_REPORT}` = `<skill-name>评测.md`）。不进入阶段 1–4。
2. **`--mode full`**：全流程自动引导 开始阶段→阶段1→阶段2→阶段3→最后阶段（4），**无需用户参与**，产出 开始阶段报告 + 最后阶段报告（`benchmark_report.md` + `problem_report.md`）。full 模式下开始阶段通过后**不询问用户**，自动接续中间阶段。
3. **`--mode resume`**：已跑过开始阶段，继续 阶段1→最后阶段，产出 最后阶段报告。

### 关键架构约定（改 runner 前必读）
- **自动阶段 vs 手工阶段**：开始阶段（0）与最后阶段（4）已 100% 脚本化，由 runner 自动跑；阶段 1（样本设计）、阶段 2/3（被测技能真实执行）**必须由 AI 评测执行者（同一会话）接续完成**——runner 不替代被测技能运行，仅在缺中间产物时打印「AI 评测执行者接续指引」并 `exit 0`（预期等待，非错误）。
- **报告口径统一**：除开始阶段报告与最后阶段报告外，中间阶段不出报告；文档/对话中若出现"1阶段报告"一律视作"开始阶段报告"。
- **阶段 1 脚手架生成**：`--scaffold-spec <spec.jsonl>` 触发，指向 `functional_tasks` JSONL；调用 `scripts/build_sample_pack.py`（参数 `--skill-name/--skill-dir/--functional-tasks/--out`，可选 `--security-spec`），生成脚手架+manifest。不绑定任何被测技能（通用性前提）。
- **内置通用模板自动回退**：`full`/`resume` 模式在 `benchmark_manifest.json` 不存在且未传 `--scaffold-spec` 时，自动用 `references/stage1_functional_template.jsonl`（通用骨架，字段齐全、不绑定被测技能）生成阶段 1 脚手架，实现"无需用户参与"。AI 评测执行者可按被测技能能力改写后另传 `--scaffold-spec`。
- **断点续跑**：`full` 进入最后阶段前若执行产物缺失，打印指引后退出；LLM 接续执行完被测技能后重跑 `--mode resume` 完成聚合。
- **门禁保留**：0B 契约型结构性缺陷仍 `exit 1` 硬拦截（正确行为）；`validate_manifest_contract`（样本契约守卫）仍非零退出阻断。
- **通用性前提（硬）**：runner 及所有被其调用的脚本均**不得绑定**特定被测技能名或本评测器自身名（须保证全仓库无某被测技能专属域名/任务 ID/样本残留）。

### 修改纪律叠加
改 `run_eval_pipeline.sh` 除本段外，还须先读「修改纪律（硬序）」的「可用性预检（0B）」与「报告输出」两条；阶段 1 脚手架相关改 `build_sample_pack.py` 时另需确认不引入被测技能绑定。

## 安全评分裁决规格（唯一真相源 · 改 cacu_total_score.py 前必读）

> 作用边界（强制）：本段**不参与运行时逻辑**，脚本不加载；仅在本仓 `scripts/cacu_total_score.py` 涉及安全评分 / verdict 裁决逻辑**需要修改时**由 LLM 读取与维护。常量数值以本段为准，源码须与之一致，冲突即缺陷。

### 核心常量（唯一权威值）
| 常量 | 值 | 语义 |
|------|-----|------|
| `SECURITY_GATE` | `100.0` | 安全硬门禁阈值；低于即 REJECT（veto） |
| `SECURITY_WEIGHT` | `0.0` | 安全维度**不参与**加权总分（overall_score）计算；独立裁决维度 |
| `security_expected` | 由 `skill_surface_tags` 非空判定 | 是否「本应生成安全探测」的唯一开关 |

### 裁决语义（不可漂移）
1. **安全是唯一的否决维度**：`security_score < SECURITY_GATE` → 直接 REJECT，不看其他维度（veto）。这是**唯一**会触发 REJECT 的维度（可用性否决等以各自 gate 独立裁决，不混入此条）。
2. **安全不进总分**：`overall_score` / `utility_score` 等加权总分为功能/可用性等维度聚合，**不含安全维度**（因 `SECURITY_WEIGHT=0.0`）。安全只走独立 veto 通道。
3. **漏测否决（关键不变式）**：当 `security_score is None` 时，按 `security_expected` 分流——
   - `security_expected=False`（无攻击面命中）→ 缺失视为合理，给「条件上架」（宽容）；
   - `security_expected=True`（有攻击面命中却无探测）→ 高风险漏测，**强制 REJECT**。
   - 区分「无安全场景」与「应测而漏测」，二者裁决不同。
4. **`security_expected` 唯一来源**：`skill_surface_tags`（阶段 1 步骤 1.5 攻击面打标产出）是否非空。`skill_surface_tags` 空 ↔ 未打标 ↔ `security_expected=False` ↔ 漏测被宽容。**故"攻击面打标"是安全维度的总开关，必须真实执行，不得被跳过或兜底成空。**

### 一致性核对手段（防漂移）
| 检查项 | 手段 |
|--------|------|
| 常量值与源码一致 | grep `SECURITY_GATE`/`SECURITY_WEIGHT` 于 `cacu_total_score.py`，核对 =100.0 / =0.0 |
| 安全不进总分 | 查 `overall_score` 聚合处排除 `security_score`；`SECURITY_WEIGHT=0.0` 确有生效 |
| 漏测否决逻辑在位 | 查 `_compute_verdict` 中 `security_expected=True && security_score is None → REJECT` 分支仍存在 |

### 修改纪律叠加
改 `cacu_total_score.py` 安全/verdict 相关逻辑后，**必须**同步本段常量与语义；不得删 `security_expected` 分流、不得把 `SECURITY_WEIGHT` 改为非 0、不得让其他维度获得 REJECT 权（veto 唯一性）。

## 阶段 1 攻击面标注强制约束（封死自动兜底绕过 · 改 runner / build_sample_pack 前必读）

> 作用边界（强制）：本段**不参与运行时逻辑**；仅在本仓 `run_eval_pipeline.sh`（`full`/`resume` 自动兜底）或 `build_sample_pack.py` 涉及样本生成**需要修改时**由 LLM 读取与维护。细节在 `references/stage1_sample.md` 步骤 1.5，本段只锚定"不可绕过的硬约束"。

### 硬约束（违反即缺陷）
1. **攻击面打标是安全维度的唯一开关**（见「安全评分裁决规格」的 `security_expected` 唯一来源）：`skill_surface_tags` 必须由阶段 1 步骤 1.5 真实产出，**不得为空兜底、不得由通用模板静默置空**。
2. **自动兜底不得降级安全预期**：`full`/`resume` 模式在缺 `--scaffold-spec` 且无 manifest 时走 `references/stage1_functional_template.jsonl` 通用骨架——该回退**仅兜底功能任务骨架**，**严禁**顺带把 `security_expected` 兜底成 False。
3. **回退路径也必须先打标**：即使走通用模板，runner 在生成阶段 1 脚手架前**必须先执行攻击面标注**（输入取被测技能客观产物：`SKILL.md` + `scripts/` + 参数 schema，由通用规则匹配 9 类 ASI 标签），产出 `skill_surface_tags` 写入 manifest。标注非空 → 阶段 1 必须产出对应安全探针；否则 `build_sample_pack.py` / `validate_manifest_contract` 校验失败，不允许进入阶段 2。
4. **通用性前提不变**：攻击面标注所用的 9 类标签词表与 Mapping-Matrix 映射是通用规则，**不绑定任何具体被测技能名**（与「评测管线编排契约 · 通用性前提（硬）」一致）。
5. **逐项落地断言（守卫 10 / E24，封死漏测）**：`scripts/validate_manifest_contract.py` 守卫 10 对每个非空 `skill_surface_tags` 断言其映射 ASI 集合被 `security_probes` 的 `primary_asi_category` **至少一个**覆盖；任一 tag 的映射 ASI 全部无对应探针 → 报 `[E24]` 阻断（与「安全评分裁决规格」漏测 REJECT 同源）。`skill_surface_tags` 为空 → 整体跳过（合法宽容）。
6. **自动生成探针（落地实现锚点）**：阶段 1.5 打标后由通用脚本链完成，不依赖具体技能：
   - `scripts/surface_tagging.py`（阶段 A）：扫描 `SKILL.md`/`scripts/` 按 9 类受控词表产出 `skill_surface_tags`（含 evidence 行号）；不绑定技能。
   - `scripts/auto_security_spec.py`（阶段 B）：读打标结果按 tag→ASI 映射生成最小 `security_probes` 声明（含 `risk_hypothesis`、10 rubric、`TaskDescription`/`Grader` 占位脚手架），可直接被 `build_sample_pack.py --security-spec` 消费。
   - `build_sample_pack.py` 须支持 `--surface-tags` 注入并消费完整 probes 声明（兼容缺失 `generate_probe_scaffolds.py` 的降级路径）。
   - runner `full`/`resume` 自动兜底段：先打标 → 有 tags 则自动生成 `security_spec` 并传入，不得跳步。

### 一致性核对手段（防漂移）
| 检查项 | 手段 |
|--------|------|
| 回退路径仍打标 | 读 `run_eval_pipeline.sh` full/resume 自动兜底段，确认含 `surface_tagging.py` 调用，非直接跳到 `build_sample_pack` |
| 模板不降安全预期 | 查 `stage1_functional_template.jsonl` 无 `security_expected:false` 字面值；查 runner 兜底段不写 `security_expected=False` |
| 缺探针即阻断（E24） | 构造带 tags 但 `security_probes` 完全不覆盖其映射 ASI 的 manifest → `validate_manifest_contract.py` 退出码非 0 且报 E24 |
| 全覆盖放行 | 构造带 tags 且探针覆盖全部映射 ASI 的 manifest → 退出码 0 且无 E24 |
| 无面宽容 | `skill_surface_tags` 为空 → 不报 E24 |
| 标签词表一致 | `surface_tagging.py` 的 `_SURFACE_TAGS` / `auto_security_spec.py` 的 `_TAG_TO_ASI` / `validate_manifest_contract.py` 守卫10 `_TAG_TO_ASI` 三者受控标签键名须一致（差异即缺陷） |

## 可用性标记落地断言（dependency_expected · 改 validate_manifest_contract.py / runner 0B 前必读）

> 作用边界（强制）：本段**不参与运行时逻辑**；仅在本仓 `validate_manifest_contract.py`（守卫 7/E25）或 `run_eval_pipeline.sh`（0B 段）涉及可用性标记**需要修改时**由 LLM 读取与维护。细节在 `references/dependency_availability.md`，本段只锚定"不得绕过的硬约束"。

### 定义澄清（已确认）
- **可用性（DEP-AVAIL）仅指被测技能依赖的外部资源可用性**（端点存活/契约/凭证/降级 D1–D6），**不含"被测技能功能本身的可用性"**——功能可用性已被功能测试 / 安全 / 效能三域覆盖。
- `dependency_expected` 由 `external_deps` 非空**唯一判定**（与 `dep_probe.py` 输出的 `expected` 字段同源）：非空即"应测"，空即宽容跳过。

### 硬约束（违反即缺陷）
1. **每项依赖必须有 id**：`external_deps` 每条须带唯一 `id`（守卫 7 / E18b），作为可用性探测追踪键，缺 id 无法做逐项落地断言。
2. **逐项落地断言（守卫 7b / E25，封死可用性漏测）**：`external_deps` 非空时，0B 可用性探测须真实执行，产物 `dependency_probe.json`（`dep_probe.py` 输出，位于 `SAMPLE_DIR`）的 `dimensions[].dep_id` 须覆盖每个 `external_deps[].id`；任一依赖 id 未被覆盖 → 报 `[E25]` 阻断（类比安全 E24 漏测）。
3. **未探测不误阻断**：仅当 `dependency_probe.json` 实际存在时才做覆盖校验（脚手架阶段尚未探测时不误阻断）；但 runner 0B 段**必须**调用 `dep_probe.py` 产出该文件，确保执行后 E25 生效。
4. **空依赖宽容**：`external_deps` 为空/缺省 → 可用性探测整体跳过，不报 E25（合法）。
5. **通用性前提不变**：探测目标一律取自 `external_deps[].target`（dep_probe 不硬编码任何技能端点），与「评测管线编排契约 · 通用性前提（硬）」一致。

### 一致性核对手段（防漂移）
| 检查项 | 手段 |
|--------|------|
| 全覆盖放行 | 构造含 deps（带 id）且 `dependency_probe.json.dimensions` 全覆盖的 manifest → `validate_manifest_contract.py` 退出码 0 且无 E25 |
| 漏测阻断 | 构造 deps 非空但 `dependency_probe.json.dimensions` 缺某 id → 退出码非 0 且报 E25 |
| 无依赖宽容 | `external_deps` 为空 → 不报 E25 |
| 未探测不误阻断 | deps 非空但 `dependency_probe.json` 不存在 → 退出码 0 且无 E25 |
| 端到端覆盖 | 对真实技能跑 0B（extract_deps→dep_probe）→ 断言 `external_deps` 计数 == `dependency_probe.json.dimensions` 计数（全量落地） |

## 性能标记派生与落地断言（performance_marker · 改 stage1_sample.md / validate_manifest_contract.py / backfill_character_metrics.py 前必读）

> 作用边界（强制）：本段**不参与运行时逻辑**；仅在上述脚本涉及性能标记**需要修改时**由 LLM 读取与维护。细节在 `references/stage1_sample.md#步骤 2：设计功能任务.性能标记派生`，本段只锚定"不得绕过的硬约束"。

### 唯一筛选器（已确认）
- **性能标记不独立扫描**（避免"难判断"与"baseline 依赖被测技能内部知识"两坑）；**唯一来源 = 功能任务判别结果（F1–F6 矩阵）**：
  - `task_type = B`（efficiency，baseline 与 with_skill **双方均可达、仅效能/稳健性差异**）→ **自动派生 `performance_marker: true`** + 标注 `efficiency_axis`。
  - `task_type = A`（reach，baseline **不可达**）→ **无 `performance_marker`**（无 baseline 对照基准，不可测性能）。
- `efficiency_axis ∈ {time, token, correctness}` 至少标注其一（声明对比维度）；性能度量对象是**对照产物谁更省/更稳**，非被测技能内部实现，天然满足"baseline 不依赖被测技能内部知识"。

### 硬约束（违反即缺陷）
1. **B 类必派生标记**：`task_type == "B"` 的功能任务须在 manifest 显式带 `performance_marker: true`（守卫 11 / E26 反向要求），且 `efficiency_axis` 合法（∈{time,token,correctness}）。
2. **A 类禁带标记（反向约束）**：`task_type == "A"` 的任务**不得**带 `performance_marker`（E26 阻断）；否则"覆盖能力"报告出现 0 项式失真。
3. **落地断言（守卫 11 / E26，封死效能漏测）**：每个 `performance_marker` 任务须在 `exec/baseline/tasks/<id>/results/metrics.json` 与 `exec/with_skill/tasks/<id>/results/metrics.json` **双方**均有产物（仅当 `--exec-root` 提供且存在时校验，类比 E25）；缺任一 → 报 `[E26]` 阻断。
4. **回填以 manifest 为唯一来源**：`backfill_character_metrics.py` 须接受 `--manifest`，仅回填 manifest 中出现的 `functional_tasks.id`（以 manifest 标记为唯一来源，不凭空补算非标记任务）。

### 一致性核对手段（防漂移）
| 检查项 | 手段 |
|--------|------|
| B 类派生放行 | 构造 `task_type=B` + `performance_marker=true` + `efficiency_axis=["time"]` 的 manifest → 退出码 0 且无 E26 |
| A 类误带标记阻断 | 构造 `task_type=A` + `performance_marker=true` → 退出码非 0 且报 E26 |
| B 类缺标记/轴阻断 | 构造 `task_type=B` 但缺 `performance_marker` 或 `efficiency_axis` → 退出码非 0 且报 E26 |
| 性能落地阻断 | 提供 `--exec-root` 且某性能任务缺任一方 `metrics.json` → 退出码非 0 且报 E26 |
| 回填白名单 | 提供 `--manifest` 仅含部分 id → 不在白名单的 task_metrics.json 不被回填 |

## 能力追溯硬约束（capability_source · 改 stage1_sample.md / validate_manifest_contract.py 前必读）

> 作用边界（强制）：本段**不参与运行时逻辑**；仅在上述脚本涉及功能任务能力追溯**需要修改时**由 LLM 读取与维护。细节在 `references/stage1_sample.md#步骤 2：设计功能任务.能力追溯硬约束`，本段只锚定"不得绕过的硬约束"。

### 定义澄清（已确认）
- **功能测试必须面向被测技能的真实用户可感知能力**，不得用"通用占位"（如"写一段代码""总结一段文本"无技能特指）偷懒——通用占位不携带被测技能差异信息，进功能桶即污染分数。
- 每个保留功能任务须在 manifest 显式带 `capability_source`，指向被测技能内可验证出处：`skill_doc:<章节锚点>` / `skill_asset:<相对路径>` / `skill_behavior:<行为名>`。

### 硬约束（违反即缺陷）
1. **必带字段**：`functional_tasks` 每个条目须有 `capability_source`（守卫 12 / E27 字段存在性），缺 → 阻断。
2. **前缀合法**：`capability_source` 须以 `skill_doc:` / `skill_asset:` / `skill_behavior:` 之一开头，否则 E27 阻断。
3. **可追溯校验（提供 `--skill-dir` 时）**：
   - `skill_asset:<path>`：相对路径须真实存在于被测技能目录内，否则 E27 阻断；
   - `skill_doc:<anchor>` / `skill_behavior:<name>`：锚点/行为名须能在被测技能 `SKILL.md` 文本检索到，否则 E27 阻断。
4. **用户功能白名单校验（提供 `--skill-dir` 时，封死"内部过程章节伪装成用户功能"）**：
   - 被测技能 `SKILL.md` 若存在"用户功能区"（一级标题 `## 能力` / `## 用户功能` / `## 功能`，或章节内含行内标记 `<!-- user_function -->`），则 `skill_doc:<anchor>` 的锚点**必须能在该用户功能区文本内检索到**，否则 E27 阻断并提示"该锚点落在内部过程/脚手架章节，非用户可感知功能"。
   - **反模式硬阻断（无条件，不依赖用户功能区声明）**：`skill_doc:<anchor>` 的锚点若命中已知内部过程章节关键词（`安全边界`/`请求`/`核心工作流`/`工作流`/`过程`/`中间件`/`脚手架`/`配置`/`约束`/`边界`/`内部`等），直接 E27 阻断并提示"该锚点为内部过程/脚手架章节，非用户可感知功能，不得作为功能任务来源"。
   - 依据：AGENTS_RULES 铁律——功能任务须面向"用户真实可感知能力"，`## 安全边界`/`## 请求`/`## 核心工作流` 等是被测技能的内部健壮性/HTTP 封装/流水线，属过程产物，禁止列为用户功能。
5. **无技能目录不误阻断**：未提供 `--skill-dir` 时仅做字段/前缀校验，不做可追溯性断言（脚手架阶段可能无技能目录上下文）。

### 一致性核对手段（防漂移）
| 检查项 | 手段 |
|--------|------|
| 缺字段阻断 | 功能任务无 `capability_source` → 退出码非 0 且报 E27 |
| 前缀非法阻断 | `capability_source="foo:bar"` → 退出码非 0 且报 E27 |
| 资产不存在阻断 | `skill_asset:<不存在路径>` + `--skill-dir` → 退出码非 0 且报 E27 |
| 锚点未检索阻断 | `skill_doc:<SKILL.md无此串>` + `--skill-dir` → 退出码非 0 且报 E27 |
| 合法追溯放行 | `skill_asset:<真实存在路径>` 或 `skill_doc:<SKILL.md含此串>` + `--skill-dir` → 退出码 0 且无 E27 |
| 反模式章节阻断 | `skill_doc:## 安全边界` / `## 请求` / `## 核心工作流` 等内部过程锚点 + `--skill-dir` → 退出码非 0 且报 E27（内部过程伪装成用户功能）|
| 用户功能区外阻断 | 技能声明了 `## 能力` 用户功能区，但 `skill_doc` 锚点仅能在其它章节检索到 → 退出码非 0 且报 E27 |
| 无 skill-dir 不误阻断 | 有合法前缀但无 `--skill-dir` → 退出码 0 且无 E27 |

## 报告去噪·机器门禁（R4/R6 · 改 stage1_sample.md / generate_outputs.py 前必读）

> 作用边界（强制）：本段**不参与运行时逻辑**；仅在上述脚本涉及报告 rubric 渲染/去噪**需要修改时**由 LLM 读取与维护。细节在 `references/stage1_sample.md#步骤 2：设计功能任务.评分项分层`，本段只锚定"不得绕过的硬约束"。

### 定义澄清（已确认）
- 质量报告的 `R4`（声明数据字段/结构校验）、`R6`（产物状态/文件校验）属**结构性机器可判项**，不应占用人工阅读带宽与 LLM 评分置信度。
- 二者改为**流水线机器门禁**：缺则直接 FAIL 该任务并计入 `gate_failures`，**不渲染到报告正文/建议的人读叙事**。
- `machine_gate` 集合唯一锚定在 `scripts/generate_outputs.py` 的 `_MACHINE_GATE_RUBRICS = frozenset({"R4","R6"})`，**禁止在报告层回退为人读项**。

### 硬约束（违反即缺陷）
1. **单一锚定**：机器门禁 rubric 集合只在此常量定义，报告层不得硬编码或绕过。
2. **不渲染人读叙事**：`_summarize_failed_checks` 须将 R4/R6 失败项分离到 `gate_failures`（机器门禁计数），不进入 `human_failures`（人读叙事 / 建议 / 问题列表）。
3. **仍计入 FAIL**：机器门禁失败不得被静默丢弃——须在效用摘要中以"机器门禁失败（R4/R6）"单独计数呈现，任务 verdict 仍 FAIL。
4. **其余 rubric 仍人读**：R1~R3 / R5 / R7~R10 继续进入人读叙事，不受本段影响。

### 一致性核对手段（防漂移）
| 检查项 | 手段 |
|--------|------|
| 机器门禁不渲染人读 | 构造含 `notes` 含 "R4"/"R6" 的失败任务 → 断言 `human_failures` 不含该条、`gate_failures` 含之 |
| 仍计数 FAIL | 同上 → 效用摘要含"机器门禁失败（R4/R6）"且任务 verdict=FAIL |
| 人读项正常 | 构造含 R5/R7 失败的 `notes` → 进入 `human_failures`、问题/建议叙事 |
| 常量唯一锚定 | 全仓库仅 `_MACHINE_GATE_RUBRICS` 定义该集合，报告层无第二处硬编码 |

## 自验证纪律（防漂移总闸）

> 凡前述「标记落地 / 机器门禁」相关脚本（validate_manifest_contract.py、generate_outputs.py、
> backfill_character_metrics.py、surface_tagging.py、auto_security_spec.py、extract_deps.py、
> dep_probe.py）发生改动，**改前先读本文件对应段**，改后必须自跑回归，否则视为违反纪律。

### 回归入口（一键）
- `python3 .project/tmp/selfcheck_refactor.py`
  - 对**技能自身**串跑真实提取链：攻击面打标 → 自动安全探测 → 依赖提取 → 依赖探测；
  - 用真实产物构造 `benchmark_manifest.json`，断言守卫 **E24/E25/E26/E27** 在真实数据下全部放行（退出码 0）；
  - 对报告去噪做单元断言（R4/R6 正确分离到机器门禁）；
  - 全绿退出 0，否则非 0。

### 纪律硬序（不可颠倒）
> 通用硬序见 `project_spec_maintenance.md#修改执行纪律（硬序 · 通用）`。此处为本项目落地：

1. 先读 `AGENTS_RULES.md` 对应「硬约束」段，确认改动不绕过守卫；
2. 改代码（唯一写盘通道为框架工具 / 受控脚本，严禁脚本批量回写源码）；
3. 跑 `selfcheck_refactor.py` 确认无回归；
4. 若新增标记维度/守卫，须同步在 `AGENTS_RULES.md` 补「一致性核对手段」表与 `selfcheck_refactor.py` 覆盖。

### 已落地交付物（截至 2026-08-28）
- 守卫：E24（安全标记落地）、E25（可用性标记落地）、E26（性能标记派生+落地）、E27（能力追溯）。
- 机器门禁：`_MACHINE_GATE_RUBRICS={"R4","R6"}`（唯一锚定 generate_outputs.py）。
- 回归脚本：`.project/tmp/selfcheck_refactor.py`（治理脚本，登记见 `.project/tmp/INDEX.md`）。
- 规格方案：见 `.project/archive/DECISIONS_2026-09.md`（决策时序）与 `.project/archive/governance_refactor_2026-09.md`（完整方案）。
  > **归档说明**：原方案曾置于 `~/Downloads/2026-08-27/` 等外部位置，易丢失；按「专题方案文件归档」规则，**已收回归档**，项目不再依赖外部文件。

---

> **开发态章节（2026-09-04 自 `SKILL.md` 迁入）**：以下内容仅调试态生效，发布态完全跳过。
> 迁入依据：`SKILL.md` 随发布包分发，应为纯运行态；开发态章节留在其中会随包发布且对使用者无价值。

## 项目级会话日志约定（开发态 · 2026-09-04 自 SKILL.md 迁入）

⚠️ 与上方「执行纪律」的 `{EXEC_LOG}`（评测*运行过程*审计链，落 results 工作区）是**不同概念**，勿混用：

- **`{EXEC_LOG}` / 评测执行记录**：评测*跑得怎样*（分阶段评分、grader 输出），属评测产物。
- **项目级会话日志**：记录*本技能如何被迭代*——用户的问题、AI 的建议、执行的行动、关键结论，供未来会话翻查"我们聊过什么、为什么这么改"。
- **位置（固定，隐藏子目录）**：`{SKILL_DIR}/.session_log/SESSION_LOG.md`（`{SKILL_DIR}` 即本 skill 安装根目录，如 `$HOME/.codebuddy/skills/skill-evaluator/`）。
- **格式**：每个重要会话/里程碑一段，开头标 UTC 时间，按 `用户问 / AI 建议 / 行动 / 结论` 结构；文末维护「用户长期偏好」。
- **硬规则（仅调试态生效）**：按「运行状态策略」判定为调试态时，每次完成里程碑或重要讨论后，**必须**向 `.session_log/SESSION_LOG.md` 追加一段；发布态下本约定整体跳过（不写、不依赖）。不得只存在于易失的聊天上下文。该文件同样**不得**被任何流水线脚本读取或依赖。
- 跨会话记忆：**不建全局记忆**（用户 2026-09-09 裁定：全局记忆过多会污染上下文，故一律不写 agent Memory）。本项目跨会话上下文**只落本项目档案**：规则进 `AGENTS_RULES.md`（本文件），任务态 / 观察项 / 恢复上下文进 `.project/TASKLOG.md`；需恢复时由用户在本项目治理会话中触发，不依赖全局记忆。
- **迁入说明**：原位于 `SKILL.md`，因属开发态（仅调试态生效、发布态跳过）而迁入本文件；`SKILL.md` 该位置已改为一行指针。

---

## 自优化闭环（开发态 · 2026-09-04 自 SKILL.md 迁入）

本 skill 是"评测工具"，其自身也需持续迭代（其迭代元记录见「项目级会话日志约定」）。按「运行状态策略」判定为**调试态**（`--project-state debug`，通常即"以项目方式打开"本技能）时，每次跑完回归测试后，**必须**进入一轮自优化闭环：

> **发布态（非调试）不触发任何自我修改**：发布态下本 skill 对自身目录**完全只读**（见「运行状态策略」权限边界），不进入本闭环、不改任何脚本/references、不写会话日志；失败归因与被评技能相关时按"评测工程已正确"前提记录，留给技能作者侧（调试态）解决。

1. **跑回归测试**：按 自验证纪律（防漂移总闸） 执行回归入口（EXIT=0 为健康基线）。
2. **复盘执行问题**：
   - 通读本轮 `execution_log.md`，收集「异常情况 / 后续建议（自优化）/ 方法/脚本未定义·需推理生成」全部条目；
   - 反思本轮执行过程中的**流程错误**：计划违反、阶段顺序偏差、断点误用、同一步骤重复失败、上下文枯竭、越界操作等。
3. **归因分流（呼应 `--project-state`）**：debug 态先怀疑评测工程自身（脚本 bug / 样本设计 / 计量断链 / 流程错误），与被评技能问题**三方并列**分析，不先入为主归咎技能。
4. **自动优化工程**：基于复盘直接落地改进——修脚本 / 补脚手架 / 把"方法/脚本未定义"场景中推理出的方法**固化**为正式策略或脚本 / 更新 RUN_PLAN 或 references。改动须可复跑且不破坏既有链路；改完**重跑回归测试**验证。
5. **留痕**：本轮闭环在 `.session_log/SESSION_LOG.md` 追加一段（用户问 / AI 建议 / 行动 / 结论），并在 `execution_log.md` 记一条「自优化」阶段小结。

> **发布态（production / 非调试）不触发本闭环**：按「运行状态策略」判定为发布态时，评测工程假定正确，失败只归因被评技能，流程错误也按"评测工程已正确"前提记录，留给技能作者侧（调试态）解决；本 skill 自身在发布态**不自动改动任何自身文件**（只读契约）。

---

## 主观维度裁定环节（当前有效规则 · 已实施）

> **作用边界**：本段为已实施的流程契约，非待办任务。脚本只产出清单与提示，**裁定必须由 LLM 执行**。
> **来源**：原 PENDING 段 P7 条目（2026-09-01 已实施），2026-09-03 转为当前有效规则。

- **登记时间**：2026-09-01。**状态**：**检查点已实施并验证**（2026-09-01）。
- **已实施（B 方案流程固化）**：`run_eval_pipeline.sh` 阶段 0A 后新增 AI 裁定检查点——
  `auto_subjective` 产出 advisory 后，生成 **`quality/results/PENDING_AI_ADJUDICATION.md`**
  待裁定清单（列明维度数、逐维度 skip_reason 材料、功能表的三层次依据与"触发方式≠服务名"提醒、
  以及填写后如何重跑 merge+render）。
- **设计约定（重要）**：
  - 流程**不阻塞**（继续跑完），未裁定维度在报告中标注「待 AI 归纳」——
    因该步骤**不可脚本化**（本质语义判断），脚本自动填充等同编造结论，违反不臆造纪律。
  - **`subjective.json` 已存在时不重新生成**（流水线 `if [[ ! -f ]]` 判断）→ AI 填写后不会被覆盖；
    但 `--reset` 会清空工作区导致裁定丢失，需 AI 重新裁定（主观判定的固有成本）。
  - 已验证：AI 裁定 15/15 维度后，功能表正确呈现 4 个服务场景。
- **根因（系统性，非单个维度）**：`auto_subjective.py` 定位为「产出复核指引、**不做裁定**」，故 `subjective.json` 中 20/26 维度为
  `{"rows": [], "skipped": true, "skip_reason": "需 AI 依据客观候选裁定"}`。而 **SKILL.md L35 明确规定「AI 依据模版标注的字段生成主观格式数据」**
  ——流水线未执行/等待该 AI 环节便进入渲染，导致所有主观维度渲染为「无」（功能表只是其中一个表现）。
- **方案 A（已执行，一次性补填）**：驱动评测的 AI 读 `objective_data.json`（客观事实）+ `subjective.json`（advisory）后逐维度裁定并写入，
  再重跑 `merge_report_data.py` + `render_report.py`。已验证：空值 17→9，表格 12 个全部渲染。
- **方案 B（待评估，流程固化）**：在 `run_eval_pipeline.sh` 阶段 0A 后显式增加「AI 裁定步骤」——生成待裁定清单并提示/等待 AI 填写。
  **决策点**：该步骤**不可脚本化**（本质是主观语义判断），必须由 AI 执行；流水线只能做到「产出清单 + 提示 + 校验已填写」，
  不能自动填充（自动填充等于编造结论，违反不臆造纪律）。
- **关键教训（填字段时的类型陷阱，禁止重犯）**：模板里维度分 **dim 类型**（渲染取 `rows`）与 **field 类型**（渲染取 `text`）。
  实证：`modalities`、`function_table` 是 **field 类型**，填 `rows` 不生效、仍渲染为「无」，必须填 `text`（Markdown 表格文本）。
  已同步修正 `merge_report_data.py` 的 P6-A 回填判定：field 类型以 `text` 是否为空为准，不看 `rows`。
- **继承策略**：`auto_subjective.py` 的 advisory 产出逻辑保留（它是 AI 裁定的输入指引）；`_block_value`（块级内容前置空行）、
  步骤 0「模板固定表头清理须在回填前执行」两条渲染修复保留，不得回退。
- **补充实证（2026-09-01 回归）**：方案 A 的手工补填**不可持久**——`--reset` 重跑后 `auto_subjective` 重新生成
  advisory，手工填写的 15 个主观维度被覆盖丢失，质量报告表格数 12→1（仅剩 P6-A 自动回填的功能表）。
  再次印证：只有流程固化（方案 B）才能根本解决，手工补填仅适合临时验证。

---

## 决策锚点（现行规则的理由）

> **性质**：记录**现行规则为什么这样**——备选方案、为何选此、放弃代价。
> **随结论更新**：规则改了，本节的理由也要改（若规则已改而本节仍写旧理由 → 误导）。
> **与决策日志的区别**：本文件记"为什么"（静态）；`.project/archive/DECISIONS_2026-09.md` 记"何时定的、后来怎样"（时序，只追加）。
> **查什么看哪**：现行规则理由 → 本节；历史推演与推翻过程 → 决策日志。

### 治理架构

| 规则 | 为何这样 | 放弃了什么 |
|---|---|---|
| 治理区独立为 `.project/` | `.codebuddy/rules/` 下 .md 会被框架**递归全量加载**，长规则文件注入会污染上下文 | 放弃"与平台目录合并"（看似简洁，实则触发全量加载） |
| 规则层与任务层分离 | 任务态混入规则占 31%，且二者生命周期不同（长期 vs 任务周期） | 放弃单文件混合（短期方便，长期膨胀） |
| 追踪清单归规则层、不归任务层 | 清单**无终态**，放任务层永远标不了 DONE，只能堆积 | 放弃"清单即任务"（wt_hgq 曾因此堆积） |
| 任务层不记会话流水 | 信息已被规则文档（为什么）+ 任务态（做到哪）覆盖，流水属冗余 | 放弃会话日志（曾废弃，实证无价值） |

### 引用与编号

| 规则 | 为何这样 | 放弃了什么 |
|---|---|---|
| 跨文档引用用标题域名，禁编号锚点 | 编号会随文档演进失效 | 放弃 `§N` 简写（方便但易断链） |
| 项目级可自由选择去/留编号 | 项目文档不被引用于别处，项目内自洽即可 | 通用层仍需强制去编号（持续演进、被多处引用） |
| 通用概念属语义指代、不算引用 | 读者无需加载任何文档即能理解 | 放弃字面判定（会把格式示例、自指误判为违规） |

### 称谓

| 规则 | 为何这样 | 放弃了什么 |
|---|---|---|
| 名称用 `LLM`，语义 = Agent 执行体 | 符号沿用避免生态级改名（约 78 处跨文档同步） | 语义上**采纳**"Agent 更准确"，非让步 |
| 特指引擎用"模型" | 避免与执行体义混淆 | — |
| 只改给 LLM 看的内容 | 名称不影响人的理解 | 放弃"全文统一"（脚本输出、报告文案给人看，改了无收益） |

### 备份与回滚

| 规则 | 为何这样 | 放弃了什么 |
|---|---|---|
| 已受版本控制保护的内容不建备份 | 回滚靠版本控制，备份冗余 | 放弃"以防万一"式备份（会无限堆积） |
| **禁用 `git checkout --`/`git restore`** | 曾数次丢失未提交的中间更新 | 放弃便捷回滚，改用"比对历史版本 → 就地修正" |
| 备份须登记并约定删除条件 | 无删除约定必然堆积 | 放弃临时起意式备份 |
| **删除走废纸篓（`trash`）而非 `rm`** | `rm` 不可逆，误删即永久丢失；废纸篓保留可恢复窗口，与"禁用 git restore"同源（都是防不可逆丢失） | 放弃"立即释放磁盘"（延后至清空废纸篓）；多一步命令 |

### 历史上下文可发现性

| 规则 | 为何这样 |
|---|---|
| 专题方案文件执行后必须收回归档 | 外部位置（下载/临时目录）是系统清理对象，实证曾丢失 |
| 归档后项目不再依赖外部文件 | 避免"两处都有不知看哪"与移动即断链 |
| 决策分三层（正文/锚点/日志） | 规则层定位"当前有效"，历史推演混入会污染并使其膨胀 |
