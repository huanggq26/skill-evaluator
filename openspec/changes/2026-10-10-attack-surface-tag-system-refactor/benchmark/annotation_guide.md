# 攻击面标签 · 人工标注规程（基准集真值）

> 本规程服务于**基准集真值标注**，与扫描器实现**完全独立**。
> 目的：产出一份"人认为该技能是否具备某能力面"的真值，用于度量扫描器的召回率与精确率。
> 因此：**标注时禁止参考 `surface_tagging.py` 的输出**，否则 kappa 与召回率都会退化为"自己对自己的一致度"。

## 判定对象

标注的是**能力面（该技能是否被授予/使用了某项能力）**，不是风险、不是好坏。

- ✅ 问的是："这个技能**会不会**做这件事？"
- ❌ 不问："这样做**危不危险**？"（那是 ASI 与评分桶的事，属下游）

## 证据等级（从强到弱）

| 等级 | 形态 | 示例 |
|---|---|---|
| E1 代码事实 | `scripts/` 内真实调用 | `subprocess.run(...)`、`requests.get(...)`、`os.environ["TOKEN"]` |
| E2 声明事实 | frontmatter / 清单声明 | `allowed-tools: Bash(...)`、`requirements.txt` |
| E3 指令事实 | `SKILL.md` 明确要求模型执行 | "执行 `python3 scripts/x.py`"、"。把结果写入 `~/.cache/x.json`" |
| E4 强暗示 | 描述中写明该能力是工作方式的必要部分 | "抓取指定网页"、"调用 XX API" |

判定规则：**E1–E3 任一命中即标 `yes`**；**只有 E4 时**，若该能力是技能完成其职责的**必要条件**标 `yes`，否则标 `no`。
**仅凭"可能""也许""可选"不标 `yes`**——召回优先只约束扫描器，不约束真值；真值必须保守准确，否则精确率无法计算。

## 11 个标签的判定口径

| 标签 | 标 `yes` 的条件 | 常见误判（应标 `no`） |
|---|---|---|
| `exec_code` | 会执行代码 / shell / 动态加载（`subprocess`、`os.system`、命令串、`eval`、`importlib`、要求运行某脚本） | 仅"输出一段代码文本"给人看，自己不执行 |
| `external_dep` | 依赖第三方包 / 服务 / 插件 / MCP server（`pip install`、`requirements.txt`、`package.json`） | 只用标准库；仅文档里提到别人的产品名 |
| `fs_access` | 会读写本机文件（`open(`、`write_to_file`、要求写 `/tmp`、读用户文件） | 只输出文本不落盘 |
| `net_egress` | 会主动向外发起网络请求（HTTP、API、抓取、curl、SDK 调用远端） | 只生成 URL 文本让人点；仅本地回环 |
| `cred_access` | 会读取或使用凭证（`token`、`api_key`、`os.environ`、cookie、`~/.ssh`、要求用户提供密钥） | 文档里出现"密钥"二字但技能本身不读取 |
| `state_persist` | 会把状态写到**跨会话可复现**的地方（缓存文件、日志、数据库、memory 文件） | 只在单次对话内记住 |
| `user_content` | 会把**用户会话内容 / 用户输入**当作处理对象（总结对话、按输入改写、读取聊天记录） | 仅接收一个参数字符串并原样转发（属 `tool_calls`） |
| `agent_comms` | 会与其他 agent / 子会话 / 团队通信（spawn、`send_message`、mailbox、多 agent 编排） | 单次调用一个 API 不算 |
| `prompt_intent` | 会把**外部输入拼进提示词**（模板、占位、条件分支、用户指令参与构造 prompt） | 固定提示词无外部插入 |
| `tool_calls` | 会调用工具 / 函数（`read_file`、`execute_command`、`web_fetch`、MCP tool、function calling） | 纯文本生成 |
| `system_instruction` | 会写入或改写系统级指令 / 规则（system prompt、忽略先前指令、注入规则、改写安全策略） | 只是自己的指令写得长 |

## 边界裁定（遇分歧按此处理）

1. **"要求模型去做"也算**：SKILL.md 指示模型执行（E3）与脚本自己执行（E1）**同等**——技能的能力面包含它驱动模型做的部分。
2. **`references/` 与 `scripts/` 同等对待**：都在技能目录内，均属客观产物。
3. **第三方依赖目录不算**：`node_modules` / `.venv` / `venv` / `__pycache__` / `.trace` 内的代码**不属于技能本体**，标注时忽略（与扫描器排除集合一致）。
4. **不确定标 `unsure`**：不要猜。两人都 `unsure` 的项在 kappa 计算中单独统计，不强行归入 yes/no。
5. **`tests/` / `examples/` / `docs/` 算**：属技能本体，可能含真实能力证据。

