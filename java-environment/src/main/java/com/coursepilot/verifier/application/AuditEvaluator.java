package com.coursepilot.verifier.application;

import com.coursepilot.verifier.domain.AuditOutcome;
import com.coursepilot.verifier.persistence.entity.Requirement;
import com.coursepilot.verifier.persistence.entity.Transcript;
import com.coursepilot.verifier.persistence.repo.CourseRepository;
import com.coursepilot.verifier.persistence.repo.RequirementRepository;
import com.coursepilot.verifier.persistence.repo.TranscriptRepository;
import com.coursepilot.verifier.web.dto.AuditDtos;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;

/**
 * 契约外的 credit-gap 排查视图（GET /api/v1/verification/credit-gap）。
 * 数据源与规则和 AuditResultAssembler 共用 AcademicLedger，这里只把结果压成
 * PASS / FAIL / UNKNOWN 与中文原因。
 */
@Service
public class AuditEvaluator {

    private final RequirementRepository requirementRepo;
    private final TranscriptRepository transcriptRepo;
    private final CourseRepository courseRepo;

    public AuditEvaluator(RequirementRepository requirementRepo,
                          TranscriptRepository transcriptRepo,
                          CourseRepository courseRepo) {
        this.requirementRepo = requirementRepo;
        this.transcriptRepo = transcriptRepo;
        this.courseRepo = courseRepo;
    }

    public AuditOutcome evaluate(String studentId, String planId) {
        List<Requirement> requirements = requirementRepo.findByPlanId(planId);
        if (requirements.isEmpty()) {
            return new AuditOutcome(AuditOutcome.Status.UNKNOWN,
                List.of("培养方案 " + planId + " 没有类别要求，无法核对"));
        }

        Transcript transcript = transcriptRepo.findByStudentId(studentId).orElse(null);
        AcademicLedger ledger = AcademicLedger.of(transcript, courseRepo::findById);

        List<String> failReasons = new ArrayList<>();
        boolean anyUnknown = false;
        for (Requirement req : requirements) {
            AuditDtos.State state = ledger.stateFor(req);
            if (state == AuditDtos.State.UNSATISFIED) {
                failReasons.add(req.getCategory() + " 还差 "
                    + (req.getRequiredCredits() - ledger.earned(req.getCategory())) + " 学分");
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
}
