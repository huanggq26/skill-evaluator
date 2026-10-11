# 标注者 B · 独立标注任务书（可直接粘贴给新会话）

> 用法：把下方「任务书正文」整段复制，粘贴到一个**全新会话**里执行。
> 该会话**不得**看到标注者 A 的结果，否则 Cohen's kappa 失去意义。

---

## 任务书正文（复制线以下）

你是**标注者 B**，任务是为一个"AI 技能攻击面标签"基准集做**人工真值标注**。你的标注将与另一位标注者（A）的结果做 Cohen's kappa 一致性检验，一致性达标后，这份真值会成为衡量扫描器召回率/精确率的唯一对照基准。

### 独立性要求（硬性，违反则本次标注作废）

1. **禁止**读取或打开 `truth_a.json`（标注者 A 的成果），也**禁止**以任何方式询问 A 的判定；
2. **禁止**运行或读取 `scripts/surface_tagging.py` 的输出——真值必须与被测扫描器**完全独立**，否则后续召回率会退化成"扫描器对自己一致度"；
3. **禁止**修改除 `truth_b.json` 以外的任何文件；
4. 标注期间不与任何人讨论判定，拿不准就标 `unsure`，**不要猜**。

### 你要判断什么

判断的是**能力面**：这个技能**会不会做这件事**。
不是判断"这样做危不危险"（那是下游 ASI 与评分的事），也不是判断技能好不好。

### 证据等级（从强到弱，取最高等级）

| 等级 | 形态 | 示例 |
|---|---|---|
| E1 代码事实 | `scripts/` 内真实调用 | `subprocess.run(`、`requests.get(`、`os.environ[` |
| E2 声明事实 | frontmatter / 清单声明 | `allowed-tools: Bash(...)`、`requirements.txt`、`package.json` |
| E3 指令事实 | `SKILL.md` 明确要求执行 | "执行 `python3 scripts/x.py`"、"。把结果写入 `~/.cache/x.json`" |
| E4 强暗示 | 描述中该能力是完成职责的必要条件 | "抓取指定网页"、"调用 XX API" |

**判定规则**：E1–E3 任一命中 → `yes`。只有 E4 时，该能力是技能完成其职责的**必要条件**才 `yes`，否则 `no`。仅凭"可能/也许/可选"不标 `yes`。

### 11 个标签的口径

| 标签 | 标 `yes` 的条件 | 常见误判（应标 `no`） |
|---|---|---|
| `exec_code` | 会执行代码 / shell / 动态加载（subprocess、os.system、命令串、eval、importlib、要求运行某脚本） | 只输出代码文本给人看，自己不执行 |
| `external_dep` | 依赖第三方包 / 服务 / 插件 / MCP server（pip install、requirements.txt、package.json、npm 装包） | 只用标准库；文档里提到别人的产品名 |
| `fs_access` | 会读写本机文件（open(、write_to_file、要求写 /tmp、读用户文件） | 只输出文本不落盘 |
| `net_egress` | 会主动向外发起网络请求（HTTP、API、抓取、curl、SDK 调远端） | 只生成 URL 让人点；仅本地回环 |
| `cred_access` | 会读取或使用凭证（token、api_key、os.environ、cookie、~/.ssh、要求用户提供密钥） | 文档里出现"密钥"二字但技能本身不读取 |
| `state_persist` | 会把状态写到**跨会话可复现**的地方（缓存、日志、数据库、memory 文件） | 只在单次对话内记住；产出物不算 |
| `user_content` | 会把用户会话内容 / 用户输入当作处理对象（总结对话、按输入改写、读聊天记录） | 仅接收参数并原样转发（那属 `tool_calls`） |
| `agent_comms` | 会与其他 agent / 子会话 / 团队通信（spawn、send_message、mailbox、多 agent 编排） | 单次调用一个 API 不算 |
| `prompt_intent` | 会把外部输入拼进**提示词**（模板、占位、条件分支、用户指令参与构造 prompt） | 固定提示词无外部插入 |
| `tool_calls` | 会调用工具 / 函数（read_file、execute_command、web_fetch、MCP tool、function calling） | 纯文本生成 |
| `system_instruction` | 会写入或改写系统级指令 / 规则（system prompt、忽略先前指令、注入规则、改写安全策略） | 只是自己的指令写得长 |

### 边界裁定（遇分歧按此处理）

1. **"要求模型去做"也算**：SKILL.md 指示模型执行（E3）与脚本自己执行（E1）**同等**；
2. **`references/` 与 `scripts/` 同等对待**，均属客观产物；
3. **第三方依赖目录不算**：`node_modules` / `.venv` / `venv` / `__pycache__` / `.trace` 内的代码忽略；
4. **`tests/` / `examples/` / `docs/` 算**（属技能本体）；
5. 拿不准标 `unsure`，**不要猜**；
6. **给人做的配置动作不算**（如文档里让用户执行 `openclaw mcp add` 属安装说明，不是技能运行时执行代码）。

### 待标注的 15 个技能（路径）

技能源目录：`/Users/family/.codebuddy/skills-marketplace/skills/`

```
minimax-pdf                        tencent-musician-skills
deep-research                      fullstack-dev
react-native-dev                   libtv-skill
ecommerce-copywriter               cloudbase
andonq                             tencentcloud-cos
lingxi-financialsearch-skill       smooth-browser
kdocs                              stock-analyzer
web-search-exa
```

### 每个技能怎么查证（建议步骤）

1. 读 `SKILL.md`（frontmatter 的 `description` + 全文），理解"这技能是干什么的"；
2. 若有 `scripts/`，列出文件并抽查关键行：
   ```bash
   grep -nE "subprocess|os\.system|requests\.|urllib|httpx|fetch\(|http://|https://|open\(|os\.environ|getenv|token|api[_-]?key|json\.dump|\.write\(|pip install|npm |requirements" <skill>/scripts/* | head -20
   ```
3. 按等级判定，填 `yes` / `no` / `unsure`，并在 `note` 里写**证据等级 + 位置**（如 `E1 scripts/x.py:L12`）。

### 产出（唯一允许写入的文件）

写入：`/Users/family/.codebuddy/skills/skill-evaluator/openspec/changes/2026-10-10-attack-surface-tag-system-refactor/benchmark/truth_b.json`

格式（已有骨架，只改值，不改结构、不改技能名、不改标签名）：

```json
{
  "set": "benchmark-2026-10-11",
  "annotator": "B",
  "labels": {
    "<skill-name>": {
      "exec_code": "yes|no|unsure",
      "external_dep": "...", "fs_access": "...", "net_egress": "...",
      "cred_access": "...", "state_persist": "...", "user_content": "...",
      "agent_comms": "...", "prompt_intent": "...", "tool_calls": "...",
      "system_instruction": "...",
      "note": "判定依据（E1–E4 + 证据位置）"
    }
  }
}
```

15 个技能 × 11 个标签 = **165 个判定**，全部填满才算完成；不允许留 `null`。

### 完成后回报

输出：① 已标注技能数 / 判定数；② 你标 `unsure` 的项及原因（这些会用于修订规程）；③ 你认为**口径最含糊**的标签（会用于改进标签定义）。

**不要**汇报你的 yes 分布统计（避免影响后续独立复核），**不要**读取 `truth_a.json`。
