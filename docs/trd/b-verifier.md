# 子 TRD B｜Java 规则核对与 Verifier（12 人日）

**目标：**让学分、路径、已修记录和建议课程的硬事实由 Java 计算；无法确认的规则显式 `UNKNOWN`。不做班次排课求解器。

## 技术与文件

Java 21 纯函数规则类 + Spring Service，JUnit 5 参数化测试。建议负责 `java-environment/.../rule/RequirementAuditor.java`、`RecommendationVerifier.java`、`domain/Requirement.java`、`dto/AuditResult.java`、对应测试。读取 A 提供的已审核快照与 C 的 repository 接口，不读 Excel 原始单元格。

## 做法

1. 定义支持的最小规则类型：课程必修、类别最低学分、实践三选一；每类记录 `ruleId, track, target, sourceRef, reviewStatus`。文字规则若尚未人工转写或缺证据，返回 `UNKNOWN`。
2. 对已修记录先去重，再按课程代码映射到当前快照。课程不在路径、学分认定不明、复合编号未拆分时生成问题，不暗自计入已修。
3. `auditRequirements(snapshotId, completedCourses)` 返回 `satisfied[]/gaps[]/unknowns[]`，每项有要求值、已确认值、差额和 `sourceRef`。
4. `validateRecommendation(snapshotId, proposedCodes, completedCourses)` 检查课程存在、路径正确、重复修读与已启用的规则。没有班次时间时追加 `OFFERING_UNAVAILABLE`，不声称“无时间冲突”。
5. 给 C/D 稳定 DTO 和一组成功、硬错误、未知样例。

## 验收

B 与 E 用 `.xls` 独立人工核对至少 10 个规则样例；JUnit 覆盖临界学分、重复课、跨路径、三选一、缺失成绩、组合编号与无班次。任何 `UNKNOWN` 在最终 DTO 中可见。规则代码不调用 LLM，Agent 文本不能覆盖 Java 数值。

**学习入口：**[Spring REST Guide](https://github.com/spring-guides/gs-rest-service) 的 DTO/API；[Spring PetClinic](https://github.com/spring-projects/spring-petclinic) 的领域服务与测试组织。只借结构，不照搬宠物业务。
