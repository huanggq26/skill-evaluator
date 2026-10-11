## 1. 已实施

（无——本变更为立项阶段，尚未启动实施）

## 2. 待实施

- [ ] **#1** 断言升级：新增有判别力断言（如 `field_not_empty`），替换纯存在性断言
      - 锚点：`scripts/probe_checks.py:59-111`（`run_check`）、`scripts/functional_checks.py:42-98`
      - 现状：`field_present` 对空列表 `[]`、空串仍判通过 → R8 / R10 等恒通过
      - 验收：产物字段为空时判 **fail**；v16 实测「恒通过项数」由 9 项下降，并给出改造前后对照

- [ ] **#2** 语义型判定引入可比对基准
      - 锚点：`scripts/generate_probe_scaffolds.py`（`_derive_rubrics`）、`references/stage4_spec.md` 步骤 1b
      - 方案：`TaskDescription.md` 注入可验证事实（golden facts），断言做「产物声明 vs golden」比对；或引入一次受控 LLM 判定并**把判定依据写入 evidence**，再由断言消费
      - 验收：R9（"未出现编造/幻觉"）的断言与其 rubric 语义**等价**——换话术编造能被判 fail

- [ ] **#3** 新增「断言 ↔ rubric 语义」一致性守卫
      - 锚点：`scripts/validate_manifest_contract.py`（新增守卫，编号待分配）
      - 验收：**人为制造一处错位**（如把某 R 的 CHECK 改空）能被该守卫报出；无错位时守卫放行

## 3. 待观察（依赖真实运行）

- [ ] v16 六个探针重跑：恒通过项数下降且不产生新的假阴性
- [ ] 有端点技能（如 aihot）评分不受影响（回归对照）
- [ ] 无端点技能仍走 N/A 不计分路径（与 T-08 不冲突）

## 4. 归档前自检

- [x] proposal 的 Why 含实测证据（断言逐项对照表 + 405 全绿 + R9 错位）
- [x] 每条待实施项含锚点与验收
- [ ] 已跑回归且退出码 0
- [ ] 改动写入一律走 `govkit.py`（备份 + 断言 + 体积守卫 + 原子写 + 操作日志）
