package com.coursepilot.verifier.web;

import com.coursepilot.verifier.application.*;
import com.coursepilot.verifier.domain.AuditOutcome;
import com.coursepilot.verifier.domain.ConflictResult;
import com.coursepilot.verifier.web.dto.PlanValidationDto;
import org.springframework.web.bind.annotation.*;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/verification")
public class VerificationController {

    private final AuditEvaluator auditEvaluator;
    private final TimeParser timeParser;
    private final ConflictChecker conflictChecker;

    public VerificationController(AuditEvaluator auditEvaluator,
                                  TimeParser timeParser,
                                  ConflictChecker conflictChecker) {
        this.auditEvaluator = auditEvaluator;
        this.timeParser = timeParser;
        this.conflictChecker = conflictChecker;
    }

    // --- 下面是你之前写的老接口，不用动 ---

    @GetMapping("/credit-gap")
    public Envelope<AuditOutcome> creditGap(
        @RequestHeader(value = "X-Request-Id", required = false) String requestId,
        @RequestHeader("X-Subject-Id") String studentId,
        @RequestParam String planId) {
        AuditOutcome outcome = auditEvaluator.evaluate(studentId, planId);
        return wrap(requestId, outcome, outcome.getStatus() == AuditOutcome.Status.UNKNOWN,
            String.join("；", outcome.getReasons()));
    }

    @PostMapping("/parse-time")
    public Envelope<TimeParser.ParseOutcome> parseTime(
        @RequestHeader(value = "X-Request-Id", required = false) String requestId,
        @RequestBody Map<String, String> body) {
        TimeParser.ParseOutcome outcome = timeParser.parse(body.get("meetingTextRaw"));
        return wrap(requestId, outcome, !outcome.isOk(),
            outcome.isOk() ? "解析成功" : outcome.getReason());
    }

    @PostMapping("/conflicts")
    public Envelope<ConflictResult> conflicts(
        @RequestHeader(value = "X-Request-Id", required = false) String requestId,
        @RequestBody List<String> offeringIds) {
        ConflictResult result = conflictChecker.check(offeringIds);
        boolean unknownOnly = !result.hasKnownConflict() && result.hasUnknownParticipant();
        return wrap(requestId, result, unknownOnly, result.getReason());
    }

    @PostMapping("/plans/validate")
    public Envelope<PlanValidationDto.PlanValidationResult> validatePlan(
        @RequestHeader(value = "X-Request-Id", required = false) String requestId,
        @RequestBody PlanValidationDto.PlanValidationRequest request) {

        if (request.snapshotId() == null || request.snapshotId().isBlank()) {
            return Envelope.unknown(requestId,
                new PlanValidationDto.PlanValidationResult("UNKNOWN", List.of("缺少合格当期快照"), List.of()),
                "缺少合格当期快照");
        }

        List<PlanValidationDto.PlanItem> items = request.planItems();
        if (items == null || items.isEmpty()) {
            return Envelope.ok(requestId, new PlanValidationDto.PlanValidationResult("VALID", List.of("课表为空，无冲突"), List.of()));
        }

        List<PlanValidationDto.ConflictItem> conflicts = new ArrayList<>();
        boolean hasUnknownTime = false;

        // 解析所有课的时间
        List<TimeParser.ParseOutcome> outcomes = new ArrayList<>();
        for (PlanValidationDto.PlanItem item : items) {
            TimeParser.ParseOutcome outcome = timeParser.parse(item.meetingTextRaw());
            outcomes.add(outcome);
            if (!outcome.isOk()) hasUnknownTime = true;
        }

        // 1. 两两比对时间冲突
        for (int i = 0; i < items.size(); i++) {
            for (int j = i + 1; j < items.size(); j++) {
                if (outcomes.get(i).isOk() && outcomes.get(j).isOk()) {
                    for (com.coursepilot.verifier.domain.MeetingTime a : outcomes.get(i).getMeetings()) {
                        for (com.coursepilot.verifier.domain.MeetingTime b : outcomes.get(j).getMeetings()) {
                            if (a.conflictsWith(b)) {
                                conflicts.add(new PlanValidationDto.ConflictItem(
                                    items.get(i).classId(), items.get(j).classId(), "时间重叠冲突"));
                            }
                        }
                    }
                }
            }
        }

        // 2. 检查硬约束 (Hard Constraints) - 例如："不排周五"
        if (request.hardConstraints() != null) {
            for (String constraint : request.hardConstraints()) {
                if (constraint.contains("周五")) {
                    for (int i = 0; i < items.size(); i++) {
                        if (outcomes.get(i).isOk()) {
                            for (com.coursepilot.verifier.domain.MeetingTime mt : outcomes.get(i).getMeetings()) {
                                if (mt.getDayOfWeek() == 5) { // 5 = 周五
                                    conflicts.add(new PlanValidationDto.ConflictItem(
                                        items.get(i).classId(), "硬约束", "触碰硬性约束：" + constraint));
                                }
                            }
                        }
                    }
                }
            }
        }

        // 3. 返回结果
        if (!conflicts.isEmpty()) {
            return Envelope.ok(requestId, new PlanValidationDto.PlanValidationResult("INVALID", List.of("发现冲突"), conflicts));
        }
        if (hasUnknownTime) {
            return Envelope.unknown(requestId,
                new PlanValidationDto.PlanValidationResult("UNKNOWN", List.of("部分课程时间无法解析，无法确认是否冲突"), List.of()),
                "部分课程时间无法解析");
        }
        return Envelope.ok(requestId, new PlanValidationDto.PlanValidationResult("VALID", List.of("核验通过"), List.of()));
    }

    private <T> Envelope<T> wrap(String requestId, T data, boolean unknown, String message) {
        return unknown ? Envelope.unknown(requestId, data, message) : Envelope.ok(requestId, data);
    }
}
