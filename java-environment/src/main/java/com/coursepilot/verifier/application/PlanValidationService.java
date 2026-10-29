package com.coursepilot.verifier.application;

import com.coursepilot.verifier.domain.MeetingTime;
import com.coursepilot.verifier.persistence.entity.CourseOffering;
import com.coursepilot.verifier.persistence.entity.CurriculumSnapshot;
import com.coursepilot.verifier.persistence.entity.CurriculumCourse;
import com.coursepilot.verifier.persistence.entity.CurriculumUnmodeledRule;
import com.coursepilot.verifier.persistence.repo.CurriculumUnmodeledRuleRepository;
import com.coursepilot.verifier.persistence.entity.Transcript;
import com.coursepilot.verifier.persistence.repo.CurriculumCourseRepository;
import com.coursepilot.verifier.persistence.repo.CurriculumSnapshotRepository;
import com.coursepilot.verifier.persistence.repo.TranscriptRepository;
import com.coursepilot.verifier.web.AccessDenied;
import com.coursepilot.verifier.web.InvalidRecordInput;
import com.coursepilot.verifier.web.SubjectGuard;
import com.coursepilot.verifier.web.SnapshotMismatch;
import com.coursepilot.verifier.web.UnknownSnapshot;
import com.coursepilot.verifier.web.dto.AuditDtos.Issue;
import com.coursepilot.verifier.web.dto.PlanDtos.Constraint;
import com.coursepilot.verifier.web.dto.PlanDtos.PlanItem;
import com.coursepilot.verifier.web.dto.PlanDtos.PlanValidation;
import com.coursepilot.verifier.web.dto.PlanDtos.PlanValidationRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.regex.Pattern;
import java.util.function.Function;
import java.util.stream.Collectors;

/**
 * 方案核验（POST /api/v1/plans/validate）。
 *
 * 判决（docs/trd/b-verifier.md）：存在已知 violation → INVALID；否则只要有 hard check 无法执行 → UNKNOWN；
 * 全部完成且无 violation → VALID。未知永远不能被当成通过。
 *
 * 范围（docs/04）：只有 mode=SIMULATION、offeringSnapshotId 非空、且每个班次都存在且 sourceKind=SYNTHETIC
 * 才是 SIMULATION；其余一律 COURSE_ONLY。REAL_TIMETABLE 目前没有任何已验证来源，本类永远不产出它。
 * COURSE_ONLY / 非 SIMULATION 下，所有时间相关检查（冲突、时间类硬约束）都记进 unknownChecks。
 *
 * 时间只经 ConflictChecker.analyze（唯一 TimeParser）得到，本类不解析客户端给的任何时间文本。
 */
@Service
public class PlanValidationService {

    static final int MAX_ITEMS = 30;
    static final int MAX_CONSTRAINTS = 30;
    /** 契约 violations / unknownChecks 的 maxItems。 */
    static final int MAX_ISSUES = 200;
    /** 契约 performedChecks 的 maxItems。 */
    static final int MAX_PERFORMED = 40;

    private static final Pattern ID = Pattern.compile("^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$");
    private static final int MAX_SOURCE_TEXT = 500;
    private static final int MAX_MESSAGE = 500;
    private static final List<String> DAY_NAMES = List.of("", "周一", "周二", "周三", "周四", "周五", "周六", "周日");

    private static final String BLOCK_DAY = "BLOCK_DAY";
    private static final String BLOCK_SECTION = "BLOCK_SECTION";
    private static final String BLOCK_SLOT = "BLOCK_SLOT";
    private static final String PIN_TEACHER_COURSE = "PIN_TEACHER_COURSE";
    private static final String PIN_COURSE = "PIN_COURSE";
    private static final String MAX_CREDITS = "MAX_CREDITS";

    private final SubjectGuard subjects;
    private final TranscriptRepository transcripts;
    private final CurriculumSnapshotRepository snapshots;
    private final CurriculumCourseRepository curriculumCourses;
    private final ConflictChecker conflictChecker;
    private final CurriculumUnmodeledRuleRepository unmodeledRules;

