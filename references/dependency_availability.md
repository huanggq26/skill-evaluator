# 可用性测试维度族（DEP-AVAIL）执行规格

> 本文件是 **阶段 0B 可用性预检** 的执行规格，也是 `scripts/extract_deps.py` 与 `scripts/dep_probe.py` 的**实现规格（规划/落地文档）**，供开发与维护脚本时参照。评测运行时流水线直接调用这两个已生成的脚本；本规格仅在「进入阶段 0B」或「需改动探测行为」时作为权威规则回看。
> 本文件属 `references/` 流程类规格（运行态技能文档，供执行时读取）。
> **归属**：阶段 0 的第二步（0B），位于 0A 静态预检之后、阶段 1 之前，是性能/安全耗时测试的总前置闸门。
> **条件触发**：仅当依赖提取器从被测技能上下文提取到 `external_deps` 非空时才执行 0B；为空则 `dependency_skipped=true`、0B 自然跳过（不是所有技能都需要可用性评测）。
> **约束对象**：`scripts/extract_deps.py`（DEP-EXTRACT 提取器）、`scripts/dep_probe.py`（D1–D6 探测与裁决）、`run_eval_pipeline.sh` 的阶段 0B 步骤。改这些文件前，必须先 `read_file` 本规格并与之保持一致，未读不得改探测行为（本段即细节逻辑所在）。
> **引用纪律**：本规格**自足**——业务原理与裁决规则都在本文件内（见下方各章）。
> 不引用项目外文档、不使用绝对路径：技能发布后外部文档不存在、路径也会变，
> 项目内文档之间一律用**相对路径**互相引用。
> （用户视角的体系说明见 `references/skill-evaluation-system.md`）

## 1. 前置：依赖提取与探测（是否进入本阶段）

> **关键定位修正**：`benchmark_manifest.json` 是**评测框架的中间产物**，不是被测技能的标准组成（被测技能标准是 `SKILL.md` + `references/` + `scripts/` + `assets/`）。因此 `external_deps` **不是可用性测试的前提权威，而是依赖提取器的产出**。可用性测试的真正前提应是「从被测技能上下文自动提取出的依赖清单」，而非「样本作者手填的中间文件」。

### 1.1 依赖提取器（DEP-EXTRACT，前置步骤）

在可用性阶段入口，先执行依赖提取，而非直接读 `external_deps`：

- **提取源（技能上下文，真相源）**：`SKILL.md` + `scripts/` + 配置类文件（`skill.json`/`mcp.json`/`.env` 等）。
- **两类依赖**：
  - **显式定义**：技能明示声明要访问的外部资源（如在 SKILL.md 写明"调用 xxx API"、在 MCP manifest 声明 server）。
    → 须核对「声明内容是否符合实际」：`target` 真实被使用、`declared_fields` 真实返回（D1/D2 负责）。
  - **隐式使用**：在脚本/配置中硬编码的域名、连接串、外部 host:port，技能未明示。
    → 只能从上下文静态提取（正则/特征匹配），无法靠"被测技能声明"获得。
- **提取方式**：SKILL.md 与配置扫 `http(s)://` URL；scripts 与配置扫连接串 / `host:port` / 已知 SDK 域名特征；MCP/SaaS 从 manifest 提。
- **产物**：提取结果**写入** `benchmark_manifest.json` 的 `external_deps`（作为承载格式），每条带 `source: explicit|implicit` 标记。

### 1.2 覆盖度与一致性核对（提醒级，不否决）

- **覆盖度**：若技能上下文提取到外部访问点（`http(s)://` / 连接串 / host:port），但 `external_deps` 未对应条目 → 在报告中告警「疑似漏提的依赖」，提示回归人工/LLM 补提取。**不静默 skip，也不否决**（这是样本准备范畴，非技能缺陷）。
- **一致性**：对显式声明项，核对「声明 target」是否在技能上下文中真实出现（防止 LLM 编造声明 / 声明与代码脱节）。

### 1.3 是否进入探测

