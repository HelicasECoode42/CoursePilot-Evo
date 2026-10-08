# E 模块：学生网页与老师报告（业务说明与 TRD）

负责人：**HelicasECoode42**。先读[团队总览](../15-team-baseline-and-batches.md)，再读本页业务功能，实施时查下半页接口与规则。当前是设计与合同，尚未实现；排期见[本期任务](../19-delivery-plan.md)。

## 先理解你要交出的完整模块

让学生顺利完成提供资料、表达目标、理解推荐和修改方案的过程；让老师通过独立入口查看评测与策略改进结果。

举例：学生只想降低工作量。页面应跳过职业问题，保留返回前的回答，展示课程评价的来源；推荐时间未知时说明待确认，学生改教师偏好后能看到新结果。

## 完整业务功能清单

| 功能编号 | 功能 | 具体需要完成什么 | 本期任务或后续期 |
| --- | --- | --- | --- |
| E-F1 | 查看和补充学业资料 | 已有本会话记录就读取，缺记录才补录；展示已满足、未满足和无法确认的培养要求。 | E2 |
| E-F2 | 引导学生表达需求 | 一次一问，支持多目标、条件分支、必须/偏好和优先级；返回保留答案。 | E1 |
| E-F3 | 比较课程与教师 | 搜索课程教师，查看来源/年份/维度/分歧，选择必须保留或优先考虑，并保留选择。 | E3 |
| E-F4 | 理解和调整推荐 | 展示候选、依据、冲突和未知；接住澄清问题，允许修改条件后重新推荐。 | E2 |
| E-F5 | 处理加载与失败 | 处理资料缺失、超时、会话失效、重试、重复点击和迟到结果，给出下一步。 | E1–E3；第七周回归 |
| E-F6 | 展示老师实验报告 | 独立受限页面显示真实基线、候选决策、质量成本和失败记录。 | 第六周细拆 |
| E-F7 | 保证页面可操作 | 桌面/窄屏/键盘可用，详情关闭后焦点返回，安全呈现评价和模型文本。 | E1–E3；第六周完善 |

上表是整个模块范围。A1/E2 等是[排期草案](../19-delivery-plan.md)的业务任务编号，尚不等于 GitHub Issue 编号；后续期功能届时拆任务。本期未覆盖的功能仍属于模块完整交付。

## 谁交给你、你交给谁

goat-yang 提供会话、查询、澄清和推荐接口；Java 事实通过 Python 后端到页面；amorfatiii 提供聚合报告。你将用户答案交 C，将页面流程交 D 验收，反馈缺失字段和显示问题。

## 你的责任边界

你拥有页面、路由、填写状态、请求适配和可访问性。学分/冲突由 Java 算，推荐由 Agent 生成，报告由 D 评分汇总。网页只调用 Python；老师报告需要后端权限支持。

## 整个模块怎样算完成

学生从资料到真实推荐/澄清/改条件可完成，普通与异常路径清楚，小屏键盘可用；老师报告显示实际运行结果，模拟与未知不会被展示为真实通过。 每项功能要有实现、实际消费者调用和正常/异常/未知的证据。权限、错误恢复等检查贯穿各功能，模拟与真实能力分别说明。

## 实现参考与技术约束

下面保留现有技术方案。业务功能是交付目标；组件、接口、函数与测试是实现这些功能的手段。字段以 contracts 为准，不在业务功能表里复制一套字段。

| 项 | 内容 |
| --- | --- |
| 责任 | HelicasECoode42，模块 E |
| 技术 | Vue 3/Vite/Router、Pinia 或会话 store、TypeScript、Fetch |
| 所有权 | web 页面/状态/API adapters、学生与老师两个路由、集成测试 |
| 输入 | 公共 DTO、C PlanningAnswer、B 经 Python 网关的事实、D RunReport |
| 输出 | 学生决策 UI、接口调用、明确 UNKNOWN 和来源、独立报告 |
| 状态 | 独立 HTML 原型，不是已接入服务的 Vue 应用 |

### 1. 需求与边界

E-01 一次一问、条件分支、返回保留；E-02 已有关联记录不重复手填；E-03 多动机而非强迫职业；E-04 课程教师详情/必须与偏好；E-05 缺真实时间不称无冲突；E-06 工程报告不进学生主线。

HTML 与 [交接规范](../../demo/README.md) 为体验参考，固定示例候选不能复制成生产推荐逻辑。学生页面不展示 Java/System/Harness/Prompt/Trace 等工程文案。

### 2. 组件结构与状态

```mermaid
flowchart TB
  R[Router] --> Q[QuestionFrame]
  Q --> G[Goals / Conditional Questions]
  Q --> T[TeacherCoursePicker]
  Q --> S[TimePreferencePicker]
  R --> C[CandidateList]
  R --> RP[独立受限 ReportView]
  D[AcademicRecordPanel / ReviewDetail] --> ST[PlanningStore]
  G --> ST
  T --> ST
  S --> ST
  ST --> API[唯一 ApiClient]
  API --> P[Python API]
```

store 分 inputDraft、record/audit、planningResult、requestState；表单 state 不等同后端事实。session bearer 只在内存，不写 localStorage/URL；刷新后提示建立新演示会话，不假装复用旧私人记录。