    public PlanValidationService(SubjectGuard subjects,
                                 TranscriptRepository transcripts,
                                 CurriculumSnapshotRepository snapshots,
                                 CurriculumCourseRepository curriculumCourses,
                                 ConflictChecker conflictChecker,
                                 CurriculumUnmodeledRuleRepository unmodeledRules) {
        this.unmodeledRules = unmodeledRules;
        this.subjects = subjects;
        this.transcripts = transcripts;
        this.snapshots = snapshots;
        this.curriculumCourses = curriculumCourses;
        this.conflictChecker = conflictChecker;
    }

    @Transactional(readOnly = true)
    public PlanValidation validate(String subjectId, PlanValidationRequest req) {
        validateShape(req);
        // 先定归属：别人的学业记录按不存在处理（404），与 AcademicRecordController 一致。
        subjects.requireOwnRecord(subjectId, req.academicRecordId());
        Transcript transcript = transcripts.findByStudentId(req.academicRecordId())
            .orElseThrow(() -> new AccessDenied("学业记录 " + req.academicRecordId() + " 不存在"));
        if (!snapshots.existsById(req.curriculumSnapshotId())) {
            throw new UnknownSnapshot(req.curriculumSnapshotId());
        }
        if (!req.curriculumSnapshotId().equals(transcript.getCurriculumSnapshotId())) {
            throw new SnapshotMismatch(transcript.getCurriculumSnapshotId(), req.curriculumSnapshotId());
        }
        if (req.offeringSnapshotId() != null) {
            CurriculumSnapshot offering = snapshots.findById(req.offeringSnapshotId())
                .orElseThrow(() -> new UnknownSnapshot(req.offeringSnapshotId()));
            if (offering.getKind() != CurriculumSnapshot.Kind.OFFERING) {
                throw new UnknownSnapshot(req.offeringSnapshotId());
            }
        }

        List<PlanItem> items = req.items();
        List<String> classIds = items.stream().map(PlanItem::classId).filter(Objects::nonNull)
            .distinct().toList();
        ConflictChecker.Analysis analysis = conflictChecker.analyze(classIds);
        Map<String, CourseOffering> offerings = analysis.offeringsById();
        // 占位编号（如 008532xx）可能对应同一快照下的多门课：编号不唯一就无法据此定位，排除后按未知处理。
        Map<String, CurriculumCourse> catalog = curriculumCourses
            .findBySnapshot_SnapshotIdAndCourse_CourseCodeIn(req.curriculumSnapshotId(),
                items.stream().map(PlanItem::courseCode).distinct().toList())
            .stream().collect(Collectors.groupingBy(cc -> cc.getCourse().getCourseCode()))
            .values().stream().filter(group -> group.size() == 1).map(group -> group.getFirst())
            .collect(Collectors.toMap(cc -> cc.getCourse().getCourseCode(), Function.identity()));

        // 只有模拟模式、带快照、且每个方案项都落到一个存在的 SYNTHETIC 班次，才是 SIMULATION。
        boolean simulation = "SIMULATION".equals(req.mode())
            && req.offeringSnapshotId() != null
            && items.stream().allMatch(i -> i.classId() != null
                && offerings.containsKey(i.classId())
                && "SYNTHETIC".equals(offerings.get(i.classId()).getSourceKind()));
        String scope = simulation ? "SIMULATION" : "COURSE_ONLY";

        Findings f = new Findings();
        // 未建模规则不参与核验，但必须显式带出：快照里有几条未建模规则，就带出一条说明。
        var unmodeled = unmodeledRules.findBySnapshot_SnapshotIdAndDispositionOrderBySourceRowAsc(
            req.curriculumSnapshotId(), CurriculumUnmodeledRule.Disposition.UNMODELED);
        if (!unmodeled.isEmpty()) {
            f.unknown(UnmodeledRuleNotice.CODE, UnmodeledRuleNotice.message(unmodeled),
                "curriculumSnapshotId");
        }
        checkClassAssignments(items, offerings, f);
        checkTime(items, classIds, analysis, simulation, f);
        for (int i = 0; i < req.hardConstraints().size(); i++) {
            Constraint c = req.hardConstraints().get(i);
            switch (c.kind()) {
                case BLOCK_DAY, BLOCK_SECTION, BLOCK_SLOT ->
                    checkTimeConstraint(i, c, items, simulation, analysis, f);
                case PIN_COURSE -> checkPinCourse(i, c, items, f);
                case PIN_TEACHER_COURSE -> checkPinTeacherCourse(i, c, items, f);
                case MAX_CREDITS -> checkMaxCredits(i, c, items, catalog, req.curriculumSnapshotId(), f);
                default -> throw new IllegalStateException("kind 已在 validateShape 中校验: " + c.kind());
            }
        }

        String verdict = !f.violations.isEmpty() ? "INVALID"
            : !f.unknowns.isEmpty() ? "UNKNOWN" : "VALID";

        List<String> refs = new ArrayList<>();
        refs.add("curriculum:" + req.curriculumSnapshotId());
        if (req.offeringSnapshotId() != null) {
            refs.add("offering-snapshot:" + req.offeringSnapshotId());
        }

        return new PlanValidation(
            "vr-" + UUID.randomUUID().toString().replace("-", ""),
            verdict,
            scope,
            req.curriculumSnapshotId(),
            req.offeringSnapshotId(),
            transcript.getRevision(),
            cap(f.violations),
            cap(f.unknowns),
            List.copyOf(f.performed.size() > MAX_PERFORMED
                ? f.performed.subList(0, MAX_PERFORMED) : f.performed),
            List.copyOf(refs));
    }

