# A 班次资料交付核对（Issue #22）

状态：**A 侧资料交接已完成；B 侧导入、解析和查询接入待后续适配。** 本文件记录契约核对、SHUOSC 固定历史样本的审计摘要和虚构测试输入；不代表历史班次已导入，也不代表它们可用于当前选课。

## 1. 契约核对

- `CourseOffering.classId` 已是必填字段，满足契约的数据项要提供它。一个课程的多个班次应表示为 `OfferingImport.offerings[]` 中多条记录：`courseCode` 相同、`classId` 不同。不是给单条班次记录新增另一个属性。
- `OfferingImport` 顶层提供 `termId`、`sourceKind`、`capturedAt` 和 `calendar`，数组每一项提供 `courseCode`、`classId`、`teacherKey`、`teacherText`、`meetingTextRaw`、`meetings`、`parseStatus` 和 `sourceRefId`。`meetings` 与 `parseStatus` 是导入对照值；Java 必须重新解析 `meetingTextRaw`。
- 当前 `sourceKind` 只允许 `BROWSER_SNAPSHOT`、`SYNTHETIC`，不能诚实表示 SHUOSC 已发布的历史公共数据。不能把历史数据标成 `BROWSER_SNAPSHOT` 或 `SYNTHETIC`。
- Schema 没有在单次 `OfferingImport` 中要求 `classId` 唯一；同一快照内的唯一性需由导入校验保证。多个班次的获取边界应由同一 `offeringSnapshotId` 与 `termId` 确定。

## 2. 固定历史样本审计

