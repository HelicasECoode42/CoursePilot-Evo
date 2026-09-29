# 子 TRD B｜Java Course Environment / Truth / Verifier（12 人日）

**输入：**A 的两个规范化快照和审核状态、全组 Tool API/错误封套。**所有权：**`java-environment/.../domain/`, `rule/`, `api/`, `persistence/`, `db/migration/` 与 JUnit；A 的 importer 代码由 A 负责。B 是 System 1 负责人，Java 不承担复杂自然语言推理。

## 要回答的问题与实现顺序

1. **数据如何不可混用？** Spring Boot + Spring Data JPA/MySQL + Flyway 保存 `CurriculumSnapshot`, `OfferingSnapshot`, `Course`, `CourseOffering`, `Requirement`, `SourceRef`；课程号字符串化。导入班次时校验 JSON Schema、学期、重复 classId、来源与时间解析状态，新快照不覆盖旧快照。
2. **哪些规则可计算？** 纯 Java 规则类计算必修/类别学分/人工审核的文字要求；对已修课程去重，未审核/学分认定不明返回 UNKNOWN。`checkConflict` 用 day×section×week 集合交叉；缺班次或解析失败返回 UNKNOWN。`validatePlan` 检查课程存在、培养路径、重复修读、学分/时间 hard condition。`scorePreference` 计算可定义的周五占用、空档等指标，不能让 soft score 掩盖硬错误。
3. **Agent 怎样获取真值？** Spring Web + Bean Validation 暴露 `courses`, `requirements/audit`, `offerings`, `plans/validate`, `preferences/score`；所有响应带两个快照 ID、SourceRef、`verifierResultId` 和 UNKNOWN/错误码。Java 的 Benchmark 客观评分接口或适配器与业务 Verifier 复用同一纯函数，不能用 Agent 答案当真值。
4. **如何防止快照失效误判？** 学期不一致 `TERM_MISMATCH`，采集过旧 `SNAPSHOT_STALE`；阈值由全组 W1 固定。没有班次时仍能做培养要求核对，但不出“无冲突”结论。

## 交付与验收

交 OpenAPI/DTO 示例、Flyway migration、JUnit 5 参数化用例和虚构 fixture。与原 `.xls` 人工对照至少 10 个要求样例；冲突测试覆盖单双周、离散周、边界节次、两门不重叠、未知时间。`UNKNOWN` 不得转成 `valid=true`。B 的 API 与 C/D/E 共用冻结合同，变更先改[共享契约](../04-infrastructure-workflow.md)。

**依赖：**A 交标准对象；C 用 HTTP 不读库；D 独立保管答案与评分器。**学习入口：**[Spring REST Guide](https://github.com/spring-guides/gs-rest-service)、[Spring Data JPA Guide](https://github.com/spring-guides/gs-accessing-data-jpa)、[Spring PetClinic](https://github.com/spring-projects/spring-petclinic) 的服务与测试组织。
