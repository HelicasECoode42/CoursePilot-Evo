# 第五至第八周交付草案（边界修订版，待核对）

第五周交付可实际操作的核心规划闭环，第六周完成功能与实验机制，第七周收敛可靠性，第八周交付。任务范围建议不等于已派发；周次以课程周为准，不另维护截止日期。

负责人：数据 JiangYiLin-Q121、Java mira-xu、Agent goat-yang、评测 amorfatiii、Web/队长 HelicasECoode42。进度只在 [Project](https://github.com/users/HelicasECoode42/projects/1) 更新；本文保存范围和验收依据。

## 四周目标与阶段验收

| 周次 | 必须交付 | 验收门槛 |
| --- | --- | --- |
| 第五周 | 完整单培养路径导入/Audit；真实模型候选与 Java 核验；网页输入→澄清→结果→改条件重规划；有限教师评价；24 例和 v0；集成 CI | 用真实 Web/Python/Java/MySQL/模型演示正常规划、缺班次 UNKNOWN、模拟冲突取舍及 replan；各模块单独 mock 演示不能替代周验收 |
| 第六周 | 首版功能完整、独立受限老师报告页；评价/职业内容与复杂分支补齐；案例扩至目标每组 5+5；Evolver/隔离 gate/回滚/lineage，两轮候选决策 | 学生主线与实验报告均可演示；至少两轮真实决策（可 rejected）；跨案例证据不足则明确为未完成实验条件，不伪造成功；周末冻结功能 |
| 第七周 | 全量回归、故障注入与恢复、权限/幂等/并发/预算边界；冻结条件下重跑基线和候选；报告/演示初稿 | 主流程故障和已知错误核验清零；P0/P1 全部验收关闭，剩余 P2 经队长明确延期；新环境复现与全链路彩排通过 |
| 第八周 | 提交包、演示、报告和限制说明定稿；只修发布阻塞 Bug | 第七周已有可提交版本；第八周不依赖新增大功能或首次运行实验 |

真实班次目前不可核验：课程层建议保留时间 UNKNOWN，模拟冲突显著标记。加快实现不能把模型猜测、模拟输入或无失败的空 CI 当可用性证据。

## 首期节奏与任务总览

每人三项有边界的交付，共 15 项，加 G0 一项共同确认。可拆成多个小 PR，不要求一个大 PR 交齐。标题以“动作＋对象＋结果”命名，卡片正文必须有输入、负责范围、输出/交接、不包含、依赖和验收。

- 开工时：G0 明确少量悬而未决的传输问题；各人同时建工程、DTO、模块测试，不能以等待 G0 为由整周停工。
- 周中联调：A/B 能提供完整路径与真实查询/Audit；C 的真实模型和 Java 客户端可调用；E 用服务返回展示；D 已交种子和 CI 启动入口。
- 周末验收：完成规划/澄清/核验/replan 全链路、首版 v0 与故障用例。没有通过就记录未完成与阻塞，不能将 mock 偷换为正式验收。

| ID | 交付结果（详见下文卡片） | 负责人 | 主要复核人 |
| --- | --- | --- | --- |
| G0 | 冻结规划闭环请求、澄清回传及 Trace 样例 | HelicasECoode42 | goat-yang |
| A1 | 将一个完整培养路径的 XLS 转成可追溯 draft | JiangYiLin-Q121 | mira-xu |
| A2 | 接通 XLS 导入入口并验证重导复用与失败回滚 | JiangYiLin-Q121 | mira-xu |
| A3 | 交付已修记录、课程教师评价和模拟班次输入包 | JiangYiLin-Q121 | mira-xu |
| B1 | 交付 MySQL 发布事务、记录存储和事实查询 API | mira-xu | JiangYiLin-Q121 |
| B2 | 按完整培养路径计算必修与类别学分核对结果 | mira-xu | amorfatiii |
| B3 | 解析模拟班次并返回 VALID、INVALID、UNKNOWN 核验 | mira-xu | goat-yang |
| C1 | 接通匿名会话、学业记录和事实查询的 Python 网关 | goat-yang | HelicasECoode42 |
| C2 | 用真实模型生成候选并强制调用 Java 核验 | goat-yang | mira-xu |
| C3 | 实现澄清续问、改条件重规划和有界失败处理 | goat-yang | HelicasECoode42 |
| D1 | 完成四组各 3+3 案例与独立答案隔离 | amorfatiii | mira-xu |
| D2 | 把真实服务规划链路与浏览器冒烟加入 CI | amorfatiii | HelicasECoode42 |
| D3 | 用生产 Runner 跑四组 v0 并输出逐例质量成本 | amorfatiii | goat-yang |
| E1 | 实现一次一问、多目标分支和返回保留的 Vue 页面 | HelicasECoode42 | goat-yang |
| E2 | 接通记录、学业核对、规划结果与修改条件重规划 | HelicasECoode42 | goat-yang |
| E3 | 实现课程教师搜索、必须/偏好选择及来源详情 | HelicasECoode42 | JiangYiLin-Q121 |

## 交接与唯一所有权

- A1 编译 draft，A2 接 XLS 入口，B1 管认证组件/发布端口/事务。A2 不写库；B1 不复制 XLS 读取器。
- A3 交结构化输入；B1 管记录/评价/班次的存储和查询；B2 唯一计算学分；B3 唯一解析时间并核验候选。
- C1 管网关，C2 管同一生产/评测 Runner，C3 管澄清/replan/幂等/预算。C 不自算 Java 事实。
- D1 管案例/真值隔离，D2 管组合启动/CI，D3 管 v0/评分与报告。各服务自身启动/健康检查和业务修复仍归模块作者。
- E1 管输入/状态，E2 管主流程调用和结果，E3 管课程教师选择/评价详情。E 只消费 Python API。
- 队长验收跨模块交付；主要复核人外的接口提供者/消费者按影响补充审批。作者不可自批。

## 首期任务卡片

### [G0 草案] 冻结规划闭环请求、澄清回传及 Trace 样例

待队长与成员核对的第五周任务草案；主要负责人：HelicasECoode42；主要复核人：goat-yang。

#### 输入
现有 contracts、公共契约和五个模块 TRD

#### 本任务负责
在第五周首次联调前明确澄清答案传输、academicRecordId 获取、priorityOrder 确认；约定 importer→PublishPort、Runner→TracePort；每个对象指定提供方和消费方。

#### 输出与交接对象
contracts 的正反例与决策记录；五方可据此并行开发。

#### 不包含／他人负责
不实现五个模块；不重新设计已经明确的字段；不把接口会议拖成整周前置。

#### 依赖与开工方式
无；A/B/C/D/E 同日提交各自边界问题。

#### 验收条件
- [ ] 完整请求能经 Schema 校验，CLARIFY/UNKNOWN/INVALID/ERROR 都有示例。
- [ ] 接口提供者及实际消费者在 PR 确认字段；争议有决定、负责人和影响范围。
- [ ] 提供实现 PR、检查命令/结果和关联模块实际调用证据；真实调用、mock 和未完成项分别标明。

[统一契约](https://github.com/HelicasECoode42/CoursePilot-Evo/blob/main/docs/04-infrastructure-workflow.md)

### [A1 草案] 将一个完整培养路径的 XLS 转成可追溯 draft

待队长与成员核对的第五周任务草案；主要负责人：JiangYiLin-Q121；主要复核人：mira-xu。

#### 输入
选定路径授权 XLS、独立核对的课程/学分/规则基线

#### 本任务负责
实现 importer 的读取、规范化、受控规则编译与 QualityGate；覆盖该路径完整必修清单和类别学分要求；保留 sheet/row/column。

#### 输出与交接对象
CurriculumSnapshotDraft、ImportIssue、虚构黄金输入，交 A2/B1；提供启动及模块检查。

#### 不包含／他人负责
不写数据库、Audit 或时间解析；不扩展其他专业；未知规则不猜测、不发布。

#### 依赖与开工方式
G0；路径和基线由 JiangYiLin-Q121 与 mira-xu 核对。

#### 验收条件
- [ ] 整条路径课程数、课程号、学分与独立基线一致，前导零和小数学分保留。
- [ ] 未知备注、重复冲突、无缓存公式和总计不符均有定位并阻断发布。
- [ ] 提供实现 PR、检查命令/结果和关联模块实际调用证据；真实调用、mock 和未完成项分别标明。

[模块 TRD](https://github.com/HelicasECoode42/CoursePilot-Evo/blob/main/docs/trd/a-data.md) · [统一契约](https://github.com/HelicasECoode42/CoursePilot-Evo/blob/main/docs/04-infrastructure-workflow.md)

### [A2 草案] 接通 XLS 导入入口并验证重导复用与失败回滚

待队长与成员核对的第五周任务草案；主要负责人：JiangYiLin-Q121；主要复核人：mira-xu。

#### 输入
A1 draft、B1 PublishPort 和 Java 服务

#### 本任务负责
拥有 curriculum-snapshots/import 的 multipart 接收、文件守卫、Importer 调用、导入结果适配；连接 B1 发布事务。B1 提供认证组件与发布服务，A2 只使用。

#### 输出与交接对象
POST /api/v1/curriculum-snapshots/import 可在真实 MySQL 下使用；管理导入说明和复现输入。

#### 不包含／他人负责
不实现持久化事务、Flyway、发布权限机制；不接学校账号。

#### 依赖与开工方式
A1、B1；A2/B1 联调原子性，Bug 回到代码所有者修复。

#### 验收条件
- [ ] 有效 XLS 发布成功，重导返回同一快照且 reused=true。
- [ ] 大于 10 MiB、伪后缀、未知规则拒绝；发布故障无半张快照，临时文件清理。
- [ ] 提供实现 PR、检查命令/结果和关联模块实际调用证据；真实调用、mock 和未完成项分别标明。

[模块 TRD](https://github.com/HelicasECoode42/CoursePilot-Evo/blob/main/docs/trd/a-data.md) · [统一契约](https://github.com/HelicasECoode42/CoursePilot-Evo/blob/main/docs/04-infrastructure-workflow.md)

### [A3 草案] 交付已修记录、课程教师评价和模拟班次输入包

待队长与成员核对的第五周任务草案；主要负责人：JiangYiLin-Q121；主要复核人：mira-xu。

#### 输入
公共 CompletedCourse/ReviewImport/OfferingImport 与 B3 TimeParser 合同

#### 本任务负责
整理完整/不完整/重修已修记录；至少两门课、两位教师的有限评价及无法匹配反例；准备单双周、离散周、节次边界、未知余串班次。

#### 输出与交接对象
可校验 JSON 与来源/匹配说明，交 B1/B2/B3、D1；评价/班次导入入口归 B1。

#### 不包含／他人负责
不爬取实时评价，不认证当期开课，不解析时间；公开样例全部虚构并标来源，真实授权资料只在本地。

#### 依赖与开工方式
G0；可与 A1/A2 并行，B1/B3 消费。

#### 验收条件
- [ ] JSON 校验通过；缺教师/学期不能自动变成已匹配。
- [ ] 每种班次原文有期望解析状态；模拟、真实培养事实、缺真实班次分开标记。
- [ ] 提供实现 PR、检查命令/结果和关联模块实际调用证据；真实调用、mock 和未完成项分别标明。

[模块 TRD](https://github.com/HelicasECoode42/CoursePilot-Evo/blob/main/docs/trd/a-data.md) · [统一契约](https://github.com/HelicasECoode42/CoursePilot-Evo/blob/main/docs/04-infrastructure-workflow.md)

### [B1 草案] 交付 MySQL 发布事务、记录存储和事实查询 API

待队长与成员核对的第五周任务草案；主要负责人：mira-xu；主要复核人：JiangYiLin-Q121。

#### 输入
A 的 draft/结构化输入、Java OpenAPI

#### 本任务负责
负责 Spring 服务、Flyway、服务/管理身份检查、PublishPort 原子幂等发布；快照/课程、学业记录、评价/班次存储和查询；评价/班次导入 Controller；teacher-course-options/reviews 查询。班次解析委托 B3。

#### 输出与交接对象
可从空库启动的服务；A2 发布端口，C1 所需存储/查询 API；固定依赖、健康检查及错误封套。

#### 不包含／他人负责
不编写 XLS 解析、学分核对、时间判决或模型；A2 的 XLS 导入 Controller 不重复实现；不承担 career 内容。

#### 依赖与开工方式
G0、A3；先交 PublishPort 和 record/course 接口，评价及班次随后补齐。

#### 验收条件
- [ ] 重导含并发重导不重复写；失败回滚；发布快照不可原地改写。
- [ ] record scope 隔离、错误快照/学期拒绝；历史评价不冒认当期教师班次。
- [ ] 提供实现 PR、检查命令/结果和关联模块实际调用证据；真实调用、mock 和未完成项分别标明。

[模块 TRD](https://github.com/HelicasECoode42/CoursePilot-Evo/blob/main/docs/trd/b-verifier.md) · [统一契约](https://github.com/HelicasECoode42/CoursePilot-Evo/blob/main/docs/04-infrastructure-workflow.md)

### [B2 草案] 按完整培养路径计算必修与类别学分核对结果

待队长与成员核对的第五周任务草案；主要负责人：mira-xu；主要复核人：amorfatiii。

#### 输入
B1 快照/记录与 A1 完整路径受控规则

#### 本任务负责
实现 AuditEvaluator 和 requirements/audit：覆盖已发布路径的全部必修与类别学分规则、已修去重及受控重修/替代；缺口、建议学期与未知分开。

#### 输出与交接对象
AuditResult 及来源，供 C1/E2/D1/D3；人工核对的黄金测试。

#### 不包含／他人负责
不只测一门课就算完成；不推断未支持规则；不决定推荐顺序、不生成班次。

#### 依赖与开工方式
B1、A1/A3；纯计算可先用共享输入独立开发。

#### 验收条件
- [ ] 完整记录与人工总表逐项一致；小数学分不丢精度，重修不重复计。
- [ ] 不完整记录或无法认定的替代只将受影响要求标 UNKNOWN，不给虚假确定缺口；suggestedTerm 不当硬规则。
- [ ] 提供实现 PR、检查命令/结果和关联模块实际调用证据；真实调用、mock 和未完成项分别标明。

[模块 TRD](https://github.com/HelicasECoode42/CoursePilot-Evo/blob/main/docs/trd/b-verifier.md) · [统一契约](https://github.com/HelicasECoode42/CoursePilot-Evo/blob/main/docs/04-infrastructure-workflow.md)

### [B3 草案] 解析模拟班次并返回 VALID、INVALID、UNKNOWN 核验

待队长与成员核对的第五周任务草案；主要负责人：mira-xu；主要复核人：goat-yang。

#### 输入
A3 原始时间/calendar、B1 数据、候选计划

#### 本任务负责
独占 TimeParser、ConflictChecker、plans/validate 和 preferences/score；覆盖单双周/离散周/节次重叠、hard 约束；核验绑定记录版本/双快照/主体/摘要。

#### 输出与交接对象
PlanValidation、verifierResultId、可计算偏好 metrics；供 C2/C3/D1。

#### 不包含／他人负责
不让模型解析时间；不把 synthetic 判定当真实排课；不自创培养规则、不处理 UI。

#### 依赖与开工方式
G0、A3、B1/B2；parser/domain 可先独立完成。

#### 验收条件
- [ ] 已知违规优先 INVALID；无违规但缺时间/来源不合格为 UNKNOWN；仅完整模拟数据可得 SIMULATION+VALID。
- [ ] 未知余串/缺周次不默认每周；错学期、跨主体及旧核验结果用于新方案被拒。
- [ ] 提供实现 PR、检查命令/结果和关联模块实际调用证据；真实调用、mock 和未完成项分别标明。

[模块 TRD](https://github.com/HelicasECoode42/CoursePilot-Evo/blob/main/docs/trd/b-verifier.md) · [统一契约](https://github.com/HelicasECoode42/CoursePilot-Evo/blob/main/docs/04-infrastructure-workflow.md)

### [C1 草案] 接通匿名会话、学业记录和事实查询的 Python 网关

待队长与成员核对的第五周任务草案；主要负责人：goat-yang；主要复核人：HelicasECoode42。

#### 输入
Python OpenAPI、B1/B2 HTTP 接口

#### 本任务负责
负责 sessions、可信主体派生、record/audit 及 curriculum/course/teacher/review 白名单网关；typed DTO、超时、错误封套；提供启动/健康检查。

#### 输出与交接对象
浏览器只访问 Python 即可创建记录、核对学业、查课程教师评价；交 E1/E2/E3。

#### 不包含／他人负责
不直读 MySQL、不计算学分和时间；不代替 C2 模型运行；报告 API 在第六周。

#### 依赖与开工方式
G0；可用合同 mock 开工，验收必须接 B1/B2。

#### 验收条件
- [ ] 同会话记录可读写，跨主体不可读；过期会话有明确错误。
- [ ] Java 超时/不可用返回受控错误，不能将失败包装为空列表成功；service/admin key 不返回浏览器。
- [ ] 提供实现 PR、检查命令/结果和关联模块实际调用证据；真实调用、mock 和未完成项分别标明。

[模块 TRD](https://github.com/HelicasECoode42/CoursePilot-Evo/blob/main/docs/trd/c-agent.md) · [统一契约](https://github.com/HelicasECoode42/CoursePilot-Evo/blob/main/docs/04-infrastructure-workflow.md)

### [C2 草案] 用真实模型生成候选并强制调用 Java 核验

待队长与成员核对的第五周任务草案；主要负责人：goat-yang；主要复核人：mira-xu。

#### 输入
PlanningRequest、C1 身份、B2/B3 事实与核验

#### 本任务负责
实现唯一 runner.run、模型适配、候选 ID/证据守卫、planning API 与 TracePort；结构化意图中的 hard/soft/priority 保持独立；候选全部经 Java 核验。

#### 输出与交接对象
真实模型→Java→PlanningAnswer；最多三份有核验/来源/未知提示的候选；D3 可调用同一 Runner 并拿 manifest/usage。

#### 不包含／他人负责
不预写候选冒充模型；不自行改写 Java 判决；不另建评测 Agent，不做训练；Harness 演化放第六周。

#### 依赖与开工方式
C1、B2/B3；模型接入与 Trace 可并行。

#### 验收条件
- [ ] 非法 JSON、虚构 course/teacher ID、恶意评价指令被拦；缺班次只能给课程层建议及 UNKNOWN。
- [ ] 有真实模型调用证据与 requestId/版本/token/耗时；拿不到 token 为 null；公开日志无成绩、密钥和完整 Prompt。
- [ ] 提供实现 PR、检查命令/结果和关联模块实际调用证据；真实调用、mock 和未完成项分别标明。

[模块 TRD](https://github.com/HelicasECoode42/CoursePilot-Evo/blob/main/docs/trd/c-agent.md) · [统一契约](https://github.com/HelicasECoode42/CoursePilot-Evo/blob/main/docs/04-infrastructure-workflow.md)

### [C3 草案] 实现澄清续问、改条件重规划和有界失败处理

待队长与成员核对的第五周任务草案；主要负责人：goat-yang；主要复核人：HelicasECoode42。

#### 输入
G0 澄清合同、C2 Runner、previousPlanId/幂等请求

#### 本任务负责
接通 CLARIFY 回答后继续规划、指定教师必须/偏好冲突取舍、previousPlanId 重新核验；实现幂等、调用/Token/deadline 上限与迟到答案丢弃。

#### 输出与交接对象
同一学生可补充答案、修改一个条件得到新核验；超时/重试有明确终态，交 E2/D2。

#### 不包含／他人负责
不静默删教师硬锁、不靠无限重试成功；不把 previousPlanId 当授权；不负责前端 store。

#### 依赖与开工方式
C2、B3；E2 按 G0 并行接状态。

#### 验收条件
- [ ] 缺关键字段 CLARIFY 且无 recommendations，补答后可继续；改条件产生新核验。
- [ ] 相同键同内容不双跑，不同内容 409；超时/预算耗尽停止发布；跨主体 previousPlanId 拒绝。
- [ ] 提供实现 PR、检查命令/结果和关联模块实际调用证据；真实调用、mock 和未完成项分别标明。

[模块 TRD](https://github.com/HelicasECoode42/CoursePilot-Evo/blob/main/docs/trd/c-agent.md) · [统一契约](https://github.com/HelicasECoode42/CoursePilot-Evo/blob/main/docs/04-infrastructure-workflow.md)

### [D1 草案] 完成四组各 3+3 案例与独立答案隔离

待队长与成员核对的第五周任务草案；主要负责人：amorfatiii；主要复核人：mira-xu。

#### 输入
A/B 真值依据、公共请求与 C2 Runner 合同

#### 本任务负责
四组各至少 3 evolution+3 held-out，共 24 例；定义评分、人工预期、虚构公开样例与运行时私有 gold/held-out；先交种子给开发。

#### 输出与交接对象
有 caseId/group/输入/预期依据的案例目录和隔离检查；交 D3，公开库仅放可公开材料。

#### 不包含／他人负责
不写第二个 Agent、不用模型输出反推答案；不把 held-out/gold 上传公开仓库；目标 5+5 在第六周扩充。

#### 依赖与开工方式
G0、A3；mira-xu 核对事实标签，goat-yang 核对意图/澄清标签。

#### 验收条件
- [ ] 四组均达到 3+3，覆盖建议学期误判、评价维度混淆、缺班次、教师硬锁和 replan。
- [ ] Evolver 身份实际尝试读取 gold/held-out 被拒；题面/答案分离，评分规则有正反例。
- [ ] 提供实现 PR、检查命令/结果和关联模块实际调用证据；真实调用、mock 和未完成项分别标明。

[模块 TRD](https://github.com/HelicasECoode42/CoursePilot-Evo/blob/main/docs/trd/d-benchmark-rsi.md) · [统一契约](https://github.com/HelicasECoode42/CoursePilot-Evo/blob/main/docs/04-infrastructure-workflow.md)

### [D2 草案] 把真实服务规划链路与浏览器冒烟加入 CI

待队长与成员核对的第五周任务草案；主要负责人：amorfatiii；主要复核人：HelicasECoode42。

#### 输入
各模块固定依赖/启动命令、E 页面与公共样例

#### 本任务负责
拥有组合启动脚本、集成测试与 CI job；启动 MySQL/Java/Python/Web，测试建会话→record→audit→planning→replan；加浏览器主路径、UNKNOWN 和服务失败冒烟。

#### 输出与交接对象
新环境一条入口复现检查；失败有 requestId/步骤/退出码；给全组联调证据。

#### 不包含／他人负责
不实现各模块业务、不替别人修业务 Bug；CI 模型可用受控假响应，但 Java/HTTP/DB/UI 必须真实；真实模型验收另跑。

#### 依赖与开工方式
B1/B2/B3、C1/C2/C3、E1/E2；先搭 CI，服务到位后逐条接通。

#### 验收条件
- [ ] 任一必需服务缺失、错误状态/Schema 或核心页面不能继续时 CI 失败，不允许 SKIP 成功。
- [ ] 模型受控响应运行可重复；每周验收另留真实模型全链路证据；接口问题明确转交所有者。
- [ ] 提供实现 PR、检查命令/结果和关联模块实际调用证据；真实调用、mock 和未完成项分别标明。

[模块 TRD](https://github.com/HelicasECoode42/CoursePilot-Evo/blob/main/docs/trd/d-benchmark-rsi.md) · [统一契约](https://github.com/HelicasECoode42/CoursePilot-Evo/blob/main/docs/04-infrastructure-workflow.md)

### [D3 草案] 用生产 Runner 跑四组 v0 并输出逐例质量成本

待队长与成员核对的第五周任务草案；主要负责人：amorfatiii；主要复核人：goat-yang。

#### 输入
D1 案例/评分器、C2 Runner/Trace、固定模型和预算

#### 本任务负责
实现 BenchmarkRunner、Scorer、manifest 校验与 RunReport；跑四组可重放 v0，聚合质量、硬违规、无证据主张、token 覆盖率和耗时。

#### 输出与交接对象
实际 v0 逐例与汇总结果；RunReport DTO 交第六周老师报告页，失败证据供后续演化。

#### 不包含／他人负责
不实现 Evolver/两轮晋级（第六周）；不将缺 token 算 0；不把 fake 模型测试算 v0。

#### 依赖与开工方式
D1、C2/C3、B2/B3；案例和 scorer 可先独立写。

#### 验收条件
- [ ] 四组真实运行有 manifest/hash，生产与评测共用 Runner/工具配置。
- [ ] 模型/评分失败保留状态，不伪造分数；同 manifest 可复跑；从至少两个不同 case 查重复失败，若不存在如实记录。
- [ ] 提供实现 PR、检查命令/结果和关联模块实际调用证据；真实调用、mock 和未完成项分别标明。

[模块 TRD](https://github.com/HelicasECoode42/CoursePilot-Evo/blob/main/docs/trd/d-benchmark-rsi.md) · [统一契约](https://github.com/HelicasECoode42/CoursePilot-Evo/blob/main/docs/04-infrastructure-workflow.md)

### [E1 草案] 实现一次一问、多目标分支和返回保留的 Vue 页面

待队长与成员核对的第五周任务草案；主要负责人：HelicasECoode42；主要复核人：goat-yang。

#### 输入
现有 HTML 交接规范、G0 DTO、C1 会话接口

#### 本任务负责
搭 Vue/TS 路由/store/唯一 ApiClient；目标多选、hard/soft/priority 输入、相关问题跳转、内存答案与返回保留；接匿名会话。

#### 输出与交接对象
可操作问题流程和 PlanningRequest，交 E2；固定依赖、启动/健康检查、桌面窄屏证据。

#### 不包含／他人负责
不复制 HTML 假候选、不算学分/时间；不存 bearer 到 localStorage/URL；不做老师报告页。

#### 依赖与开工方式
G0；页面可用共享 fixture 并行，验收接 C1 会话。

#### 验收条件
- [ ] 非职业目标跳过职业题，多目标不覆盖；返回上一题仍保留答案。
- [ ] 一次仅显示当前问题，键盘和窄屏可用；刷新按合同新建会话，不声称恢复旧私人记录。
- [ ] 提供实现 PR、检查命令/结果和关联模块实际调用证据；真实调用、mock 和未完成项分别标明。

[模块 TRD](https://github.com/HelicasECoode42/CoursePilot-Evo/blob/main/docs/trd/e-web-integration.md) · [统一契约](https://github.com/HelicasECoode42/CoursePilot-Evo/blob/main/docs/04-infrastructure-workflow.md)

### [E2 草案] 接通记录、学业核对、规划结果与修改条件重规划

待队长与成员核对的第五周任务草案；主要负责人：HelicasECoode42；主要复核人：goat-yang。

#### 输入
E1 状态、C1 record/audit、C2/C3 planning

#### 本任务负责
实现记录缺失补录/已有关联记录读取、Audit 展示、提交规划、CLARIFY 补答、候选与依据/未知展示、修改条件后重新规划；处理错误、重试、迟到响应。

#### 输出与交接对象
用户从输入到真实建议再到 replan 的完整浏览器流程；交 D2 验收。

#### 不包含／他人负责
不只展示 Audit 就完成；不自己判断 VALID；不绕过 Python；教师评价详情由 E3，老师报告第六周。

#### 依赖与开工方式
E1、C1/C2/C3、B2/B3；UI 状态可依共享样例并行。

#### 验收条件
- [ ] 正常、资料不完整、缺班次、模拟冲突、澄清和服务失败均有可操作界面。
- [ ] 缺时间无绿色通过，模拟明确标注；重试同请求保留幂等键；旧响应不覆盖新条件；修改条件可得到新结果。
- [ ] 提供实现 PR、检查命令/结果和关联模块实际调用证据；真实调用、mock 和未完成项分别标明。

[模块 TRD](https://github.com/HelicasECoode42/CoursePilot-Evo/blob/main/docs/trd/e-web-integration.md) · [统一契约](https://github.com/HelicasECoode42/CoursePilot-Evo/blob/main/docs/04-infrastructure-workflow.md)

### [E3 草案] 实现课程教师搜索、必须/偏好选择及来源详情

待队长与成员核对的第五周任务草案；主要负责人：HelicasECoode42；主要复核人：JiangYiLin-Q121。

#### 输入
A3 评价、B1 经 C1 暴露的教师/评价查询

#### 本任务负责
课程绑定教师选择器；必须/优先考虑分别写 pinned pair；展示评价课程/教师/学期、来源、样本和维度；返回问题保留选择。

#### 输出与交接对象
用户可查两门课的教师评价并将明确意愿送入 E2/C3。

#### 不包含／他人负责
不抓取评价、不把历史评价当当期开课；不做未支持专业的真实规划；职业资料扩充第六周。

#### 依赖与开工方式
E1、C1/B1/A3；合同 fixture 可先做，验收用真实查询。

#### 验收条件
- [ ] 未知评价没有假星级，低签到不代替低作业/高分；来源可追溯。
- [ ] 教师必须项不在返回/重规划时消失；详情关闭后焦点回原入口。
- [ ] 提供实现 PR、检查命令/结果和关联模块实际调用证据；真实调用、mock 和未完成项分别标明。

[模块 TRD](https://github.com/HelicasECoode42/CoursePilot-Evo/blob/main/docs/trd/e-web-integration.md) · [统一契约](https://github.com/HelicasECoode42/CoursePilot-Evo/blob/main/docs/04-infrastructure-workflow.md)

## 后续如何拆任务

第六周以上表大目标为父项，在第五周周末根据实际欠账拆子任务；第七/八周同理。前置条件现在落在 D1/D3 的隔离/Trace/manifest/报告合同，C2 的同一 Runner 和 B3 的事实核验中。后续缺陷使用同一 Project 的 Bug Issue，写复现、所有者、优先级和回归证据。

本排期明显快于旧版，依赖并行开发和周中接口可用。尚未采集个人可投入时间；首次周中联调以实际吞吐调整单项范围，不能通过降低 UNKNOWN/权限/真实验收标准来报完成。
