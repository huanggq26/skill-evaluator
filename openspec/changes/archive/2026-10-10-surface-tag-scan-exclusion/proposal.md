# surface-tag-scan-exclusion

## Why

`_candidate_files()` 对 `scripts/` 下的 `.py` / `.md` / `.json` / `.sh` / `.txt` 做**全递归**扫描（源码注释称"不递归未知深目录"，实际实现为 `rglob("*")`，即全递归）。因此若被测技能 `scripts/` 下存在依赖目录或缓存目录，**其中的第三方代码会被计入打标**。

**实测（2026-10-10，`SAMPLE_ROOT` 6 个样本）**：`scripts/` 下第三方 / 缓存目录数量为 **0** → 当前**尚未发生**误报，属**潜在风险**而非现存问题。

**风险性质**：依赖与缓存目录中的第三方代码必然包含 `subprocess`、`open(`、`.json` 等强信号 → 一旦出现，会命中 `exec_code`、`fs_net_cred`、`secret_memory` 并放大证据条数。

**与已实测污染同源**：向 `scripts/` 注入 tracer 脚本后，打标由 `secret_memory`(2) 变为 `exec_code`(6)、`fs_net_cred`(5)、`secret_memory`(12)——新增 2 个标签、证据 +19 行。本次要防的污染**机制完全相同**，差别只是污染源来自插桩还是依赖目录。

**与"召回优先"的关系**：被排除的是**依赖 / 缓存代码**，不是被测技能自身的能力，故排除提升精确率而**不损失有意义的召回**。

**来源**：自运行时能力观测项目（策略文档「插桩与污染源的影响范围界定」）拆出的独立小改造——它与运行时观测无关，且零回归，不必随该项目排期。

## 任务类别判定

- 判据：是否改变对外可观察行为 → **是**（当被排除目录存在时，打标结果与产物字段会变化）
- 分流：**行为变更** → 由规范区变更承载任务态，不登记 TASKLOG（避免双写）

## What Changes

1. `_candidate_files()` 增加**排除目录集合**：`node_modules`、`.venv`、`venv`、`__pycache__`、`.trace`
2. 排除须**可追溯**：产物记录被排除的目录清单与文件数量，**禁止静默排除**（否则漏扫不可发现）
3. 明确**不排除** `tests/` / `examples/` / `docs/`——属技能本体，可能含真实能力证据；扩大排除会伤召回
4. 不改扫描后缀集合，不改信号词表，不改标签集

## 验收（改后自验证）

- [x] 一键回归入口：`python3 .project/tmp/selfcheck_refactor.py` → 退出码 1，但**失败项与改动前逐项一致**（`[E29]` × 3，2026-10-09 既有，与本变更正交；对照 `/tmp/sc.out`）
- [x] 关键锚点仍存在（govkit verify：`_EXCLUDED_DIRS` / `excluded_dirs` / `def _candidate_files` / `node_modules` 全部 ✅）
- [x] 产物 / 评分无意外变化：6 样本标签数 / 证据条数改动前后逐项一致（2/4、3/9、3/64、9/1827、5/17、5/82）
- [x] 补充判据一（**零回归**）：6 个既有样本打标结果逐项一致；`excluded_dirs` 均为 `[]`（`skill-evaluator/scripts/__pycache__` 存在但仅含 `.pyc`，非候选后缀，故 0 条）
- [x] 补充判据二（**排除生效**）：`/tmp/excl_demo/skill` 中 `node_modules` 下 2 个含 `os.system` / `subprocess` 的文件不进证据，产物记 `excluded_dirs=[{"dir":"scripts/node_modules","files":2}]`；改前则误命中 `exec_code` 2 条
- [x] 补充判据三（**不误伤**）：同一样例 `scripts/tests/test_app.py:L1` 的 `fs_net_cred` 证据仍被正常扫描
