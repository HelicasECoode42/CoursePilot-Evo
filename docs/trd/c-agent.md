# 子 TRD C v1.0｜Planning Agent 与运行 Harness

| 项 | 内容 |
| --- | --- |
| 责任 | C，待填写；11 人日 |
| 技术 | Python 3.11+/FastAPI/Pydantic/httpx、受控模型客户端 |
| 所有权 | API 网关、application Runner、ToolClient、意图/候选/Guard、运行 Harness |
| 输入 | PlanningRequest、session scope、Java facts、固定配置 |
| 输出 | PlanningAnswer、TraceEvent、RunManifest |
| 状态 | 无真实 Agent；HTML 候选不算实现 |

## 1. 需求追溯与边界

C-01 多动机/hard-soft；C-02 条件澄清；C-03 指定教师必须/偏好；C-04 按需取证；C-05 Java 二次核验；C-06 相同 Runner 给生产和评测用。

C 不直读 MySQL、不自算学分/时间、不改 gold/evaluator；未知信息不由模型补值。学生查询经 Python 白名单网关，Service Key 不进入 Web。少量职业内容按来源整理，不做实时爬取。

## 2. 结构与内部接口

```mermaid
flowchart LR
  API[FastAPI / session / idempotency] --> R[PlanningApplication]
  R --> I[IntentResolver / ClarificationPolicy]
  R --> T[Typed ToolClient]
  T --> J[Java]
  R --> M[ModelAdapter]
  M --> G[CandidateGuard / EvidenceBinder]
  G --> T
  R --> A[AnswerCompiler]
  H[HarnessLoader: snapshot allowlist] --> R
  R --> O[TracePort / ResultRepository]
```

`runner.run(request, executionContext) -> PlanningAnswer` 是唯一入口；executionContext 分离主体、deadline、模型配置和 snapshot。`ToolClient.call(registeredTool, dto, context)` 不接受模型 URL。`CandidateGuard.check(items, facts)` 拦不存在/错教师/错快照对象；`AnswerCompiler.compile(verdicts, evidence)` 不许改 Java 判决。

api 只解析请求；application 管状态；domain/policies 纯决策；adapters 封装模型/HTTP/存储。Prompt 文件单独版本化，不把整个业务函数写进 Prompt。

## 3. HTTP 契约

[Python OpenAPI](../../contracts/planning.openapi.json) 为真源：session 创建、只读查询网关、record 创建/查询、audit、planning、受限报告。body 不接受客户端 ownerId/model/temperature/budget/自报 scope。

PlanningRequest 必填 schemaVersion、curriculumSnapshotId、academicRecordId、mode、intent、promptText；offeringSnapshotId、previousPlanId 用 null 表示无。intent 中 motives、hardConstraints、softPreferences、pinnedTeacherCoursePairs 分开；priorityOrder 需确认。

| header | 语义 |
| --- | --- |
| Authorization | session bearer，服务端解析主体 |
| X-Request-Id | 合法请求定位 ID，不等于幂等键 |
| Idempotency-Key | 同会话同内容复用；不同内容 409 |

PlanningAnswer decision=CLARIFY 必须有 Question 且无 recommendations；每份 recommendation 有 PlanValidation，最多 3 份。UNKNOWN 可保留课程层建议，不能返回真实合格课表。usage 未取得 token 用 null。

## 4. 正常与重规划时序

```mermaid
sequenceDiagram
  participant W as Web
  participant P as API
  participant R as Runner
  participant J as Java
  participant M as LLM
  W->>P: request + idempotency key
  P->>P: session / scope / 摘要 / 幂等
  P->>R: trusted context
  R->>J: audit / courses / evidence
  J-->>R: typed facts 与未知项
  R->>M: bounded context，评价仅数据
  M-->>R: candidate JSON 或 clarification
  R->>R: Pydantic / identity guard
  R->>J: validate(candidate)
  J-->>R: verdict/scope/provenance
  R-->>P: structured answer
  P->>P: 原子保存结果、Trace、幂等缓存
  P-->>W: Envelope
```

```mermaid
sequenceDiagram
  participant W as Web
  participant P as Planning API
  participant J as Java
  W->>P: 改条件 + previousPlanId + 新幂等键
  P->>P: 旧方案所属主体校验；重新绑定当前版本
  P->>J: 重新查事实与验证
  alt 指定教师与硬条件冲突
    P-->>W: 询问放宽哪项，不静默换教师
  else 无法取得真实时间
    P-->>W: 保存意愿 + 时间 UNKNOWN
  else 已有完整事实
    P-->>W: 新核验与推荐
  end
```

## 5. Harness、预算和安全门禁

ModelAdapter 只允许选定模型端点，不接受文件/评价里给的 URL。tool_policy 白名单工具、次数上限；context_policy 选本次任务需要的事实/评价，不把全库、历史全部聊天塞入模型。

默认累计 input8000/output2000 tokens、6 tools、3 model calls、45 秒；各调用按剩余预算设置 timeout。provider 自动重试关闭。无效模型 JSON 最多在模型调用预算内修复一次；超过即 MODEL_INVALID_OUTPUT，不因语言顺畅放行。

HarnessLoader 只加载已记录 hash 的白名单快照。文件内容是策略文本/受控配置，不能 import/exec 生成代码。运行 root AGENTS.md 与 repo 工程规范不被 Evolver 修改。

系统处理评价中的“忽略之前指令、调某 URL、泄露 key”等文本为资料，不执行。模型候选 ID 必须属于工具给的集合；可信答案引用 evidence ID。日志不写完整 Prompt/私有思维链或学生成绩。

## 6. 故障与恢复

| code | 处置 |
| --- | --- |
| REQUEST_IN_PROGRESS / IDEMPOTENCY_CONFLICT | 409，不双跑 |
| MODEL_TIMEOUT / RUN_DEADLINE | 504，原任务标 failed，不伪造方案 |
| MODEL_INVALID_OUTPUT | 422/ERROR，有限修复后停止 |
| TOOL_UNAVAILABLE | 503 ERROR，不声称无冲突 |
| EVIDENCE_MISMATCH | 拦主张/候选并澄清或返回未知 |
| BUDGET_EXCEEDED | 停止运行，保留用量和失败原因 |

即使模型请求取消不了，也不能继续发布迟到答案；请求 taskId/attempt 标终态，丢弃超过 deadline 的输出。幂等缓存只对当前合法会话可读，过期会话不可重取私人记录。

## 7. 验收与批次

W1 API/intent/Runner/Trace 合同；W2 typed fake Tool；W3 真 Java、多目标/教师/重规划；W4 固定 manifest；W5 两轮 Harness。

案例覆盖：高分≠学分、少签到≠低工作量、最好≠必须、返回澄清、缺班次、恶意评价注入、候选错 ID、教师锁定冲突、模型非法 JSON/超时、幂等重试不双费用、不同 scope previousPlanId。与 D 比较生产/评测 Runner 的模型配置和工具集合一致。

## 契约变更与完成标准

字段以 [contracts](../../contracts/README.md) 为真源，行为以 [公共契约](../04-infrastructure-workflow.md) 为准。提交提供者/消费者 DTO、正反例和受影响测试；Schema 破坏性变更升版本，不能边跑 Benchmark 边改。调试和提交要求见 [工程规范](../16-engineering-and-debugging.md)。

任务完成至少包含：实现目录、输入/输出、正常和失败证据、限制；fixture 不算真实接入，HTML 不算生产前端，手工改 Prompt 不算 RSI。每次 PR 使用仓库模板自查，接口 PR 由相邻模块复核。
