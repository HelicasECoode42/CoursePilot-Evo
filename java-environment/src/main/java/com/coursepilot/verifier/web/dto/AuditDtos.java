package com.coursepilot.verifier.web.dto;

import java.util.List;

public class AuditDtos {
    public record AuditRequest(String academicRecordId, String planId) {}

    public record AuditResult(
        String curriculumSnapshotId,
        String academicRecordId,
        int recordRevision,
        boolean transcriptComplete,
        List<AuditItem> items,
        List<Issue> unmetRequirements,
        List<Issue> unknowns
    ) {}

    public record AuditItem(
        String requirementId,
        List<String> courseCodes,
        double requiredCredits,
        double earnedCredits,
        double gap,
        State state,
        List<String> sourceRefIds
    ) {}

    public enum State { SATISFIED, UNSATISFIED, UNKNOWN }

    public record Issue(String code, String message, String field, boolean retryable) {}
}
