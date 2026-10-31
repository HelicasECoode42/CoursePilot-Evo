# 学业导入、推荐与下学期课表实施方案

## 目标和业务流程

保留现有逐步引导、目标排序、时间偏好、兴趣职业输入、教师意愿、学分组合算法。学生在 CoursePilot 发起连接，在正方自行登录，在学业情况页点击浮窗导入，确认接收后返回原 CoursePilot 标签页。学校学业完成情况提供进度依据，课程明细提供修读事实。学生继续原有引导并选择课程，Python Runner 使用 Java 课程事实和评价形成建议，Java 核验方案。学生直接删除课程或更换班次，保存新版本并重新核验，查看下学期课表。

规划学期必须显式选择。本学期在读课程不作为下学期时间冲突来源；未结课不等同已获得学分。建议修读学期、历史开课学期、目标开课学期分别保存。

## 技术栈、责任与失败处理

| 部分 | 技术栈与数据 | 处理流程 | 失败处理 | 验收标准 |
| --- | --- | --- | --- | --- |
| 正方读取 | Chromium Manifest V3、JavaScript content script、DOM、Shadow DOM | 固定右下角浮窗；按 treeview 类别树解析节点与课程表，保留父子关系和课程状态；通过 extension background/bridge 回传原标签页 | 登录或页面未加载时提示；未知图标状态保留 UNKNOWN；扩展未连接提示连接；可选择已有 JSON 手动导入 | 与学校页面对照类别、父子关系、同名节点、课程状态；滚动与展开不移动浮窗 |
| 传输 | extension service worker、session storage、runtime message、同源页面消息 | 记录发起标签页和 requestId；只向该页回传；接收方确认后激活标签页；发送期间锁定按钮 | 接收方超时不宣称成功；原数据保留，可重试同次导入 | 真实跨标签页返回并显示；重复点击只处理一次；不发送学校凭据 |
| 保存和学业进度 | Java 21+、Spring Boot 3.4.1、Spring Data JPA、H2；Python FastAPI/Pydantic typed gateway | 学校进度独立聚合，保存类别树与课程事实，subject 从会话派生；事务保存、内容摘要幂等；映射至已有 AcademicRecord；学校报告和 Java 核对标注各自来源 | 数据不完整保留未知；同名父子节点不合并；与培养方案不符显示差异；保存失败不覆盖已选记录 | 重复导入复用、跨会话不可读、重启后可读、失败无半份记录；学校缺口能在我缺什么中显示 |
| 学分选课 | Vue 3、TypeScript、Pinia、现有 credit-plan 纯函数 | 缺口与课程类别关联；排除已通过；保留未知学分；选择进入规划；组合仍按恰好补足、超出量、未补足及兴趣排序 | 类别不能匹配不强行归类；学分未知不参与凑分；未修读状态未知不冒充已通过 | 从导入到候选和已选学分一致，返回页面保留选择 |
| 评价 | Java 查询、Vue 汇总组件、现有 review source refs | 按课程和维度统计记录覆盖与反馈，原文可展开；不把记录数写成独立人数，不生成无依据分数 | 无记录显示暂无评价依据；未查询明确标记；教师不明不强归教师 | 分页覆盖、证据同课程、维度各自呈现、来源可追溯 |
| AI 推荐 | Python 唯一 Planning Runner、现有模型 HTTP adapter、Pydantic、Java typed tools | 消费目标优先级、偏好、课程事实与实际查询评价；逐课程理由和探索方向；来源及评价查询状态由服务端派生 | 模型超时/格式错误沿用预算与错误状态，不自动付费重试；旧方案保留；缺评价仍可基于课程事实给建议 | 真实模型小样本联调，理由引用属于同课程，已通过不重荐，不把探索方向称为学校事实 |
| 删除与换班 | FastAPI、SessionPlanStore、既有 PlanReplacement、Java validatePlan、Vue ResultView | 删除指定项并去掉对应固定约束；其他项保留；生成新 planId 和新核验；同步当前展示与选择 | Java失败保持原方案，重试复用幂等键；最后一门删除形成明确空方案，不生成虚假核验 | 不调用模型，指定课程确定消失，其他课程不变，换班后重新核验，会话归属与重复请求通过 |
| 下学期课表 | 目标学期开课快照、Java TimeParser/Verifier、Vue PlanTimetable | 课程号关联班次、教师、原始排课文本和周次；Java统一解析；界面选班后生成新版本 | 缺目标学期来源只显示课程建议；解析失败保留时间未知；历史资料不作为当期班次 | 已验证目标学期样本；已知冲突/不冲突对照；删除换班立即反映于课表 |

## 并行工作所有权

- luna_school_import：扩展、学校进度 Java/Python 保存、导入相关 Web store/component，以及 RecordsView/CreditPlanView。
- luna_plan_edit：方案确定性编辑、ResultView、Web API client 和相关删除契约。
- luna_reviews_ai：评价 Java 查询汇总、TeacherView/新展示组件、Python Runner 及理由证据。
- 主 Agent：共享契约合并、开课来源调查、集成检查、真实浏览器与最终验收。

公共字段以 contracts 为准；各 worker 先写 proposals，主 Agent 合并。数据流为 Web → Python → Java；学校快照由学生主动读取，LLM 不获取登录态。

## Checkpoint 与恢复

执行 `python3 scripts/checkpoint.py <阶段名>`，得到不可变 commit 和 refs/checkpoints/coursepilot/* 引用。脚本使用临时 Git index，保留真实暂存区、当前分支和未提交文件；会保存 Git 非忽略文件。各 worker 在 docs/checkpoints/ 下记录对应引用与验证。

基线：`refs/checkpoints/coursepilot/20261029-153938-baseline`，commit `e2a30b519ec65b1bd50229aacc6a3fddd64fd5a6`。

恢复时先创建独立目录 `git worktree add --detach <新目录> <checkpoint commit>` 检查文件，不对当前协作目录执行 reset --hard。网络中断不会删除本地 Git 对象；重连后从 checkpoint 和工作记录继续。需要移动到其他电脑时，可对 checkpoint ref 创建 git bundle。

代码 checkpoint 不包含被忽略的密钥、私有学校原始资料、H2 数据库或运行中的会话。数据库使用停写后的文件备份或 H2 一致性备份；具体备份位置与恢复验证另记本地 checkpoint 记录。不得在服务写入时简单复制数据库并声称可恢复。Python 内存会话在重启后需要新建；持久化学校快照按真实认证归属读取，不跨会话自动认领。

## 验收顺序

1. 各模块相关单元/API测试、格式与类型检查。
2. contracts、自检和 Java/Python/Web/集成回归。
3. 正方真实页面读取对照；从 CoursePilot 发起、直接返回、保存并显示缺口。
4. 相同数据重复导入、网络错误重试、旧记录保留、页面刷新与服务重启分别验证。
5. 真实模型一次规划，核对课程与评价来源，再直接删除、换班并检查下学期课表。
6. 逐项记录通过、失败或缺数据阻塞；没有真实班次不得将真实课表验收标为通过。
