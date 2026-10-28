package edu.coursepilot.importer;

import static edu.coursepilot.importer.ImportModels.IssueCode.*;

import edu.coursepilot.importer.ImportModels.CategoryRequirement;
import edu.coursepilot.importer.ImportModels.CurriculumDraft;
import edu.coursepilot.importer.ImportModels.CurriculumEntry;
import edu.coursepilot.importer.ImportModels.ImportIssue;
import edu.coursepilot.importer.ImportModels.SourceRef;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.math.BigDecimal;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;
import org.apache.poi.ooxml.POIXMLException;
import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.CellType;
import org.apache.poi.ss.usermodel.DataFormatter;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.xssf.usermodel.XSSFCell;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;

/** Reads one selected path from the approved A1 workbook layout. Never evaluates formulas. */
public final class A1WorkbookImporter {
  public static final String VERSION = "a1-xlsx-1";
  private static final Map<String, String> TRACK_SHEETS =
      Map.of(
          "cs-direct", "计科学直招",
          "cs-general", "计科学",
          "ai-science-direct", "智能科直招",
          "ai-science", "智能科",
          "cybersecurity-direct", "网安全直招",
          "cybersecurity", "网安全",
          "ai-engineering-direct", "人智能直招",
          "ai-engineering", "人智能");
  /** contracts/schemas/domain.schema.json Course.courseCode pattern. */
  private static final Pattern COURSE_CODE = Pattern.compile("^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$");
  private final XlsxInputGuard inputGuard = new XlsxInputGuard();

  public CurriculumDraft prepare(Path file, String trackId) {
    if (trackId == null) {
      throw new XlsxInputGuard.ImportRejectedException(TRACK_NOT_ALLOWED);
    }
    String trackSheet = TRACK_SHEETS.get(trackId);
    if (trackSheet == null) {
      throw new XlsxInputGuard.ImportRejectedException(TRACK_NOT_ALLOWED);
    }
    byte[] bytes = inputGuard.read(file);
    String hash = sha256(bytes);
    List<ImportIssue> issues = new ArrayList<>();
    List<CategoryRequirement> requirements = new ArrayList<>();
    List<CurriculumEntry> entries = new ArrayList<>();
    try (XSSFWorkbook workbook = new XSSFWorkbook(new ByteArrayInputStream(bytes))) {
      var sheet = workbook.getSheet(trackSheet);
      if (sheet == null
          || !cellText(sheet.getRow(0), 0).startsWith("CoursePilot｜2024级培养计划课程清单｜" + trackSheet)) {
        issues.add(new ImportIssue(TEMPLATE_MISMATCH, trackSheet, 1, 1));
      } else {
        readSelectedSheet(sheet, trackSheet, hash, requirements, entries, issues);
      }
    } catch (IOException | POIXMLException e) {
      issues.add(new ImportIssue(INVALID_OOXML, trackSheet, 1, 1));
    }
    String naturalKey = normalizedKey(trackId, requirements, entries, issues);
    if (requirements.isEmpty() || entries.isEmpty()) {
      issues.add(new ImportIssue(INVALID_ROW, trackSheet, 1, 1));
    }
    return new CurriculumDraft(
        trackId,
        hash,
        VERSION,
        naturalKey,
        List.copyOf(requirements),
        List.copyOf(entries),
        List.copyOf(issues));
  }

  public ImportModels.PublishResult publish(CurriculumDraft draft, ImportModels.PublishPort port) {
    if (!draft.publishable()) {
      throw new IllegalStateException("Rejected draft cannot be published");
    }
    return port.publish(draft);
  }

