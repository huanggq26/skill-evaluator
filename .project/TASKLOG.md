# TASKLOG（任务进度 · 可中断恢复）

> **读者=编辑者=LLM**。仅载**待办 / 进行中 / 阻塞**任务；已完成任务归档至 `archive/TASKLOG_YYYY-MM.md`。
> **本文件不记录会话流水**：续跑所需信息由任务态（做到哪）与 `.project/AGENTS_RULES.md`（为什么这么定）共同覆盖。
> 建立：2026-09-03（自原 `AGENTS_RULES.md` PENDING 段剥离）

---

## [待办] P1. 依赖维度数据层解耦：internal_resource 移出 dependency 维度（方案 B）

**登记**：2026-08-31 ｜ **状态**：**已转出至规范区变更**（2026-09-14 立项，本文件不再推进）

> **转出依据**：本任务改变 `dependency_score` 计算口径（对外可观察行为），按无双写纪律应由**规范区变更**承载，治理区任务记录不重复登记。
> **承接变更**：`openspec/changes/decouple-internal-resource-from-dependency/`
> **范围收敛**：原「方案 B（移入独立维度）」改为「保留探测、结果移出评分与否决、输出到独立字段」。依据：报告层文案早已声明「可用性评分只统计外部运行时依赖」（`generate_outputs.py:2704-2707`、`:2764-2765`），实现未兑现——本次是消除文案与实现的不一致，非改语义。
> 本条保留作历史索引（含继承策略 1–6 条，实施时在变更内逐条映射）。
**触发条件**：仅在"重大结构调整"或"依赖评分口径需根治"时启动；日常不主动改

**目标**：`internal_resource` 探测结果写入独立维度（如 `packaging`/`internal_integrity`），不再进 `dependency.dimensions` / `dependency_score` / `structural_veto`。

**锚点**：`scripts/extract_deps.py`、`scripts/dep_probe.py`、`scripts/cacu_total_score.py`、`scripts/generate_outputs.py`、`references/dependency_availability.md`

**执行中问题**：无（未启动）

**待处理问题**：
- 随包缺失是否还参与上架否决？规格本意（仅外部依赖可用性否决）是不否决，但原实现否决了 → **需人裁决**，且须写明文案，不得静默改语义。

**步骤**：
- [ ] 写"6 条历史策略 → 新结构落点"映射表，经确认
- [ ] 改 `dep_probe.py` 分流维度
- [ ] 改 `cacu_total_score.py` 的 expected + score + veto
- [ ] 改 `extract_deps.py` 标注产出用途
- [ ] 改 `generate_outputs.py` §5.1/§5.2
- [ ] 同步 `dependency_availability.md`（加"内部资源不属 DEP-AVAIL"条款）、`config.md`、`validate_quality_report.py` schema
- [ ] 回归：`selfcheck_refactor.py` + aihot 实例 + 至少 1 个"无外部依赖技能"，确认不退化（重点盯 expected 误判与否决语义）

