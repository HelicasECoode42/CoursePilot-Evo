package com.coursepilot.verifier.application;

import com.coursepilot.verifier.persistence.entity.CourseOffering;
import com.coursepilot.verifier.persistence.entity.CurriculumSnapshot;
import com.coursepilot.verifier.persistence.repo.CourseOfferingRepository;
import com.coursepilot.verifier.persistence.repo.CourseRepository;
import com.coursepilot.verifier.persistence.repo.CurriculumSnapshotRepository;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 开课快照导入（契约 importOfferings，OfferingImport schema）。
 *
 * 三条硬规则（AGENTS.md）：
 * 1. 时间只由唯一的 TimeParser 从 meetingTextRaw 重新解析；客户端的 meetings 只做结构校验，
 *    不入库；客户端的 parseStatus 只用来比对并给出提示，不采信。
 * 2. sourceValidation 由 Java 决定：SYNTHETIC 来源为 SYNTHETIC，其余一律 UNVERIFIED。
 *    上传者声称什么都不影响它，也不会自动变成 VERIFIED。
 * 3. 解析不出的时间保留为 UNPARSED，不丢班次；读取与计划核验都把它当未知。
 *
 * 幂等：快照 id 由规范化内容的 SHA-256 派生（OFS_ + 60 位十六进制），同内容重复导入
 * 直接返回已有快照（reused=true），不重复写入。meetings 与 parseStatus 不参与摘要。
 */
@Service
public class OfferingImportService {

    public static final int MAX_OFFERINGS = 2000;
    public static final int MAX_MEETINGS = 40;
    private static final String SNAPSHOT_PREFIX = "OFS_";
    private static final Pattern ID = Pattern.compile("^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$");

    private static final Set<String> TOP_FIELDS =
        Set.of("schemaVersion", "termId", "sourceKind", "capturedAt", "calendar", "offerings");
    private static final Set<String> CALENDAR_FIELDS = Set.of("weeks", "sectionsPerDay");
    private static final Set<String> OFFERING_FIELDS = Set.of("courseCode", "classId", "teacherKey",
        "teacherText", "credits", "capacity", "meetingTextRaw", "meetings", "parseStatus", "sourceRefId");
    private static final Set<String> MEETING_FIELDS = Set.of("dayOfWeek", "sectionStart", "sectionEnd", "weeks");
    private static final Set<String> SOURCE_KINDS = Set.of("BROWSER_SNAPSHOT", "SYNTHETIC");
    private static final Set<String> PARSE_STATUSES = Set.of("PARSED", "UNPARSED", "INVALID");

    private final CourseOfferingRepository offerings;
    private final CurriculumSnapshotRepository snapshots;
    private final CourseRepository courses;
    private final TimeParser timeParser;
    private final ObjectMapper mapper = new ObjectMapper();

    public OfferingImportService(CourseOfferingRepository offerings, CurriculumSnapshotRepository snapshots,
                                 CourseRepository courses, TimeParser timeParser) {
        this.offerings = offerings;
        this.snapshots = snapshots;
        this.courses = courses;
        this.timeParser = timeParser;
    }

    // ------------------------------------------------------------------ 结构校验

    /** 结构与契约校验；不通过抛 OfferingImportRejected，不写库。 */
    public Draft parse(JsonNode body) {
        if (body == null || !body.isObject()) throw schema("body", "请求体必须是对象");
        exactFields(body, TOP_FIELDS, "body");
        JsonNode schemaVersion = body.get("schemaVersion");
        if (schemaVersion == null || !schemaVersion.isTextual() || !"1.0".equals(schemaVersion.asText())) {
            throw schema("schemaVersion", "schemaVersion 必须为 1.0");
        }
        String termId = id(body, "termId", "termId");
        String sourceKind = text(body, "sourceKind", "sourceKind");
        if (!SOURCE_KINDS.contains(sourceKind)) throw schema("sourceKind", "sourceKind 不在允许的取值内");
        Instant capturedAt = instant(body, "capturedAt");

        JsonNode calendar = body.get("calendar");
        if (calendar == null || !calendar.isObject()) throw schema("calendar", "calendar 必须是对象");
        exactFields(calendar, CALENDAR_FIELDS, "calendar");
        int weeks = intIn(calendar.get("weeks"), 1, 60, "calendar.weeks");
        int sectionsPerDay = intIn(calendar.get("sectionsPerDay"), 1, 64, "calendar.sectionsPerDay");

        JsonNode list = body.get("offerings");
        if (list == null || !list.isArray() || list.size() < 1 || list.size() > MAX_OFFERINGS) {
            throw schema("offerings", "offerings 必须是 1 到 " + MAX_OFFERINGS + " 条的数组");
        }
        List<Row> rows = new ArrayList<>();
        Set<String> classIds = new HashSet<>();
        for (int i = 0; i < list.size(); i++) {
            Row row = parseRow(list.get(i), "offerings[" + i + "]");
            if (!classIds.add(row.classId())) {
                throw new OfferingImportRejected(OfferingImportRejected.Kind.SEMANTIC, "DUPLICATE_CLASS_ID",
                    "同一次导入中班次编号重复", "offerings[" + i + "].classId");
            }
            rows.add(row);
        }
        return new Draft(termId, sourceKind, capturedAt, weeks, sectionsPerDay, rows, digest(termId, sourceKind,
            capturedAt, weeks, sectionsPerDay, rows));
    }

