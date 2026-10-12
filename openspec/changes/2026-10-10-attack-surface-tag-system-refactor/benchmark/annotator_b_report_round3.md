# 标注者 B · 第三轮标注回报（10 个无偏验收样本）

- **set**：`benchmark-2026-10-11`
- **标注者**：B
- **产出**：`benchmark/truth_b.json` **追加** 10 个条目（前 24 条一字未动）
- **独立性声明**：全程未读取 `truth_a.json`，未运行或读取 `scripts/surface_tagging.py` 的输出；10 个样本在标注期间未与任何人讨论判定。
- **规程基线**：v2 判定式 + v4 第 16–21 条。

---

## ① 完成度

| 项 | 数值 |
|---|---|
| 补标技能数 | **10 / 10** |
| 本轮判定数 | **110**（10 × 11） |
| 文件累计 | 34 个技能 / **374** 个判定 |
| `null` 残留 | 0 |
| 非法值 | 0 |
| `unsure` | 0 |

### 本轮 10 个样本里，v4 裁定确实见效的地方

- **第 19 条（执行主体）**：10 个技能里 `exec_code` 全部为 yes，且判据完全机械——每个技能都有 SKILL.md 明示的命令行或自建脚本，没有一个是"教人写代码"型。第二轮的 `agent-team-orchestration` / `content-factory` 那种 2 no + 1 yes 的分裂没有重现。
- **第 17 条（回读路径）**：判据从"叫不叫产出物"变成"有没有 readFileSync / cached for N days / 下次继续"，本轮 5 个 yes 全部由代码或文档里的明确回读动作支撑，没有一处需要靠语义推断。
- **第 18 条（表面形态）**：`tencentcloud-ocr` 因为 `resume-parsing.md:L40 ## Prompt 模板` + `L77 {raw_text}` 干净判 yes；`excalidraw-diagram` 的渲染模板无占位符、`product-showcase-site` 的 SEO meta `[App Name]` 被明确划为 HTML placeholder，两者干净判 no。
- **第 21 条（tool_calls 宽口径）**：本轮无一例因该标签产生犹豫。

---

## ② `unsure` 项

**0 个** —— 110 项全部落到 `yes` / `no`。

但以下 6 项是靠显式裁决压下去的，建议纳入最终合并前的复核（前 3 条最可能与 A 分歧）：

| 技能 · 标签 | 裁决 | 裁决依据 |
|---|---|---|
| `imsg` · `user_content` | **no** | v4 第 20 条把判据收窄为"文件/文档/网页"，聊天记录不属其三；且 history/watch/send 均为读取-展示/搬运。**但 v1 口径曾把"读聊天记录"明确列为 yes** —— 见第三节 |
| `12306-train-assistant` · `external_dep` | **no** | `client.py` 确实 `import requests`，但全仓无 requirements.txt/package.json、SKILL.md 无任何 pip install 指示。按第 13 条"需明示安装"判 no（与第二轮 `capability-evolver` 同口径） |
| `migraq` · `fs_access` | **no** | 两个脚本均无 `open()`/写文件调用；唯一写文件动作 `echo 'export ...' >> ~/.zshrc` 是安装配置命令，按第 6 条不计 |
| `migraq` · `agent_comms` | **no** | L30"原样转发给远端 CMG 专家 Agent"确为 agent 间通信，但按首轮 `andonq`/`libtv-skill` 同型先例（单次 API 调用转远端 Agent 不算 spawn/编排）判 no；本技能无 spawn/子会话/编排指令 |
| `migraq` · `prompt_intent` | **no** | L165-L172 追加上下文格式 `{用户原话}---[上下文] {补充信息}` 有字面占位符，但它是 API 请求体构造，文档未称其为 prompt |
| `product-showcase-site` · `cred_access` / `external_dep` | **yes / no** | `--auth user:password` 是技能自身命令行里的明示凭证使用 → yes；但 Chrome MCP/Playwright/Tailwind CDN/npx wrangler 全篇无明示安装指令 → no |

