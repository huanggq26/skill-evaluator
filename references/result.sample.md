# result.json 字段定义与输出规范

## 输出文件

执行本技能后，必须将评测的量化结果写入 **`<skill-name>评测.json`** 文件，保存到系统下载目录。

> 例：评估 `my-custom-skill` 技能时，生成 `my-custom-skill评测.json`。

## 字段完整性约束

以下规则适用于所有字段，违反任一项即视为输出不完整：

- **所有 15 个顶层字段必须存在**，不可因"未发现问题"而省略字段；未发现问题时用空数组 `[]` 或 `false` 表示
- **所有数字字段必须为有效数字**，不可用 `null`、`"?"` 或空字符串替代
- `dependencies` 中各条目（`explicit_tools`、`implicit_tools`、`skills`、`system_commands`）必须包含 `name`、`function`、`scenario` 三个字段
- `content_correctness.factual_claims` 中每条记录必须包含 `verification_result` 字段（值为 `"verified"` / `"unverified"` / `"false"`）
- `content_correctness.findings` 中每条记录必须包含 `severity` 和 `explanation`
- `scoring.dimensions` 中各维度的 `passed` 计数必须与 Markdown 报告中对应数字一致

## 关键字段说明

### description_quality
| 字段 | 类型 | 说明 |
|------|------|------|
| `char_count` | number | description 的字符数，**必须是数字，不可省略** |
| `trigger_check.performed` | boolean | **必须为 `true`**，表示已检查触发场景 |
| `trigger_check.passed` | boolean | 触发检查是否通过 |
| `length_check.passed` | boolean | 长度检查是否通过（≤1024 字符） |

### grammar_analysis
| 字段 | 类型 | 说明 |
|------|------|------|
| `typo_density` | number | 错别字密度（个/千字），无错别字时写 `0`，**不可用 `"?"` 替代** |
| `contradictions[].excerpts` | string[] | 矛盾双方的原文摘录 |
| `contradictions[].lines` | number[] | 矛盾所在行号 |
| `voice_violations[].text` | string | 违规语气的原文 |
| `style_analysis.has_style_analysis` | boolean | 是否执行了风格分析 |

### dependencies
| 字段 | 类型 | 说明 |
|------|------|------|
| `implicit_tools[].reasoning` | string | 隐式调用的推理依据，必须填写 |
| `classification_field_present` | boolean | 是否包含分类字段 |

### content_correctness
| 字段 | 类型 | 说明 |
|------|------|------|
| `factual_claims[].verification_result` | string | 必须为 `"verified"` / `"unverified"` / `"false"` |
| `logic_errors[].error_type` | string | 逻辑错误类型 |
| `findings[].severity` | string | 必须为 `"critical"` / `"warning"` / `"info"` |
| `findings[].explanation` | string | 问题解释 |

### structure_analysis
| 字段 | 类型 | 说明 |
|------|------|------|
| `violations[].type` | string | 违规类型：`"jump"` / `"nesting"` / `"missing"` |
| `char_count` | number | 正文字符数 |
| `deep_nesting_found` | boolean | 是否发现深层嵌套（>4 级） |

## 15 个顶层字段列表

执行完成后必须逐项检查以下字段全部存在且已填充：

1. `skill_name`
2. `generated_at`
3. `frontmatter`
4. `description_quality`
5. `tag_assessment`
6. `related_skills_check`
7. `platform_info`
8. `structure_analysis`
9. `grammar_analysis`
10. `dependencies`
11. `content_correctness`
12. `content_completeness`
13. `security_compliance`
14. `ecosystem_check`
15. `scoring`
16. `critical_issues`
17. `warning_issues`

## 完整模式示例

以下 JSON 为 `<skill-name>评测.json` 的完整字段模式。占位符 `...`、`0`、`false`、`[]` 在实际输出中应替换为真实的评测数据：