**继承策略（改造时逐条映射，禁止重写丢失）**：
1. `dep_probe.py` L198 计分口径：`score=100 if (dims and failed==0) else (0 if structural_fail else (50 if dims else None))`；`internal_missing`/`internal_unreadable` 当前与 `contract_defect` 并列进 `structural_veto`（L195-196）
2. `cacu_total_score.py` L1156-1158 `dependency_expected` 防误判：解耦删 internal 后须保证"有内部资源但无外部依赖"的技能**不**被误判 `expected=False`→REJECT（用等价逻辑替代，不得简单删除该分支）
3. `generate_outputs.py` L2522-2523 skipped 文案：解耦后若只认外部，文案须改为仅外部口径
4. `generate_outputs.py` L2514-2538 口径说明：若删 §5.2，该句须相应调整，避免悬空引用
5. `_collect_internal_resources` 收集规则（`extract_deps` L119-141）：references/*.md 必读、assets/* 选读、SKILL.md/README.md 必读——若迁移须整体迁移
6. `_probe_internal_one` 判定（`dep_probe` L159-167）：存在+可读才 pass；权限/编码问题标 `internal_unreadable`

**约束**：与方案 A 可独立，A 不阻塞 B。启动前先读本库全部「硬约束」段与 `dependency_availability.md`。

---

## [待办] P3a. external_deps 误报过滤（无 scheme 相对路径误判）

> **拆分与过时清理（2026-10-09 核实）**：原 P3 含两部分。
> ②「无端点时安全探测 N/A 满分」**已关闭**——由 **T-08**（2026-10-07）以更优方案取代：不再计满分，而是标记 `excluded_from_scoring` 并从通过率**分子分母一并剔除**，消除「无攻击面反而满分」的语义倒置。证据：`exec_security_probes.py:104/142`、`cacu_total_score.py:942`、`backfill_reviews.py:206/229-230`。
> 原步骤中「输出 N/A 满分（`status=pass/na`）」的写法**本身即倒置，已废弃，不再执行**。本任务保留 ①。

**登记**：2026-09-01 ｜ **状态**：已评估，待实施

**目标**：消除两类误报——① 无 scheme 的相对路径被误判为外部依赖；② 无端点时安全探针全 fail（语义倒置）。

**锚点**：`scripts/extract_deps.py`（`_add` L163-168）、`scripts/exec_security_evidence.py`、`scripts/exec_security_probes.py`

**执行中问题**：无（未启动）

**待处理问题**：无

**根因（实测）**：
1. `_add` 对**无 scheme 的 target 也直接加入** external_deps → 文档相对路径/文件名（实证 `report.template.md`、`spec.md`）被误当外部依赖，0B 误触发、对无效 URL 探活。违背 SKILL.md L118「无 external_deps 完全不出网」。
2. 安全探针 `status=fail` **非真安全问题**：`exec_security_evidence` 因无端点跳过采集 → 无证据文件 → 10 探针 Grader 全判「结果文件缺失」（R1–R10）→ 全 fail。**无端点 = 无攻击面 = 无可采集证据**，按现状却得 0 分。

**步骤**：
- [ ] `extract_deps.py` `_add` 增守卫：无 scheme 且含路径分隔符或文件扩展名（`.md`/`.json`/`.py` 等）→ 弃
- [ ] **保留** `host.tld:port`（HOSTPORT_RE，无 scheme）与 `scheme://`（CONNSTR_RE）——**禁止一刀切要求 http(s)**，否则丢失 host:port 类真实依赖
- [x] `exec_security_evidence` 跳过时标记 `evidence_skipped` ✅ 已存在（`exec_security_probes.py:39-40` 检测）
- [x] ~~输出 N/A 满分（`status=pass/na`）~~ → **已废弃并取代**：该写法本身即语义倒置，改为 `excluded_from_scoring=True` 并从通过率分子分母剔除（T-08，2026-10-07）
- [ ] 回归：aihot（有端点、有证据、4/4 pass）不受影响

**继承策略（禁止退化）**：真有端点时的 fail 判定必须保留；仅对「证据采集被跳过/无端点」这一特定状态放行。

---

## [待办] P4. 可移植性机器路径检测误报修正

**登记**：2026-09-01 ｜ **状态**：已评估，待实施

**目标**：排除三类误报，保留真实硬编码路径的检测能力。

**锚点**：`scripts/extract_stats.py`（`MACHINE_PATH_PATTERNS` L106-115）

**执行中问题**：无（未启动）

**待处理问题**：无

**根因（实测）**：`MACHINE_PATH_PATTERNS` 逐行正则匹配，不区分「真实写死路径」与「文档举例/正则字符串/模板说明块」。实证误报：`schema_from_template.py:46`（`FIELD_RE` 正则被当 `windows_drive`）、`assets/report.template.md:96`（模板说明「如 `/Users/...`」举例）。

**步骤**：
- [ ] 排除 `> **模板说明**` 段（`.md`）
- [ ] 排除 `re.compile(r"...")` / `_RE = r"..."` 正则定义字符串内的匹配（`.py`）
- [ ] 排除反引号/引号内举例路径
- [ ] **保留**字符串常量中的真实硬编码路径（如 `LOG_DIR = "/Users/x/logs"`）

**禁止过宽排除**：不可「凡在引号内都排除」——真实硬编码多写在字符串里，过宽会漏检。

**继承策略**：候选仍交 LLM 复核、**不自动判级**（L123 原有设计保留），故误报风险可控。

---

## [待办] P5. 清理硬编码降级数据（低优先）

**登记**：2026-09-01 ｜ **状态**：已审查，结论为**无被测技能定制逻辑**，仅余清理项

**目标**：消除两处硬编码降级数据，对齐「引用而非硬编码」纪律。

**锚点**：`scripts/generate_outputs.py`（L65-80、L518-542）、`scripts/exec_functional_tasks.py`（L20/24）

**执行中问题**：无

**待处理问题**：无

**已审查结论（无需再查）**：
- `exec_functional_tasks.py` L20/24 的 `aihot` 仅出现在**用法 docstring 示例**（`--skill-name aihot`），非运行时逻辑
- `generate_outputs.py` L65-80 的 `_SKILLS_SH_SKILLSH_URLS` / `_CLAWHUB_URLS` 是**技能市场来源 URL 映射表**（第三方技能的市场页/仓库页），用于报告 canonical URL 生成，非被测技能定制逻辑；已具备 `_load_url_map()` 优先读 JSON、缺失才降级硬编码，属可接受降级

**步骤**：
- [ ] 把 `_SKILLS_SH_SKILLSH_URLS` / `_CLAWHUB_URLS` 外置为 `assets/skill_url_map.json`
- [ ] `exec_functional_tasks.py` docstring 示例改为通用占位（如 `<skill-name>`），避免被误读为定制

---

> **P6 已完成并归档**（2026-09-04）：见 `archive/TASKLOG_2026-09.md`。

---

## [已完成] P8. SKILL.md 开发态章节迁出（方案 A）

**登记**：2026-09-04 ｜ **完成**：2026-09-04

**目标**：`SKILL.md` 随发布包分发，应为纯运行态；开发态章节留在其中会随包发布且对使用者无价值（且会产生空指针）。

**迁移明细**：

| 章节 | 处置 | 理由 |
|---|---|---|
| 项目级会话日志约定 | **迁出**（11 行）→ `.project/AGENTS_RULES.md` | 仅调试态写 `.session_log/`，发布态完全跳过 |
| 自优化闭环 | **迁出**（16 行）→ `.project/AGENTS_RULES.md` | 发布态对自身目录只读，不进入闭环 |
| 运行状态策略（含判定 + 权限边界） | **保留** | 运行态需判定自身状态；权限边界（不写自身、防御他人写入）是运行态安全约束 |

**关键实现（防引入新空指针）**：`SKILL.md` 的替代指针**不写治理区路径**（写 `.project/…` 会在发布包内成为新空指针），改用语义指代"治理区规则文件（属维护期内容，不随发布包分发）"。

**验证**：
| 项 | 结果 |
|---|---|
| SKILL.md 开发态路径残留 | 清零 ✅ |
| 发布隔离门禁 | 0 阻断（14 处警告均为格式举例/历史标注误报）✅ |
| 业务回归 / 回归测试 / 声明块门禁 | 均退出码 0 ✅ |
| SKILL.md 体量 | 352 → 354 行（章节变指针，净减少约 27 行原文） |

**教训**：迁移类改动最易在"留指针"环节引入新空指针——指针指向的目标在发布包内不存在。**指针目标必须与所在文件的分发范围一致**。

---

## [待办] P8b. SKILL.md 剩余开发态章节复核（**待评估**）

**登记**：2026-09-04 ｜ **状态**：待评估

**遗留**：P8 只迁了 2 个最明确的章节。按同一判据复核，`SKILL.md` 仍可能存在开发态内容（如「执行纪律：运行计划 + 执行日志」中的自优化相关表述、`{EXEC_LOG}` 中"供 skill-evaluator 自身优化"的措辞）。本轮未逐一判定，待后续按需处理。

**发现**：按「规格=开发态 / 运行态=技能文档」定义，`SKILL.md` 作为发布包主文件应是**纯运行态**，但实测含多个**开发态章节**（发布态不触发，却会随包发布）：

| 章节 | 行号 | 发布态是否触发 |
|---|---|---|
| 项目级会话日志约定 | 177 | ❌ 仅调试态写 `.session_log/` |
| 自优化闭环（调试态） | 243 | ❌ 发布态对自身目录只读，不进入闭环 |
| 运行状态策略 | 139 | ⚠️ 判定逻辑需要，但含开发态路径引用 |

**已暴露的具体问题**：自优化闭环第 1 步原写 `python3 scripts/test_backfill_reviews.py`（脚本已移入治理区）→ 发布包内为空指针。本轮已改为**语义指代**（"执行治理区登记的回归入口"）绕过，但这只是掩盖，未解决"开发态章节留在发布包"的根因。

**处置选项**：
| 选项 | 做法 |
|---|---|
| A | 开发态章节整体迁出 `SKILL.md` → 治理区 `AGENTS_RULES.md`；`SKILL.md` 只留一行指针（最符合定义，但改动大） |
| B | 保留章节，但全文替换具体路径为语义指代（本轮临时做法，治标） |
| C | 承认 `SKILL.md` 是双时态文件，靠「发布态跳过规则」兜底（与 `references/specs/*.spec.md` 的旧问题同型） |

**倾向**：A。C 会让「规格=开发态」这条新定义对 `SKILL.md` 失效，等于开例外。

---

## [待办] P7. `references/specs/*.spec.md` 是否改名（**暂缓**，风险已量化）

**登记**：2026-09-04 ｜ **状态**：**决定不改名**，风险量化后留档；触发条件见下

**背景**：按新定义「规格=开发态 / 运行态=技能文档」，`*.spec.md` 的 "spec" 暗示开发态规格，与其实为运行态数据格式定义冲突。

**风险实测（2026-09-04）**：

| 项 | 实测 |
|---|---|
| 文件名提及总数（发布区） | **146 处**，分布在 13 个文件（`stage1_sample.md`、`stage4_spec.md`、`spec_contract.md`、`exec_common.md`、`sample_contract.md`、`exec_contract.md` 及 8 个脚本） |
| 单文件最高提及 | `grader.spec.md` 27 处、`benchmark_manifest.spec.md` 25 处、`metrics.spec.md` 20 处 |
| 脚本是否 `open()` 读取 | **否**——全部为文档引用/注释，**无运行时 I/O 依赖** |
| 目录名 `references/specs/` 提及 | 30+ 处 |

**不改名理由（核心）**：
1. **无测试能兜住改名**：因无脚本按路径读取 spec 文件，**改名不完整不会产生任何测试失败**——属"静默漂移"类变更，风险与收益不对称。
2. **语义矛盾已由 Q2-A 消除**：声明块已移除，文件不再自称规格文件；`SKILL.md` 索引已注明「`.spec.md` 指数据结构说明，非开发态规格」。
3. 文件名属不透明标识符，`.spec.md` 作为"数据结构说明"的通用约定已被广泛理解。

**触发条件**（满足任一则重启本任务）：
- 出现**按路径读取** spec 文件的脚本（届时改名有测试兜底，风险下降）
- 实际发生因 "spec" 词义导致的归类错误
- 需新建 spec 文件且命名冲突

**若执行时的做法**（留档）：`*.spec.md` → `*.format.md`，`references/specs/` → `references/formats/`；用 sed 批量改后跑 `check_release_isolation.py` + 全仓 grep 旧名应为 0。

---

## [观察] P9. 旧 Node 副本在回收站——确认无异常后再清空

**登记**：2026-09-09 ｜ **状态**：**观察中**（用户指示：先别急着清空；若有问题由用户指示恢复）

**背景**：为解除对第三方工具链运行时的依赖、收敛为唯一 Node，旧运行时副本（v22.22.3，206M，原路径 `~/.hermes/node`）已移入回收站，原路径改挂软链指向新 Node。

**现状（2026-09-09 已验证）**：

| 项 | 值 |
|---|---|
| 回收站位置 | `~/.Trash/node.20260909-200524` |
| 原路径现状 | `~/.hermes/node` → 软链 → `~/.workbuddy/binaries/node/versions/22.12.0`（兼容第三方硬编码引用，如 hermes `node-bootstrap.sh` 策略 2） |
| 全部入口 | `which node` / `~/.local/bin/node` / `~/.hermes/node/bin/node` / `CODEBUDDY_NODE_BIN` **均为 v22.12.0** |
| 真实二进制 | `find` 仅 `~/.workbuddy/binaries/node/versions/22.12.0/bin/node` 一份 |
| 功能回归 | openspec 1.12.0 ✓、hermes v0.14.0 ✓ |

**恢复方式**（用户指示时执行，二选一）：
1. `trash --undo` —— 仅当该条为 `~/.codebuddy/trash.log` **最后一条**时可用（当前是）
2. 手动：先移出现存 `~/.hermes/node` 软链，再 `mv ~/.Trash/node.20260909-200524 ~/.hermes/node`

**清空责任（2026-09-09 用户明确）**：**由用户本人处理**。AI 不得清空废纸篓，也不得在后续会话中主动提议清空或把它当作待办推进；仅当用户明确要求恢复旧副本时，才按上述方式协助恢复。本条目的存在意义仅是**保留恢复所需上下文**。

**锚点**：档案 `ERR-025`（`.project/error_registry/by_module/_cross_cutting.md`）；全局工具 `~/.codebuddy/bin/trash`（删除纪律见 `AGENTS_RULES.md` 修改纪律第 7 条）

---

## [观察] P10. win 评测输出目录多出一层 `table_column_relations_v2`（待确认）

**登记**：2026-09-19 ｜ **状态**：**待确认**（win 评测尚未跑完，未取到完整输出）

**现象**：输出目录为 `skill-evaluator_results\table_column_relations_v2\table_column_relations`，比预期多一层（预期为 `skill-evaluator_results\<技能名>`）。

**初步判断（高置信度，倾向非缺陷）**：`run_eval_pipeline.sh` 的目录规则为 `WS = RESULTS_ROOT / SKILL_NAME`，其中 `SKILL_NAME = basename(被测技能目录)`（第 84–85 行）。脚本建的**最后一层必然等于被测技能目录名**——此处即 `table_column_relations`。故 `table_column_relations_v2` 属**结果根目录的一部分**，由 `SKILL_EVALUATOR_RESULTS_ROOT` 环境变量（第 32 行）或 `--results-root` 参数（第 43 行）指定/创建。

- [ ] 确认：win 上是否设置了 `SKILL_EVALUATOR_RESULTS_ROOT`，或传入了 `--results-root`
- [ ] 若确为环境变量/参数所致 → **非缺陷**；仅需在使用文档中说明「结果根可被子目录覆盖，脚本在其下再建技能名层」
- [ ] 若两者均未设置 → 属真实缺陷，须开 openspec 变更排查（可能为某脚本在 WS 内又按技能名建了一层）

> **连带提醒**：若后续启用 R11（工作区清空默认化），删除范围必须仍是 `RESULTS_ROOT/<技能名>` 整层，不得只删内层——否则 v2 这类外层目录会残留。

---

# 治理改造（非行为变更 · **由本区承载，不进规范区**）

> **为何单列**：按 `openspec/config.yaml` 第 5 条，治理改造类任务**不**在规范区建变更（不改变对外行为，建了会污染规范区且违反第 7 条），因此**只在任务记录中承载**。
> **判据**：是否改变**对外可观察行为**——改变 → 走规范区变更；不改变（仅改项目自身治理结构）→ 登记本区。
> **教训（2026-09-09）**：T3–T5 曾因分类不清，既未进本文件、也未进规范区，悬空于对话而丢失，由用户翻查历史才发现。此后治理改造任务一律登记本区。

## [治理·已完成] G1. T3 基线化 scoring/（评分契约 → 需求 + 场景）

**登记**：2026-09-09（补登） ｜ **状态**：**已完成**

- **产出**：`openspec/specs/scoring/spec.md` —— 8 条需求（SHALL/MUST）+ GIVEN/WHEN/THEN 场景
- **来源契约**：`references/spec_contract.md` §3/§4/§5（效用/安全/最终分）+ `references/specs/scores.spec.md`（scores.json + verdict 规则 + comparable 前提）
- **校验**：`openspec spec validate scoring` → valid；`openspec list --specs` → `scoring requirements 8`
- **性质**：仅把既有评分语义搬入规范区，**未改变任何评分行为**（故属治理类，不进规范区变更）

## [治理·已完成] G2. T4 首变更演练：三方漂移告警 propose → apply → archive + 回归

**登记**：2026-09-09 ｜ **状态**：**已完成**（2026-10-09 核实回填）

> **过时状态修正**：此前标「待 apply」，但代码已实际实施——`scripts/validate_function_table.py:115` 存在 `_check_three_way_drift()`（含 USER_GUIDE 提取 L87、三方比对、告警输出），change `2026-09-09-add-three-way-drift-alert` 已归档。apply 与 archive 均已完成，本条关闭。

- **主题出处**：`ERR-021` 修改策略第 4 条「⬜ 三方校验（待做）：description ↔ USER_GUIDE ↔ 功能表 漂移告警」（§4 ↔ 功能表 已结构性消除，三方漂移仍待做）
- **变更**：`openspec/changes/add-three-way-drift-alert`（4/4 产物齐全，校验通过；16 项任务 0 完成）
  - `proposal.md`（触及 ERR-021；非目标：不自动修复、不做 §4 比对、不升级为阻断）
  - `specs/function-description/spec.md`（5 条需求）
  - `design.md`（扩展既有 `validate_function_table.py`，不新建脚本——避免第二份归一实现）
  - `tasks.md`（首条为读规则层 + 查错误档案）
- **下一步**：apply（改 `scripts/validate_function_table.py`：USER_GUIDE 提取 + 三方比对 + 告警输出）→ 回归 → archive

## [治理·已完成] G3. T5 收尾：改造方案归档 + 错误档案回写

**登记**：2026-09-09 ｜ **状态**：**已完成**（2026-09-09）

- [x] openspec 改造方案（T1–T5 全过程 + 环境收敛 + 机制缺陷修复）收归 `.project/archive/openspec_adoption_2026-09.md`
- [x] 错误档案回写：`ERR-021` 第 4 条由 ⬜ 待做改为已实施（补验证结果与「实测推翻」留档）
- [x] 机制缺陷（治理改造任务无载体）已修复并留档于方案归档第三节
- [x] 提交工作区改动（3 次提交：`54efd83` feat / `a616f91`+`ce424e1` chore）
- [x] 治理区与规范区纳入版本管理，发布过滤改由 `.gitattributes` 的 `export-ignore` 承担

---

## [治理·待办] G4. 链接检查降噪（跨项目引用误报 + 错误档案锚点噪声）

**登记**：2026-09-14 ｜ **状态**：**待办**（用户 2026-09-14 指示：先记录，暂不实施）

**背景**：跑 `.project/tmp/check_links.py --scope openspec --scope .project --scope <上级规格目录>` 得 ✗ 3 条、⚠ 111 条。

- [x] **已定性**：✗ 3 条均为 `CODING_AND_NAMING_STANDARDS.md` 引用各项目 `.project/specs/CODING_PROJECT_APPENDIX.md`——按该文件第 15 行，项目附录**由各项目自建**，属**跨项目引用而非悬空**；且第 16 行适用边界为「国内量化投资领域的 C++ 工程」，本仓（Python/Node AI 技能评测）**不适用**（上级规格以各文件头部 `层级/归属` 声明即生效，见规则层「上级规格约束」段）。
- [x] **已统一表述**：该文件 447 / 890 行的裸文件名补 `.project/specs/` 前缀，与 15 / 825 行一致（仅消歧义，未改语义）。
- [ ] 脚本侧降噪：支持「跨项目引用白名单」（形如 `.project/specs/xxx.md`）或按适用性排除不适用规格，使其不判为悬空。
- [ ] 噪声侧降噪：⚠ 多为错误档案 `by_module/*.md` 的 `#误报` `#待验证` 等锚点被判告警——评估加白名单，或改用 `errindex` 检索替代链接检查。

---

## [治理·待办] G5. 归档自检是否立为独立脚本（**待用户决策**）

**登记**：2026-09-14 ｜ **状态**：**待定**（等决策；用户 2026-09-14 指示先记录）

- [x] **现状**：规则层「治理执行清单（薄层）」C 小节已给六项自检 + 一条组合初筛命令（未勾任务 / 占位残留 / validate），属「清单优先、脚本补位」形态，未新建脚本文件。
- [ ] 若立脚本：需新建 `.project/scripts/`，并**同步更新**规则层「目录与文件规划」表（一处为准，防两张皮）。
- [ ] **决策点**：保持清单形态（薄、零维护）还是升为脚本（机械项全自动、需维护目录规划）。

---

## [治理·进行中] G6. 规则层 ↔ 代码 一致性核对（防静默漂移）

> **标题与状态对齐（2026-10-09）**：内容区早已标注方案 C 已闭环，标题仍写待办（字段未同步）；且区块内仍有 1 项未勾选（决策：核对粒度与执行时机）→ 更正为进行中。

**登记**：2026-09-14 ｜ **状态**：**已闭环（2026-10-09）**——方案采用 **C（清单 + 脚本）**

**起因**：实施变更 `decouple-internal-resource-from-dependency` 时发现——规则层「可用性标记落地断言」段**早已规定** `dependency_expected` 由 `external_deps` 非空**唯一判定**，而 `dep_probe` 的实现长期为 `bool(deps + internal)`，**违规而长期未被发现**。

- [x] **调研**（2026-10-09 完成）

  **① 现有「一致性核对（防漂移）」段已有 6 项手段**（`AGENTS_RULES.md`）：规格字段清单 ≡ 源码产出 / 元规格合规 / 自检锚点 / 发布隔离 / 上级规格一致性 / 锚点未失效。

  **② 为何没覆盖本次类问题**：现有 6 项均为「**改某类文件后跑某脚本**」的**触发式核对**，缺少「**规则层断言 ↔ 代码实际行为**」的**系统性核对**——即规则写了但代码违规时，无对应核对项会发现。

  **③ 实检（以守卫编号为例）**：规则层提及 `E24 E25 E26 E27 E31`；代码中检索到 `E24 E25 E26 E27`，**`E31` 未检索到**。

  **④ 关键边界（否则核对会误报）**：`E31` 是**纪律 / 自罚码**（未查档即诊断 → 记入错误档案），**不是代码守卫**，本就不应在代码中实现。→ **核对项必须先分类**：
  - **代码类**（可机器核对）：`dependency_expected` 唯一判定（本项起因）、归桶 `E28`、`supporting_dimensions` 非空 `E29`、展示名 `sg_` 前缀、判级常量单一权威源（G7）、产物输出位置声明（G11 / R21）
  - **纪律类**（不属代码核对范围）：`E31` 等自罚码 / 流程码

- [x] **方案**（2026-10-09 采用 **C**）

  - **A 清单**：`AGENTS_RULES.md`「一致性核对（防漂移）」表新增「规则层断言 ↔ 代码实际行为」核对项，并写明**仅核对代码类断言、纪律/自罚码不纳入**（防误报）。
  - **B 脚本**：`.project/tmp/check_rule_code_consistency.py`（已建，RC-01~RC-06），退出码 0 为通过。
  - **实测结果**：漂移 **0** 项；并识别出 **3 处残留字面量**（`auto_security_spec.py` 的 `_ASI_TO_GROUP` / `_TAG_TO_ASI`、`validate_manifest_contract.py` 的 `_TAG_TO_ASI`）——运行时已被共享源覆盖，**不是错误但是漂移隐患**，已另立 **G16** 清理。
  - **自动发现的价值**：RC-01 证实 G6 起因项（`dependency_expected` 掺入 internal）**已被修复**（现为 `bool(deps)`），但若无本脚本，此类修复无从持续验证。

  | 选项 | 做法 | 取舍 |
  |---|---|---|
  | **A** 扩展「一致性核对」表 | 在 `AGENTS_RULES.md` 该表新增「规则层断言 ↔ 代码」核对项，按③④分类列出可机器核对清单，人工/定期跑 | 薄、零新增脚本，但依赖人执行 |
  | **B** 新增核对脚本 | 按 `治理脚本（派生 · 有终期）` 建 `check_rule_code_consistency.py`，机械核对上述代码类断言 | 全自动，但需维护 + 登记失效条件 |
  | **C** A + B 结合 | 表内列清单（人可读）+ 脚本跑机械项 | 最稳，成本略高 |

  **建议 C**：先用 A 把「哪些可机器核对」固化成清单（人能看懂），再用 B 把其中机械项自动化——与本次事故后 `govkit.py` 的做法一致（规则写进规格 + 守卫可执行）。
- [ ] 决策：核对粒度（全量 / 增量）与执行时机（提交前 / 回归中）

> **价值**：这类漂移不报错、不阻断流程，只在"规则写了却没人遵守"时静默存在——比功能性缺陷更隐蔽，也更难被发现。

---

## [治理·待办] G7. 判级常量收敛为单一来源（对应 R5）

**登记**：2026-09-18 ｜ **状态**：**待办**

**背景**：级别词与渲染色在 4 处硬编码（`build_objective_data` 的 `_SEVERE` / `_WARNING`、`render_report` 的 `SEVERITY_COLOR`、`validate_quality_report` 的 `ALLOWED_FONT_COLORS`），级别判定实现有 2 份同逻辑代码（`_severity_of`）。改级别词需改 6 处，且无机器校验。

- [ ] 抽为单一常量模块（级别词 + 渲染色 + 枚举取值）
- [ ] 各脚本改为引用，删除本地副本
- [ ] 验收：grep 级别词字面量仅命中常量模块

> **判为治理改造的依据**：内部重构，报告对外呈现不变。级别**结构化**（增 `level` 字段）属行为变更，已由 openspec 变更 `2026-09-18-report-template-constraint-optimization` 承载（R1）。

---

## [治理·待办] G8. 依赖对关系改由模板标注派生（对应 R6）

**登记**：2026-09-18 ｜ **状态**：**待办**

**背景**：`merge_report_data` 的 `_DEP_PAIRS` 把「客观候选字段 ↔ 主观裁定维度」三对关系硬编码，与模板内的子小节结构重复定义；模板改名即失效（抑制「候选列表 + 无」的逻辑会静默失效）。

- [ ] 模板增 `dep-pair` 标注，删除 `_DEP_PAIRS` 硬编码
- [ ] 验收：改模板槽位名后依赖对关系仍成立

---

## [治理·待办] G9. 功能表守卫词表合并（对应 R7）

**登记**：2026-09-18 ｜ **状态**：**待办**

**背景**：守卫常量定义 2 处（`_common.py` 的 `FUNCTION_TABLE_INTERNAL_KW` 与 `validate_quality_report.py` 的 `FORBIDDEN_FUNCTION_TABLE_TERMS`），注释称「同源」实为两份语义不同的词表；标识符扩散至 10 个文件。

- [ ] 保留 `_common.py` 为唯一定义，另一处改为 import
- [ ] 验收：grep 定义处计数 = 1

---

## [治理·待办] G10. 依赖可用性 category 表化（对应 R8）

**登记**：2026-09-18 ｜ **状态**：**待办**

**背景**：`dep_probe.py` 内 category 硬编码 16 处、取值仅 5 类；新增 checker 需手工对齐，无机器校验。

- [ ] 抽为常量表，checker 引用
- [ ] 验收：grep `category=` 硬编码处 = 0

---

## [治理·待办] G11. 产物输出位置声明纳入单一权威源（对应 R21）

**登记**：2026-09-18 ｜ **状态**：**待办**

**背景**：上个版本于 Windows + opencode 实测产出的反思文档落盘位置不确定（反思文档问题 10）——反思/改进类产物未纳入路径单一权威源。

- [ ] 在 `references/config.md` 路径表补齐全部对外产物声明（含反思与改进建议文档）
- [ ] 验收：产物清单覆盖全部对外文档，新增产物必有声明路径

---

## [治理·已完成] G12. 改造方案归档（本轮方案收尾）

**登记**：2026-09-18 ｜ **状态**：**已完成**（2026-10-09）

> **前置已满足**：6 个 2026-09-18 批次变更全部已归档（eval-scope-and-dependency-probe / pipeline-execution-integrity / report-naming-unification / report-template-constraint-optimization / stage0-gate-reachability / stage4-report-template-and-role-gate）。
> **已执行**：`输出报告模板约束优化方案.md` 由 `~/Downloads/` 收回 `.project/archive/`（原位置为临时位置，属系统清理对象）。

**背景**：`输出报告模板约束优化方案.md` 现滞留下载目录（外部 / 临时位置是系统清理对象）；`openspec/config.yaml` 明确将「方案归档」列为治理改造项。

- [x] 6 个变更实施并归档后，方案收回 `.project/archive/` ✅ 2026-10-09
- [ ] 归档后同步规则层当前结论（行为类结论进 `openspec/specs/`），**不回写 TASKLOG**、不留逐条依据指针

---

# 待决策候选（**未立项**，决定做后转 openspec 变更）

> **为什么单列**：这类条目实施后会改变对外行为（新增检测能力），按 `openspec/config.yaml` 第 5 条应由规范区变更承载、不登记进任务记录；但**尚未立项**时若也不登记此处，就会重现「T3–T5 悬空丢失」的事故。故设此区暂存：**立项后本条标注「已转出至 openspec 变更 XXX」并从本区移除**，避免双写。

## [治理·进行中] G13. 安全评测整改清单（T-01 ~ T-15）落地

**登记**：2026-10-07 ｜ **状态**：15 项已完成，2 项剩余（T-07r / T-12r）
**载体**：`CloudDocs/Agent/skill-evaluator_risk-assessment-explainer.md`「待整改任务清单（集中登记）」

**已完成**（2026-10-05 / 10-07）：T-01 映射收敛单一权威源 · T-02 归桶收敛 + 守卫 E28 · T-03 准入表补 9 行双列 · T-04 术语统一 + 展示名 `sg_` 前缀 · T-05 反查补齐 + E29 · T-06 评审资产消费（已接入阶段 5） · T-07 探针有效性前置校验 · T-08 N/A 从通过率剔除 · T-09 `execution_path` 声明 · T-10 占位路径告警 · T-11 视角索引补齐 · T-12 覆盖面下限告警 · T-13 前缀改按 ASI 推导 · T-14 执行顺序澄清 · T-15 非法评分桶值修复

**剩余**：T-07r、T-12r（另立 G14 / G15）

**断点续跑**：任务态不依赖外部说明材料——15 项完成记录已归档于 `.project/archive/安全评测整改_2026-10.md`（治理区内，外部文档丢失不影响）；剩余 2 项由规范区变更承载（G14 → `2026-10-09-security-grading-semantics-validity`；G15 → 并入 `2026-09-24` 的 N5 / N9）。所有写入走 `.project/tmp/govkit.py`（备份 + 断言 + 体积守卫 + 原子写 + 操作日志）。

---

## [治理·已转出] G14（T-07r）：评分语义断言升级

> **已转出（2026-10-09）**：本项为**行为变更**（改变评分器产出与评分结果），按「无双写纪律」**任务态由规范区变更承载**，不在任务层保留待办。
> → 载体：`openspec/changes/2026-10-09-security-grading-semantics-validity`
> 本条仅留指针，作为阅读入口；进度与验收以该变更为准。

**登记**：2026-10-09 ｜ **状态**：待立项

**目标**：① `field_present` 等纯存在性断言升级为有判别力断言（如 `field_not_empty`）；② 语义型判定引入 golden facts 比对或受控 LLM 判定；③ 增加「断言 ↔ rubric 语义」一致性守卫（当前 R9 的语义错位无人发现）。

**为何需先立项**：改变评分器产出与评分结果 → **行为变更**。

**建议 change**：`security-grading-semantics-validity`（二期）。

---

## [治理·已转出] G15（T-12r）：打标召回率度量与覆盖阈值拍板

> **已转出（2026-10-09）**：本项与在途 `2026-09-24-security-surface-scan-normalization` 的 **N5**（基准测试集 / 召回率）、**N9**（取舍决策记录）同源同义，**任务态并入该变更承载**，避免三处重复。
> → 载体：`openspec/changes/2026-09-24-security-surface-scan-normalization`（N5 / N9）
> 本条仅留指针；阈值拍板属领域决策，在该变更内完成。

**登记**：2026-10-09 ｜ **状态**：待立项 / 待领域决策

**目标**：建立基准测试集并度量打标召回率；ASI 覆盖下限阈值需领域拍板（当前默认 9，仅告警不阻断）。

**关联**：在途 `2026-09-24-security-surface-scan-normalization` 的 **N5**（基准测试集 / 召回率）、**N9**（取舍决策记录）。

**建议**：并入该 change，或单列。

---

## [候选·待定] C1. 语义漂移治理（方案 v2 已完成，待讨论定稿）

**登记**：2026-09-10 ｜ **状态**：**方案已出，未讨论定稿、未立项、未实现**（用户明确：先搞清可行性，不要动手）

- **方案**：`~/Library/Mobile Documents/com~apple~CloudDocs/Agent/语义漂移治理方案.md`
  （外部位置，**定稿后须收回归档**至 `.project/archive/`，避免重蹈「方案散落外部」覆辙）
- **目标**：治理「技能声明的能力 ↔ 功能表 ↔ SKILL.md 实际内容」之间的漂移；功能表未显式定义时给出**编写建议**（不警告、不错误）
- **可行性实测结论（关键）**：
  | 对照语料 | 覆盖率 | 结论 |
  |---|---|---|
  | Frontmatter / When to Use | 0–27%（多数 0%） | ❌ 不能作对照（一句话定位，天然覆盖不了功能清单） |
  | SKILL.md **全文** | **25–29%** | ⚠️ 文档更长也不提升，**词面匹配天花板**，不能做覆盖判定 |
  | — | 零命中的条目占 14–20% | ✅ 可做「防 AI 臆造」提示 |
- **由此定的分层**：机械层只做**零命中检测**（防臆造）；**语义覆盖判定交 AI**（须给行号证据）
- **用户已定的 6 条**：① 词表动态生成 + 市场可作语料（不作对照）② 可建议格式但**提取放宽标题**③ **只在 SKILL.md 找**，不查 scripts ④ 不单列建议区，作为检查项挂子标题下标注「编写建议」⑤ 自评与外部评测**不区别**⑥ 先方案后立项，现在不进 openspec
- **剩余待确认**：零命中阈值是否严格 `hit==0`；AI 判定挂在哪（复用 PENDING_AI_ADJUDICATION？）；广泛词表是否必要；「疑似遗漏」是否报

### 复评（2026-09-19）

**结论：问题仍存在，但整改必要性为「有条件」——存在前置依赖。**

| 原问题 | 现状核实 |
|---|---|
| 纯中文分词 `_CJK_WORD` | **仍在**：`validate_function_table.py:42 / 78 / 169 / 179` |
| 语料硬编码 `references/USER_GUIDE.md` | **仍在**：`validate_function_table.py:59` |
| 无语言自适应 | **仍在**（无英文分词路径）→ 英文技能填表后必被误报 |
| 零命中检测 | **未实现** |
| L2 引导材料 | **已部分实现**（2026-09-18 改造 P9：`auto_subjective` 三层次材料 + 归纳纪律）；剩余「每条附来源行号」未强制 |

**新增关键事实**：`validate_function_table.py:164-166` —— 功能表**无数据行时直接跳过并返回 0**。而功能表属主观维度、当前**未裁定**（报告呈现「未检查」）。故：

> 功能表没内容 → 漂移无从谈起 → L0 / L1 / L3 **全部空转**，做完也验证不了效果。

**处置**：

- [x] 已在方案文档追加「复评记录」节（含逐项核实表、前置依赖、建议顺序）
- [ ] **不立项、不废弃**，等前置依赖满足后再评估
- [ ] 前置依赖：功能表裁定闭环（待裁定清单落地 + R13 阶段完成门禁），已由 openspec 变更 `2026-09-18-pipeline-execution-integrity` 承载
- [x] **L0 语言自适应已实施**（2026-09-19）：`_content_words` 改为中英**并集**分词（`_CJK_WORD` 行为不变 + 新增 `_EN_WORD` 与英文停用词）。不预设主语言阈值（避免未实测阈值）
  - 验证：英文文本分词 **0 → 6** 词；中文文本分词不变（不回退）；英文功能表**不再**被判「缺乏可区分的能力词」
- [x] 方案已归档副本至 `.project/archive/语义漂移治理方案.md`（**原件仍在外部 CloudDocs/Agent/，是否删除待你定**——不擅自删）
- [ ] L1 语料多候选发现（硬编码 `references/USER_GUIDE.md` 仍在 `validate_function_table.py:59`）
- [ ] L3 零命中检测（未实现）
- [ ] L4 判定侧：LLM 覆盖判定须给行号（材料侧已被 P9 覆盖）
- [ ] **残留误报（L0 未覆盖）**：`_SERVICE_VERBS` 为**纯中文**正则，英文功能表条目仍被提示「缺少用户动作动词」——提示级、不阻断（退出码 0），但属误报，需随 L0 一并处理（词表在 `_common.py`，改动会影响 `extract_functional_tasks`，须谨慎）

**建议顺序**：win 平台评测结果回来 → R14/R15（阶段 4 模板化）→ 功能表可被真正归纳 → 再回来评估是否立项。

---

## [候选·待定] C2. win 平台评测暴露的兼容性与效率改进（已分析，未立项）

**登记**：2026-09-19 ｜ **状态**：**已产出分析，未立项**（等用户决定是否实施）

- **分析文档**：`~/Downloads/skill-evaluator-win评测结果分析.md`（外部位置，定稿后归档至 `.project/archive/`）
- **一线素材**：`~/Downloads/skill-evaluator-v2-全流程评测报告与改进建议.md`（opencode agent 产出）
- **输出目录**：`~/Downloads/skill-evaluator_results/`（208 文件，980K）

### 关键事实

| 项 | 实测 |
|---|---|
| 全流程 | ✅ 阶段 0→4 全部完成，评分 74.01 / 条件上架 |
| **真实耗时** | **88 分钟**（16:57 → 18:25）；一线报告估「~18 分钟」，低估 5 倍 |
| **瓶颈** | sample 阶段 **80 分钟（占 91%）**；报告估「5 分钟」，低估 16 倍 |
| 样本 | common×2 + hard×1 + security×4 = 7 个，每个约 23 文件，共 156 文件 |

### 根因（最重要的一条）

**样本脚手架脚本早已存在**（`build_sample_pack.py` / `generate_functional_scaffolds.py` / `generate_probe_scaffolds.py`），但 opencode agent **未调用**，改为手工生成 156 个文件。

> 这是**流程问题不是能力问题**，且与本项目此前发现同源：LLM 倾向「自己写」而非「调脚本」（阶段 4 报告手工整理、主观维度不裁定 → 「未检查」）。
> 治理手段应是**强制脚本路径 + 产物结构门禁**，而非靠提示。

### 待实施项（均属行为变更，立项后由 openspec 变更承载）

- [ ] **P0** 6 个脚本 10 处硬编码 `python3` → `sys.executable`（`exec_functional_tasks.py` 5 处为阶段 2/3 真实调用）
- [ ] **P0** `backfill_character_metrics.py:70` 的 `_TASK_ROOT_PATTERN` 只匹配 `/`，须支持 `\`
- [ ] **P0** `generate_outputs.py:2148` 模板嵌套占位符 `{_count_text(_comp_base_time)}` → KeyError
- [ ] **P1** `generate_task_metrics.py:52` 的 `task_description` 硬编码空串，须从 TaskDescription.md 读取
- [ ] **P1** 样本生成**强制走脚本** + 产物结构门禁（预期 80 分钟 → 分钟级）
- [ ] **P1** 阶段 2/3/4 并行执行
- [ ] **P1** 空分组目录处理、产物落点统一（`subjective.json` 落在结果根而非工作区）
- [ ] 分析文档归档至 `.project/archive/`

### 已修复（win 评测用的是旧包，故仍命中）

- `dep_probe.py` 只支持 GET → 已修复（R20）
- 治理/开发态文件被评 → 已修复（R12）

### 一线报告的可信度

**可借鉴**：脚本报错记录、阶段意外现象（baseline 写示例结果、子代理自行选参数）——属一线观察。
**不可信**：所有耗时估算（按脚本执行时间估，忽略 LLM 手工开销）；「0 个 hard 任务」与实际 H_01 存在矛盾。

## [治理·已完成] G16. 清理残留字面量（消除规则层 ↔ 代码 漂移隐患）

**登记**：2026-10-09 ｜ **状态**：**已完成（2026-10-09）**

**目标**：清理 `auto_security_spec.py` / `validate_manifest_contract.py` 中仍保留的 `_ASI_TO_GROUP`、`_TAG_TO_ASI` **字面量定义**（共 3 处）。它们运行时已被单一权威源覆盖，**不产生错误**，但属漂移隐患——后续有人改字面量会误以为生效。

**锚点**：`scripts/auto_security_spec.py:26`（`_TAG_TO_ASI`）、`:39`（`_ASI_TO_GROUP`）；`scripts/validate_manifest_contract.py:361`（`_TAG_TO_ASI`）。覆盖语句分别在 `:67` / `:69` / `:372`。

**步骤**：

- [x] 删除 3 处字面量定义，直接引用 `_common.TAG_TO_ASI` 与 `derive_security_group()`
- [x] 删除后跑 `check_rule_code_consistency.py`（RC-02 / RC-03 应报"无第二份映射"）
- [x] ~~顺带清理 `_common.PROBE_GROUP_MAP`~~ → **已撤销（2026-10-09 复核）**：登记前提**错误**。`PROBE_GROUP_MAP` 并非死代码——`backfill_reviews.py:188` 在 `derive_security_group()` 推导失败时仍以其作为最终兜底，`run_security_pipeline.py:73` 亦导入使用，须保留。教训：登记前须实测调用点，不得据「命名不匹配」推断无引用。
- [x] 跑既有回归确认产物不变

**验收**：`check_rule_code_consistency.py` 退出码 0，且 RC-02 / RC-03 明细不再出现"残留字面量"字样；回归退出码 0。

**完成结果（2026-10-09 实测）**：

- 已删除 `auto_security_spec.py` 的 `_TAG_TO_ASI` / `_ASI_TO_GROUP` 内联字面量与 `validate_manifest_contract.py` 的 `_TAG_TO_ASI` 内联字面量（共 3 处），仅保留指向单一权威源的别名赋值。
- `check_rule_code_consistency.py` 退出码 **0**：6 项核对漂移 0；RC-02 明细为「无第二份映射」，RC-03 明细为「仅 _common.py 定义，无本地副本」。
- 等价性验证：`auto_security_spec._TAG_TO_ASI is _common.TAG_TO_ASI` 为 True；`_ASI_TO_GROUP` 十项逐个等于 `derive_security_group()` 推导值（ASI03 → permission，旧字面量的 abnormal 已彻底消失）。
- 回归：`test_backfill_reviews.py` 全通过；`selfcheck_refactor.py` / `test_session_fixes.py` 退出码 1，失败点为**既往存在**且与本次改动无关（前者是历史 fixture 的 `supporting_dimensions` 为空触发 E29，后者是 `--stage0` 参数已改名）。

> **额外发现（比原登记更严重）**：`auto_security_spec.py` 保留的旧 `_ASI_TO_GROUP` 字面量里**仍写着被判定为错的「编号三等分」映射**（ASI01→abnormal 等），运行时虽被覆盖，却是极强的误导源——本次已一并清除。

---

## [治理·已转出] G17. 两个攻击面标签的 `mapped_asi` 与准入表语义不一致

> **已转出（2026-10-09）**：本项为**行为变更**，按「无双写纪律」任务态由规范区变更承载，不在任务层保留待办。
> → 载体：`openspec/changes/2026-10-09-surface-tag-asi-mapping-alignment`（与 G18 合流）
> 本条仅留指针；进度与验收以该变更为准。

**登记**：2026-10-09 ｜ **状态**：已转出（2026-10-09）

**目标**：`prompt_intent` 与 `system_instruction` 在 `TAG_TO_ASI`（代码）中的映射值，与 `Mapping-Matrix.md` 准入表已确认的触发维度**不一致**，需裁定并统一。

**锚点**：`scripts/_common.py:145`（`TAG_TO_ASI`）；`references/SafeTest/dimensions/Mapping-Matrix.md:33` 起准入表。

**不一致明细**：

| 标签 | 代码 `TAG_TO_ASI` | 准入表已确认触发维度 | 差异 |
|---|---|---|---|
| `prompt_intent` | ASI04、ASI07 | ASI01（目标劫持，提示注入的直接对应）+ `social-engineering` + `content-policy-compliance` | 代码缺 ASI01 |
| `system_instruction` | ASI04、ASI10 | ASI01、ASI10 + `social-engineering` | 代码含 ASI04（供应链，关联弱） |

**为何需先立项**：改 `TAG_TO_ASI` 会改变"命中标签 → 生成哪些探测"，属**行为变更** → 任务态由规范区变更承载。

**承载 change**：`2026-10-09-surface-tag-asi-mapping-alignment`

**复核修正（2026-10-09 实施前核验）**：原登记称两个标签不一致，**实测为 9 个标签全部不一致**（0/9 一致）；且准入表触发维度的 ASI 并集缺 **ASI08**。差异面由 2 扩到 9，全量对照表见承载变更的 proposal。

---

## [治理·已转出] G18. 准入表（文档）与 `TAG_TO_ASI`（代码）两条路径无对账

> **已转出（2026-10-09）**：本项为**行为变更**，按「无双写纪律」任务态由规范区变更承载，不在任务层保留待办。
> → 载体：`openspec/changes/2026-10-09-surface-tag-asi-mapping-alignment`（与 G17 合流）
> 本条仅留指针；进度与验收以该变更为准。

**登记**：2026-10-09 ｜ **状态**：已转出（2026-10-09）

**复核补充（2026-10-09）**：核验确认两条路径的不一致为**全量**（9/9），非个别行错位；故对账校验按「逐标签全集合比对」设计，而非抽样或仅校验新增标签。

**目标**："生成哪些探测"当前存在两条并行路径——代码按 `TAG_TO_ASI` 键名做确定映射；文档准入表按「键名 + 中文说明」匹配触发维度。**两条路径结论不一致时无任何校验**。

**锚点**：`scripts/_common.py:145`；`references/SafeTest/dimensions/Mapping-Matrix.md:33`。

**步骤**：

- [ ] 裁定权威源（建议以 `TAG_TO_ASI` 为唯一权威，准入表改为由其生成或校验）
- [ ] 新增守卫：逐标签比对准入表触发的 ASI 集合与 `TAG_TO_ASI` 集合，不一致即报错

**验收**：人为改坏准入表某一行能被守卫报出；无差异时守卫放行。

---

## [治理·待办] G19. 阶段编号重排（阶段 5 实际先于阶段 4 执行）

**登记**：2026-10-09 ｜ **状态**：待实施（低优先）

**目标**：安全探测以"阶段 5"编号运行，但**执行顺序为 2/3 → 5 → 4**。2026-10-07 已在流水线增加运行日志披露（T-14 已澄清），**完整重排延后**，本次转为正式待办。

**锚点**：`scripts/run_eval_pipeline.sh:490`（披露日志）、`:492-502`（阶段 5 三个步骤）。

**为何属治理改造**：重排只改编号与文档命名，不改变产物结构与评测结果 → **不改变对外可观察行为**。

**步骤**：

- [ ] 统一重排编号，使编号与实际执行顺序一致
- [ ] 同步更新 `references/stage*.md`、`SKILL.md` 与脚本日志文案

**验收**：编号与执行顺序一致；回归退出码 0。

---

# 2026-10-12 发布收敛（最小改造集 · 基线留档）

> **判据**：只做「**阻断发布**」或「**会让评测结果失真**」的项；
> 不做「锦上添花」或「**改完无法验证**」的行为变更。

## [已完成] R1. 最小改造集（随 `2026-10-12.1` 发布）

| 项 | 内容 | 为什么必做 |
|---|---|---|
| **M1** | `references/stage0_preflight.md` 评测范围表的治理区路径改**语义指代** | 发布隔离门禁 **EXIT=1 阻断**（2 处）。依据 P8 教训：指针目标必须与所在文件的分发范围一致 |
| **M2** | `.project/tmp/selfcheck_refactor.py` 补 `lenses_for_asi` 反查补齐 | 回归入口 **EXIT=1**（E29：`supporting_dimensions` 恒空）。根因 = 该脚本直连 `auto_security_spec.py`，**绕过** `generate_probe_scaffolds.py:296-302` 的补齐步骤 → **夹具缺步，非产品缺陷**（真实链路 `build_sample_pack.py:55` 复用该脚手架，字段会被补齐） |
| **M4** | `scripts/backfill_character_metrics.py` 的 `_TASK_ROOT_PATTERN` 支持 `\` | 只认 `/` 时 Windows 下全部 `task_metrics.json` 匹配失败 → 字符数 / 耗时回填为 0 → **效用与效率指标失真** |
| **M5** | `VERSION` → `2026-10-12.1` | 发布基线 |

**发布前实测门禁**：

| 门禁 | 结果 |
|---|---|
| 发布隔离 `check_release_isolation.py` | **EXIT=0** ✅ |
| 回归入口 `selfcheck_refactor.py` | **EXIT=0** ✅（E24/E25/E26/E27 真实数据全放行；R4/R6 分离正确） |
| 规则↔代码一致性 `check_rule_code_consistency.py` | **EXIT=0**，漂移 **0** ✅ |

**实测中确认"已无需再做"的旧记录**（避免以后误当遗留）：
C2 的 P0-①（`exec_functional_tasks.py` 硬编码 `python3`）**已修复**（现用 `sys.executable`，见 L448/454/561/565/674）；
P0-③（`generate_outputs.py` 模板嵌套占位符 `{_count_text(...)}` KeyError）**已修复**（L2295 留有修复说明）。

---

## [治理·待办] G20. 回归脚本 `test_session_fixes.py` 已失效（待废止或重写）

**登记**：2026-10-12 ｜ **状态**：待办

**实测**：`EXIT=1`，失败点 `#7 --stage0 应通过并返回 0，实际 rc=2`（STDERR：`未知参数: --stage0`）。
`run_eval_pipeline.sh` 现行参数为 `--skill-dir` / `--results-root` / `--run-id` / `--scaffold-spec` / `--security-spec`；
**`--stage0` 与 `--reset` 均已不存在** → 该脚本测的是**已废弃 CLI**。

**为何不在最小集**：属**派生治理脚本**（`.project/tmp/`，有终期）；修它等于重写整层 Bash 集成测试，不是最小改造。
产品侧未受影响——未知参数被正确拒绝，说明新参数校验**正常**。注：项目定义的**正式回归入口是 `selfcheck_refactor.py`**（已 EXIT=0），本脚本不在发布门禁链路上。

- [ ] 二选一：① 废止（移入 `.project/archive/` 并在 `.project/tmp/INDEX.md` 标失效）；② 按现行 CLI 重写
- [ ] 若重写：最小参数集为 `--skill-dir` + `--results-root`，产物断言改为 `objective_data.json`

---

## [治理·已转出] G21. 攻击面标签体系改造（#2 词形字典 / #3 标签拆分与判据修订 / #1-i 扩样）

> **已转出**：属**行为变更**（改变打标结果与触发的探测），按**无双写纪律**任务态由规范区变更承载，本条仅留指针。
> → 载体：`openspec/changes/2026-10-10-attack-surface-tag-system-refactor`
> 进度与验收以该变更为准；本条不重复登记步骤。

**为何本次发布不做（关键——避免以后误判为"漏做"）**：

1. **U1 硬门禁当前无法验证**：U1 要求「逐标签召回率 ≥ 0.90」方可归档，而现有真值只有 **14 个技能**
   （单个判定误差 ≈ 1/14 ≈ **7%**，与 10% 容差同量级）→ **改了也验不了**，等于发一个未验证的行为变更。
2. 该变更自身载明：**未决未裁决前，#3 / #4 的实施范围不得自行扩大**。
3. 第四轮已证明判别力问题的解在**判据形态**（E1–E2：κ 0.6000 → **0.8967**），不在标签语义；
   故按变更内顺序推进即可（先 #2 词形字典，再 #3），不必抢在本次发布前做。

**变更内已登记的子项**（供回溯，不在此展开）：
#1-i（扩样至 ≥30）/ #1-i-a（样本包内文件完整性）/ #2（词形字典落地 `scripts/_common.py` 单一权威源）/
#2-a（`exec_code` 判据语言无关）/ #2-b（`state_persist` 补 shell 重定向）/ #3（标签拆分 + 剔恒真信号）/
#3-a（`external_dep` 收窄 + 隐式依赖出口）/ #3-b（`system_instruction` 收紧）/ #3-c（E1–E2 已知代价由 U10 运行时补）。

**已具备的前置成果**（均在变更的 `benchmark/` 下）：
`truth.json`（第四轮裁定后合并，含 `tag_usability` 逐标签可用性）、`kappa_round4.json`、
`tag_judgeability.md`（逐标签可判定性分级表）、`annotation_guide.md` v5（E1–E2 口径 + 裁定 22–26）。

---

## [观察] G22. 评测测试回来后的承接顺序（建议，非承诺）

**登记**：2026-10-12 ｜ **状态**：待用户评测结果

本次发布的目的之一是取得**真实评测数据**。回来后建议按此顺序处理，避免同时开工导致结论互相污染：

1. 先判定**本次实测是否复现** C2 记录的两个瓶颈（样本阶段耗时、LLM 不调脚本）——属流程问题，非本版改动范围
2. 若要在 win 评测：重点看 `backfill_character_metrics` 的字符数 / 耗时是否**不再是 0**（M4 的验证点）
3. 攻击面标签改造（G21）**不因评测结果而提前启动**——它等的不是评测数据，而是 G21 第 1 条的真值扩样


---
