# 标注者 B · 第四轮任务书（可直接粘贴给新会话）

> 第四轮标 **14 个全新技能 × 8 个标签 = 112 个判定**。
> 与前三轮的关键差别：**口径换成 E1–E2 事实判定**（v5），不再做语义推断；打标集由 11 个标签**缩减为 8 个**。
> 这 14 个是**最终无偏验收样本**：其 kappa ≥ 0.8 才合并 `truth.json`。

---

## 任务书正文（复制线以下）

你是**标注者 B**，第四轮任务：为一个"AI 技能攻击面标签"基准集标注 **14 个技能 × 8 个标签**。

### 背景（一句话）

前三轮 kappa 依次是 0.4944 → 0.8063（但被口径污染）→ 0.5565 → 0.6000，且第三轮发现有 4 个标签**双方恒同值**（kappa=1.0 却是假一致）。根因判定为**标签定义依赖语义推断**，不是标注态度（你前面两轮 264 个判定 `unsure`=0 且条条带证据）。因此本轮换判据形态：把「这个技能有没有这个能力」换成「本体的文件里有没有这个事实」。

### 独立性要求（硬性）

1. **禁止**读取 `truth_a.json`、`truth_a_round4.json`，禁止询问 A 面判定；
2. **禁止**读取 `scripts/surface_tagging.py` 的输出；
3. 产出写入**新文件** `truth_b_round4.json`（不要改 `truth_b.json`，那是 v4 口径）；
4. **不再使用 `unsure`**——判据是事实判定，查不到即是没有该事实，判 no。

### 判定对象与打标集（8 个标签）

| 处置 | 标签 |
|---|---|
| **本轮打标** | `exec_code` `external_dep` `fs_access` `net_egress` `cred_access` `state_persist` `agent_comms` `system_instruction` |
| **不再打标**（已转 `evidence_level`） | `user_content` `prompt_intent` |
| **已剔除**（恒真） | `tool_calls` |

若看到 `user_content` / `prompt_intent` 的信号，写进 `note` 即可，**不占判定格**。

### 唯一判据：只认 E1 / E2

- **E1 代码事实**：技能本体（`SKILL.md` + `scripts/` 下 `.py` `.sh` `.js` `.ts` `.json` `.md`）中**存在**该能力的代码/命令事实，可给出 `文件:行号`。
- **E2 声明事实**：依赖/配置声明（`requirements.txt` / `package.json` / `pyproject.toml` / frontmatter 的 `primaryEnv` / `permissions` / `requires` / MCP server 声明），可给出 `文件:行号`。
- **E3 / E4 不触发标签**：`SKILL.md` 的**指令、说明、示例讲解、给用户的步骤散文**属 E3，强隐含属 E4，**一律判 no**，只在 `note` 记等级与位置。

#### E1 / E2 / E3 的机械判据（不留推断空间）

无 `scripts/` 的技能占多数，若把 `SKILL.md` 一律当散文，这类技能会**全标签判 no**——那正是第三轮假一致的成因。故按下表切分：

| 等级 | 形态 | 判定方法（机械） |
|---|---|---|
| **E1** | ① `scripts/` 下的代码文件；② `SKILL.md` 中 **fenced 代码块**（``` 包裹）或**行内 `` ` `` 代码**内出现的**实际命令 / 代码语句** | 该行是否位于 ``` fence 之内，或被反引号包裹 |
| **E2** | frontmatter 声名字段与依赖清单文件；安装命令（`pip install` / `npm install`）即使写在代码块里仍按 E2 计 | 是否属声明/清单而非执行动作 |
| **E3** | 散文叙述（非代码块）中的能力描述、说明、示例讲解、给用户步骤文字 | 不在代码块内即 E3 |

**推论（照抄即可）**
- 代码块里 `curl -s https://…` → `net_egress` = **yes（E1）**；散文里"调用云端接口" → **no（E3）**。
- 代码块里 `os.environ.get("X_KEY")` → `cred_access` = **yes（E1）**；散文里"支持 AK/SK 鉴权" → **no（E3）**。
- 代码块里 `pip install xxx` → `external_dep` = **yes（E2）**。
- 散文里"运行 `bash scripts/x.sh`" → `exec_code` = **no（E3）**，除非该脚本本体确在 `scripts/` 中且其内含执行类调用。

