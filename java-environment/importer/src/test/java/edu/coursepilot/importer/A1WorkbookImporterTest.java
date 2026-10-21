package edu.coursepilot.importer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
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
  void blocksUnknownRuleAndNeverCallsPublishPort() throws Exception {
    var draft = new A1WorkbookImporter().prepare(workbook(true), "cs-general");

    assertFalse(draft.publishable());
    assertTrue(
        draft.issues().stream()
            .anyMatch(issue -> issue.code() == ImportModels.IssueCode.UNKNOWN_RULE));
    assertThrows(
        IllegalStateException.class,
        () ->
            new A1WorkbookImporter()
                .publish(
                    draft,
                    ignored -> {
                      throw new AssertionError("publish must not be called");
                    }));
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

  private Path workbook(boolean withUnknownRule) throws Exception {
    return workbook(withUnknownRule, false, false, false, false);
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
