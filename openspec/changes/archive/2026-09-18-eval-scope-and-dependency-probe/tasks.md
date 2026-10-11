## 任务

- [x] 读项目规则层（`.project/AGENTS_RULES.md`）+ 按模块/标签查错误档案（`.project/error_registry/`）
- [x] **R12** 扫描范围排除不随发布包分发的内容（治理区 / 规范区 / 平台机制目录 / 版本控制文件）
- [x] **R12** 目录树遍历排除清单同步（`build_objective_data`）
- [x] **R20** 依赖探测按 manifest 声明的 HTTP 方法发起请求
- [x] **R20** 405 且未声明 method 时判为 `config_defect`（不否决）

## 验证证据

| 需求项 | 验证 |
|---|---|
| R12 | 对 `skill-doctor` 重跑：`machine_absolute_paths` **3 → 0**（`.gitignore:12`、`.project/CONTEXT_HANDOVER.md:66/82` 消除）；`eco_portability` 3 → 0；`objective_warning` 4 → 1（余下 1 条为真实问题） |
| R20 | 模拟 405（不联网）：未声明 `method` → `skip/config_defect`（不否决）；已声明 `POST` 仍 405 → `fail/contract_defect` |

## 待确认（实施时裁决）

| # | 事项 |
|---|---|
| Q9 | 治理入口文件（`AGENTS.md` / `CODEBUDDY.md` / `opencode.json`）是否一并排除——项目文档称其不发布，**倾向排除**，待确认 |
| Q10 | 排除后目录树（dir_tree）是否仍展示被排除目录——**倾向不展示**，改为报告注明「未纳入评测」清单 |

## 备注

- R12 依据：项目 `SKILL.md`「发布包不含任何开发态文件」+ `openspec/config.yaml` 第 4 条
- 归档待 Windows 平台评测结果回来后执行
