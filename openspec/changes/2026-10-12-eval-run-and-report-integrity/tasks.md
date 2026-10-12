# 任务：评测运行与质量报告的三处一致性修复

## 1. 已实施

（无——本变更新建）

## 2. 待实施

- [x] **#1** ✅（2026-10-12 已实施）阶段完成文案与 DoD 门禁自洽（**不放宽门禁**）
      - 锚点：`scripts/run_eval_pipeline.sh`（「全部阶段完成（进度 5/5）」打印处；阶段 0 DoD 检查处）
      - 验收：DoD 未满足时**不再打印**「✅ 全部阶段完成（进度 5/5）」；改为打印「阶段产物已齐（x/5），但阶段 0 DoD 未满足 → 结论不完整」；
        DoD 满足时才允许打印「全部阶段完成」。**退出码语义不变**（DoD 未满足仍为非 0）
      - 约束：R13 门禁语义不得放宽——未裁定仍不得宣告阶段完成、不得提示查看成品报告

- [x] **#2** ✅（2026-10-12 已实施）主观未裁定时，客观候选文本须带「待 AI 裁定」标记
      - 锚点：`scripts/merge_report_data.py`（objective 与 subjective 合并处）；**不改** `assets/report.template.md`
      - 验收：`deps_tools` / `deps_skills` / `deps_commands` 三个主观维度 `skipped=True` 时，
        对应的 `*_candidates` 文本渲染为「<候选文本>（客观候选，待 AI 裁定）」，不再裸显「无（文档未提及）」
      - 为什么在 merge 层而不改模版：模版是唯一真相源，改字段标注须同步 `schema_from_template.py` 派生 schema，
        风险与收益不对称

- [x] **#3** ✅（2026-10-12 已实施）run-id 缺省按 `v<N>` 递增 + 字符集校验 + 历史目录提示
      - 锚点：`scripts/run_eval_pipeline.sh:100-101`（`RUN_ID` 默认值与 `WS` 组装）
      - 验收：① 未传 `--run-id` 时，扫描 `$RESULTS_ROOT/$SKILL_NAME` 下已有 `v<N>` 目录取 max+1（无则 `v1`）；
        ② 显式传入时校验仅含 `[A-Za-z0-9._-]`，含路径分隔符或空格即报错退出；
        ③ 运行结束打印该技能下历史运行目录数量与 `LATEST.json` 位置，提示清理需手动走废纸篓
      - 约束：**不自动删除**任何历史结果目录（跨平台删除风险 + 项目删除纪律）

## 3. 归档前自检

- [x] #1–#3 完成
- [x] `validate_quality_report.py --objective` 退出码 0 ✅（`--objective ... --template assets/report.template.md` → success=true, quality_score=100, errors=[]）
- [x] `schema_from_template.py` 比对无差异 ✅（**未改模版**，EXIT=0）
- [x] aihot 全流程重跑 ✅：run-id 自动取 `v1`；DoD 未满足时不再打印「全部阶段完成」，改打印「阶段产物已生成（5/5 阶段均已执行）」+ 结论完整性待校验；非法 run-id `bad/id with space` 被拒（EXIT=2）
- [x] `.project/tmp/selfcheck_refactor.py` 退出码 0 ✅
- [x] `.project/tmp/check_release_isolation.py` 退出码 0 ✅
- [x] `.project/tmp/check_rule_code_consistency.py` 退出码 0 ✅（漂移 0）
- [x] `openspec validate --changes` 通过 ✅（7 items, 0 failed）
