# SafeTest

`SafeTest` 是跨阶段共享的安全评审库，在 `SampleAgent` 设计安全探测（选定 `primary_asi_category` 主分类）与 `SpecAgent` 评审探测时共同使用。它已从原 `references/SpecLibrary/` 提升至共享层 `references/SafeTest/`，不再隶属于任一阶段专用目录。

本库采用双层结构：

1. `dimensions/owasp-agentic-top10/`
   - 规范主分类体系
   - 对齐 OWASP Top 10 for Agentic Applications 2026
2. 现有交叉维度
   - `dangerous-calls/` — 危险调用
   - `dependency-risk/` — 依赖风险
   - `permission-boundary/` — 权限边界
   - `sensitive-info-leak/` — 敏感信息泄露
   - `social-engineering/` — 社会工程
   - `content-policy-compliance/` — 内容策略合规
   - 这些保留为可复用的评审视角，而非唯一顶层分类

## 使用方式

当 `SampleAgent` 设计安全探测或 `SpecAgent` 评审探测时：

1. 首先在 `dimensions/owasp-agentic-top10/` 下选择一个主 OWASP ASI 类别
2. 然后在需要时选择一个或多个辅助传统视角
3. 编写探测，使探测假设、预期风险行为和通过/失败证据全部绑定到主 ASI 类别
4. 使用传统视角丰富评审深度，而非替代主 ASI 分类

## 设计目标

本结构的目标是：

- 保留现有 SafeTest 内容和积累的案例
- 将库对齐到 OWASP agentic 威胁分类体系
- 使探测设计更全面地覆盖之前建模不足的内存、通信、级联失败和 rogue-agent 风险

## 来源基础

本结构保留现有 SafeTest 材料，并融合来自以下来源的相关分类和缓解思路：

- `OWASP Top 10 for Agentic Applications 2026`

高层原则参见：

- [principles.md](principles.md)
- [dimensions/README.md](dimensions/README.md)
