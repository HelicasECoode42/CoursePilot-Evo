# 子 TRD C｜Planning Agent 与 Harness State（10 人日）

**输入：**B 的 typed Tool API、冻结的模型配置和共享 DTO。**所有权：**`agent-runtime/app.py`, `planner.py`, `tools.py`, `schemas.py`, `harness/AGENTS.md`, `harness/skills/`, `tool_policy.yaml`, `context_policy.yaml`。C 提供**唯一** `planner.run(case)` 给产品与 Benchmark 复用，不另写评测 Agent。

## 要回答的问题与实现顺序

1. **怎样理解目标？** Python 3.11+、FastAPI、Pydantic、httpx、OpenAI-compatible client。提取 `GoalIntent` 的 hard conditions、soft preferences、课程目标和 `needsClarification`；“必须/最好”不混淆，歧义影响硬判断时先问。
2. **怎样调用 Java？** 按 tool_policy 查询要求/课程/班次，模型最多提出 3 个候选，调用 `plans/validate`；硬错误最多修正一次。没有 `offeringSnapshotId` 或 Java 返回 UNKNOWN 时，不生成确定性无冲突结论。固定模型、温度、token/tool budget 并写 run manifest。
3. **怎样将昂贵分析变可复用策略？** `AGENTS.md` 写角色/边界；`skills/` 存可检验的领域步骤（例如先核路径再算缺口）；`tool_policy.yaml` 规定何时查哪种 Tool；`context_policy.yaml` 限制传给模型的字段/Trace 片段。D 的 Evolver 只能按白名单提出候选；C 维护 schema 和运行装载器，不人工偷改候选对比条件。
4. **怎样给学生解释？** `PlanningAnswer` 分 verifiedFacts/recommendations/unknowns/clarification，硬事实引用 SourceRef 或 verifierResultId；服务故障与业务未知分开。生成脱敏 Trace、Agent State 和 token 用量；不可记录私有思维链或教务凭据。

## 交付与验收

先用假 Tool 验证普通缺口、hard/soft 解析、课程不存在、无班次、工具超时、无效模型 JSON、一次 replan；再接 Java。E 可直接消费 PlanningAnswer；D 能用相同 Runner 重放 Case 并追踪版本。每个硬事实有 Java 依据；Agent 不能直接改 Java 数据或 Benchmark 答案。

**依赖：**B 交 API，D 定义 Trace/run-manifest 共同字段，E 展示 DTO。**学习入口：**[FastAPI](https://github.com/fastapi/fastapi)、[Pydantic](https://github.com/pydantic/pydantic)、[httpx](https://github.com/encode/httpx) 最小接口/校验/HTTP 调用示例。
