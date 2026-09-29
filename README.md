# CoursePilot-Evo｜五周课程项目

**当前状态：文档、数据源副本和仓库骨架；尚无可运行的 CoursePilot Java/Python/Web 或 Benchmark 结果。**目标是在一条经审核的 2024 级培养路径上，建立可核验的学业规划 Agent，并实验将重复有效的推理沉淀为可复用的 Harness 资产。

## 一句话架构

Vue 3 Web 接受学生已修课程与目标；**System 2** Python Planning Agent 解释目标并调 typed Tool；**System 1** Java/Spring Boot 用培养计划和可选的本学期班次快照计算课程、学分、要求、冲突和计划合法性；Python Benchmark/RSI 保存 Trace，按隔离 held-out 结果晋级或回滚 `AGENTS.md/skills/tool_policy/context_policy`。Java Tool API、基模和预算在同轮比较中固定。首版**网页，不做小程序或自动选课**。

用户提供的 `.xls` 是培养计划真源。本机 `选课插件v0.6.js` 只能用于静态倒推班次字段；目前无法进入教务选课页实测，真实班次入口记为 `UNVERIFIED_NO_ACCESS`。五周首版用明确标注的模拟班次 fixture 测解析/冲突算法，对真实周五空课和实时开课一律回答 UNKNOWN。[Java 导入与规则落地方案](docs/10-java-import-and-rules.md)说明自动导入门槛、SQL 与 AI 的分工。

## 推荐阅读顺序

1. [今天可提交的项目设定字段](docs/11-project-setting-submission.md)、[项目设定 PDF](docs/CoursePilot-Evo-项目设定提交版.pdf)与[老师版五周项目安排](docs/01-teacher-project-plan.md)
2. [真实教学计划核查](docs/06-workbook-audit.md)与[浏览器班次入口/JSON Schema](docs/09-browser-adapter.md)
3. [内部 PRD](docs/02-prd.md)、[总体 TRD](docs/03-trd.md)与[Java 导入/SQL/规则实施方案](docs/10-java-import-and-rules.md)
4. [统一基础设施与工作流契约](docs/04-infrastructure-workflow.md)
5. [四组 Benchmark 与多轮 RSI 协议](docs/07-benchmark-protocol.md)
6. [五人分工和子 TRD](docs/05-team-and-sub-trds.md)、[学习仓库](docs/08-learning-repos.md)
7. [项目编码 Agent 约定](AGENTS.md)、[五人 GitHub 协作约定](docs/12-github-collaboration.md)及[Mermaid 图源](docs/diagrams/README.md)

原 v0.1 讨论稿保留在 `docs/archive/`，八周安排已失效。`data/raw/` 的原始工作簿和插件副本只作本地输入并被 Git 忽略。**计划建立五人协作的私有 GitHub 仓库；当前凭据失效，远程尚未创建**。PhysicalRSI/GDPevo 仅作设计参考，不是本项目已复现或已达成的结果。
