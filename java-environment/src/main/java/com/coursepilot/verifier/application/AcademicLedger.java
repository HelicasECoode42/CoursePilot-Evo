package com.coursepilot.verifier.application;

import com.coursepilot.verifier.persistence.entity.Course;
import com.coursepilot.verifier.persistence.entity.Requirement;
import com.coursepilot.verifier.persistence.entity.Transcript;
import com.coursepilot.verifier.persistence.entity.TranscriptCourse;
import com.coursepilot.verifier.web.dto.AuditDtos;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.TreeSet;
import java.util.function.Function;

/**
 * 把一份学业记录（Transcript 聚合）折算成「每个类别已修多少学分、哪些地方不能确定」。
 * AuditResultAssembler（契约核对）与 AuditEvaluator（credit-gap 排查）共用这里，
 * 规则只写一处。
 *
 * 规则：
 *   - 重修去重：同一课程取第一次 PASSED 的那次，之后的修读不再计。
 *   - 只有 PASSED 计入已修学分；FAILED 不计，也不算未知（确定没通过，是事实）。
 *   - 类别归属：课程库里的类别优先；课程不在库中或类别为空时，用学校报告里该课程挂的类别名。
 *     学校侧按课程挂的节点沿祖先链向上，取最近的培养类别名（如 通选课 -> 通识课）。
 *     两边都没有则无法归类，相应判断按未知处理。
 *   - 在读（IN_PROGRESS）：不计已修学分，也不让类别判 UNKNOWN；缺口仍是 要求 − 已通过学分，
 *     在读学分单独报告为 inProgressCredits。
 *   - 结果未知（UNKNOWN）：这门课可能已通过，相应类别的缺口不能确定，记为待定。
 *   - 没有学业记录（transcript 为 null）：所有要求判 UNKNOWN，缺口不给确定值。
 *   - 学业记录未声明完整（transcriptComplete 为 false）：已修学分只是下界。
 *     已满足的要求仍为满足；未满足的要求判 UNKNOWN，缺口不给确定值。
 *   - PASSED 但学分未知（课程库、学校报告与记录都没有学分）：相应类别判 UNKNOWN。
 */
final class AcademicLedger {

    private final Map<String, Double> earned = new HashMap<>();
    private final Map<String, Double> inProgress = new HashMap<>();
    private final Set<String> inProgressUnknownCredits = new HashSet<>();
    private final Map<String, Set<String>> courseCodes = new HashMap<>();
    private final Set<String> hardUnknownCategories = new HashSet<>();
    private final Set<String> pendingCategories = new HashSet<>();
    private boolean hardUnknownAll;
    private boolean pendingAll;
    private boolean hasPassed;
    private final List<AuditDtos.Issue> issues = new ArrayList<>();
    /** 没有学业记录：所有要求都无法确定。 */
    private final boolean noRecord;
    /** 有效的完整性（已合并学校导入读全）。 */
    private final boolean transcriptComplete;
    private final SchoolReport school;
    /** 培养方案里的类别名（课程归类时用来识别学校节点链上哪一层是培养类别）。 */
    private final Set<String> curriculumCategories;

    private AcademicLedger(boolean noRecord, boolean transcriptComplete, SchoolReport school,
                           Set<String> curriculumCategories) {
        this.noRecord = noRecord;
        this.transcriptComplete = transcriptComplete;
        this.school = school;
        this.curriculumCategories = curriculumCategories;
    }

    /**
     * transcript 为 null 表示该主体还没有学业记录：没有任何课程，也没有问题项，
     * 所有要求都判 UNKNOWN（不把「没有记录」当成「已修 0 学分」）。
     * transcriptComplete 由调用方给出有效值（见 SchoolReport.completes）。
     */
    static AcademicLedger of(Transcript transcript, boolean transcriptComplete,
                             Function<String, Optional<Course>> catalog, SchoolReport school,
                             Set<String> curriculumCategories) {
        if (transcript == null) {
            return new AcademicLedger(true, false, school, curriculumCategories);
        }
        AcademicLedger ledger = new AcademicLedger(false, transcriptComplete, school,
            curriculumCategories);
        Map<String, List<TranscriptCourse>> byCode = new LinkedHashMap<>();
        for (TranscriptCourse c : transcript.getCompletedCourses()) {
            byCode.computeIfAbsent(c.getCourseCode(), k -> new ArrayList<>()).add(c);
        }
        for (List<TranscriptCourse> attempts : byCode.values()) {
            attempts.sort(Comparator.comparingInt(TranscriptCourse::getAttemptNo));
            String code = attempts.get(0).getCourseCode();
            Optional<TranscriptCourse> passed = attempts.stream()
                .filter(a -> a.getOutcome() == TranscriptCourse.Outcome.PASSED)
                .findFirst();
            if (passed.isPresent()) {
                ledger.addPassed(passed.get(), catalog);
            } else if (attempts.stream().anyMatch(a -> a.getOutcome() == TranscriptCourse.Outcome.UNKNOWN)) {
                ledger.addPending(code, catalog);
            } else if (attempts.stream().anyMatch(a -> a.getOutcome() == TranscriptCourse.Outcome.IN_PROGRESS)) {
                ledger.addInProgress(code, catalog);
            }
            // 只有 FAILED 的课程：不计学分，也不是未知。
        }
        return ledger;
    }

