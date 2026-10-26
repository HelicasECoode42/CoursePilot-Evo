# D2 交付说明（一页）

Issue #12 ｜ 模块 D（验收、评测与策略改进）｜ 功能 D-F3 ｜ 分支 `feat/d2-integration`

一句话：D2 让「从输入到推荐和调整」的整条链路可以被重复检查，并且**服务缺失、流程中断、异常返回都会被报出来** ——
缺了不许跳过算过。

## 一条入口（新环境）

```bash
cp integration/stack.env.example data/private/stack.env   # 真实配置只放这里（.gitignore 已覆盖）
python integration/check_all.py                           # 配置校验 → 组合启动 → 主链路 → 异常覆盖 → 受控假响应 → 浏览器检查
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
| 3 | 集成测试 | `integration/check_stack.py`（建会话 → record → audit → planning → replan） | 框架完成；Java 已实现 `audit`，但 `POST /api/v1/academic-records` 在 Java 侧仍没有，所以 record 这一步仍判 `DEGRADED` |
| 4 | 异常与未知覆盖 | `integration/smoke_stack.py`（四条） | 框架完成 |
| 5 | 浏览器检查 | `integration/check_web.py` + `web_checks.py`（七项） | 本机已真跑：4 项 `PASS`、2 项 `BLOCKED`、1 项 `FAIL`（后者是页面缺陷，见「已知限制」）。**这组数字记录于 Java 落地与 `fetch` 修复之前，尚未复跑** |
| 6 | 自动检查入口 | `.github/workflows/integration-checks.yml` | 完成（挂法 B：手动 + 每天定时，不进 PR 门禁） |
| 7 | 交付物 | `integration/check_all.py` + 本文件 | 完成 |
| 附 | 受控响应可重复（验收条件 2） | `integration/stub_upstream.py` + `check_stub.py` | 完成（7 项自检全 PASS） |

## mock / 真实 / 未实现分列

| 类别 | 内容 | 现状与证据 |
| --- | --- | --- |
| 真实（必须真实，也已真实） | HTTP 与页面：Python 网关按契约真实响应，页面服务真实返回入口文档与入口模块；契约与字段以 `contracts/` 为真源 | 本地实测：配置校验退出码 `0`；页面未起时判 `BLOCKED` 而不是 SKIP |
| 真实但依赖未到 | Java 模块已落地（8 个路由，其中 `audit` 可用）；MySQL 当前不在技术栈里——Java 用的是 H2 文件库，pom 无 MySQL 驱动与 Flyway | 缺 Java 接线时判 `DEGRADED`，`java_unwired` 断言「必须报 503」；mysql 已按「当前不适用」登记，不计入就绪也不挡退出码 |
| 受控假响应（已实现） | `integration/stub_upstream.py`：按 `Envelope` 契约返回**固定**响应，三个场景（只答未知 / 正常 / 上游不可用）；`check_stub.py` 断言契约、可重复（两次响应逐字节相同）与「不得给时间结论」 | 本机实测 7 项全 `PASS`；记录在 `runs/stack/stub/records.jsonl`。模型端点留空时 C 仍走 W1 stub（无真实模型调用） |
| 未实现 | Java 契约里仍缺 10 个路径+方法（`plans/validate`、`teacher-course-options`、`reviews/search` 等）、MySQL 本体、页面稳定步骤标识、CI 常驻真浏览器；C 的真实模型适配器已实现，但未配 `CP_MODEL_*` 时默认走受控假实现 | 逐条登记在 `README.md` 的「与相邻模块的接口缺口」表并注明归属 |

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

- 主链路的「正常分支」目前仍拿不到完整一条：Java 的 `audit` 已可用，但 record 写入与 `plans/validate` 在 Java 侧没有，所以只能取得「缺接线时如实报错」的证据。
- 受控假响应已实现并自检通过，但 planning 的**真实**正常分支仍要等 C 接上模型与 Java；页面「答未知」分支还需要页面的稳定步骤标识（E）。
- 真浏览器：本机复用已装的 Edge（`channel=msedge`），CI 里装 chromium；装了 playwright 才有真跑，否则判 `BLOCKED`，不跳过、不算过。
- ~~页面真实模式无法连接后端~~：`fetch` 未绑定导致的 `Illegal invocation` 已由提交 `09a5e68` 修掉。上面第 5 行记录的 `web_stub_path` `FAIL` 与 `web_api_down` `BLOCKED` 是修复前的结果，尚未在浏览器里复测。
- 本模块不实现各模块业务、不替别人修业务 Bug，只提供可复现的失败证据与复测手段。

## 证据在哪

- 终端输出：五段式失败块（可直接作为 Issue 评论与转交原文）
- `runs/stack/`：服务日志（`api.log`、`web.log`）、浏览器截图（`web/*.png`）、PID 文件、受控假响应记录（`stub/records.jsonl`）
- CI：工件 `stack-evidence`，job 名 `integration-checks`
