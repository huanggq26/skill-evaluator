# 任务清单

> 归档前自检项与初筛命令遵 `.project/AGENTS_RULES.md#治理执行清单（薄层）` C 小节。

## 0. 前置（每次续跑必做）

- [x] 读项目规则层（`.project/AGENTS_RULES.md`）重建约束上下文；按模块与标签检索错误档案（`.project/error_registry`），读完原文核对前提后再动手，禁止只读单一证据源

## 1. 已实施并通过本机验证

- [x] **R26** 修复 §3 模板 `.format()` 调用形式错误 → 以具名参数传值，验证：对有可比任务的评测跑 `generate_outputs` 退出码 0
- [x] **R27a** 关键问题汇总标注由 `field` 改 `dim`，汇总槽位排除「未检查」渲染 → 验证：v4 真实数据重渲染输出 9 严重 + 9 警告，AI 补充显示为「无」
- [x] **R13** 新增 `scripts/check_stage0_dod.py` 并接入 `run_eval_pipeline.sh` 阶段 0 尾部 → 验证：v4 数据识别出 13 个未裁定槽位、退出码 1；逃生阀 `--skip-subjective-gate`
- [x] **R22** `_baseline_unavailable_reason()` 识别写示例结果却判成功者 → 验证：v2 数据 C_01 标注为「未真实执行」，C_02（真成功）未被误伤
- [x] **R28** `_resolve_task_dir()` 兼容 exec 两层嵌套 → 验证：v5 数据 §4.2/§4.3 一致显示「未实测」，不再出现「技能未能交付该能力」
- [x] **R20 根因** `extract_deps.py` 移除 `method: "GET"` 预填 → 验证：v5 运行 6 个 405 归 `config_defect`，`structural_veto=False`（不再否决）
- [x] **R19** `assemble_findings.py` 标题改为按质量报告路径推导技能名 → 验证：输出 `# 问题报告：<技能名>`
- [x] **R11** 默认清空（resume 除外）→ 验证：start/full 清理本技能子目录，resume 保留
- [x] **R29** runner 顶部 `python3 → python` 回退 → 验证：`bash -n` 通过
- [x] **R30** `extract_stats.py` 与 `_common.load_json` 改 `utf-8-sig` → 验证：带 BOM 的 SKILL.md 成功解析出 `name`，带 BOM 的 JSON 成功 `load`
- [x] **R31** `merge_report_data` 功能表未归纳时 `text` 留空 → 验证：报告显示「未检查」，占位文案消失

## 2. 待实施（根因已定位）

- [x] **R32** 依赖探测自动识别访问方法（`dep_probe.py`）
      - GET 返回 405 且 manifest 未声明 method 时，按候选方法依次重试（POST → HEAD → PUT）
      - 命中 2xx 则按该方法的真实结果判定，并在 `retry` 中建议 manifest 声明该方法
      - 全部失败才归 `config_defect`
      - 验收：对已知 POST 端点（本次 6 个 405 端点）重测，能自动识别并给出真实可用性结论
- [x] **R33** 修正 `exec_security_evidence.py` 的 `no_external_endpoint` 误判
      - 现状：manifest 有 8 个 external_deps 仍跳过采集 → §6 安全评估整节为空
      - 验收：对含 external_deps 的技能，安全评估不再因该误判而空缺
- [x] **R34** 主观 rows 列名宽容 → 验证：v5 数据重渲染，「原因」列由裸级别词「警告」变为真实描述「代码块缺少语言标签 4 处…」
- [x] **R40** 产出物标的（内容级）：新增 `scripts/validate_report_completeness.py`，把「报告必须含有什么」固化为机器可判项 → 验证：对 v5 产物精确报出 5 项内容缺陷（text 占位 / 7 处空白单元格 / §4.1 降级 / 安全整节 N/A / 问题报告 3 处空白），零误报
      - 键名别名归一（如 `问题`→原因、`建议`→改进建议）；无法归一时空单元格显式呈现缺失而非留空
      - 验收：AI 以 `问题/原因/位置` 填写时，报告三列均有正确内容
- [x] **R35** §4.1 兼容纯文本功能表：无表格行时直接采用文本，不再降级为「未完成 AI 归纳」
- [x] **R36** 功能清单标题归一化：剥离前导序号（`2. `），保证表格各行一致
- [x] **R37** 主观裁定写入校验：占位字面值（`text`/`待填`/`N/A`）须报错拦截 ——**决定不实施**：v16 实测占位值 0 处（提示词约束已生效）；加机器拦截有误伤风险（合法值「无」会被拦），收益不抵风险。
- [x] **R38** `exec_functional_tasks.py` 的 `_run` 脚本路径改为检查 `cmd[1]`
- [x] **R39** 生成脚手架内的 shebang 由 `python3` 改为跨平台写法

## 3. 归档前自检

- [x] 待实施各项全部勾选 ——**决定不实施**：v16 实测占位值 0 处（提示词约束已生效）；加机器拦截有误伤风险（合法值「无」会被拦），收益不抵风险。
- [x] 以真实评测产物（非模拟数据）复跑全链路，确认报告内容与退出码均正确
- [x] 回归入口退出码 0
