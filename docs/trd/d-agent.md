# 子 TRD D｜Python Planning Agent（10 人日）

**目标：**把自然语言目标转成可执行的 Java 工具调用，并在 Java 核验后给出附来源的课程建议。五周首版只用一个 Agent，不引入多 Agent 框架。

## 技术与文件

Python 3.11+、FastAPI、Pydantic、httpx、一个 OpenAI-compatible 模型客户端、pytest。建议负责 `agent-runtime/app.py`、`planner.py`、`tools.py`、`schemas.py`、`harness/prompts/planner.md`、`harness/tool-descriptions/*.json`。模型凭据仅从环境变量读取；不要放前端或 Trace。

## 一次请求怎么跑

1. FastAPI 接受 `snapshotId, completedCourses, userQuery`；Pydantic 检查字段。生成 `taskId/traceId`，固定 `harnessVersion`。
2. 用受控提示词让模型输出结构化 `GoalIntent`：课程目标、硬要求、软偏好、需澄清的歧义。若用户要求“周五空课”，记录为意愿，但 Tool 返回无班次时必须说明不能验证。
3. Python `httpx` 调 C 的 Java Tool：课程目录、要求核对；把 Tool 响应及来源交模型，而不是复制数据库或 Excel 给模型。
4. 模型提出最多 3 条候选课程建议；调用 `validateRecommendation`。若课程不存在、跨路径或重复，最多修正一次；再失败就返回错误原因和可行下一步。
5. 最终 `PlanningAnswer` 分 `verifiedFacts[]/recommendations[]/unknowns[]/sourceRefs[]/verifierResultId`。网页不能把建议渲染成规则事实。每步写脱敏 JSONL Trace。

设置最多 4 次 Tool 调用、1 次自动修正和一次请求超时预算（具体秒数在第 1 周测网络后定）。工具返回 `UNKNOWN` 时不要让模型自行补全。需要等待学生回答的澄清，返回 `needsClarification`，不无限循环。

## 验收

用 C 的假 Tool 客户端先测：普通缺口、跨路径错误、周五空课但无班次、Java 超时、模型无效 JSON；再接真实 Java API。每个最终硬事实有 `sourceRef` 或 `verifierResultId`。E 能用同一个 `planner.run(case)` 调用评测，不存在“演示 Agent”和“评测 Agent”两套逻辑。

**学习入口：**[FastAPI 官方仓库](https://github.com/fastapi/fastapi) 的最小接口与 Pydantic 示例；[pytest](https://github.com/pytest-dev/pytest) 的 fixture 和参数化测试。先实现一个显式循环，再决定是否需要框架。
