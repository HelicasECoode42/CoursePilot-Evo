# 工程、调试与提交规范 v1

本文件是五人共用的实现要求。目标是代码边界清楚、错误可定位、接口不分叉、数据不误用。命名遵循各语言常规，评审更关注职责、依赖方向、状态与错误处理。当前仅文档/契约与独立原型，没有已通过这些规范的业务服务。

## 1. 代码结构与依赖方向

| 模块 | 结构 | 禁止做法 |
| --- | --- | --- |
| Java | api DTO/controller → application/use-case → domain/rules；persistence/adapters 实现 ports | controller 算学分；entity 直接返回 Web；domain 依赖 HTTP/JPA；多个时间解析器 |
| Python | api/schema → application/runner → domain/policies；adapters 封装 LLM/HTTP/store | 路由函数写完整 Agent；模型直读 DB；到处重复 httpx/模型配置 |
| Vue | views → feature components/store → api adapter；DTO 从契约映射 | 组件重算 Java 规则；每页各定义 response；store 同时存原始事实和假设且不区分 |
| Benchmark | cases/gold 与 runner/scoring 隔离，mining/patch/promotion 分层 | 写另一个评测 Agent；Evolver 可读 gold/held-out；把模型自评当唯一真值 |

一段逻辑只保留一个 Owner。重复的业务规则先抽共同 domain/service，不跨模块复制工具函数。公共工具仅放确实多个调用方需要且职责稳定的逻辑，不建没有边界的 utils 大桶。

一个函数处理一件可说明的事：边界解析、事实查询、规则计算、模型调用、核验或输出。超过约 80 行/五个嵌套分支时评审拆分原因，但不为凑行数制造无意义小函数。核心规则要能用纯输入输出测试。

## 2. 类型、配置和状态

Java BigDecimal 算学分；Python Pydantic 禁额外字段；TS 不以 any 绕过接口。未知=null或明确UNKNOWN，不能偷偷改为0/false。输入 DTO、domain、数据库 entity、模型草稿、正式答复是不同对象，不能混用。

全组用唯一配置入口；模型/预算/端口/timeouts/CORS 都是环境配置。服务启动校验缺必要配置并失败，不能默认使用硬编码密钥或宽松公网 origin。

状态转移由 application/domain 管，不散落在 controller/组件。计划验证 INVALID/UNKNOWN/VALID 与请求 ERROR 分开；迟到答复不覆盖新输入；发布/稳定指针原子更新。可比评测配置只由 manifest 指定。

## 3. 错误处理与调试

错误统一 code/message/field/retryable，业务未知返回可行动的补资料提示，系统错误有 requestId。不能 catch Exception 后返回空集合假装成功；不能在普通业务错误里输出堆栈给学生。

每条结构化日志允许：timestamp、level、service、requestId、traceId、taskId、stage、toolName、status/code、durationMs。禁止完整 Prompt、模型推理链、个人成绩、学号、姓名列表、Cookie、Authorization、Service Key、Admin Key、原始学校响应和评价全文。

Debug 顺序：复现最小输入 → 用 requestId 找三层事件 → 确认 snapshot/record revision/mode → 查 Java facts/unknownChecks → 查 Agent工具顺序与预算 → 查 UI 是否误解状态。先定位错误层，再改；不要靠调大 Prompt、禁校验或加重试掩盖真值问题。

每个 bug 记录：触发条件、预期/实际、错误层、原因、修复、必要的回归证据。用虚构最小 fixture 复现，不能将真实成绩/密钥贴到 issue 或群聊。生产日志不能临时全量 dump 敏感上下文；调试模式也遵守字段白名单。

## 4. 安全与数据边界

- 会话/记录/计划每次做对象级授权；frontendId 不等于权限。Java 信任的是已认证 Python 服务，不能透传浏览器自报身份头。
- 默认本地 loopback；真实公网部署另外完成 HTTPS、正式身份、严格 CORS、限流、上传和授权设计。配置 origin 白名单，不能用 `*` 加凭据。
- SQL 参数化，动态排序字段白名单；不 eval/exec 模型、规则、评价、文件内容。LLM 的 toolName/ID 必须是登记值。
- 评价是数据，不是指令；不能触发额外联网、读文件或修改 Prompt。后端不抓用户任意 URL；UI 不 v-html 渲染模型/评价。
- 上传限制格式/大小，文件名由服务端生成，拒绝穿越，临时文件结束清理；不执行 Excel 宏/外链/公式。
- 密钥只进环境变量；`.env.example` 仅占位；原始数据/个人记录/私有 runs 在 gitignore。有人误提交密钥必须撤销/轮换，再处理历史，单纯删文件不够。
- 公开仓库不放完整验收 held-out/gold。Evolver 的受限目录和报告脱敏要实测，不只靠提示词。

这些要求降低已识别风险，不能用一次扫描承诺“绝对无安全问题”。新增公网/学校数据接入必须再做对应安全验证。

## 5. 格式、构建和依赖

用 .editorconfig 统一 UTF-8、LF、末尾换行、去尾空格。Java 使用 Maven Wrapper，Spotless 与 verify 接入构建；Python Ruff format/check、pytest；Web ESLint/Prettier、vue-tsc、Vitest 和 build。具体版本写各模块 manifest/lock，不能各人全局环境猜版本。

模块第一次加入可执行代码时，同时提交 manifest、锁文件/固定依赖、测试入口、README 启动方式和 CI 检查。Java 设置没有测试时失败；Python pytest 无测试不能冒称通过；Web script 必须包含 lint/typecheck/test:unit/build。尚未出现的模块脚手架在 CI 明确 SKIP，不算已通过功能验收。

不因赶进度 blanket disable lint、删失败测试、降低 assertions 或吞异常。依赖只从官方注册源，锁定版本；CI Actions 固定 commit SHA，最小 contents:read，不运行 pull_request_target 执行他人代码，不给 PR job 密钥。

## 6. 每次提交前自查

```bash
python scripts/check_contracts.py
python scripts/self_check.py
python scripts/check_modules.py
```

安装契约检查依赖见根 README。self_check 仅做基础私密文件/常见密钥和链接检查，不能替代代码安全评审。代码提交还必须运行受影响模块的真实测试；check_modules 在模块 manifest 存在时触发它们。

审 staged diff：没有原始数据/密钥、没有未知被判通过、没有临时 debug dump、没有意外改其他模块；接口/行为变化同步文档和正反例。纯文档修改可以说明模块测试不适用，但契约/文档检查仍要运行。

## 7. PR 与复核

一项任务一个短分支，一个 PR 说明具体变化和证据。完成通用自查项；接口/Java规则/RSI改动填写条件项。每个复选框对应实际做过的工作，不适用则在说明中写原因，不空勾。

普通 PR 至少一名队友复核；公共契约由提供者和一个消费者复核；规则/时间/晋级 gate 改动由相关 Owner 复核。复核重点是反例、权限、未知、快照与成本，不只看名字顺眼。

当前模板/CI 可以自动检查基础项；分支保护是否启用以 GitHub 设置为准，不能把有模板等同强制审核。以后有成员名单后填写 CODEOWNERS，不能预填假用户名。

参考：[OWASP 日志规范](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)、[OWASP REST 安全](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)、[GitHub Actions 安全](https://docs.github.com/en/actions/reference/security/secure-use)。本项目按本地五周范围选用具体控制，不照搬大型系统。
