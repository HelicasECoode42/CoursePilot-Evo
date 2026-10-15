# D2 集成检查（D-F3）：组合启动、统一配置与主链路检查

对应 Issue #12。目标：从输入到推荐和调整的流程可重复检查，**服务缺失和失败会被发现**；
模型可用受控假响应，但 Java / HTTP / DB / UI 必须真实。

现在是 **W1 骨架的扩展**：配置入口、组合启动、主链路检查与异常覆盖都已可用；
Java 与 MySQL 尚未落地，跑起来会如实报缺谁、缺在哪一步，不用假结果补位。

## 一条入口

```bash
cp integration/stack.env.example data/private/stack.env   # 新环境第一步
python integration/check_all.py                           # 配置校验 → 组合启动 → 主链路 → 异常覆盖 → 受控假响应 → 浏览器检查
```

`check_all.py` 是本地与 CI 共用的入口：全 PASS 退出码 `0`，其余一律 `1`。
一页速览（交付物、mock/真实/未实现分列、已知限制、归属）见 [DELIVERY.md](DELIVERY.md)。

## 交付物

| 文件 | 作用 |
| --- | --- |
| `check_all.py` | 一条入口：按顺序跑下面六项检查并汇总退出码，真跑时自动 `--stop` 收尾 |
| `DELIVERY.md` | 一页交付说明：七件事现状、mock/真实/未实现分列、已知限制、失败归属 |
| `stack_config.py` | 统一配置入口：读 `data/private/stack.env` 或环境变量，校验缺项/占位密钥/端口冲突/CORS 通配，密钥不回显 |
| `stack.env.example` | 配置模板（入库，只有占位值），键名与模块 C 的 `agent-runtime/.env.example` 对齐（`CP_` 前缀） |
| `start_stack.py` | 组合启动：按登记表拉起 MySQL / Java / Python / Web 并判定就绪；未就绪即非零退出 |
| `stack_checks.py` | 判定层：期望分支匹配、Envelope 结构校验、五段式失败输出、HTTP 传输（可注入假传输做自测） |
| `check_stack.py` | 主链路检查：建会话 → record → audit → planning → replan，逐步断言状态码、Envelope 与业务字段 |
| `smoke_stack.py` | 异常与未知覆盖：Java 未接线、无班次快照不得断言时间、契约拒绝、无令牌/假令牌 |
| `web_checks.py` | 浏览器检查判定层：HTTP 探针驱动与 Playwright 驱动、挂载/失败提示/窄屏溢出的观察与判定 |
| `check_web.py` | 浏览器检查 CLI：主路径、答未知、服务失败、窄屏四类观察点，含 `--plan` 与 `--driver` |
| `tests/test_stack_config.py` | 配置入口自测（缺项、占位值、通配 CORS、端口冲突、来源优先级、掩码） |
| `tests/test_stack_checks.py` | 判定层自测（缺服务不许算过、DEGRADED 不算绿、编造必须被抓、失败块五段齐） |
| `stub_upstream.py` | 受控假响应服务：按 `Envelope` 契约返回固定响应，三个场景（只答未知 / 正常 / 上游不可用） |
| `check_stub.py` | 受控假响应检查：契约（domain schema）、可重复（两次响应逐字节相同）、不许编（不得给时间维度的核验） |
| `tests/test_web_checks.py` | 浏览器检查自测（页面没起算 BLOCKED、缺浏览器算 BLOCKED、白屏或缺重试入口必须 FAIL） |
| `tests/test_stub_upstream.py` | 受控假响应自测（可重复、只答未知、课程层核验、503、Envelope、裸奔与未知端点） |
| `../.github/workflows/integration-checks.yml` | 自动检查入口（CI job）：组合启动 + 主链路 + 异常覆盖 + 浏览器检查，失败工件留存 |

## 怎么跑

```bash
cp integration/stack.env.example data/private/stack.env   # 真实配置放这里（.gitignore 已覆盖）
python integration/stack_config.py --check                 # 只看配置校验，密钥显示为 ***
python integration/start_stack.py --plan                   # 只判定与打印计划，不启动进程，退出码与真跑一致
python integration/start_stack.py                          # 真启动并等待就绪
python integration/check_stack.py --plan                   # 主链路：只判定与打印计划
python integration/check_stack.py                          # 主链路：真跑
python integration/smoke_stack.py --plan                   # 异常覆盖：只判定与打印计划
python integration/smoke_stack.py                          # 异常覆盖：真跑
python integration/check_web.py --plan                     # 浏览器检查：只判定与打印计划
python integration/check_web.py                            # 浏览器检查：真跑（需先起页面）
python integration/check_web.py --driver playwright        # 指定真浏览器驱动
cd integration && python -m pytest -q                      # 自测（不联网、不起服务）
```

