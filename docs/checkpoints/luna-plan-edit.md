# 方案删除与编辑 checkpoint

## 技术栈与流程

- Python FastAPI 路由 `agent-runtime/src/agent_runtime/api/routes/plan_replacement.py` 调用应用服务 `PlanReplacement`，会话归属由 `SessionPlanStore` 检查。
- 删除使用 `POST /api/v1/session-plans/remove-course` 和 `Idempotency-Key`。应用服务要求课程在方案中恰好出现一次，过滤该课程的 `PIN_COURSE`、`PIN_TEACHER_COURSE`，并深拷贝其他课程与硬约束。
- 有剩余课程时调用 Java `validatePlan`。原样保存 Java `VALID`、`INVALID` 或 `UNKNOWN` 结果；Java 失败或复用旧 verifierResultId 时不保存新方案。
- 删除末课时保存新 planId 与 `items=[]`、`empty=true`、`verification=null`，不调用 Java。已检查 `PlanValidationService.validateShape` 明确拒绝空 items（1..MAX_ITEMS）。前端显示“空方案，尚无核验结果”，可返回问卷重新规划。
- Vue 结果页调用删除接口，不再为删除提交规划请求。编辑版本同步到 Pinia 和页面状态；在途状态阻止重复点击，重复提交复用幂等键。换班次仍经原替换接口核验整份方案。
- 结果页接入 `CourseReviewBasis` 与 `ReviewSummary`：课程来源、理由来源、评价查询状态和引用来源由接口字段展示。编辑后保留且未改变的课程理由标记为原推荐理由；班次或教师发生变化时不沿用旧理由；已删除课程的理由不再渲染。
- 合同更新在 `contracts/planning.openapi.json`、`contracts/schemas/domain.schema.json` 与删除请求/空结果 examples；HTTP client 与 fixture client 提供一致的数据形状。未验证的下学期快照不会被描述为真实课表验证。

## 失败处理

- 不属于当前会话的 planId 返回 404；方案不存在目标课程返回 422。
- Java 不可用时返回 503，旧方案保持可读，不创建新 planId。
- Java 返回旧 verifierResultId 时拒绝创建新版本。
- 相同幂等键和请求返回原响应；在途请求由幂等存储拒绝并发执行。
- 空方案没有核验对象，契约明确使用 `verification: null`，界面不复用旧核验结论。

## 回滚

检查点引用 `refs/checkpoints/coursepilot/20261029T103116552919Z-luna-plan-edit-finalize` 指向 `d9c3d5224ec220b7cbed6937108fb25799864fae`；上一阶段引用为 `refs/checkpoints/coursepilot/20261029T102558134923Z-luna-plan-edit-final`（`cbc2307ccf583a86f74055e3af0c4ccd8307f688`）。基线为 `e2a30b519ec65b1bd50229aacc6a3fddd64fd5a6`，另有主 Agent 保存的全量检查点 `629eca91d6631fa7a622e607fae7d7a401a44048`。检查点引用只保存快照，删除引用不会回退文件。恢复时先保存当前检查点，再用 `git worktree add --detach <独立目录> <检查点>` 检查快照；确定要回退的文件后，仅对明确路径运行 `git restore --source <检查点> -- <路径...>`，不移动分支，也不覆盖其他模块文件。

## 验证结果

- `npm run typecheck`：通过。
- 受影响 Web 单测（ResultView、HTTP client、fixture client、planning store）：129 项通过。
- `agent-runtime/tests/test_plan_replacement.py`：15 项通过；对应 Python 文件 `ruff check` 通过。
- Python 契约测试（schema、OpenAPI、方案编辑）：39 项通过。
- `scripts/check_contracts.py`：通过，检查 3 份 Schema/OpenAPI、引用和 22 个正反例。
- 主 Agent 的服务联调验证：生成方案 HTTP 200、删除 HTTP 200、其余方案项保持不变、相同幂等键重放响应一致。该联调不证明真实学期班次来源已核验。
- 问卷与结果页定向 Web 测试：41 项通过；`npm run typecheck`、相关 ESLint 和 Prettier 检查通过。

## 未完成

- 没有已验证的下学期真实班次快照，因此不能做真实学期的课表核验验收。
