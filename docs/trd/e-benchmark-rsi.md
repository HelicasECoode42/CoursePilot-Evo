# 子 TRD E｜Benchmark、Trace 与最小 Harness 自进化（10 人日）

**目标：**可重复地证明一个候选 Prompt/工具说明在固定任务上是否更好；失败时回滚。只做一个完整候选循环，不追求通用 RSI 平台。

## 技术与文件

Python 3.11+、pytest、标准 `json`/`jsonlines` 文件、`hashlib`、`subprocess` 读取 Git commit、Pydantic 校验任务格式。建议负责 `benchmark/cases/`、`benchmark/labels/`、`benchmark/runner.py`、`benchmark/scorer.py`、`benchmark/runs/`、`evo-harness/miner.py`、`evolver.py`、`promotion.py`。留出标签单独存储，Evolver 只拿训练 Trace；正式 Git 仓库开设时可通过 CI/权限再隔离。

## 做法

1. 与 B 从真实 `.xls` 和虚构已修记录人工写任务；初始目标 24 条，12/6/6 分训练/开发/留出。每条有 `caseId`、快照 hash、输入、必需事实、应未知项、禁止结论和来源。人工双人复核。
2. `runner.py` 调 D 的**同一个** Planning Agent；输出 `run-manifest.json`、逐例 `case-results.jsonl` 与脱敏 Trace。模型版本、温度、预算、Java verifier commit、Harness hash 和数据 hash 固定。
3. `scorer.py` 先查硬事实错误，再算核对准确、未知识别、来源完整和任务完成；失败逐例列出，不能只算总分。
4. `miner.py` 只对训练失败 Trace 按 `COURSE_NOT_FOUND/RULE_UNKNOWN/NO_SOURCE/OVERCONFIDENT` 等归类，附 caseId 和证据；`evolver.py` 调模型提出**最小文本 diff**，白名单仅 `agent-runtime/harness/prompts/`、`tool-descriptions/`。
5. 候选在同配置下跑训练、开发、留出。至少修好一例训练失败，且没有新增硬错误、没有已通过留出任务退化，才由 `promotion.py` 更新稳定版本指针；否则写拒绝原因并回滚。原版本、候选和 Trace 都保留。

## 验收

演示一次“候选通过晋级”或“候选失败回滚”，并展示逐例差异、未见任务结果和版本 hash。额外构造一个故意引入越权结论的候选，确认硬门槛会拒绝。若模型或经费不可用，保留 runner/评分与设计，但**不得**称完成自动自进化。

**学习入口：**[promptfoo](https://github.com/promptfoo/promptfoo) 的固定测试/断言和结果导出；[pytest](https://github.com/pytest-dev/pytest) 的参数化与 fixture。这里可自行写轻量 runner，避免为了 24 个任务搭复杂评测平台。
