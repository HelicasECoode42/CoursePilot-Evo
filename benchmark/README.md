# 四组 Benchmark（待标注/待实现）

## 外部 HTTP Runner（evolution 基线）

`run_benchmark.py` 复用 PR36 的逐例 HTTP 调用、请求契约校验、逐例报告、用量记录、重复运行比较和失败归因骨架；适配当前 `/api/v1/sessions`、`/api/v1/planning`、学业记录、培养要求核查及评价查询响应信封。该 Runner 调用运行中的 Python API，不实现第二个 Agent。当前不运行 held-out，也不执行晋级或 patch 生成。

默认不读取 gold/私有判据。无人工判据的案例记 `UNSCORED`，同时将 `FAKE_MODEL` 等合成标记单独记为 `assessmentStatus=DEGRADED_SYNTHETIC`；不得把它计入通过率。即使显式提供 gold，默认 `keyword_matcher` 也只生成词元覆盖基线，状态仍为 `UNSCORED_KEYWORD_BASELINE`；要形成可用于质量判定的分数，调用方必须注入有明确定义的 matcher，且要求的 `SourceRef` 均由 JavaVerifier 核验。token 缺失保持 `null`。单次运行的 `repeatStable` 为 `null`；多次运行分别报告判定差异和用量差异。失败归因仅聚合至少两个不同案例中重复出现的可观测类别，`likelyCause` 保持“原因未查明”。

以当前 contracts 校验随仓示例 manifest，并先只规划虚构 smoke 题面：

```bash
python benchmark/run_benchmark.py \
  --manifest benchmark/manifests/synthetic-smoke.json \
  --cases-root benchmark/cases/smoke \
  --plan
```

连接本地 Python API 的合成运行：

```bash
python benchmark/run_benchmark.py \
  --manifest benchmark/manifests/synthetic-smoke.json \
  --cases-root benchmark/cases/smoke \
  --base-url http://127.0.0.1:8002 \
  --out /tmp/coursepilot-benchmark-synthetic
```

合成 HTTP 案例格式是 Runner 专用输入，不能当作标准 CasePrompt rubric。该命令需要 API 以 `CP_USE_FAKE_TOOLS=true`、无 `CP_MODEL_BASE_URL` 运行。此处所有输入与模型输出均为合成数据，案例无人工判据，因此会记为 `UNSCORED`，进程返回非零；`assessmentStatus=DEGRADED_SYNTHETIC` 标记假模型输出。默认没有任何非合成 gold 路径；若要对已审核标注评分，必须显式传入 `--gold-root`，并注入非默认 matcher 与 JavaVerifier。`--plan` 不发 HTTP 请求；只有非空案例集全部可构造时才返回成功。逐例状态与分数覆盖率写入 `cases.jsonl`、`summary.json`；符合公共契约的聚合 `RunReport` 写入 `run-report.json`。缺少 outcome 的课程按 `UNKNOWN` 折算。

每个案例、每轮运行会新建一个 API session。生产默认建会话限流为每个来源地址 10 个 / 300 秒；多案例运行前需在独立 benchmark API 进程配置足够的 `CP_SESSION_RATE_LIMIT_MAX`（至少等于案例数 × 重复次数），不调整生产默认值。manifest 记录由调用者提供的配置声明，不会自动核验被测 API 的实际模型、Harness、Java API 或预算配置；两者不一致时不可作同条件比较。

## 本地 smoke run（不是质量评测）

`python benchmark/smoke_runner.py` 使用 C 模块现有的 `PlanningRunner`，并强制使用类型化假工具与假模型。`benchmark/cases/smoke/` 中的输入和预期都是明确的虚构演示，只检查运行接线、输出形状、`FAKE_MODEL` 标记与班次未知状态；输出报告会标为 `SYNTHETIC_SMOKE_NOT_QUALITY_EVALUATION`。它不使用 12 条 evolution 题面的真实快照、不调用真实 Java 核验、不产生正确率，也不能用于候选晋级。