来源为 [shuosc/shu-course-data 的 data 分支](https://github.com/shuosc/shu-course-data/tree/data)，固定文件 [`terms/2024-2025-3.json`](https://github.com/shuosc/shu-course-data/blob/data/terms/2024-2025-3.json)，固定上游提交 `a6e8b59be67dfc416e871a8b16dc45ebb19a7e53`。文件 SHA-256：`0ab433a2fabb83a7195e0670d2312605edd8cdd24932540857d356512f44257d`；上游记录数 4,822；所属学期 `2024-2025-3`（2024–2025 学年春季）；本地读取时间 `2026-10-25T19:18:49Z`。抓取/读取日期不改变历史学期。

SHUOSC 仓库页面目前标为 archived，因此此固定样本只能说明历史记录格式，不能替代当前学期数据。

完整 JSON 只保留在本机 `data/raw/a3/shuosc-2024-2025-3.json`（该路径被 `.gitignore` 忽略）。仓库只记录固定来源、提交、哈希和审计摘要，不提交完整历史数据或逐条教师/班次原文。按 A1 工作簿 8 条路径中的课程号精确比对，共 460 个课程号行、101 个不同课程号；其中 381 条历史记录匹配 43 个不同课程号，23 个课程号各有多个历史班次。匹配记录的上游 `teacherId` 均非空；应用用户批准的公式后，381 个派生 `classId` 无重复。逐条候选映射仅保留在被忽略的 `data/private/a3/offering/historical-a1-matched-classid-candidates.json`；审计摘要在被忽略的 `data/private/a3/offering/historical-sample-audit.json`。

### 字段映射与不能推断的字段

| 上游字段 | 候选映射 | 当前结论 |
| --- | --- | --- |
| `courseId` | `courseCode` | 以字符串精确匹配 A1 课程号，保留前导零；导入端也应按原字符串处理。 |
| 无 `classId` 字段；`teacherId` 来自上游 `KXH` | `classId` 候选 | SHUOSC [采集映射代码](https://github.com/shuosc/shu-course-data/blob/main/src/index.ts#L1054-L1088)把上游 `KCH` 输出为 `courseId`、把上游 `KXH` 输出为 `teacherId`，代码中没有按上课时间生成 `teacherId` 的逻辑证据；[上海大学本科生学生手册](https://xxgk.shu.edu.cn/ziliao/shanghaidaxuexuebenkeshengxueshengshouce2023nian.pdf)说明同课不同教师另设教师序号。SHUOSC 公开样本的值可复用于来源记录和派生 `classId`，但不能据此证明它是跨课程稳定的教师身份号。用户已批准将 `termId + ":" + courseId + ":" + teacherId` 用作本次历史候选数据的派生 `classId`。这不是 SHUOSC 原始字段，也不代表 `teacherId` 是教师全局身份；原值仍另存为来源侧标识。 |
| `teacherId` | `teacherKey` | **不映射，统一为 `null`。** `teacherId` 是 SHUOSC 从上游 `KXH` 复制出的来源字段；本次候选输出将它另存为 `upstreamTeacherId`，不填入 `teacherKey`。SHUOSC 资料没有证明它是稳定的教师身份键。当前教务选课系统的对应编号语义也尚未独立核实，不能假设其与 SHUOSC 编号生成机制相同。 |
| `teacherName` | `teacherText` | 显示名称候选，不是稳定身份键；空值需按契约/导入规则处理，不能造姓名。 |
| `classTime` | `meetingTextRaw` | 可原样提供给 B 的唯一 `TimeParser`；不能由 A 另写解析器或声称已解析。 |
| 文件学期标识 | `termId` | `2024-2025-3`，为历史学期。 |
| 本地读取时间 | `capturedAt` | 是本地取得副本的时间，不等于上游更新时间或开课时间。 |
| 无对应字段 | `calendar` | 固定数据不含该学期校历/节次依据；不得猜周数或每日节次数。 |
| 历史公共来源 | `sourceKind` | 当前 enum 无对应值，需跨模块确认后另行变更契约。 |

因此，SHUOSC 文件**没有可原样复制的 `classId` 字段**；它有 `teacherId`，但采集代码只是把上游 `KXH` 映射到该字段，现有公开材料不足以说明该值由爬虫按上课时间生成。当前选课系统的编号规则仍需以该系统实际公开字段或用户脱敏导出单独核实。本次按用户批准的公式，为 A1 匹配到的本地历史候选行生成 `termId:courseId:teacherId`，并验证了同课多班次区分及 ID 唯一性。逐条候选记录是提供给 B 适配的历史 staging 数据，不是可直接提交的 `OfferingImport`：当前 `sourceKind` 枚举无历史来源选项，来源没有提供权威校历，时间由 B 的 Java 解析器重新处理。历史文件不能代表当前学期或有效的当前冲突核验快照。

## 3. 虚构契约样例

以下样例均标为 `SYNTHETIC`，只验证数据形状和预期逻辑，不证明 SHUOSC 历史班次映射成功：

- [同课多班次且时间冲突](../contracts/examples/offering-import-synthetic-conflict.json)：同一 `courseCode` 两个不同 `classId`，时间重叠。
- [同课多班次且时间不冲突](../contracts/examples/offering-import-synthetic-no-conflict.json)：同一 `courseCode` 两个不同 `classId`，时间不同。
- [班次时间未知](../contracts/examples/offering-import-synthetic-unknown-time.json)：保留两种不同 `classId`，其中一条原文不能解析；预期不得降级为“无冲突”。

预期冲突样例采用星期/节次/周次交集判断。Schema 校验仅验证结构；真正的 `TimeParser` 重解析和整份方案冲突判定由 B 执行。`sourceKind=SYNTHETIC` 样例只能用于测试或模拟，不能用于 REAL 核验。

## 4. B 后续适配提示（不属于本次 A 侧改动）

公共契约声明了 `POST /api/v1/offering-snapshots/import`，`GET /api/v1/offerings` 也要求 `curriculumSnapshotId`、`offeringSnapshotId`，并可按 `courseCode` 查询。但当前 Java 实现的 `CourseOffering` 只有 `offeringId`、`courseCode`、教师文本、时间原文和 `sourceKind`；未持久化 offering snapshot、`termId`、独立 `classId`、`teacherKey` 与 `sourceRefId`。当前 `QueryController` 只按 `courseCode` 读 SeedData；仓库 Java 源码中未发现 offering snapshot 导入 Controller/Service。因此契约定义与当前 B 实现尚未接通。

交接给 B 时请保留这些边界：

1. 历史来源标记为 `SHUOSC_HISTORICAL_PUBLIC`，不可改标为 `BROWSER_SNAPSHOT`、`SYNTHETIC` 或 `VERIFIED`。
2. `teacherKey` 为 null；`upstreamTeacherId` 仅作来源追溯，不能当作稳定教师身份。
3. 缺失的 calendar 保持未知；B 不应从历史数据猜测校历或节次上限。
4. `parseStatus=UNPARSED`，`meetings=[]`；Java 应重新解析 `meetingTextRaw`，不能以候选文件中的解析状态代替服务端判定。
5. 当前 OfferingImport Schema 尚不能直接接收该历史 staging 数据，当前 Java offering 导入/快照链路也未由本次 A 工作实现。B 可按本交接数据适配；若需改公共契约，应另行同步 Schema、fixture、提供方、消费者和 TRD。

本次已完成 A 侧来源审计、历史候选映射及三类虚构样例。Issue #22 的 B 消费者验收项仍需 B 实际确认；本次不修改公共 Schema、不把历史资料伪装成可导入数据，也不声称真实班次已通过 Java 核验。

## 5. 检查记录

- 本机历史副本 SHA-256 与固定审计记录相符；解析为 4,822 条 `courses` 记录，字段集合与本文件映射表一致。A1 工作簿精确匹配结果为 8 条路径、460 个课程号行、101 个不同课程号、381 条匹配历史记录、43 个匹配课程号、23 个多班次课程号。所有匹配行均有 `teacherId`；派生 classId 无空值、无重复。
- 对来源仅读取已发布 JSON 固定文件；未运行爬虫、未登录学校网站、未使用学校凭据。
- 本次新增的三个 JSON 样例由 `scripts/check_contracts.py` 按 `OfferingImport` Schema 校验；Java 的时间解析与冲突判定仍须由 B 复核。
- 原始历史 JSON 与 A1 原始工作簿均在 `data/raw/`，逐条派生结果和私人审计表在 `data/private/`；这些目录均被忽略，不作为公开交付文件。逐条候选结果使用 `parseStatus: UNPARSED` 和空 `meetings` 表示尚未解析；顶层 `calendar` 明确为 null（来源未提供），并采用 schema 不支持的历史 `sourceKind`，**不是**可直接提交的 `OfferingImport`。
