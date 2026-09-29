# 可进化运行 Harness（待实现）

首版白名单：`AGENTS.md`、`skills/`、`tool_policy.yaml`、`context_policy.yaml`。每次运行冻结完整内容 hash 为 `harnessVersion` 并保存 Snapshot；Evolver 只能基于跨至少两个 Case 的 failure hypothesis 产生一次有限 patch。根目录 `AGENTS.md` 是开发者约定，**不在** Evolver 白名单。Java Tool API、评分器、答案、held-out、基模和预算不属于可改内容。详见 `../../docs/07-benchmark-protocol.md`。
