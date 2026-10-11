## 1. 已实施

- [x] **#1-a** 基准集抽样与标注基础设施（2026-10-11）
      - 锚点：新增 `scripts/build_benchmark_set.py`（分层抽样）、`scripts/benchmark_agreement.py`（Cohen's kappa + 真值合并）；`benchmark/annotation_guide.md`（标注规程）、`benchmark/benchmark_set.json`（15 个样本清单）、`benchmark/truth_a.json` / `truth_b.json`（标注骨架）
      - 实测：**15 个**已从 295 个候选中抽出，`scripts/` 8 / 英文 6 / 中文 9 / 六域 doc3 data3 web3 dev2 gen2 sys2 —— 约束全部达成
      - **分层维度改过两版才可用**（教训留档）：① 按"是否命中能力面"分层 → 退化（几乎全部技能命中全部类，样本全阳性、无阴性，精确率无法计算）；② 按 SKILL.md 开头 1200 字判域 → 仍退化；③ 最终按 frontmatter `description` 的**命中分取主域** + 两阶段选择（先按域保底、再补语言 / scripts）→ 区分度成立
      - 试点标注完成 **3 / 15**（kdocs、web-search-exa、stock-analyzer），暴露两处规程待明确项（`prompt_intent` 是否含"请求参数拼接"、`external_dep` 对 node 类依赖的判定），已在 note 中记录为 `unsure`


## 2. 待实施

- [ ] **#1** 基准集建设（**前置项，后续各项的度量基础**）
      - 锚点：`SAMPLE_ROOT`（现有 6 个异质技能）；改造方案文档「基准集与普遍性设计」
      - 验收（**U6 已裁决 2026-10-11**）：**两批推进**。第一批 **15 个**：含 `scripts/` ≥ 8、纯英文 ≥ 5、纯中文 ≥ 5、6 类能力面每类 ≥ 2；双人独立标注 + Cohen's kappa **≥ 0.8**（< 0.8 须先对齐标注规程再重标）；第二批扩至 30 收窄置信区间。来源 = `skills-marketplace/skills/`（实测 295 个 / 124 个含 `scripts/`），**不含**历史已评测技能
      - 进度：抽样与基础设施已完成（见 #1-a）；**标注者 A 已全量完成 15/15**；剩余 = 标注者 B 独立全量 15 个 + kappa ≥ 0.8 裁定 + 合并 `truth.json`
      - **A 面分布实测（15 个样本，yes 计数）**：`user_content` **15/15**、`tool_calls` **15/15**、`exec_code` 11、`net_egress` 11、`fs_access` 10、`prompt_intent` 9、`cred_access` 8、`state_persist` 3；`agent_comms` **0/15**、`system_instruction` **0/15**；`unsure` 5 项（`external_dep`×2、`prompt_intent`×2、`agent_comms`×1）
      - **分布暴露两个必须处置的问题**：① `agent_comms` / `system_instruction` **无阳性样本** → 这两个标签的**召回率无法度量**（没有可召回的阳性），且扫描器一旦打出 yes 精确率必为 0；② `user_content` / `tool_calls` **15/15 恒真** → 对准入无区分度，与 U4 判定的"映射恒真即冗余"同理，须在标签集重构时重新审视其定义边界
      - 硬约束：标注期间**不得参考** `surface_tagging.py` 的输出（否则真值与被测对象耦合，召回率失去意义）

- [ ] **#1-b** 标注者 B 独立全量标注
      - 锚点：`benchmark/annotator_b_brief.md`（可直接粘贴给新会话的任务书）；`benchmark/truth_b.json`
      - 验收：15 个技能 × 11 标签 = **165 个判定全部填满**（无 `null`）；**B 面标注期间未读取 `truth_a.json`、未读取 `surface_tagging.py` 输出**；完成后跑 `scripts/benchmark_agreement.py` 得 kappa ≥ 0.8
      - 独立性硬约束：B 必须在**全新会话**执行；同会话连做 A 与 B 会使 kappa 退化为自证

- [ ] **#1-c** 样本平衡补样与标签区分度复核
      - 锚点：`benchmark/benchmark_set.json`；`scripts/build_benchmark_set.py`（新增平衡约束）
      - 验收：① 补入 **≥ 3 个 `agent_comms` 阳性**，使每个标签的**阳性数 ≥ 3 且阴性数 ≥ 3**；② 对 `user_content` / `tool_calls` 出具"是否收窄定义"的裁决意见（15/15 说明其当前定义过宽，等同于恒真）；③ 对 `system_instruction` 的处置出具裁决（见下）
      - 硬约束：补样**不得**以 A 面标注作为筛选真值（会与真值耦合）；只能按"描述中明确出现多 agent / 系统指令"等**客观检索式**定向取样
      - **补样已完成（`benchmark/supplement_set.json`）**：定向检索得 `agent_comms` 候选 37 个，核验后取 **4 个**——`agent-team-orchestration`（多 agent 团队编排 + 交接协议）、`content-factory`（五个 agent persona + `spawn separate sub-agents`）、`leader`（内置技能，"把活分给几个 agent 并行"）、`capability-evolver`（经 Proxy mailbox 与 hub 通信，**边缘，待 B 面裁定**）
      - **`system_instruction` 零阳性是分布事实，不是抽样失误**：295 个技能按"system prompt / 忽略先前 / 改写指令"检索仅 **2 个**候选，且核验后二者均为**产出提示词文本给人用**（`prompt-engineering-expert` 设计 system prompts、`novel-writer` 构建 LLM 提示词），**不是技能自身写入/改写系统级指令** → 按现口径均应为 no，即本池 **0 真阳性**。三个处置选项待裁决：① 与 `prompt_intent` 合并（前者可视作后者的极端形态）；② 改用定向构造样本度量召回率；③ 保留标签但在报告标注"真实分布罕见，召回率未经实测"

