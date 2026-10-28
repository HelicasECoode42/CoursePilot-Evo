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
 *   - 没有学业记录（transcript 为 null）：所有要求判 UNKNOWN，缺口不给确定值。
 *   - 学业记录未声明完整（transcriptComplete = false）：已修学分只是下界。
 *     已满足的要求仍为满足（学分只增不减）；未满足的要求判 UNKNOWN，缺口不给确定值。
 *   - IN_PROGRESS / UNKNOWN 不计学分，但它们可能带来学分：相应类别记为「待定」。
 *     待定类别若已满足则仍为满足；未满足则判 UNKNOWN，不判确定缺口。
 *   - PASSED 但学分未知（课程库与记录都没有学分）、或课程不在库中 / 类别为空：
 *     相应类别判 UNKNOWN。课程不在库或类别为空时无法归类，所有类别都判 UNKNOWN。
 */
final class AcademicLedger {

    private final Map<String, Double> earned = new HashMap<>();
    private final Map<String, Set<String>> courseCodes = new HashMap<>();
    private final Set<String> hardUnknownCategories = new HashSet<>();
    private final Set<String> pendingCategories = new HashSet<>();
    private boolean hardUnknownAll;
    private boolean pendingAll;
    private boolean hasPassed;
    private final List<AuditDtos.Issue> issues = new ArrayList<>();
    /** 没有学业记录：所有要求都无法确定。 */
    private final boolean noRecord;
    /** 学业记录是否声明完整；没有记录时视为不完整。 */
    private final boolean transcriptComplete;

    private AcademicLedger(boolean noRecord, boolean transcriptComplete) {
        this.noRecord = noRecord;
        this.transcriptComplete = transcriptComplete;
    }

    /**
     * transcript 为 null 表示该主体还没有学业记录：没有任何课程，也没有问题项，
     * 所有要求都判 UNKNOWN（不把「没有记录」当成「已修 0 学分」）。
     */
    static AcademicLedger of(Transcript transcript, Function<String, Optional<Course>> catalog) {
        if (transcript == null) {
            return new AcademicLedger(true, false);
        }
        AcademicLedger ledger = new AcademicLedger(false, transcript.isTranscriptComplete());
        Map<String, List<TranscriptCourse>> byCode = new LinkedHashMap<>();
        for (TranscriptCourse c : transcript.getCompletedCourses()) {
            byCode.computeIfAbsent(c.getCourseCode(), k -> new ArrayList<>()).add(c);
        }
        for (List<TranscriptCourse> attempts : byCode.values()) {
            attempts.sort(Comparator.comparingInt(TranscriptCourse::getAttemptNo));
            Optional<TranscriptCourse> passed = attempts.stream()
                .filter(a -> a.getOutcome() == TranscriptCourse.Outcome.PASSED)
                .findFirst();
            if (passed.isPresent()) {
                ledger.addPassed(passed.get(), catalog);
            } else if (attempts.stream().anyMatch(AcademicLedger::isPending)) {
                ledger.addPending(attempts.get(0).getCourseCode(), catalog);
            }
            // 只有 FAILED 的课程：不计学分，也不是未知。
        }
        return ledger;
    }

    private void addPassed(TranscriptCourse row, Function<String, Optional<Course>> catalog) {
        hasPassed = true;
        String code = row.getCourseCode();
        Optional<Course> course = catalog.apply(code);
        if (course.isEmpty()) {
            hardUnknownAll = true;
            issues.add(new AuditDtos.Issue("COURSE_NOT_IN_CATALOG",
                "课程 " + code + " 不在课程库中，无法归类", "completedCourses", false));
            return;
        }
        String category = course.get().getCategory();
        if (category == null || category.isBlank()) {
            hardUnknownAll = true;
            issues.add(new AuditDtos.Issue("COURSE_CATEGORY_MISSING",
                "课程 " + code + " 类别为空", "completedCourses", false));
            return;
        }
        courseCodes.computeIfAbsent(category, k -> new TreeSet<>()).add(code);

        // 两边都必须是包装类型：混用 double 会在 catalog 学分为 null 时拆箱抛 NPE。
        Double credits = row.getEarnedCredits() != null
            ? Double.valueOf(row.getEarnedCredits().doubleValue()) : course.get().getCredits();
        if (credits == null) {
            hardUnknownCategories.add(category);
            issues.add(new AuditDtos.Issue("CREDITS_UNKNOWN",
                "课程 " + code + " 学分未知", "completedCourses", false));
            return;
        }
        earned.merge(category, credits, Double::sum);
    }

    private void addPending(String code, Function<String, Optional<Course>> catalog) {
        Optional<Course> course = catalog.apply(code);
        String category = course.map(Course::getCategory).orElse(null);
        if (category == null || category.isBlank()) {
            pendingAll = true;
            issues.add(new AuditDtos.Issue("PENDING_COURSE_UNCATEGORIZED",
                "课程 " + code + " 尚未出结果，且无法归类，所有要求的缺口都不能确定",
                "completedCourses", false));
            return;
        }
        pendingCategories.add(category);
        issues.add(new AuditDtos.Issue("PENDING_COURSE",
            "课程 " + code + " 在修或结果未知，" + category + " 类别的缺口不能确定",
            "completedCourses", false));
    }

    private static boolean isPending(TranscriptCourse c) {
        return c.getOutcome() == TranscriptCourse.Outcome.IN_PROGRESS
            || c.getOutcome() == TranscriptCourse.Outcome.UNKNOWN;
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

    List<String> courseCodes(String category) {
        return List.copyOf(courseCodes.getOrDefault(category, Set.of()));
    }

    boolean hasPassed() { return hasPassed; }

    List<AuditDtos.Issue> issues() { return List.copyOf(issues); }
}
