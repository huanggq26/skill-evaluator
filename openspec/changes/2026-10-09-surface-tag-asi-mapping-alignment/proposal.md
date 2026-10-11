# surface-tag-asi-mapping-alignment

## Why

决定"生成哪些探测"存在**两条并行路径**，结论长期互不一致且**无任何对账校验**——此为 G16（清理残留字面量）核对单一权威源时暴露。

实测对照（2026-10-09 取数：代码侧 `scripts/_common.py` `TAG_TO_ASI`；文档侧 `references/SafeTest/dimensions/Mapping-Matrix.md` 准入表第 3 列，仅取其中的 ASI 项）：

| 标签 | 代码 `TAG_TO_ASI` | 准入表触发维度中的 ASI | 一致 |
|---|---|---|---|
| `exec_code` | ASI01, ASI05 | ASI02, ASI05 | ✗ |
| `external_dep` | ASI02, ASI08 | ASI04, ASI07 | ✗ 完全不同 |
| `fs_net_cred` | ASI03, ASI07, ASI10 | ASI01, ASI03 | ✗ |
| `secret_memory` | ASI06, ASI09 | ASI06, ASI03 | ✗ |
| `user_content` | ASI04, ASI07 | ASI09, ASI10 | ✗ 完全不同 |
| `agent_comms` | ASI09, ASI10 | ASI07, ASI10 | ✗ |
| `prompt_intent` | ASI04, ASI07 | ASI01 | ✗ 完全不同 |
| `tool_calls` | ASI01, ASI02, ASI03 | ASI02, ASI05, ASI03 | ✗ |
| `system_instruction` | ASI04, ASI10 | ASI01, ASI10 | ✗ |

**9 个标签全部不一致（0/9 一致）。**

**为什么必须管**：

- 代码路径（`auto_security_spec.py` / `generate_probe_scaffolds.py` 走 `TAG_TO_ASI`）**实际决定生成的探测集合**；
- 准入表路径（`Mapping-Matrix.md`「攻击面 → SafeTest 维度准入规则」，阶段 1 步骤 1.5 阶段 B 的查表源）是**人工查表**依据；
- 二者并集不同、互不校验 → "文档说该测 A、实际生成的是 B"长期静默存在。

**额外发现**：准入表触发维度的 ASI 并集为 `{01,02,03,04,05,06,07,09,10}`，**缺 ASI08**——无任何标签能通过准入表触发 ASI08（级联失败）。这与 v16 实测覆盖面告警所列"未覆盖 ASI01 / 02 / 05 / 08"吻合，说明 ASI08 的覆盖缺口在文档侧另有成因。

**溯源**：原登记为治理待办 **G17**（两个标签映射不一致）与 **G18**（两条路径无对账守卫）。实施前复核发现差异面为 9/9 而非 2 个，故按行为变更合流，任务态由本变更承载。

## 任务类别判定

- 判据：是否改变对外可观察行为 → **是**（修正 `TAG_TO_ASI` 会改变"命中标签 → 生成哪些探测"，进而改变产物目录、报告覆盖与覆盖面告警）
- 分流：**行为变更** → 由规范区变更承载任务态，不登记 TASKLOG（避免双写）

## What Changes

1. **裁定权威源**：`_common.TAG_TO_ASI` 为唯一权威；准入表的 ASI 列改为**由其派生或校验**，不再各自写死。
   - 改前：两处各自手写，靠注释互称"与某某一致"，无机器校验。
   - 改后：一处定义、一处引用，并有校验使漂移报错。
2. **逐标签裁定正确映射并修正**：含 `prompt_intent` / `system_instruction` 的 ASI01 归属、`user_content` / `external_dep` 的整体错位。每个标签的最终归属须给出语义理由。
3. **新增一致性校验**：逐标签比对"准入表触发的 ASI 集合"与 `TAG_TO_ASI` 集合，不一致即报错（建议新增 RC-07，置于 `check_rule_code_consistency.py`，与 RC-01~RC-06 同模式）。
4. **ASI08 覆盖缺口归档或修复**：至少一个标签映射到 ASI08，或显式记录"ASI08 不适用/不由标签触发"的领域决策。
5. **决策留档**：每个标签的最终 ASI 归属与语义理由写入 `Mapping-Matrix.md`，作为后续改动的判据。

## 验收（改后自验证）

- [ ] 一键回归入口：`python3 .project/tmp/check_rule_code_consistency.py && python3 .project/tmp/test_backfill_reviews.py`
- [ ] 关键锚点仍存在（govkit verify）
- [ ] 产物 / 评分无意外变化（附实测对照值）
- [ ] 补充判据：9 个标签两条路径 **100% 一致**（改前 0/9）