    /** 班次存在性与班次归属课程。 */
    private void checkClassAssignments(List<PlanItem> items, Map<String, CourseOffering> offerings, Findings f) {
        boolean any = false;
        for (int i = 0; i < items.size(); i++) {
            PlanItem item = items.get(i);
            if (item.classId() == null) continue;
            any = true;
            String field = "items[" + i + "].classId";
            CourseOffering offering = offerings.get(item.classId());
            if (offering == null) {
                f.unknown("CLASS_NOT_FOUND",
                    "班次 " + item.classId() + " 不存在，无法核验课程 " + item.courseCode() + " 的时间与归属", field);
            } else if (!item.courseCode().equals(offering.getCourseCode())) {
                f.violation("CLASS_COURSE_MISMATCH",
                    "班次 " + item.classId() + " 属于课程 " + offering.getCourseCode()
                        + "，不是方案中的课程 " + item.courseCode(), field);
            }
        }
        if (any) f.performed("班次与课程归属核对");
    }

    /**
     * 时间冲突。SIMULATION 下用 ConflictChecker 的明细判断，把相撞的两门课点名；
     * 其他范围下没有已验证班次，冲突未核验，记入 unknownChecks。
     */
    private void checkTime(List<PlanItem> items, List<String> classIds,
                           ConflictChecker.Analysis analysis, boolean simulation, Findings f) {
        if (!simulation) {
            f.unknown("TIMETABLE_UNVERIFIED",
                "没有已验证来源的班次（mode=REAL 或班次非 SYNTHETIC），时间冲突与时间类硬约束未核验，不能判为通过",
                null);
            return;
        }
        for (String id : classIds) {
            String reason = analysis.unparseableReasons().get(id);
            if (reason != null) {
                f.unknown("TIME_UNPARSEABLE",
                    "班次 " + id + "（课程 " + courseOf(analysis, id) + "）时间无法解析：" + reason,
                    "items");
            }
        }
        for (ConflictChecker.ConflictPair p : analysis.conflicts()) {
            f.violation("TIME_CONFLICT",
                "课程 " + courseOf(analysis, p.leftId()) + "（班次 " + p.leftId() + "）与课程 "
                    + courseOf(analysis, p.rightId()) + "（班次 " + p.rightId() + "）时间冲突",
                null);
        }
        f.performed("时间冲突核对（同星期、节次、周次相交）");
    }

