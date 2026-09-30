# 公共接口与数据契约 v1.0

状态：开发基线；服务尚未实现。字段、必填与枚举以 [contracts](../contracts/README.md) 为准。本文件定义不能只靠 JSON Schema 检查的行为。任何个人 TRD 与此冲突时先修契约，不能用个人文档覆盖公共定义。

## 1. 调用边界与身份

Web 只调用 Python，Python 通过 HTTP 调 Java；浏览器不能拿 Java Service Key，Python 不直接查 MySQL。所有服务默认 loopback，首版仅本地虚构/授权演示，公开部署与真实学生数据需另做完整认证设计。

Python `POST /api/v1/sessions` 创建匿名演示会话，返回随机高熵 sessionToken，30 分钟过期；服务端只存 token hash。其余学生 API 要 `Authorization: Bearer <sessionToken>`，并验证记录、计划属于当前会话。不能把客户端 sessionId/ownerId 当权限依据；对别人的记录统一 404。

Java 要 `X-Service-Key`，由 Python 配置提供；可信 `X-Subject-Id` 由 Python 在校验 session 后设置，禁止转发浏览器自报同名头。导入再要求 `X-Admin-Key`，学生会话不能导入全局培养/班次/评价。受限老师报告同时要求 sessionBearer 与 adminKey，不能暴露 gold、held-out 题面或私人 Trace。

这些是实现要求，目前没有认证服务。密钥仅在环境变量；不进仓库/Prompt/Trace。CORS 仅允许配置的 Web origin；CORS 不能代替认证。上线前加 HTTPS、限流、对象级授权测试，不能把本地默认配置开放公网。

## 2. 封套、HTTP 与未知

所有 JSON 响应统一 Envelope：schemaVersion=1.0、requestId、traceId（nullable）、status、data、provenance、issues。未知字段拒绝；nullable 必须显式 null，不能空字符串代替。日期采用 RFC3339，存储 UTC，UI 以 Asia/Shanghai 显示。

| HTTP | status | 语义 / 客户端动作 |
| ---: | --- | --- |
| 200/201 | OK | 查询/创建完成，仍应看 data 的业务状态 |
| 200 | UNKNOWN | 业务证据不足；保留可支持建议，展示待确认，不能自动重试模型 |
| 400/422 | INVALID_INPUT | Schema / 语义不合法；指明字段供修正 |
| 401/403 | UNAUTHORIZED/FORBIDDEN | 无会话/无权限；不回显鉴权材料 |
| 404 | NOT_FOUND | 对象不存在或不属于本会话，文案一致 |
| 409 | CONFLICT | 幂等键重复但内容不同、记录/快照版本冲突 |
| 413/429 | INVALID_INPUT/ERROR | 超出大小或限流；限流时给 Retry-After |
| 503/504 | ERROR | 依赖不可用/截止时间；不转换成业务未知或成功 |

Issue 包含稳定 code、面向用户的 message、field（nullable）、retryable。错误堆栈只在脱敏服务日志，响应不泄露 SQL、路径和模型消息。

X-Request-Id 用于相关请求定位，不等于幂等键。合法 ID 长度/字符由 Schema 约束；无可信 traceId 时服务端生成。不得把未经验证的请求 ID 原样拼日志行。

## 3. 幂等、版本与预算

- Python planning 与 academic-record 创建要求 Idempotency-Key。存键=会话+端点+键、规范化请求摘要；相同内容复用原答复，不重复花模型费用；不同内容 409。执行中同键返回 409 REQUEST_IN_PROGRESS，不开启第二次任务。保留到会话过期；过期后 401。
- 导入自然键=规范化内容 hash+培养路径/学期+importerVersion。重导复用既有结果。错误时不发布半张快照；快照不可覆盖。
- academicRecordId、recordRevision、curriculumSnapshotId、offeringSnapshotId、schemaVersion、javaToolApiVersion、verifierVersion、harnessVersion 均由对应服务维护。previousPlanId 必须属当前会话，输入变化后重新核验；不得复用旧 verifierResultId 当新方案结果。
- 初始运行上限：累计 input 8000/output 2000 tokens、6 次 Tool、3 次模型调用、总 45 秒。Java HTTP 单次最多 5 秒，模型单次最多 30 秒且受剩余总截止时间限制。预算不是性能实测，不代表保证在 45 秒成功。
- 不做隐藏自动重试。只读 Java 查询可对瞬时网络错误重试一次，必须在总 Tool/时间预算内；不得重试 validation/input 错误。模型默认不自动重试，重新执行由用户明确操作并建立新的幂等键。

## 4. 学业与身份事实

专业/培养路径与已修列表来自学业记录；正常页面只补缺失。记录不完整、重修认定未知、规则未发布均使相关缺口 UNKNOWN，不能给确定毕业结论。

