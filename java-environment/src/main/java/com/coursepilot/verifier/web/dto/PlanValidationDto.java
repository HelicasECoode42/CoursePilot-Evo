package com.coursepilot.verifier.web.dto;
import java.util.List;

public class PlanValidationDto {
    public record PlanValidationRequest(
        String snapshotId,
        String term,
        List<PlanItem> planItems,
        List<String> hardConstraints
    ) {}

    public record PlanItem(String courseCode, String classId, String meetingTextRaw, boolean isRequired) {}

    public record PlanValidationResult(String verdict, List<ConflictItem> conflicts, List<String> unknowns) {}

    public record ConflictItem(String classId, String conflictWith, String type, String details) {}
}
