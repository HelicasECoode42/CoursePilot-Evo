# A 模块：数据导入与资料整理（业务说明与 TRD）

负责人：**JiangYiLin-Q121**。先读[团队总览](../15-team-baseline-and-batches.md)，再读本页业务功能，实施时查下半页接口与规则。当前是设计与合同，尚未实现；排期见[本期任务](../19-delivery-plan.md)。

## 先理解你要交出的完整模块

让项目能使用正确、统一、有来源的培养计划、已修课程、评价和班次参考资料。队友应能知道每条数据来自哪里，哪些资料可以使用，哪些需要补充。

举例：一张培养计划表里有前导零课程号、小数学分和看不懂的备注。你要把课程与要求读出来、指出无法解释的行，并只把检查通过的数据交给 Java 保存。

## 完整业务功能清单

| 功能编号 | 功能 | 具体需要完成什么 | 本期任务或后续期 |
| --- | --- | --- | --- |
| A-F1 | 读取培养计划 | 整理选定路径的全部课程、必修和类别学分要求，保留建议学期及原表位置。 | A1 |
| A-F2 | 检查并发布资料 | 指出缺失、重复冲突和无法解释的规则；合法资料可以导入，重复导入可复用，失败时说明原因。 | A1、A2 |
| A-F3 | 整理已修课程输入 | 定义完整、不完整、重修等已修记录的输入格式和样例，让页面与 Java 对同一份资料有一致理解。 | A3 |
| A-F4 | 整理教师评价 | 按课程、教师、修读学期整理有限评价，保留来源、维度和无法匹配的情况。 | A3；第六周补覆盖 |
| A-F5 | 准备班次与时间样例 | 提供时间原文和独立预期，覆盖单双周、离散周、节次边界和未知格式，标清模拟来源。 | A3；第六周补反例 |

上表是整个模块范围。A1/E2 等是[排期草案](../19-delivery-plan.md)的业务任务编号，尚不等于 GitHub Issue 编号；后续期功能届时拆任务。本期未覆盖的功能仍属于模块完整交付。

## 谁交给你、你交给谁

输入来自授权培养计划与受控记录/评价输入。交给 mira-xu 的是标准化资料、来源和异常；交给 amorfatiii 的是独立核对依据与测试样例。收到 Java 的导入结果后，你负责核对资料是否正确落地。

## 你的责任边界

Java 保存数据并负责学分/时间判定；Agent 理解需求；网页收集和展示。你拥有 importer、输入格式及来源映射；XLS 文件入口由你实现，身份组件与发布事务由 mira-xu 提供。时间原文交唯一 Java 解析器处理。

## 整个模块怎样算完成

一条完整路径能正确导入、重复导入并定位失败；已修/评价/班次输入被消费者使用；原始资料与公开虚构样例分清。 每项功能要有实现、实际消费者调用和正常/异常/未知的证据。权限、错误恢复等检查贯穿各功能，模拟与真实能力分别说明。

## 实现参考与技术约束

下面保留现有技术方案。业务功能是交付目标；组件、接口、函数与测试是实现这些功能的手段。字段以 contracts 为准，不在业务功能表里复制一套字段。

| 项 | 内容 |
| --- | --- |
| 责任 | JiangYiLin-Q121，模块 A |
| 技术 | Java 21、Apache POI、JSON Schema、JUnit 5 |
| 所有权 | java-environment/importer、输入模板、黄金样例、来源映射 |
| 输入 | 本地 xls、受控已修/评价输入、插件静态字段研究 |
| 输出 | Curriculum draft、ImportResult、ReviewImport、原始班次 fixture |
| 当前状态 | 无导入服务；原始文件不进入公开仓库 |

### 1. 需求与边界

A-01：一个选定培养路径可重复导入，课程号保留零、学分和规则可追原表。A-02：未知格式自动阻断。A-03：有限评价输入按课程教师学期匹配。A-04：给时间解析提供完整原文/对照样例。

A 不拥有学分审核、时间冲突、模型推理或生产页面。B 维护唯一 TimeParser，A 在规范化时使用该接口，不能重写一套 JS/AI 时间解析。原插件只做静态研究，不原样运行其点击/请求逻辑。

### 2. 组件结构

```mermaid
flowchart LR
  F[xls / 受控 JSON] --> G[InputGuard]
  G --> X[WorkbookReader]
  X --> N[CurriculumNormalizer]
  N --> C[RuleTemplateCompiler]
  C --> Q[ImportQualityGate]
  Q --> P[PublishPort，B 的事务入口]
  Q --> I[ImportIssue]
  R[评价输入] --> M[ReviewMatcher]
  M --> P
  T[原始时间 fixture] --> TP[B TimeParser Port]
```

目录：importer/input（大小/格式）、excel（受控表型读取）、normalization（字段映射）、rules（模板编译）、quality（门槛）、port（发布接口）；黄金样例放模块 test/resources，公开 fixture 仅虚构数据。

### 3. 接口与输入约束