    private Row parseRow(JsonNode n, String at) {
        if (n == null || !n.isObject()) throw schema(at, "班次必须是对象");
        exactFields(n, OFFERING_FIELDS, at);
        String courseCode = id(n, "courseCode", at + ".courseCode");
        String classId = id(n, "classId", at + ".classId");
        String teacherKey = nullableId(n, "teacherKey", at + ".teacherKey");
        String teacherText = text(n, "teacherText", at + ".teacherText");
        if (teacherText.isEmpty() || teacherText.length() > 200) throw schema(at + ".teacherText", "teacherText 长度须在 1 到 200 之间");
        Double credits = credits(n.get("credits"), at + ".credits");
        Integer capacity = capacity(n.get("capacity"), at + ".capacity");
        String meetingTextRaw = text(n, "meetingTextRaw", at + ".meetingTextRaw");
        if (meetingTextRaw.length() > 1000) throw schema(at + ".meetingTextRaw", "meetingTextRaw 超过 1000 字符");
        validateMeetingsShape(n.get("meetings"), at + ".meetings");
        String claimed = text(n, "parseStatus", at + ".parseStatus");
        if (!PARSE_STATUSES.contains(claimed)) throw schema(at + ".parseStatus", "parseStatus 不在允许的取值内");
        String sourceRefId = id(n, "sourceRefId", at + ".sourceRefId");
        return new Row(courseCode, classId, teacherKey, teacherText, credits, capacity, meetingTextRaw,
            claimed, sourceRefId);
    }

    /** meetings 只校验形状，内容不入库：时间以 meetingTextRaw 为准。 */
    private static void validateMeetingsShape(JsonNode meetings, String at) {
        if (meetings == null || !meetings.isArray() || meetings.size() > MAX_MEETINGS) {
            throw schema(at, "meetings 必须是最多 " + MAX_MEETINGS + " 段的数组");
        }
        for (int i = 0; i < meetings.size(); i++) {
            JsonNode m = meetings.get(i);
            String mAt = at + "[" + i + "]";
            if (m == null || !m.isObject()) throw schema(mAt, "meeting 必须是对象");
            exactFields(m, MEETING_FIELDS, mAt);
            intIn(m.get("dayOfWeek"), 1, 7, mAt + ".dayOfWeek");
            intIn(m.get("sectionStart"), 1, 64, mAt + ".sectionStart");
            intIn(m.get("sectionEnd"), 1, 64, mAt + ".sectionEnd");
            JsonNode weeks = m.get("weeks");
            if (weeks == null || !weeks.isArray() || weeks.size() < 1 || weeks.size() > 60) {
                throw schema(mAt + ".weeks", "weeks 必须是 1 到 60 个元素的数组");
            }
            Set<Integer> seen = new HashSet<>();
            for (int w = 0; w < weeks.size(); w++) {
                int week = intIn(weeks.get(w), 1, 60, mAt + ".weeks[" + w + "]");
                if (!seen.add(week)) throw schema(mAt + ".weeks", "weeks 不得重复");
            }
        }
    }

    // ------------------------------------------------------------------ 发布

