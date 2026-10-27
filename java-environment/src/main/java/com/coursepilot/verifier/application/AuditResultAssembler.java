package com.coursepilot.verifier.application;

import com.coursepilot.verifier.persistence.entity.CompletedCourse;
import com.coursepilot.verifier.persistence.entity.Course;
import com.coursepilot.verifier.persistence.entity.Requirement;
import com.coursepilot.verifier.persistence.entity.Transcript;
import com.coursepilot.verifier.persistence.repo.CourseRepository;
import com.coursepilot.verifier.persistence.repo.RequirementRepository;
import com.coursepilot.verifier.persistence.repo.TranscriptRepository;
import com.coursepilot.verifier.web.dto.AuditDtos;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.util.*;

@Service
public class AuditResultAssembler {

    private final RequirementRepository requirementRepo;
    private final TranscriptRepository transcriptRepo;
    private final CourseRepository courseRepo;

    public AuditResultAssembler(RequirementRepository requirementRepo,
                                TranscriptRepository transcriptRepo,
                                CourseRepository courseRepo) {
        this.requirementRepo = requirementRepo;
        this.transcriptRepo = transcriptRepo;
        this.courseRepo = courseRepo;
    }

    public AuditDtos.AuditResult assemble(String curriculumSnapshotId, String academicRecordId) {
        List<AuditDtos.Issue> unknowns = new ArrayList<>();
        List<Requirement> requirements = requirementRepo.findByPlanId(curriculumSnapshotId);

        if (requirements.isEmpty()) {
            unknowns.add(new AuditDtos.Issue("CURRICULUM_NOT_FOUND",
                "培养方案 " + curriculumSnapshotId + " 没有类别要求，无法核对", "curriculumSnapshotId", false));
            return emptyResult(curriculumSnapshotId, academicRecordId, unknowns);
        }

        Transcript transcript = transcriptRepo.findById(academicRecordId).orElse(null);
        if (transcript == null) {
            unknowns.add(new AuditDtos.Issue("ACADEMIC_RECORD_NOT_FOUND",
                "学业记录 " + academicRecordId + " 不存在", "academicRecordId", false));
            return emptyResult(curriculumSnapshotId, academicRecordId, unknowns);
        }

        List<CompletedCourse> completedCourses = transcript.getCompletedCourses();
        if (completedCourses == null || completedCourses.isEmpty()) {
            unknowns.add(new AuditDtos.Issue("ACADEMIC_RECORD_EMPTY",
                "学业记录没有已通过的课程，缺口无法计算", "academicRecordId", false));
        }

        Map<String, BigDecimal> earned = new LinkedHashMap<>();
        Map<String, Set<String>> courseCodesByCategory = new LinkedHashMap<>();
        Set<String> unknownCategories = new HashSet<>();

        if (completedCourses != null) {
            for (CompletedCourse record : completedCourses) {
                if (!record.isPassed()) continue;

                Course course = courseRepo.findById(record.getCourseCode()).orElse(null);
                String category = course != null ? course.getCategory() : null;

                if (category == null || category.isBlank()) {
                    unknowns.add(new AuditDtos.Issue("COURSE_CATEGORY_MISSING",
                        "课程 " + record.getCourseCode() + " 类别为空", "completedCourses", false));
                    continue;
                }

                courseCodesByCategory.computeIfAbsent(category, k -> new TreeSet<>()).add(record.getCourseCode());

                BigDecimal credits = record.getCredits() != null ? record.getCredits() : (course != null ? course.getCredits() : null);
                if (credits == null) {
                    unknownCategories.add(category);
                    unknowns.add(new AuditDtos.Issue("CREDITS_UNKNOWN",
                        "课程 " + record.getCourseCode() + " 学分未知", "completedCourses", false));
                    continue;
                }
                earned.merge(category, credits, BigDecimal::add);
            }
        }

        List<AuditDtos.AuditItem> items = new ArrayList<>();
        for (Requirement req : requirements) {
            String category = req.getCategory();
            BigDecimal required = req.getRequiredCredits();
            BigDecimal got = earned.getOrDefault(category, BigDecimal.ZERO);

            AuditDtos.State state;
            if (unknownCategories.contains(category)) {
                state = AuditDtos.State.UNKNOWN;
            } else if (got.compareTo(required) >= 0) {
                state = AuditDtos.State.SATISFIED;
            } else {
                state = AuditDtos.State.UNSATISFIED;
            }

            items.add(new AuditDtos.AuditItem(
                requirementId(req),
                List.copyOf(courseCodesByCategory.getOrDefault(category, Set.of())),
                required.doubleValue(),
                got.doubleValue(),
                Math.max(0.0, required.subtract(got).doubleValue()),
                state,
                sourceRefIds(curriculumSnapshotId)
            ));
        }

        unknowns.add(new AuditDtos.Issue("REQUIREMENT_SOURCE_REFS_MISSING",
            "当前 Requirement 没有记录课程清单与来源引用，courseCodes 仅由已修记录反推", "requirements", false));

        return new AuditDtos.AuditResult(
            curriculumSnapshotId,
            academicRecordId,
            transcript.getRevision(),
            transcript.isTranscriptComplete(),
            items, List.of(), List.copyOf(unknowns));
    }

    private String requirementId(Requirement req) {
        return "req-" + req.getId();
    }

    private List<String> sourceRefIds(String curriculumSnapshotId) {
        return List.of("curriculum:" + curriculumSnapshotId);
    }

    private AuditDtos.AuditResult emptyResult(String curriculumSnapshotId, String academicRecordId, List<AuditDtos.Issue> unknowns) {
        return new AuditDtos.AuditResult(curriculumSnapshotId, academicRecordId, 1, false, List.of(), List.of(), List.copyOf(unknowns));
    }
}
