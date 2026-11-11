# 接口契约基线 v1

OpenAPI/Schema 是字段真源，行为不变量见 共享契约。模块 TRD 不重复创造同名 DTO。当前版本为 1.0，具体模型和培养路径由部署配置与数据快照确定。

- [Java OpenAPI](java.openapi.json)：课程/记录/导入/核对/评价/班次/核验。
- [Python OpenAPI](planning.openapi.json)：匿名演示会话、学生 API 网关、规划与受限报告。
- [公共 JSON Schema](schemas/domain.schema.json)：必填、nullable、枚举、长度及结构门槛。
- [正反例索引](examples/index.json)：每个 fixture 说明类型和是否应该通过。

使用 OpenAPI 3.1.0 和 JSON Schema 2020-12；不是宣称采用最新规范。未知属性默认拒绝；不能偷偷接收 client ownerId、serviceKey 或模型配置。

```bash
uv sync --group dev
uv run python scripts/check_contracts.py
uv run python scripts/self_check.py
```

`docs/course-offering-snapshot.schema.json` 保留为浏览器原始导出格式参考。A 将它映射为当前 OfferingImport；B 从 `meetingTextRaw` 重新解析，不信任上传者给的 `meetings/parseStatus`，也不因 sourceKind=BROWSER_SNAPSHOT 就判来源已验证。服务端快照 `sourceValidation` 才决定真实模式资格。

改契约时提交 Schema、正反例、提供者/消费者修改或明确的兼容适配、TRD 和测试证据。破坏性变化升版本；在 benchmark 版本比较中不得修改 Java API/评分条件。

## 变更记录

- 学业核对输出支持单份记录中的最多 500 个课程编号及 503 条未知说明（逐课程说明加核对级提示）。教师选项附带最多 200 个班次编号和前 200 条评价引用。开课快照的班次数以 `sectionCount` 为准，完整评价通过 `searchReviews` 分页读取。
- Java 核验响应必须同时包含 `TIMETABLE` 和 `CURRICULUM` 两个分项。Python 在接收 Java 响应时检查两项，受控假工具也返回两项。
- 运行记录中的预算字段记录实际部署配置，默认值由 Python 设置提供。班次查询与时间预览的响应上限和单课程查询一致。

- `GET /api/v1/offerings` 的 `limit` 上限在指定 `courseCode` 时由 100 提高到 1000、默认返回该课全部班次（未指定课程时仍为默认 20、上限 100）。接口没有游标，返回条数恰为 1000 视为可能不完整。Python 的 `listOfferings` 调用（planner 班次核对、班次替换、学期班次汇总）按单课请求 1000 条，不再沿用 Java 默认的 20 条。响应形状未变。
- 新增 `POST /api/v1/session-plans/add-course`（`addSessionPlanCourse`，请求 `SessionPlanCourseAddRequest`：`previousPlanId`、`courseCode`，可选 `classId`），响应复用 `SessionPlanEditResult`（非空，带 Java 对整份新方案的 `verification`）。拒绝：课程已在方案中、标为 PASSED/IN_PROGRESS（422 `COURSE_ALREADY_TAKEN`）、方案已满 30 门（422 `PLAN_FULL`）、课程不在培养快照或开课快照（404）、指定班次不属于该课程（404）、方案无班次快照却指定班次（422）。`PlanningAnswer` 增加可选 `planningContext`（`PlanningContext`）：`targetTerm` 恒为 `NEXT_SEMESTER`，`timetableReferenceSnapshotId` / `timetableReferenceTermId` / `timetableSourceValidation` 取自方案所用开课快照；快照未知时三者为 null。旧消费者无需改动。

- `GET /api/v1/session-offerings` 的 `data` 增加必填 `mustAvoidChecks`：方案带硬时间约束时，每个候选班次各一条 `{classId, verdict}`，`verdict` 为 `CONFLICT`（Java 的 `CONSTRAINT_BLOCK_*` 违规，或来源未核验时的 `CONSTRAINT_HIT_UNVERIFIED_SOURCE`）、`CLEAR`、`CLEAR_UNVERIFIED`（来源未核验、按解析出的班次时间未命中，即 `CONSTRAINT_CLEAR_UNVERIFIED_SOURCE`）或 `UNKNOWN`（Java 的 `CONSTRAINT_UNVERIFIABLE`）；方案没有硬约束时为空数组，空数组不代表已核对。Python 对每个候选班次各调用一次 Java `validatePlan`（只带该班次与原硬约束），时间判断仍全部在 Java。`CourseOffering` 本身未改动。网页搜索预览据此标出「与必避时段冲突」，不再对此类班次显示「没有发现冲突」。

- `PlanValidation` 增加必填 `sections`（恰好两项，`scope` 为 `TIMETABLE` 本学期课表核验 / `CURRICULUM` 毕业要求核对），每项携带自己的 `verdict`、`violations`、`unknownChecks`。两个分项的判决口径与总判决相同，取值仍为 VALID / INVALID / UNKNOWN（不另引入 PASS/FAIL 词汇）。总判决 `verdict` 是两个分项中最差的一个（INVALID > UNKNOWN > VALID），Schema 用条件规则约束这一关系；顶层 `violations` / `unknownChecks` 仍是两个分项的合并，旧消费者无需改动。`schemaVersion` 保持 `1.0`（无已发布的外部消费者）。Python 网关的 `PlanValidation` 同步加入 `sections` 与分项判决约束；为不破坏既有构造该对象的测试数据，Python 侧暂缺省为空列表，待 fixture 补齐后改为必填。新增正反例：`verification-two-sections.json` 与三条反例。另新增未指定班次时的 `SECTION_UNASSIGNED` 未知项（归 TIMETABLE）。培养快照的未建模规则新增 `INFORMATIONAL` 处置（仅用于「任意选修说明」与「课程标记图例」这两类纯说明文字），不计入未知；导入时只对上述整句精确匹配，其余备注仍为 `UNMODELED`。