    /**
     * 写入开课快照与班次。同内容重复导入返回已有快照（reused=true）。
     * 班次编号即计划项引用的 classId，全库唯一：编号已属于另一快照时整次拒绝（409），不静默覆盖。
     */
    @Transactional
    public Result publish(Draft draft) {
        List<Parsed> parsed = draft.rows().stream().map(r -> new Parsed(r, parseStatus(r.meetingTextRaw()))).toList();
        List<Issue> issues = new ArrayList<>();

        long unparsed = parsed.stream().filter(p -> !"PARSED".equals(p.status())).count();
        if (unparsed > 0) {
            issues.add(new Issue("MEETING_TEXT_UNPARSED",
                unparsed + " 个班次的时间文本无法解析或超出契约上限，已记为未知", "offerings"));
        }
        long overridden = parsed.stream().filter(p -> !p.status().equals(p.row().claimedParseStatus())).count();
        if (overridden > 0) {
            issues.add(new Issue("CLIENT_PARSE_STATUS_IGNORED",
                overridden + " 个班次的客户端 parseStatus 与 Java 重新解析结果不一致，已采用 Java 结果", "offerings"));
        }
        Set<String> courseCodes = draft.rows().stream().map(Row::courseCode).collect(Collectors.toCollection(LinkedHashSet::new));
        Set<String> known = courses.findAllById(courseCodes).stream()
            .map(c -> c.getCourseCode()).collect(Collectors.toSet());
        long unknownCourses = courseCodes.stream().filter(c -> !known.contains(c)).count();
        if (unknownCourses > 0) {
            // 合同未规定课程号必须已在目录中，所以接受并提示，不替调用方拒绝。
            issues.add(new Issue("COURSE_NOT_IN_CATALOG",
                unknownCourses + " 个课程号不在课程目录中，班次仍已导入，计划核验时仍需课程与班次对应", "courseCode"));
        }

        String snapshotId = SNAPSHOT_PREFIX + draft.digest().substring(0, 60);
        var existing = snapshots.findById(snapshotId);
        if (existing.isPresent()) {
            if (existing.get().getKind() != CurriculumSnapshot.Kind.OFFERING) {
                throw new OfferingImportRejected(OfferingImportRejected.Kind.CONFLICT, "SNAPSHOT_ID_CONFLICT",
                    "快照标识已被其他快照占用", null);
            }
            return new Result(snapshotId, true, issues);
        }

        List<String> classIds = draft.rows().stream().map(Row::classId).toList();
        Map<String, CourseOffering> clashes = offerings.findAllById(classIds).stream()
            .collect(Collectors.toMap(CourseOffering::getOfferingId, Function.identity()));
        if (!clashes.isEmpty()) {
            String first = clashes.keySet().iterator().next();
            throw new OfferingImportRejected(OfferingImportRejected.Kind.CONFLICT, "CLASS_ID_CONFLICT",
                "班次编号已属于其他快照或既有数据（如 " + first + "），整次导入已拒绝", "offerings");
        }

        CurriculumSnapshot.SourceKind kind = CurriculumSnapshot.SourceKind.valueOf(draft.sourceKind());
        // 只有 SYNTHETIC 来源才是 SYNTHETIC；其余一律 UNVERIFIED，不接受上传者声明的核验结论。
        CurriculumSnapshot.SourceValidation validation = kind == CurriculumSnapshot.SourceKind.SYNTHETIC
            ? CurriculumSnapshot.SourceValidation.SYNTHETIC : CurriculumSnapshot.SourceValidation.UNVERIFIED;
        CurriculumSnapshot snapshot = new CurriculumSnapshot(snapshotId, CurriculumSnapshot.Kind.OFFERING,
            CurriculumSnapshot.State.PUBLISHED, kind, validation, draft.termId(), Instant.now());
        snapshot.recordOfferingFacts(draft.capturedAt(), draft.weeks(), draft.sectionsPerDay());
        snapshots.save(snapshot);

        offerings.saveAll(parsed.stream().map(p -> new CourseOffering(
            p.row().classId(), p.row().courseCode(), p.row().teacherText(), p.row().meetingTextRaw(),
            draft.sourceKind(), snapshotId, p.status(), p.row().teacherKey(), p.row().sourceRefId(),
            p.row().credits(), p.row().capacity())).toList());

        return new Result(snapshotId, false, issues);
    }

    /** 与 CatalogAssembler 同一判定：超契约上限 INVALID，解析不出 UNPARSED，其余 PARSED。 */
    private String parseStatus(String raw) {
        TimeParser.ParseOutcome outcome = timeParser.parse(raw == null ? "" : raw);
        if (outcome.isOutOfContract()) return "INVALID";
        return outcome.isOk() ? "PARSED" : "UNPARSED";
    }

