# 标注者 B · 攻击面标签真值标注回报

- **set**：`benchmark-2026-10-11`
- **标注者**：B
- **产出文件**：`~/Library/../.codebuddy/skills/skill-evaluator/openspec/changes/2026-10-10-attack-surface-tag-system-refactor/benchmark/truth_b.json`
- **独立性声明**：本次标注全程未读取 `truth_a.json`，未运行或读取 `scripts/surface_tagging.py` 的输出，除 `truth_b.json` 外未修改任何文件。

---

## ① 完成度

| 项 | 数值 |
|---|---|
| 已标注技能数 | **15 / 15** |
| 判定数 | **165 / 165**（15 × 11） |
| `null` 残留 | 0 |
| 非法值 | 0 |
| `unsure` | 0 |

结构未改动：`set` / `annotator` / 技能名 / 11 个标签名 / `note` 字段均保持骨架原样，只填值。

---

## ② `unsure` 项

**0 个** —— 全部 165 项均落到 `yes` / `no`。

但以下 7 项是我在边界上做了**显式裁决**的存疑点，建议一并纳入规程修订——它们最可能造成 A/B 分歧：

| 技能 · 标签 | 裁决 | 裁决依据 |
|---|---|---|
| `ecommerce-copywriter` · `exec_code` | **no** | 虽有 `scripts/generate_title.py`，但 SKILL.md 全篇（L1–L161）无"运行该脚本"指示；脚本纯标准库、无 subprocess/网络/写文件；按 E4 判据，执行它并非完成职责的必要条件（标题公式与模板已在正文给出，模型可直接生成）。**风险最高的一条** |
| `web-search-exa` · `exec_code` | **no** | 仅 `openclaw mcp add exa --url ...` 一条命令，属边界裁定 6「给人做的配置动作」 |
| `web-search-exa` · `cred_access` | **no** | API key 拼进 MCP URL 属给人做的安装配置；技能运行时不读取凭证 |
| `tencentcloud-cos` · `state_persist` | **no** | `--persist` 写 `.env` 是**可选项**，默认/推荐为 ephemeral 不落盘 → 按「仅凭可能/可选不标 yes」 |
| `andonq` · `external_dep` | **no** | `check_env.py:125` 确有 `import requests`，但属 L1 首选且有 L2 `clawhub` CLI 回退，SKILL.md 声明"纯 Python 实现" → 判为可选依赖 |
| `stock-analyzer` · `cred_access` | **no** | "引导用户登录东方财富"是给**人**做的动作（边界裁定 6），技能本身不读取任何密钥 |
| `minimax-pdf` · `net_egress` | **yes** | `palette.py` 硬编码 `fonts.googleapis.com` → `cover.py:23` 写入 `@import` → `render_cover.js` 用真实 Chromium 渲染并实际拉取。E1 证据链完整，但层级较深，易被误判 no |

---

## ③ 口径最含糊的标签

### 第一名：`user_content`

定义里「用户输入当作处理对象」与「仅接收参数并原样转发」之间**没有判据**。

我实际使用的切分（规程里没写，是我自己补的）：

> 用户提供的**内容**（文本 / 文档 / 网页）被当成**加工原料** → `yes`
> 用户给的**请求 / 标识 / 查询词**被当参数**转发** → `no`

典型难例：`stock-analyzer`（股票名 → 分析报告）、`deep-research`（topic → outline）到底算不算"按输入改写"，判定过程中反复摇摆。

**建议补充判定式**：*"输入是被检索/查询的**键**，还是被改写的**料**"*。

---

### 第二名：`cred_access`

"文档里出现密钥但技能本身不读取"这句话，遇到下面两类都不好套：

1. **文档教人在配置里填密钥**（`web-search-exa` 的 `exaApiKey=YOUR_EXA_KEY`）
2. **文档教人扫码/登录**（`stock-analyzer` 引导登录东财）

此外"代码里出现 `process.env` / `os.environ`"是否算（`fullstack-dev` 通篇都是）完全没有边界说明。

**建议补充**：明确 `cred_access` 的主体是"技能自身运行时"还是"包含技能生成的代码"；并界定"人机混合登录流程"如何归类。

---

### 第三名：`tool_calls`

定义把 `execute_command` 列为示例，导致它与 `exec_code` **高度重叠**——凡能跑 shell 的必然 `yes`，区分度很低。当前实际效果：只有"纯文本生成"类技能会判 `no`。

**建议**：明确 `tool_calls` 是否专指"结构化工具 / 函数调用（MCP tool、function calling）"，从而与 `exec_code`（自由 shell / 脚本执行）拉开距离。

---

## 附：我实际使用的统一判定口径（供规程修订参考）

为保证 165 项内部自洽，我对几个高频歧义点固定了口径：

| 标签 | 采用的判定口径 |
|---|---|
| `external_dep` | = **需要安装**第三方包 / SDK / 插件 / MCP server。远程 API 调用归入 `net_egress`，不算 `external_dep`（否则该标签将恒为 yes） |
| `net_egress` | `curl localhost` / 本地回环 → `no`；`pip install` / `npm install` 归入 `external_dep`，不算主动外联 |
| `state_persist` | = 写入**机器可读、且被技能在后续会话回读**的状态（token 缓存、版本缓存、断点续传标记、memory 文件、浏览器 profile）；一次性产出物不算 |
| `agent_comms` | 需出现 spawn / 子会话 / 多 agent 编排；"单次调用一个 API"不算，与后端 Agent 的一次接口交互也不算 |
| `prompt_intent` | 需存在**模板 + 占位符**并由外部输入填槽；把用户输入原样作为 API 参数传递不算 |
| `system_instruction` | 仅当明确指示写入 AGENTS.md / system prompt / long-term memory 规则；写记忆文件本身另计 `state_persist` |