- 提取后 `external_deps` 为空 → 仍产出 `dependency_skipped=true`，但**同时报告「未发现外部依赖」**（区别于"漏提"告警）。
- 存在依赖 → 对每个依赖生成对应 checker，进入 §2 维度族。

`external_deps` 字段（写入 `benchmark_manifest.json`，作为提取产物承载格式）：

> 以下为**通用占位示例**，仅说明字段结构。其中 `target` / `declared_params` / `declared_fields` 来自**依赖提取器从技能上下文提取**，框架不预设、不理解具体业务含义——探测器只做「你声明 Expect X，我验证返回有没有 X」的通用比对。

```
external_deps:
  - id: demo_api            # 提取器自定标识
    kind: http              # http | local_service | db | saas（受控枚举，见 validate_manifest_contract 守卫 7）
    target: "https://<被测服务域名>/<路径>"   # 提取自技能上下文，仅作被检测对象
    source: explicit        # explicit（技能显式声明） | implicit（从代码/配置隐式提取）
    declared_params: ["<参数名1>", "<参数名2>"]   # 选填：D3 参数生效验证所用
    declared_fields: ["<返回字段1>", "<返回字段2>"] # 选填：D2 契约验证所用（留空则 D2 自动 skip）
    credential: none        # none | env_token | conn_str | user_provided | configurable（受控枚举）
    degradation: "<降级策略声明，或指向被测技能内部文档>"  # 选填：D4 验证所用
```

## 2. 维度族（checker 注册表）

每个 checker 输出：`{name, kind: structural|transient|config, passed, detail, retry_recommended}`。

| ID | 名称 | 验证目标 | 触发条件 |
|---|---|---|---|
| D1 connectivity | 端点存活 | target 可达（HTTP 探活）；**含通配 `*` 或路径参数 `{...}` 的模板端点直接 skip（无法请求，不否决）** | 所有依赖（模板端点 skip） |
| D2 contract | 契约履行 | 返回 JSON 结构与 `declared_fields` 一致 | kind=http/saas/db |
| D3 param-effect | 参数有效性 | `declared_params` 中关键参数真实改变响应 | 有声明参数 |
| D4 degradation | 降级契约 | 校验「是否声明降级策略」：`degradation` 字段非空 / 或 references 文档含降级·兜底·重试·404 处理等描述 → pass；仅显式声明"无降级"才判缺陷 | 所有依赖（声明缺失则 skip，不否决） |
| D5 credential | 凭证可用 | 凭证可用来调用（非硬编码泄漏） | credential != none |
| D6 idempotency | 缓存语义 | **只读匿名 GET（credential=none 且 method=GET）视为天然幂等 → pass**；其余需 `idempotency` 声明 | 有缓存/轮询声明（只读 GET 免声明） |
| Dx | 扩展槽 | 未来场景（版本漂移、WS 重连…） | 按需注册 |

**扩展机制**：新增场景 = 新建一个 checker 函数 + 在 `DEP_CHECKERS` 注册表追加映射；`external_deps` 命中即调度。主干不写死具体端点。

## 3. 裁决策略（核心）

判定矩阵：

| 结果性质 | 含义 | 重试 | verdict 影响 |
|---|---|---|---|
| structural fail | 契约永久不成立（字段缺失、永久 404、凭证校验失败） | 否 | 计入 `dependency_score`；`< DEPENDENCY_GATE` → REJECT |
| transient fail | 网络超时、5xx、429 等可恢复 | 是（重试 N 次） | **不否决**；报告「瞬态观测」章节，附 retry 建议 |
| config missing | 需用户提供凭据但未配置 | 否 | 记为「未配置」，条件上架，提示补配置 |

重试规则：`transient` 项带 `retry_recommended=true`，框架自动重试 `DEP_RETRY_MAX` 次；重试成功则转 pass，仍失败降级为 structural。

