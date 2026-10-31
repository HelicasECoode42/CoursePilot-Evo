package com.coursepilot.verifier.web.dto;

import java.util.List;

/**
 * 契约形状的学业核对 DTO。字段名、枚举和必填项逐条对照
 * contracts/schemas/domain.schema.json 的 AuditRequest / AuditResult / AuditItem，
 * 不在这里另造一套命名。
 *
 * 这是外层壳：核对算法在 AcademicLedger（与 AuditEvaluator 共用），本文件只负责把算出来的数按契约摆好。
 */
public final class AuditDtos {

    private AuditDtos() {}

    /** contracts: AuditRequest */
    public record AuditRequest(
        String schemaVersion,
        String curriculumSnapshotId,
        String academicRecordId) {}

    /** contracts: AuditItem.state */
    public enum State { SATISFIED, UNSATISFIED, UNKNOWN }

    /** contracts: AuditItem。gapCredits 在 state=UNKNOWN 时为 null，表示缺口无法确定。 */
    public record AuditItem(
        String requirementId,
        /** 类别名（必修 / 通识 …）。没有这个字段，前端只能显示「培养要求 1」。 */
        String category,
        List<String> courseCodes,
        double requiredCredits,
        double earnedCredits,
        Double gapCredits,
        State state,
        List<String> sourceRefIds) {}

    /** contracts: AuditResult */
    public record AuditResult(
        String curriculumSnapshotId,
        String academicRecordId,
        int recordRevision,
        boolean transcriptComplete,
        List<AuditItem> requirements,
        List<String> suggestedCourseCodes,
        List<Issue> unknowns) {}

    /** contracts: Issue */
    public record Issue(String code, String message, String field, boolean retryable) {}
}
