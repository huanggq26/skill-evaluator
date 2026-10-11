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

## 双人独立标注流程（硬性）

1. 两人**各自独立**标注同一批样本，**标注期间不得交流、不得看对方文件**；
2. 各自产出 `truth_a.json` / `truth_b.json`；
3. 跑 `python3 scripts/benchmark_agreement.py --a ... --b ...` 计算 Cohen's kappa；
4. **kappa ≥ 0.8 才承认该真值可用**；< 0.8 → 先对着分歧项修订**本规程**（不是改标注结果），再重新标注一轮；
5. 分歧全部裁定后合并为 `truth.json`，作为召回率 / 精确率的唯一对照基准。

> 为什么 kappa 不达标要改规程而不是改标注：改标注等于把分歧"抹平"，真值的一致性是假的，
> 后续召回率会被高估。规程不够清晰才是根因（这是 MUC/ACE 标注工程的通行做法）。
