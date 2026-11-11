package com.coursepilot.verifier.application;

import com.coursepilot.verifier.domain.AuditOutcome;
import com.coursepilot.verifier.persistence.entity.Course;
import com.coursepilot.verifier.persistence.entity.Requirement;
import com.coursepilot.verifier.persistence.entity.Transcript;
import com.coursepilot.verifier.persistence.entity.CurriculumCourse;
import com.coursepilot.verifier.persistence.repo.CurriculumCourseRepository;
import com.coursepilot.verifier.persistence.repo.RequirementRepository;
import com.coursepilot.verifier.persistence.repo.TranscriptRepository;
import com.coursepilot.verifier.web.dto.AuditDtos;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.math.BigDecimal;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * 契约外的 credit-gap 排查视图（GET /api/v1/verification/credit-gap）。
 * 数据源与规则和 AuditResultAssembler 共用 AcademicLedger，这里只把结果压成
 * PASS / FAIL / UNKNOWN 与中文原因。
 */
@Service
public class AuditEvaluator {

    private final RequirementRepository requirementRepo;
    private final TranscriptRepository transcriptRepo;
    private final CurriculumCourseRepository curriculumCourses;
    private final SchoolReportLoader schoolReports;

    public AuditEvaluator(RequirementRepository requirementRepo,
                          TranscriptRepository transcriptRepo,
                          CurriculumCourseRepository curriculumCourses,
                          SchoolReportLoader schoolReports) {
        this.requirementRepo = requirementRepo;
        this.transcriptRepo = transcriptRepo;
        this.curriculumCourses = curriculumCourses;
        this.schoolReports = schoolReports;
    }

    public AuditOutcome evaluate(String studentId, String planId) {
        List<Requirement> requirements = requirementRepo.findByPlanId(planId);
        if (requirements.isEmpty()) {
            return new AuditOutcome(AuditOutcome.Status.UNKNOWN,
                List.of("培养方案 " + planId + " 没有类别要求，无法核对"));
        }

        Transcript transcript = transcriptRepo.findByStudentId(studentId).orElse(null);
        SchoolReport school = schoolReports.latest(studentId, planId);
        Map<String, Course> snapshotCatalog = transcript == null ? Map.of()
            : curriculumCourses.findBySnapshot_SnapshotIdAndCourse_CourseCodeIn(planId,
                    transcript.getCompletedCourses().stream().map(c -> c.getCourseCode()).distinct().toList())
                .stream()
                .collect(Collectors.groupingBy(cc -> cc.getCourse().getCourseCode()))
                .values().stream().filter(group -> group.size() == 1).map(group -> group.getFirst())
                .filter(cc -> hasUsableFacts(cc, planId))
                .collect(Collectors.toMap(cc -> cc.getCourse().getCourseCode(), cc ->
                    new Course(cc.getCourse().getCourseCode(), cc.getName(), cc.getCredits(), cc.getCategory())));
        AcademicLedger ledger = AcademicLedger.of(transcript, school.completes(transcript),
            code -> java.util.Optional.ofNullable(snapshotCatalog.get(code)), school, requirements.stream()
                .map(Requirement::getCategory).collect(java.util.stream.Collectors.toSet()));

        List<String> failReasons = new ArrayList<>();
        boolean anyUnknown = false;
        for (Requirement req : requirements) {
            var schoolCategory = school.category(req.getCategory());
            if (schoolCategory.isPresent()) {
                // 与 AuditResultAssembler 一致：学校同名类别直接采用学校剩余学分。
                if (schoolCategory.get().remaining().signum() > 0) {
                    failReasons.add(req.getCategory() + " 按学校报告还差 "
                        + schoolCategory.get().remaining().doubleValue() + " 学分");
                }
                continue;
            }
            AuditDtos.State state = ledger.stateFor(req);
            if (state == AuditDtos.State.UNSATISFIED) {
                failReasons.add(req.getCategory() + " 还差 "
                    + BigDecimal.valueOf(req.getRequiredCredits()).subtract(ledger.earnedDecimal(req.getCategory()))
                        .doubleValue() + " 学分");
            } else if (state == AuditDtos.State.UNKNOWN) {
                anyUnknown = true;
            }
        }

        if (!failReasons.isEmpty()) {
            return new AuditOutcome(AuditOutcome.Status.FAIL, failReasons);
        }
        if (anyUnknown || !ledger.issues().isEmpty()) {
            List<String> reasons = ledger.issues().stream().map(AuditDtos.Issue::message).toList();
            return new AuditOutcome(AuditOutcome.Status.UNKNOWN,
                reasons.isEmpty() ? List.of("部分类别无法确认") : reasons);
        }
        return new AuditOutcome(AuditOutcome.Status.PASS, List.of("所有类别学分已满足"));
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
}
