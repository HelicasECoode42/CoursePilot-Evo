# 对话到规划第一轮接口

实施范围见 [分类与实施顺序](28-course-categories-and-chat-delivery.md)。本轮新增只读对话，学生确认后更新当前规划草稿，正式方案仍走已有 Planning Runner。以下为本轮实现约定，完成情况另记验收。

## HTTP 接口

`POST /api/v1/advice/chat`，使用现有 Bearer 会话、`X-Request-Id`、`Idempotency-Key` 与 Envelope。相同请求重放不增加模型费用，修改消息使用新幂等键。每轮最多一次模型调用，不自动付费重试，复用现有单轮预算、deadline 和会话累计预算。

请求 `AdviceChatRequest`：

| 字段 | 内容 |
| --- | --- |
| schemaVersion | `1.0` |
| curriculumSnapshotId | 当前培养方案 ID，必填 |
| academicRecordId | 本会话记录 ID，可为 null；没有记录仍能讨论方向 |
| mode | 现有 PlanningMode |
| message | 本轮问题，1–1000 字符 |
| history | 最多 8 条 `{role: user或assistant, text: 1–3000字符}`，仅供上下文，不作为学校事实 |
| interestText | 当前已确认兴趣文本，最多 1000 字符，可为空 |
| selectedCourseCodes | 当前已选课程号，最多 10 项 |
| preferredCourseCodes | 可选，默认空数组，最多 10 项；已确认优先考虑的课程，与明确选入的课程分开 |

响应 `AdviceChatAnswer`：

| 字段 | 内容 |
| --- | --- |
| schemaVersion | `1.0` |
| reply | 回答，1–3000 字符 |
| question | 需要学生补充的一个问题，或 null |
| courses | 最多 5 门 `{courseCode, name, credits, category, reason, reviewNoteIds, reviews, reviewStatus}`；名称、学分、类别、评价均由服务端查询补全，reason 来自模型 |
| suggestions | 最多 6 项 `{suggestionId, kind, label, value}`；kind 为 `INTEREST`、`SELECT_COURSE`、`PREFER_COURSE`；课程动作必须引用本次响应中的候选 |
| schoolProgress | null 或 `{capturedAt, source, nodes:[{nodeId,parentId,name,requiredCredits,earnedCredits,remainingCredits}]}`；保留学校原始数字，不汇总父子，不提升来源核验状态 |
| unknowns | 现有 Issue 数组 |
| usage | 现有 Usage：inputTokens、outputTokens、toolCalls、elapsedMs；每轮模型调用上限由后端执行 |

`credits` 和节点学分允许 null；`reviews` 为现有 ReviewNote 数组，`reviewStatus` 为 `AVAILABLE`、`NONE`、`NOT_QUERIED`、`UNKNOWN`，分别对应实际查询结果；不得将未查询写成没有评价。`reviewNoteIds` 必须属于同课程的已查询评价。原始学校成绩、登录凭据不进入模型消息或日志。

## 失败与重新生成

网络中断等可重试请求沿用原请求体与幂等键，以便取回已完成的结果。已有明确模型用量的结构或引用校验失败会按原键保留，普通重放只返回同一失败，不能把它描述为再次生成。

学生明确点击“重新生成回答”时，使用新的幂等键发起一次新模型调用；不自动执行。修改问题后发送也属于新请求。失败后结束处理中状态，保留原问题、已有回答和已确认偏好；失败提示使用对话语义，不显示“没有写入任何方案”作为聊天结果。失败消息不作为成功回答加入下一轮历史。

错误诊断只记录请求标识、阶段、字段路径或稳定错误分类、用量与响应形状，不记录完整模型文本、Prompt、成绩或学校凭据。没有保存的过去响应不能据此推断其具体失败字段，应标记原因未查明。

## 模型与事实

对话应用服务通过现有 ToolClient 查询学校进度、必要学业记录、课程目录及有限相关评价。学校进度不存在时保留 null；其他查询失败按真实错误处理。没有记录可提供方向讨论，不能声称已经排除个人已修课程。

候选默认取专业选修、高年级研讨，排除已通过与在读课程；挂科允许补修讨论，状态未知单独说明，不自动判作已修。公共基础退出主动推荐。模型不得返回事实集之外的课程、跨课程评价或修改事实的动作。显式固定课程仍由正式规划原有约束处理，不因默认推荐范围而被静默丢弃。

模型适配器复用已有 HTTP 传输和错误处理，增加对话结构化输出能力，不能用固定模板冒充真实模型。受控假模型明确标识。对话服务不另建正式规划 Runner，不写 Java 学业事实，不生成 planId。

## 前端与确认

我的学业中的自由输入改为真实发送消息，原有学分、课程评价、方向和完整引导入口保留。展示历史消息、处理中、失败和课程卡片，保留失败前输入；对方消息以文本渲染。前端只消费本次已展示的建议，点击“采用”才调用已有 draft 更新方法。

INTEREST 追加兴趣文本，保留原文与 1000 字符限制；SELECT_COURSE 加入已有 selectedCourseCodes，去重且遵守 10 门上限；PREFER_COURSE 写入 preferredCourseCodes，构建正式请求时转换为 softPreferences 的 `dimension=course.prefer`、`value=课程号`，不转换为 PIN_COURSE。两类选择分别显示，可取消。每项重复点击不重复应用。已通过、在读课程不作为可采用课程返回。已有画像字段不自动填动机和优先级。

点击继续进入原有完整引导，既有选择保持。尚缺记录或确认步骤时如实提示，学生完成后调用现有 `/api/v1/planning`。对话文字、兴趣和所选课程随既有请求进入 Runner。

## 所有权与验收

- 后端 Luna：对话 schema、应用服务、路由、适配器扩展、app/deps 接线；公共 OpenAPI、Schema、examples 同步；相关测试。
- 规则 Luna：统一推荐候选与课程状态政策、PlanningRunner 接线和相关测试；不改模型适配器或对话接口。
- 前端 Luna：类型、HTTP/fixture client、聊天组件、Dashboard 接线、会话内对话状态与相关测试；不改 contracts JSON 或后端。
- 主 Agent：文档、共享约定协调、真实服务与浏览器验收；完成一轮后由独立 Luna 复核。

验收覆盖事实来源、公共基础排除、已修/在读/挂科/未知、学校缺口进入对话、引用同课程、失败与幂等记账、显式采用、重复采用、原引导保留、草稿进入正式规划。测试使用受控响应；真实模型先完成一次完整链路，记录实际用量。