Java `POST /api/v1/curriculum-snapshots/import`，multipart fields= schemaVersion、trackId、file；Service Key+Admin Key。10 MiB 上限、仅 .xls、检查文件签名，不信任后缀。文件路径/输出目录由服务端生成，接口不能接受任意 sourcePath。

`WorkbookReader.read(stream, trackId) -> CurriculumSnapshotDraft`；`RuleTemplateCompiler.compile(rawRule, templateVersion) -> CompiledRule|ImportIssue`；`ImportQualityGate.check(draft, baseline) -> publishable + issues`；`PublishPort.publish(draft, inputHash, importerVersion) -> ImportResult`。

| 字段 | 规则 |
| --- | --- |
| courseCode | 字符串；保留前导零，不能同名合并 |
| credits | BigDecimal；最多两位小数，未知复合数值不硬拆 |
| suggestedTerm | 可空，仅建议，不构成本学期硬要求 |
| SourceRef | refId/kind/snapshotId/locator/capturedAt；locator 保留 sheet/row/column |
| compiled rule | 白名单受控表达式；备注不能 eval 成代码 |
| hash/version | 内容摘要+路径+importerVersion 构成自然幂等键 |

不执行 Excel 公式、宏或外链。受控格式中公式仅读取有依据的缓存值；不能获取的值标未知。左右并列表、实践表与组合编号在模板内明确，不靠 LLM 猜出缺失单元格。

### 4. 导入发布时序

```mermaid
sequenceDiagram
  participant I as 本地管理调用
  participant A as Importer
  participant Q as QualityGate
  participant B as PublishService
  participant DB as MySQL
  I->>A: file + track + admin auth
  A->>A: 文件类型/大小/hash/模板检查
  A->>Q: draft + baseline
  alt 未知模板/总计不一致
    Q-->>A: issues，禁止发布
    A-->>I: REJECTED，snapshotId=null
  else 校验通过
    A->>B: publish(draft, naturalKey)
    B->>DB: 单事务写快照/课程/规则/来源
    alt 相同内容已发布
      DB-->>B: existing snapshot
      B-->>I: PUBLISHED，reused=true
    else 新版本
      DB-->>B: commit
      B-->>I: 新 snapshotId
    end
  end
```

首个模板做独立基线对照；之后同模板自动门槛发布。没有“人工批准忽略未知”的绕过接口。事务失败无 PUBLISHED，无半张快照。

### 5. 评价与班次适配

ReviewImport Schema 为唯一格式：notes≤200、excerpt≤1500 字；sourceUrl 仅 http/https，teacherKey/termId 未知为 null。course/teacher/term 不能可靠对齐则 UNVERIFIED，不用文本相似度自动确认为教师事实。原文定位或有限摘要按授权范围保留。

浏览器原始导出格式见旧 snapshot Schema，转换到 OfferingImport：termId、calendar、sourceKind、capturedAt、offerings。sourceKind 由输入说明来源，sourceValidation 由 B 的后台验证流程控制；上传者不能声明 VERIFIED。meetings/parseStatus 客户端值仅供对照，B 重新解析 raw。

```mermaid
sequenceDiagram
  participant A as Adapter
  participant P as B TimeParser
  participant B as OfferingImportService
  A->>P: meetingTextRaw + calendar
  P-->>A: normalized meetings / parse status
  A->>B: 标为 SYNTHETIC 的样例输入
  B->>P: 重新解析并比对
  B-->>A: import issues / snapshot
```

### 6. 异常、调试与安全

| 场景 | 返回/处理 |
| --- | --- |
| 未知表型/备注 | UNKNOWN_RULE/IMPORT_REJECTED；不发布 |
| 重复课程冲突/总计错误 | 导入 issue，定位字段与 sheet/row |
| 重导 | 复用自然键，不插重复版本 |
| 超大/错误类型/路径试探 | 413/422，清理临时文件 |
| 存储失败 | ERROR/503，事务回滚 |

日志：requestId、input hash、模板版本、行计数、issue code，不记录完整表、成绩或上传路径。资料来自不可信文件时不能影响系统 Prompt、shell 或 SQL。私有原始输入在 gitignore 下，测试公开虚构 fixture。

### 7. 验收与批次

课程周与业务任务见[本期排期](../19-delivery-plan.md)。完整功能按上表逐项验收。

必须覆盖：前导零、合并/并列表、重复冲突、学分总计、未知备注、公式无缓存、重导幂等、发布中失败、未匹配教师、缺学期、超限文件。不需要为每个 getter 写镜像测试，重点测会改变结论或发布状态的风险。

### 契约变更与完成标准

字段以 [contracts](../../contracts/README.md) 为真源，行为以 [公共契约](../04-infrastructure-workflow.md) 为准。提交提供者/消费者 DTO、正反例和受影响测试；Schema 破坏性变更升版本，不能边跑 Benchmark 边改。调试和提交要求见 [工程规范](../16-engineering-and-debugging.md)。

任务完成至少包含：实现目录、输入/输出、正常和失败证据、限制；fixture 不算真实接入，HTML 不算生产前端，手工改 Prompt 不算 RSI。每次 PR 使用仓库模板自查，接口 PR 由相邻模块复核。
