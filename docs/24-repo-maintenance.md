# 仓库维护手册

这份写给全组。不是规范（规范在 [AGENTS.md](../AGENTS.md) 和[工程规范](16-engineering-and-debugging.md)），是**怎么把仓库维持在能干活的状态**，以及我们已经踩过的坑。每条都标了为什么，不照做会出什么事。

## 一、每次提交前跑什么

三层，从快到慢。前两层几分钟内能跑完，不要跳。

```bash
# 1. 契约与文档（秒级）
python scripts/check_contracts.py     # Schema/OpenAPI 合法、本地引用可达、正反例判定正确
python scripts/self_check.py          # 披露检查、本地 Markdown 链接、不该入库的文件

# 2. 你改动的模块
cd java-environment && ./mvnw -B test          # Java
cd agent-runtime   && pytest tests/ -q         # Python
cd web             && npm run test:unit        # Vue（含 demo HTML 结构检查）
cd web             && npm run lint && npm run typecheck

# 3. 全仓（慢，PR 前跑一次）
python scripts/check_modules.py
```

CI 跑的是 `check_contracts.py` + `self_check.py` + `check_modules.py`。**CI 绿不等于功能对**——它只验结构、链接和各模块自己的测试。

## 二、本地起服务

### Java 核验服务

**必须带服务密钥，否则 `/api/v1` 全部返回 503。**

```bash
# macOS / Linux
cd java-environment
COURSEPILOT_SERVICE_KEY=local-dev-key ./mvnw spring-boot:run
```

```powershell
# Windows PowerShell —— 上面那种「变量=值 命令」的写法在 PowerShell 里不认
cd java-environment
$env:COURSEPILOT_SERVICE_KEY = "local-dev-key"
.\mvnw.cmd spring-boot:run
```

服务在 `http://127.0.0.1:8081`。调接口要同时带三个头：

```bash
curl -H 'X-Service-Key: local-dev-key' \
     -H 'X-Subject-Id: S001' \
     -H 'X-Request-Id: req-1' \
     http://127.0.0.1:8081/api/v1/courses
```

**为什么没配密钥是 503 而不是放行**：没有密钥就分辨不出调用方是谁，而 `X-Subject-Id`（要查谁的数据）是调用方自报的。Java 信任这个自报身份的唯一前提，就是密钥已经证明调用方是已认证的 Python 服务（[工程规范](16-engineering-and-debugging.md)）。放行等于谁都能读任意学生的成绩。

密钥只从环境变量来，**仓库里不放默认值**（[基础设施与协作](04-infrastructure-workflow.md)）。`local-dev-key` 只是本地占位，不要写进代码、配置文件或提交信息。

跑测试**不需要**设这个变量：用到 HTTP 的测试自己用 `@TestPropertySource` 指定密钥和内存库。但跑测试前要先停掉 `spring-boot:run`，否则 H2 文件库被占住会导致上下文启动失败。

H2 控制台默认关闭——它在同一端口上提供免认证的任意 SQL 执行，等于绕过对象级授权直接读整张成绩表。临时需要用命令行参数打开，不要写回仓库。

### Python 网关

```bash
cd agent-runtime
CP_JAVA_BASE_URL=http://127.0.0.1:8081 CP_SERVICE_KEY=local-dev-key uvicorn agent_runtime.api.app:create_app --factory
```

配置全部走 `CP_` 前缀的环境变量，见 `agent_runtime/api/settings.py`。`CP_JAVA_BASE_URL` 为空时所有 Java 工具报 `TOOL_UNAVAILABLE`。模型密钥不配时走受控假实现，不会调真实模型。

### Vue 页面

```bash
cd web
npm run dev                                   # 默认 http 模式，要有 Python 网关
VITE_COURSEPILOT_MODE=fixture npm run dev     # 合成数据，不需要后端
```

Node 要 **>= 22**（`package.json` 的 `engines`）。用 Node 20 跑过 lint 会报出一堆和主分支无关的格式问题——那是依赖版本不同造成的假阳性，不是真问题。

## 三、我们踩过的坑

按踩的顺序排，每条都真发生过。

### 1. 契约约束的不只是字段名，还有值

Java 的学业核对返回了 HTTP 200，Python 侧却一直报「服务不可用」。真正原因是 `requirementId` 把中文类别名拼了进去，而契约的 pattern 是 `^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$` 不许非 ASCII；同时 `sourceRefIds` 返回了空数组，而契约是 `minItems: 1`（每条结论必须可追溯）。

**教训**：接口对齐不是看字段名对不对，pattern、`minItems`、枚举值都会卡。写完要用 `domain.schema.json` 真校验一次响应，不能只看起来对。

### 2. 契约和提供方必须一起合入

有人实现了两个网关端点但没写进 `planning.openapi.json`。补契约时如果单独放一条分支，`agent-runtime/tests/test_openapi_contract.py` 会挂——它要求契约里每个端点在 FastAPI 的实现里都存在。

**教训**：Schema 改动和提供者实现放同一个 PR。那条测试拦住了错误放置，不要为了让它变绿去放宽它。

### 3. 单元测试全绿也可能有洞