### 两处包内文件缺失（不影响判定，但请记录）

| 技能 | SKILL.md 引用但不存在的文件 |
|---|---|
| `conversion-ops` | `telemetry/version_check.py`、`telemetry/telemetry_init.py`（Preamble 每次启动都跑） |
| `tencent-survey` | `scripts/setup.sh`（鉴权流程核心脚本） |

两处均按 E3（SKILL.md 明示指示运行）判定，未因文件缺失改判。

---

## ③ v4 第 16–21 条中最难用的：**第 20 条**（`user_content` 搬运不算）

### 为什么是它

第 20 条把判据收窄为**"文件 / 文档 / 网页"**三件套，但**没有说明"其他形式的用户自有数据"怎么算**。本轮 `imsg` 正好卡在这个缺口上：

- `imsg history --chat-id 1 --attachments` / `imsg watch` 读取的是**用户的聊天记录与附件**；
- 聊天记录不是"文件"，也不是"文档"或"网页"——按字面判 `no`；
- 但 **v1 口径曾把"读聊天记录"明确列为 `user_content` 的 yes 示例**（v1 原表：`总结对话、按输入改写、读聊天记录`）。

也就是说，**v4 的收窄在治好了 v1 含糊的同时，很可能无意中把一类原本 yes 的情况漏成了 no**。`imsg` 是本轮唯一的测试样本，我按 v4 字面判了 `no`，但这个结论我不敢说对。

### 同一处缺口的另外两个变体（本轮未出现，但预计会命中）

| 输入形态 | 是否"文件/文档/网页" | 风险 |
|---|---|---|
| 聊天记录 / 会话历史 | 否 | `imsg` 已命中 |
| 用户粘贴的一段文字（非文件） | 否 | 本轮 `academic-translation` 的 `input_kind: text` 分支、`conversion-ops` 的 `--csv` 之外的自由文本 |
| 系统数据库内容（通讯录、日历、邮件库） | 否 | 同类 iMessage/日历/邮件 skill 会一致命中 |

### 建议改法（一句话）

把第 20 条的主语从"**文件 / 文档 / 网页**"改成"**用户自有的内容数据**（文件 / 文档 / 网页 / 聊天记录 / 数据库记录 / 粘贴文本）"，判据不变（被读取/转换/生成 → yes；仅搬运 → no）。这样既保留 v4 修好的"搬运不算"，又不会漏掉聊天记录这一类。

### 次难用：第 16 条（`cred_access` 看明示读取动作）

第 16 条把"不得以依赖的 CLI 会持有凭证反推 yes"写死了，本轮很干净（`imsg`、`excalidraw-diagram`、`conversion-ops` 都直接判 no）。

但它**没有覆盖"凭证被作为命令行参数传入"这一形态**：`product-showcase-site` 的 `--auth user:password` 既不是"读取环境变量/文件"，也不是"CLI 自己持有"，而是技能自己的命令行里明示出现的口令。我判了 yes，但这一步是推断而非条文。

**建议**：在第 16 条补一句"凭证出现在技能自身命令行参数/请求体中 → 视同明示使用，判 yes"。

### 其余四条（17 / 18 / 19 / 21）本轮无一处卡壳，建议不再修订。

---

## 附：为保持跨轮自洽而沿用的两条口径

1. **`external_dep`**：严格按"需明示安装"执行，**不**因脚本里 `import requests` 之类反推 yes（`12306-train-assistant`、`capability-evolver` 均按此判 no）。这是本轮唯一一处我认为可能偏严的取舍——若发起人认为"代码里的第三方 import 也算明示依赖"，这两条需翻为 yes。
2. **`tool_calls`**：继续采用第 21 条宽口径（具名工具 → yes），与 `exec_code` 的重叠按第 21 条明示不在本轮处理。
