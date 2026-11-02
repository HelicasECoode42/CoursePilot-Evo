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
    /** 「三、备注」区段里的未建模规则：工作簿原文，系统尚未形成执行规则。不阻断发布， 而是作为快照级 UnmodeledRule 保存，并随学业核对与方案核验带出 unknown。 */
    UNKNOWN_RULE,
    UNSUPPORTED_ENTRY,
    INVALID_COURSE_CODE,
    COURSE_CODE_TOO_LONG,
    INVALID_ROW,
    /** 课程号是占位值（工作簿用 x 代表待确认的数字，如 008532xx）。课程仍然入库， 只是真实编号未知，必须让人看见。不阻断发布。 */
    COURSE_CODE_PENDING,
    /** 连号课程号（如 01014125~127）已按工作簿原文展开为多门课。不阻断发布。 */
    COURSE_CODE_RANGE_EXPANDED,
    /** 连号课程组的学分是整组合计（工作簿没有给出每门的拆分），展开后各门学分记为未知（null）。 不阻断发布，但学分不能被当作已知值使用。 */
    CREDITS_UNSPLIT,
    /** 「课程组/要求行（非单门课程）」不是单门课程，不作为课程入库。它的类别学分要求已经 由类别要求表覆盖，所以跳过它不丢任何必修课。不阻断发布。 */
    GROUP_REQUIREMENT_ROW;

    /**
     * 阻断性问题：出现任何一条整批都不能发布。 结构错误、学分非数字、类别缺失、课程组内非法课程号等属于这一类。 未建模规则不阻断：它们被快照级保存，并随学业核对/方案核验显式带出
     * unknown。 非阻断（可记录）的有五类：课程号占位、连号展开、学分未拆分、课程组要求行、未建模规则（见各枚举值注释）。
     */
    public boolean blocking() {
      return switch (this) {
        case COURSE_CODE_PENDING,
            COURSE_CODE_RANGE_EXPANDED,
            CREDITS_UNSPLIT,
            GROUP_REQUIREMENT_ROW,
            UNKNOWN_RULE ->
            false;
        default -> true;
      };
    }
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

  /** credits 为 null 表示学分未知（连号课程组未拆分），不是 0。 */
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
      List<ImportIssue> issues,
      List<UnmodeledRule> unmodeledRules) {

    /** 阻断性问题列表；为空才可以发布。 */
    public List<ImportIssue> blockingIssues() {
      return issues.stream().filter(issue -> issue.code().blocking()).toList();
    }

    /** 可记录问题列表：不阻断发布，但要展示给用户（例如待确认的课程号）。 */
    public List<ImportIssue> recordedIssues() {
      return issues.stream().filter(issue -> !issue.code().blocking()).toList();
    }

    public boolean publishable() {
      return blockingIssues().isEmpty();
    }
  }

  /**
   * 工作簿「备注」区段的一条规则或待核问题，原文保留。 disposition：UNMODELED = 未建模，带入核验 unknown；EXCLUDED = 按负责人要求排除（原表课程行）。
   */
  public record UnmodeledRule(
      String sheet,
      int row,
      String sourceLocator,
      String subject,
      String originalNote,
      String currentStatus,
      String sourceType,
      Disposition disposition) {
    public enum Disposition {
      UNMODELED,
      EXCLUDED
    }
  }

  public record PublishResult(String snapshotId, boolean reused) {}

  @FunctionalInterface
  public interface PublishPort {
    PublishResult publish(CurriculumDraft draft);
  }
}
