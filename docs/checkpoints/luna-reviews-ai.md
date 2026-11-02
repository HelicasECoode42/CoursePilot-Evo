# 评价汇总与 AI 证据链检查点

更新日期：2026-10-29

## 技术栈

- Java 21 / Spring Boot / JPA：评价查询、分页、课程教师匹配状态和来源引用。
- Python 3.11+ / Pydantic：唯一 planning Runner 查询课程与评价，验证模型返回的课程和评价引用，并生成逐课程依据。
- Vue 3 / TypeScript：教师页按课程与维度汇总有限评价记录；推荐依据组件展示课程来源和评价引用。

## 数据流

1. Java `searchReviews` 按课程、可选教师/学期和偏移游标分页；评价 DTO 保留 `reviewNoteId`、`matchStatus`、`dimensions` 与原始 `sourceRefId`。未绑定教师的记录维持课程级/未核实状态。
2. Python Runner 读取培养快照课程（名称、学分、类别、课程 SourceRef）和学生目标，结合意图优先级及兴趣信息排序候选；结构化动机、偏好或非空自由文本包含潜在兴趣/职业目标时按原工具预算查询评价，并把查询课程清单和记录 SourceRef 交给模型。
3. Runner 校验评价 ID 与课程对应关系及来源集合；按每门候选课程的目录信息回填 `courseSourceRefIds`、`reviewBasisStatus`、`rationaleSource`，并从 Java 查询结果派生 `reviewEvidenceRefs`（评价 ID 与 SourceRef 成对返回）。模型理由缺失时只生成明确标记为 `COURSE_FACTS` 的课程事实说明，不代写评价结论。
4. 教师页使用完整翻页后的评价记录按课程维度计数，展开内容包含摘录、来源类型、匹配状态和原始 SourceRef。组件不计算均分、星级或综合口碑分。
5. ResultView 已集成推荐依据组件；页面先显示友好来源标签，原始课程/评价 SourceRef 与记录 ID 收入默认折叠的资料详情。已关联但尚未加载摘录时显示记录数，记录存在但没有被该课程理由引用时单独说明。

## 缺失处理

| 情况 | 输出 |
| --- | --- |
| 课程已查询评价且有记录 | `HAS_EVIDENCE`；只将同课程、Java 返回的记录 ID 作为可引用评价 |
| 课程已查询但返回空列表 | `NO_RECORDS`；页面显示“暂无评价依据” |
| 因查询预算等原因没有查询该课程 | `NOT_QUERIED`；页面显示“未查询评价” |
| 旧 PlanningAnswer 未带新字段 | `null` / 空 SourceRef 列表；页面显示“评价依据状态未记录”，不推断查询状态 |
| 教师身份缺失或匹配状态不足 | 不绑定到具体教师；课程级汇总仍显示其匹配状态 |
| 课程或评价来源 | 页面显示可读来源类型；原始 SourceRef 在折叠资料详情中保留 |
| `IN_PROGRESS` 学业记录 | Runner 将该课排除出下学期候选以避免重复推荐；Runner 不将其折算为已获学分，学分状态由 Java 审核事实决定 |

## 验收

- Python：`tests/test_runner.py` 与 `tests/test_model_http.py` 共 50 项通过，覆盖课程来源回填、模型/目录理由区分、评价 ID 与 SourceRef 配对、无记录/未查询状态、旧答复兼容、`IN_PROGRESS` 排除重荐及探索步骤。
- Web：评价摘要、课程来源、推荐依据组件及 TeacherView 共 33 项 Vitest 通过；相关文件 ESLint/Prettier 检查通过，`npm run typecheck` 通过。
- Java：主 Agent 报告全量 Java 测试 196 项通过，0 失败、0 错误；当前 JVM 使用 Mockito Java agent。
- Web 全量：主 Agent 报告 326 项 Vitest 与 26 项演示检查通过。
- Java 学业核验已有测试确认 `IN_PROGRESS` 不计学分；SchoolProgress 导入端点测试也确认该状态 `earnedCredits` 为 null。

## 未完成

- 主 Agent 浏览器验收仍需确认 ResultView 推荐卡片布局、旧响应兼容和来源链接展示。
- 合成数据真实模型联调共提交两次有效 planning 请求，未得到规划答案。两次均使用通过 `PlanningRequest.model_validate` 的同一 fixture 形状、`PLAN_CS_2025`、`OFFER_2025_FALL`、新建的空合成学业记录和 `max_tokens=1000`；每次 runner `max_model_calls=1`，没有自动重试。第一次 HTTP 422 `MODEL_INVALID_OUTPUT`，“模型响应缺少 content”；第二次 HTTP 422 `MODEL_INVALID_OUTPUT`，“模型输出不是 JSON”。两次请求均未返回答案体，因此逐课程理由和评价 SourceRef 对应性未验收。请求后隔离 API 已停止，未触及用户服务 8000/8001，也未使用私有学业数据。
- 第一次的 provider 响应未保存，无法判断具体响应结构、`finish_reason` 或 usage。第二次错误表明适配器取得了非空字符串 content，但其内容不是有效 JSON；content 未保存。产生这次响应时，安全结构诊断尚未覆盖 JSON 解析失败分支，因此该次 `finish_reason` 和 usage 未写入日志。原因未查明到 provider 输出内容层面。
- HTTP 适配器现对缺失 content 和解析失败都记录结构分类、受限的 `finish_reason`、HTTP 状态及 token usage；不记录 prompt、content 或密钥。失败调用中已知的 token usage 会计入预算。该日志修复经 mock 测试覆盖；真实 provider 的 `finish_reason`/usage 尚未验证。
- 另修复自由文本未触发评价查询的条件：即使动机仅为 `CREDIT_PROGRESS`，非空 `promptText` 也会按既有工具上限查询评价；评价查询预算和核验预留保持不变。

## 目标学期文案复核

- QuestionView 的规划标题、目标问题、校验提示、时间未知提示与优先级摘要统一指向下学期。
- ResultView 由结果页负责人同步为“下学期选课规划”，模拟班次说明指向下学期开课情况。
- RecordsView 保留学校当前在读进度语义；TeacherView 的“本学期任课”保留为教师当前任课事实。CreditPlanView 未使用当前学期规划文案。
- QuestionView 与 ResultView 定向测试合计 41 项通过；类型检查、ESLint 与 Prettier 通过。
- 本轮新增：`tests/test_model_http.py` 17 项通过；`CourseReviewBasis.spec.ts` 5 项通过。诊断字段及日志仅用模拟响应验证；真实 provider 的结构原因未查明。
