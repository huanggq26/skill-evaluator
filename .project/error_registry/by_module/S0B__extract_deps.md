# S0B / extract_deps

> 阶段 0B（可用性预检）· 模块 `scripts/extract_deps.py`

## _add() — 无 scheme 相对路径被误判为外部依赖

- **ID**: ERR-006
- **标签**: `E13` `#误报`
- **状态**: active
- **发现**: 2026-09-01（源自 TASKLOG P3）
- **现象**: `_add` 对**无 scheme 的 target 也直接加入** `external_deps`，
  导致文档相对路径与文件名（实证：`report.template.md`、`spec.md`）
  被误当外部依赖 → 0B 误触发、对无效 URL 探活。
- **前提/依赖**: 违背 `SKILL.md` L118「无 external_deps 完全不出网」
- **归因**: 边界未处理——未区分「无 scheme 的相对路径/文件名」与「真实外部依赖」
- **修改策略**:
  - `_add` 增守卫：无 scheme 且含路径分隔符或文件扩展名（`.md`/`.json`/`.py`）→ 弃
  - **保留** `host.tld:port`（HOSTPORT_RE，无 scheme）与 `scheme://`（CONNSTR_RE）
- **验证方式**: 回归 aihot，确认 0B 不再对文档路径探活
- **误判史**: 无
- **⚠️ 防过宽（关键）**: **禁止一刀切要求 http(s)**——
  否则会丢失 `host:port` 类真实依赖，产生**反向漏检**。
  修误报时最易犯的错就是"扩大排除范围"，反而造成漏检。

> **同型错误**：安全探针「无端点被判全 fail」见 `S4__security_evidence.md`（ERR-007）。
> 二者可合并归因为「**状态机缺 N/A 分支**」——边界状态被当普通失败处理。
