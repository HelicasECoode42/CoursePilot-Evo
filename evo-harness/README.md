# Benchmark / RSI 执行器（待实现）

Python、pytest、JSONL：运行 evolution cases、按多条 Trace 找共同失败、对 Harness 白名单生成最小 Patch、隔离 held-out 评测、Promote/Rollback，并保存 v0→v1→v2 的 Snapshot/lineage。未严格提升或 held-out 退化就回滚；不能声称已经节省 Token。详见 `../docs/trd/d-benchmark-rsi.md`。