退出码约定：任一必需服务缺失、启动命令未登记、配置有 error、步骤判定不是 PASS（`--plan` 下是 PLAN）→ `1`。
**不允许 SKIP 算通过**：模块不存在报 `MISSING`，启动命令没依据报 `BLOCKED`，两者都算未就绪；
`--plan` 的退出码与真跑一致，避免用计划模式绕过判定。

## 判定等级（脚本、本文、PR 用同一组词）

| 等级 | 含义 |
| --- | --- |
| `PASS` | 服务真实、状态码与结构都对 —— 唯一算通过的等级 |
| `DEGRADED` | 契约正确但走受控缺口（Java 未接线、无真实模型）—— 单独列出，整轮不算通过 |
| `FAIL` | 服务在，但状态码、结构或语义不符契约 |
| `BLOCKED` | 前置服务未就绪（缺模块、命令未登记、端口不通），或依赖它的端点无法开始 |
| `PLAN` | `--plan` 只判定与打印，不连服务 |

失败输出固定五段：`requestId` / 步骤 / 期望 / 实际 / 退出码，另附可直接粘贴的复现命令；
复现命令里的会话令牌与密钥只留占位符。

## 主链路检查项（`check_stack.py`）

| 步骤 | 断言 | 依赖 | 当前预期 |
| --- | --- | --- | --- |
| sessions | `201` + Envelope(OK) + `sessionId/sessionToken/expiresAt` | api | 可真实通过 |
| record | `201` + Envelope(OK, AcademicRecord)；Java 未接线时 `503` issue=`TOOL_UNAVAILABLE` | api, java | 503，判 `DEGRADED` |
| audit | `200` + Envelope(OK, AuditResult)；Java 未接线时 `503` issue=`TOOL_UNAVAILABLE` | api, java | 503，判 `DEGRADED` |
| planning | `200` + Envelope(OK, PlanningAnswer)，`decision` 落在 RECOMMENDATIONS / CLARIFY / UNABLE_TO_VERIFY | api | W1 拒答，判 `DEGRADED` |
| replan | 同上，且同一 `Idempotency-Key` 重复提交必须返回同一份结果（不双跑） | api | 幂等命中，判 `DEGRADED` |

## 异常与未知覆盖检查项（`smoke_stack.py`）

| 用例 | 断言 | 说明 |
| --- | --- | --- |
| java_unwired | Java 未就绪时 audit 必须 `503` issue=`TOOL_UNAVAILABLE`，不得返回编造的核对结果 | Java 就绪时改为走 `200` 正常分支 |
| no_time_claim | 无班次快照时不得断言时间无冲突：`verification.scope` 不得是 `REAL_TIMETABLE` / `SIMULATION` | 该情形下「答未知或先澄清」判为通过 |
| bad_input | 违反契约的请求必须 `422` + Envelope(ERROR, issues 非空)，不得 `200` | 请求体取 `contracts/examples/invalid-block-day-with-section.json` |
| no_auth | 无令牌 → `401`；假令牌 → `404`；两者都不许 `200` | 对 `GET /api/v1/academic-records` |

## 浏览器检查项（`check_web.py`）

观察点全部取自 E 的页面实现与 README：`web/index.html`（挂载点 `#app`、`/src/main.ts`）、
`web/src/main.ts`（`createApp(...).mount("#app")`）、`web/src/App.vue`（品牌与模式徽标、footer 文案）、
`web/src/views/QuestionView.vue`（失败时的「重试」按钮）、`web/README.md`（真实模式网络失败显示错误与重试入口，不切换演示数据）。

| 检查项 | 观察 | 驱动 | 当前预期 |
| --- | --- | --- | --- |
| web_document | 入口文档 `200` 且含挂载点与入口脚本引用 | HTTP 即可 | 起页面后可过 |
| web_bundle | `/src/main.ts` 返回 `200` 且含 `createApp` | HTTP 即可 | 起页面后可过 |
| web_shell | 页面挂载成功、品牌/模式徽标/footer 齐备、无未捕获 JS 错误 | 需浏览器 | 缺 playwright 判 `BLOCKED` |
| web_api_down | Python 不可达时给出错误提示与重试入口、不白屏 | 需浏览器 | 需先停掉 Python 再跑 |
| web_unknown | 接口答未知/无法核验时如实呈现并可继续 | 需浏览器 + 受控假响应 | 假响应未做，判 `BLOCKED` |
| web_narrow | `390x844` 视口无横向溢出（`scrollWidth - clientWidth <= 2px`） | 需浏览器 | 缺 playwright 判 `BLOCKED` |

