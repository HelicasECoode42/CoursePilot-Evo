package com.coursepilot.verifier.application;

import com.coursepilot.verifier.persistence.entity.AcademicRecord;
import com.coursepilot.verifier.persistence.entity.Course;
import com.coursepilot.verifier.persistence.entity.Requirement;
import com.coursepilot.verifier.persistence.repo.AcademicRecordRepository;
import com.coursepilot.verifier.persistence.repo.CourseRepository;
import com.coursepilot.verifier.persistence.repo.RequirementRepository;
import com.coursepilot.verifier.web.dto.AuditDtos;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

/**
 * 把学业核对结果摆成契约的 AuditResult。
 *
 * 算法和 AuditEvaluator 一致（重修去重、学分未知不当 0、有缺口优先于未知），
 * 区别只在于这里逐条产出 AuditItem，而不是把数字拼成一句中文。C 模块按
 * contracts/java.openapi.json 调用 POST /api/v1/requirements/audit，拿到的就是这个结构。
 *
 * 当前模型的已知落差，统一记进 unknowns，不猜也不填假值：
 *   - 还没有培养快照与学业记录聚合实体，暂以 planId / studentId 承担两个 ID；
 *   - Requirement 没有 courseCodes 与 sourceRefIds，返回空数组并记未知；
 *   - 没有记录完整性与修订号，transcriptComplete 返回 false、recordRevision 返回 1。
 */
@Service
public class AuditResultAssembler {

    private final RequirementRepository requirementRepo;
    private final AcademicRecordRepository recordRepo;
    private final CourseRepository courseRepo;

    public AuditResultAssembler(RequirementRepository requirementRepo,
                                AcademicRecordRepository recordRepo,
                                CourseRepository courseRepo) {
        this.requirementRepo = requirementRepo;
        this.recordRepo = recordRepo;
        this.courseRepo = courseRepo;
    }

    public AuditDtos.AuditResult assemble(String curriculumSnapshotId, String academicRecordId) {
        List<AuditDtos.Issue> unknowns = new ArrayList<>();
        List<Requirement> requirements = requirementRepo.findByPlanId(curriculumSnapshotId);

        if (requirements.isEmpty()) {
            unknowns.add(new AuditDtos.Issue("CURRICULUM_NOT_FOUND",
                "培养方案 " + curriculumSnapshotId + " 没有类别要求，无法核对",
                "curriculumSnapshotId", false));
            return emptyResult(curriculumSnapshotId, academicRecordId, unknowns);
        }

        // 重修去重：同一课程只取第一次通过的记录。
        Map<String, AcademicRecord> firstPassed = new LinkedHashMap<>();
        recordRepo.findByStudentId(academicRecordId).stream()
            .filter(AcademicRecord::isPassed)
            .sorted(Comparator.comparingInt(AcademicRecord::getAttemptNo))
            .forEach(r -> firstPassed.putIfAbsent(r.getCourseCode(), r));

        if (firstPassed.isEmpty()) {
            unknowns.add(new AuditDtos.Issue("ACADEMIC_RECORD_EMPTY",
                "学业记录 " + academicRecordId + " 没有已通过的课程，缺口无法计算",
                "academicRecordId", false));
        }

        Map<String, Double> earned = new LinkedHashMap<>();
        Map<String, Set<String>> courseCodesByCategory = new LinkedHashMap<>();
        Set<String> unknownCategories = new HashSet<>();

        for (AcademicRecord record : firstPassed.values()) {
            Course course = courseRepo.findById(record.getCourseCode()).orElse(null);
            if (course == null) {
                unknowns.add(new AuditDtos.Issue("COURSE_NOT_IN_CATALOG",
                    "课程 " + record.getCourseCode() + " 不在课程库中，无法归类",
                    "completedCourses", false));
                continue;
            }
            String category = course.getCategory();
            if (category == null || category.isBlank()) {
                unknowns.add(new AuditDtos.Issue("COURSE_CATEGORY_MISSING",
                    "课程 " + course.getCourseCode() + " 类别为空", "completedCourses", false));
                continue;
            }
            courseCodesByCategory
                .computeIfAbsent(category, k -> new TreeSet<>())
                .add(course.getCourseCode());

            Double credits = record.getCreditsEarned() != null
                ? record.getCreditsEarned() : course.getCredits();
            if (credits == null) {
                unknownCategories.add(category);
                unknowns.add(new AuditDtos.Issue("CREDITS_UNKNOWN",
                    "课程 " + course.getCourseCode() + " 学分未知", "completedCourses", false));
                continue;
            }
            earned.merge(category, credits, Double::sum);
        }

        List<AuditDtos.AuditItem> items = new ArrayList<>();
        for (Requirement req : requirements) {
            String category = req.getCategory();
            double required = req.getRequiredCredits();
            double got = earned.getOrDefault(category, 0.0);

            AuditDtos.State state;
            if (unknownCategories.contains(category)) {
                // 该类别里有学分未知的课程，缺口算不准，不能说满足也不能说差多少。
                state = AuditDtos.State.UNKNOWN;
            } else if (got >= required) {
                state = AuditDtos.State.SATISFIED;
            } else {
                state = AuditDtos.State.UNSATISFIED;
            }

            items.add(new AuditDtos.AuditItem(
                requirementId(req),
                List.copyOf(courseCodesByCategory.getOrDefault(category, Set.of())),
                required,
                got,
                Math.max(0.0, required - got),
                state,
                sourceRefIds(curriculumSnapshotId)));
        }

        unknowns.add(new AuditDtos.Issue("REQUIREMENT_SOURCE_REFS_MISSING",
            "当前 Requirement 没有记录课程清单与来源引用，courseCodes 仅由已修记录反推，sourceRefIds 为空",
            "requirements", false));
        unknowns.add(new AuditDtos.Issue("TRANSCRIPT_COMPLETENESS_UNKNOWN",
            "当前模型不记录学业记录完整性与修订号，transcriptComplete 按未确认处理",
            "transcriptComplete", false));

        return new AuditDtos.AuditResult(
            curriculumSnapshotId, academicRecordId, 1, false,
            items, List.of(), List.copyOf(unknowns));
    }

    /**
     * requirementId 必须匹配契约的 ^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$，不能含中文。
     * 类别名是中文，所以用自增主键做稳定标识，类别放在 courseCodes 与消息里体现。
     */
    private String requirementId(Requirement req) {
        return "req-" + req.getId();
    }

    /**
     * 契约要求每条核对结论至少有一个来源引用（sourceRefIds minItems=1），
     * 即结论必须可追溯。当前判断完全来自该培养快照里的类别学分要求，
     * 所以引用快照本身；等 Requirement 记录了原表行号后换成更细的引用。
     */
    private List<String> sourceRefIds(String curriculumSnapshotId) {
        return List.of("curriculum:" + curriculumSnapshotId);
    }

    private AuditDtos.AuditResult emptyResult(String curriculumSnapshotId,
                                              String academicRecordId,
                                              List<AuditDtos.Issue> unknowns) {
        return new AuditDtos.AuditResult(curriculumSnapshotId, academicRecordId, 1, false,
            List.of(), List.of(), List.copyOf(unknowns));
    }
}