    private String digest(String termId, String sourceKind, Instant capturedAt, int weeks, int sectionsPerDay,
                          List<Row> rows) {
        List<List<Object>> canonical = new ArrayList<>();
        canonical.add(List.of("v1", termId, sourceKind, capturedAt.toString(), weeks, sectionsPerDay));
        rows.stream().sorted((a, b) -> a.classId().compareTo(b.classId())).forEach(r -> canonical.add(List.of(
            r.classId(), r.courseCode(), String.valueOf(r.teacherKey()), r.teacherText(),
            String.valueOf(r.credits()), String.valueOf(r.capacity()), r.meetingTextRaw(), r.sourceRefId())));
        try {
            byte[] bytes = mapper.writeValueAsString(canonical).getBytes(StandardCharsets.UTF_8);
            return hex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (Exception ex) {
            throw new IllegalStateException("开课快照摘要计算失败", ex);
        }
    }

    private static String hex(byte[] bytes) {
        StringBuilder sb = new StringBuilder();
        for (byte b : bytes) sb.append(String.format("%02x", b));
        return sb.toString();
    }

    // ------------------------------------------------------------------ 小工具

    private static void exactFields(JsonNode node, Set<String> allowed, String at) {
        var names = node.fieldNames();
        while (names.hasNext()) {
            String name = names.next();
            if (!allowed.contains(name)) throw schema(at + "." + name, "包含契约未声明的字段");
        }
        for (String required : allowed) {
            if (!node.has(required)) throw schema(at + "." + required, "缺少必填字段");
        }
    }

    private static String text(JsonNode node, String field, String at) {
        JsonNode v = node.get(field);
        if (v == null || !v.isTextual()) throw schema(at, "必须是字符串");
        return v.asText();
    }

    private static String id(JsonNode node, String field, String at) {
        String v = text(node, field, at);
        if (!ID.matcher(v).matches()) throw schema(at, "格式不合法");
        return v;
    }

    private static String nullableId(JsonNode node, String field, String at) {
        JsonNode v = node.get(field);
        if (v == null) throw schema(at, "缺少必填字段");
        if (v.isNull()) return null;
        if (!v.isTextual() || !ID.matcher(v.asText()).matches()) throw schema(at, "格式不合法");
        return v.asText();
    }

    private static Instant instant(JsonNode node, String field) {
        String v = text(node, field, field);
        try {
            return OffsetDateTime.parse(v).toInstant();
        } catch (DateTimeParseException ex) {
            throw schema(field, "capturedAt 必须是带时区的 date-time");
        }
    }

    private static int intIn(JsonNode v, int min, int max, String at) {
        if (v == null || !v.isIntegralNumber() || !v.canConvertToInt() || v.asInt() < min || v.asInt() > max) {
            throw schema(at, "必须是 " + min + " 到 " + max + " 之间的整数");
        }
        return v.asInt();
    }

    /** credits：null 或 0..1000、精度到分的数。 */
    private static Double credits(JsonNode v, String at) {
        if (v == null) throw schema(at, "缺少必填字段");
        if (v.isNull()) return null;
        if (!v.isNumber()) throw schema(at, "必须是数字或 null");
        BigDecimal value = v.decimalValue();
        if (value.signum() < 0 || value.compareTo(BigDecimal.valueOf(1000)) > 0
            || value.movePointRight(2).stripTrailingZeros().scale() > 0) {
            throw schema(at, "学分须在 0 到 1000 之间且精确到 0.01");
        }
        return value.doubleValue();
    }

    private static Integer capacity(JsonNode v, String at) {
        if (v == null) throw schema(at, "缺少必填字段");
        if (v.isNull()) return null;
        return intIn(v, 0, 100000, at);
    }

    private static OfferingImportRejected schema(String field, String message) {
        return new OfferingImportRejected(OfferingImportRejected.Kind.SCHEMA, "INVALID_OFFERING_IMPORT", message, field);
    }

    // ------------------------------------------------------------------ 数据类型

    /** 通过结构校验后的导入内容。meetings 与客户端 parseStatus 不在其中。 */
    public record Draft(String termId, String sourceKind, Instant capturedAt, int weeks, int sectionsPerDay,
                        List<Row> rows, String digest) {}

    public record Row(String courseCode, String classId, String teacherKey, String teacherText, Double credits,
                      Integer capacity, String meetingTextRaw, String claimedParseStatus, String sourceRefId) {}

    private record Parsed(Row row, String status) {}

    public record Issue(String code, String message, String field) {}

    public record Result(String snapshotId, boolean reused, List<Issue> issues) {}

    /** 拒绝导入。Kind 决定 HTTP 状态：SCHEMA=400，SEMANTIC=422，CONFLICT=409。 */
    public static final class OfferingImportRejected extends RuntimeException {
        public enum Kind { SCHEMA, SEMANTIC, CONFLICT }

        private final Kind kind;
        private final String code;
        private final String field;

        public OfferingImportRejected(Kind kind, String code, String message, String field) {
            super(message);
            this.kind = kind;
            this.code = code;
            this.field = field;
        }

        public Kind kind() { return kind; }
        public String code() { return code; }
        public String field() { return field; }
    }
}
