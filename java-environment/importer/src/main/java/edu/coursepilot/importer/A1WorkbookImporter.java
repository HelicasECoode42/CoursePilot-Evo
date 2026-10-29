package edu.coursepilot.importer;

import static edu.coursepilot.importer.ImportModels.IssueCode.*;

import edu.coursepilot.importer.ImportModels.CategoryRequirement;
import edu.coursepilot.importer.ImportModels.CurriculumDraft;
import edu.coursepilot.importer.ImportModels.CurriculumEntry;
import edu.coursepilot.importer.ImportModels.ImportIssue;
import edu.coursepilot.importer.ImportModels.SourceRef;
import edu.coursepilot.importer.ImportModels.UnmodeledRule;
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
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
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
  /**
   * 连号课程组的逐门学分拆分。来源：用户 2026-10-29 确认（工作簿只给整组学分）。
   * 键是工作簿原文课程号，值是按连号顺序各门的学分，总和必须等于工作簿整组学分。
   * 注意：这不是「总分÷门数」的推导规则，微积分(1-3) 按 6+6+4 拆是用户明确纠正的例外。
   * 表外的连号课程仍记为学分未知（null），并记 CREDITS_UNSPLIT，不要自行推算。
   */
  static final Map<String, List<BigDecimal>> CONFIRMED_RANGE_CREDITS =
      Map.ofEntries(
          Map.entry("01014125~127", List.of(bd("6"), bd("6"), bd("4"))),
          Map.entry("01034117~118", List.of(bd("4"), bd("4"))),
          Map.entry("08305009~010", List.of(bd("4"), bd("4"))),
          Map.entry("08305011~012", List.of(bd("4"), bd("4"))),
          Map.entry("08305140~141", List.of(bd("3"), bd("3"))),
          Map.entry("08305073~074", List.of(bd("3"), bd("3"))),
          Map.entry("0869A002~003", List.of(bd("2"), bd("2"))),
          Map.entry("08A6A001~002", List.of(bd("2"), bd("2"))),
          Map.entry("08B2A002~003", List.of(bd("2"), bd("2"))),
          Map.entry("0830A030~031", List.of(bd("2"), bd("2"))),
          Map.entry("01034120~121", List.of(bd("1"), bd("1"))),
          Map.entry("08305075~076", List.of(bd("1"), bd("1"))));

  private static BigDecimal bd(String value) {
    return new BigDecimal(value);
  }

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
    List<UnmodeledRule> unmodeled = new ArrayList<>();
    try (XSSFWorkbook workbook = new XSSFWorkbook(new ByteArrayInputStream(bytes))) {
      var sheet = workbook.getSheet(trackSheet);
      if (sheet == null
          || !cellText(sheet.getRow(0), 0).startsWith("CoursePilot｜2024级培养计划课程清单｜" + trackSheet)) {
        issues.add(new ImportIssue(TEMPLATE_MISMATCH, trackSheet, 1, 1));
      } else {
        readSelectedSheet(sheet, trackSheet, hash, requirements, entries, issues, unmodeled);
      }
    } catch (IOException | POIXMLException e) {
      issues.add(new ImportIssue(INVALID_OOXML, trackSheet, 1, 1));
    }
    String naturalKey = normalizedKey(trackId, requirements, entries, issues, unmodeled);
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
        List.copyOf(issues),
        List.copyOf(unmodeled));
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
      List<ImportIssue> issues,
      List<UnmodeledRule> unmodeled) {
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
                source(hash, trackId(track), track, r, 2, text(row, 4, formatter), 0)));
      }
    }
    if (statedTotal == null || statedTotal.compareTo(categoryTotal) != 0) {
      issues.add(new ImportIssue(TOTAL_MISMATCH, track, requirementHeader + 1, 3));
    }

    Map<String, CurriculumEntry> byCode = new HashMap<>();
    // 占位课程号下的去重键：编号+名称+建议学期。占位编号不全局唯一，只拦截完全相同的行。
    Set<String> placeholderKeys = new HashSet<>();
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
      if (name.isBlank() || category.isBlank() || kind.isBlank()) {
        issues.add(new ImportIssue(INVALID_ROW, track, r + 1, 2));
        continue;
      }
      if (credits == null) {
        issues.add(new ImportIssue(INVALID_CREDITS, track, r + 1, 5));
        continue;
      }
      if (kind.startsWith("课程组/要求行")) {
        // 课程组要求行（如“通识课课程组”）不是单门课程；其类别学分已在类别要求表中，
        // 这里不入库，只记录下来，不丢任何单门必修课。
        issues.add(new ImportIssue(GROUP_REQUIREMENT_ROW, track, r + 1, 3));
        continue;
      }
      if (!"课程明细".equals(kind)) {
        // Java currently stores only concrete courses, not choice groups or rule expressions.
        // Refuse to publish those rows until a typed persistence model exists.
        issues.add(new ImportIssue(UNSUPPORTED_ENTRY, track, r + 1, 3));
        continue;
      }
      if (name.length() > 200 || category.length() > 100) {
        issues.add(new ImportIssue(INVALID_ROW, track, r + 1, 2));
        continue;
      }
      // 连号课程号（如 01014125~127）按工作簿原文展开；展开失败视为非法课程号，阻断。
      boolean range = code.contains("~");
      List<String> codes = range ? expandRange(code) : List.of(code);
      if (codes == null) {
        issues.add(new ImportIssue(INVALID_COURSE_CODE, track, r + 1, 3));
        continue;
      }
      // 连号课程组：工作簿只给整组学分。已确认的拆分表逐门拆；表外的记为未知（null）。
      List<BigDecimal> confirmed = range ? CONFIRMED_RANGE_CREDITS.get(code) : null;
      if (range) {
        issues.add(new ImportIssue(COURSE_CODE_RANGE_EXPANDED, track, r + 1, 3));
        if (confirmed == null) {
          issues.add(new ImportIssue(CREDITS_UNSPLIT, track, r + 1, 5));
        } else if (confirmed.size() != codes.size()
            || confirmed.stream().reduce(BigDecimal.ZERO, BigDecimal::add).compareTo(credits) != 0) {
          // 已确认的拆分与工作簿整组学分或门数对不上，视为结构冲突，阻断。
          issues.add(new ImportIssue(INVALID_CREDITS, track, r + 1, 5));
          continue;
        }
      }
      for (int m = 0; m < codes.size(); m++) {
        String memberCode = codes.get(m);
        if (!COURSE_CODE.matcher(memberCode).matches()) {
          issues.add(new ImportIssue(INVALID_COURSE_CODE, track, r + 1, 3));
          continue;
        }
        // The persisted Course primary key is narrower than the public DTO contract.
        if (memberCode.length() > 32) {
          issues.add(new ImportIssue(COURSE_CODE_TOO_LONG, track, r + 1, 3));
          continue;
        }
        BigDecimal memberCredits = range ? (confirmed == null ? null : confirmed.get(m)) : credits;
        CurriculumEntry entry =
            new CurriculumEntry(
                name,
                memberCode,
                category,
                memberCredits,
                term,
                kind,
                source(hash, trackId(track), track, r, 1, text(row, 6, formatter), m));
        if (isPlaceholder(memberCode)) {
          // 占位编号（如 008532xx）：工作簿说明编号待确认，这里保留每门课，只记录待确认。
          issues.add(new ImportIssue(COURSE_CODE_PENDING, track, r + 1, 3));
          if (!placeholderKeys.add(memberCode + "\n" + name + "\n" + term)) {
            issues.add(new ImportIssue(DUPLICATE_COURSE, track, r + 1, 3));
          }
        } else {
          CurriculumEntry previous = byCode.putIfAbsent(memberCode, entry);
          if (previous != null) {
            boolean conflicting =
                !previous.name().equals(name)
                    || !sameCredits(previous.credits(), memberCredits)
                    || !previous.category().equals(category)
                    || !previous.suggestedTerm().equals(term);
            issues.add(
                new ImportIssue(
                    conflicting ? DUPLICATE_COURSE_CONFLICT : DUPLICATE_COURSE, track, r + 1, 3));
          }
        }
        entries.add(entry);
      }
    }

    // 「三、备注」区段：表头之后的每一行都是独立的规则/待核问题记录，不是课程数据。
    // 按表头位置而不是行号识别，并保留原文，不会因为行号不同而漏掉。
    for (int r = ruleHeader + 1; r <= sheet.getLastRowNum(); r++) {
      Row row = sheet.getRow(r);
      if (isEmpty(row, 2)) continue;
      if (!track.equals(text(row, 0, formatter))) continue;
      String sourceType = text(row, 5, formatter);
      // 原表课程行（如 Java EE 开发技术）已由负责人要求从有效清单删除，按排除记录。
      boolean excluded = "原表课程行".equals(sourceType);
      unmodeled.add(
          new UnmodeledRule(
              track,
              r + 1,
              text(row, 1, formatter),
              text(row, 2, formatter),
              text(row, 3, formatter),
              text(row, 4, formatter),
              sourceType,
              excluded
                  ? UnmodeledRule.Disposition.EXCLUDED
                  : UnmodeledRule.Disposition.UNMODELED));
      if (!excluded) {
        issues.add(new ImportIssue(UNKNOWN_RULE, track, r + 1, 3));
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

  /**
   * memberIndex 区分同一工作簿行展开出来的多门课：第 0 门保持原 refId，之后追加 :mN，
   * 保证 SourceReference 主键唯一。
   */
  private SourceRef source(
      String hash,
      String trackId,
      String sheet,
      int zeroBasedRow,
      int zeroBasedColumn,
      String originalLocator,
      int memberIndex) {
    int row = zeroBasedRow + 1;
    int column = zeroBasedColumn + 1;
    String suffix = memberIndex == 0 ? "" : ":m" + (memberIndex + 1);
    return new SourceRef(
        hash + ":" + trackId + ":" + row + ":" + column + suffix,
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

  /**
   * 把 "01014125~127" 展开为 01014125、01014126、01014127。
   * 写法：~ 左边是完整课程号，右边是末尾同宽的数字，表示连号的终点。
   * 不是合法连号（右边过宽、终点小于起点、跨度超过 10 门）时返回 null。
   */
  static List<String> expandRange(String raw) {
    int tilde = raw.indexOf('~');
    if (tilde < 1) return null;
    String start = raw.substring(0, tilde);
    String endSuffix = raw.substring(tilde + 1);
    if (!endSuffix.matches("[0-9]{1,3}") || start.length() < endSuffix.length()) return null;
    int width = endSuffix.length();
    String head = start.substring(0, start.length() - width);
    String tail = start.substring(start.length() - width);
    if (!tail.matches("[0-9]+")) return null;
    int from = Integer.parseInt(tail);
    int to = Integer.parseInt(endSuffix);
    if (to < from || to - from > 9) return null;
    List<String> codes = new ArrayList<>();
    for (int n = from; n <= to; n++) {
      codes.add(head + String.format(java.util.Locale.ROOT, "%0" + width + "d", n));
    }
    return codes;
  }

  /** 工作簿用 x 代表待确认的数字，例如 008532xx、00304xxx。 */
  static boolean isPlaceholder(String code) {
    return code.matches("[0-9]+[xX]+");
  }

  private static boolean sameCredits(BigDecimal a, BigDecimal b) {
    return a == null ? b == null : b != null && a.compareTo(b) == 0;
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
      List<ImportIssue> issues,
      List<UnmodeledRule> unmodeled) {
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
      append(canonical, entry.credits() == null ? "" : entry.credits().toPlainString());
      append(canonical, entry.suggestedTerm());
      append(canonical, entry.recordKind());
      append(canonical, entry.source().originalLocator());
    }
    for (UnmodeledRule rule : unmodeled) {
      append(canonical, "rule");
      append(canonical, rule.sourceLocator());
      append(canonical, rule.subject());
      append(canonical, rule.originalNote());
      append(canonical, rule.currentStatus());
      append(canonical, rule.sourceType());
      append(canonical, rule.disposition().name());
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
