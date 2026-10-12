# 标注者 B · 第三轮任务书（可直接粘贴给新会话）

> 第三轮只标 **10 个新技能**（前两轮的 24 个**不需要重标**）。
> 这 10 个是**第三轮无偏验收样本**：从未参与任何口径讨论，其 kappa 决定真值能否最终合并。

---

## 任务书正文（复制线以下）

你是**标注者 B**，第三轮任务：为一个"AI 技能攻击面标签"基准集补标 **10 个技能**。

### 背景（一句话）

前两轮 A/B 在 5 个留出集样本上只拿到 kappa 0.5565（未达 0.8），暴露出**语义型标签判别力不足**。据此已发布 **v4 裁定**（下方）。本轮 10 个样本用于检验 v4 是否真的解决了问题：**这 10 个的 kappa ≥ 0.8，真值才最终合并**。

### 独立性要求（硬性）

1. **禁止**读取 `truth_a.json`，禁止询问 A 面判定；
2. **禁止**读取 `scripts/surface_tagging.py` 的输出；
3. 只准**追加** 10 个条目到 `truth_b.json`，前 24 条一字不动；
4. 拿不准标 `unsure`，不要猜。

### 判定对象

判断**能力面**：这个技能**会不会做这件事**。不判断危不危险、不判断好不好。

### 证据等级（取最高）

| 等级 | 形态 |
|---|---|
| E1 代码事实 | `scripts/` 内真实调用（`subprocess.run(`、`requests.get(`、`os.environ[`） |
| E2 声明事实 | frontmatter / 清单声明（`allowed-tools`、`requirements.txt`） |
| E3 指令事实 | `SKILL.md` 明确要求执行 |
| E4 强暗示 | 描述中该能力是完成职责的必要条件 |

E1–E3 任一命中 → `yes`；只有 E4 且是职责必要条件 → `yes`，否则 `no`。

### 11 个标签口径（v2 判定式 + v4 裁定）

| 标签 | 判定式 |
|---|---|
| `exec_code` | **看执行主体**：命令由**本技能自己**执行 → yes；交给**被编排 / 被生成的第三方**（builder、sub-agent、执行者）→ no。教人写代码、教模型实现、无 scripts → no |
| `external_dep` | **需明示安装**（`npm install` / `pip install` / `requirements.txt` / `package.json` / 明示的环境依赖）。远程 API 调用归 `net_egress`，不算 |
| `fs_access` | 读写本机文件（含要求写 `/tmp`、读用户文件）；仅 `print` 到 stdout → no |
| `net_egress` | 主动向外发起网络请求。本地回环 → no；`pip/npm install` 取包归 `external_dep` |
| `cred_access` | **看是否有明示读取动作**。① 明示"禁止读取"→ **no**；② "可选 / 默认避免"→ **no**（裁定 7）；③ **不得**以"依赖的 CLI 会持有凭证"反推 yes |
| `state_persist` | 主判据 = **是否存在回读路径**（代码里 `readFileSync` / `existsSync` / 加载动作，或文档写"cached for N days" / "下次不传 session_id" / "继续编辑"）。**不问它叫不叫产出物** |
| `user_content` | 用户提供的**文件 / 文档 / 网页**被**读取 / 转换 / 生成**（转 PDF、总结、审核、改写）→ yes；仅**搬运**（上传 / 下载 / 移动 / 重命名 / 分享）→ no；用户的**创作要求 / 指令文本**→ no |
| `agent_comms` | 需**明示** spawn / 子会话 / 多 agent 编排。"并行检索""浏览器自动化""名字里带 agent""编排的是制作阶段"都不算 |
| `prompt_intent` | **只看表面形态，不做语义还原**。仅当存在**字面模板 / 占位符**，或文档明确称作 prompt / 提示词 → yes；**回复模板 ≠ prompt**；HTML placeholder 等结构化字段 → no |
| `tool_calls` | 凡使用**具名工具**（含 `execute_command` / Bash、具名 CLI 子命令、MCP tool、文件读写工具）→ yes；纯文本生成 → no |
| `system_instruction` | 仅当明确指示**写入** AGENTS.md / system prompt / 长期记忆规则；写记忆文件本身另计 `state_persist` |

