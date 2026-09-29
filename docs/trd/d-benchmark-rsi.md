# 子 TRD D｜Task Group Benchmark、Trace 与 RSI（11 人日）

**输入：**A/B 的人工对照、C 的唯一 Agent Runner、全组 Trace/版本合同。**所有权：**`benchmark/`、`evo-harness/`、评测标签/评分器/隔离 Runner、版本 lineage。D 不改 Java 规则，也不把主观推荐分当唯一晋级依据。

## 要回答的问题与实现顺序

1. **任务与真值如何造？** Python 3.11+、pytest、Pydantic、JSONL。G1 要求、G2 hard/soft、G3 规划/冲突/replan、G4 澄清/拒编，每组目标 5 evolution + 5 held-out，最低 3+3。B/D 双人对照原表/经验证班次标注，分歧排除；答案与题面分目录、不同进程权限。
2. **如何计分和量成本？** `runner.py` 调 C 的同一 `planner.run`；`scorer.py` 用独立标签/Java Verifier 计算规则正确率、硬违规、unsupported claim、clarification correctness、四组等权 held-out score；Trace 记录 input/output token、tool calls、elapsedMs。缺 token 数据标 UNAVAILABLE。
3. **如何形成可解释的 patch？** `miner.py` 仅分析 evolution Trace；每个 failure hypothesis 至少有两个不同 caseId/Trace 证据。`evolver.py` 对 `AGENTS.md/skills/tool_policy/context_policy` 一次改一个策略，输出最小 diff、预期影响和 patch hash；不能读答案/held-out/评分器或改 Java API/模型预算。
4. **如何多轮晋级？** `promotion.py` 独立读取候选与父版本的隔离评分，按[协议](../07-benchmark-protocol.md)的严格客观门槛晋级或回滚。保存 Agent State、Snapshot、Trace、Score、Token、Latency、Tool Calls、lineage；支持 v0→v1→v2 两轮独立候选决策。Rejected 分支留记录，不伪装成稳定版本。

## 交付与验收

交四组任务清单/人工复核记录、隔离检查、基线与候选逐例报告、两轮决策记录。构造一个故意越权宣称无冲突的候选，验证门槛拒绝；检查 Evolver 运行目录不可见 held-out 或 gold 答案。若两轮均未晋级，只报告失败/回滚，不称“成功演化”。

**依赖：**A/B 提供真值和快照；C 提供 Runner/Trace；E 只展示 D 的版本决策。**学习入口：**[GDPevo 官方仓库](https://github.com/Prism-Shadow/GDPevo) 的 task group/评测目录、[promptfoo](https://github.com/promptfoo/promptfoo) 的断言思路、[pytest](https://github.com/pytest-dev/pytest) 参数化测试。