驱动两档：`--driver http` 只用标准库取文档与脚本；`--driver auto`（默认）在装了 playwright 时用真浏览器，
否则退回 HTTP 探针并把需要 JS 的检查判 `BLOCKED`。真浏览器装法：

```bash
python -m pip install playwright && python -m playwright install chromium
```

截图证据写到 `runs/stack/web/`（`runs/` 已被 `.gitignore` 覆盖）。

## 自动检查入口（CI job）

文件 `../.github/workflows/integration-checks.yml`，**挂法 B**：只手动触发 + 每天定时，不进 PR 门禁。
理由：门禁要防的是「假绿」，而现在会红的原因是 Java/MySQL 尚未落地；缺服务不该反过来挡住别人的 PR。
各模块到位后，再把这个 job 提为必过。

| 项 | 内容 |
| --- | --- |
| 触发 | Actions 页面手动 `workflow_dispatch`；每天定时 `30 1 * * *`（UTC，即北京时间 09:30） |
| 权限 | `contents: read`，不碰 Issue/Project |
| 服务 | MySQL 由 workflow 的 `services: mysql:8.4` 提供（含 healthcheck）；Java 目前没有 → 判 `MISSING` |
| 步骤 | 装 `integration[test]` 与 `agent-runtime[test]` → `npm ci` → 装 chromium → `check_all.py --driver playwright`（内部按同样的顺序跑六项检查，含受控假响应） |
| 门禁 | 全链路检查步骤或浏览器安装步骤不是 success → 末尾门禁步骤失败；不允许 SKIP 算通过 |
| 证据 | `runs/stack/`（服务日志、`check_web` 截图）上传为 `stack-evidence` 工件；五段式失败块在各步骤输出里 |
| 配置 | 只用环境变量注入 CI 专用值（`CP_*`），不在仓库里放密钥；缺必填项时 `stack_config` 直接失败 |

按当前依赖，这个 job 会是红的，且红的原因逐条可查：`record`/`audit` 停在 `DEGRADED`（Java 未落地）、
`planning` 停在 `DEGRADED`（C 的 W1 骨架拒答）、`web_api_down` 与 `web_unknown` 判 `BLOCKED`（需要停掉 Python／需要受控假响应）。
`smoke_stack` 的四条在 Python 起着的情况下应全绿 —— 它验证的正是「Java 缺失时必须报 503」这类异常行为。

## 失败登记与转交

每次失败按五段式输出（`requestId` / 步骤 / 期望 / 实际 / 退出码 + 复现命令），并按归属转交：

| 失败来源 | 转交 | 登记方式 |
| --- | --- | --- |
| `java_unwired`、`record`、`audit` 的 503/缺模块 | B（Java 模块） | Issue 评论附五段式 + 复现命令；需要修复时按 docs/18 §5 开 Bug 单 |
| `sessions`、`planning`、`replan`、`no_time_claim`、`bad_input`、`no_auth`、`web_unknown` | C（唯一 Runner） | 同上 |
| `web_*`（挂载、失败提示、窄屏） | E（页面） | 同上，附 `runs/stack/web/` 截图 |
| `stack_config`、`start_stack`、判定层本身 | D（本模块） | 直接在本分支修 |

「接口问题转交所有者」是 Issue #12 的相邻责任；本模块不替别人修业务 Bug，只提供可复现的失败证据与复测手段。

## 受控假响应（可重复）

```bash
python integration/check_stub.py                       # 起临时端口自检：契约 / 可重复 / 不许编
python integration/stub_upstream.py --port 8099        # 手动起一个（默认场景：资料不足只答未知）
python integration/check_web.py --with-stub --driver playwright   # 用它在 Python 端口当上游，检查页面能否进入引导第一问
```

| 检查项 | 断言 |
| --- | --- |
| stub_sessions / stub_curriculum | 201/200 + `Envelope`，且培养方案过 `$defs/SnapshotSummary` |
| stub_unknown | 默认场景必须 `decision=UNABLE_TO_VERIFY` 且不带推荐 |
| stub_repeatable | 同一请求发两次，响应逐字节相同（受控响应可重复） |
| stub_no_auth / stub_not_found | 无令牌 → 401；未知端点 → 404 |
| stub_normal | 正常场景给课程层推荐，`verification.scope` 不得是 `REAL_TIMETABLE` / `SIMULATION`，且过 `$defs/PlanningAnswer` |
| stub_unavailable | 上游不可用时 audit / planning 必须 503 `TOOL_UNAVAILABLE` |

