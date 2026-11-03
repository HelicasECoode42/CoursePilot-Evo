# B 模块：Java 数据与规则核验（业务说明与 TRD）

负责人：**mira-xu**。先读[团队总览](../15-team-baseline-and-batches.md)，再读本页业务功能，实施时查下半页接口与规则。当前已有可运行实现：课程/班次查询、学业核对、时间解析与冲突判断、服务密钥与对象级授权，54 个测试通过。契约 15 个操作实现了 5 个，其中只有 `auditRequirements` 端到端可用——`listCourses`/`listOfferings` 出参不合契约，两个学业记录端点恒返回 UNKNOWN；排期见[本期任务](../19-delivery-plan.md)。

## 先理解你要交出的完整模块

让系统准确回答课程事实、学生已满足哪些要求，以及推荐方案哪些条件通过、违规或无法确认。每项判断要有数据和规则依据。

举例：学生已经修过某门必修课两次，另一类学分资料不完整。你应按支持的重修规则计一次，并将无法确定的类别标为未知；推荐班次缺时间时不能宣布没有冲突。

## 完整业务功能清单

| 功能编号 | 功能 | 具体需要完成什么 | 本期任务或后续期 |
| --- | --- | --- | --- |
| B-F1 | 保存并查询业务资料 | 保存培养计划、课程、学业记录、教师评价和班次；保留版本/来源，正确处理重复发布与存储失败。 | B1 |
| B-F2 | 核对学业进度 | 计算选定完整路径的必修与类别学分满足情况；处理已修去重、支持的重修/替代，区分缺口、建议与未知。 | B2 |
| B-F3 | 提供课程教师资料 | 查询课程教师对应关系及评价证据，明确历史、当期和未知，不用旧评价证明当期开课。 | B1；第六周补边界 |
| B-F4 | 理解上课时间 | 唯一解析时间原文，保留周次和节次；不支持的格式给出原因。 | B3 |
| B-F5 | 核验推荐方案 | 核对完整候选课程方案、硬条件、时间冲突及可计算偏好；支持将一门课程替换为指定真实班次后重新核验整份方案；逐项返回冲突原因/检查范围/未知和核验版本，已知违规优先于未知。 | B3；第六周班次替换 |
| B-F6 | 保证资料隔离与一致性 | 只允许访问所属记录；拒绝错误快照/学期和过期核验引用；数据库操作失败时保持完整性。 | B1–B3；第七周回归 |

上表是整个模块范围。A1/E2 等是[排期草案](../19-delivery-plan.md)的业务任务编号，尚不等于 GitHub Issue 编号；后续期功能届时拆任务。本期未覆盖的功能仍属于模块完整交付。

## 谁交给你、你交给谁

JiangYiLin-Q121 提供规范化资料和核对基线；goat-yang 提供候选和待核验条件。你向 Agent 返回事实、学业核对和方案核验结果，由网页经 Agent 后端使用；与 amorfatiii 核对独立预期。

## 你的责任边界

你拥有持久化、权限/事务、规则计算和唯一时间解析器。XLS 读取归 JiangYiLin-Q121；推荐策略和解释归 goat-yang；页面归 HelicasECoode42。数据库与 Java 判定由你维护。

## 整个模块怎样算完成

完整路径学业核对与独立预期一致；班次算法覆盖正常/冲突/未知；方案不能绕过核验，其他人的记录与混版本输入被拒绝。 每项功能要有实现、实际消费者调用和正常/异常/未知的证据。权限、错误恢复等检查贯穿各功能，模拟与真实能力分别说明。

## 实现参考与技术约束

下面保留现有技术方案。业务功能是交付目标；组件、接口、函数与测试是实现这些功能的手段。字段以 contracts 为准，不在业务功能表里复制一套字段。

| 项 | 内容 |
| --- | --- |
| 责任 | mira-xu，模块 B |
| 技术 | Java 21、Spring Boot/Web/Validation、JPA、MySQL、Flyway、JUnit |
| 所有权 | domain/application/api/persistence、TimeParser/ConflictChecker、核验结果 |
| 输入 | A 的受控导入、可信主体与当前快照、C 的候选 |
| 输出 | AuditResult、只读事实、评价证据、PlanValidation |
| 状态 | 契约与设计；无可运行 Java 服务 |

### 1. 需求追溯与唯一写入

班次输入可参考 [SHUOSC 历史样本](../09-browser-adapter.md)。B1/B3 与 A 核对来源类型、标识关联、校历和容量策略后再接入；`teacherId` 不能直接作为本项目 `teacherKey`，时间原文中的备注与缺周次不能被忽略。历史格式测试与当期真实核验分开。

