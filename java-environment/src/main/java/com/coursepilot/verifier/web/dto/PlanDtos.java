package com.coursepilot.verifier.web.dto;

import java.util.List;

/**
 * 方案核验的契约形状（contracts/schemas/domain.schema.json 的 PlanValidationRequest /
 * PlanValidation / PlanItem / Constraint）。字段名与枚举逐条对照契约，不另造命名。
 * 枚举类字段在 PlanValidationService 里校验，这里保持字符串，避免 Jackson 把非法值变成 500。
 */
public final class PlanDtos {

    private PlanDtos() {}

    /** contracts: PlanValidationRequest。mode 取 REAL / SIMULATION。 */
    public record PlanValidationRequest(
        String schemaVersion,
        String curriculumSnapshotId,
        String offeringSnapshotId,
        String academicRecordId,
        String mode,
        List<PlanItem> items,
        List<Constraint> hardConstraints) {}

    /** contracts: PlanItem。classId 指向班次；时间一律由 Java 按 classId 从库里取，不接受客户端时间文本。 */
    public record PlanItem(String courseCode, String teacherKey, String classId) {}

    /**
     * contracts: Constraint。kind 取 BLOCK_DAY / BLOCK_SECTION / BLOCK_SLOT /
     * PIN_TEACHER_COURSE / PIN_COURSE / MAX_CREDITS。
     */
    public record Constraint(
        String kind,
        String courseCode,
        String teacherKey,
        Integer dayOfWeek,
        Integer section,
        Double value,
        String sourceText) {}

    /** contracts: PlanValidation。verdict 取 VALID / INVALID / UNKNOWN；scope 取 COURSE_ONLY / REAL_TIMETABLE / SIMULATION。 */
    public record PlanValidation(
        String verifierResultId,
        String verdict,
        String scope,
        String curriculumSnapshotId,
        String offeringSnapshotId,
        int recordRevision,
        List<AuditDtos.Issue> violations,
        List<AuditDtos.Issue> unknownChecks,
        List<String> performedChecks,
        List<String> sourceRefIds) {}
}
