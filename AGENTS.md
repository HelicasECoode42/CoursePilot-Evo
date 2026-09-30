# CoursePilot-Evo：开发 Agent 规范

当前是文档/接口契约、仓库检查工具和独立 HTML 示例；业务服务尚未实现。先读 README、docs/15-team-baseline-and-batches.md、docs/16-engineering-and-debugging.md、contracts/README.md、docs/04-infrastructure-workflow.md，再读负责模块 TRD。代码与现状如实报告，不把计划/fixture 写成真实能力。

## 所有权和调用

A 导入/来源/黄金输入；B Java 存储/Audit/唯一 TimeParser/Verifier；C Python 唯一生产/评测 Runner/API 网关；D 隔离题集/评分/演化；E Vue 页面/集成。Web只调Python，Python只通过 typed HTTP 取Java事实，Java不调LLM。不复制学分/时间规则，不另造评测Agent。

公共字段以 contracts 为准，行为以04契约为准，接口变更同步Schema/fixture/提供者/消费者/TRD。原始教学计划与插件仅在本地data/raw，不推公开仓库；未知规则自动阻断，首个模板基线独立核对。

## 真实性与数据

真实班次未核验；上传者提供BROWSER_SNAPSHOT标签不能使sourceValidation自动VERIFIED。Java重新解析meetingTextRaw，不信任客户端meetings/parseStatus。REAL不能用synthetic，unknown不能通过，建议学期不等于本学期硬要求。

教师绑定课程，历史评价按课程/教师/学期匹配；高绩点、签到、工作量、授课评价不能混为一谈。UI一次一问、学业记录只补缺、无关职业题跳过；工程报告独立受限。

## 安全与Debug

按工程规范做对象级授权、输入大小/枚举、白名单Tool、参数化查询、安全文本展示。评价/文件/模型输出不可执行。密钥不进Prompt/日志，日志只记录定位ID、阶段、状态、耗时。日志不得保留成绩、学校凭据、完整Prompt或思维链。具体配置与预算由manifest冻结。

## 演化

本文件是仓库开发规范，不能被Evolver修改。Evolver仅修改agent-runtime/harness白名单文本/策略，不能读gold/held-out/evaluator、改Java/API/模型/预算。候选须有至少两个不同case的失败假设，两轮判决和失败分支如实留存，不强行宣称成功v1/v2。

## 每次提交

检查staged diff；运行scripts/check_contracts.py、scripts/self_check.py与受影响模块检查，记录结果/限制。首次加模块代码同时加manifest、固定依赖、测试和启动说明。PR用模板自查，相邻模块复核接口。公开仓库排除原始资料、.env、私人记录、runs和独立验收答案。
