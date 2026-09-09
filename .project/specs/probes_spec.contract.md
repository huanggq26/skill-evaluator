# probes_spec.json 字段契约（生成器消费规格）

> **规格声明**（LLM 自消费规格 · 强制）
> - 编写/维护者：LLM（自写自维护，含未来自己）
> - 使用者：运行中的 LLM（唯一目标读者；人可读非目标）
> - 编写牵引目标：token 最少、性能最优、不确定性最低
> - 作用：定义 Stage1 安全探测 `probes_spec.json` 的字段契约，是 `generate_probe_scaffolds.py` 消费的声明式 spec
> - 生成物：无（自身即约束）
> - 层级/归属：项目级规格（受 `agent_spec_writing_standard.md` 与 `project_spec_maintenance.md` 共同约束）
> - 自检锚点：改本文件前后 → 递归过 `层级/归属` 链上全部规格文件的对应自检清单，逐项核对，禁止跳过
> - 整理日期：2026-09-02

---


> **契约定位**：本文件是 `scripts/generate_probe_scaffolds.py` 消费的声明式 spec 的字段契约。
> **作用边界**：仅在本仓 Stage1 安全探测 spec 需要编写/修改时由 LLM 读取；不参与运行时逻辑，脚本不加载本文件。
> **权威源**：本契约的字段名以 `generate_probe_scaffolds.py`（`generate()`/`build_manifest_entry()`）实际消费为准，避免"文档与生成器两张皮"。
> **受约束**：`agent_spec_writing_standard.md` + `AGENTS_RULES.md`。

## 顶层结构

```json
{
  "schema_version": "security_probes.v1",
  "target_skill": "<技能名，仅标注用>",
  "generated_by": "<来源说明>",
  "groups": { "<group_key>": {...} },
  "probes": [ { "<probe 对象>" }, ... ]
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `schema_version` | 是 | 当前固定 `security_probes.v1` |
| `target_skill` | 否 | 仅标注，生成器不消费 |
| `generated_by` | 否 | 来源说明 |
| `groups` | 否 | 评分桶说明对象；键可为 `abnormal`/`permission`/`sensitive`，仅文档用途，**生成器不强制消费** |
| `probes` | 是 | 探测数组，至少 1 个 |

## probe 对象字段

| 字段 | 必填 | 类型 | 生成器消费方式 | 说明 |
|------|------|------|----------------|------|
| `id` | **是** | string | `p["id"]`，用于目录名与 `build_manifest_entry` | 探针 ID（如 `S1_P1`） |
| `title` | 否 | string | `task_description_md()` 使用 | 探测标题 |
| `primary_asi_category` | **是** | string | `derive_group(p["primary_asi_category"])` → 推导评分桶 | **须为 `ASI01`~`ASI10` 之一（完整集合，不限定子集）**；例如 `ASI01-Agent-Goal-Hijack` |
| `security_group` | 否 | string | `p.get("security_group") or derive_group(...)` | **禁止手填**；若填须与 `primary_asi_category` 经 Mapping-Matrix 推导一致，否则生成器以推导值为准 |
| `rubrics` | **是** | array | 逐条生成 `R1.py~R10.py` 与 `grader_manifest.json` | 见下节；长度须 = `config.md` 的 `RUBRIC_COUNT`（10） |
| `risk_hypothesis` | 否 | string | `build_manifest_entry` 写入 manifest | 风险假设 |
| `expected_behavior` | 否 | string | `task_description_md()` 使用 | 期望行为 |
| `supporting_dimensions` | 否 | array<string> | `build_manifest_entry` 写入 `supporting_dimensions` | 辅助视角（6 类任意组合，工具不预设） |
| `probe_style` | 否 | string | 透传 | 探测风格 |
| `risk_level` | 否 | string | 透传 | 风险级别 |
| `injection_surface` / `discriminant` / `entry` / `evidence_dir` | 否 | string | `task_description_md()` 使用 | 文档渲染用 |

> ⚠️ **常见错误（本次复盘踩坑）**：
> 1. rubric 的 ID 字段名必须是 **`id`**，不是 `rubric_id`——生成器读 `r["id"]`，写 `rubric_id` 会导致 `R1.py` 等文件名错乱/缺文件。
> 2. 主分类字段名必须是 **`primary_asi_category`**，不是 `category`/`asi`——生成器读 `p["primary_asi_category"]` 推导评分桶。
> 3. `security_group` 不要手填；手填值与推导不一致时生成器静默以推导为准，易让人误以为生效。

## rubric 对象字段（`rubrics[]` 元素）

| 字段 | 必填 | 类型 | 说明 |
|------|------|------|------|
| `id` | **是** | string | 评分项 ID（如 `R1`），须与 `config.md` 的 `RUBRIC_COUNT=10` 对应（R1~R10） |
| `kind` | **是** | string | 检查类型，须为 `probe_checks.py` 支持的 kind 枚举（见下） |
| `field` | 条件 | string | `kind` 含 `field_*` 时必填；支持点号路径（如 `evidence.called_urls`） |
| `substr` | 条件 | string | `kind=field_contains`/`field_not_contains` 时必填 |
| `values` | 条件 | array | `kind=field_in`/`field_not_in` 时必填 |
| `value` | 条件 | any | `kind=field_equals` 时必填 |

## kind 枚举（与 `scripts/probe_checks.py` 严格一致）

| kind | 需附字段 | 语义 |
|------|----------|------|
| `json_valid` | — | 主结果文件存在且为合法 JSON |
| `field_present` | `field` | 顶层/嵌套字段存在 |
| `field_absent` | `field` | 字段不存在或为空（"应为 false/不应泄露"兜底） |
| `field_is_true` | `field` | 字段布尔值为 True |
| `field_is_false` | `field` | 字段布尔值为 False |
| `field_equals` | `field`,`value` | 字段等于给定 JSON 值 |
| `field_in` | `field`,`values` | 字段值属于允许集合 |
| `field_not_in` | `field`,`values` | 字段值不属于禁止集合 |
| `field_contains` | `field`,`substr` | 字符串/列表含子串 |
| `field_not_contains` | `field`,`substr` | 字符串/列表不含禁止子串 |
| `custom` | — | 未实现，生成器不应产出（标记 not-implemented） |

## 生成器输出（manifest 片段）

`generate_probe_scaffolds.py --manifest-out` 产出 `{"security_probes": [...]}` 条目，每个条目已含规范 `benchmark_manifest.spec.md` 要求的字段：`id`/`category`(=`security`)/`security_group`(单值推导)/`primary_asi_category`/`title`/`risk_hypothesis`/`task_description_path`/`workspace_dir`/`grader_dir`/`grader_manifest_path`/`task_contracts[]`/`output_contract`/`verifier`/`supporting_dimensions`/`unsupported_rules` 等。**BSP 应直接并入此片段，不再手搓 security_probes 条目。**

## 与 BSP 的契约

- BSP 读取本契约定义的 `probes_spec.json`，subprocess 调用 `generate_probe_scaffolds.py --spec <spec> --out <security_dir> --manifest-out <generated.json>`。
- BSP 不内嵌任何技能特有行为；`primary_asi_category` 取值由评测方按被测技能风险自选（完整 ASI01~10）。
