# Planning Agent（模块 C）

CoursePilot-Evo 的 System 2 层：唯一的**生产/评测 Runner**、FastAPI 网关和可版本化运行
Harness。硬事实全部来自 Java（System 1），本模块只负责理解目标、调用策略、候选、澄清与解释。

> 当前是 **W1 骨架**：DTO 契约、Runner 入口、意图/澄清/守卫纯策略、Harness 装载、session/planning
> 最小纵向切片。**尚未接入真实模型与真实 Java**——模型适配器和 ToolClient 的 HTTP 部分留到 W2/W3。

## 目录结构（依赖方向 api → application → domain/policies，adapters 封装 IO）

```text
agent-runtime/
  harness/                    运行 Harness 白名单（策略文本，Evolver 可改；不含根 AGENTS.md）
    AGENTS.md                 runtime 策略
    tool_policy.yaml          工具白名单与次数上限
    context_policy.yaml       事实/评价选取上限
    skills/                   技能文本（占位）
  src/agent_runtime/
    api/schemas/              Pydantic DTO，逐字段对照 contracts/schemas/domain.schema.json
    api/routes/               FastAPI 路由（sessions / planning / gateway）
    api/app.py                应用组装 create_app()
    application/              PlanningRunner、ExecutionContext、Budget
    domain/policies/          意图解析、澄清、候选守卫、答案编译（纯函数）
    adapters/                 模型、Java Tool、Harness、Trace 的封装
  tests/                      契约对应证明 + Runner/策略/Harness/API 测试
  pyproject.toml              manifest、固定依赖、[test] extra、ruff/pytest 配置
```

## 接口对应（重点）

`api/schemas/` 里每个 Pydantic 模型与 `contracts/schemas/domain.schema.json` 的 `$defs`
**同名、同字段、同枚举、同约束**，并 `extra="forbid"` 拒绝契约外字段。schema 里的条件规则
（`allOf` if/then）以 `model_validator` 重写：

- `PlanValidation`：`VALID` 时 `violations`/`unknownChecks` 必须为空；时间 scope 必须有 `offeringSnapshotId`。
- `PlanningAnswer`：`CLARIFY` 必须有 `clarification` 且 `recommendations` 为空。

对应关系由 `tests/test_schema_contract.py` 用仓库自带的 8 个正反例证明（正例通过、反例抛
`ValidationError`）。`schemas/__init__.py` 的 `SCHEMA_DEFS` 是 `$defs` 名 → 模型 的映射。

**字段真源是 `contracts/`，不是这里的 Python**。改契约时先改 `contracts/` 和正反例，再同步这里。

## 唯一入口

```python
runner.run(request: PlanningRequest, context: ExecutionContext) -> PlanningAnswer
```

生产和 Benchmark 共用同一个 `PlanningRunner`，模型配置与工具集合一致（C-06）。

## 运行与检查

```bash
python -m venv .venv && . .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -e '.[test]'
python -m ruff format --check .
python -m ruff check .
python -m pytest -q

# 启动（本地 demo，无 Java 时 planning 返回 503 TOOL_UNAVAILABLE）
python -m uvicorn agent_runtime.api.app:app --port 8000
```

## 当前限制（如实）

- `ModelAdapter` 只有接口，无真实模型调用；`PlanningRunner` 对「有目标」的请求返回
  `UNABLE_TO_VERIFY`（`PLANNING_LOOP_PENDING`），不伪造推荐。
- `ToolClient` 只有工具白名单注册表；未配置 `CP_JAVA_BASE_URL` 时任何工具报 `TOOL_UNAVAILABLE`(503)。
- 会话与幂等是内存实现，仅本地 demo，非生产身份设计。
- `planning.openapi.json` 的 11 个端点全部有对应路由；走 Java 的端点未配置 `CP_JAVA_BASE_URL`
  时返回 `TOOL_UNAVAILABLE`(503)，不冒充无冲突。
- 预算默认值（8000/2000 tokens、6 tools、3 model calls、45 s）来自公共契约，未做性能实测。
