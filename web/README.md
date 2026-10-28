# CoursePilot E1 学生页面

E1 使用 Vue 3、Vite、TypeScript、Vue Router 和 Pinia，完成一次一问的引导流程：固定八个问题——目标收集、上课与考核偏好、发展方向、兴趣主题、教师偏好、课表网格上的必须/尽量避开时段、目标优先级确认和资料核对；已发布培养方案多于一份时，在最前面插入培养方案选择，最多九步。每个问题都向全部学生展示，都可以留空跳过。页面仅挂载当前问题；答案保存在 Pinia 内存状态中，刷新后匿名会话和答案都不会恢复。

## 启动

环境要求见 `package.json` 的 `engines`：Node.js 22 或更新版本。

```bash
npm ci
npm run dev
```

Vite 默认监听 `http://127.0.0.1:5173`。可用以下命令检查页面服务是否启动并返回入口文档：

```bash
curl --fail --silent --show-error http://127.0.0.1:5173/
```

没有完整系统健康检查接口。Python OpenAPI 当前也没有 `/health` 路由；真实服务连通性由页面实际创建匿名会话并读取已发布培养方案来确认。Vite 返回页面只能证明前端进程在运行，不能证明 Python 或 Java 服务可用。

## 运行模式

### 使用本地服务运行虚构数据

下面的三个终端分别启动 Java、Python 和网页。需要 Java 21、Python 3.11+、Node.js 22+；Python 已安装 `agent-runtime` 的依赖，网页已执行 `npm ci`。

```bash
# 终端 1，仓库根目录：使用临时内存数据库和虚构种子
cd java-environment
COURSEPILOT_SERVICE_KEY=local-demo-key SPRING_DATASOURCE_URL='jdbc:h2:mem:coursepilot-demo;DB_CLOSE_DELAY=-1' ./mvnw spring-boot:run
```

```bash
# 终端 2，仓库根目录：首次使用先安装 pip install -e './agent-runtime[test]'
cd agent-runtime
CP_JAVA_BASE_URL=http://127.0.0.1:8081 CP_SERVICE_KEY=local-demo-key python -m uvicorn agent_runtime.api.app:app --host 127.0.0.1 --port 8000
```

```bash
# 终端 3，仓库根目录
cd web
VITE_COURSEPILOT_MODE=simulation npm run dev
```

打开 `http://127.0.0.1:5173`，选择目标，在资料页填写虚构课程（例如 `CS101`、3 学分），返回问答页提交规划。此模式连接本地 Java 和 Python，使用虚构培养方案；未配置真实模型时结果会标明假模型。临时数据库在 Java 停止后清空。

- **真实服务模式**是默认模式。可用 `VITE_API_BASE_URL` 指定 Python 服务地址，未设置时为 `http://127.0.0.1:8000`。启动示例：

  ```bash
  VITE_COURSEPILOT_MODE=http VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev
  ```

  页面只经唯一 API client 调用 Python。网络失败、超时或响应不符合契约时显示错误和重试入口，不会切换成演示数据。

- **演示模式**必须显式选择，数据和模式徽标都会标为虚构：

  ```bash
  VITE_COURSEPILOT_MODE=fixture npm run dev
  ```

  它使用固定的虚构培养方案、学业记录和规划结果，不调用后端服务。

匿名 bearer 只存于当前页面内存，不进入 URL、`localStorage`、`sessionStorage` 或应用日志。页面按 `expiresAt` 安排过期清理；真实服务端返回 401 或会话过期时，会中止在途请求、清除会话凭据和培养方案上下文并提示重新开始。已填写的选课目标暂留在当前页面内存，新会话建立后可继续；刷新页面会清空会话与答案。

## 当前交付边界

页面支持创建会话、选择培养方案、读取和补录学业记录、学业核对以及规划结果展示。真实模式要求来源已核验的培养方案；`simulation` 模式使用合成数据和本地 Java/Python 服务。浏览器已使用合成数据完成学业补录、核对、规划及教师与时间条件的澄清回填。当前没有经核验的真实当期班次；默认模型为受控假模型，结果会标明该状态。老师报告接口尚未接入真实报告。

`buildPlanningRequest` 根据已确认的目标、分别填写的必须/偏好时间条件、可选课程考核偏好和会话上下文构造请求，并用仓库中的 `contracts/schemas/domain.schema.json` 验证。只有在相关偏好页、同一时间页的两组条件和目标顺序都明确检查后才能交接；页面允许不选任何偏好或时段，留空表示没有这类要求。确认页列出目标排序、各项偏好、培养方案来源和学业记录状态，并说明真实模式缺少哪些资料。E1 只负责把答案整理成请求；提交与结果展示属于 E2，见下一节。

