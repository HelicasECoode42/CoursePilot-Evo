# 接口契约基线 v1

状态：开发契约，尚未实现服务。OpenAPI/Schema 是字段真源，行为不变量见 [共享契约](../docs/04-infrastructure-workflow.md)。模块 TRD 不重复创造同名 DTO。当前版本为 1.0，W1 的具体基模 ID/首次培养路径还需要填入配置。

- [Java OpenAPI](java.openapi.json)：课程/记录/导入/核对/评价/班次/核验。
- [Python OpenAPI](planning.openapi.json)：匿名演示会话、学生 API 网关、规划与受限报告。
- [公共 JSON Schema](schemas/domain.schema.json)：必填、nullable、枚举、长度及结构门槛。
- [正反例索引](examples/index.json)：每个 fixture 说明类型和是否应该通过。

使用 OpenAPI 3.1.0 和 JSON Schema 2020-12；不是宣称采用最新规范。未知属性默认拒绝；不能偷偷接收 client ownerId、serviceKey 或模型配置。

```bash
uv sync --group dev
uv run python scripts/check_contracts.py
uv run python scripts/self_check.py
```

`docs/course-offering-snapshot.schema.json` 保留为浏览器原始导出格式参考。A 将它映射为当前 OfferingImport；B 从 `meetingTextRaw` 重新解析，不信任上传者给的 `meetings/parseStatus`，也不因 sourceKind=BROWSER_SNAPSHOT 就判来源已验证。服务端快照 `sourceValidation` 才决定真实模式资格。

改契约时提交 Schema、正反例、提供者/消费者修改或明确的兼容适配、TRD 和测试证据。破坏性变化升版本；在 benchmark 版本比较中不得修改 Java API/评分条件。

## 变更记录

- `Constraint.kind` 增加 `BLOCK_SLOT`（星期 × 节次的交集），软偏好增加 `schedule.blocked_slot`。同时为三个时间 kind 加条件规则：`BLOCK_DAY` 的 `section` 必须为 null，`BLOCK_SECTION` 的 `dayOfWeek` 必须为 null，`BLOCK_SLOT` 两者都必须非空。在此之前 Schema 并不禁止同时填写两者，语义只靠文档约定，属于已存在的歧义。`schemaVersion` 保持 `1.0`：各模块均未开始实现，无已发布消费者需要兼容。模块开工后再改契约必须升版本。

离线校验仅验证契约、引用与样例；跨字段含义、对象级授权、SQL 事务和运行截止时间仍必须在模块测试中验证。
