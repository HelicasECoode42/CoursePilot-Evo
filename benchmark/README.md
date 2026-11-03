# 四组 Benchmark（待标注/待实现）

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

## 基线测量入口（D-F2 骨架）

`run_benchmark.py` 逐例驱动 C 侧的 `/api/v1/planning`（被测 Agent 只有这一个，本模块不另写 Agent），
把每例的判定、结构化答复、用量、耗时、评分写成一条 JSONL，并按 contracts 出 `RunReport`。

```text
python benchmark/run_benchmark.py --manifest benchmark/manifests/example.json --plan
python benchmark/run_benchmark.py --manifest benchmark/manifests/example.json \
    --base-url http://127.0.0.1:8000 --gold-root ../restricted/gold
```

退出码：`0` 全部 PASS（或 `--plan`）；`1` 存在 DEGRADED / FAIL / BLOCKED；`2` manifest 不符合 `RunManifest`。

重复运行：`--repeats N`（缺省取 manifest 的 `repeatCount`）。第二轮起逐例与第一轮比对判定类字段
（判定、路线、决策、未知码、token、工具调用数、分数、blocked、错误说明），耗时类字段天然有波动不参与比对；
不一致会写进 `repeat-compare.json` 并以退出码 1 收尾，不按通过的那一轮结案。

`manifests/example.json` 只是字段示例（`modelId`、`javaToolApiVersion`、`verifierVersion` 未定），不是任何一次真实运行记录；实跑前按当次配置另存一份，manifest 一旦运行就不该再改。

判定语义（一例一判）

| 判定 | 含义 |
| --- | --- |
| PASS | HTTP 200、**有判据且已评分**、分数达到 `--pass-threshold`（默认 0.6）、无占位标记 |
| DEGRADED | HTTP 200 但答案带 FAKE_MODEL / FAKE_TOOL / OFFERING_UNAVAILABLE / DRY_TRANSPORT，只证明链路通 |
| FAIL | 已评分但 blocked（命中禁止结论、引用核验不通过），或分数低于门槛 |
| UNSCORED | 没有判据文件，未评分：**不计入通过**，CLI 退出码仍为非 0 |
| BLOCKED | 用例按契约构造不出请求，或上游 503、缺依赖，本例没有有效结果 |
| PLAN | 只登记不执行 |

没有判据时不会落到 PASS：默认判据目录 `../restricted/gold` 在干净检出与 CI 里不存在，
所以「没标判据」必须表现为 `UNSCORED` 而不是通过；`summary.json` 另报已评分覆盖率。

成本口径：Provider 没给 token 用量时记 `null`，不记 0、不估算；`summary.json` 另报成本可用样本覆盖率。

输出（默认 `runs/benchmark/<runId>/`）：`run-manifest.json`、`cases.jsonl`、`run-report.json`、`summary.json`。
`RunReport` 字段固定（`additionalProperties=false`），所以分组等权分数、覆盖率、matcher 名、held-out 状态写在 `summary.json`。

### 判据怎么判（分层）

`scoring/judge.py` 把判据分成三层判，跑基线时用的是它，不是纯文本匹配：

| 层 | 判哪些 | 口径 |
| --- | --- | --- |
| structured | 必须未知、必须反问 | 对答案的 `unknowns` / `clarification` 字段判，不看整段文本 |
| text | 必须答到的事实、不许说的结论 | 全文匹配；默认 `keyword_matcher` 占位基线 |
| unwired | 引用核验 | 没有 JavaVerifier 时记 `unwired`，既不算通过也不判 blocked |

「不许说的结论」另有一条启发式：命中句如果全是"无法判断／是否／未知"这类不确定措辞，不算违反，
否则正确答案说「全英语要求是否满足无法判断」会被误判成「声称已满足」。这条的已知风险是：
答案用"未满足"下断言时仍算命中，但同一段里若夹带不确定措辞可能被放过，复核时要抽查。

`summary.json` 会报 `claimModes` 与 `textShare`：文本判占比越高，这份分数越不能当语义正确率读。

### 失败归因（D-F4 骨架）

```text
python benchmark/mine_failures.py --run runs/benchmark/<runId>
```

读一次运行的 `cases.jsonl`，把逐例失败按「失败类型 + 判据原句」归并，产出 `hypotheses.json`。

| 项 | 口径 |
| --- | --- |
| 成假设的门槛 | 同一失败至少出现在 2 个不同用例（协议：单例失误不得触发自动补丁） |
| 单例处理 | 进 `rejected` 并写明原因，不静默丢弃 |
| 环境未接线 | `BLOCKED` 与带 `FAKE_*` 的 `DEGRADED` 不进归因，只计入 `excluded` 并写原因 |
| 可改范围 | `allowedTargets` 只能落在 agent-runtime/harness 白名单内，越界直接报错 |
| 输出 | `hypothesisId / category / caseIds / pattern / likelyCause / allowedTargets / expectedMetric / traceRefs` |

只做归因：不生成补丁、不判断晋级；Evolver 与 PromotionGate 属第六周。当前假工具下 12 例全部计入 `excluded`，
假设数为 0——这是正确结果，不是归因失效。

### held-out 隔离跑

```text
python benchmark/run_heldout.py --cases ../restricted/held-out --gold ../restricted/gold \
    --manifest benchmark/manifests/example.json --transport dry
```

父进程只拿聚合结果，题面与判据只在子进程里出现。三条约束：

| 约束 | 做法 |
| --- | --- |
| 路径 | 判据目录必须在仓库工作区之外（resolve 之前逐段检查，路径上不得有软链）；held-out 题面在 `cases/held-out/`，Evolver 不得读取 |
| 数据 | 判据只在子进程读；子进程只输出聚合 JSON，输出前自检不含判据原句（前 12 字命中即拒绝返回） |
| 失败 | 子进程非零退出、输出不是 JSON、自检发现泄漏，一律报 IsolationError，不伪造分数 |

`--transport dry` 只验证隔离机制，不发网络请求，结果带 `DRY_TRANSPORT` 占位标记并判 DEGRADED，不能当分数用。

held-out 形态适配现状（12 例）：12 例均可跑。传输层支持 `GET`，评价类题面走 `GET /api/v1/reviews/search`
（该接口 `courseCode` 必填，教师名不进请求；fixture 的修读学期为 null 时应答未知，不得当作本学期事实）。
其余形态已接：自报学分汇总（`completed` 键、`reportedCredits`）按缺失逐门明细处理并落空记录、
replan 形态（`originalGoal`/`newGoal`）按新目标重算且 `previousPlanId` 为 null、
单元格引用课号（`计科学1-A12`）不折 `PIN_COURSE` 而把课名留在题面、只给课名没给课号的已修课程不入库但留痕。

当前限制

* 语义匹配仍是 `scoring/scorer.py` 的 `keyword_matcher` 占位基线，分数偏低不代表模型差；接 C 的匹配器后应换掉。
* 引用核验未接线（`JavaVerifier` 为 `None`），逐条记 `unverified`，不折算成通过。
* held-out 未接入，`heldOutScore` 恒为 `None`，本轮只跑 evolution。
* G1/G4 的题面走 `academic-records` 与 `requirements/audit` 路径，本骨架只接 `/planning`，这些用例判 `BLOCKED` 并写明原因。
* 培养方案原表的合上课编号（`08305009~010`）含波浪号，契约标识符字符集不含该字符。折算口径：取波浪号之前的主号作课程标识，原写法原样写进 `sourceText`；不做字符替换，也不造原表里不存在的编号。
