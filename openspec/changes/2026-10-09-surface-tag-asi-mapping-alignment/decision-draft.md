# 领域决策草案：标签 → ASI 映射裁定

> **状态**：草案，**待裁定**后转入实施（承载变更 `2026-10-09-surface-tag-asi-mapping-alignment` 的待实施项 #1 / #2）。
> **证据基准（2026-10-09 实取）**：`scripts/surface_tagging.py` `_SURFACE_TAGS`（9 标签真实判定信号）、`scripts/_common.py` `TAG_TO_ASI`、`references/SafeTest/dimensions/Mapping-Matrix.md` 表 1（视角 → 主/次 ASI）与准入表。
> **裁定视角**：不迁就任一侧现状。两侧均有错误（见下方三列对照），故按语义重裁，而不是"选一边"。

## 一、裁定原则

1. **按中文类别语义归属**，不按编号、不迁就现状。
2. **逐概念裁决，再取并集**：一个标签常捆绑多个风险面（如 `fs_net_cred` = 文件系统 + 网络 + 凭证），标签级直接给一组 ASI 必然是妥协。
3. **中文 / 英文是同一概念的两种词形，不参与 ASI 归属判定**；词形归一是信号层问题（属在途 `2026-09-24` N1 / N2），不混进映射裁定。
4. **间接风险不重复计入**：ASI01（目标劫持）由**注入面**标签承担，不由执行手段标签（exec_code / tool_calls）承担——后者只提供"怎么执行"，不提供"目标被改写"。
5. **结果须同时满足**：① 每条映射能写出一句中文理由；② 10 个 ASI 均被至少一个标签映射（无孤儿）。

## 二、三列对照（代码 / 准入表派生 / 草案建议）

"准入表派生" = 准入表触发维度中的 ASI 与其触发视角在表 1 的**主 ASI** 之并集（即文档侧按自身规则推出的结果）。

| 标签 | 代码 `TAG_TO_ASI` | 准入表派生 | 草案建议 | 主要分歧 |
|---|---|---|---|---|
| `exec_code` | 01, 05 | 02, 05 | **05**(主), 02(次) | 代码侧 ASI01 无依据 |
| `external_dep` | 02, 08 | 04, 07 | **04**(主), 05(次), 08(次) | 两侧都不完整：代码缺 04、准入表多了 07 |
| `fs_net_cred` | 03, 07, 10 | 01, 03 | **03**(主), 10(次) | 代码侧 ASI07 属另一通信面 |
| `secret_memory` | 06, 09 | 03, 06, 07 | **06**(主), 03(次) | 代码侧 ASI09 属信任面 |
| `user_content` | 04, 07 | 09, 10 | **09**(主), 01(次) | 代码侧 04/07 与该标签无关 |
| `agent_comms` | 09, 10 | 04, 07, 10 | **07**(主), 10(次), 08(次) | **代码侧完全没有 ASI07——最明确的漏** |
| `tool_calls` | 01, 02, 03 | 01, 02, 03, 05 | **02**(主), 03(次), 05(次) | 准入表经 permission-boundary 带入 ASI01 |
| `prompt_intent` | 04, 07 | 01, 09, 10 | **01**(主), 09(次) | 代码侧 04/07 与提示注入无关 |
| `system_instruction` | 04, 10 | 01, 09, 10 | **01**(主), **10**(主), 09(次) | 代码侧 ASI04 供应链关联弱 |

## 三、逐标签裁定表（含概念拆分与中英词形归一）

### 1. `exec_code`

| 概念 | 中文词形（现状） | 英文词形（现状 / 建议补） |
|---|---|---|
| 命令执行 | — | `subprocess`、`os.system`、`shell`、`popen` |
| 动态求值 | — | `exec`、`eval` |
| 动态导入 / 反序列化 | 动态加载 | `__import__`、`importlib`、`pickle`（建议补 `marshal`、`dill`、反序列化 / deserialization） |

**建议 ASI**：`ASI05 非预期代码执行`（主）、`ASI02 工具滥用与利用`（次）。
**理由**：`eval` / `subprocess` / `pickle` 与 ASI05 字面同一；ASI02 因 shell / eval 常被作为被滥用工具的执行路径。
**删除**：代码侧 ASI01（描述的是执行能力，不含"目标被改写"语义）。

### 2. `external_dep`

| 概念 | 中文词形 | 英文词形 |
|---|---|---|
| 包安装 | — | `pip install`、`npm`、`yarn` |
| 依赖清单 | — | `requirements.txt`、`package.json` |
| 第三方导入 | `import ...第三方` | `importlib` |
| MCP / 插件注册 | 插件 | `MCP server`（建议补 `plugin`、`extension`、`plugin.json`） |

