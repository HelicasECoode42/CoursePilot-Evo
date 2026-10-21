package edu.coursepilot.importer;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public final class ImportModels {
  private ImportModels() {}

  public enum IssueCode {
    FILE_TOO_LARGE,
    WRONG_EXTENSION,
    INVALID_OOXML,
    TRACK_NOT_ALLOWED,
    TEMPLATE_MISMATCH,
    FORMULA_WITHOUT_CACHED_VALUE,
    EXTERNAL_LINK_PRESENT,
    INVALID_CREDITS,
    DUPLICATE_COURSE,
    DUPLICATE_COURSE_CONFLICT,
    TOTAL_MISMATCH,
    UNKNOWN_RULE,
    INVALID_ROW
  }

  public record SourceRef(
      String refId,
      String kind,
      String snapshotId,
      String workbookHash,
      String sheet,
      int row,
      int column,
      String originalLocator,
      Instant capturedAt) {}

  public record CategoryRequirement(
      String category, BigDecimal requiredCredits, String rawCredits, SourceRef source) {}

  public record CurriculumEntry(
      String name,
      String courseCode,
      String category,
      BigDecimal credits,
      String suggestedTerm,
      String recordKind,
      SourceRef source) {}

  public record ImportIssue(IssueCode code, String sheet, int row, int column) {}

  public record CurriculumDraft(
      String trackId,
      String workbookHash,
      String importerVersion,
      String idempotencyKey,
      List<CategoryRequirement> requirements,
      List<CurriculumEntry> entries,
      List<ImportIssue> issues) {
    public boolean publishable() {
      return issues.isEmpty();
    }
  }

  public record PublishResult(String snapshotId, boolean reused) {}

  @FunctionalInterface
  public interface PublishPort {
    PublishResult publish(CurriculumDraft draft);
  }
}
