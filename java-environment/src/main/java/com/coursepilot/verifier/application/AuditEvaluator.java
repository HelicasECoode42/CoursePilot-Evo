package com.coursepilot.verifier.application;

import com.coursepilot.verifier.domain.AuditOutcome;
import com.coursepilot.verifier.persistence.entity.*;
import com.coursepilot.verifier.persistence.repo.*;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.util.*;

@Service
public class AuditEvaluator {

    private final RequirementRepository requirementRepo;
    private final AcademicRecordRepository recordRepo;
    private final CourseRepository courseRepo;

    public AuditEvaluator(RequirementRepository requirementRepo,
                          AcademicRecordRepository recordRepo,
                          CourseRepository courseRepo) {
        this.requirementRepo = requirementRepo;
        this.recordRepo = recordRepo;
        this.courseRepo = courseRepo;
    }

    public AuditOutcome evaluate(String studentId, String planId) {
        List<Requirement> requirements = requirementRepo.findByPlanId(planId);
        if (requirements.isEmpty()) {
            return new AuditOutcome(AuditOutcome.Status.UNKNOWN,
                List.of("培养方案 " + planId + " 没有类别要求，无法核对"));
        }

        List<AcademicRecord> records = recordRepo.findByStudentId(studentId);
        // 重修去重：同一课程只取第一次通过的记录
        Map<String, AcademicRecord> firstPassed = new LinkedHashMap<>();
        records.stream()
            .filter(AcademicRecord::isPassed)
            .sorted(Comparator.comparingInt(AcademicRecord::getAttemptNo))
            .forEach(r -> firstPassed.putIfAbsent(r.getCourseCode(), r));

        // 改为 BigDecimal
        Map<String, BigDecimal> earned = new LinkedHashMap<>();
        Set<String> unknownCategories = new HashSet<>();
        List<String> unknownReasons = new ArrayList<>();

        for (AcademicRecord record : firstPassed.values()) {
            Course course = courseRepo.findById(record.getCourseCode()).orElse(null);
            if (course == null) {
                return new AuditOutcome(AuditOutcome.Status.UNKNOWN,
                    List.of("课程 " + record.getCourseCode() + " 不在课程库中，无法归类"));
            }
            if (course.getCategory() == null || course.getCategory().isBlank()) {
                return new AuditOutcome(AuditOutcome.Status.UNKNOWN,
                    List.of("课程 " + course.getCourseCode() + " 类别为空"));
            }

            BigDecimal credits = record.getCreditsEarned() != null
                ? record.getCreditsEarned() : course.getCredits();
            if (credits == null) {
                unknownCategories.add(course.getCategory());
                unknownReasons.add("课程 " + course.getCourseCode() + " 学分未知");
                continue;
            }
            // 使用 add 方法累加
            earned.merge(course.getCategory(), credits, BigDecimal::add);
        }

        boolean anyFail = false;
        List<String> failReasons = new ArrayList<>();
        boolean anyUnknown = false;

        for (Requirement req : requirements) {
            if (unknownCategories.contains(req.getCategory())) {
                anyUnknown = true;
                continue;
            }
            BigDecimal got = earned.getOrDefault(req.getCategory(), BigDecimal.ZERO);

            // 使用 compareTo 进行比较：如果 got 小于 required，说明还差学分
            if (got.compareTo(req.getRequiredCredits()) < 0) {
                anyFail = true;
                // 使用 subtract 计算差额
                BigDecimal gap = req.getRequiredCredits().subtract(got);
                failReasons.add(req.getCategory() + " 还差 " + gap + " 学分");
            }
        }

        if (anyFail) {
            return new AuditOutcome(AuditOutcome.Status.FAIL, failReasons);
        }
        if (anyUnknown) {
            return new AuditOutcome(AuditOutcome.Status.UNKNOWN, unknownReasons);
        }
        return new AuditOutcome(AuditOutcome.Status.PASS, List.of("所有类别学分已满足"));
    }
}
