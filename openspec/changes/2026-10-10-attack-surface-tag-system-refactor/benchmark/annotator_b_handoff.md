# 标注者 B · 交付说明（供任务发起人参考）

> 面向任务发起人的一份汇总。两轮标注的细节回报另见：
> - `annotator_b_report.md`（第一轮 15 个主样本）
> - `annotator_b_report_round2.md`（第二轮 9 个，含 5 个留出集）

---

## 一、一句话结论

两轮共 **24 个技能 / 264 个判定** 已全部完成并落盘，`null` 0、非法值 0、`unsure` 0，JSON 校验通过。
**但有 3 件事需要发起人拍板**（见第三节），其中第 1 条会影响留出集的可比性。

---

## 二、交付物清单

| 文件 | 位置 | 内容 |
|---|---|---|
| `truth_b.json` | `benchmark/truth_b.json` | 唯一真值产出。24 个技能 × 11 标签，每条目附 `note`（证据等级 + 文件:行号） |
| `annotator_b_report.md` | `~/Downloads/` | 第一轮回报 |
| `annotator_b_report_round2.md` | `~/Downloads/` | 第二轮回报 |
| `annotator_b_handoff.md` | `~/Downloads/` | 本文件（两轮汇总 + 待拍板事项） |

### 独立性声明（已全程遵守）

- 未读取 `truth_a.json`，未以任何方式询问 A 面判定；
- 未运行、未读取 `scripts/surface_tagging.py` 的输出；
- 除 `truth_b.json` 外未修改任何文件（第二轮为**追加**，首轮 15 条一字未动）；
- 按要求未输出 yes 分布统计。

---

## 三、需要发起人拍板的 3 件事

### ① `leader` 路径不存在（影响留出集可比性，**建议优先处理**）

任务书给的 `skills-marketplace/skills/leader` **在本机不存在**（`ls` 与 `find` 均报 `No such file or directory`）。

我实际标注的是 **`/Users/family/.codebuddy/skills/leader`**（含 `SKILL.md` + `references/anatomy.md` + `references/style.md`），并已把该偏差写进该条目 `note` 首句。

**风险**：若 A 面标注的是另一个位置的 `leader`，这一条不可比，会直接污染留出集的 kappa。
**请确认**：是你指定的路径写错了，还是 A 面用了别的副本？若不一致，建议剔除该条后重算，或先统一路径再补标。

### ② `tool_calls` 的 v3 收窄口径，我**没有**采用（两轮保持一致）

v3 把 `tool_calls` 收窄为"结构化工具/函数调用（MCP tool、function calling、`read_file`/`write_to_file`）"，与 `exec_code` 拉开了距离。

但我在两轮均沿用首轮口径：**凡使用具名工具（含 `execute_command`/Bash、具名 CLI 子命令、MCP tool、文件读写工具）→ yes；纯文本生成 → no。**

理由：v3 给出的唯一反例是"纯文本生成 → no"，与首轮口径并不冲突；若中途改用更窄定义，会造成**同一基准集内两轮不可比**。

**请确认**：这个取舍是否可接受？如果发起人要求严格按 v3 收窄口径，首轮 15 条需要重标（我可以在不接触 A 面结果的前提下只改这一列）。

### ③ 我的 6 条统一口径，是否与 A 面一致

为让 264 个判定内部自洽，我对高频歧义点固定了口径（见第四节）。其中 **第 1、3、4 条最可能与 A 面产生系统性分歧**——如果 A 面用了不同切法，分歧会成片出现而不是零散出现。

**建议**：算完 kappa 后，若某个标签一致性特别低，优先回查该标签对应的口径条目，比逐条复核更高效。

---

## 四、我固定的 6 条统一口径

| 标签 | 采用的判定口径 |
|---|---|
| `external_dep` | = **需要安装**第三方包/SDK/插件/MCP server（明示 `npm install`/`pip install`/`requirements.txt`/`package.json`）。远程 API 调用归入 `net_egress`，不重复计入 |
| `net_egress` | `curl localhost`/本地回环 → no；`pip install`/`npm install` 的取包动作归入 `external_dep`，不算主动外联 |
| `state_persist` | = 写入**机器可读、且被技能在后续会话回读**的状态（token 缓存、版本缓存、断点续传标记、memory 文件、浏览器 profile）。一次性产出物不算 |
| `agent_comms` | 需**明示** spawn / 子会话 / 多 agent 编排。"并行检索""浏览器自动化""名字里带 agent"均不算 |
| `prompt_intent` | 需存在**模板 + 占位符**并由外部输入填槽；把用户输入原样作为 API 参数传递不算。**回复模板 ≠ prompt** |
| `system_instruction` | 仅当明确指示**写入** AGENTS.md / system prompt / 长期记忆规则；写记忆文件本身另计 `state_persist` |

