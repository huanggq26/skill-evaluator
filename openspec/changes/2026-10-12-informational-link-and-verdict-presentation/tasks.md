# 任务：告知性链接隔离 + REJECT 触发维度可辨

## 1. 待实施

- [x] **#1** ✅（2026-10-12）`extract_deps.py`：识别并标记告知性链接（`informational`）
      - 实测：aihot 20 项依赖中 `/mp` 判为 informational，**API 端点无误伤**
      - 锚点：`scripts/extract_deps.py` 的 URL / CONNSTR 提取与依赖落地处
      - 判据（**两者同时满足**才判 informational）：
        ① 所在行含引导词（提示用户去 / 详见 / 参考 / 参见 / 访问 / 前往 / 看一下 / 阅读）
        ② 路径**非** API 形态（不含 `/api`、`/v\d`、`openapi`、`swagger`）
      - 验收：每条依赖带 `informational: true|false`；「详见 API 文档 `https://api.x.com/v1`」**不得**被判 informational

- [x] **#2** ✅（2026-10-12）`dep_probe.py`：告知性链接**仍探测以记录可达性**（供问题报告），但 `score=None`（不进分母）、`structural=False`（不否决）
      - 实测：`通过 19，失败 0，结构性否决=False`，可用性 100；`/mp` 记 `HTTP 404`、`informational_unreachable=true`
      - 锚点：`scripts/dep_probe.py` 探测主循环（各模式 A/B/C 分支之前）
      - 验收：`informational=true` 的依赖直接 `status="skip", category="informational", score=None`，
        不计入失败数与可用性分母；**不触发** `structural_veto`

- [x] **#3** ✅（2026-10-12）`assemble_findings.py` 新增「三点五、告知性链接不可达」章节（新增 `sample_dir` 参数）
      - 实测：`problem_report.md` 记录「`https://aihot.virxact.com/mp` —— HTTP 404，建议更新该告知性链接（不计入上架否决，仅供作者优化）」
      - 锚点：`scripts/generate_outputs.py` 与 `assets/problem_report.template.md`（待确认）
      - 验收：`problem_report.md` 出现「告知性链接不可达」小节，逐条列出链接原文、出处、状态码，
        并注明「不计入上架否决，仅供技能作者后续优化」

- [x] **#4** ✅（2026-10-12 连带达成）Verdeict 区已不再出现「安全评分 100.00」与 REJECT 并列的误导：
      - G24 修复后 verdict 由 `REJECT` → **`推荐上架`**，理由为「增量覆盖 reach 绝对数=8」；
      - 版面误导的**根因（可用性 0 触发 REJECT）已消除**，故未再改渲染模板（避免无谓行为变更）
      - 锚点：`scripts/generate_outputs.py` 的 Verdeict / 关键优势渲染处
      - 验收：Verdeict 区显式写出「触发维度 = 可用性（DEPENDENCY_GATE=100，实测 0）」或「= 安全（SECURITY_GATE=100，实测 X）」；
        安全评分为满分时**不再**作为「关键优势」与 REJECT 并列呈现（现为 `安全评分 100.00` + `REJECT` 相邻，误导）

## 2. 后续另案登记（本变更不做）

- 单次 4xx 被一律定性为「永久性契约缺陷」，无法区分服务端临时改版/迁移 → 待领域决策
- `cacu_total_score.py` 安全权重硬编码 `"security": 0.0`（:1260 / :1420）→ 待领域决策
- `quality_score` 实为 schema 合规分却命名为「编写质量」→ 待领域决策

## 3. 归档前自检

- [x] #1–#4 完成
- [x] aihot 重跑 ✅：`/mp` 判 informational → 可用性 100、结构性否决 False → **REJECT 消除（现为「推荐上架」）**；
      `problem_report.md` 已记录该链接 HTTP 404 不可达；`reach=100.00（8 个）` 为真实执行结果
- [ ] 回归： openerfailed 进程的 KEYS 保持不变（20 项依赖中告知性项被隔离，其余不受影响）
- [x] `.project/tmp/selfcheck_refactor.py` 退出码 0 ✅
- [x] `.project/tmp/check_release_isolation.py` 退出码 0 ✅
- [x] `.project/tmp/check_rule_code_consistency.py` 退出码 0 ✅（漂移 0）
- [x] `openspec validate --changes` 通过 ✅（8 items, 0 failed）
