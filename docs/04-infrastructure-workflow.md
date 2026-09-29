# 统一基础设施与工作流规范 v0.1

本文件是五人共用的集成契约草案；第 1 周结合真实数据冻结 v1。修改契约需记录字段变化、迁移方法和受影响模块，不在私有模块内各自定义“课程”“方案”或“成功”。

## 1. 共同标识和版本

| 标识 | 含义 | 要求 |
| --- | --- | --- |
| `snapshotId` | 同一学期的培养规则、班次和来源快照 | 每次 Tool 调用与 Benchmark 任务必须固定 |
| `schemaVersion` | API/Trace 结构版本 | 破坏性更改升大版本；客户端拒绝未知必需字段 |
| `taskId` / `traceId` | 一次用户规划与其轨迹 | 不复用；日志、结果、评分可关联 |
| `harnessVersion` | Prompt、Skill、Tool 描述和工作流配置的内容 hash | Agent 每次运行固定；禁止中途热改 |
| `verifierVersion` | Java 规则和核验器版本 | 评测前冻结；与 Harness 版本分别记录 |
| `benchmarkSetVersion` | 任务集与标准答案的 hash | 训练与留出集分别记录，留出答案隔离 |

记录来源时至少有 `sourceType`、`sourceId`、`term`、`capturedAt`、`pageOrRow?`、`confidence/verificationStatus`。`confidence` 不能替代人工确认。所有学分、周次、节次计算须在 Java 中使用同一规范化表示。

## 2. 工作流状态

| 状态 | 进入条件 | 退出条件 |
| --- | --- | --- |
| `created` | 接受用户目标和快照 | 输入校验完成 |
| `clarifying` | 关键歧义影响硬条件或数据选择 | 用户补充或取消 |
| `planning` | 查证与候选生成中 | 候选提交核验 |
| `verifying` | Java Verifier 正在处理候选 | 通过、返回错误或未知 |
| `revising` | 有可修正错误 | 重新核验或向用户解释限制 |
| `completed` | 最终答复与核验引用已持久化 | 终态 |
| `failed` | 系统错误或修正预算耗尽 | 可由用户重新发起新 task |

模型不得直接设置状态；Orchestrator 根据工具结果转移。一次 task 至多两次自动修正是首版预算建议，实际值在契约冻结时定。未知数据不能被当作验证通过。

## 3. Tool API 响应封套

```json
{
  "schemaVersion": "1.0",
  "requestId": "req-example",
  "snapshotId": "term-example-v1",
  "status": "OK",
  "data": {},
  "provenance": [{"sourceType": "curriculum_excel", "sourceId": "file-hash", "pageOrRow": "sheet1:12"}],
  "warnings": []
}
```

`status` 为 `OK | UNKNOWN | INVALID_INPUT | SNAPSHOT_MISMATCH | NOT_FOUND | INTERNAL_ERROR`。`UNKNOWN` 是业务数据缺失，不是系统异常。`PlanValidation` 中分别列 `hardViolations[]`、`unknownChecks[]`、`softScores[]`；每项有 `ruleId`、`message`、`evidenceRefs[]`。仅 `hardViolations` 为空**且**所有必需检查已知时才可标 `valid=true`。

## 4. Trace 事件规范

每条事件包含 `schemaVersion, traceId, taskId, seq, timestamp, stage, actor, eventType, inputRefIds[], outputRefIds[], toolName?, durationMs?, errorCode?, snapshotId, harnessVersion, verifierVersion`。按 `taskId + seq` 保序；重试另起 attempt 并保留前次事件。事件类型建议：`USER_INPUT`、`CONSTRAINT_EXTRACTED`、`TOOL_CALLED`、`TOOL_RETURNED`、`CANDIDATE_PROPOSED`、`VERIFICATION_RETURNED`、`CLARIFICATION_REQUESTED`、`FINAL_DELIVERED`、`ERROR`。原始学生记录和完整模型思考不进入公开 Trace；只保存必要输入引用与脱敏摘要。

## 5. Benchmark 与晋级门槛

1. 用固定 `snapshotId` 跑基线 Harness，保存 Trace、Java 核验结果、任务成功与成本。
2. Weakness Miner 只读训练轨迹，输出可复现的失败簇、证据 `traceId[]` 和候选修改点。
3. Evolver 只可改 `harness/prompts/`、`harness/skills/`、`harness/tool-descriptions/`；产出 diff、理由及预期影响。
4. 先跑训练回归，再跑封存留出集。任意硬违规增加、规则核对退化或留出任务成功率下降均不晋级；其余改善也须记录成本变化。
5. 晋级采用原子版本指针，保留上一个稳定版本；回滚只切指针，不覆盖历史 Trace。人工可以拒绝任何候选。

评测任务数（原 v0.1 计划约 30–40）是容量估计，不是已做数量。分组比例、重复次数和阈值在样本核验后固定，不能看留出结果后再调门槛。

## 6. 五人统一交付门槛

每个模块提交：输入输出样例、错误/未知案例、数据来源、接口版本、最小验证记录和下一模块使用说明。每周至少一次共享集成演示。子 TRD 使用本文件的对象和错误码，不另造同名格式。
