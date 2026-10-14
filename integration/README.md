# D2 集成检查（D-F3）：组合启动与统一配置入口

对应 Issue #12。目标：从输入到推荐和调整的流程可重复检查，**服务缺失和失败会被发现**；
模型可用受控假响应，但 Java / HTTP / DB / UI 必须真实。

现在是 **W1 骨架**：配置入口与组合启动脚本可用，四个服务尚未落地，跑起来会如实报缺谁。

## 交付物

| 文件 | 作用 |
| --- | --- |
| `stack_config.py` | 统一配置入口：读 `data/private/stack.env` 或环境变量，校验缺项/占位密钥/端口冲突/CORS 通配，密钥不回显 |
| `stack.env.example` | 配置模板（入库，只有占位值），键名与模块 C 的 `agent-runtime/.env.example` 对齐（`CP_` 前缀） |
| `start_stack.py` | 组合启动：按登记表拉起 MySQL / Java / Python / Web 并判定就绪；未就绪即非零退出 |
| `tests/test_stack_config.py` | 配置入口的自测（缺项、占位值、通配 CORS、端口冲突、来源优先级、掩码） |

## 怎么跑

```bash
cp integration/stack.env.example data/private/stack.env   # 真实配置放这里（.gitignore 已覆盖）
python integration/stack_config.py --check                 # 只看配置校验，密钥显示为 ***
python integration/start_stack.py --plan                   # 只判定与打印计划，不启动进程，退出码与真跑一致
python integration/start_stack.py                          # 真启动并等待就绪
```

退出码约定：任一必需服务缺失、启动命令未登记、配置有 error、或超时就绪 → `1`。
**不允许 SKIP 算通过**：模块不存在时报 `MISSING`，启动命令没依据时报 `BLOCKED`，两者都算未就绪。

## 服务登记表

| 服务 | 归属 | 实现清单（判断是否落地） | 启动命令 | 依据 |
| --- | --- | --- | --- | --- |
| mysql | B / 环境 | — | 未登记 | 本地启动方式环境相关；CI 侧用 workflow 的 `services: mysql` |
| java | B | `java-environment/pom.xml` | `./mvnw -B spring-boot:run` | Spring Boot 约定；待 B 的 README 确认后转正 |
| api | C | `agent-runtime/pyproject.toml` | 未登记 | 待 C 的 README 登记启动命令（PR #11 尚未写） |
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

## 边界

| 不做 | 原因 |
| --- | --- |
| 不实现各模块业务、不替别人修业务 Bug | Issue #12 的相邻责任 |
| 不用假响应替掉 Java / HTTP / DB / UI | 卡片规定：只有模型可以受控假响应 |
| 不在缺少书面依据时猜启动命令 | 猜错会把「未登记」伪装成「已接通」 |
| 不把 plan 模式当绿灯 | `--plan` 的退出码与真跑一致，避免用计划模式绕过判定 |
| 密钥不进仓库、不进日志 | 配置校验与打印都掩码；真实值只在环境变量或 `data/private/stack.env` |
