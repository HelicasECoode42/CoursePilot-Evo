# 接口与开发规范复核记录

日期：2026-09-30。范围是设计契约与仓库检查；服务未实现，不能据此声称运行时鉴权、排课或 RSI 已通过验收。

## 复核结果

| 检查项 | 结果与落点 |
| --- | --- |
| 共享对象与引用 | 单一 domain Schema；两份 OpenAPI 仅引用仓库内文件，无远程动态引用 |
| 前端可达接口 | Python 网关补齐培养方案、课程、教师评价、发展方向与培养核对；Java 接口不直接暴露给浏览器 |
| 身份边界 | 浏览器不提交 owner；Python 从会话派生 subject，Java 二次校验资源归属；报告需会话与管理员凭据 |
| 未知时间 | VALID 与 unknownChecks 并存被 Schema 拒绝；真实/模拟核验要求班次快照，客户端来源标签不能自行升级为 VERIFIED |
| 错误处理 | 报告错误响应补齐统一 Envelope；HTTP/status 与重试规则见共享工作流 |
| 固定评测 | Benchmark 文档统一到 RunManifest 与同一预算；题面、标签和评分器与 Evolver 隔离 |
| 提交检查 | PR 清单、基础泄漏检查、契约校验和按模块检查；存在源码但没有构建清单时失败，空骨架只报告 SKIP |

## 本地执行证据

已运行 `python scripts/check_contracts.py`：3 份 Schema/OpenAPI 文件、仓库内引用、8 个正反例通过。
已运行 `python scripts/self_check.py`：基础文本泄漏与相对链接检查通过。
已运行 `python scripts/check_modules.py`：Java、三个 Python 模块与 Web 均无实现清单，明确 SKIP。

这些检查验证结构和示例，不证明所有业务规则已成立。时间解析黄金样例、真实登录态/快照、模型调用、对象鉴权、数据库事务、浏览器视觉和端到端行为仍由各模块按 TRD 实现与验收。基础文本扫描不能替代安全评审。

## 每次接口变更的复核顺序

需求与使用场景 → 修改共享 Schema/OpenAPI → 正反 fixture → 对照生产者和消费者 → 检查权限/未知/幂等/超时 → 更新时序图 → 执行检查 → PR 列出证据。不能只改一方字段后要求另一方猜测。
