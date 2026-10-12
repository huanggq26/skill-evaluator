# 变更提案：告知性链接不计入依赖可用性，且 REJECT 触发维度在报告中可辨

## 背景（Why）

治理台账 G24（2026-10-12 登记）经 2026-10-12 裁决，方向确认为 **A 方案**。裁决要点：

1. **告知性（信息性）链接不是运行时依赖**。它不可达时，应写入**问题报告**供技能作者后续优化，**不得影响上架结论**。
2. 经费领域确认：网络/环境的暂时原因造成的功能依赖不可达，**已经不是一票否决**（`dep_probe.py` 默认 `env_issue`，仅"其余 4xx"才置 `contract_defect`）。故本次**不改**已有可用性分级逻辑。

### 实证：当前口径不成立

aihot 本地实测（run `v1`）中，同一份 SKILL.md 里的两类链接被同样的规则处理：

| 链接 | 性质 | 探测结果 | 当前后果 |
|---|---|---|---|
| `https://aihot.virxact.com/openapi.yaml` | **文档链接** | 可达 | 计入可用性，**拿满分 100** |
| `https://aihot.virxact.com/mp`（语境：可以提示用户去 X 看） | **告知性阅读链接** | 不可达（迁移） | 计入可用性，**可用性 0 → REJECT** |

同为文档/告知性质，只因网络状态不同，一边加分一边否决上架。这是口径缺陷，非技能缺陷。

### 连带问题：REJECT 的触发维度在报告中不可辨

`benchmark_report.md` 把「安全评分 100.00」与「REJECT」印在相邻行。实际两者无关：

- `cacu_total_score.py:1048` 安全门禁：本例 `security_score=100`，**未触发**
- `cacu_total_score.py:1067` 可用性门禁：本例 `dependency_score=0`，**触发**

版面误导读者以为技能是因安全问题被拒。

## 目标契约

1. **告知性链接**：在依赖提取侧标为 `informational`；**不探活、不计入可用性评分、不触发结构性否决**；
   不可达时**写入问题报告**（`problem_report.md`），供技能作者后续优化。
2. **判据**（两者同时满足才判 informational）：
   - 出现**引导语语境**：所在行含「提示用户去 / 详见 / 参考 / 参见 / 访问 / 前往 / 看」等引导词
   - **非 API 形态**：路径不含 `/api`、`/v\d`、`openapi`、`swagger` 等技术契约标识
   > API 形态优先于语境：如「详见 API 文档 `https://api.x.com/v1`」仍按运行时依赖处理，避免误丢真依赖。
3. **报告呈现**： Verdeict 区明确写出触发维度（安全 / 可用性），并给出对应门禁值与实测值，不再让读者自行猜测。

## 非目标

- **不**改动 `dep_probe.py` 已有的分级逻辑（`env_issue` / `config_defect` / `contract_defect`）。
- **不**解决"单次 4xx 被一律定性为永久性契约缺陷"（无法区分服务端临时改版）——另行登记。
- **不**修改 `cacu_total_score.py` 的安全权重（现为硬编码 0.0）——另行登记，待领域决策。
- **不**放宽安全门禁 `SECURITY_GATE=100`。

## 依据

- 治理台账 `.project/TASKLOG.md` **G24**（2026-10-12 裁决，选 A）
- `scripts/dep_probe.py:70` 注释：默认 `env_issue`，结构性否决需显式置 `contract_defect`
- `scores.json`：`security_score=100.0`、`dependency.score=0`、`verdict.reasons` 仅含可用性一条
- 规则层：改流水线脚本后须跑 `selfcheck_refactor.py` / `check_release_isolation.py` / `check_rule_code_consistency.py` 均退出码 0