## 标注产出格式

`truth_<annotator>.json`：

```json
{
  "set": "benchmark-2026-10-11",
  "annotator": "A",
  "labels": {
    "<skill-name>": {
      "exec_code": "yes",
      "external_dep": "no",
      "...": "yes|no|unsure",
      "note": "判定依据（E1–E4 + 证据位置，如 scripts/run.py:L12）"
    }
  }
}
```

## 样本平衡要求（补充，2026-10-12）

首轮 15 个样本标注完成后，分布暴露两端问题，均会**直接毁掉度量**：

| 形态 | 后果 | 处置 |
|---|---|---|
| 某标签 **0 个阳性** | 召回率**无从计算**（没有可召回的阳性）；扫描器一旦打 yes，精确率必然为 0 | 定向补样，使每个标签阳性 ≥ 3 |
| 某标签 **全阳性** | 精确率**无从计算**（没有阴性）；该标签对准入无区分度，等同恒真 | 收窄定义，或明确其为"低区分度标签"并在报告中不参与覆盖面统计 |

> 首轮实测：`agent_comms` 0/15、`system_instruction` 0/15（无阳性）；`user_content` 15/15、`tool_calls` 15/15（全阳性）。

## 判定口径 v2（2026-10-12 修订 · 强制）

**修订缘由**：首轮 A/B 一致性 **Cohen's kappa = 0.4944 < 0.8**，165 对判定中 **40 项分歧（24%）**。
分歧**不是随机噪声，而是系统性口径分歧**——表现为 4 个标签的 kappa 恒为 0.0
（`user_content` / `tool_calls` / `agent_comms` / `system_instruction`）：
当一方把某标签**全部标成同一值**时，kappa 的期望一致率 `pe` 会追平观察一致率 `po`，
kappa 数学上归零（kappa 悖论）。这恰恰坐实了**宽窄两套口径并存**，必须统一口径后重标。

**逐标签 kappa（升序，越低越含糊）**：`user_content` 0.0、`tool_calls` 0.0、`agent_comms` 0.0、
`system_instruction` 0.0、`prompt_intent` 0.071、`exec_code` 0.189、`state_persist` 0.222、
`fs_access` 0.588、`cred_access` 0.602、`external_dep` 0.698、**`net_egress` 0.815（唯一达标）**。

**v2 判定式（本轮起强制，A/B 双方统一适用）**

| 标签 | v2 判定式 |
|---|---|
| `user_content` | 用户提供的**内容**（文本/文档/网页）被当成**加工原料** → yes；用户给的**请求/标识/查询词**被当参数**转发** → no。判据口诀：**"输入是被检索的键，还是被改写的料"** |
| `tool_calls` | 专指**结构化工具 / 函数调用**（MCP tool、function calling、`read_file`/`write_to_file`/`execute_command` 等具名工具）；与 `exec_code`（自由 shell / 脚本执行）拉开距离 |
| `prompt_intent` | 需存在**模板 + 占位符**并由外部输入填槽；把用户输入原样作为 API 参数传递 → no |
| `external_dep` | = **需要安装**第三方包 / SDK / 插件 / MCP server。远程 API 调用归入 `net_egress`，**不算** `external_dep` |
| `state_persist` | 写入**机器可读、且被技能在后续会话回读**的状态（token 缓存、版本缓存、断点续传标记、memory 文件、浏览器 profile）；一次性产出物 → no |
| `net_egress` | `curl localhost` / 本地回环 → no；`pip install` / `npm install` 归入 `external_dep`，不算主动外联 |
| `cred_access` | 主体是**技能自身运行时**读取凭证。**"教人在配置里填密钥"或"引导人扫码登录" → no**（边界裁定 6 扩展到凭证）：那是对**人**的动作 |
| `agent_comms` | 需出现 spawn / 子会话 / 多 agent 编排；单次调用一个 API 不算，与后端 Agent 的一次接口交互也不算 |
| `system_instruction` | 仅当明确指示**写入** AGENTS.md / system prompt / 长期记忆规则；写记忆文件本身另计 `state_persist` |
| `exec_code` | 技能**自身运行时**执行代码 / shell / 脚本；文档里让用户执行的安装配置命令 → no（边界裁定 6）。**"SKILL.md 未指示运行、且脚本非完成职责的必要条件" → no** |
| `fs_access` | 读写本机文件（含要求写 `/tmp`、读用户文件）；仅 `print` 到 stdout → no |

**v2 新增边界裁定**

