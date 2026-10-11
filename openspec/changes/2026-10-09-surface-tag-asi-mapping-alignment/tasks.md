## 1. 已实施

（无——本变更为立项阶段，尚未启动实施）

## 2. 待实施

- [ ] **#1** 领域决策：裁定权威源，并逐标签裁定最终 ASI 归属（含 ASI01 归属、`user_content` / `external_dep` 整体错位）
      - 锚点：`scripts/_common.py:145`（`TAG_TO_ASI`）；`references/SafeTest/dimensions/Mapping-Matrix.md:38-48`（准入表）
      - 验收：产出「标签 → 最终 ASI 集合 + 语义理由」表并写入 `Mapping-Matrix.md`；9 个标签各一行，**无待定项**

- [ ] **#2** 修正不一致：按 #1 结论同步 `TAG_TO_ASI` 与准入表
      - 锚点：`scripts/_common.py:145`；`references/SafeTest/dimensions/Mapping-Matrix.md:38-48`
      - 验收：9 个标签两条路径逐项一致（给出改前 / 改后对照表）；Surface tagging 单测或同名校验通过

- [ ] **#3** 新增一致性校验，使未来漂移能被自动发现
      - 锚点：`.project/tmp/check_rule_code_consistency.py`（RC-01~RC-06 同模式；建议编号 RC-07）
      - 备选：`scripts/validate_manifest_contract.py` 新增守卫
      - 验收：**人为改坏**准入表任一行能被报出；无差异时放行且退出码 0

- [ ] **#4** 处理 ASI08 无标签触发的覆盖缺口
      - 锚点：`references/SafeTest/dimensions/Mapping-Matrix.md:38-48`；`scripts/_common.py` `MIN_ASI_COVERAGE = 9`
      - 验收：至少一个标签映射到 ASI08，**或**显式记录"ASI08 不由标签触发"的领域决策与理由

## 3. 待观察（依赖真实运行）

- [ ] 既有技能（`table_column_relations` / `aihot` / `leader` / `skill-doctor`）重新打标后，**标签集合与探测集合的变化已记录**
- [ ] 覆盖面告警中的未覆盖 ASI 集合变化已记录（v16 基线：覆盖 6/10，未覆盖 ASI01 / 02 / 05 / 08）
- [ ] 无新的误报或回归：回归入口退出码 0

## 4. 归档前自检

- [x] proposal 的 Why 含实测证据（9/9 不一致对照表 + ASI08 缺口）
- [x] 每条待实施项含锚点与验收
- [ ] 已跑回归且退出码 0
- [ ] 改动写入一律走 `govkit.py`（备份 + 断言 + 体积守卫 + 原子写 + 操作日志）
