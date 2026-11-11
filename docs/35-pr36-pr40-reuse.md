# PR #36 与 #40 的代码复用

## 版本与取舍

本轮基于 `main` 的 `d6380364375f835da3abb6e04cc7a0e6c4d48a87`，比较 [PR #36](https://github.com/HelicasECoode42/CoursePilot-Evo/pull/36) 的 `b8d32163434dea182ee6671f9b52cc52dd62df25` 与 [PR #40](https://github.com/HelicasECoode42/CoursePilot-Evo/pull/40) 的 `0acd0c2246bd8328d4a9a7f3a0e46490e4a388c9`。实现由 Luna 执行，接口与报告语义由主 Agent 复核。

| 来源 | 复用内容 | 处理依据 |
| --- | --- | --- |
| #36 | HTTP 案例运行、输入适配、RunManifest/RunReport、重复运行比较 | 通过现有 Python API 调用生产 Runner；保留原有 smoke 与真实模型遥测入口 |
| #40 | 时间解析接口回归测试 | 检查路由返回的星期、起止节次与周次；已有时间边界、冲突和对象授权测试继续保留 |
| #40 | MySQL/Flyway 配置 | 旧迁移仅创建全局课程表，与当前快照级课程模型不符，需要另行设计完整迁移 |

当前 Java 使用 H2。课程实体的学分仍有 `Double` 字段，学业记录部分使用 `BigDecimal`；本轮没有进行全链路数值类型迁移。

## 评测数据流

`case + fixture → case_adapters → HTTP sessions / academic-records / requirements/audit / planning → 逐例记录 → RunReport + summary + 重复运行差异`。

学分和时间规则继续由 Java 执行。适配器负责生成请求，不生成标准答案。缺少成绩结果按 `UNKNOWN` 处理，未声明完整的记录保持不完整。复合课程号需要在案例中明确展开；缺少有效原方案的重规划案例保留未测状态。

运行入口为 [benchmark/run_benchmark.py](../benchmark/run_benchmark.py)，参数和输出说明见 [Benchmark README](../benchmark/README.md)。执行时显式指定目标 API；`--plan` 只检查案例能否构造请求。运行产物保存在被忽略的 `runs/` 目录。

## 报告解释

没有人工判据时记录 `UNSCORED`。词元覆盖基线与未核验引用不能形成质量通过结论。受控假模型保留合成标记，缺少供应商用量时保留 `null`。

重复运行比较接口状态、决策和未知项等已记录字段，成本差异单独记录。该比较不覆盖回答的全部语义。单次运行无法估计重复稳定性。RunManifest 记录执行者声明的配置，被测服务配置仍需执行者核对。

真实模型质量评测还需要独立人工标注、引用核验和固定配置下的重复运行。候选生成、隔离评测、晋级与回滚继续按 Benchmark 协议实施。

## HTTP 验收

独立 Python API 使用 8002 端口，模型保持受控假实现。两次假工具运行完成学业记录写入与核对，报告保留 `FAKE_TOOL`、`UNSCORED` 和缺失用量。随后改为连接实际 Java 8081，创建 `CS101` 虚构已修记录并核对；接口返回 200，核对结果为 `UNKNOWN / REQUIREMENT_SOURCE_REFS_MISSING`，耗时约 1.35 秒。没有人工判据，评测继续记录 `UNSCORED`，命令返回非零。

该验收覆盖会话、记录、核对与报告衔接，未调用付费模型。8002 测试进程已停止。实际 Java 链路产物位于本地 `runs/benchmark/http-synthetic-java/`，不提交公开仓库。

| 检查 | 结果 |
| --- | --- |
| Benchmark 全量测试 | 62 通过，1 跳过；主 Agent 独立复跑结果一致 |
| Benchmark Ruff 0.16.10 | 静态检查通过；18 个文件格式检查通过 |
| Java 受影响测试 | 时间解析、冲突服务与对象授权共 50 项通过，0 失败、0 错误；H2 内存库 |

修改前 checkpoint 为 `refs/checkpoints/coursepilot/20261102T003515636890Z-before-pr36-pr40-reuse`。HTTP 验收后的 checkpoint 为 `refs/checkpoints/coursepilot/20261102T105302166981Z-pr-reuse-http-accepted`。这些 checkpoint 保存源码，不包含被忽略的私有配置与数据库。
