# held-out 题面

本目录是**留出集**（`split=held-out`）的题面，共 12 条：四组各 3 条，与 `../evolution/` 一一对应。

## 与 evolution 的区别

| 项 | evolution | held-out |
| --- | --- | --- |
| 题面 | 在本目录，Evolver 可读 | 在本目录，Evolver **不得**读取 |
| 判据 | 工作区外 `restricted/gold/` | 工作区外 `restricted/gold/` |

判据一律不进仓库：按 docs/07 第 4 节，standarded 答案与评分器由隔离 Runner 持有。
本目录只放题面，文件里不得出现 `requiredFacts` / `requiredUnknowns` / `requiredClarification` /
`forbiddenClaims` / `requiredSourceRefs`（`validate_cases.py` 的 E06 会报错）。

## 隔离方式（2026-10-26 调整）

此前 held-out 题面放在工作区外，靠「不在仓库」实现隔离；编写人决定改为题面进仓库、判据仍在外，
隔离由目录约定与流程约束承担：

- 失败归因（`failure_mining.py`）与任何候选生成流程只读 `../evolution/`，不读本目录；
- 候选可修改的白名单只有 `agent-runtime/harness/` 下的四个路径；
- 读判据只能经 `benchmark/private_access.py` 的受控入口，不在 runner 里直接拼路径。

## 核对

```text
python benchmark/validate_cases.py --cases-root benchmark/cases/held-out --gold-root ../restricted/gold
```

预期 `ERROR 0`；只应有 `WARNING W02`（未完成双人复核）。