    private void checkTimeConstraint(int i, Constraint c, List<PlanItem> items, boolean simulation,
                                     ConflictChecker.Analysis analysis, Findings f) {
        String field = "hardConstraints[" + i + "]";
        String label = "第 " + i + " 条硬约束（" + c.kind() + "）";
        if (!simulation) {
            f.unknown("CONSTRAINT_UNVERIFIABLE",
                label + "需要已验证的班次时间，当前没有可用来源，无法核验", field);
            return;
        }
        f.performed("硬约束 #" + i + " " + c.kind() + " 时间核对");
        for (PlanItem item : items) {
            Applicability ap = appliesTo(c, item);
            if (ap == Applicability.NO) continue;
            if (ap == Applicability.UNKNOWN) {
                f.unknown("CONSTRAINT_UNVERIFIABLE",
                    label + "无法确定课程 " + item.courseCode() + " 的教师是否受约束，方案项未给教师", field);
                continue;
            }
            if (item.classId() == null) {
                f.unknown("CONSTRAINT_UNVERIFIABLE",
                    label + "无法核验课程 " + item.courseCode() + "：方案项未指定班次", field);
                continue;
            }
            List<MeetingTime> meetings = analysis.meetingsById().get(item.classId());
            if (meetings == null) {
                f.unknown("CONSTRAINT_UNVERIFIABLE",
                    label + "无法核验课程 " + item.courseCode() + "：班次 " + item.classId() + " 时间不可用", field);
                continue;
            }
            for (MeetingTime m : meetings) {
                if (hits(c, m)) {
                    f.violation("CONSTRAINT_" + c.kind(),
                        "课程 " + item.courseCode() + "（班次 " + item.classId() + "）"
                            + DAY_NAMES.get(m.getDayOfWeek()) + "第" + m.getStartSection() + "-"
                            + m.getEndSection() + "节，命中" + label, field);
                    break;
                }
            }
        }
    }

    private void checkPinCourse(int i, Constraint c, List<PlanItem> items, Findings f) {
        String field = "hardConstraints[" + i + "]";
        boolean present = items.stream().anyMatch(it -> c.courseCode().equals(it.courseCode()));
        if (!present) {
            f.violation("PIN_COURSE_MISSING",
                "方案未包含必选课程 " + c.courseCode() + "（第 " + i + " 条硬约束）", field);
        }
        f.performed("硬约束 #" + i + " PIN_COURSE 核对");
    }

    private void checkPinTeacherCourse(int i, Constraint c, List<PlanItem> items, Findings f) {
        String field = "hardConstraints[" + i + "]";
        List<PlanItem> same = items.stream().filter(it -> c.courseCode().equals(it.courseCode())).toList();
        if (same.isEmpty()) {
            f.violation("PIN_COURSE_MISSING",
                "方案未包含必选课程 " + c.courseCode() + "（第 " + i + " 条硬约束，指定教师 " + c.teacherKey() + "）", field);
        } else if (same.stream().noneMatch(it -> c.teacherKey().equals(it.teacherKey()))) {
            if (same.stream().anyMatch(it -> it.teacherKey() == null)) {
                f.unknown("PIN_TEACHER_UNKNOWN",
                    "课程 " + c.courseCode() + " 的方案项未给教师，无法确认是否为第 " + i + " 条硬约束指定的教师", field);
            } else {
                f.violation("PIN_TEACHER_MISMATCH",
                    "课程 " + c.courseCode() + " 的方案教师与第 " + i + " 条硬约束要求的教师不符", field);
            }
        }
        f.performed("硬约束 #" + i + " PIN_TEACHER_COURSE 核对");
    }

    private void checkMaxCredits(int i, Constraint c, List<PlanItem> items,
                                 Map<String, CurriculumCourse> catalog, String snapshotId, Findings f) {
        String field = "hardConstraints[" + i + "]";
        if (c.courseCode() != null) {
            // 按课程限定的学分上限语义未在契约里定义，不擅自套用成全方案上限。
            f.unknown("CREDITS_SCOPE_UNSUPPORTED",
                "第 " + i + " 条硬约束按课程限定学分上限，本接口暂不核验", field);
            return;
        }
        BigDecimal total = BigDecimal.ZERO;
        for (String code : items.stream().map(PlanItem::courseCode).distinct().toList()) {
            CurriculumCourse membership = catalog.get(code);
            if (membership == null || !hasUsableFacts(membership, snapshotId)) {
                f.unknown("COURSE_FACTS_UNKNOWN",
                    "课程 " + code + " 在培养快照 " + snapshotId
                        + " 中缺少可追溯的快照级属性或来源，无法核验第 " + i + " 条学分上限", field);
            } else if (membership.getCredits() == null) {
                f.unknown("CREDITS_UNKNOWN",
                    "课程 " + code + " 在培养快照 " + snapshotId + " 中学分未知，无法计入第 "
                        + i + " 条学分上限", field);
            } else {
                total = total.add(BigDecimal.valueOf(membership.getCredits()));
            }
        }
        BigDecimal limit = BigDecimal.valueOf(c.value());
        // 已知学分合计已超上限时结论确定，即使还有未知课程。
        if (total.compareTo(limit) > 0) {
            f.violation("MAX_CREDITS_EXCEEDED",
                "已知课程学分合计 " + total.stripTrailingZeros().toPlainString() + " 超过第 " + i
                    + " 条硬约束的上限 " + limit.stripTrailingZeros().toPlainString(), field);
        }
        f.performed("硬约束 #" + i + " MAX_CREDITS 学分合计核对");
    }

