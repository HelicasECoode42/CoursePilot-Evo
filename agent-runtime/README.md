# Planning Agent（模块 C）

CoursePilot-Evo 的 System 2 层：唯一的**生产/评测 Runner**、FastAPI 网关和可版本化运行
Harness。硬事实全部来自 Java（System 1），本模块只负责理解目标、调用策略、候选、澄清与解释。

> 当前是 **W2 类型化假循环**：DTO 契约、Runner 入口、意图/澄清/守卫、假模型候选、假 Java
> `validatePlan`、Harness、session/planning。未配置模型密钥时走假模型，答案 `unknowns`
> 带 `FAKE_MODEL`。默认无 `CP_JAVA_BASE_URL` 时 planning 仍返回 503；本地演示可设
> `CP_USE_FAKE_TOOLS=true`。

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
- `Constraint`：`BLOCK_DAY`/`BLOCK_SECTION` 各取 dayOfWeek/section 一维，`BLOCK_SLOT` 两者都必填。

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

# 启动（默认无 Java 时 planning 返回 503 TOOL_UNAVAILABLE）
python -m uvicorn agent_runtime.api.app:app --port 8000

# 本地看 W2 假循环（课程层 UNKNOWN，不是真课表）
# set CP_USE_FAKE_TOOLS=true
```

## 当前限制（如实）

- `FakeModelAdapter` 只从工具返回的课程 id 里挑候选，不是真实模型；只要走到假模型，
  `PlanningAnswer.unknowns` 就有 `FAKE_MODEL`。核验器假工具固定 `UNKNOWN` + `COURSE_ONLY`，
  不能当成无冲突课表。工具课程集为空时返回 `UNABLE_TO_VERIFY`，不报模型输出非法。
- 有目标时 Runner 走 提议 → Guard → `validatePlan` → 编译；候选 id 不在工具集合则
  `EVIDENCE_MISMATCH`/`UNKNOWN_COURSE`，非法模型 JSON 只修复一次。
- `ToolClient` 已按 `java.openapi.json` 发 typed HTTP（`X-Service-Key` /
  `X-Subject-Id` / `X-Request-Id`，GET 列表读 `data.items`）。未配置
  `CP_JAVA_BASE_URL` 且未开假工具时仍是 `TOOL_UNAVAILABLE`(503)。
- 配置了 `CP_MODEL_BASE_URL` 与 `CP_MODEL_API_KEY` 时走 OpenAI 兼容
  `/chat/completions`；密钥只放本机 `.env`。只配地址、密钥为空时仍用假模型，并留下
  `FAKE_MODEL`。地址和密钥都在、但模型名仍是占位符时，进程启动失败。上游 429 是
  `MODEL_RATE_LIMITED`，5xx 是 `MODEL_UNAVAILABLE`，都不当成非法输出。
- 会话与幂等是内存实现。相同键执行中返回 `409 REQUEST_IN_PROGRESS`；失败会释放占位以便重试。
- `planning.openapi.json` 的 12 个端点全部有对应路由；走 Java 的端点未配置 `CP_JAVA_BASE_URL`
  时返回 `TOOL_UNAVAILABLE`(503)，不冒充无冲突。`listSessionRecords` 对应的 Java 列表工具
  （`listAcademicRecords`）尚待模块 B 在 `java.openapi.json` 补齐。
- 预算默认值（8000/2000 tokens、6 tools、3 model calls、45 s）只写在 `Budget`，manifest 记录同一份，未做性能实测。页面看到答案级 `FAKE_MODEL` 时不得显示真实通过。