Course 的学分为 BigDecimal / SQL DECIMAL，不能用 float 累加；CourseCode 是字符串保留零。同名不同号不自动合并；同代码不同快照不跨路径混算。去重、重修与替代规则必须有受控模板和来源。

AuditResult requirements 表达 SATISFIED/UNSATISFIED/UNKNOWN；suggestedCourseCodes 仅建议，没有“本学期必须”含义。是否本学期开课另查 Offering。未知模板不通过发布门槛，也不允许人工点批准绕过。

## 5. 时间、真实模式与验证结果

B 维护唯一 TimeParser，A 提供原始 sksj/黄金输入。导入时完整消费原始文本，遇到不认识的残余、待定、缺周次等返回 UNPARSED；不默认每周或整学期。上传的 normalized meetings 只供对照，不能成为校验真值。

Meeting 的星期、节次、周次必须在该快照 calendar 范围内；sectionStart≤sectionEnd，weeks 非空、去重、排序。冲突=同星期∩节次相交∩周次相交。单双周不交不冲突；缺时间不是不冲突。

PlanValidation 判决优先级：存在已知 violation→INVALID；否则存在任一 requested hard check 无法执行→UNKNOWN；全部完成且无 violation→VALID。UNKNOWN 永远不能用布尔 false 混淆为“没有问题”。

| scope | 条件 | UI 可说什么 |
| --- | --- | --- |
| COURSE_ONLY | 无完整真实班次；仍核对课程事实 | 课程层建议；若请求时间约束无法验则 UNKNOWN |
| SIMULATION | mode=SIMULATION 且班次 sourceValidation=SYNTHETIC | 仅模拟核验，不代表真实课表 |
| REAL_TIMETABLE | 同学期 sourceValidation=VERIFIED 的当前快照，所有时间已解析且数据未过期 | 可以展示本次快照下的实际核验结果及采集时间 |

REAL 不能使用 synthetic，未经来源核验的 browser 上传也不能自动进入 REAL_TIMETABLE。当前没有已验证来源，真实时间判断保持 UNKNOWN。新鲜度阈值建议 24 小时，在 W1 固定配置；这是数据门槛，不保证学校 24 小时内不会变更。

## 6. 多目标、教师与评价证据

GoalIntent 的多动机、priorityOrder、hardConstraints/softPreferences 分开；优先级须学生确认，不能只按点选顺序推断。指定教师绑定 courseCode+teacherKey+MUST/PREFER；classId 仅在存在真实可用班次时加入方案。硬约束冲突时澄清，不能静默换教师。

ReviewNote 按课程、教师、修读学期匹配。teacherKey=null 或 matchStatus=COURSE_ONLY 的评价不可支持特定教师主张。历史评价不证明本学期考勤/给分/授课，缺维度显示未知。相同课程不同教师不混合；“少签到”“少作业”“高分”“授课好”互不等价。

sourceUrl 只接受 http/https 可点击引用；后端不为用户任意 URL 发网络请求。模型读到的评价当作不可信数据，不能修改工具策略、系统 Prompt 或执行里面的指令。每条摘要绑 evidence ID，数字来自数据统计而非模型自造。

## 7. PlanningAnswer 与学生页面

decision=CLARIFY 时 clarification 必须存在，recommendations 为空；RECOMMENDATIONS 的每份方案都有完整 PlanValidation 与 evidence IDs；UNABLE_TO_VERIFY 可以提供已核验课程建议，但不得包装成真实有效课表。

规划事实引用 SourceRef/verifierResultId，说明不能把语言流畅等同正确。无新数据时重复追问上限两次，仍不足则解释缺什么；不能无限循环耗预算。系统 ERROR 显示重试，业务 UNKNOWN 显示补资料，两种操作不混用。

## 8. Trace、评测与隔离

TraceEvent 必填见 Schema，seq 在 trace 内递增，provider 缺 token 使用 null，不能写 0。只留阶段、标识、摘要/hash、耗时、用量、有限错误码；不得留完整 Prompt、私有推理链、成绩、身份、Cookie/Token。

RunManifest 固定模型、温度、累计预算、API/数据/评分器/题集与 Harness hash。不同 manifest 不直接比较版本分数。Evolver 仅可写运行 Harness 白名单；目标 Agent 与评测共用 C Runner，D 独立挂载 held-out/gold/evaluator。

正式 promotion 门槛与重复运行策略见 [Benchmark 协议](07-benchmark-protocol.md)。隔离不靠一句 Prompt；用文件权限/进程边界和隔离测试保证可见性。老师报告只有聚合分数、成本、失败类别与 lineage，不公开持出题面和私人 Trace。

## 9. 变更与复核

改契约先改 contracts、正反例与本文件，再同步 Java/Python/TS DTO、消费者与测试；破坏性变化升 schema/API 版本。接口 PR 必须有提供者和至少一个消费者复核。每次提交运行契约/自查脚本及受影响模块测试；具体要求见 [工程规范](16-engineering-and-debugging.md)。