    private static boolean hasUsableFacts(CurriculumCourse cc, String snapshotId) {
        var source = cc.getSourceReference();
        return cc.getName() != null && !cc.getName().isBlank()
            && cc.getCategory() != null && !cc.getCategory().isBlank()
            && source != null && source.getRefId() != null && !source.getRefId().isBlank()
            && snapshotId.equals(source.getSnapshotId())
            && source.getLocator() != null && !source.getLocator().isBlank()
            && ("CURRICULUM".equals(source.getKind()) || "SYNTHETIC".equals(source.getKind()));
    }

    private enum Applicability { YES, NO, UNKNOWN }

    private static Applicability appliesTo(Constraint c, PlanItem item) {
        if (c.courseCode() != null && !c.courseCode().equals(item.courseCode())) return Applicability.NO;
        if (c.teacherKey() == null) return Applicability.YES;
        if (item.teacherKey() == null) return Applicability.UNKNOWN;
        return c.teacherKey().equals(item.teacherKey()) ? Applicability.YES : Applicability.NO;
    }

    private static boolean hits(Constraint c, MeetingTime m) {
        return switch (c.kind()) {
            case BLOCK_DAY -> m.getDayOfWeek() == c.dayOfWeek();
            case BLOCK_SECTION -> covers(m, c.section());
            case BLOCK_SLOT -> m.getDayOfWeek() == c.dayOfWeek() && covers(m, c.section());
            default -> false;
        };
    }

    private static boolean covers(MeetingTime m, int section) {
        return m.getStartSection() <= section && section <= m.getEndSection();
    }

    private static String courseOf(ConflictChecker.Analysis analysis, String offeringId) {
        CourseOffering o = analysis.offeringsById().get(offeringId);
        return o == null ? "?" : o.getCourseCode();
    }

    private static List<Issue> cap(List<Issue> list) {
        if (list.size() <= MAX_ISSUES) return List.copyOf(list);
        List<Issue> out = new ArrayList<>(list.subList(0, MAX_ISSUES - 1));
        out.add(new Issue("RESULT_TRUNCATED",
            "另有 " + (list.size() - (MAX_ISSUES - 1)) + " 条同类结果未逐条列出", null, false));
        return out;
    }

    /** 收集判决所需的三类结果。 */
    private static final class Findings {
        final List<Issue> violations = new ArrayList<>();
        final List<Issue> unknowns = new ArrayList<>();
        final List<String> performed = new ArrayList<>();

        void violation(String code, String message, String field) {
            violations.add(new Issue(code, clip(message), field, false));
        }

        void unknown(String code, String message, String field) {
            unknowns.add(new Issue(code, clip(message), field, false));
        }

        void performed(String description) {
            performed.add(description);
        }

        private static String clip(String s) {
            return s.length() <= MAX_MESSAGE ? s : s.substring(0, MAX_MESSAGE);
        }
    }

    // ---------------------------------------------------------------- 输入校验

