package com.coursepilot.verifier.web.dto;

import java.time.LocalDateTime;
import java.util.List;

public record TranscriptDto(
    String academicRecordId,
    int revision,
    String curriculumSnapshotId,
    List<CompletedCourseDto> completedCourses,
    boolean transcriptComplete,
    String sourceKind,
    LocalDateTime createdAt
) {
    public record CompletedCourseDto(String courseCode, String courseName, java.math.BigDecimal credits, boolean passed) {}
}
