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

- **真实服务模式**是默认模式。可用 `VITE_API_BASE_URL` 指定 Python 服务地址，未设置时为 `http://127.0.0.1:8000`。启动示例：

  ```bash
  VITE_COURSEPILOT_MODE=http VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev
  ```

  页面只经唯一 API client 调用 Python。网络失败、超时或响应不符合契约时显示错误和重试入口，不会切换成演示数据。

- **演示模式**必须显式选择，数据和模式徽标都会标为虚构：

  ```bash
  VITE_COURSEPILOT_MODE=fixture npm run dev
  ```

  它展示一份固定的 synthetic 培养方案和虚构学业记录，PlanningRequest 使用 `SIMULATION`。演示不会调用真实规划接口，也不会生成课程推荐。

匿名 bearer 只存于当前页面内存，不进入 URL、`localStorage`、`sessionStorage` 或应用日志。页面按 `expiresAt` 安排过期清理；真实服务端返回 401 或会话过期时，会中止在途请求、清除会话凭据和培养方案上下文并提示重新开始。已填写的选课目标暂留在当前页面内存，新会话建立后可继续；刷新页面会清空会话与答案。

## 当前交付边界

页面按合同实现了匿名会话创建和 `GET /api/v1/curriculum-snapshots` 已发布培养方案读取调用；Python 服务尚未实现，所以真实后端联调仍待完成。真实模式会过滤合成培养方案；即使提供了快照 ID，`PlanningRequest` builder 也只接受来源已核验的真实培养方案。当前契约没有按当前会话发现或读取学业记录的端点；虽然定义了按已知 ID 读取和创建记录的接口，E1 没有记录录入与 ID 来源流程。因此真实模式不会要求学生填写内部编号，也不会伪造 `academicRecordId`；没有真实、已核验的培养方案和学业记录时，不会生成 REAL 请求。

`buildPlanningRequest` 根据已确认的目标、分别填写的必须/偏好时间条件、可选课程考核偏好和会话上下文构造请求，并用仓库中的 `contracts/schemas/domain.schema.json` 验证。只有在相关偏好页、同一时间页的两组条件和目标顺序都明确检查后才能交接；页面允许不选任何偏好或时段，留空表示没有这类要求。确认页列出目标排序、各项偏好、培养方案来源和学业记录状态，并说明真实模式缺少哪些资料。真实模式只有在后续资料流程提供真实培养方案和学业记录 ID 后才会得到有效请求。E1 当前不提交 `/planning`，不展示推荐结果。

时间页用课表网格收集条件：横轴星期、纵轴节次，点选或拖动涂选具体时段，同一页分「必须避开」和「尽量避开」两组。整列归一为 `BLOCK_DAY`，剩余格子中整行归一为 `BLOCK_SECTION`，其余散格为 `BLOCK_SLOT`；软偏好对应 `schedule.blocked_day`/`blocked_section`/`blocked_slot`。两组答案同时存在。归一后超过合同上限 30 条时给出「改用整行或整列」的可操作提示，不静默截断。

上课与考核偏好向全部学生展示，可以全部不选，不按动机隐藏题目。六项选择通过 `softPreferences` 交接。公共 Schema 只规定 dimension/value 为字符串；Python/Agent 消费端尚未实现或确认这些语义，页面和本地构建器不能据此承诺推荐系统已经支持高分、少签到或特定考核方式。

选择“指定教师”时会说明教师必须和课程绑定，并交接到 E3 的课程教师选项；没有实际选项时页面不创建教师、教师键或班次。教师“必须保留”与“优先考虑”由拿到真实选项的后续步骤写入合同字段。

## 依赖与检查

`package.json` 固定直接依赖，`package-lock.json` 固定完整安装图。CI 和 `scripts/check_modules.py` 使用 `npm ci`，再运行以下固定检查入口：

```bash
npm run lint
npm run typecheck
npm run test:unit
npm run build
```

`test:unit` 还运行独立 HTML 原型的 Node 分支测试和 HTML 结构/内联脚本检查。测试覆盖目标分支和路由限制、返回保留、同页并列的必须与偏好时间、空白继续、优先级显式确认、课程考核偏好条件及清理、硬/软条件独立交接、PlanningRequest 契约校验、HTTP 错误封套、无静默 fixture fallback、重复启动、401 失效和迟到会话响应。它们不代替真实后端联调或浏览器桌面、窄屏、键盘检查。真实服务尚未就绪时，后端联调仍未验证。

页面不使用 `v-html`，用户可见输入通过普通文本控件呈现。焦点样式、label、状态提示、小屏布局均在源码中提供，键盘和实际浏览器评审仍需按 [E 模块 TRD](../docs/trd/e-web-integration.md) 执行。
