# Java 核验服务做了什么

`java-environment/`：Spring Boot 3.4.1、Java 21、Spring Data JPA、H2 文件库，端口 8081，默认只监听本机。

**一句话**：Java 是整个系统的"事实与规则中心"。课程、课表、学业记录、评价都存在这里；上课时间只在这里解析；学分够不够、时间冲不冲突，只在这里判定。Java 不调用 AI。AI 给出的推荐，最后都要交给 Java 核验。

规模：主代码 96 个类、约 8100 行；测试 28 个文件、约 5700 行、267 个 `@Test`。

## 1. 在整个系统里的位置

```mermaid
flowchart LR
  S[学生浏览器] --> W[Vue 网页]
  X[浏览器插件<br/>读取学校学业情况] --> W
  W --> P[Python 网关与规划器]
  P -->|调用模型| M[(大模型)]
  P -->|带服务密钥的 HTTP| J[Java 核验服务]
  J --> DB[(H2 数据库)]
  subgraph Java 负责
    J
  end
```

- 网页只调用 Python；Python 通过带类型的 HTTP 接口向 Java 取数据、请求核验。
- 每个请求都要带服务密钥 `X-Service-Key` 和学生身份 `X-Subject-Id`。数据按学生隔离，访问别人的数据一律返回 404，不暴露数据是否存在。

## 2. 代码结构

| 包 | 内容 | 代表类 |
|---|---|---|
| `web` | 13 个 Controller、过滤器、统一返回格式、异常处理 | `QueryController`、`PlanValidationController`、`ServiceKeyFilter`、`RequestSizeLimitFilter`、`SubjectGuard`、`ApiExceptionHandler`、`Envelope` |
| `application` | 业务服务与算法 | `TimeParser`、`ConflictChecker`、`PlanValidationService`、`OfferingImportService`、`OfferingVerificationService`、`SchoolProgressService`、`SchoolReport`、`AcademicLedger`、`AuditResultAssembler` |
| `domain` | 领域值对象 | `MeetingTime`、`ConflictResult`、`AuditOutcome` |
| `persistence` | 16 个实体、15 个 Repository | `CurriculumSnapshot`、`CourseOffering`、`SchoolProgressSnapshot`、`OfferingVerificationAudit`、`CurriculumUnmodeledRule` |
| `importer` | 培养方案 Excel 导入器 | `A1WorkbookImporter`、`XlsxInputGuard`、`ImportModels` |

## 3. 接口一览（均在 `/api/v1` 下）

| 类别 | 接口 |
|---|---|
| 查询 | `GET /courses`、`GET /offerings`、`GET /curriculum-snapshots`、`GET /offering-snapshots`、`GET /reviews/search`、`GET /teacher-course-options`、`GET /career-directions` |
| 导入（需管理员密钥） | `POST /curriculum-snapshots/import`（Excel）、`POST /offering-snapshots/import`（课表）、`POST`/`DELETE /reviews/import`（评价） |
| 课表人工核验 | `POST /offering-snapshots/{id}/verification` |
| 学业进度与记录 | `PUT`/`GET /school-progress`、`GET`/`POST /academic-records` |
| 核验 | `POST /requirements/audit`（学业核对）、`POST /plans/validate`（方案核验） |

## 4. 五条核心流程

### 4.1 培养方案导入：Excel 进库

```mermaid
flowchart TD
  A[上传培养方案 .xlsx] --> B{管理员密钥 · 仅本机 · 不超过 10MB}
  B -->|不通过| R1[拒绝]
  B --> C[XlsxInputGuard 安全读取<br/>防压缩炸弹]
  C --> D[A1WorkbookImporter.prepare<br/>识别工作表 · 校验模板标题]
  D --> E[逐行解析课程<br/>课程号、名称、类别、学分、建议学期]
  E --> F[展开课程号区间<br/>01014125~127 展开成 3 门]
  F --> G{学分能确认吗}
  G -->|不能| H[学分记为空，标 CREDITS_UNSPLIT]
  G -->|能| I[正常入库]
  E --> J[说明行分三类：<br/>需人工确认 / 仅说明 / 排除]
  H & I & J --> K[按内容算 SHA-256 幂等键<br/>同一文件重复导入只入库一次]
  K --> L[发布快照，来源标"未核验"]
```

数据清洗规则：
- 占位课程号（如体育 `xx`）记为 `COURSE_CODE_PENDING`，不编造课程号。
- 学分没法拆分的区间，学分留空，不平均分摊。
- "毕业前修一门全英语课"这类规则，系统建模不了就记为"需人工确认"，不会当作已经满足。

### 4.2 课表导入：不信任客户端，Java 自己解析时间