路由：/plan/questions/{questionId}、/plan/result、/records、/reports/{runId}。只有当前问题挂载；详情可用 dialog/drawer，键盘焦点回原入口。URL 记录问题标识，不放成绩/Prompt/token；退回保留内存答案。

### 3. 输入和调用约束

使用 [Python OpenAPI](../../contracts/planning.openapi.json)。浏览器不调 8080，不拿 serviceKey。正常入口建立会话→读本会话记录→audit；缺记录时 POST academic-records，明确完整性。成绩导入首版用结构化授权/虚构记录，不偷偷读取学校账号。

| UI 动作 | 接口 / 状态 |
| --- | --- |
| 选路径/查课程 | curricula/courses，带 requestId，处理空与分页 |
| 查教师与评价 | teacher-course-options/reviews，current/historical/unknown 分开 |
| 看职业介绍 | career-directions，按 subjectTag，只展示有来源内容 |
| 发规划/改条件 | planning，bearer+新 Idempotency-Key，previousPlanId 可空 |
| 重试同一次网络丢答复 | 保持相同幂等键与内容，不能重复建新任务 |
| 看报告 | reports，只有有 admin 资格的独立路由 |

字段由共享 TS DTO/Schema 适配，不在每个组件定义同一接口的变体。未知 nullable 不转成 0、空字符串或“无冲突”。Backend status 与 requestState 分开。

### 4. 单问题路由时序

```mermaid
sequenceDiagram
  participant U as Student
  participant W as Question UI
  participant S as Store
  participant P as Python
  U->>W: 选择多个动机
  W->>S: 更新 draft，不改变事实
  W->>W: 只显示相关下一个问题
  U->>W: 指定教师 / 时间条件
  W->>P: PlanningRequest + 幂等键
  P-->>W: CLARIFY / recommendations / UNKNOWN
  alt 需要澄清
    W->>S: 保存 Question 和既有答案
    W-->>U: 当前问题替换为澄清题
  else 有候选
    W->>S: 保存服务端结果
    W-->>U: 候选与来源、时间状态
  end
```

```mermaid
sequenceDiagram
  participant U as Student
  participant W as UI
  participant P as Query Gateway
  U->>W: 看某老师课程详情
  W->>P: reviews(courseCode, teacherKey, term?)
  P-->>W: notes + provenance / unknown
  W-->>U: 修读年份、有限反馈、不同意见
  U->>W: 必须保留这位老师
  W->>W: 写 pinned pair，不自动当已开课
  U->>W: 返回上一题
  W-->>U: 保留条件与选择
```

### 5. 状态和展示门禁

UI requestState=idle/loading/succeeded/failed；答复 decision 与 verification verdict/scope 是业务状态，不用一个 loading/error 字段包全部。

| 后端状态 | 文案与动作 |
| --- | --- |
| COURSE_ONLY / UNKNOWN | 课程建议，时间待确认，补资料入口 |
| SIMULATION + VALID | 模拟核验通过，不代表本学期课表 |
| REAL_TIMETABLE + VALID | 本次快照下核验结果，显示采集时间 |
| INVALID | 明确冲突/不满足项，调整条件 |
| ERROR/timeout | 重试同请求或重新修改，不伪造候选 |
| historical review | 往年主观反馈，本学期要求未确认 |

只有 scope REAL_TIMETABLE + verdict VALID + 对应来源资格才显示真实时间通过；不能自己从无 violations 数组推断通过。记录 completeness 影响学分文案。

### 6. 安全、易用性与调试

不使用 v-html 渲染评价/模型文本；如需 Markdown 用禁 HTML 的安全渲染器并限制 URL scheme。链接 rel=noopener noreferrer；搜索/字段受长度限制。不能将 token 放 query、下载文件或调试截图。

loading 期间禁重复执行按钮但允许阅读/返回；响应绑定 task/request revision，较旧响应不能覆盖新条件。AbortController 只取消前端等待，不宣称后端模型已停止；迟到响应丢弃。

可访问性：label、button、visible focus、dialog focus trap/Escape、aria-live 状态；桌面与窄屏检查，不靠禁止缩放修布局。系统问题给可操作文案，不对学生展示 JSON/stack。

### 7. 验收与批次

排期见[本期任务](../19-delivery-plan.md)：先学生主线与教师详情，第六周独立老师报告与体验完善。

测：非职业目标不问岗位、多目标不互相覆盖、返回保存、详情关回原焦点、未知评价无假星级、教师硬锁不消失、缺班次无绿色通过、401过期、404越权、503超时、重复点击与迟到响应、小屏溢出。PR 附桌面/手机截图和交互结果；不能仅 node 语法检查声称视觉通过。

### 契约变更与完成标准

字段以 [contracts](../../contracts/README.md) 为真源，行为以 [公共契约](../04-infrastructure-workflow.md) 为准。提交提供者/消费者 DTO、正反例和受影响测试；Schema 破坏性变更升版本，不能边跑 Benchmark 边改。调试和提交要求见 [工程规范](../16-engineering-and-debugging.md)。

任务完成至少包含：实现目录、输入/输出、正常和失败证据、限制；fixture 不算真实接入，HTML 不算生产前端，手工改 Prompt 不算 RSI。每次 PR 使用仓库模板自查，接口 PR 由相邻模块复核。
