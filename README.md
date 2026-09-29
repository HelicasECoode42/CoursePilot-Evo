# CoursePilot-Evo｜五周课程项目

状态：**方案与仓库骨架**。尚无可运行的 Java/Python Agent、页面或 Benchmark 结果。以用户提供的 2024 级教学计划 `.xls` 为真实培养计划来源，先做可核验的学业要求分析，再做有来源的课程建议与受控 Harness 自进化。

## 一句话架构

学生在 **Vue 3 + Vite 网页**输入已修课程与目标；Python/FastAPI Planning Agent 查询 Java 21/Spring Boot 的课程与培养规则工具；Java 返回确定性核验结果与来源；Python 保存 Trace、运行 Benchmark，并只对 Prompt/Skill/工具说明提出候选修改。五周内**做响应式网页，不做小程序**。当前教学计划没有班次时间，课表冲突和周五空课不作为首版已知能力。

## 按顺序读

1. [老师提交版五周安排](docs/01-teacher-project-plan.md)
2. [数据实查：24 张表与字段边界](docs/06-workbook-audit.md)
3. [内部 PRD](docs/02-prd.md) 与 [总体 TRD](docs/03-trd.md)
4. [基础设施/工作流契约](docs/04-infrastructure-workflow.md)
5. [Benchmark 操作方案](docs/07-benchmark-protocol.md)
6. [五人子 TRD 索引](docs/05-team-and-sub-trds.md) 与 [学习仓库](docs/08-learning-repos.md)
7. [AGENTS.md](AGENTS.md)：给后续编码 Agent 的入口

原 v0.1 讨论稿归档于 `docs/archive/`，其八周安排已失效。`data/raw/` 的原始工作簿只作本地输入，不进入 Git。各文档把目标与已实现状态分开书写；GitHub 远程尚未创建。
