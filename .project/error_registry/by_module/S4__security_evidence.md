# S4 / security_evidence

> 阶段 S4（安全探测）· 涉及 `scripts/exec_security_evidence.py`、`scripts/exec_security_probes.py`

## 安全探针「无端点」被判全 fail（语义倒置）

- **ID**: ERR-007
- **标签**: `E13` `#误报`
- **状态**: active
- **发现**: 2026-09-01（源自 TASKLOG P3 根因 2）
- **现象**: `exec_security_evidence` 因**无端点**跳过采集 → 无证据文件
  → 10 探针 Grader 全判「结果文件缺失」（R1–R10）→ **全 fail**。
  **无端点 = 无攻击面 = 无可采集证据**，按现状却得 0 分（**语义倒置**）。
- **前提/依赖**: 被测技能无网络端点
- **归因**: 边界状态未特殊处理——把「采集被跳过」等同于「安全失败」
- **修改策略**:
  - 跳过时标记 `evidence_skipped`
  - 探针 / 聚合据此输出 **N/A 满分**（`status=pass/na`），落 `grading_result.json`
- **验证方式**: aihot（有端点、4/4 pass）不受影响；无端点技能得 N/A 而非 0
- **误判史**: 无
- **⚠️ 继承策略（禁止退化）**: 真有端点时的 fail 判定**必须保留**，
  仅对「证据采集被跳过 / 无端点」这一特定状态放行。

> **同型错误**：`S0B__extract_deps.md`（ERR-006）。
> 合并归因：**状态机缺 N/A 分支**——边界状态被当作普通失败处理。