- [ ] **#2** 词形字典与概念层改造
      - 锚点：`scripts/surface_tagging.py` `_SURFACE_TAGS`；改造方案文档「词形扩展方法」
      - 验收：11 个标签均有概念定义 + 中英词形表；凭证类补齐 `credential` / `secret` / `api_key`；纯中文信号标签补齐英文词形；改词表跑基准集并报告 delta

- [ ] **#3** 标签集拆分与信号收窄
      - 锚点：`scripts/surface_tagging.py` `_SURFACE_TAGS`；改造方案文档「拆分方案」
      - 验收：`fs_net_cred` → `fs_access` / `net_egress` / `cred_access`；`secret_memory` → `state_persist`；`\.md` / `\.json` / `search` 等恒真信号已剔除或收窄；历史产物兼容策略已落地（见未决 U2）

- [ ] **#4** 判定分层与全量输出（**决策 U3：不含 LLM 层**）
      - 锚点：`scripts/surface_tagging.py` `tag_skill()`；改造方案文档「各层具体职责」
      - 验收：S1 / S2 两层可用（**不引入 S3 语义层**）；产物输出**全部标签**的二元判定 + 判据 + 证据（未命中亦输出）；判定来源区分 `static` / `runtime`（`default` 已由 U4/V4 裁决取消）；**每个命中附 `evidence_level`（E1–E4，机械判定，取最高等级）**——用于在不牺牲召回的前提下提供严格口径视图

- [ ] **#5** 语法层基础版（**对应 U7：做语法层，不做数据流污点追踪**）
      - 锚点：`scripts/surface_tagging.py`（新增语法级判定分支）
      - 验收：识别执行类调用节点与 import 语句；同义改写测试中 M4（`subprocess` → `os.popen`）造成的 `exec_code` 丢失被补回；Python 外的语言仍走词形层

- [ ] **#6** 防漏检门禁
      - 锚点：`.project/tmp/check_rule_code_consistency.py`（同模式扩展）；基准集度量脚本
      - 验收（**U1 已裁决 2026-10-11**）：词表或映射变更后重跑基准集；**逐标签召回率 ≥ 0.90（硬门禁，不达标阻断归档）**；**单一判定信号命中率 ≤ 0.95（硬门禁，超出即进强制下线候选）**；**逐标签精确率 ≥ 0.60（软告警，不阻断）**

- [ ] **#7** 映射对齐（与 `2026-10-09-surface-tag-asi-mapping-alignment` 协同）
      - 锚点：`scripts/_common.py` `TAG_TO_ASI`；`references/SafeTest/dimensions/Mapping-Matrix.md`
      - 验收：11 个标签的两条路径 100% 一致；人为改坏任一行能被报出；无孤儿（10 ASI + 6 视角均有归属）

## 3. 待观察（依赖真实运行）

- [ ] 6 个既有技能重新打标后，标签集合与探测集合的变化已记录（对照本变更 Why 的实测二）
- [ ] `aihot` 的 `net_egress` 已由未命中转为命中（对照实测三）
- [ ] 覆盖面告警中的未覆盖 ASI 集合变化已记录（v16 基线：覆盖 6/10）
- [ ] 无新的误报或回归：回归入口退出码 0

## 4. 归档前自检

- [x] proposal 的 Why 含实测证据（五项实测 + 分类学依据）
- [x] 每条待实施项含锚点与验收
- [ ] 已跑回归且退出码 0
- [ ] 改动写入一律走 `govkit.py`（备份 + 断言 + 体积守卫 + 原子写 + 操作日志）

> 补充裁决（2026-10-12）：**取向 = 召回优先**（不变）；**优先级 = 有效性 > 召回**（新增）；新增 **U10 可运行性门禁**与**证据分级 `evidence_level`**（见改造方案「裁决落地值」）。未决项状态（2026-10-11）：**U1 / U2 / U3 / U4 / U5 / U6 / U7 / U8 均已裁决**（见改造方案文档「决策建议与风险分析」与「裁决落地值」）；U9（业界基准数字核实）为执行前核实项。**未决未裁决前，#3 与 #4 的实施范围不得自行扩大。**
