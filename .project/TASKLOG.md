# TASKLOG（任务进度 · 可中断恢复）

> **读者=编辑者=LLM**。仅载**待办 / 进行中 / 阻塞**任务；已完成任务归档至 `archive/TASKLOG_YYYY-MM.md`。
> **本文件不记录会话流水**：续跑所需信息由任务态（做到哪）与 `.project/AGENTS_RULES.md`（为什么这么定）共同覆盖。
> 建立：2026-09-03（自原 `AGENTS_RULES.md` PENDING 段剥离）

---

## [待办] P1. 依赖维度数据层解耦：internal_resource 移出 dependency 维度（方案 B）

**登记**：2026-08-31 ｜ **状态**：暂缓（已先实施低风险方案 A）
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

## [待办] P3. external_deps 误报过滤 + 无外部依赖时安全探测 N/A 满分

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
- [ ] `exec_security_evidence` 跳过时标记 `evidence_skipped`
- [ ] `exec_security_probes`/聚合据此输出 **N/A 满分**（`status=pass/na`），落 `grading_result.json`
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

## [治理·进行中] G2. T4 首变更演练：三方漂移告警 propose → apply → archive + 回归

**登记**：2026-09-09 ｜ **状态**：propose 已完成，**待 apply**

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

# 待决策候选（**未立项**，决定做后转 openspec 变更）

> **为什么单列**：这类条目实施后会改变对外行为（新增检测能力），按 `openspec/config.yaml` 第 5 条应由规范区变更承载、不登记进任务记录；但**尚未立项**时若也不登记此处，就会重现「T3–T5 悬空丢失」的事故。故设此区暂存：**立项后本条标注「已转出至 openspec 变更 XXX」并从本区移除**，避免双写。

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
- **下一步**：讨论定稿 → 立项（openspec 变更）→ 实现