  private void readSelectedSheet(
      org.apache.poi.ss.usermodel.Sheet sheet,
      String track,
      String hash,
      List<CategoryRequirement> requirements,
      List<CurriculumEntry> entries,
      List<ImportIssue> issues) {
    int requirementHeader = findRow(sheet, "课程类别", "要求学分", "原表学分文本");
    int detailHeader = findRow(sheet, "课程名称/课程组", "课程编号（原文或规则）", "记录性质");
    int ruleHeader = findRow(sheet, "涉及对象/规则", "原表说明或待核问题", "当前解释与处理状态");
    if (requirementHeader < 0 || detailHeader < 0 || ruleHeader < 0) {
      issues.add(new ImportIssue(TEMPLATE_MISMATCH, track, 1, 1));
      return;
    }
    for (Row row : sheet) {
      for (Cell cell : row) {
        if (cell.getCellType() == CellType.FORMULA
            && (cell.getCachedFormulaResultType() == CellType.BLANK
                || cell.getCachedFormulaResultType() == CellType._NONE
                || (cell instanceof XSSFCell xssfCell
                    && (!xssfCell.getCTCell().isSetV()
                        || xssfCell.getCTCell().getV() == null
                        || xssfCell.getCTCell().getV().isBlank())))) {
          issues.add(
              new ImportIssue(
                  FORMULA_WITHOUT_CACHED_VALUE,
                  track,
                  row.getRowNum() + 1,
                  cell.getColumnIndex() + 1));
        }
      }
    }
    DataFormatter formatter = new DataFormatter(java.util.Locale.ROOT);
    BigDecimal statedTotal = null;
    BigDecimal categoryTotal = BigDecimal.ZERO;
    for (int r = requirementHeader + 1; r < detailHeader - 1; r++) {
      Row row = sheet.getRow(r);
      if (isEmpty(row, 1)) continue;
      String rowTrack = text(row, 0, formatter);
      if (!track.equals(rowTrack)) {
        issues.add(new ImportIssue(TEMPLATE_MISMATCH, track, r + 1, 1));
        continue;
      }
      String category = text(row, 1, formatter);
      BigDecimal credits = decimal(text(row, 2, formatter));
      if (category.isBlank() || category.length() > 32) {
        issues.add(new ImportIssue(INVALID_ROW, track, r + 1, 2));
        continue;
      }
      if (credits == null) {
        issues.add(new ImportIssue(INVALID_CREDITS, track, r + 1, 3));
        continue;
      }
      if ("总计".equals(category)) {
        statedTotal = credits;
      } else {
        categoryTotal = categoryTotal.add(credits);
            requirements.add(
            new CategoryRequirement(
                category,
                credits,
                text(row, 3, formatter),
                    source(hash, trackId(track), track, r, 2, text(row, 4, formatter))));
      }
    }
    if (statedTotal == null || statedTotal.compareTo(categoryTotal) != 0) {
      issues.add(new ImportIssue(TOTAL_MISMATCH, track, requirementHeader + 1, 3));
    }

    Map<String, CurriculumEntry> byCode = new HashMap<>();
    for (int r = detailHeader + 1; r < ruleHeader - 1; r++) {
      Row row = sheet.getRow(r);
      if (isEmpty(row, 1)) continue;
      if (!track.equals(text(row, 0, formatter))) {
        issues.add(new ImportIssue(TEMPLATE_MISMATCH, track, r + 1, 1));
        continue;
      }
      String name = text(row, 1, formatter);
      String code = text(row, 2, formatter);
      String category = text(row, 3, formatter);
      BigDecimal credits = decimal(text(row, 4, formatter));
      String term = text(row, 5, formatter);
      String kind = text(row, 8, formatter);
      if (name.isBlank() || category.isBlank() || credits == null || kind.isBlank()) {
        issues.add(new ImportIssue(INVALID_ROW, track, r + 1, 2));
        continue;
      }
      CurriculumEntry entry =
          new CurriculumEntry(
              name,
              code,
              category,
              credits,
              term,
              kind,
              source(hash, trackId(track), track, r, 1, text(row, 6, formatter)));
      if (!"课程明细".equals(kind)) {
        // Java currently stores only concrete courses, not choice groups or rule expressions.
        // Refuse to publish those rows until a typed persistence model exists.
        issues.add(new ImportIssue(UNSUPPORTED_ENTRY, track, r + 1, 3));
      } else if (!COURSE_CODE.matcher(code).matches()) {
        issues.add(new ImportIssue(INVALID_COURSE_CODE, track, r + 1, 3));
      } else if (code.length() > 32) {
        // The persisted Course primary key is narrower than the public DTO contract.
        issues.add(new ImportIssue(COURSE_CODE_TOO_LONG, track, r + 1, 3));
      }
      if (name.length() > 200 || category.length() > 100) {
        issues.add(new ImportIssue(INVALID_ROW, track, r + 1, 2));
      }
      if (!code.isBlank()) {
        CurriculumEntry previous = byCode.putIfAbsent(code, entry);
        if (previous != null) {
          boolean conflicting =
              !previous.name().equals(name)
                  || previous.credits().compareTo(credits) != 0
                  || !previous.category().equals(category)
                  || !previous.suggestedTerm().equals(term);
          issues.add(
              new ImportIssue(
                  conflicting ? DUPLICATE_COURSE_CONFLICT : DUPLICATE_COURSE, track, r + 1, 3));
        }
      }
      entries.add(entry);
    }

    for (int r = ruleHeader + 1; r <= sheet.getLastRowNum(); r++) {
      Row row = sheet.getRow(r);
      if (isEmpty(row, 1)) continue;
      String rowTrack = text(row, 0, formatter);
      if (!track.equals(rowTrack)) continue;
      String status = text(row, 4, formatter);
      String kind = text(row, 5, formatter);
      if (kind.contains("规则")
          || kind.contains("课程行")
          || status.contains("待")
          || status.contains("冲突")) {
        issues.add(new ImportIssue(UNKNOWN_RULE, track, r + 1, 5));
      }
    }
  }