6. **给人做的动作不算**（已扩展到凭证与安装）：文档里让用户执行 `openclaw mcp add`、让用户填 API key、
引导用户登录第三方站点 —— 都是对**人**的动作，技能自身运行时并未执行/读取 → 一律 `no`。
7. **可选能力不算**：能力仅在**可选项**中提供（如 `--persist` 写 `.env`，默认为 ephemeral）→ `no`。
8. **可选依赖不算**：依赖存在**回退路径**且技能声明"纯 X 实现"（如首选 `requests`、回退 CLI）→ `external_dep` = `no`。
9. **深层证据链仍然算**：证据需跨文件传递时（如 `palette.py` 硬编码域名 → `cover.py` 写 `@import` →
`render_cover.js` 真实拉取），**链条完整即 yes**，不得因"层级深"判 no。

**v3 补丁（2026-10-12 · 主样本 kappa=0.8063 后的剩余分歧裁定）**

主样本在 v2 下 kappa 升至 0.8063，但**该值已被污染**（A 重标时已知 B 的切分），只作过程指标。
剩余 16 项分歧的方向统计显示：**除 `prompt_intent` 双向对立外，9 项均为「A 严 B 宽」**——属系统性宽严差，可逐条裁定：

| # | 裁定 | 依据 |
|---|---|---|
| 10 | **产出物不算 `state_persist`**：报告 / 文档 / 生成物一律 no，除非 SKILL.md 明示"下次读取 / 继续 / 跨会话生效" | 分歧 3 项全为 A=no B=yes（deep-research / kdocs / lingxi） |
| 11 | **指导型技能不算 `exec_code`**：教人写代码、教模型实现、无 scripts 且未指示运行 → no。**只有"指示运行某脚本 / 命令"才 yes** | 分歧 2 项全为 A=no B=yes（deep-research / react-native-dev） |
| 12 | **`agent_comms` 需明示** spawn / 子会话 / 多 agent 编排；"并行检索""浏览器自动化""名字里带 agent"都不算 | 分歧 2 项全为 A=no B=yes（deep-research / smooth-browser） |
| 13 | **`external_dep` 需明示安装**（`npm install` / `pip install` / `requirements.txt` / 自动装 SDK）；"可能有运行时依赖"不算 | 分歧 2 项全为 A=no B=yes（kdocs / tencent-musician-skills） |
| 14 | **`user_content`：用户提供的文件 / 文档 / 网页被加工 → yes；用户的创作要求 / 指令文本 → no** | 分歧 2 项为 A=yes B=no（tencentcloud-cos 属前者 → yes；libtv 属后者 → no） |
| 15 | **`prompt_intent`：外部输入进入自然语言指令串（提示词 / 查询描述 / 生成描述）→ yes；进入结构化字段 / 参数（ID、字段名、枚举、表单字段）→ no** | 唯一**双向对立**标签（A=yes B=no 与 A=no B=yes 各 2 项），说明 v2 的"模板+占位符"判据双方解读相反，须换成"字符串性质"判据 |

> v3 只在 **held-out 留出集**上验证：主样本不再回头修改（继续改会持续放大污染）。
> 留出集 kappa ≥ 0.8 才算**真通过**；主样本 kappa 只回答"口径是否已统一"。

**v4（2026-10-12 · 留出集实测后修订）**

**关键实测：主样本 kappa 0.8063 vs 留出集 kappa 0.5565 —— 差值 ≈ 0.25 就是口径过拟合的量化证据。**
主样本的高分是"口径被讨论过"换来的，不是标签真的清楚。**留出集未达 0.8 → 真值整体未通过验收。**

留出集逐标签 kappa（客观型 vs 语义型泾渭分明）：

| 类型 | 标签 | 留出集 kappa |
|---|---|---|
| **客观型（可信）** | `exec_code` / `external_dep` / `net_egress` / `agent_comms` / `system_instruction` | **1.0** |
| **语义型（暂不可用）** | `user_content` 0.286；`fs_access` / `prompt_intent` / `tool_calls` 0.0；`state_persist` −0.154；`cred_access` −0.25 | ≤ 0.29 |

**结论：有代码事实可查的标签，人与人都判得一致；需要语义推断的标签，人自己也判不到一块儿。**
这与"证据分级"的判断同源——度量能力只覆盖 E1–E2 可客观判定的标签。

**v4 裁定（采纳 B 面建议 + 发起人裁决）**

