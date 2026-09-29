# CoursePilot-Evo：给后续编码 Agent 的项目约定

当前项目只有方案、数据源副本和目录骨架。开始前依次读 `README.md`、`docs/06-workbook-audit.md`、`docs/03-trd.md`、`docs/04-infrastructure-workflow.md`，再读负责成员的 `docs/trd/*.md`。不要将计划写成已实现。

## 真实来源与边界

- `data/raw/以此为准，计算机2024级教学计划表20250306.xls` 是培养计划来源，已被 Git 忽略。24 张表覆盖多个专业和直招路径。第 1 周先选定并审核一个路径，所有课程/规则记录来源工作表、行、文件 hash。
- 该文件**没有班次的星期和节次**。无独立班次快照时，时间冲突、空周五、实时开课和余量都回答 `UNKNOWN`，不能凭建议学期推断。
- Java Tool API 是课程/学分/培养规则真值；Python Agent 只理解目标、调用 Tool 和组织解释。Evolver 不可改 Java 规则、评分器、留出答案或模型预算。
- 展示层是 Vue 3 + Vite Web 单页，不做小程序；五周安排以 `docs/01-teacher-project-plan.md` 为准，归档 v0.1 的八周排期已失效。

## 开发与验收顺序

1. 冻结 `snapshotId/schemaVersion/harnessVersion` 和 Tool/Trace 样例，再分模块写代码。
2. Java 导入和规则单测通过后，Python Agent 才把其返回作为硬事实；前端分开显示已核验、建议、未知。
3. 先用假 Tool 完成一条垂直调用链，再接真实快照。每周至少运行一次 Web → Python → Java 的集成场景。
4. Benchmark 先人工标注、固定数据和模型，再比较候选。不得读取留出答案生成修改；不得把训练提升或少量样本称为普遍提升。
5. 新接口或字段先改 `docs/04-infrastructure-workflow.md`，再同步 Java/Python/Web DTO、测试和示例。
6. 对每项完成工作记录实际测试命令与结果；未验证的模块标待验证。模型密钥和真实学生成绩不得进入 Git 或 Trace。

成员文件所有权与交付见 `docs/05-team-and-sub-trds.md`。若任务要求超出五周 MVP，先评估对首版闭环的影响，不默默增加基础设施。
