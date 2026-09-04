# SafeTest 维度

`dimensions/` 现在有两层。

## 1. 主分类体系

主分类位于：

- [owasp-agentic-top10](owasp-agentic-top10/README.md)

这是新安全探测设计和评审的规范顶层结构。

## 2. 辅助交叉视角

以下目录保留并应继续复用：

- `dangerous-calls`：危险调用 — [审计手册](dangerous-calls/Audit-Manual.md)、[案例库](dangerous-calls/Case-Library.md)
- `dependency-risk`：依赖风险 — [审计手册](dependency-risk/Audit-Manual.md)、[案例库](dependency-risk/Case-Library.md)
- `permission-boundary`：权限边界 — [审计手册](permission-boundary/Audit-Manual.md)、[案例库](permission-boundary/Case-Library.md)
- `sensitive-info-leak`：敏感信息泄露 — [审计手册](sensitive-info-leak/Audit-Manual.md)、[案例库](sensitive-info-leak/Case-Library.md)
- `social-engineering`：社会工程 — [审计手册](social-engineering/Audit-Manual.md)、[案例库](social-engineering/Case-Library.md)

这些不再是唯一的顶层分类。它们是辅助评审视角，用于深化 ASI 分类探测的评审。

## 工作规则

对每个新安全探测：

1. 分配恰好一个主 ASI 类别
2. 可选分配一个或多个辅助传统视角
3. 针对主 ASI 类别编写探测假设、证据标准和通过/失败结论

参见：

- [Mapping-Matrix.md](Mapping-Matrix.md)
