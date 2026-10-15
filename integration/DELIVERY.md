# D2 交付说明（一页）

Issue #12 ｜ 模块 D（验收、评测与策略改进）｜ 功能 D-F3 ｜ 分支 `feat/d2-integration`

一句话：D2 让「从输入到推荐和调整」的整条链路可以被重复检查，并且**服务缺失、流程中断、异常返回都会被报出来** ——
缺了不许跳过算过。

## 一条入口（新环境）

```bash
cp integration/stack.env.example data/private/stack.env   # 真实配置只放这里（.gitignore 已覆盖）
python integration/check_all.py                           # 配置校验 → 组合启动 → 主链路 → 异常覆盖 → 浏览器检查
python integration/check_all.py --plan                    # 只看计划：不起进程、不连服务
python integration/check_all.py --keep                    # 跑完保留服务，自己排查
python integration/start_stack.py --stop                  # 随时收掉服务（PID 记在 runs/stack/pids.json）
```

退出码只有两种：全 `PASS` 为 `0`，其余（`BLOCKED` / `DEGRADED` / `FAIL`）一律 `1`。

## 七件事现状

| # | 做什么 | 产出 | 状态 |
| --- | --- | --- | --- |
| 1 | 组合启动脚本 | `integration/start_stack.py`（含 `--plan` / `--keep` / `--stop`） | 完成 |
| 2 | 统一配置入口 | `integration/stack_config.py` + `stack.env.example` | 完成（15 条自测） |
| 3 | 集成测试 | `integration/check_stack.py`（建会话 → record → audit → planning → replan） | 框架完成；Java 未落地时 record/audit 判 `DEGRADED` |
| 4 | 异常与未知覆盖 | `integration/smoke_stack.py`（四条） | 框架完成 |
| 5 | 浏览器检查 | `integration/check_web.py` + `web_checks.py`（六项） | 框架完成；需执行 JS 的四项等真浏览器 |
| 6 | 自动检查入口 | `.github/workflows/integration-checks.yml` | 完成（挂法 B：手动 + 每天定时，不进 PR 门禁） |
| 7 | 交付物 | `integration/check_all.py` + 本文件 | 完成 |

## mock / 真实 / 未实现分列

| 类别 | 内容 | 现状与证据 |
| --- | --- | --- |
| 真实（必须真实，也已真实） | HTTP 与页面：Python 网关按契约真实响应，页面服务真实返回入口文档与入口模块；契约与字段以 `contracts/` 为真源 | 本地实测：配置校验退出码 `0`；页面未起时判 `BLOCKED` 而不是 SKIP |
| 真实但依赖未到 | MySQL 由 CI 的 `services: mysql:8.4` 提供真实容器；Java 模块尚未落地 | 缺 Java 时 record/audit 判 `DEGRADED`，`java_unwired` 断言「必须报 503」 |
| 受控假响应 | 模型端点留空时走 C 的 W1 stub（无真实模型调用）；**受控假响应服务本身尚未实现** | C 的 `PlanningRunner` 在有目标时返回 `UNABLE_TO_VERIFY`，不伪造推荐；受控 stub 服务待做 |
| 未实现 | Java / MySQL 模块本体、受控假响应服务、页面稳定步骤标识、CI 常驻真浏览器 | 逐条登记在 `README.md` 的「与相邻模块的接口缺口」表并注明归属 |

## 判定与转交

判定五个词：`PASS` / `DEGRADED` / `FAIL` / `BLOCKED` / `PLAN`。失败按五段式输出
（`requestId`、步骤、期望、实际、退出码 + 复现命令），归属如下：

| 失败来源 | 归属 |
| --- | --- |
| `java_unwired`、`record`、`audit` 的 503 与缺模块 | B |
| `sessions`、`planning`、`replan`、`no_time_claim`、`bad_input`、`no_auth`、`web_unknown` | C |
| `web_*`（挂载、失败提示、窄屏） | E |
| 配置入口、组合启动、判定层、本入口自身 | D |

## 已知限制（如实）

- 主链路与浏览器检查里的「正常分支」目前拿不到：Java 未落地，只能取得「缺服务时如实报错」的证据。
- 受控假响应未实现，因此 planning 的正常推荐分支与 `web_unknown` 无法验证。
- 真浏览器（playwright + chromium）本机与 CI 都未默认安装：需要执行 JS 的检查一律判 `BLOCKED`，不跳过、不算过。
- 本模块不实现各模块业务、不替别人修业务 Bug，只提供可复现的失败证据与复测手段。

## 证据在哪

- 终端输出：五段式失败块（可直接作为 Issue 评论与转交原文）
- `runs/stack/`：服务日志（`api.log`、`web.log`）、浏览器截图（`web/*.png`）、PID 文件
- CI：工件 `stack-evidence`，job 名 `integration-checks`
