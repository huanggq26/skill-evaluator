# .project/tmp/ 临时物登记

> 清理依据 = **本文件的登记**，**不依据目录名**——状态为「在用」的治理脚本禁止仅因位于 `tmp/` 被删。
> 依据：`project_spec_maintenance.md#治理脚本（派生 · 有终期）`

| 文件 | 类型 | 用途 | 触发时机 | 失效条件 | 状态 |
|---|---|---|---|---|---|
| `check_spec_anchors.py` | 治理脚本 | 校验规格文件声明块含 `自检锚点` 等必需字段，缺失即非零退出 | 改规格文件后 | 「机械校验（条件项）」条款被删，或被上游规格脚本接管 | 在用 |
| `check_release_isolation.py` | 治理脚本 | 校验发布区（SKILL.md / references / scripts / assets）无开发态指针、无治理文件残留 | 打包发布前 | 发布隔离条款被删，或被上游脚本接管 | 在用 |
| `check_links.py` | 治理脚本 | 跨文档链接门禁：点分域名引用可定位 + 无违规 MD 链接 | 改任何规格/技能文档后 | 链接机制分流条款变更，或被上游脚本接管 | 在用 |
| `selfcheck_refactor.py` | 治理脚本 | 改造自验证（防漂移）：串跑真实提取链 + 断言 E24–E27 守卫放行 + 报告去噪断言 | 改标记/门禁脚本后 | 守卫体系重构或回归职责被测试框架接管 | 在用 |
| `validate_downstream_discovery.py` | 治理脚本 | 下游发现逻辑契约守卫（D1–D2 回归断言，防通用性破坏） | 改下游发现逻辑后 | 发现逻辑契约变更或被上游脚本接管 | 在用 |
| `test_session_fixes.py` | 治理脚本 | 会话修复回归测试（含端到端跑 `run_eval_pipeline.sh`） | 改会话/流水线逻辑后 | 相关修复项废弃或被测试框架接管 | 在用 |
| `test_backfill_reviews.py` | 治理脚本 | 守护 `backfill_reviews` 的 2 项**静默失败**风险：回归#1（grader 双参数显式传，防静默跳过）、回归#2（Py3.9 联合注解导入不崩） | 改 `backfill_reviews.py` 后 | 被测逻辑重构，或被测试框架接管 | 在用 |

> **回归#3 已合并**：原 `test_backfill_reviews.py` 的「hard 优先于 common」已并入
> `validate_downstream_discovery.py` 的 **D1b**（白盒），本文件不再重复守护。

## 运行方式

```bash
# 规格声明块门禁（显式入参，不写死路径）
python3 .project/tmp/check_spec_anchors.py \
  .project/AGENTS_RULES.md .project/specs/*.contract.md

# 发布隔离门禁（打包前必跑，应为 0 命中）
python3 .project/tmp/check_release_isolation.py

# 跨文档链接门禁（可重复 --scope 附加外部规格目录 / 其他项目治理区）
SPECS="$HOME/Library/Mobile Documents/com~apple~CloudDocs/Specs"
WT="$HOME/Documents/winSources/wt_hgq/.project"
python3 .project/tmp/check_links.py --scope "$SPECS" --scope "$WT"

# 改造自验证（防漂移回归）
python3 .project/tmp/selfcheck_refactor.py
```

> **路径锚定**：治理脚本不假设自身位于 `scripts/`，均以「向上查找含 `scripts/run_eval_pipeline.sh` 的目录」定位仓库根，故可置于治理区任意子目录。
>
> **已知豁免（非缺陷）**：`docs/`、`SafeTest/`、`archive/` 不套规格文档的链接规则——
> 前两者属人读文档 / 知识库导航（MD 链接是合理形态），后者只追加不改。
>
> **同名文件按同根解析**：多项目均有 `TASKLOG.md` / `AGENTS_RULES.md` 时，
> `check_links.py` 优先在引用文件所在根内解析目标，避免跨项目错配。