  private String text(Row row, int column, DataFormatter formatter) {
    if (row == null) return "";
    Cell cell = row.getCell(column, Row.MissingCellPolicy.RETURN_BLANK_AS_NULL);
    if (cell == null) return "";
    if (cell.getCellType() != CellType.FORMULA) return formatter.formatCellValue(cell).trim();
    CellType cachedType = cell.getCachedFormulaResultType();
    return switch (cachedType) {
      case STRING -> cell.getStringCellValue().trim();
      case NUMERIC ->
          formatter
              .formatRawCellContents(
                  cell.getNumericCellValue(),
                  cell.getCellStyle().getDataFormat(),
                  cell.getCellStyle().getDataFormatString())
              .trim();
      case BOOLEAN -> Boolean.toString(cell.getBooleanCellValue());
      case BLANK, _NONE, ERROR, FORMULA -> "";
    };
  }

  private String cellText(Row row, int column) {
    if (row == null || row.getCell(column) == null) return "";
    return row.getCell(column).getStringCellValue();
  }

  private boolean isEmpty(Row row, int column) {
    return row == null || text(row, column, new DataFormatter(java.util.Locale.ROOT)).isBlank();
  }

  private int findRow(org.apache.poi.ss.usermodel.Sheet sheet, String... markers) {
    for (int r = 0; r <= sheet.getLastRowNum(); r++) {
      Row row = sheet.getRow(r);
      boolean matches = true;
      for (String marker : markers) {
        boolean found = false;
        if (row != null) {
          for (Cell cell : row) {
            if (cell.getCellType() == CellType.STRING
                && cell.getStringCellValue().contains(marker)) {
              found = true;
              break;
            }
          }
        }
        matches &= found;
      }
      if (matches) return r;
    }
    return -1;
  }

  private SourceRef source(
      String hash,
      String trackId,
      String sheet,
      int zeroBasedRow,
      int zeroBasedColumn,
      String originalLocator) {
    int row = zeroBasedRow + 1;
    int column = zeroBasedColumn + 1;
    return new SourceRef(
        hash + ":" + trackId + ":" + row + ":" + column,
        "A1_CURRICULUM_XLSX",
        null,
        hash,
        sheet,
        row,
        column,
        originalLocator,
        Instant.now());
  }

  private String trackId(String sheet) {
    return TRACK_SHEETS.entrySet().stream()
        .filter(entry -> entry.getValue().equals(sheet))
        .map(Map.Entry::getKey)
        .findFirst()
        .orElseThrow(() -> new IllegalArgumentException("Unknown import sheet"));
  }

  private BigDecimal decimal(String value) {
    if (value == null || value.isBlank()) return null;
    try {
      BigDecimal parsed = new BigDecimal(value.trim());
      return parsed.scale() <= 2 && parsed.signum() >= 0
              && parsed.compareTo(new BigDecimal("1000")) <= 0
          ? parsed
          : null;
    } catch (NumberFormatException e) {
      return null;
    }
  }

  private String sha256(byte[] bytes) {
    try {
      return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
    } catch (NoSuchAlgorithmException e) {
      throw new IllegalStateException("SHA-256 unavailable", e);
    }
  }

  private String normalizedKey(
      String trackId,
      List<CategoryRequirement> requirements,
      List<CurriculumEntry> entries,
      List<ImportIssue> issues) {
    StringBuilder canonical = new StringBuilder();
    append(canonical, VERSION);
    append(canonical, trackId);
    for (CategoryRequirement requirement : requirements) {
      append(canonical, "requirement");
      append(canonical, requirement.category());
      append(canonical, requirement.requiredCredits().toPlainString());
      append(canonical, requirement.rawCredits());
      append(canonical, requirement.source().originalLocator());
    }
    for (CurriculumEntry entry : entries) {
      append(canonical, "entry");
      append(canonical, entry.name());
      append(canonical, entry.courseCode());
      append(canonical, entry.category());
      append(canonical, entry.credits().toPlainString());
      append(canonical, entry.suggestedTerm());
      append(canonical, entry.recordKind());
      append(canonical, entry.source().originalLocator());
    }
    for (ImportIssue issue : issues) {
      append(canonical, issue.code().name());
      append(canonical, issue.sheet());
      append(canonical, Integer.toString(issue.row()));
      append(canonical, Integer.toString(issue.column()));
    }
    return sha256(canonical.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8));
  }

  private void append(StringBuilder target, String value) {
    String safeValue = value == null ? "" : value;
    target.append(safeValue.length()).append(':').append(safeValue);
  }
}