边界：它**不是**真实服务，也不是 C 的模型适配器替身。C 的真实行为仍由 `check_stack.py` 对真实服务验证；
`--with-stub` 只用于驱动页面行为。每次请求与响应的 sha256 追加到 `runs/stack/stub/records.jsonl`。

## 服务登记表

| 服务 | 归属 | 实现清单（判断是否落地） | 启动命令 | 依据 |
| --- | --- | --- | --- | --- |
| mysql | B / 环境 | — | 未登记 | 本地启动方式环境相关；CI 侧用 workflow 的 `services: mysql` |
| java | B | `java-environment/pom.xml` | `./mvnw -B spring-boot:run` | Spring Boot 约定；待 B 的 README 确认后转正 |
| api | C | `agent-runtime/pyproject.toml` | `python -m uvicorn agent_runtime.api.app:app --port 8000` | `agent-runtime/README.md` 已登记（需先在该模块内 `pip install -e .[test]`） |
| web | E | `web/package.json` | `npm run dev` | Vite 约定；待 E 的 `package.json` 确认后转正 |

「未登记」不是跳过：脚本会把它判成 `BLOCKED` 并计入未就绪。启动命令只写已有书面依据的，不猜。

## 配置键（与模块 C 对齐）

| 键 | 服务 | 默认 | 说明 |
| --- | --- | --- | --- |
| `CP_MYSQL_HOST` / `CP_MYSQL_PORT` | mysql | `127.0.0.1` / `3306` | docs/03 默认端口 |
| `CP_MYSQL_DB` / `CP_MYSQL_USER` / `CP_MYSQL_PASSWORD` | mysql | 无默认（必填） | 口令只放环境变量或 `data/private/stack.env` |
| `CP_JAVA_BASE_URL` | java | `http://127.0.0.1:8080` | B 的事实 API |
| `CP_SERVICE_KEY` | java | 无默认（必填） | Python→Java 的 `X-Service-Key`（docs/04） |
| `CP_API_BASE_URL` | api | `http://127.0.0.1:8000` | C 的网关 |
| `CP_MODEL_BASE_URL` / `CP_MODEL_API_KEY` | api | 空 | 留空 = 用受控 stub；真实模型属每周验收另跑 |
| `CP_WEB_BASE_URL` / `CP_CORS_ORIGINS` | web / api | 5173 | CORS 只允许配置的 origin，禁通配 |
| `CP_HEALTH_TIMEOUT_SECONDS` / `CP_HEALTH_POLL_SECONDS` / `CP_START_COMMAND_TIMEOUT_SECONDS` | common | 60 / 2 / 180 | 就绪等待与轮询 |

## 与相邻模块的接口缺口（登记，转交所有者）

| 缺口 | 影响 | 转交 |
| --- | --- | --- |
| `agent-runtime` 未提供健康端点（无 `/health`） | 组合启动的就绪判定只能到 TCP 层，行为级就绪由主链路检查的第一步（建会话必须 `201`）承担 | C |
| `planning.openapi.json` 的 `listSessionRecords` 依赖 Java 侧 `listAcademicRecords` | 网关列表端点走 Java，未接线时只会 `503` | C / B |
| `java-environment` 无 `pom.xml` 与 `mvnw` | JVM 服务无法启动，`record`/`audit` 两步停在 `DEGRADED` | B |
| 页面缺少稳定的步骤标识（`data-testid` 之类） | 浏览器检查目前只能断言挂载、失败提示与版式，无法逐步断言「第 N 问推进到第 N+1 问」 | E |

## 边界

| 不做 | 原因 |
| --- | --- |
| 不实现各模块业务、不替别人修业务 Bug | Issue #12 的相邻责任 |
| 不用假响应替掉 Java / HTTP / DB / UI | 卡片规定：只有模型可以受控假响应 |
| 不在缺少书面依据时猜启动命令 | 猜错会把「未登记」伪装成「已接通」 |
| 不把 plan 模式当绿灯 | `--plan` 的退出码与真跑一致 |
| 不把 `DEGRADED` 说成通过 | 契约对但走的是受控缺口，交付说明里单独列 |
| 密钥不进仓库、不进日志 | 配置校验与打印都掩码；真实值只在环境变量或 `data/private/stack.env` |
