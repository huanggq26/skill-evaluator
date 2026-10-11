## 任务

- [x] 读项目规则层（`.project/AGENTS_RULES.md`）+ 按模块/标签查错误档案（`.project/error_registry/`）
- [x] 阶段 0 报告名定义改为英文： `QUALITY_REPORT="$QUALITY_DIR/quality_report.md"`
- [x] 同步活跃文件中的字面描述（10 个文件 / 24 处）
- [x] 三份报告标题统一为 `# <中文职能名>：<技能名>`
- [x] 同步 `validate_quality_report.py` 内硬编码的旧标题
- [x] 回归：重跑渲染，标题正确、报告行数与改前一致

## 验证证据

| 项 | 结果 |
|---|---|
| 文件名定义 | `$QUALITY_DIR/quality_report.md` |
| 活跃文件同步 | 10 个 / 24 处 |
| 历史档案 | `.project/error_registry/RECHECK.md` 按「历史归档保持原貌」纪律**不回改** |
| 渲染回归 | 标题 `质量评测报告：skill-doctor` 正确；行数 112（与改前一致） |

## 备注

- 历史结果目录中已存在的旧中文文件名**不迁移**，与新名并存（保持原貌）
- 归档待 Windows 平台评测结果回来后执行
