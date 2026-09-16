# ExecAgent Baseline 阶段

> 本阶段是 ExecAgent 的 **baseline** 运行实例（无 skill）。
> 完整流程、步骤、约束、验证均定义在 **`references/exec_common.md`**（两阶段共享的唯一流程权威来源，且不含任何 skill 逻辑）。
> 本文件仅声明本实例的运行参数与唯一一项 baseline 专属约束，**禁止在此内联重定义任何流程/约束**。

---

## 前置条件（进入本阶段前必须成立）

- 已阅读 `references/exec_common.md`（本阶段唯一流程权威来源）
- 阶段 0 门禁已通过、阶段 1 样本已生成
- **不得跳过本阶段**：上一阶段的**依赖状态**（含外部依赖不可达 / 配置待补 / 需鉴权）与**被测技能自身状况**（质量低 / 功能简单 / 依赖外部服务）**均不得**作为跳过本阶段的理由。仅契约型缺陷才阻断流程，判定见 `references/dependency_availability.md`「可用性探测结果的阻断边界」。
- 执行纪律见 `exec_common.md` 硬约束 #14–#16（执行尝试强制 / 执行失败处理 / 禁止未实测推断）。

## 本实例运行参数

| 参数 | 取值 |
|------|------|
| `MODE` | `baseline` |
| `{STAGE_OUTPUT_DIR}` | `{BASELINE_DIR}`（= `{RESULTS_ROOT}/{SKILL_NAME}/exec/baseline/`） |

> 所有跨阶段全局变量的唯一定义源为 `references/config.md`「跨阶段输出路径变量」表。禁止重定义，仅引用。

## 本实例专属约束（薄封装补充）

> 共享流程的「硬约束」列表未内置 skill 源读取规则，此处按 baseline 语义声明：

- **禁止读取 skill 源代码目录或 `SKILL.md`**（共享流程「禁止读取」指路项中已指向本封装）。

除此之外，共享流程对两阶段完全一致，本阶段无需其他补充。

## 执行入口

请按 `references/exec_common.md` 的「完成标准 → 阶段地图 → 执行步骤 → 结果验证」顺序执行，应用以下替换：

- 所有 `{MODE}` → `baseline`
- 所有 `{STAGE_OUTPUT_DIR}` → `{BASELINE_DIR}`

阶段终点为共享流程「步骤 5：停止」——baseline 完成后停止当前终端，不进入 with_skill。

## 相关文件

| 文件 | 用途 |
|------|------|
| `references/exec_common.md` | **唯一流程权威来源**（本阶段实际执行依据）；其文末「相关文件」节为本阶段所需的全部 spec / 脚本 / 配置完整索引，请以该节为准，本封装不重复列举以免漂移 |
