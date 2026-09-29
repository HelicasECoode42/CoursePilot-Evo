# Planning Agent（待实现）

Python 3.11+、FastAPI、Pydantic、httpx 与 OpenAI-compatible 模型客户端。System 2 解析目标、调 Java Tool、修正/澄清、解释；生产与 Benchmark 共用唯一 `planner.run(case)`。硬事实必须来自 System 1，班次未知不猜。详见 `../docs/trd/c-agent.md`、`../docs/04-infrastructure-workflow.md`。