Java 的服务密钥校验曾经用 `request.getRequestURI().startsWith("/api/v1/")` 判断要不要校验。11 条测试全绿，但 `GET /api/v1;x=1/verification/credit-gap` 不带任何密钥就能读到真实学生的学分缺口——原始路径带着分号后的矩阵变量不匹配前缀，于是跳过校验，而 Spring 的路径匹配会把这段剥掉照样路由到控制器。

MockMvc 的路径归一化和真 Tomcat 不一样，所以单元测试发现不了。

**教训**：**授权和解析类的代码，必须起真服务打一遍**。单元测试不能当证据。现在那里改成不按路径开豁免口（所有请求都要密钥），并有 10 种路径写法的参数化回归。

### 4. 错误分类糊在一起会让排查变成挖矿

Python 的 `ToolClient` 曾经用 `except (ValueError, TypeError, KeyError)` 兜住解析，而 Pydantic 的 `ValidationError` 继承 `ValueError`。结果拿真 Java 打一遍，七个工具失败五个全是同一句 `ToolUnavailable`，**错误密钥和越权 404 也长得一模一样**，只能一个个裸 `httpx` 去挖才知道真实原因。

**教训**：三类错误要分开——依赖挂了（可重试）、对方拒绝了我们（透传状态码和原因）、对方答的东西不合契约（不可重试，要指出字段）。

### 5. fixture 漂出契约没有兜底

演示数据没有联调这一步能发现问题。照一份不合契约的假数据把页面做出来，要等真实联调才会炸。

**教训**：`web/src/api/fixture-client.spec.ts` 逐条校验 fixture 出参是否过 `domain.schema.json`。改 fixture 要让这组测试继续绿。

### 6. UNKNOWN 不是「没问题」

缺时间、缺班次、缺资料一律是未知，**不能显示成通过**，也不能当成「没有冲突」。Java 的 `ConflictChecker` 区分「已知冲突」和「存在未知参与者」；前端有 `describeVerification` 做展示门禁，带受控缺口标记时降级。

**教训**：新增任何判定路径，先问「数据缺失时这里会不会变成绿色」。

### 7. 不要只测 `conflictsWith` 不测调用它的入口

`ConflictChecker.check()` 曾经一条测试都没有，只有底层的 `MeetingTime.conflictsWith` 被直接测过。结果它把一个「时间待定、根本不可能冲突」的班次报成了冲突方——时间列表按仓库返回顺序建，班次名却按入参顺序取。学生照这个结论会去退错的课。

**教训**：入口函数要有自己的测试，不能靠「里面那层测过了」。

### 8. Windows 和 Mac 的差异是真的

- `mvnw` 的可执行位：Windows 的 Git 不记录，在 Mac/CI 上会「Permission denied」
- `COURSEPILOT_SERVICE_KEY=x ./mvnw` 在 PowerShell 里不认，要 `$env:X = "..."` 分两行
- `python` vs `python3`：脚本里统一用 `python3`

**教训**：改启动方式或脚本时，两个平台的写法都要给。

## 四、分支与 PR

- 分支保护：main 需要 **1 个 approve**，`dismiss_stale_reviews`（推新提交会作废已有 approve），`require_last_push_approval`（**最后推送者不能批自己**），`enforce_admins`（管理员也绕不过）
- 因为 `require_last_push_approval`，你往自己 PR 推完提交后**自己批不了**，必须别人点
- 禁止 force push
- **不要随便删分支**：删掉某条分支会把以它为 base 的 PR 自动关闭。被关掉的 PR 可以用 `gh pr view N --json headRefOid` 拿回 SHA 重新推分支、reopen，再用 `gh api -X PATCH .../pulls/N -f base=main` 改 base
- 提交信息和 PR 描述不要挂 AI 作者
- PR 用仓库模板自查，接口变更请相邻模块复核

合并后远端分支不会自动删。定期清理已并入 main 且没有开放 PR 的分支，但**删之前确认它不是任何开放 PR 的 base**。

## 五、不能进公开仓库的东西

`.gitignore` 已经挡了 `data/raw/`、`data/private/`、`*.xls`、`*.xlsx`、`.env*`（除 `.env.example`）、`runs/`、`target/`、`coverage/`。

`scripts/self_check.py` 会再查一遍已跟踪文件。**如果你发现检查挡住了你要提交的东西，先在群里说，不要直接改检查脚本给自己开白名单**——规则可以改，但应该是一起改，而不是加一个单文件例外，否则规则和实际做法会越来越对不上。

这个仓库是 public 的。「校内自己用」和「公开仓库」是矛盾的，任何人都能 clone。真要放真实资料，正确做法是把仓库设成 private，或者把规则明确改掉，而不是绕过检查。

## 六、文档别写成愿望

[AGENTS.md](../AGENTS.md) 要求「代码与现状如实报告，不把计划/fixture 写成真实能力」。反过来也成立：**已经实现的东西不要还写着「尚未实现」**。

README、`docs/15`、`docs/05`、`docs/03` 的状态句是新人和老师看到的第一句话。每次有模块落地，记得回头改这几处。写的时候区分三档：

1. **已实测打通**：起真服务、真调用、看过响应
2. **已实现未联调**：代码写了、单元测试过了，但没有真实消费者打过
3. **未实现**

fixture 跑通属于第 2 档，**不能写成第 1 档**。
