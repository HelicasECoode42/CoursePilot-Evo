# CoursePilot-Evo：给后续编码 Agent 的项目约定

当前只有方案、原始数据本地副本和目录骨架；**不要把设计写成已实现**。先读 `README.md`、`docs/06-workbook-audit.md`、`docs/09-browser-adapter.md`、`docs/10-java-import-and-rules.md`、`docs/03-trd.md`、`docs/04-infrastructure-workflow.md`、`docs/07-benchmark-protocol.md`，再读负责模块的 `docs/trd/*.md`。根目录的本文件是开发约定，**不是**可由 Evolver 修改的运行 Harness；运行 Harness 的白名单在 `agent-runtime/harness/`。

## 真值与权限边界

- `data/raw/以此为准，计算机2024级教学计划表20250306.xls` 是培养计划原始来源；24 张表含多路径。首个路径模板做一次独立基线核对，后续同模板由自动门槛发布，保留 `sourceFileHash/sheet/row/column`。`.xls` 没有班次时间。
- `data/raw/选课插件v0.6.js` 是第三方脚本副本，仅供只读研究。它观察教务页面响应，但原代码含自动点击页面按钮与疑似索引错误，**不可原样运行/复制为 CoursePilot 的只读 Adapter**。不要调用学校接口、模拟登录或保存 Cookie/Token；当前无法访问选课页，真实快照验证延期，首版只做静态分析和模拟 fixture。详见 `docs/09-browser-adapter.md`。
- System 1 Java 对课程、学分、规则、冲突、计划合法性与来源负责；System 2 Python 对自然语言目标、规划和解释负责。Java 不做复杂自然语言推理，Agent 不自行宣布硬事实。真实班次快照未验证或时间解析未知时返回 UNKNOWN；模拟班次仅用于算法测试，不能展示成真实开课。
- 页面是 Vue 3 Web，五周不做小程序；学生在官方系统自行选课，项目无提交选课写操作。

## 开发顺序与共享契约

1. 全组 W1 先冻结 `curriculumSnapshotId/offeringSnapshotId/schemaVersion/javaToolApiVersion/harnessVersion`、CourseOffering JSON、Tool API、Trace、run manifest，再分 A–E 开发；变更先改 `docs/04-infrastructure-workflow.md`。教学计划按 `docs/10-java-import-and-rules.md` 的自动门槛发布：未知格式或总计不一致必须阻断并返回 UNKNOWN，不能用人工点批准绕过。
2. A 数据适配，B Java Environment/Verifier，C Agent/Harness，D Benchmark/RSI，E Web/集成。不要跨模块复制同一规则或独立发明 DTO；每周跑 Web→Python→Java 的一条集成链。
3. C 的生产规划与 D 的评测必须用同一个 Runner。模型、temperature、token budget、工具上限、Java Tool API 和评分器在版本比较中冻结。
4. D 的 Evolver 只见 evolution 输入与脱敏失败 Trace，不得读 Evaluator、标准答案或 held-out 题目/标签。每个 patch 至少有两个不同 case 的共同失败假设，仅修改 `agent-runtime/harness/AGENTS.md`, `skills/`, `tool_policy.yaml`, `context_policy.yaml`。保存 Snapshot/Trace/Score/Token/Latency/Tool Calls/lineage；候选不满足客观门槛就回滚。
5. 多轮机制至少覆盖 v0→v1→v2 的两次候选决策；实际未成功晋级时要保留 rejected 分支并如实报告。Token 降低且 held-out 不降质是待验证目标，不预填结果。
6. 对每项完成工作记录测试命令、输出与限制。模型密钥、学号、成绩、教务凭据、完整原始响应不进 Git/Trace；只用虚构或经授权且脱敏的测试数据。私有 GitHub 仓库 `HelicasECoode42/CoursePilot-Evo` 已创建；仍不得提交原始数据和密钥。成员邀请与分支约定见 `docs/12-github-collaboration.md`。