```mermaid
flowchart TD
  A[课表 JSON：6431 个教学班] --> B{结构校验<br/>字段、枚举、最多 7000 个班<br/>班号不能重复}
  B -->|不通过| R[400 拒绝]
  B --> C[逐班用 TimeParser 重新解析 meetingTextRaw]
  C --> D{解析结果}
  D -->|成功| E[PARSED]
  D -->|超出规格| F[INVALID]
  D -->|看不懂/被截断| G[UNPARSED，保留原文，不丢弃]
  C --> H[客户端自带的解析结果<br/>一律忽略，并记录提示]
  E & F & G --> I[按内容生成快照编号<br/>同内容重复导入时复用]
  I --> J{来源}
  J -->|模拟| K[SYNTHETIC]
  J -->|学校 PDF / 浏览器抓取| L[UNVERIFIED，等待人工核验]
```

### 4.3 TimeParser：全系统唯一的时间解析器

输入示例：`星期一第9-11节{1-8周};星期二第7-8节{1-8周}`

```mermaid
flowchart LR
  A[原始文本] --> B[去空白]
  B --> C[正则逐段匹配<br/>星期/周 + 第a-b节 + 周次]
  C --> D[节次：支持 3-4,7-8 多段]
  C --> E[周次：1-16周、1周,5周、单双周]
  C --> F[段间分隔符：逗号 分号 顿号]
  D & E & F --> G{还有没认出来的文字吗}
  G -->|有| U[UNKNOWN 并给出原因]
  G -->|没有| O[若干 MeetingTime<br/>星期、起止节、周集合]
```

- 防御性上限：节次不超过 64、周次不超过 60、段数不超过 40，超出返回 `OUT_OF_CONTRACT`。
- 看不懂的时间不会被当成"没有冲突"。

### 4.4 课表人工核验：上传者不能自己说了算

```mermaid
flowchart TD
  A[核验请求：核验人、上传人、抽查条数、错误条数、样本文件指纹] --> B{管理员密钥}
  B --> C{是模拟数据吗}
  C -->|是| X[422 模拟数据不能核验]
  C --> D{核验人和上传人是同一人吗}
  D -->|是| Y[422 拒绝]
  D --> E{抽查至少 30 条，且错误率不超过 2%}
  E -->|是| V[VERIFIED]
  E -->|否| N[REJECTED]
  V & N --> Z[写入审计表 offering_verification_audit]
```

### 4.5 学业核对与方案核验

```mermaid
flowchart TD
  subgraph 学业核对
    A1[插件导入学校学业进度<br/>45 个类别、127 门课] --> A2[SchoolProgressService 保存<br/>幂等、限制条数]
    A2 --> A3[SchoolReport：同名类别取最上层<br/>课程沿父类别向上归类]
    A3 --> A4[AcademicLedger：已通过才计学分<br/>在读算 0 分，单独列出]
    A4 --> A5[AuditResultAssembler：<br/>有学校数据的类别以学校为准<br/>读全则认定记录完整]
  end
  subgraph 方案核验
    B1[方案：课程与班次] --> B2{是本人的记录吗}
    B2 -->|否| B9[404]
    B2 --> B3[ConflictChecker：两两比较时间与周次]
    B3 --> B4[课表分项：班次是否属于本学期课表、时间冲突、必避时段]
    B1 --> B5[毕业要求分项：学分上限、需人工确认的规则]
    B4 & B5 --> B6[各分项：违规→不通过；有未知→无法确认；否则通过<br/>总结论取两项中较差的]
  end
```

关键原则：**未知永远不算通过。** 课表没有核验之前，冲突和必避时段照常按解析出的时间检查，并给出"冲突 / 不冲突（按未核验课表）"的预览，但总结论保持"无法确认"。

## 5. 安全与可靠性

| 措施 | 实现 |
|---|---|
| 服务鉴权 | `ServiceKeyFilter`：所有请求必须带服务密钥，不按路径放行；没配置密钥时直接拒绝服务 |
| 管理操作 | 导入、核验、删除需要另外的管理员密钥，采用常量时间比较 |
| 数据隔离 | `SubjectGuard` 加归属检查：别人的记录返回 404 |
| 请求大小 | `RequestSizeLimitFilter`：JSON 默认上限 2 MiB，超出返回 413 |
| 网络暴露 | 默认绑定 `127.0.0.1`；培养方案导入还要求请求来自本机 |
| 幂等 | 导入按内容哈希去重，重复提交不会产生重复数据 |
| 测试 | 267 个单元测试和接口测试，CI 每次提交都会运行 |

## 6. 哪些不是 Java 做的（如实说明）

- 把学校 PDF 课表转成 JSON：`scripts/convert_timetable_pdf.py`（Python 脚本）。Java 接收后重新校验、重新解析。
- 读取学校教务页面：浏览器插件（JavaScript）。
- 推荐课程、生成理由、对话：Python 规划器调用大模型。Java 不接触模型。
