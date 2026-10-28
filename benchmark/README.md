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
