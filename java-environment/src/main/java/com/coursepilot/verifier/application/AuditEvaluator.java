package com.coursepilot.verifier.application;

import com.coursepilot.verifier.domain.AuditOutcome;
import com.coursepilot.verifier.persistence.entity.CompletedCourse;
import com.coursepilot.verifier.persistence.entity.Requirement;
import com.coursepilot.verifier.persistence.entity.Transcript;
import com.coursepilot.verifier.persistence.repo.RequirementRepository;
import com.coursepilot.verifier.persistence.repo.TranscriptRepository;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

@Service
public class AuditEvaluator {

    private final RequirementRepository requirementRepo;
    private final TranscriptRepository transcriptRepo;

    public AuditEvaluator(RequirementRepository requirementRepo, TranscriptRepository transcriptRepo) {
        this.requirementRepo = requirementRepo;
        this.transcriptRepo = transcriptRepo;
    }

    public AuditOutcome evaluate(String studentId, String planId) {
        // 1. 查培养方案要求
        List<Requirement> requirements = requirementRepo.findByPlanId(planId);
        if (requirements.isEmpty()) {
            return new AuditOutcome(AuditOutcome.Status.UNKNOWN, List.of("培养方案不存在或无要求"));
        }

        // 2. 查学生的真实成绩单
        Transcript transcript = transcriptRepo.findByStudentId(studentId);
        if (transcript == null || transcript.getCompletedCourses() == null) {
            return new AuditOutcome(AuditOutcome.Status.UNKNOWN, List.of("该学生没有学业记录"));
        }

        // 3. 累加已修学分 (简单起见，这里假设所有已修通过的课都算进总学分，真实业务还需按 category 匹配)
        BigDecimal totalEarned = BigDecimal.ZERO;
        for (CompletedCourse c : transcript.getCompletedCourses()) {
            if (c.isPassed() && c.getCredits() != null) {
                totalEarned = totalEarned.add(c.getCredits());
            }
        }

        // 4. 算总缺口（这里做一个极其简化的演示逻辑：只比总学分）
        BigDecimal totalRequired = BigDecimal.ZERO;
        for (Requirement req : requirements) {
            totalRequired = totalRequired.add(req.getRequiredCredits());
        }

        List<String> failReasons = new ArrayList<>();
        if (totalEarned.compareTo(totalRequired) < 0) {
            BigDecimal gap = totalRequired.subtract(totalEarned);
            failReasons.add("总学分还差 " + gap + " 分");
            return new AuditOutcome(AuditOutcome.Status.FAIL, failReasons);
        }

        return new AuditOutcome(AuditOutcome.Status.PASS, List.of("学分已满足"));
    }
}
