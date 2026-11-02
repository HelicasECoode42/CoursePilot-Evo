package edu.coursepilot.importer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import java.util.zip.ZipOutputStream;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class A1WorkbookImporterTest {
  @TempDir Path tempDir;

  @Test
  void readsSingleParallelTrackAndPreservesLeadingZeroCourseCode() throws Exception {
    Path workbook = workbook(false);

    var draft = new A1WorkbookImporter().prepare(workbook, "cs-general");
    var sameInput = new A1WorkbookImporter().prepare(workbook, "cs-general");

    assertEquals("cs-general", draft.trackId());
    assertEquals(1, draft.requirements().size());
    assertEquals(1, draft.entries().size());
    assertEquals("00123456", draft.entries().getFirst().courseCode());
    assertEquals("第二学年", draft.entries().getFirst().suggestedTerm());
    assertEquals(18, draft.entries().getFirst().source().row());
    assertEquals("source!B2", draft.entries().getFirst().source().originalLocator());
    assertEquals("A1_CURRICULUM_XLSX", draft.entries().getFirst().source().kind());
    assertNull(draft.entries().getFirst().source().snapshotId());
    assertEquals(draft.idempotencyKey(), sameInput.idempotencyKey());
    assertTrue(draft.publishable());
  }

  @Test
  void validatesCourseCodePatternAndPersistenceLength() throws Exception {
    for (String code : new String[] {"CS 101", "中文101"}) {
      var draft =
          new A1WorkbookImporter()
              .prepare(workbookWithCourse(code, "Valid name", "核心课程"), "cs-general");
      assertFalse(draft.publishable());
      assertTrue(
          draft.issues().stream()
              .anyMatch(issue -> issue.code() == ImportModels.IssueCode.INVALID_COURSE_CODE));
    }

    var tooLong =
        new A1WorkbookImporter()
            .prepare(workbookWithCourse("A".repeat(33), "Valid name", "核心课程"), "cs-general");
    assertFalse(tooLong.publishable());
    assertTrue(
        tooLong.issues().stream()
            .anyMatch(issue -> issue.code() == ImportModels.IssueCode.COURSE_CODE_TOO_LONG));
  }

  @Test
  void courseNameAndCategoryRespectDtoAndMembershipBoundaries() throws Exception {
    var maximum =
        new A1WorkbookImporter()
            .prepare(
                workbookWithCourse("A".repeat(32), "N".repeat(200), "C".repeat(100)), "cs-general");
    assertTrue(maximum.publishable(), maximum.issues().toString());

    var longName =
        new A1WorkbookImporter()
            .prepare(workbookWithCourse("COURSE1", "N".repeat(201), "核心课程"), "cs-general");
    assertFalse(longName.publishable());
    assertTrue(
        longName.issues().stream()
            .anyMatch(issue -> issue.code() == ImportModels.IssueCode.INVALID_ROW));

    var longCategory =
        new A1WorkbookImporter()
            .prepare(workbookWithCourse("COURSE1", "Valid name", "C".repeat(101)), "cs-general");
    assertFalse(longCategory.publishable());
    assertTrue(
        longCategory.issues().stream()
            .anyMatch(issue -> issue.code() == ImportModels.IssueCode.INVALID_ROW));
  }

  @Test
  void unmodeledRuleIsCarriedAsSnapshotRuleAndNoLongerBlocksPublication() throws Exception {
    var draft = new A1WorkbookImporter().prepare(workbook(true), "cs-general");

    assertTrue(draft.publishable(), draft.blockingIssues().toString());
    assertTrue(
        draft.recordedIssues().stream()
            .anyMatch(issue -> issue.code() == ImportModels.IssueCode.UNKNOWN_RULE));
    assertEquals(1, draft.unmodeledRules().size());
    var rule = draft.unmodeledRules().getFirst();
    assertEquals(ImportModels.UnmodeledRule.Disposition.UNMODELED, rule.disposition());
    assertEquals("source!A3", rule.sourceLocator());
    assertEquals("Synthetic unresolved rule", rule.subject());
    assertEquals("raw note", rule.originalNote());
    assertEquals("原表注释/规则", rule.sourceType());
    // 发布路径仍然可用：未建模规则不再被当作阻断。
    var published =
        new A1WorkbookImporter()
            .publish(draft, ignored -> new ImportModels.PublishResult("SNAP", false));
    assertEquals("SNAP", published.snapshotId());
  }

  @Test
  void excludedSourceRowIsKeptWithDispositionExcluded() throws Exception {
    var draft =
        new A1WorkbookImporter().prepare(workbookWithRule("原表课程行", "Java EE开发技术"), "cs-general");

    assertTrue(draft.publishable(), draft.blockingIssues().toString());
    assertEquals(1, draft.unmodeledRules().size());
    assertEquals(
        ImportModels.UnmodeledRule.Disposition.EXCLUDED,
        draft.unmodeledRules().getFirst().disposition());
    assertTrue(
        draft.recordedIssues().stream()
            .noneMatch(issue -> issue.code() == ImportModels.IssueCode.UNKNOWN_RULE));
  }

  @Test
  void confirmedRangeCreditsSplitExactlyAsUserConfirmed() throws Exception {
    var draft =
        new A1WorkbookImporter()
            .prepare(
                detailWorkbook(
                    new String[][] {{"微积分(1-3)", "01014125~127", "核心课程", "16", "第一学年", "课程明细"}}),
                "cs-general");

    assertEquals(
        List.of(new BigDecimal("6"), new BigDecimal("6"), new BigDecimal("4")),
        draft.entries().stream().map(ImportModels.CurriculumEntry::credits).toList());
    assertTrue(
        draft.recordedIssues().stream()
            .noneMatch(issue -> issue.code() == ImportModels.IssueCode.CREDITS_UNSPLIT));
  }

  @Test
  void confirmedRangeCreditsThatDoNotMatchWorkbookTotalBlock() throws Exception {
    var draft =
        new A1WorkbookImporter()
            .prepare(
                detailWorkbook(
                    new String[][] {{"大学物理(1-2)", "01034117~118", "核心课程", "9", "第一学年", "课程明细"}}),
                "cs-general");

    assertFalse(draft.publishable());
    assertTrue(
        draft.blockingIssues().stream()
            .anyMatch(issue -> issue.code() == ImportModels.IssueCode.INVALID_CREDITS));
  }

  @Test
  void unconfirmedRangeStaysUnknownCredits() throws Exception {
    var draft =
        new A1WorkbookImporter()
            .prepare(
                detailWorkbook(
                    new String[][] {{"未知连号课", "01014100~101", "核心课程", "4", "第一学年", "课程明细"}}),
                "cs-general");

    assertTrue(draft.entries().stream().allMatch(e -> e.credits() == null));
    assertTrue(
        draft.recordedIssues().stream()
            .anyMatch(issue -> issue.code() == ImportModels.IssueCode.CREDITS_UNSPLIT));
  }

  @Test
  void rejectsNonXlsxInputBeforeReadingWorkbook() throws Exception {
    Path wrong = tempDir.resolve("curriculum.xls");
    Files.writeString(wrong, "not an xlsx");

    var error =
        assertThrows(
            XlsxInputGuard.ImportRejectedException.class,
            () -> new A1WorkbookImporter().prepare(wrong, "cs-general"));

    assertEquals(ImportModels.IssueCode.WRONG_EXTENSION, error.code());
  }

  @Test
  void rejectsOversizedFileAndInvalidZipContent() throws Exception {
    Path oversized = tempDir.resolve("oversized.xlsx");
    try (var output = Files.newOutputStream(oversized)) {
      output.write(new byte[XlsxInputGuard.MAX_BYTES + 1]);
    }
    var sizeError =
        assertThrows(
            XlsxInputGuard.ImportRejectedException.class,
            () -> new A1WorkbookImporter().prepare(oversized, "cs-general"));
    assertEquals(ImportModels.IssueCode.FILE_TOO_LARGE, sizeError.code());

    Path invalid = tempDir.resolve("invalid.xlsx");
    Files.writeString(invalid, "not a zip container");
    var formatError =
        assertThrows(
            XlsxInputGuard.ImportRejectedException.class,
            () -> new A1WorkbookImporter().prepare(invalid, "cs-general"));
    assertEquals(ImportModels.IssueCode.INVALID_OOXML, formatError.code());
  }

  @Test
  void rejectsUnknownTrackId() throws Exception {
    Path workbook = workbook(false);
    var error =
        assertThrows(
            XlsxInputGuard.ImportRejectedException.class,
            () -> new A1WorkbookImporter().prepare(workbook, "some-other-track"));
    assertEquals(ImportModels.IssueCode.TRACK_NOT_ALLOWED, error.code());
  }

  @Test
  void changingParallelTrackChangesNaturalKey() throws Exception {
    Path workbook = workbook(false);
    var csDraft = new A1WorkbookImporter().prepare(workbook, "cs-general");
    var aiDraft = new A1WorkbookImporter().prepare(workbook, "ai-science");
    assertFalse(csDraft.idempotencyKey().equals(aiDraft.idempotencyKey()));
    assertTrue(
        aiDraft.issues().stream()
            .anyMatch(issue -> issue.code() == ImportModels.IssueCode.TEMPLATE_MISMATCH));
  }

  @Test
  void idempotencyKeyIgnoresUnselectedSheets() throws Exception {
    Path original = workbook(false);
    Path withOtherPath = tempDir.resolve("with-other-path.xlsx");
    try (var input = Files.newInputStream(original);
        XSSFWorkbook workbook = new XSSFWorkbook(input)) {
      workbook.createSheet("unselected-path").createRow(0).createCell(0).setCellValue("irrelevant");
      try (OutputStream output = Files.newOutputStream(withOtherPath)) {
        workbook.write(output);
      }
    }

    var originalDraft = new A1WorkbookImporter().prepare(original, "cs-general");
    var modifiedDraft = new A1WorkbookImporter().prepare(withOtherPath, "cs-general");
    assertFalse(originalDraft.workbookHash().equals(modifiedDraft.workbookHash()));
    assertEquals(originalDraft.idempotencyKey(), modifiedDraft.idempotencyKey());
  }

  @Test
  void blocksTotalsDuplicateCodesAndFormulaWithoutCachedValue() throws Exception {
    var draft =
        new A1WorkbookImporter().prepare(workbook(false, true, false, true, true), "cs-general");

    assertTrue(
        draft.issues().stream()
            .anyMatch(issue -> issue.code() == ImportModels.IssueCode.TOTAL_MISMATCH));
    assertTrue(
        draft.issues().stream()
            .anyMatch(issue -> issue.code() == ImportModels.IssueCode.DUPLICATE_COURSE_CONFLICT));
    assertTrue(
        draft.issues().stream()
            .anyMatch(
                issue -> issue.code() == ImportModels.IssueCode.FORMULA_WITHOUT_CACHED_VALUE));
    assertFalse(draft.publishable());
  }

  @Test
  void blocksIdenticalDuplicateCourseCodeInsteadOfSilentlyDuplicatingIt() throws Exception {
    var draft =
        new A1WorkbookImporter().prepare(workbook(false, false, true, false, false), "cs-general");
    assertTrue(
        draft.issues().stream()
            .anyMatch(issue -> issue.code() == ImportModels.IssueCode.DUPLICATE_COURSE));
    assertFalse(draft.publishable());
  }

  @Test
  void expandsRangeCodeIntoMembersWithUnknownCredits() throws Exception {
    var draft =
        new A1WorkbookImporter()
            .prepare(
                detailWorkbook(
                    new String[][] {{"微积分(1-3)", "01014125~127", "核心课程", "16", "第一学年", "课程明细"}}),
                "cs-general");

    assertEquals(
        List.of("01014125", "01014126", "01014127"),
        draft.entries().stream().map(ImportModels.CurriculumEntry::courseCode).toList());
    // 已确认的逐门拆分：微积分(1-3) 按用户确认为 6+6+4，不能每门都记 16。
    assertEquals(
        List.of(new BigDecimal("6"), new BigDecimal("6"), new BigDecimal("4")),
        draft.entries().stream().map(ImportModels.CurriculumEntry::credits).toList());
    // 同一工作簿行展开出的多门课必须有各自的 SourceReference 主键。
    assertEquals(3, draft.entries().stream().map(e -> e.source().refId()).distinct().count());
    assertTrue(draft.publishable(), draft.blockingIssues().toString());
    assertTrue(
        draft.recordedIssues().stream()
            .anyMatch(i -> i.code() == ImportModels.IssueCode.COURSE_CODE_RANGE_EXPANDED));
    assertTrue(
        draft.recordedIssues().stream()
            .noneMatch(i -> i.code() == ImportModels.IssueCode.CREDITS_UNSPLIT));
  }

  @Test
  void rejectsMalformedRangeSpans() {
    assertEquals(List.of("08305140", "08305141"), A1WorkbookImporter.expandRange("08305140~141"));
    assertEquals(List.of("0830A030", "0830A031"), A1WorkbookImporter.expandRange("0830A030~031"));
    assertNull(A1WorkbookImporter.expandRange("01014127~125"));
    assertNull(A1WorkbookImporter.expandRange("01014125~1270"));
    assertNull(A1WorkbookImporter.expandRange("01014100~199"));
    assertNull(A1WorkbookImporter.expandRange("~127"));
  }

  @Test
  void keepsEveryPlaceholderCourseAndMarksCodesPending() throws Exception {
    var draft =
        new A1WorkbookImporter()
            .prepare(
                detailWorkbook(
                    new String[][] {
                      {"体育1", "008532xx", "公共基础课", "1", "第一学年 第1学期", "课程明细"},
                      {"体育2", "008532xx", "公共基础课", "1", "第一学年 第2学期", "课程明细"},
                      {"体育3", "008532xx", "公共基础课", "1", "第一学年 第3学期", "课程明细"}
                    }),
                "cs-general");

    assertEquals(
        List.of("体育1", "体育2", "体育3"),
        draft.entries().stream().map(ImportModels.CurriculumEntry::name).toList());
    assertTrue(draft.entries().stream().allMatch(e -> "008532xx".equals(e.courseCode())));
    assertTrue(draft.publishable(), draft.blockingIssues().toString());
    assertEquals(
        3,
        draft.recordedIssues().stream()
            .filter(i -> i.code() == ImportModels.IssueCode.COURSE_CODE_PENDING)
            .count());
  }

  @Test
  void exactDuplicatePlaceholderRowIsStillBlocked() throws Exception {
    var draft =
        new A1WorkbookImporter()
            .prepare(
                detailWorkbook(
                    new String[][] {
                      {"体育1", "008532xx", "公共基础课", "1", "第一学年 第1学期", "课程明细"},
                      {"体育1", "008532xx", "公共基础课", "1", "第一学年 第1学期", "课程明细"}
                    }),
                "cs-general");

    assertFalse(draft.publishable());
    assertTrue(
        draft.blockingIssues().stream()
            .anyMatch(i -> i.code() == ImportModels.IssueCode.DUPLICATE_COURSE));
  }

  @Test
  void structuralErrorsStillBlockWhenCodesArePlaceholders() throws Exception {
    var badCredits =
        new A1WorkbookImporter()
            .prepare(
                detailWorkbook(
                    new String[][] {{"体育1", "008532xx", "公共基础课", "一", "第一学年 第1学期", "课程明细"}}),
                "cs-general");
    assertFalse(badCredits.publishable());
    assertTrue(
        badCredits.blockingIssues().stream()
            .anyMatch(i -> i.code() == ImportModels.IssueCode.INVALID_CREDITS));

    var missingCategory =
        new A1WorkbookImporter()
            .prepare(
                detailWorkbook(new String[][] {{"体育2", "008532xx", "", "1", "第一学年 第2学期", "课程明细"}}),
                "cs-general");
    assertFalse(missingCategory.publishable());
    assertTrue(
        missingCategory.blockingIssues().stream()
            .anyMatch(i -> i.code() == ImportModels.IssueCode.INVALID_ROW));
  }

  @Test
  void groupRequirementRowIsRecordedAndNotStoredAsCourse() throws Exception {
    var draft =
        new A1WorkbookImporter()
            .prepare(
                detailWorkbook(
                    new String[][] {
                      {"通识课课程组（具体选修课见附表）", "", "通识课", "12", "", "课程组/要求行（非单门课程）"},
                      {"形势与政策", "16583109", "公共基础课", "1", "", "课程明细"}
                    }),
                "cs-general");

    assertEquals(1, draft.entries().size());
    assertEquals("16583109", draft.entries().getFirst().courseCode());
    assertTrue(draft.publishable(), draft.blockingIssues().toString());
    assertTrue(
        draft.recordedIssues().stream()
            .anyMatch(i -> i.code() == ImportModels.IssueCode.GROUP_REQUIREMENT_ROW));
  }

  /** 合成一个只含一段课程明细的工作簿（计科学页签）。每个课程行为 {名称, 课程号, 类别, 学分文本, 建议学期, 记录性质}。 */
  private Path detailWorkbook(String[][] courseRows) throws Exception {
    Path path = tempDir.resolve("detail-" + System.nanoTime() + ".xlsx");
    try (XSSFWorkbook workbook = new XSSFWorkbook()) {
      var sheet = workbook.createSheet("计科学");
      sheet.createRow(0).createCell(0).setCellValue("CoursePilot｜2024级培养计划课程清单｜计科学");
      sheet.createRow(4).createCell(0).setCellValue("一、各专业课程类别学分要求");
      var requirementHeader = sheet.createRow(5);
      requirementHeader.createCell(0).setCellValue("专业路径");
      requirementHeader.createCell(1).setCellValue("课程类别");
      requirementHeader.createCell(2).setCellValue("要求学分");
      requirementHeader.createCell(3).setCellValue("原表学分文本");
      requirementHeader.createCell(4).setCellValue("原表位置");
      var category = sheet.createRow(6);
      category.createCell(0).setCellValue("计科学");
      category.createCell(1).setCellValue("核心课程");
      category.createCell(2).setCellValue(3);
      category.createCell(3).setCellValue("3");
      category.createCell(4).setCellValue("source!A1");
      var total = sheet.createRow(7);
      total.createCell(0).setCellValue("计科学");
      total.createCell(1).setCellValue("总计");
      total.createCell(2).setCellValue(3);
      total.createCell(3).setCellValue("3");
      total.createCell(4).setCellValue("source!A1");

      sheet.createRow(15).createCell(0).setCellValue("二、总体课程与课程组明细");
      var detailHeader = sheet.createRow(16);
      detailHeader.createCell(0).setCellValue("专业路径");
      detailHeader.createCell(1).setCellValue("课程名称/课程组");
      detailHeader.createCell(2).setCellValue("课程编号（原文或规则）");
      detailHeader.createCell(3).setCellValue("课程类别");
      detailHeader.createCell(4).setCellValue("学分");
      detailHeader.createCell(5).setCellValue("建议修读学期");
      detailHeader.createCell(6).setCellValue("原表位置");
      detailHeader.createCell(8).setCellValue("记录性质");
      for (int i = 0; i < courseRows.length; i++) {
        String[] values = courseRows[i];
        var row = sheet.createRow(17 + i);
        row.createCell(0).setCellValue("计科学");
        row.createCell(1).setCellValue(values[0]);
        row.createCell(2).setCellValue(values[1]);
        row.createCell(3).setCellValue(values[2]);
        row.createCell(4).setCellValue(values[3]);
        row.createCell(5).setCellValue(values[4]);
        row.createCell(6).setCellValue("source!B" + (i + 2));
        row.createCell(8).setCellValue(values[5]);
      }
      int ruleHeaderRow = 17 + courseRows.length + 1;
      sheet.createRow(ruleHeaderRow - 1).createCell(0).setCellValue("三、备注：无法解释或需确认的规则");
      var ruleHeader = sheet.createRow(ruleHeaderRow);
      ruleHeader.createCell(1).setCellValue("原表位置");
      ruleHeader.createCell(2).setCellValue("涉及对象/规则");
      ruleHeader.createCell(3).setCellValue("原表说明或待核问题");
      ruleHeader.createCell(4).setCellValue("当前解释与处理状态");
      ruleHeader.createCell(5).setCellValue("来源类型");
      try (OutputStream out = Files.newOutputStream(path)) {
        workbook.write(out);
      }
    }
    return path;
  }

  private Path workbookWithRule(String sourceType, String subject) throws Exception {
    Path path = workbook(false);
    try (var input = Files.newInputStream(path);
        XSSFWorkbook workbook = new XSSFWorkbook(input)) {
      var sheet = workbook.getSheet("计科学");
      var rule = sheet.createRow(21);
      rule.createCell(0).setCellValue("计科学");
      rule.createCell(1).setCellValue("source!A3");
      rule.createCell(2).setCellValue(subject);
      rule.createCell(3).setCellValue("按负责人要求删除");
      rule.createCell(4).setCellValue("冲突待确认");
      rule.createCell(5).setCellValue(sourceType);
      Path modified = tempDir.resolve("rule-" + System.nanoTime() + ".xlsx");
      try (OutputStream output = Files.newOutputStream(modified)) {
        workbook.write(output);
      }
      return modified;
    }
  }

  private Path workbook(boolean withUnknownRule) throws Exception {
    return workbook(withUnknownRule, false, false, false, false);
  }

  private Path workbookWithCourse(String code, String name, String category) throws Exception {
    Path original = workbook(false);
    Path modified = tempDir.resolve("course-properties.xlsx");
    try (var input = Files.newInputStream(original);
        XSSFWorkbook workbook = new XSSFWorkbook(input)) {
      var course = workbook.getSheet("计科学").getRow(17);
      course.getCell(1).setCellValue(name);
      course.getCell(2).setCellValue(code);
      course.getCell(3).setCellValue(category);
      try (OutputStream output = Files.newOutputStream(modified)) {
        workbook.write(output);
      }
    }
    return modified;
  }

  private Path workbook(
      boolean withUnknownRule,
      boolean withConflictingDuplicate,
      boolean withExactDuplicate,
      boolean totalMismatch,
      boolean withUncachedFormula)
      throws Exception {
    Path path = tempDir.resolve("synthetic-curriculum.xlsx");
    try (XSSFWorkbook workbook = new XSSFWorkbook()) {
      var sheet = workbook.createSheet("计科学");
      sheet.createRow(0).createCell(0).setCellValue("CoursePilot｜2024级培养计划课程清单｜计科学");
      var requirementHeading = sheet.createRow(4);
      requirementHeading.createCell(0).setCellValue("一、各专业课程类别学分要求");
      var requirementHeader = sheet.createRow(5);
      requirementHeader.createCell(0).setCellValue("专业路径");
      requirementHeader.createCell(1).setCellValue("课程类别");
      requirementHeader.createCell(2).setCellValue("要求学分");
      requirementHeader.createCell(3).setCellValue("原表学分文本");
      requirementHeader.createCell(4).setCellValue("原表位置");
      var category = sheet.createRow(6);
      category.createCell(0).setCellValue("计科学");
      category.createCell(1).setCellValue("核心课程");
      category.createCell(2).setCellValue(3);
      category.createCell(3).setCellValue("3");
      category.createCell(4).setCellValue("source!A1");
      category.createCell(4).setCellValue("source!A1");
      var total = sheet.createRow(7);
      total.createCell(0).setCellValue("计科学");
      total.createCell(1).setCellValue("总计");
      total.createCell(2).setCellValue(totalMismatch ? 4 : 3);
      total.createCell(3).setCellValue("3");

      sheet.createRow(15).createCell(0).setCellValue("二、总体课程与课程组明细");
      var detailHeader = sheet.createRow(16);
      detailHeader.createCell(0).setCellValue("专业路径");
      detailHeader.createCell(1).setCellValue("课程名称/课程组");
      detailHeader.createCell(2).setCellValue("课程编号（原文或规则）");
      detailHeader.createCell(3).setCellValue("课程类别");
      detailHeader.createCell(4).setCellValue("学分");
      detailHeader.createCell(5).setCellValue("建议修读学期");
      detailHeader.createCell(6).setCellValue("原表位置");
      detailHeader.createCell(8).setCellValue("记录性质");
      var course = sheet.createRow(17);
      course.createCell(0).setCellValue("计科学");
      course.createCell(1).setCellValue("Synthetic course");
      course.createCell(2).setCellValue("00123456");
      course.createCell(3).setCellValue("核心课程");
      course.createCell(4).setCellValue(3);
      course.createCell(5).setCellValue("第二学年");
      course.createCell(6).setCellValue("source!B2");
      course.createCell(8).setCellValue("课程明细");
      if (withConflictingDuplicate) {
        var duplicate = sheet.createRow(18);
        duplicate.createCell(0).setCellValue("计科学");
        duplicate.createCell(1).setCellValue("Conflicting synthetic course");
        duplicate.createCell(2).setCellValue("00123456");
        duplicate.createCell(3).setCellValue("核心课程");
        duplicate.createCell(4).setCellValue(4);
        duplicate.createCell(6).setCellValue("source!B3");
        duplicate.createCell(8).setCellValue("课程明细");
      }
      if (withExactDuplicate) {
        var duplicate = sheet.createRow(18);
        duplicate.createCell(0).setCellValue("计科学");
        duplicate.createCell(1).setCellValue("Synthetic course");
        duplicate.createCell(2).setCellValue("00123456");
        duplicate.createCell(3).setCellValue("核心课程");
        duplicate.createCell(4).setCellValue(3);
        duplicate.createCell(5).setCellValue("第二学年");
        duplicate.createCell(6).setCellValue("source!B3");
        duplicate.createCell(8).setCellValue("课程明细");
      }

      sheet.createRow(19).createCell(0).setCellValue("三、备注：无法解释或需确认的规则");
      var ruleHeader = sheet.createRow(20);
      ruleHeader.createCell(1).setCellValue("原表位置");
      ruleHeader.createCell(2).setCellValue("涉及对象/规则");
      ruleHeader.createCell(3).setCellValue("原表说明或待核问题");
      ruleHeader.createCell(4).setCellValue("当前解释与处理状态");
      ruleHeader.createCell(5).setCellValue("来源类型");
      if (withUnknownRule) {
        var rule = sheet.createRow(21);
        rule.createCell(0).setCellValue("计科学");
        rule.createCell(1).setCellValue("source!A3");
        rule.createCell(2).setCellValue("Synthetic unresolved rule");
        rule.createCell(3).setCellValue("raw note");
        rule.createCell(4).setCellValue("待拆分复核");
        rule.createCell(5).setCellValue("原表注释/规则");
      }
      if (withUncachedFormula) {
        sheet.createRow(22).createCell(0).setCellFormula("1+1");
      }
      try (OutputStream out = Files.newOutputStream(path)) {
        workbook.write(out);
      }
    }
    if (withUncachedFormula) clearFormulaCache(path);
    return path;
  }

  private void clearFormulaCache(Path workbookPath) throws IOException {
    Path rewritten = tempDir.resolve("uncached-formula.xlsx");
    try (ZipInputStream input = new ZipInputStream(Files.newInputStream(workbookPath));
        ZipOutputStream output = new ZipOutputStream(Files.newOutputStream(rewritten))) {
      ZipEntry entry;
      while ((entry = input.getNextEntry()) != null) {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        input.transferTo(bytes);
        byte[] data = bytes.toByteArray();
        if (entry.getName().equals("xl/worksheets/sheet1.xml")) {
          String xml = new String(data, StandardCharsets.UTF_8);
          xml = xml.replaceAll("(<c[^>]*r=\"A23\"[^>]*>.*?<f>1\\+1</f>).*?(</c>)", "$1<v></v>$2");
          data = xml.getBytes(StandardCharsets.UTF_8);
        }
        output.putNextEntry(new ZipEntry(entry.getName()));
        output.write(data);
        output.closeEntry();
      }
    }
    Files.move(rewritten, workbookPath, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
  }
}