    /** 课程库类别优先，其次学校报告的链接类别；都没有则 null。 */
    private String categoryOf(String code, Optional<Course> course) {
        String fromCatalog = course.map(Course::getCategory).filter(c -> !c.isBlank()).orElse(null);
        return fromCatalog != null ? fromCatalog : school.categoryOfCourse(code, curriculumCategories);
    }

    private void addPassed(TranscriptCourse row, Function<String, Optional<Course>> catalog) {
        hasPassed = true;
        String code = row.getCourseCode();
        Optional<Course> course = catalog.apply(code);
        String category = categoryOf(code, course);
        if (category == null) {
            hardUnknownAll = true;
            issues.add(course.isEmpty()
                ? new AuditDtos.Issue("COURSE_NOT_IN_CATALOG",
                    "课程 " + code + " 不在课程库中，且学校报告未给出类别，无法归类", "completedCourses", false)
                : new AuditDtos.Issue("COURSE_CATEGORY_MISSING",
                    "课程 " + code + " 类别为空", "completedCourses", false));
            return;
        }
        courseCodes.computeIfAbsent(category, k -> new TreeSet<>()).add(code);

        // 两边都必须是包装类型：混用 double 会在学分为 null 时拆箱抛 NPE。
        Double credits = row.getEarnedCredits() != null
            ? Double.valueOf(row.getEarnedCredits().doubleValue())
            : course.map(Course::getCredits).orElse(school.creditsOfCourse(code));
        if (credits == null) {
            hardUnknownCategories.add(category);
            issues.add(new AuditDtos.Issue("CREDITS_UNKNOWN",
                "课程 " + code + " 学分未知", "completedCourses", false));
            return;
        }
        earned.merge(category, credits, Double::sum);
    }

    private void addPending(String code, Function<String, Optional<Course>> catalog) {
        String category = categoryOf(code, catalog.apply(code));
        if (category == null) {
            pendingAll = true;
            issues.add(new AuditDtos.Issue("PENDING_COURSE_UNCATEGORIZED",
                "课程 " + code + " 结果未知，且无法归类，所有要求的缺口都不能确定",
                "completedCourses", false));
            return;
        }
        pendingCategories.add(category);
        issues.add(new AuditDtos.Issue("PENDING_COURSE",
            "课程 " + code + " 结果未知，" + category + " 类别的缺口不能确定", "completedCourses", false));
    }

    /**
     * 在读课：不计已修学分，不产生问题项，也不让类别判 UNKNOWN。
     * 只把它的学分记到 inProgress；无法归类或学分未知时不计入，学分未知则该类别的在读学分报 null。
     */
    private void addInProgress(String code, Function<String, Optional<Course>> catalog) {
        Optional<Course> course = catalog.apply(code);
        String category = categoryOf(code, course);
        if (category == null) {
            return;
        }
        Double credits = course.map(Course::getCredits).orElse(school.creditsOfCourse(code));
        if (credits == null) {
            inProgressUnknownCredits.add(category);
            return;
        }
        inProgress.merge(category, credits, Double::sum);
    }

    /** 相应要求的状态。 */
    AuditDtos.State stateFor(Requirement req) {
        String category = req.getCategory();
        if (noRecord || hardUnknownAll || hardUnknownCategories.contains(category)) {
            return AuditDtos.State.UNKNOWN;
        }
        // 已修学分只增不减：未声明完整时，已满足的要求依然满足。
        if (earned(category) >= req.getRequiredCredits()) {
            return AuditDtos.State.SATISFIED;
        }
        // 未声明完整：漏录的课可能正好补足缺口，未满足的要求不能判确定缺口。
        if (!transcriptComplete || pendingAll || pendingCategories.contains(category)) {
            return AuditDtos.State.UNKNOWN;
        }
        return AuditDtos.State.UNSATISFIED;
    }

    double earned(String category) {
        return earned.getOrDefault(category, 0.0);
    }

    /** 该类别在读学分；学分有未知的在读课时为 null。 */
    Double inProgressCredits(String category) {
        if (inProgressUnknownCredits.contains(category)) {
            return null;
        }
        return inProgress.getOrDefault(category, 0.0);
    }

    List<String> courseCodes(String category) {
        return List.copyOf(courseCodes.getOrDefault(category, Set.of()));
    }

    boolean hasPassed() { return hasPassed; }

    List<AuditDtos.Issue> issues() { return List.copyOf(issues); }
}
