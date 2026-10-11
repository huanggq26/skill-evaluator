# 标注者 B · 第二轮任务书（可直接粘贴给新会话）

> 用法：把「任务书正文」整段复制到**全新会话**执行。
> 第二轮只包含 **9 个新技能**（4 个补样 + 5 个留出集），第一轮的 15 个主样本**不需要重标**。
> 其中 **留出集 5 个是无偏验收对象**：它们从未参与任何口径讨论，其 kappa 才是真通过的判据。

---

## 任务书正文（复制线以下）

你是**标注者 B**，第二轮任务：为一个"AI 技能攻击面标签"基准集补标 **9 个技能**。这 9 个技能中，有 5 个是**留出集**——它们从未参与过任何口径讨论，A/B 在这一批上的一致性即**无偏判别力**，达标线 Cohen's kappa ≥ 0.8。

### 独立性要求（硬性）

1. **禁止**读取 `truth_a.json`（A 面成果），禁止询问 A 的判定；
2. **禁止**读取 `scripts/surface_tagging.py` 的输出；
3. 只准修改 `truth_b.json`（**追加** 9 个技能条目，不要动已有的 15 个）；
4. 拿不准标 `unsure`，不要猜。

### 判定对象

判断**能力面**：这个技能**会不会做这件事**。不判断危不危险，不判断好不好。

### 证据等级（取最高）

| 等级 | 形态 | 示例 |
|---|---|---|
| E1 代码事实 | `scripts/` 内真实调用 | `subprocess.run(`、`requests.get(`、`os.environ[` |
| E2 声明事实 | frontmatter / 清单声明 | `allowed-tools`、`requirements.txt`、`package.json` |
| E3 指令事实 | `SKILL.md` 明确要求执行 | "执行 `python3 scripts/x.py`" |
| E4 强暗示 | 描述中该能力是完成职责的必要条件 | "抓取指定网页" |

E1–E3 任一命中 → `yes`；只有 E4 且是职责必要条件 → `yes`，否则 `no`。

### 11 个标签口径（v2 判定式）

| 标签 | 判定式 |
|---|---|
| `exec_code` | 技能**自身运行时**执行代码 / shell / 脚本。**只有"指示运行某脚本/命令"才 yes**；教人写代码、教模型实现、无 scripts → no |
| `external_dep` | **需要安装**第三方包 / SDK / 插件 / MCP server（明示 `npm install` / `pip install` / `requirements.txt`）。远程 API 调用归 `net_egress`，不算 |
| `fs_access` | 读写本机文件（含要求写 `/tmp`、读用户文件）；仅 `print` 到 stdout → no |
| `net_egress` | 主动向外发起网络请求。本地回环 → no；`pip/npm install` 归 `external_dep` |
| `cred_access` | **技能自身运行时**读取凭证。教人在配置里填密钥、引导人扫码登录 → no |
| `state_persist` | 写入**机器可读、且被技能在后续会话回读**的状态。**产出物（报告/文档/生成物）不算**，除非明示"下次读取/继续/跨会话生效" |
| `user_content` | 用户提供的**文件/文档/网页**被当**加工原料** → yes；用户的**创作要求/指令文本** → no |
| `agent_comms` | 需**明示** spawn / 子会话 / 多 agent 编排。"并行检索""浏览器自动化""名字里带 agent"都不算 |
| `prompt_intent` | 外部输入进入**自然语言指令串**（提示词 / 查询描述 / 生成描述）→ yes；进入**结构化字段/参数**（ID、字段名、枚举、表单字段）→ no |
| `tool_calls` | 专指**结构化工具 / 函数调用**（MCP tool、function calling、`read_file`/`write_to_file` 等具名工具）；纯文本生成 → no |
| `system_instruction` | 仅当明确指示**写入** AGENTS.md / system prompt / 长期记忆规则；写记忆文件本身另计 `state_persist` |

### 边界裁定（v2 第 6–9 条 + v3 第 10–15 条）

6. **给人做的动作不算**（含凭证与安装）：让用户执行 `openclaw mcp add`、让用户填 API key、引导用户登录第三方站点 → 一律 no。
7. **可选能力不算**：能力仅在可选项中提供（如 `--persist` 写 `.env`，默认 ephemeral）→ no。
8. **可选依赖不算**：依赖有回退路径且声明"纯 X 实现"→ `external_dep` no。
9. **深层证据链仍然算**：证据跨文件传递（如 A 文件硬编码域名 → B 文件写 `@import` → C 文件真实拉取），链条完整即 yes，不得因"层级深"判 no。
10. 产出物不算 `state_persist`。
11. 指导型技能（教人/教模型写代码）不算 `exec_code`。
12. `agent_comms` 需明示 spawn / 编排。
13. `external_dep` 需明示安装。
14. `user_content`：文件/文档/网页被加工 → yes；创作要求/指令文本 → no。
15. `prompt_intent`：自然语言指令串 → yes；结构化字段/参数 → no。

另有两条通用规则：`references/` 与 `scripts/` 同等对待；`node_modules` / `.venv` / `venv` / `__pycache__` / `.trace` 内的代码忽略；`tests/` / `examples/` / `docs/` 算。

### 待标注的 9 个技能

**补样 4 个**（用于修复首轮 `agent_comms` 零阳性）：

```
/Users/family/.codebuddy/skills-marketplace/skills/agent-team-orchestration
/Users/family/.codebuddy/skills-marketplace/skills/content-factory
/Users/family/.codebuddy/skills-marketplace/skills/capability-evolver
/Users/family/.codebuddy/skills/leader
```

**留出集 5 个**（无偏验收对象，请勿与我们讨论这些技能的判定）：

```
/Users/family/.codebuddy/skills-marketplace/skills/12306
/Users/family/.codebuddy/skills-marketplace/skills/academic-tutor
/Users/family/.codebuddy/skills-marketplace/skills/agent-browser-core
/Users/family/.codebuddy/skills-marketplace/skills/agent-mbti
/Users/family/.codebuddy/skills-marketplace/skills/baidu-drive
```

### 查证步骤

1. 读 `SKILL.md`（frontmatter `description` + 全文）；
2. 若有 `scripts/`，抽查关键行：
   ```bash
   grep -nE "subprocess|os\.system|requests\.|urllib|httpx|fetch\(|http://|https://|open\(|os\.environ|getenv|token|api[_-]?key|json\.dump|\.write\(|pip install|npm |requirements|spawn|send_message|profile|memory" <skill>/scripts/* | head -20
   ```
3. 按等级判定，在 `note` 写**证据等级 + 位置**（如 `E1 scripts/x.py:L12`）。

### 产出

在 `truth_b.json` **追加** 9 个条目（已有的 15 个保持不动），路径：
`/Users/family/.codebuddy/skills/skill-evaluator/openspec/changes/2026-10-10-attack-surface-tag-system-refactor/benchmark/truth_b.json`

```json
"<skill-name>": {
  "exec_code": "yes|no|unsure", "external_dep": "...", "fs_access": "...",
  "net_egress": "...", "cred_access": "...", "state_persist": "...",
  "user_content": "...", "agent_comms": "...", "prompt_intent": "...",
  "tool_calls": "...", "system_instruction": "...",
  "note": "判定依据（E1–E4 + 证据位置）"
}
```

9 × 11 = **99 个判定**，全部填满，不留 `null`。

### 完成后回报

① 已标注技能数 / 判定数；② `unsure` 项及原因；③ **你认为 v3 里仍然含糊的裁定编号**（10–15 中哪条最难用）。

**不要**汇报你的 yes 分布统计，**不要**读取 `truth_a.json`。