```json
{
  "skill_name": "<被评估的 skill 名称>",
  "generated_at": "<ISO 8601 时间戳>",
  "frontmatter": {
    "fields": {"name": "...", "description": "...", "version": "...", "author": "...", "license": "..."},
    "validation_results": [
      {"field": "name", "status": "pass|fail", "reason": "...", "issues": []},
      {"field": "description", "status": "pass|fail", "reason": "...", "issues": []}
    ],
    "validation_summary": {"total_checks": 0, "passed_count": 0, "failed_count": 0, "frontmatter_score": 0},
    "issues": [{"severity": "critical|warning|info", "field": "...", "description": "..."}]
  },
  "description_quality": {
    "char_count": 0,
    "length_check": {"passed": false, "reason": "..."},
    "trigger_check": {"performed": true, "passed": false, "reason": "..."},
    "semantic_relevance": {"verified": true, "issues": []},
    "overclaimed_capabilities": [],
    "quality_score": 0
  },
  "tag_assessment": {
    "tag_count": 0,
    "tags": ["标签1", "标签2"],
    "relevance": [{"tag": "...", "relevant": false, "reason": "..."}],
    "missing_tags": []
  },
  "related_skills_check": {
    "entries": [{"name": "skill-name", "resolvable": false}],
    "has_resolvability": true
  },
  "platform_info": {
    "platforms": ["linux", "macos", "windows"],
    "has_info": true
  },
  "structure_analysis": {
    "heading_tree": [{"level": 1, "text": "# 标题", "line": 0}],
    "section_presence": {
      "overview": false,
      "when_to_use": false,
      "common_pitfalls": false,
      "verification_checklist": false
    },
    "violations": [{"type": "jump|nesting|missing", "line": 0, "description": "..."}],
    "step_numbering": {"has_numbered_steps": true, "issues": []},
    "edge_case_coverage": false,
    "title_match": false,
    "char_count": 0,
    "deep_nesting_found": false,
    "structure_score": 0
  },
  "grammar_analysis": {
    "typos": [{"line": 0, "text": "...", "suggestion": "..."}],
    "typo_density": 0,
    "contradictions": [{"location_1": "...", "location_2": "...", "excerpts": ["...", "..."], "lines": [0, 0], "description": "..."}],
    "voice_violations": [{"line": 0, "text": "...", "type": "first_person|second_person"}],
    "code_block_issues": [{"line": 0, "issue": "..."}],
    "formatting_issues": [{"line": 0, "issue": "..."}],
    "style_analysis": {"has_style_analysis": true, "imperative_mood_issues": [], "rhetorical_question_issues": []},
    "writing_quality_score": 0
  },
  "dependencies": {
    "explicit_tools": [{"name": "...", "function": "...", "scenario": "..."}],
    "implicit_tools": [{"name": "...", "function": "...", "scenario": "...", "reasoning": "..."}],
    "skills": [{"name": "...", "function": "...", "scenario": "..."}],
    "system_commands": [{"command": "...", "function": "...", "scenario": "..."}],
    "problematic": [{"reference": "...", "issue": "...", "severity": "critical|warning|info"}],
    "high_risk_commands": [],
    "classification_field_present": true,
    "dependency_summary": {"total_explicit_tools": 0, "total_implicit_tools": 0, "total_skills": 0, "total_system_commands": 0, "problematic_count": 0}
  },
  "content_correctness": {
    "factual_claims": [{"claim_id": "...", "claim": "...", "source_location": "...", "verification_result": "verified|unverified|false", "basis": "..."}],
    "false_claims": [{"claim_id": "...", "contradiction": "..."}],
    "logic_chains": [{"id": "...", "premises": [], "conclusion": "...", "valid": false}],
    "logic_errors": [{"id": "...", "error_type": "...", "description": "..."}],
    "ordering_issues": [{"before_step": 0, "after_step": 0, "violation": "..."}],
    "findings": [{"severity": "critical|warning|info", "explanation": "...", "location": "..."}],
    "correctness_score": 0
  },
  "content_completeness": {
    "command_count": 0,
    "tool_precision": {"precise_count": 0, "vague_count": 0},
    "self_containment": {"can_execute_alone": false, "prerequisite_count": 0},
    "trigger_specificity": {"score": 0},
    "file_references": {"has_subdirs": false, "all_referenced": false},
    "cross_reference_overuse": false,
    "workflow_quality": "workflow_guide|tool_reference|mixed",
    "completeness_score": 0
  },
  "security_compliance": {
    "issues": [],
    "has_violations": false
  },
  "ecosystem_check": {
    "issues": [],
    "has_violations": false
  },
  "scoring": {
    "dimensions": [
      {"name": "格式检查", "check_items": 0, "passed": 0, "pass_rate": 0, "weight": 0.20, "score": 0},
      {"name": "对外依赖", "check_items": 0, "passed": 0, "pass_rate": 0, "weight": 0.30, "score": 0},
      {"name": "内容验证", "check_items": 0, "passed": 0, "pass_rate": 0, "weight": 0.20, "score": 0},
      {"name": "安全合规", "check_items": 0, "passed": 0, "pass_rate": 0, "weight": 0.20, "score": 0},
      {"name": "生态适配", "check_items": 0, "passed": 0, "pass_rate": 0, "weight": 0.10, "score": 0}
    ],
    "total_score": 0,
    "star_rating": "★"
  },
  "critical_issues": ["问题描述1", "问题描述2"],
  "warning_issues": ["问题描述1", "问题描述2"]
}
```