方案工作区的班次替换复用 `GET /api/v1/offerings` 查询课程在指定学期快照下的多个班次，并复用 `POST /api/v1/plans/validate` 对替换后的完整 `PlanItem[]` 进行核验。Python 是 Web 唯一入口；B 不增加浏览器直连路径。每个返回班次必须保留 `classId`、原始时间/解析状态、来源及所属快照。Java 必须把变更后的整份方案与其余班次和 `hardConstraints` 一起核验；单个班次自身无冲突不代表放入整份方案后无冲突。无真实、同学期且通过资格检查的 offering snapshot 时返回 UNKNOWN。

B-01 核对必修/类别学分；B-02 分开建议与硬要求；B-03 时间完整解析/冲突；B-04 评价身份和来源；B-05 UNKNOWN 不通过；B-06 对象级隔离与不可变版本。

B 写课程/快照/学业记录/评价与核验记录；A 只提交 draft，C 只通过 Tool API 读事实。Java 不调用模型解释自然语言，也不把社区评价认证为客观成绩。

### 2. 组件和表关系

```mermaid
flowchart TB
  API[Controllers: DTO / 认证 / 参数] --> APP[Application Services: 事务与编排]
  APP --> AUD[AuditEvaluator]
  APP --> TP[唯一 TimeParser]
  APP --> CF[ConflictChecker / HardConstraintChecker]
  APP --> RV[ReviewQuery]
  APP --> REP[Repository Ports]
  REP --> DB[(MySQL / Flyway)]
  AUD --> D[无框架依赖的 Domain Rules]
  CF --> D
```

```mermaid
erDiagram
  CURRICULUM_SNAPSHOT ||--o{ REQUIREMENT_RULE : defines
  CURRICULUM_SNAPSHOT ||--o{ CURRICULUM_COURSE : contains
  ACADEMIC_RECORD ||--o{ COMPLETED_COURSE : has
  OFFERING_SNAPSHOT ||--o{ COURSE_OFFERING : contains
  COURSE_OFFERING ||--o{ MEETING : has
  TEACHER o|--o{ REVIEW_NOTE : matched
  VERIFICATION_RESULT ||--o{ VERIFICATION_ITEM : has
```

Repository 只保存/查询，Domain 不依赖 Controller/JPA；transaction 由 application service 管。Flyway 唯一管理表变更，不用自动 ddl 覆盖历史数据库。

### 3. 接口合同

完整路径/字段见 [Java OpenAPI](../../contracts/java.openapi.json)。所有请求需 Service Key；X-Subject-Id 仅来自可信 Python。全局 import 另需 Admin Key。academic record 每次检查所属 scope，不能只查主键。

| 接口 | 输入 | 输出 / 行为 |
| --- | --- | --- |
| requirements/audit | recordId + curriculumSnapshotId | AuditResult，缺口/建议/未知分开 |
| courses | 发布快照 + query/limit/cursor | Course[]，SourceRef |
| teacher-course-options | 培养快照 + courseCode/query（课程号、课程名、教师名子串） | 绑定登记（TEACHER_BINDING）与本学期开课表（OFFERING_SNAPSHOT，取 VERIFIED 优先、OFFICIAL_DOCUMENT 次之的非 SYNTHETIC 快照）合并；开课事实未核验前 availability 为 UNKNOWN，historical/current/unknown 不能用旧评价证明当期 |
| reviews/search | courseCode、teacherKey?、term?、limit≤10 | 有维度与来源的 ReviewNote[] |
| offerings | 双快照、courseCode | 原文/Meeting/parseStatus；不跨学期 |
| plans/validate | items≤30、硬条件、记录、mode/双快照 | verdict/scope/violations/unknownChecks |
| preferences/score | verifierResultId + 偏好 | 可计算 metrics 和 unknownMetrics |

`AuditService.audit(recordRef, snapshotRef, subject)`；`TimeParser.parse(raw, calendar)`；`ConflictChecker.check(Meeting[], Meeting[])`；`PlanValidator.validate(plan, facts)`。Domain 返回结构化原因，不返回“AI觉得不错”。

### 4. 关键不变量

学分 BigDecimal；已修去重与重修/替代按受控规则。无完整记录、未知规则或重复认定不明确时相应要求 UNKNOWN，不把未知贡献算零以得出确定缺口。

源快照不可修改，新的内容产生新版本；核验绑定输入摘要、recordRevision 和两个快照。偏好评分不能用旧 result 给新 candidate 算分；校验 request digest 和所属 scope。

