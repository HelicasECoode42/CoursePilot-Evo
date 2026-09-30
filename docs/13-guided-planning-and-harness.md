# 产品流程与 Harness 实施索引

开发基线以 [PRD](02-prd.md)、[开发大纲](15-team-baseline-and-batches.md)、[总体 TRD](03-trd.md)和 [公共契约](04-infrastructure-workflow.md)为准。本文件保留为旧链接的阅读入口，避免存在另一份互相冲突的协议。

学生从已关联学业记录开始，缺资料才导入。一次一问表达多动机；职业只是条件分支。查看课程教师评价、指定必须/偏好、选择时间底线，Agent 提候选，Java 校验事实，证据不足澄清或标未知。

课程/学分/时间用 SQL + Java，不以向量检索猜；少量评价先按课程教师学期普通检索。长文档 RAG 是有数据规模和评测后的扩展，不是首版前提。

Harness 演化继续使用唯一 Runner、固定配置、跨 Case 假设、有限 patch、隔离 held-out 与两轮晋级/回滚。运行策略与页面问题不同；学生页面不展示内部模型提示词、Trace、Token 或版本 gate。

- [交互与 HTML](../demo/README.md)
- [学生可能在意的维度](14-student-choice-research-and-ux.md)
- [C Agent 具体接口与时序](trd/c-agent.md)
- [D 演化具体接口与时序](trd/d-benchmark-rsi.md)
- [E 页面与集成](trd/e-web-integration.md)

当前 HTML 的数据和候选是占位，服务/评测结果仍未实现。