### 8 个标签的 E1/E2 判据（照此判，不需要推断）

| 标签 | 判 yes 的事实（E1/E2） | 明确判 no 的情形（易错） |
|---|---|---|
| `exec_code` | `scripts/` 内出现执行类调用：`subprocess` / `os.system` / `os.popen` / `Popen` / `exec(` / `eval(` / `importlib` / `execSync` / `child_process` | SKILL.md 写"运行 `bash xxx.sh`"但 `scripts/` 内无执行代码 → **E3，判 no** |
| `external_dep` | 存在 `requirements.txt` / `package.json` / `pyproject.toml` / `Pipfile` / `Cargo.toml` / `Gemfile`，或脚本内 `pip install` / `npm install` / MCP server 声明 | 仅正文提"依赖某某云服务"但无声明文件、无安装命令 → E3，判 no |
| `fs_access` | 代码内出现文件读写 API：`open(` / `read_text(` / `write_text(` / `os.remove` / `shutil` / `fs.readFile` / `fs.writeFile` | 只出现工具名（`read_file` / `write_to_file`）而无实际文件 API → 判 no |
| `net_egress` | 出现 HTTP 客户端调用或命令：`requests.` / `httpx` / `urllib` / `aiohttp` / `fetch(` / `axios` / `curl` / `wget` / `http.client` | 仅"云端 / 在线服务"描述 → 判 no（那归 `external_dep`） |
| `cred_access` | 出现凭证读取事实：`os.environ` / `getenv` / `process.env` / `~/.ssh` / `~/.aws` / `.env` / `api_key` / `credential` / `secret` / `password` / `token` / `AK/SK` / `keychain` | 正文出现"令牌"但代码无读取动作 → E3，判 no |
| `state_persist` | 出现**写入非临时路径**的事实：`json.dump` / `write_text(` / `sqlite` / `pickle.dump` / `localStorage` / 写状态或日志文件 | 只出现 `.md` / `.json` 文件**名**、或只读不写、或仅 `print` 到 stdout → 判 no |
| `agent_comms` | 出现 agent 间通信事实：`send_message` / `spawn … agent` / `subagent` / `mailbox` / `agent_id` 通信协议 | 仅"多 agent / 编排"等描述性文字 → E3，判 no |
| `system_instruction` | 出现对系统提示/安全策略的**写入或覆盖**：`systemPrompt` 赋值 / `ignore previous` / `忽略先前` / `覆盖安全策略` | **产出提示词文本给人用**（prompt 工程类技能）→ 判 no |

### 边界裁定 22–26（本轮新增）

| # | 情形 | 裁定 |
|---|---|---|
| 22 | frontmatter 声明 `requires.bins`（如 `uvx` / `python3`） | `external_dep` = **yes（E2）** |
| 23 | 脚本内确有第三方 `import`（如 `from agentmail import AgentMail`）或 `pip install` / `npm install` | `external_dep` = **yes（E2）**；仅错误提示文字且无实际 `import` → no |
| 24 | 环境变量读取，变量名含 `KEY` / `TOKEN` / `SECRET` / `CRED` / `PASSWORD` / `AK` / `SK` | `cred_access` = **yes**；变量名是配置类（`*_DIR` / `*_PATH` / `*_BASE` / `*_URL`）→ **no** |
| 25 | 词形命中但**同名异义**：`mailbox` 指钉钉/邮件邮箱、`team` 指团队成员、`token` 指分页游标 | `agent_comms` = **no**——词形命中须确认确指 **agent 之间**的通信 |
| 26 | 存在 system prompt 的**赋值 / 写入 / 覆盖**语句（含作为 LLM 调用的 `system` 参数传入） | `system_instruction` = **yes**；仅"回复模板"或"不覆盖其他技能指令"的声明 → no |

