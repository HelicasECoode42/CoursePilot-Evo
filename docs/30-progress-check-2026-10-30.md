# 进度核对（2026-10-30）

核对对象：分支 `feat/b-contract-endpoints` 的工作区现状（含大量未提交改动）。
方法：读代码 + 跑 web 与 agent-runtime 测试 + 只读探测线上域名。没有跑 Java 测试，没有改任何服务。

## 一句话结论

"前端 OK、AI 接口没写"不准确。**接口和 AI 对话的代码都已写好，本机三个服务也在用真模型 + 真 Java 跑着；真正缺的是：线上隧道没开、评测/演化没做、部署没登记进仓库。**

## 各模块状态

| 模块 | 状态 | 依据 | 缺口 |
|---|---|---|---|
| Web（Vue） | 能用 | 默认走真实 HTTP，`/api` 由 Vite 代理到 8000；`npx vitest run` 435 项全过 | E2 整体联调未验收（见 `docs/trd/e-web-integration.md`）；教师比较、老师报告未验收 |
| Python 网关 | 基本能用 | `contracts/planning.openapi.json` 的 19 个接口都有路由；`pytest` 233 项全过 | `GET /api/v1/reports/runs/{runId}` 只会返回 NOT_FOUND；没有 `/health` |
| AI 模型接入 | 已写，本机在用真模型 | 配了 `CP_MODEL_BASE_URL` + `CP_MODEL_API_KEY` 才走真模型，否则用假模型；本机 8000 进程已带这两项 | 仓库里没有 `.env` 示例，新人默认拿到的是假模型 |
| AI 对话（advice chat） | 已写，未提交 | `api/routes/advice_chat.py` 等新文件 + `web/src/components/AdviceChat.vue` | 文件仍是 untracked；`docs/checkpoints/advice-chat.md` 说真实验收过，本次没复跑 |
| Python → Java | 能通 | 配 `CP_JAVA_BASE_URL` 才真调，不配直接 503；本机已配 | — |
| Java 核验服务 | 部分 | Spring Boot，8081，H2；21 个测试文件 | 本次没跑 `mvn test`，结果未验证 |
| 浏览器插件（学业导入） | 开发版能用 | 只接受 `localhost:5173` 来源 | 不支持线上域名 |
| 评测 / 演化（D） | 未实现 | `benchmark/` 只有骨架，评分是关键词占位；`evo-harness/` 只有 README | held-out、Promote/Rollback 都没落地 |
| 部署 | 未登记 | 仓库里没有 Dockerfile/compose/部署脚本，搜不到 `helicase` | 线上怎么起只存在于本机，没人能复现 |

## 线上 coursepilot.helicase.xin

- `coursepilot.helicase.xin`：返回 Cloudflare 530 / 1033，意思是**隧道没有连接器在线**。
- `www.coursepilot.helicase.xin`：核对时**没有 DNS 记录**。后来已加 CNAME，但免费证书不覆盖这一级子域，HTTPS 仍打不开（见 `docs/33`）。
- 源站就是这台 Mac：Vite 5173、Python 8000、Java 8081 都在跑，但 `cloudflared` 没在跑。隧道 `coursepilot-demo` 存在，当前 0 个连接；`~/.cloudflared/` 下没有 config 文件。

要让外网能访问，至少要做三件事：

1. Vite 带上隧道域名重启，否则外部请求会被 Vite 以 Host 不允许拦掉：
   `COURSEPILOT_TUNNEL_HOST=coursepilot.helicase.xin VITE_API_BASE_URL=https://coursepilot.helicase.xin npm run dev`（在 `web/` 下）。
   `VITE_API_BASE_URL` 必须设：不设时页面会去请求访问者自己电脑上的 `127.0.0.1:8000`。
2. 开隧道：`cloudflared tunnel run --url http://localhost:5173 coursepilot-demo`。
3. 需要 `www.` 的话，在 Cloudflare 后台给它加一条指向该隧道的 CNAME。

注意：这样等于把本机开发服务器公开到公网。`docs/04` 写明公开部署要另做认证、限流、CORS，目前都没做。

## 文档和代码对不上的地方

- `docs/trd/c-agent.md` 写 81 个测试，实际 233。
- `integration/DELIVERY.md` 说 Java 缺 10 个路径，其中 `plans/validate`、`reviews/search`、`teacher-course-options` 已经有了。
- `docs/trd/a-data.md` 说"尚无导入实现"，但 `java-environment/importer/` 有 XLSX 导入代码（是否完整未核）。
- `docs/03` 写 Java 端口 8080，实际是 8081。

## 建议的下一步（按优先级）

1. 把 advice chat 等未提交改动整理提交，否则队友看不到。
2. 把线上启动方式写进仓库（一个脚本或 README 小节），并加一个 `/health`。
3. 修正上面四处过时文档。
4. D 模块评测/演化仍是空白，需要排人。