时间页用课表网格收集条件：横轴星期、纵轴节次，点选或拖动涂选具体时段，同一页分「必须避开」和「尽量避开」两组。整列归一为 `BLOCK_DAY`，剩余格子中整行归一为 `BLOCK_SECTION`，其余散格为 `BLOCK_SLOT`；软偏好对应 `schedule.blocked_day`/`blocked_section`/`blocked_slot`。两组答案同时存在。归一后超过合同上限 30 条时给出「改用整行或整列」的可操作提示，不静默截断。

上课与考核偏好向全部学生展示，可以全部不选，不按动机隐藏题目。六项选择通过 `softPreferences` 交接，并传入模型请求；偏好对实际推荐的效果还需要真实模型和评价资料验证。

选择“指定教师”时会说明教师必须和课程绑定，并交接到 E3 的课程教师选项；没有实际选项时页面不创建教师、教师键或班次。教师“必须保留”与“优先考虑”由拿到真实选项的后续步骤写入合同字段。

## E2：学业资料、核对与结果

路由：`/records`（学业资料与核对）、`/plan/result`（规划结果）。作答页在缺学业记录时给出「去补充学业资料」入口。

- **学业资料**：进入 `/records` 先读本会话记录；`items` 为空数组是**正常业务状态而非错误**，此时才走补录。核对结果按「还差 / 无法确认 / 已满足」三组展示，`UNKNOWN` 永远单独成组，页面结构上无法把它渲染成「已满足」。学分缺口未知时保持 `null`，不写成 0。
- **提交与结果**：`/plan/result` 展示 `decision`（`CLARIFY` / `RECOMMENDATIONS` / `UNABLE_TO_VERIFY`）、候选与依据，以及答复级与候选级的未知项（按 `code`+`message` 去重）。
- **展示门禁**：只有 `scope=REAL_TIMETABLE` 且 `verdict=VALID` 才允许显示为通过，`domain/answer-display.ts` 是全站唯一判定处。`COURSE_ONLY + VALID` 仍是「时间待确认」；`SIMULATION + VALID` 必须标注「不代表本学期课表」。页面不从 `violations` 为空推断通过，也不计算学分、不解析时间。
- **幂等与竞态**：同一份请求重试复用同一个 `Idempotency-Key`，条件变化后换新键（`domain/idempotency.ts`）。改任何条件都会中止在途提交并按版本号丢弃迟到响应；重复点击在提交期间被忽略。
- **澄清回填范围**：结果页支持固定问题 `tradeoff:teacher-vs-schedule` 的两个选项，并把选择写入请求优先顺序后重新提交。此选择不会删除 MUST 教师或必须避开的时段；冲突仍由核验服务返回。其他模型生成的澄清题暂不支持结构化回填。教师比较页面已用合成数据连接后端；老师报告接口仍是桩。

## 依赖与检查

`package.json` 固定直接依赖，`package-lock.json` 固定完整安装图。CI 和 `scripts/check_modules.py` 使用 `npm ci`，再运行以下固定检查入口：

```bash
npm run lint
npm run typecheck
npm run test:unit
npm run build
```

`test:unit` 还运行独立 HTML 原型的 Node 分支测试和 HTML 结构/内联脚本检查。测试覆盖目标分支和路由限制、返回保留、同页并列的必须与偏好时间、空白继续、优先级显式确认、课程考核偏好条件及清理、硬/软条件独立交接、PlanningRequest 契约校验、HTTP 错误封套、无静默 fixture fallback、重复启动、401 失效和迟到会话响应；E2 追加了学业记录三态分组与 UNKNOWN 隔离、空列表不算错误、补录入参去空白、记录选中的归属、真实 `academicRecordId` 进入请求、核对结果作废旧请求、展示门禁真值表（含 `COURSE_ONLY + VALID` 不许判通过）、未知项去重、幂等键复用与轮换、重复提交、迟到答复丢弃。它们不代替真实后端联调或浏览器桌面、窄屏、键盘检查。真实服务尚未就绪时，后端联调仍未验证。

页面不使用 `v-html`，用户可见输入通过普通文本控件呈现。焦点样式、label、状态提示、小屏布局均在源码中提供，键盘和实际浏览器评审仍需按 [E 模块 TRD](../docs/trd/e-web-integration.md) 执行。