通用规则：`references/` 与 `scripts/` 同等对待；`node_modules` / `.venv` / `venv` / `__pycache__` / `.trace` 内代码忽略；`tests/` / `examples/` / `docs/` 算。

### 待标注的 14 个技能

```
/Users/family/.codebuddy/skills-marketplace/skills/cloudq
/Users/family/.codebuddy/skills-marketplace/skills/content-ops
/Users/family/.codebuddy/skills-marketplace/skills/dingtalk-unified
/Users/family/.codebuddy/skills-marketplace/skills/a-stock-data
/Users/family/.codebuddy/skills-marketplace/skills/admapix
/Users/family/.codebuddy/skills-marketplace/skills/agent-mail
/Users/family/.codebuddy/skills-marketplace/skills/aihot
/Users/family/.codebuddy/skills-marketplace/skills/airbnb
/Users/family/.codebuddy/skills-marketplace/skills/anti-distill
/Users/family/.codebuddy/skills-marketplace/skills/apple-notes
/Users/family/.codebuddy/skills-marketplace/skills/api-gateway
/Users/family/.codebuddy/skills-marketplace/skills/ai-shifu-course-creator
/Users/family/.codebuddy/skills-marketplace/skills/caveman
/Users/family/.codebuddy/skills-marketplace/skills/content-repurposer
```

**请勿就这些技能的判定与我们讨论**——它们是无偏验收样本。

### 查证步骤

1. 读 `SKILL.md`（frontmatter + 全文），注意区分**代码块**与**散文**；
2. 若有 `scripts/`，逐个抽查：
   ```bash
   grep -rnE "subprocess|os\.system|os\.popen|\bexec\(|\beval\(|importlib|pip install|npm install|requirements|MCP server|\bopen\(|read_text\(|write_text\(|os\.remove|shutil|requests\.|urllib|httpx|fetch\(|curl |wget |os\.environ|getenv|api_key|credential|secret|password|token|json\.dump|sqlite|pickle\.dump|send_message|subagent|mailbox|system_prompt|systemPrompt|ignore previous" <skill>/scripts <skill>/SKILL.md | head -40
   ```
3. 每个 `yes` 必须在 `note` 写**等级 + 文件:行号**（如 `E1 scripts/x.py:L12`）；
4. 每个 `no` 至少写一句"按哪条判据 / 哪条裁定判 no"。

### 产出

写入**新文件**（不要改 `truth_b.json`）：
`/Users/family/.codebuddy/skills/skill-evaluator/openspec/changes/2026-10-10-attack-surface-tag-system-refactor/benchmark/truth_b_round4.json`

```json
{
  "set": "heldout_round4", "annotator": "B", "round": 4,
  "caliber": "v5（E1–E2 打标约束）",
  "tags": ["exec_code", "external_dep", "fs_access", "net_egress",
           "cred_access", "state_persist", "agent_comms", "system_instruction"],
  "labels": {
    "<skill-name>": {
      "exec_code": "yes|no", "external_dep": "yes|no", "fs_access": "yes|no",
      "net_egress": "yes|no", "cred_access": "yes|no", "state_persist": "yes|no",
      "agent_comms": "yes|no", "system_instruction": "yes|no",
      "note": "每个 yes 附 等级+文件:行号；每个 no 附依据条款"
    }
  }
}
```

14 × 8 = **112 个判定**，全部填满，不留 `null`、不留 `unsure`。

### 完成后回报

① 已标注技能数 / 判定数；② **哪一条判据或裁定仍然需要推断才能用**（这是本轮唯一想收集的反馈）；③ 有无技能让你觉得"判据与事实明显不符"（如实写，不要迁就判据）。

**不要**汇报 yes 分布统计，**不要**读取 `truth_a*.json`。
