# ExecAgent 阶段配置

> 本文档定义 Stage 2-3（ExecAgent baseline / withskill）专属的路径和脚本引用。
> 跨阶段共享配置 → 见 `references/config.md`。
> ExecAgent 基准合约 → 见 `references/exec_contract.md`。

---

## 执行输出路径

| 变量名 | 路径模板 | 说明 |
|--------|------|------|
| `EXEC_DIR` | `{RESULTS_ROOT}/{SKILL_NAME}/exec/` | ExecAgent 输出根目录 |
| `BASELINE_DIR` | `{RESULTS_ROOT}/{SKILL_NAME}/exec/baseline/` | baseline 阶段输出 |
| `BASELINE_METRICS` | `{RESULTS_ROOT}/{SKILL_NAME}/exec/baseline/metrics.json` | baseline 聚合指标 |
| `WITHSKILL_DIR` | `{RESULTS_ROOT}/{SKILL_NAME}/exec/with_skill/` | with_skill 阶段输出 |
| `WITHSKILL_METRICS` | `{RESULTS_ROOT}/{SKILL_NAME}/exec/with_skill/metrics.json` | with_skill 聚合指标 |
| `AGENT_WORKLOG` | `{RESULTS_ROOT}/{SKILL_NAME}/exec/agent_worklog.log` | 全局执行工作日志 |