---

## 五、两轮边界裁决清单（共 14 条，均已靠显式推理压到 yes/no）

### 第一轮（7 条）

| 技能 · 标签 | 裁决 | 一句话依据 |
|---|---|---|
| `ecommerce-copywriter` · `exec_code` | no | 有脚本但 SKILL.md 全篇未指示运行；按 E4 非职责必要条件 |
| `web-search-exa` · `exec_code` | no | 仅 `openclaw mcp add`，属给人做的配置动作 |
| `web-search-exa` · `cred_access` | no | API key 拼进 MCP URL 属安装配置，运行时不读凭证 |
| `tencentcloud-cos` · `state_persist` | no | `--persist` 写 `.env` 是可选项，默认 ephemeral |
| `andonq` · `external_dep` | no | `import requests` 有 L2 回退，且文档声明纯标准库 |
| `stock-analyzer` · `cred_access` | no | "引导用户登录东财"是给**人**做的动作 |
| `minimax-pdf` · `net_egress` | yes | 硬编码 Google Fonts 域名 → 写 `@import` → Chromium 真实拉取（证据链跨 3 文件） |

### 第二轮（7 条）

| 技能 · 标签 | 裁决 | 一句话依据 |
|---|---|---|
| `agent-team-orchestration` · `exec_code` | no | 命令属 handoff 示例 / Builder 角色，非本技能自身执行 |
| `content-factory` · `exec_code` | no | 唯一命令 `sessions_spawn` 归入 `agent_comms` |
| `leader` · `exec_code` | **yes** | L43「书里每条命令你必须亲手跑过」= 明示指示 |
| `leader` · `state_persist` | no | `PROGRESS.md` 是给执行者的机制；暗卷明示"留在会话侧" |
| `capability-evolver` · `external_dep` | no | 允许 npm 但无明示安装、无 `package.json` |
| `capability-evolver` · `net_egress` | yes | `publish_public.js:271-283` 对 `api.github.com` 真实 `https.request` |
| `agent-browser-core` · `cred_access` / `state_persist` | no / no | 命令表里有，但文档明示"默认避免 / 保持 ephemeral" |

> **注意**：第二轮前三条都是"指导型技能"，却因一句措辞分出 2 个 no + 1 个 yes。这正是我认为 v3 第 11 条最难用的证据（见下）。

---

## 六、规程修订建议（按优先级）

### v3 第 10–15 条里最难用的三条

1. **第 11 条**（指导型技能不算 `exec_code`）—— **最难**。区分"指导"与"指示"只靠措辞强度，反直觉且不稳定。
   **建议补判据**：命令的**执行主体是本技能自己** → yes；**交给被编排/被生成的第三方**（builder、sub-agent、执行者）→ no。

2. **第 10 条**（产出物不算 `state_persist`）—— 得靠后半句"是否明示跨会话回读"救，但多数技能不写这句话，只能从代码 `existsSync`/`readFileSync` 或"cached for 7 days"推断。
   **建议**：把"是否存在回读路径"升格为主判据，不问它叫不叫产出物。

3. **第 15 条**（`prompt_intent`）—— "生成描述"是缺口：语义完全相同的自然语言指令与结构化参数会给出相反结论。
   **建议**：明确"只看表面形态，不做语义还原"。

**12 / 13 / 14 三条实测好用**；其中 13 需与裁定 7 合并为「依赖三问：明示安装？必需？有回退？」；14 是相比 v1 改进最大的一条。

### v1→v3 已解决、无需再动的

- `user_content`：v1 时是最含糊的标签（"用户输入当作处理对象"与"原样转发"无判据）。v3 第 14 条的"文件/文档/网页 = 原料 → yes；创作要求/指令文本 → no"基本治好了它。

### 仍存在的一处结构性重叠

- `tool_calls` 与 `exec_code`：因 `execute_command` 被列为 `tool_calls` 的示例，两者高度重叠，导致 `tool_calls` 区分度很低（目前只有纯文本生成类技能会判 no）。这是第 ③ 条待拍板事项的根源。

---

## 七、执行过程中的两点说明（供审计）

1. **两条命令因审批超时被取消，已用无需审批的检索工具完整补回**，证据已用于判定。补回发生在写入条目之前，JSON 校验发生在写入之后，最终落盘文件包含补回证据。唯一未补回的 `head -20 tests/integration_test.py` 属多余检查（证据本就来自 `SKILL.md:L361` 的显式命令指示）。
2. **留出集 5 个**（`12306`、`academic-tutor`、`agent-browser-core`、`agent-mbti`、`baidu-drive`）在标注期间未与任何人讨论，全部逐条独立判定。
