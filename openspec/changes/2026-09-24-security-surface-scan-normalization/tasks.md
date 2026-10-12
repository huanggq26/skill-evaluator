## 1. 已实施

（无——本变更为立项阶段，尚未启动实施）

## 2. 待实施

- [ ] ~~**N1** 建立「概念 → 词形变体」同义词词典~~ **已转出（2026-10-12）**：由 `2026-10-10-attack-surface-tag-system-refactor` 的 **#2** 统一承载（目标相同：概念 → 中英词形表），**避免两份字典并存**。本项保留仅为追溯，实施以 #2 为准
      - 先梳理 9 个标签各自对应的**概念**（如 credential / persistence / injection carrier…）
      - 每个概念列出中英文词形变体，标注每个词形的来源与理由
- [ ] ~~**N2** 标签定义改为引用概念~~ **已转出（2026-10-12）**：同 N1，由 refactor 变更的 **#2** 承载
      - 保持输出结构不变（`tag` / `evidence` / `mapped_asi`）
      - 保持证据行号机制不变
- [x] **N3** ✅（2026-10-05 已实施：`Mapping-Matrix.md` 准入表补至 9 行并改「键名 + 中文说明」双列） 准入表补齐至 9 个标签；左列改为「键名 + 中文说明」双列
      - 新增三个标签的触发维度**已于 2026-10-05 由领域决策确认**（依据 Mapping-Matrix 现有语义推导后拍定）：
        - `tool_calls` → `dangerous-calls`、`ASI02`、`ASI05`、`permission-boundary`、`ASI03`
        - `prompt_intent` → `ASI01`、`social-engineering`、`content-policy-compliance`
        - `system_instruction` → `ASI01`、`ASI10`、`social-engineering`
      - 遗留（另行登记）：`surface_tagging.py` 中 `prompt_intent` / `system_instruction` 的 `mapped_asi` 现为 ASI04/ASI07、ASI04/ASI10，与上述语义判定不一致，疑为映射存疑，归入 T-01 关联项单独处理
- [x] **N4** ✅（2026-10-05 已实施：展示名加 `sg_` 前缀，取值键不改） 命名空间隔离：**展示名**加 `sg_` 前缀，消除与传统视角的同名异义
      - 靶子修正（2026-10-05）：撞车发生在**展示名 vs 目录名**（`permission_boundary` 下划线 vs `permission-boundary` 连字符），不是取值键
      - 因此：`_common.py` `SECURITY_CATEGORY_TO_DIMENSION` 的值改为 `sg_abnormal_behavior_control` / `sg_permission_boundary` / `sg_sensitive_data_protection`
      - 同步改 `cacu_total_score.py:927-945`、`generate_outputs.py`、`spec_contract.md`、`specs/Template.spec.md`、`specs/scores.spec.md`
      - **`security_group` 取值键不改**（`abnormal`/`permission`/`sensitive` 为对外契约，已写入 v14–v16 产物 manifest 与目录结构）
- [ ] **N5** 建立基准测试集并度量召回率
- [ ] **N6** 文档侧改为引用单一权威源，删除重复词表值
      - 进度（2026-10-09 核实）：**代码侧已收敛**（`auto_security_spec` / `validate_manifest_contract` / `surface_tagging` 三处改为引用 `_common.TAG_TO_ASI`，对应 T-01）；**文档侧未收敛**——`stage1_sample.md` L143-148 仍逐条列出 tag→ASI 值，属重复定义，本项仍有效
- [x] **N7** ✅（2026-10-07 已实施：`_common.MIN_ASI_COVERAGE` 下限默认 9 + 覆盖面告警） 覆盖面保底：设定 ASI 覆盖下限或提供"全覆盖模式"选项（基线：原始固定配额 9 探测 / 9 ASI）
- [x] **N8** ✅（2026-10-07 已实施：`scripts/resolve_review_context.py` 解析校验审计手册/案例库，已接入阶段 5） 打通历史积累消费路径：评审按 `primary_asi_category` 与 `supporting_dimensions` 检索规格文件与视角目录
      - 当前源码与阶段文档均未引用 Audit-Manual / Case-Library，属悬空资产
- [ ] **N9** 记录"去冗余 vs 完备性"的取舍决策与代价

## 3. 待观察（依赖真实运行）

- [ ] 回归后标签集合与历史一致
- [ ] 召回率较改造前有可度量提升
- [ ] 未引入新的误报（基准测试集验证）

## 4. 归档前自检

- [ ] N1–N6 完成
- [ ] 待观察项在真实运行中确认
- [ ] `openspec validate --changes` 通过
- [ ] 回归入口退出码 0

## 备注

- 本变更由 `skill-evaluator_risk-assessment-explainer.md`「一致性核查与风险 / 已知限制」章节所记录的问题驱动。
- N3 中新增三个标签的触发维度归属**需用户或领域专家决策**，是实施前的阻塞项。
- 评分机制（Grader 模板态）与证据采集范围问题**不在本变更范围**，另立议题。
