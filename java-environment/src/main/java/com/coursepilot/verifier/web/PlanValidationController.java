package com.coursepilot.verifier.web;

import com.coursepilot.verifier.application.PlanValidationService;
import com.coursepilot.verifier.web.dto.PlanDtos;
import org.springframework.web.bind.annotation.*;

/**
 * POST /api/v1/plans/validate（operationId validatePlan）。
 *
 * 单独成类、用绝对路径挂载。不能挂到 VerificationController 下面：那个类的类级注解是
 * /api/v1/verification，会把路径变成 /api/v1/verification/plans/validate，与契约对不上。
 * 归属一律由 X-Subject-Id 派生（经 SubjectGuard），不接受请求体自报主体。
 */
@RestController
@RequestMapping("/api/v1")
public class PlanValidationController {

    private final SubjectGuard subjects;
    private final PlanValidationService plans;

    public PlanValidationController(SubjectGuard subjects, PlanValidationService plans) {
        this.subjects = subjects;
        this.plans = plans;
    }

    @PostMapping("/plans/validate")
    public Envelope<PlanDtos.PlanValidation> validate(
        @RequestHeader(value = "X-Request-Id", required = false) String requestId,
        @RequestHeader(value = "X-Subject-Id", required = false) String subjectId,
        @RequestBody PlanDtos.PlanValidationRequest body) {
        String subject = subjects.require(subjectId);
        PlanDtos.PlanValidation result = plans.validate(subject, body);
        // 与 /verification/conflicts 一致：UNKNOWN 判决用 UNKNOWN 封套，INVALID 仍是 OK 封套且 data 明确违规。
        if ("UNKNOWN".equals(result.verdict())) {
            return Envelope.unknown(requestId, result,
                "核验未完成：" + result.unknownChecks().size() + " 项无法核验，不能判为通过");
        }
        return Envelope.ok(requestId, result);
    }
}
