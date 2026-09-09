# OpenSpec 改造落地归档（2026-09-09）

> 专题方案执行后收回归档，项目不再依赖会话上下文或外部位置。

## 一、改造分两段

| 段 | 任务 | 状态 |
|---|---|---|
| 第一段 | T1 环境就绪（安装命令行 + `openspec init`）、T2 治理契约落地（`openspec/config.yaml`） | 完成 |
| 第二段 | T3 基线化 scoring、T4 首变更演练、T5 收尾 | 完成（本次补齐） |

**第二段曾整体丢失**，由用户翻查历史会话发现。丢失与补做过程见第三节——这是本次改造最有价值的产出。

## 二、各任务成果

### T3 基线化 scoring

- 产出：`openspec/specs/scoring/spec.md`（8 条需求 + GIVEN/WHEN/THEN 场景）
- 来源：`references/spec_contract.md` §3/§4/§5 + `references/specs/scores.spec.md`
- 性质：**只搬移既有契约，未改任何评分行为**——故属治理改造，不进规范区变更
- 校验：`openspec spec validate scoring` → valid

### T4 首变更演练（三方漂移告警）

- 来源：`ERR-021` 修改策略第 4 条「⬜ 三方校验（待做）：description ↔ USER_GUIDE ↔ 功能表 漂移告警」
- 变更：`add-three-way-drift-alert`，走完 propose → apply → archive
- 实现：`scripts/validate_function_table.py` 新增第 4 层三方漂移检测（警告级，不阻断）
- 归档：`openspec/changes/archive/2026-09-09-add-three-way-drift-alert`；`function-description` spec 并入主规范（5 条需求）
- **实施中被推翻的设计**：按比例断言「新增未同步」——实测三种切词下缺失率恒在 68%–98%，差异样例为「今日 vs 今天」这类同义改写，机械层无法区分「能力缺失」与「用词不同」。已移除，只保留缺项与零交集两类可靠判定；语义级漂移交 AI 裁定。详见该变更的 `design.md`

### 环境收敛（ERR-025，改造期间插入）

旧 Node 运行时（v22.22.3）来自第三方工具链目录，openspec 装在它下面形成依赖耦合。收敛为唯一一套：

- 装独立 Node（`~/.workbuddy/.../22.12.0`），npm 全局前缀随之迁移
- `~/.local/bin/node|npm|npx` 重指向；openspec 用 wrapper 硬编码解释器路径（不用裸软链，因包内 shebang 是 `#!/usr/bin/env node` 会回落到 PATH）
- 旧副本 `trash` 入回收站（`~/.Trash/node.20260909-200524`，**暂不清空，观察项见 TASKLOG P9**），原路径建软链指向新 Node 以兼容硬编码引用
- 四处入口（`which node` / `~/.local/bin/node` / `~/.hermes/node/bin/node` / `CODEBUDDY_NODE_BIN`）全为 v22.12.0

## 三、机制缺陷：治理改造任务没有载体（核心教训）

**现象**：T3–T5 既未进 TASKLOG，也未进 openspec，悬空于对话；会话压缩后丢失，新会话查档案也查不到。

**根因**：`openspec/config.yaml` 第 5 条「变更任务不登记进任务记录」的**边界不清**。该条本意是防止 openspec 承载的行为变更与 TASKLOG 双写，但字面上涵盖所有「变更任务」，导致**治理改造任务**（不产生对外行为变更、按第 7 条不该进规范区）被一并挡在 TASKLOG 外，两边都不收。

**修复**（已落地）：

1. `config.yaml` 第 5 条按**判据**分流：是否改变**对外可观察行为**——
   - 行为变更 → 规范区承载，不进 TASKLOG（防双写）；
   - 治理改造（规范区建设、基线化、流程演练、工具链收敛、方案归档、档案建设）→ 不在规范区建变更，**必须**进 TASKLOG 的「治理改造」分区。
2. 第 6 条恢复机制补充：会话恢复须读 TASKLOG **含治理改造分区**，不得只查规范区就下结论。
3. TASKLOG 增设「治理改造（非行为变更）」分区，补登 G1（T3）/ G2（T4）/ G3（T5）。

**判据要点**：不是「是不是叫变更」，而是「是否改变对外可观察行为」。基线化既有契约不改变行为 → 治理类。

## 四、错误档案回写

| 档案 | 动作 |
|---|---|
| `ERR-021` | 第 4 条由 ⬜ 待做 → 已实施；补实测数据与「实测推翻」留档（防重犯） |
| `ERR-025` | 补第 3 层归因（运行时归属耦合）+ 收敛为唯一运行时的策略与最终态验证 |
| `AGENTS_RULES.md` | 修改纪律第 7 条：删除一律走 `trash`，禁 `rm`，被安全拦截时不得改写为等效删除绕过；跨会话上下文不建全局记忆，只落项目档案 |

## 五、遗留

- **语义级漂移**（某处新增能力另一处未同步）需 AI 裁定，机械层已明确不越权——待立项
- **工作区未提交**：档案改动（ERR-023/024/025/021）+ `TASKLOG.md` + `.gitignore`（`openspec/`、`.codebuddy/` 整目录过滤）+ `scripts/validate_function_table.py` + `openspec/`（已 gitignore）
- 回收站旧 Node 副本待观察后清空（TASKLOG P9）