- `OfferingImport.sourceKind` 与 `SnapshotSummary.sourceKind` 增加 `OFFICIAL_DOCUMENT`（官方公开课表文件转换所得），导入后 sourceValidation 恒为 `UNVERIFIED`。`OfferingImport.offerings` 上限由 2000 提高到 7000：2026-27 秋季官方课表共 6431 条，须整体进入同一开课快照，否则同一学期被拆成多个快照。新增 `POST /api/v1/offering-snapshots/{snapshotId}/verification`（`verifyOfferingSnapshot`，管理员密钥）与 `OfferingVerificationRequest`/`OfferingVerificationResult`：核验人与上传人不得相同；样本至少 30 条；错误率不超过 2% 记为 VERIFIED，否则 REJECTED；SYNTHETIC 快照不可核验；每次写审计记录。只有 mode=REAL、快照 VERIFIED 且方案项都在该快照内时，方案核验 scope 才为 REAL_TIMETABLE。Python 网关两处 sourceKind 枚举同步加入该值。

- 新增 `POST /api/v1/advice/chat` 及 AdviceChatRequest/Answer、课程建议、学校进度引用与确认动作 Schema，支持有来源的课程咨询。相同请求重放不重复调用模型；明确选课与优先考虑分别进入硬条件和软偏好。完整字段与交互见 对话接口。

- `Recommendation` 增加可选 `courseRationales` 和 `explorationDirections`：逐课程理由携带所引用的评价编号，探索方向包含可执行的学习步骤。Python 校验理由所引用的评价来自同一课程的已查询证据；方向内容为模型建议。
- `GET /api/v1/reviews/search` 增加可选的 `cursor` 和响应 `nextCursor`，按评价 ID 顺序分页；课程维度统计需要读取全部页面。评价记录数不等同于独立评价人数。
- `ImportWorkbook` 增加可选 `sourceKind`：默认 `SYNTHETIC`；受限本机导入时可显式选择 `CURRICULUM_FILE`，服务端将快照标为 `UNVERIFIED`，不会由上传者指定已核验状态。同一工作簿的真实来源与虚构快照分别保存。`Course` 增加可选 `suggestedTerm`，表示培养文件中的建议修读学期，不代表本学期开课。
- 新增 `GET /api/v1/offering-snapshots`（Java 侧 `listOfferingSnapshots`，网关侧 `gatewayListOfferingSnapshots`），列出已发布的开课快照（kind=OFFERING, state=PUBLISHED）。响应与 `GET /api/v1/curriculum-snapshots` 同形（`data.items: SnapshotSummary[]`），`SnapshotSummary` 未改动。培养方案列表继续只返回 kind=CURRICULUM，两条路径互不混入。Web 据此在建会话时取开课快照，并由 `isCurriculumUsableForMode` 按模式筛选，不再把 `offeringSnapshotId` 写死为 null。
- 新增 `GET /api/v1/academic-records`，列出本会话已有的学业记录。此前只有按 ID 读取和创建两个接口，学生无从得知自己的记录编号，`docs/15` 第 2 节「已有本会话记录则读取，缺记录才补充」这一步在契约上无法实现。归属由会话派生，浏览器不提交 owner，与 `docs/17` 的身份边界一致；`items` 为空数组表示尚无记录，属于正常业务状态，不返回 404。同时补上 `AcademicRecord` 的一个正例与两个反例，此前该对象没有任何样例。同一条链路在 `java.openapi.json` 补上对应的 `listAcademicRecords`（`GET /api/v1/academic-records`）：Python 网关需要它才能向 Java 取记录，此前只有 Python 侧声明而 Java 侧缺失，提供者与消费者不同步。
- `TeacherCourseOption` 增加可选字段 `courseName`、`sectionCount`、`offeringSnapshotId`、`offeringSourceValidation`、`factSource`（均可为 null，旧数据缺省）。`GET /api/v1/teacher-course-options` 不新增参数：培养快照下的教师选项在原有绑定登记之外，由同一培养快照课程对应的开课快照推出（`factSource=OFFERING_SNAPSHOT`）。开课快照按 VERIFIED 优先、其次 OFFICIAL_DOCUMENT、同级取最新选取，永不取 SYNTHETIC；培养快照未登记学期时不按学期过滤。开课事实未核验（快照非 VERIFIED）时 `availability` 为 `UNKNOWN`，只有核验通过的快照才可能是 `CURRENT_VERIFIED`。同一课程与教师两边都有时以开课事实为准。`OFFERING_SNAPSHOT` 的三个来源字段为必填（domain.schema.json 条件规则）。`TEACHER_BINDING` 的旧行为不变。Python 网关 `TeacherCourseOption` 与 Web `contracts.ts` 同步加入可选字段；Web 界面如何展示未核验开课事实由 Web 侧接线。

- `Constraint.kind` 增加 `BLOCK_SLOT`（星期 × 节次的交集），软偏好增加 `schedule.blocked_slot`。同时为三个时间 kind 加条件规则：`BLOCK_DAY` 的 `section` 必须为 null，`BLOCK_SECTION` 的 `dayOfWeek` 必须为 null，`BLOCK_SLOT` 两者都必须非空。在此之前 Schema 并不禁止同时填写两者，语义只靠文档约定，属于已存在的歧义。`schemaVersion` 保持 `1.0`：各模块均未开始实现，无已发布消费者需要兼容。模块开工后再改契约必须升版本。

离线校验仅验证契约、引用与样例；跨字段含义、对象级授权、SQL 事务和运行截止时间仍必须在模块测试中验证。
