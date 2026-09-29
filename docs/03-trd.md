# 总体 TRD v0.2｜五周最小实现

本文件确定技术栈、进程、数据模型和接口。尚未实现；第 1 周用真实样本冻结 v1 契约。细节见[工作流规范](04-infrastructure-workflow.md)与[五份子 TRD](05-team-and-sub-trds.md)。

## 1. 技术栈定案

| 组件 | 建议技术 | 为什么选它，五周内做什么 |
| --- | --- | --- |
| 培养计划导入 | Java 21、Apache POI `WorkbookFactory`/`DataFormatter` | 原始文件是二进制 `.xls`；保留前导零、三种表型、来源坐标 |
| 真值与 API | Spring Boot、Spring Web、Bean Validation、JUnit 5 | 把规则核对封成 typed HTTP 工具，可独立测试 |
| 存储 | MySQL 8 + Spring Data JPA + Flyway（Docker Compose） | 存快照、课程、规则、已修样例和核验结果；迁移可重复 |
| Agent 服务 | Python 3.11+、FastAPI、Pydantic、httpx、一个 OpenAI-compatible 模型客户端 | 单 Agent 有界工具循环，Python 通过 HTTP 调 Java；不引入多 Agent 框架 |
| 页面 | Vue 3 + Vite + 原生 Fetch | 单页展示；浏览器只请求 Python API，Python 代理 Java 工具 |
| Benchmark/RSI | Python、pytest、JSONL/JSON、Git 内容 hash | 固定任务、逐条评分、候选 Prompt diff、晋级/回滚；不另起数据库 |

建议本地端口：Web `5173`、Agent `8000`、Java `8080`、MySQL `3306`。端口只是开发约定，配置可改。前端**不直接调用模型**；模型密钥只在 Python 服务环境变量中。Java 不导入 Python 代码，Python 不读 MySQL 表，只用 Java Tool API。

## 2. 最小目录和数据模型

- `java-environment/`: `importer/`, `domain/`, `rule/`, `api/`, `persistence/`, `src/test/`。
- `agent-runtime/`: `app.py`, `planner.py`, `tools.py`, `schemas.py`, `harness/`。
- `web/`: Vue 单页及 API client。现目录 `web/` 尚未创建。
- `benchmark/`: `cases/`, `labels/`, `runner.py`, `scorer.py`, `runs/`；留出集标签不能给 Evolver。
- `evo-harness/`: `miner.py`, `evolver.py`, `promotion.py`，只写 Harness 白名单。

MySQL 核心表：`source_snapshot(id, file_sha256, major, track, reviewed, imported_at)`；`course(code, title, credits, category, suggested_term, source_sheet, source_row, snapshot_id)`；`requirement(id, type, target, expression, review_status, source_sheet, source_row, snapshot_id)`；`completed_course(session_id, course_code, recognized_credits)`；`verification_result(id, snapshot_id, status, violations_json, unknowns_json, provenance_json)`。组合课程编号和文字备注先保存 `raw_value` 与审核状态，不强拆成伪单课。

## 3. 版本化接口（草案）

| 接口 | 调用者 | 结果 |
| --- | --- | --- |
| `GET /api/v1/snapshots` | Python/Web 经代理 | 已导入且人工核对的路径与文件版本 |
| `GET /api/v1/courses?snapshotId=...` | Python | 课程目录、类别、学分、建议学期和来源 |
| `POST /api/v1/requirements/audit` | Python | 已满足、缺口、未知项和规则依据 |
| `POST /api/v1/recommendations/validate` | Python | 建议课程代码是否存在/同路径、学分与已修重复；班次字段缺失时 `UNKNOWN` |
| `POST /api/v1/planning`（FastAPI） | Web | `taskId`、结构化答复、`verifierResultId`、引用与未知项 |

请求封套含 `schemaVersion, requestId, snapshotId`。Java 响应含 `status: OK|UNKNOWN|INVALID_INPUT|SNAPSHOT_MISMATCH|ERROR`、`data`、`provenance[]`、`warnings[]`。示例：

```json
{
  "schemaVersion":"1.0","requestId":"demo-001","snapshotId":"sha256:...",
  "status":"UNKNOWN","data":{"missingCredits":4},
  "provenance":[{"sheet":"计科学1","row":45,"field":"专业选修学分"}],
  "warnings":["缺少当学期班次快照，无法校验时间冲突"]
}
```

`UNKNOWN` 与 Java 500 错误分开处理。最终答复区分 `verifiedFacts[]`、`recommendations[]`、`unknowns[]`。任何学分差额要有 `requirementId`/来源；没有核验依据的 Agent 句子只能标建议。

## 4. Agent 的实际运行算法

1. Pydantic 解析用户输入，检查路径、已修课、目标。歧义影响规则时先澄清。
2. 最多 4 次 Tool 调用（计划值）：查目录/要求、核对已修、验证建议；工具返回保存 Trace。
3. LLM 只能根据工具结果提出至多 3 条建议课程；建议必须交 Java 验证。没有班次时，不输出可行课表。
4. 若验证失败，最多一次自动修正；仍失败则返回问题与可选操作。最终答复附 `verifierResultId` 与来源。
5. 模型/工具超时后返回结构化错误，不把缺失数据当正常值。

## 5. 评测与受控进化

数据源 hash、Java verifier commit、模型配置、Harness 内容 hash、Benchmark 集合 hash 一起写 `run-manifest.json`。Trace 只保存模型输入摘要、工具调用和输出引用、错误码、耗时，不保存完整思维链。Evolver 只可改 `harness/prompts/` 与 `harness/tool-descriptions/`，先用训练失败 Trace 生成小 diff，之后跑训练/开发/封存留出。任何硬错误增加或留出成功例退化都回滚；晋级/回滚决定写审计文件。具体案例与算分见[Benchmark 协议](07-benchmark-protocol.md)。

## 6. 五周集成策略

第一周冻结真实字段与 API v1；第二周 Java 工具可被 curl 调通；第三周网页经 Python 调 Java 跑通一条完整路径；第四周形成基线与坏例；第五周一次真实候选修改/复评/回滚演示。每周都留可运行的主分支，避免五人到最后才合并。