**建议 ASI**：`ASI04 Agentic 供应链漏洞`（主）、`ASI05`（次，恶意依赖导致代码执行）、`ASI08 级联失败`（次，第三方 / MCP 服务失效级联）。
**理由**：依赖与 MCP / 插件是 ASI04 的字面对象。
**删除**：代码侧 ASI02（工具滥用不属依赖面）、准入表侧 ASI07（MCP 描述符投毒的主风险已在 ASI04 覆盖）。

### 3. `fs_net_cred`

| 概念 | 中文词形 | 英文词形 |
|---|---|---|
| 文件系统访问 | — | `open(`、`os.remove` |
| 网络出网 | — | `requests.`、`urllib`、`httpx`、`fetch` |
| 凭证读取 | 令牌、`读 env` | `token`、`getenv`、`os.environ`、`~/.ssh`、`~/.aws`（**建议补** `credential`、`secret`、`api_key`、`apikey`、`password`、`私钥`、`AK/SK`） |

**建议 ASI**：`ASI03 身份与权限滥用`（主）、`ASI10 流氓 Agent`（次，越权出网 / 数据外传）。
**删除**：代码侧 ASI07（Agent 间通信是同类不同面）、准入表侧 ASI01（该面不直接产生目标改写）。
**注明**：凭证类缺少 `credential` / `secret` / `api_key` 是已登记的完备性缺口，与 O-7 / N1 同源；词形归一在 N1 落地，本变更不动信号词表。

### 4. `secret_memory`

| 概念 | 中文词形 | 英文词形 |
|---|---|---|
| 日志与打印 | 写日志、`print...密钥` | （建议补 `logging`、`log write`、`stdout`） |
| 上下文持久化 | 持久化、`memory` | （建议补 `persist`、`persistence`、`state.json`、`MEMORY.md`） |
| 跨进程 / 共享 | 跨进程、管道 | （建议补 `IPC`、`shared memory`、`mmap`、`queue`） |

**建议 ASI**：`ASI06 内存与上下文投毒`（主）、`ASI03`（次，日志 / 缓存中常含凭证）。
**删除**：代码侧 ASI09（信任利用 ≠ 内存泄露）。
**精度问题（建议一并处理）**：现有信号 `.json` / `.md` 几乎必命中任何技能，是误报源，建议收窄为 `memory` / `MEMORY.md` / `context.json` / `state.json` / `persist`。

### 5. `user_content`

| 概念 | 中文词形 | 英文词形 |
|---|---|---|
| 读取用户对话 / 输入 | 读取用户对话、用户输入 | （**建议补** `user input`、`user message`、`user query`、`conversation`） |
| 模板渲染 | 模板渲染 | （**建议补** `template render`、`jinja`、`render`、`format string`） |
| 遵循指令处理 | `遵循 ... instructions` | `instructions` |

**建议 ASI**：`ASI09 人-Agent 信任利用`（主）、`ASI01`（次，用户内容是间接提示注入的载体）。
**删除**：代码侧 ASI04 / ASI07（供应链与 Agent 间通信与该标签无关）。
**中英风险**：该标签信号**几乎全为中文**，纯英文技能很可能漏打标——这是覆盖面缺口（实测最高仅 7/10）的成因之一，词形归一应优先做此标签。

### 6. `agent_comms`

| 概念 | 中文词形 | 英文词形 |
|---|---|---|
| 派生子 Agent | `多 agent` | `spawn ... agent`、`subagent`、`sub-agent` |
| Agent 间消息 | — | `send_message`、`mailbox`（建议补 `message queue`、`a2a`、`topic`） |
| 编排 | 编排 | （建议补 `orchestrate`、`orchestration`、`dispatch`、`workflow`） |

**建议 ASI**：`ASI07 不安全的 Agent 间通信`（主）、`ASI10 流氓 Agent`（次，派生子 agent 失控）、`ASI08 级联失败`（次，多 agent 编排中的失败扩散）。
**关键修复**：标签名就是 inter-agent communication，**代码侧却完全没有 ASI07**，这是本组最明确的漏。
**补齐 ASI08**：准入表触发维度的 ASI 并集缺 ASI08（级联失败），本标签与 `external_dep` 共同补上。

### 7. `tool_calls`

| 概念 | 中文词形 | 英文词形 |
|---|---|---|
| 文件类工具 | — | `read_file`、`write_to_file` |
| 命令类工具 | — | `execute_command` |
| 网络类工具 | — | `web_fetch` |
| 工具 / 函数协议 | 工具调用 | `function calling`、`MCP tool`、`Skills`（建议补 `tool_call`、`tools[]`） |

**建议 ASI**：`ASI02 工具滥用与利用`（主）、`ASI03`（次，工具越权调用）、`ASI05`（次，`execute_command` 类工具导致非预期代码执行）。
**删除**：准入表经 `permission-boundary` 带入的 ASI01——按原则 4，目标劫持应由注入面标签承担。
**精度问题**：信号 `search` 过宽泛，建议移除或收窄为具体工具名白名单。

### 8. `prompt_intent`

