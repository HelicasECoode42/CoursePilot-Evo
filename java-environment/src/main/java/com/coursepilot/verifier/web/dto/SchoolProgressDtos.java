package com.coursepilot.verifier.web.dto;

import com.coursepilot.verifier.web.dto.RecordDtos.AcademicRecord;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

/** Wire DTOs for the user's imported school progress report. */
public final class SchoolProgressDtos {
    private SchoolProgressDtos() {}

    public record ImportRequest(String schemaVersion, String curriculumSnapshotId,
                                Snapshot snapshot) {}
    public record Snapshot(String format, Integer version, Instant capturedAt,
                           String source, List<Node> nodes, List<Course> courses) {}
    public record Node(String nodeId, String parentId, String schoolNodeId,
                       Boolean leaf, String name, BigDecimal requiredCredits,
                       BigDecimal earnedCredits, BigDecimal remainingCredits) {}
    public record Course(String nodeId, String courseCode, String name,
                         BigDecimal credits, String outcome, String completedYear,
                         String completedTerm, String grade, String makeup,
                         String retake, String suggestedYear, String suggestedTerm) {}
    public record Receipt(String schoolProgressId, String contentHash,
                          Instant importedAt, boolean reused) {}
    public record ImportResult(Receipt receipt, Snapshot snapshot, AcademicRecord academicRecord) {}
}