时间全部消费：未知余串/待定/未给周次不得默认每周。schema 上限不是学校实际上限，实际 calendar 限制更严格。weeks 需非空排序去重，sectionStart≤sectionEnd。

判决：已知 violation→INVALID；无 violation 但未完成 hard check→UNKNOWN；全部检查且无 violation→VALID。synthetic 可 VALID 但 scope=SIMULATION；REAL 只用 VERIFIED、同学期、未过期快照。今天没有这种真实快照。

### 5. 核验时序

```mermaid
sequenceDiagram
  participant C as Python ToolClient
  participant API as Java API
  participant S as PlanService
  participant DB as Repository
  participant V as Domain Verifier
  C->>API: validate + trusted headers
  API->>S: validated DTO / subject
  S->>DB: record scope + immutable snapshots
  DB-->>S: facts / missing status
  S->>V: plan + facts + source eligibility
  V-->>S: INVALID / UNKNOWN / VALID + checks
  S->>DB: 保存结果与输入 hash
  S-->>C: Envelope，verifierResultId 与 provenance
```

```mermaid
sequenceDiagram
  participant W as Python Gateway
  participant A as AuditService
  participant D as DataRepository
  W->>A: audit(recordRef, trackSnapshot)
  A->>D: 读所属 record、规则、SourceRef
  D-->>A: immutable facts
  A->>A: BigDecimal / 去重 / 受控规则
  alt 输入完整且规则已发布
    A-->>W: 确定结果 + 建议
  else 资料不全
    A-->>W: affected requirements UNKNOWN
  end
```

### 6. 错误与故障

| code | HTTP/status | 行为 |
| --- | --- | --- |
| RECORD_NOT_FOUND | 404 NOT_FOUND | 不泄露其他 scope 记录 |
| SNAPSHOT_MISMATCH / TERM_MISMATCH | 409 CONFLICT | 拒绝混版本计算 |
| UNKNOWN_TIME_FORMAT / OFFERING_UNAVAILABLE | 200 UNKNOWN | 拦无冲突结论 |
| SOURCE_UNVERIFIED / SNAPSHOT_STALE | 200 UNKNOWN | 不用来源标签冒认真实 |
| COURSE_NOT_FOUND | 422 INVALID_INPUT 或 validation violation | 请求查询错误与候选错误区分 |
| TOOL_UNAVAILABLE | 503 ERROR | 不退化成已通过 |

### 7. 安全、观测与测试

参数化 SQL，排序/字段白名单，不执行用户或模型 SQL。只读查询有限分页；response 无原始成绩名单/堆栈。日志只记 requestId、耗时、核验原因。导入单事务，snapshot 发布后只读；并发重导用唯一键和事务处理重复，而非先查后插竞态。

测试：单双周不重叠、离散周交集、节次边界、未知余串、缺周次、错误学期、synthetic/REAL 混用、部分已知违规加未知、record 越权、重复导入、旧 verifier 复用。第五周完成培养事实/模拟时间与 C/E 联调。B/D 共同复核事实标签，不向 Evolver 开放答案。

### 契约变更与完成标准

字段以 [contracts](../../contracts/README.md) 为真源，行为以 [公共契约](../04-infrastructure-workflow.md) 为准。提交提供者/消费者 DTO、正反例和受影响测试；Schema 破坏性变更升版本，不能边跑 Benchmark 边改。调试和提交要求见 [工程规范](../16-engineering-and-debugging.md)。

任务完成至少包含：实现目录、输入/输出、正常和失败证据、限制；fixture 不算真实接入，HTML 不算生产前端，手工改 Prompt 不算 RSI。每次 PR 使用仓库模板自查，接口 PR 由相邻模块复核。

### 当前可验证实现补充（2026-10-28）

课程目录中的 `Course` 只作为跨版本的课程编号身份；名称、学分、类别存于 `CurriculumCourse` 的快照关联，来源元数据单独存于 `SourceReference`，目录响应携带 `sourceRefIds` 和完整的 `provenance`。课程查询、学业核对及 `MAX_CREDITS` 均按请求的培养快照读取关联属性。合成种子只写入新建的合成培养快照，不依据旧 `Course` 行或旧关联推导版本属性/来源。

升级到该模型后，旧快照关联的新增字段保持空值，不会被全局课程信息自动补齐。课程查询遇到缺属性或缺来源的关联返回 `SNAPSHOT_COURSE_FACTS_UNKNOWN`（HTTP 409）；学业核对和方案学分上限保留 UNKNOWN。该行为需要后续导入流程提供来源和快照字段后才能恢复确定核验。目前仓库没有真实授权培养计划数据，本实现和测试均为 synthetic；不构成真实课程来源或真实规则验收。属性和来源实体已可持久化，导入发布事务仍未接入。