    private static void validateShape(PlanValidationRequest r) {
        if (r == null) throw new InvalidRecordInput("body", "请求体缺失");
        if (!"1.0".equals(r.schemaVersion())) {
            throw new InvalidRecordInput("schemaVersion", "schemaVersion 必须为 1.0");
        }
        checkId("curriculumSnapshotId", r.curriculumSnapshotId());
        if (r.offeringSnapshotId() != null) checkId("offeringSnapshotId", r.offeringSnapshotId());
        checkId("academicRecordId", r.academicRecordId());
        if (!"REAL".equals(r.mode()) && !"SIMULATION".equals(r.mode())) {
            throw new InvalidRecordInput("mode", "mode 只能是 REAL 或 SIMULATION");
        }
        if (r.items() == null || r.items().isEmpty() || r.items().size() > MAX_ITEMS) {
            throw new InvalidRecordInput("items", "items 必须为 1 到 " + MAX_ITEMS + " 项");
        }
        for (int i = 0; i < r.items().size(); i++) {
            PlanItem item = r.items().get(i);
            String f = "items[" + i + "]";
            if (item == null) throw new InvalidRecordInput(f, "方案项不能为空");
            checkId(f + ".courseCode", item.courseCode());
            if (item.teacherKey() != null) checkId(f + ".teacherKey", item.teacherKey());
            if (item.classId() != null) checkId(f + ".classId", item.classId());
        }
        if (r.hardConstraints() == null || r.hardConstraints().size() > MAX_CONSTRAINTS) {
            throw new InvalidRecordInput("hardConstraints", "hardConstraints 必须为 0 到 " + MAX_CONSTRAINTS + " 项");
        }
        for (int i = 0; i < r.hardConstraints().size(); i++) {
            validateConstraint(i, r.hardConstraints().get(i));
        }
    }

    private static void validateConstraint(int i, Constraint c) {
        String f = "hardConstraints[" + i + "]";
        if (c == null) throw new InvalidRecordInput(f, "硬约束不能为空");
        if (!List.of(BLOCK_DAY, BLOCK_SECTION, BLOCK_SLOT, PIN_TEACHER_COURSE, PIN_COURSE, MAX_CREDITS)
                .contains(c.kind())) {
            throw new InvalidRecordInput(f + ".kind", "kind 不在允许的取值内");
        }
        if (c.sourceText() == null || c.sourceText().isEmpty() || c.sourceText().length() > MAX_SOURCE_TEXT) {
            throw new InvalidRecordInput(f + ".sourceText", "sourceText 必填，长度 1 到 " + MAX_SOURCE_TEXT);
        }
        if (c.courseCode() != null) checkId(f + ".courseCode", c.courseCode());
        if (c.teacherKey() != null) checkId(f + ".teacherKey", c.teacherKey());
        if (c.dayOfWeek() != null && (c.dayOfWeek() < 1 || c.dayOfWeek() > 7)) {
            throw new InvalidRecordInput(f + ".dayOfWeek", "dayOfWeek 必须在 1 到 7 之间");
        }
        if (c.section() != null && (c.section() < 1 || c.section() > 64)) {
            throw new InvalidRecordInput(f + ".section", "section 必须在 1 到 64 之间");
        }
        if (c.value() != null) {
            double v = c.value();
            if (!(v >= 0 && v <= 1000)) {
                throw new InvalidRecordInput(f + ".value", "value 必须在 0 到 1000 之间");
            }
            if (BigDecimal.valueOf(v).stripTrailingZeros().scale() > 2) {
                throw new InvalidRecordInput(f + ".value", "value 最多两位小数");
            }
        }
        switch (c.kind()) {
            case BLOCK_DAY -> requireNonNull(c.dayOfWeek(), f + ".dayOfWeek", "BLOCK_DAY 需要 dayOfWeek");
            case BLOCK_SECTION -> requireNonNull(c.section(), f + ".section", "BLOCK_SECTION 需要 section");
            case BLOCK_SLOT -> {
                requireNonNull(c.dayOfWeek(), f + ".dayOfWeek", "BLOCK_SLOT 需要 dayOfWeek");
                requireNonNull(c.section(), f + ".section", "BLOCK_SLOT 需要 section");
            }
            case PIN_COURSE -> requireNonNull(c.courseCode(), f + ".courseCode", "PIN_COURSE 需要 courseCode");
            case PIN_TEACHER_COURSE -> {
                requireNonNull(c.courseCode(), f + ".courseCode", "PIN_TEACHER_COURSE 需要 courseCode");
                requireNonNull(c.teacherKey(), f + ".teacherKey", "PIN_TEACHER_COURSE 需要 teacherKey");
            }
            case MAX_CREDITS -> requireNonNull(c.value(), f + ".value", "MAX_CREDITS 需要 value");
            default -> throw new IllegalStateException("unreachable: " + c.kind());
        }
    }

    private static void requireNonNull(Object v, String field, String message) {
        if (v == null) throw new InvalidRecordInput(field, message);
    }

    private static void checkId(String field, String value) {
        if (value == null || !ID.matcher(value).matches()) {
            throw new InvalidRecordInput(field, field + " 缺失或格式不合法");
        }
    }
}