输出中的 `executionStatus` 区分 `COMPLETED`、`NOT_RUN` 与 `FAILED`；`assessmentStatus` 会单独保留 `UNKNOWN`，用量缺失保持 `null`。当前 smoke runner 只接受显式 `SYNTHETIC_FICTION` 的 `planning-request` 输入；其它 case 会输出 `NOT_RUN`，不会计为 0 分。

命令仅在至少运行一个案例且所有案例均为 `COMPLETED` / `SMOKE_PASS` 时返回成功；空集、`NOT_RUN`、`FAILED`、`UNKNOWN` 或 smoke 检查失败均返回非零。

## 真实模型遥测基线（无质量结论）

`real_model_baseline.py` 是后续真实模型评测的采集入口，复用模块 C 的生产 `PlanningRunner`。本命令只接受 `benchmark/cases/smoke/` 下的虚构输入，要求真实 Java 服务与非占位模型均已配置，并且必须显式设置 `CP_BENCHMARK_ENABLE_REAL_MODEL=true`。配置检查会在任何运行前完成；未设置开关时不会创建应用或发起网络调用。真实模型端点可能产生费用，因此本地显式执行者需确认端点的计费设置。

在安装了 `agent-runtime` 固定依赖的 Python 环境、并且本地配置文件包含 `CP_MODEL_BASE_URL`、`CP_MODEL_API_KEY`、`CP_MODEL_ID`、`CP_JAVA_BASE_URL` 与 `CP_SERVICE_KEY` 后，显式运行：

```bash
CP_BENCHMARK_ENABLE_REAL_MODEL=true python benchmark/real_model_baseline.py \
  --env-file data/private/stack.env \
  --output benchmark/runs/real-model-baseline.json
```

采集器把 smoke 输入绑定到 Java 演示种子主体 `S001` 与培养方案快照 `PLAN_CS_2025`（可用 `--subject-id`、`--curriculum-snapshot-id` 覆盖），不创建会话或学业记录。若目标服务没有对应的种子快照/记录，失败会保留在逐例记录中。报告保留运行清单、每例 `COMPLETED` / `FAILED`、运行耗时、决策类型、未知项代码、推荐数量及 provider 返回的 token 用量；不保存用户提示或回答文本。当前输入没有人工真值，`assessmentStatus` 固定为 `NOT_ASSESSED_NO_HUMAN_LABELS`，因此该报告只能说明模型调用接线、失败情况和延迟，不能计算正确率、宣称质量改善或用于晋级。Java/模型调用失败会保留为失败记录，进程返回非零。该入口不使用 evolution 或 held-out 题目和答案。

G1 培养要求；G2 hard/soft 偏好；G3 规划/冲突/replan；G4 缺信息时澄清与拒绝编造。每组目标 5 evolution + 5 held-out，五周最低可缩至 3+3 并说明局限。真值由双人对照原数据人工标注；Evolver 不得读取答案/held-out/评分器。记录客观分数、平均输入/输出 Token、工具调用、耗时与版本 lineage。详见 `../docs/07-benchmark-protocol.md`。

## 数据快照（D1 登记）

| 项 | 值 |
| --- | --- |
| curriculumSnapshotId | `3c405feaa6d7`（教学计划表 20250306 版，SHA-256 前 12 位） |
| 快照全量哈希 | `3c405feaa6d73bd067b1c03df6abd635b7b987bfe1d35ae6971363ab7bb7a756` |
| 本地副本 | `data/raw/`（.gitignore 覆盖，不提交） |
| 采用工作表 | 计科学1/2/3（非直招）、计科学直招1/2/3（直招） |
| offeringSnapshotId | 未冻结；G2/G3 需要人造班次（SIMULATION），生成后补登记 |
| 事实等级 | `REAL` = 培养要求事实；`SIMULATION` = 人造班次；无班次 = 语料确实没有排课时间 |

case 文件只引用 `curriculumSnapshotId`，不写"老师给的那张表"。