### 开课快照人工核验与多段时间（2026-11-02）

- `OFFICIAL_DOCUMENT` 来源导入后恒为 UNVERIFIED。`POST /api/v1/offering-snapshots/{snapshotId}/verification` 写入抽样核验审计（核验人、上传人、样本数、错误数、样本 SHA-256、结论）。错误率 ≤ 2% 为 VERIFIED，否则 REJECTED；以最近一次结论为准。核验人与上传人（忽略大小写与空白）相同拒绝；SYNTHETIC 快照不可核验。
- 方案核验：mode=REAL 且快照 VERIFIED、带学期、方案项都在该快照内，scope 为 REAL_TIMETABLE，时间检查照常执行，不再产生 TIMETABLE_UNVERIFIED。仍缺任一条件则保持 COURSE_ONLY 与未知项。
- TimeParser 支持一个周次块对应多段节次（`星期四第3-4,7-8节{9-12周}` 拆为两段）。截断或残缺片段仍整体未知。
- 尚未实现：核验过期机制（快照没有有效期字段，REAL 只检查学期非空）；SnapshotSummary 不展示核验人与时间。

### 方案核验分项：本学期课表 / 毕业要求（2026-11-03）

`POST /api/v1/plans/validate` 的结果新增 `sections`，把两类结论拆开，避免演示时整份方案都显示为“未知”：

| 分项 scope | 含义 | 归入的 violations / unknownChecks |
| --- | --- | --- |
| TIMETABLE | 本学期课表：班次归属、时间冲突、时间类硬约束、班次来源核验、钉选课 | CLASS_COURSE_MISMATCH、TIME_CONFLICT、CONSTRAINT_*、TIMETABLE_UNVERIFIED、TIME_UNPARSEABLE、CLASS_NOT_FOUND、SECTION_UNASSIGNED、CONSTRAINT_UNVERIFIABLE、PIN_* |
| CURRICULUM | 毕业要求：学分上限、未建模培养规则 | MAX_CREDITS_EXCEEDED、CREDITS_UNKNOWN、COURSE_FACTS_UNKNOWN、CREDITS_SCOPE_UNSUPPORTED、UNMODELED_CURRICULUM_RULES |

- 分项判决与总判决同口径：有 violation 为 INVALID，无 violation 但有 unknown 为 UNKNOWN，否则 VALID；总判决 = 两个分项中最差的一个。
- TIMETABLE 判 VALID 的条件：每个方案项都有班次且时间可解析、班次快照已核验（REAL 需 VERIFIED 且同学期），且无冲突、无违规。方案项未指定班次时记 SECTION_UNASSIGNED，不通过。
- 只有 `UNMODELED` 规则进入 CURRICULUM 的 UNKNOWN；`INFORMATIONAL`（任意选修说明、课程标记图例）不计入。`EXCLUDED` 不参与。
- 学分缺口、转读完整性 (TRANSCRIPT_COMPLETENESS_UNKNOWN) 与 PENDING_COURSE 仍只在 `/requirements/audit` 中判定；方案核验的 CURRICULUM 分项目前只覆盖 MAX_CREDITS 与未建模规则，不声称已核对全部毕业要求。
- 测试：`PlanValidationEndpointTest` 覆盖分项拆分、总判决取最差、SECTION_UNASSIGNED；`OfferingVerificationEndpointTest` 覆盖（a）已核验无冲突 → TIMETABLE VALID 而 CURRICULUM UNKNOWN（未建模规则）；（b）OFFICIAL_DOCUMENT 未核验 → TIMETABLE UNKNOWN(TIMETABLE_UNVERIFIED)；（c）BLOCK_DAY 命中 → TIMETABLE INVALID、总判决 INVALID；`A1WorkbookImporterTest` 覆盖 INFORMATIONAL 分类。
- 已知限制：Python 网关的 `PlanValidation.sections` 暂缺省为空列表（既有 fake/测试数据未带分项），页面尚未展示分项；这两处需在 UI 与 fixture 任务中补齐。
- 已知限制：`INFORMATIONAL` 是新的处置值。`spring.jpa.hibernate.ddl-auto=update` 不会修改已存在表上的枚举检查约束，已有本地库需用新导入重建（或手工放宽约束）后才能写入此处置值；未重新导入前，现存库中的 `UNMODELED` 行保持原样，仍会作为未知出现。