### 边界裁定（沿用第 6–15 条 + 新增 16–21 条）

6. 给人做的动作不算（含让用户填 API key、引导用户登录、安装配置命令）。
7. 可选能力不算（如 `--persist` 写 `.env`，默认 ephemeral）。
8. 可选依赖不算（有回退路径且声明"纯 X 实现"）。
9. 深层证据链仍然算（跨文件传递，链条完整即 yes，不因"层级深"判 no）。
10. 产出物不算 `state_persist`（已被第 17 条"回读路径"主判据取代）。
11. 指导型技能不算 `exec_code`（已被第 19 条"执行主体"取代）。
12. `agent_comms` 需明示 spawn / 编排。
13. `external_dep` 需明示安装。
14. `user_content`：文件/文档/网页被加工 → yes；创作要求/指令文本 → no。
15. `prompt_intent`：自然语言指令串 → yes；结构化字段/参数 → no。
16. `cred_access` 看明示读取动作（见上表）。
17. `state_persist` 看回读路径（见上表）。
18. `prompt_intent` 只看表面形态（见上表）。
19. `exec_code` 看执行主体（见上表）。
20. `user_content` 搬运不算（见上表）。
21. `tool_calls` 采用宽口径（具名工具 → yes），与 `exec_code` 的重叠不在本轮处理。

通用规则：`references/` 与 `scripts/` 同等对待；`node_modules` / `.venv` / `venv` / `__pycache__` / `.trace` 内代码忽略；`tests/` / `examples/` / `docs/` 算。

### 待标注的 10 个技能

```
/Users/family/.codebuddy/skills-marketplace/skills/12306-train-assistant
/Users/family/.codebuddy/skills-marketplace/skills/academic-translation
/Users/family/.codebuddy/skills-marketplace/skills/conversion-ops
/Users/family/.codebuddy/skills-marketplace/skills/excalidraw-diagram
/Users/family/.codebuddy/skills-marketplace/skills/imsg
/Users/family/.codebuddy/skills-marketplace/skills/migraq
/Users/family/.codebuddy/skills-marketplace/skills/product-showcase-site
/Users/family/.codebuddy/skills-marketplace/skills/promo-creator-skills
/Users/family/.codebuddy/skills-marketplace/skills/tencent-survey
/Users/family/.codebuddy/skills-marketplace/skills/tencentcloud-ocr
```

**请勿就这些技能的判定与我们讨论**——它们是无偏验收样本。

### 查证步骤

1. 读 `SKILL.md`（frontmatter `description` + 全文）；
2. 若有 `scripts/`，抽查关键行：
   ```bash
   grep -nE "subprocess|os\.system|requests\.|urllib|httpx|fetch\(|http://|https://|open\(|os\.environ|getenv|token|api[_-]?key|readFileSync|existsSync|json\.dump|\.write\(|pip install|npm |requirements|spawn|send_message|profile|memory|placeholder" <skill>/scripts/* | head -20
   ```
3. 按等级判定，在 `note` 写**证据等级 + 位置**（如 `E1 scripts/x.py:L12`）。

### 产出

在 `truth_b.json` **追加** 10 个条目（前 24 条不动），路径：
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

10 × 11 = **110 个判定**，全部填满，不留 `null`。

### 完成后回报

① 已标注技能数 / 判定数；② `unsure` 项及原因；③ **v4 第 16–21 条中仍然最难用的是哪条**（第三轮之后不再修订规程，这条反馈会直接决定语义型标签的处置）。

**不要**汇报 yes 分布统计，**不要**读取 `truth_a.json`。
