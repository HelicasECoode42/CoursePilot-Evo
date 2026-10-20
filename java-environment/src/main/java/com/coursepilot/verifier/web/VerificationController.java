package com.coursepilot.verifier.web;

import com.coursepilot.verifier.application.*;
import com.coursepilot.verifier.domain.AuditOutcome;
import com.coursepilot.verifier.domain.ConflictResult;
import org.springframework.web.bind.annotation.*;

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

    @GetMapping("/credit-gap")
    public Envelope<AuditOutcome> creditGap(
        @RequestHeader(value = "X-Request-Id", required = false) String requestId,
        @RequestParam String studentId,
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
        // 已知冲突 -> OK 封套但 data 明确表示违规；仅未知 -> UNKNOWN 封套
        boolean unknownOnly = !result.hasKnownConflict() && result.hasUnknownParticipant();
        return wrap(requestId, result, unknownOnly, result.getReason());
    }

    private <T> Envelope<T> wrap(String requestId, T data, boolean unknown, String message) {
        return unknown
            ? Envelope.unknown(requestId, data, message)
            : Envelope.ok(requestId, data);
    }
}