| # | 裁定 | 来源 |
|---|---|---|
| 16 | **`cred_access`**：以"是否存在**明示读取动作**"为准。**明示"禁止读取"→ no**（如 baidu-drive 明令禁止读 `~/.config/bdpan`）；**"可选 / 默认避免"→ no**（裁定 7，如 agent-browser-core）。**不得**以"依赖的 CLI 会持有凭证"反推 yes | 留出集两起方向相反的分歧 |
| 17 | **`state_persist`**：主判据改为**"是否存在回读路径"**（代码里 `readFileSync` / `existsSync` / 加载 / "cached for N days"），**不问它叫不叫产出物** | 采纳 B 面建议（第 10 条难用的根因） |
| 18 | **`prompt_intent`**：**只看表面形态，不做语义还原**。仅当存在**字面模板 / 占位符**，或文档明确称作 prompt / 提示词 → yes；**回复模板 ≠ prompt** | 采纳 B 面建议（第 15 条缺口） |
| 19 | **`exec_code`**：判据改为**执行主体**。命令由**本技能自己**执行 → yes；交给**被编排 / 被生成的第三方**（builder、sub-agent、执行者）→ no | 采纳 B 面建议（第 11 条最难用） |
| 20 | **`user_content`**：内容被**读取 / 转换 / 生成**（转 PDF、总结、审核、改写）→ yes；仅**搬运**（上传 / 下载 / 移动 / 重命名 / 分享）→ no | 留出集 baidu-drive 分歧 |
| 21 | **`tool_calls`**：v3 的收窄口径**撤销**，恢复 B 面两轮一致口径（凡使用具名工具 → yes；纯文本生成 → no）。与 `exec_code` 的重叠问题**转交标签集重构阶段**处置，不在真值阶段解决——中途改口径会毁掉跨轮可比性 | 采纳 B 面第 ② 条诉求 |

**标签分级承认（当前生效）**：`exec_code` / `external_dep` / `net_egress` / `agent_comms` / `system_instruction`
**可用于度量**；其余 6 个**暂不可用于度量**，任何报告若引用其召回率 / 精确率，必须标注"判别力未达标（留出集 kappa < 0.8）"。

**第三轮（2026-10-12 终局）：假一致发现与收敛**

第三轮 10 个无偏样本总体 kappa = **0.6000**（110 判定对，22 项分歧），仍未达 0.8。
但**比总体值更重要的发现是：4 个标签的 kappa=1.0 是假一致**。

| 标签 | A 阳性 / B 阳性（第三轮） | kappa | 判读 |
|---|---|---|---|
| `exec_code` | 10 / 10 | 1.0 | **假一致**：双方全 yes，无判别信息 |
| `tool_calls` | 10 / 10 | 1.0 | **假一致**：同上 |
| `agent_comms` | 0 / 0 | 1.0 | **假一致**：双方全 no |
| `system_instruction` | 0 / 0 | 1.0 | **假一致**：同上 |
| `external_dep` | 3 / 6 | 0.444 | 可解释，**最高** |
| `net_egress` | 7 / 9 | 0.412 | 可解释 |
| `user_content` | 8 / 5 | 0.400 | 可解释 |
| `prompt_intent` | 2 / 2 | 0.375 | 可解释 |
| `cred_access` | 4 / 6 | 0.231 | 可解释 |
| `state_persist` | 3 / 5 | 0.200 | 可解释 |
| `fs_access` | 8 / 8 | −0.250 | 可解释，**负** |

**结论（比"未通过"更严格）**：剔除 4 个假一致标签后，**有判别信息的 7 个标签最高只有 0.444**。
本真值**不足以支撑任何标签的召回率 / 精确率度量**。

**根因不是标注态度**：B 面两轮共 264 个判定、`unsure` 为 0、每条都给出证据等级与位置；
分歧集中在需要**语义推断**的标签，而非有代码事实可查的标签。是**标签定义**的问题，不是人的问题。

**同时暴露抽样方法缺陷**：#1-c 曾要求"每标签阳性 ≥3 且阴性 ≥3"，但抽样脚本未实现该配额，
导致本轮 4 个标签全同值、kappa 不可解释。该配额须写入 `build_benchmark_set.py` 供后续扩样使用。

**收敛约定（已生效）**：不再修订规程、不再投入标注轮次。语义型标签的判别力问题
**转交标签集重构（#3）**处置，处置方向见改造方案「第三轮结论与设计约束」。

## 双人独立标注流程（硬性）

1. 两人**各自独立**标注同一批样本，**标注期间不得交流、不得看对方文件**；
2. 各自产出 `truth_a.json` / `truth_b.json`；
3. 跑 `python3 scripts/benchmark_agreement.py --a ... --b ...` 计算 Cohen's kappa；
4. **kappa ≥ 0.8 才承认该真值可用**；< 0.8 → 先对着分歧项修订**本规程**（不是改标注结果），再重新标注一轮；
5. 分歧全部裁定后合并为 `truth.json`，作为召回率 / 精确率的唯一对照基准。

> 为什么 kappa 不达标要改规程而不是改标注：改标注等于把分歧"抹平"，真值的一致性是假的，
> 后续召回率会被高估。规程不够清晰才是根因（这是 MUC/ACE 标注工程的通行做法）。