> **与 §2 checker `kind` 的映射**：§2 每个 checker 输出 `kind ∈ {structural, transient, config}`（失败性质）；本文件的 `category` 分级（contract_defect / env_issue / config_defect）是 `dep_probe.py` 中 `DepResult.category` 的归属——`structural fail` 中属「技能自身缺陷」的标 `contract_defect`（否决），属「运行环境/网络」的标 `env_issue`（不否决）；`config` 类失败标 `config_defect`（不否决）。即：`kind` 描述失败性质，`category` 描述失败归属，二者经 `dep_probe.py` 的 D1–D6 实现关联。

### 阻断边界与后续阶段推进（硬规则）

**只有契约型缺陷（`contract_defect`）阻断后续阶段并触发否决**；`env_issue`（环境/瞬态）与 `config_defect`（配置待补，含模板化端点与**鉴权类失败**）**均不阻断**，须记录后**继续执行阶段 1→4**，其不可用性作为评测结果（环境限制 / 待补项）体现，**不得作为跳过阶段的理由**。

> **为什么鉴权类失败（401/403）不阻断**：`D1 connectivity` 的验证目标是**端点存活 / 链路可达**。401/403 意味着请求已完成 DNS 解析、连接建立与 HTTP 往返并获得服务端响应——**链路已通、端点存活即已证明**；未能取得业务数据源于**鉴权未通过**（属 `D5 credential` 层面）。因探活为**匿名请求**（不带凭证），此情形正是上表 `config missing`（"需用户提供凭据但未配置"），其规定即为**不否决、记为未配置、提示补配置**。把它判为契约缺陷等于把"**未能验证契约**"当作"**契约不成立**"。
>
> **边界（避免放宽过度）**：上述适用于**未提供凭证**的情形；若已声明并提供凭证却仍被拒（凭证无效 / 泄露），属真正的配置或契约缺陷，**维持既有 structural 判定**。

**推进规则（探测结果驱动，禁止推断驱动）**：

| 探测结果 | 类别 | 阻断 | 后续动作 |
|---|---|---|---|
| 2xx 可达 | — | 否 | 继续执行功能 / 性能测试 |
| 超时 / 网络不可达 / 5xx / 429 | `env_issue` | 否 | 记录为环境限制，继续执行 |
| 模板化端点 / 基路径 | `config_defect` | 否 | 提示补具体示例，继续执行 |
| **401 / 403（匿名探活遇鉴权）** | `config_defect` | 否 | 提示补凭证后重测，继续执行 |
| 凭证无效（已提供仍被拒） | 按 §3 判定 | 依判定 | 记录待补或阻断 |
| 契约不成立（结构不符 / 具体端点永久 404） | `contract_defect` | **是** | 阻断，并给失败原因与修复建议 |
| **未执行探测** | — | — | **禁止据此推断不可达**；须补执行探测或实际尝试执行后据实推进 |

## 4. 与 SafeTest 边界

- 凭证泄露（硬编码/回显）→ `sensitive-info-leak`（安全维度）
- 凭证可用（失效/配额）→ D5（可用性维度）
- 越权调用 → `permission-boundary`（安全维度）
- 依赖存活/契约 → DEP-AVAIL

边界总览：安全管「行为合规」，可用性管「依赖可达与契约成立」。该边界与 `config.md`「可用性维度（DEP-AVAIL，与安全平行）」节一致，不再于 config.md 重复定义。

## 5. 输出与常量（scripts/cacu_total_score.py）

- 新增顶层常量：`DEPENDENCY_GATE`、`DEP_RETRY_MAX`。
- `scores.json` 新增：`dependency_score`、`dependency_skipped`、`dependency.dimensions`（各 checker 结果）。
- `verdict` 裁决：structural 不通过 → REJECT；瞬态/config → 不否决（沿用 `_compute_verdict` 的 `security_expected` 同类项设计，新增 `dependency_expected` 参数分流"有依赖却无探测=REJECT"）。

## 6. 自检清单

- [ ] `external_deps` 为空时 `dependency_skipped=true`，不否决
- [ ] 每个 checker 必须显式输出 `kind`，禁止默认 structural
- [ ] 瞬态项带 `retry_recommended` 且实际重试
- [ ] 新 checker 在 `DEP_CHECKERS` 注册，不硬编码端点于主干
