# 四组 Benchmark（待标注/待实现）

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

`manifests/example.json` 只是字段示例（`modelId`、`javaToolApiVersion`、`verifierVersion` 未定），不是任何一次真实运行记录；实跑前按当次配置另存一份，manifest 一旦运行就不该再改。

判定语义（一例一判）

| 判定 | 含义 |
| --- | --- |
| PASS | HTTP 200、评分未 blocked、答案没有占位或缺失标记 |
| DEGRADED | HTTP 200 但答案带 FAKE_MODEL / FAKE_TOOL / OFFERING_UNAVAILABLE，只证明链路通 |
| FAIL | HTTP 200 但评分 blocked（命中禁止结论或引用核验不通过） |
| BLOCKED | 用例按契约构造不出请求，或上游 503、缺依赖，本例没有有效结果 |
| PLAN | 只登记不执行 |

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

当前限制

* 语义匹配仍是 `scoring/scorer.py` 的 `keyword_matcher` 占位基线，分数偏低不代表模型差；接 C 的匹配器后应换掉。
* 引用核验未接线（`JavaVerifier` 为 `None`），逐条记 `unverified`，不折算成通过。
* held-out 未接入，`heldOutScore` 恒为 `None`，本轮只跑 evolution。
* G1/G4 的题面走 `academic-records` 与 `requirements/audit` 路径，本骨架只接 `/planning`，这些用例判 `BLOCKED` 并写明原因。
* fixture 里 `08305009~010` 一类课程编号过不了契约 `Id` 字符集，无法折成 `PIN_COURSE` 约束，同样判 `BLOCKED` 而不是改写编号。