| 概念 | 中文词形 | 英文词形 |
|---|---|---|
| 可被改写的提示结构 | 可被...改写 | （建议补 `override`、`overwrite`、`injectable`、`mutable prompt`） |
| 占位与拼接 | 占位、条件分支、指令式 | （建议补 `placeholder`、`{{ }}`、`{ }`、`template injection`、`conditional`、`imperative`） |
| 外部输入进入提示 | 用户输入的引用、外部输入 | （建议补 `external input`、`user-supplied`、`untrusted input`） |

**建议 ASI**：`ASI01 Agent 目标劫持`（主，提示注入的直接对应，与决策记录 1 已确认的裁定一致）、`ASI09`（次，social-engineering 路径）。
**删除**：代码侧 ASI04 / ASI07。
**中英风险**：信号全为中文，同 `user_content`，英文技能易漏。

### 9. `system_instruction`

| 概念 | 中文词形 | 英文词形 |
|---|---|---|
| 系统提示注入 | 忽略先前指令、注入...system、隐藏规则 | `system prompt`（建议补 `ignore previous instructions`、`system message`、`hidden instruction`） |
| 安全策略被覆盖 | 覆盖安全策略 | （建议补 `policy override`、`safety bypass`、`guardrail bypass`、`jailbreak`） |
| 指令篡改 | 修改...指令 | （建议补 `instruction tampering`、`prompt rewrite`、`prompt injection`） |

**建议 ASI**：`ASI01`（主，目标被劫持）、`ASI10 流氓 Agent`（主，安全基线被篡改后行为失控）、`ASI09`（次）。
**删除**：代码侧 ASI04（供应链关联弱，与原登记判断一致）。

## 四、覆盖矩阵（验证无孤儿 ASI）

| ASI | 由哪些标签触发（草案） |
|---|---|
| ASI01 | `prompt_intent`(主)、`system_instruction`(主)、`user_content`(次) |
| ASI02 | `tool_calls`(主)、`exec_code`(次) |
| ASI03 | `fs_net_cred`(主)、`secret_memory`(次)、`tool_calls`(次) |
| ASI04 | `external_dep`(主) |
| ASI05 | `exec_code`(主)、`external_dep`(次)、`tool_calls`(次) |
| ASI06 | `secret_memory`(主) |
| ASI07 | `agent_comms`(主) |
| ASI08 | `external_dep`(次)、`agent_comms`(次) ← **补齐原有缺口** |
| ASI09 | `user_content`(主)、`prompt_intent`(次)、`system_instruction`(次) |
| ASI10 | `system_instruction`(主)、`fs_net_cred`(次)、`agent_comms`(次) |

**10 / 10 全部有归属**，ASI08 由缺位变为有触发。

## 五、中文 / 英文语义匹配专项

现状三类问题（均在信号层，不属本映射变更的改动范围，但决定裁定的可执行性）：

| 类型 | 表现 | 涉及标签 |
|---|---|---|
| **纯中文信号** | 英文技能可能完全漏打标 | `user_content`、`prompt_intent`、`system_instruction`（几乎全中文） |
| **一词一形** | 同一概念只登记了一种语言的词 | `fs_net_cred` 凭证类只有 `token` / 令牌，缺 `credential` / `secret` / `api_key` |
| **过宽 / 多义信号** | 几乎必命中，产生误报 | `secret_memory` 的 `.json` / `.md`；`tool_calls` 的 `search` |

**建议形态（与在途 N1 / N2 同构）**：信号改为「概念 → 中英词形表」，ASI 归属挂**概念**而非标签：

```
概念「凭证读取」: {zh: [令牌, 凭证, 密钥, 私钥], en: [token, credential, secret, api_key, apikey, password, AK/SK]}
概念「凭证读取」→ ASI03
```

依赖说明：词形字典落地在 `2026-09-24` 的 N1 / N2；本变更只裁定并统一**映射值**，两者顺序上互不阻塞，但**概念字典落地后映射应迁移到概念级**（标签级映射是过渡形态）。

## 六、预期影响与回归对照

- **探测集合会变（属预期，非回归失败）**：命中同样 3 个标签的 v16 场景，按草案的并集为 `{ASI01, ASI03, ASI06, ASI09, ASI10}` = **5 个 ASI**（现为 6 个：`03,04,06,07,09,10`）。减少的是 `ASI04`（供应链）与 `ASI07`（Agent 间通信）——对一个数据库元数据查询技能而言这两项本不该由这三个标签触发，故这是语义修正。
- **`MIN_ASI_COVERAGE = 9` 仍会告警**（5 < 9）：覆盖面下限问题由 O-2 / N5 / N9 承载，不因本变更解决。
- **守卫 E28 / E29 不受影响**：二者依赖 `primary_asi_category` 与 `security_group` 推导，与本映射正交。
- **验收对照建议**：改动前后各跑一次同技能打标，记录 `skill_surface_tags` 集合、去重后 ASI 集合、生成探测数三项，作为是否引入意外的判据。
