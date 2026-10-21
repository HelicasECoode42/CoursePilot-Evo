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
    private final SubjectGuard subjects;

    public VerificationController(AuditEvaluator auditEvaluator,
                                  TimeParser timeParser,
                                  ConflictChecker conflictChecker,
                                  SubjectGuard subjects) {
        this.auditEvaluator = auditEvaluator;
        this.timeParser = timeParser;
        this.conflictChecker = conflictChecker;
        this.subjects = subjects;
    }

    /**
     * 本地排查用的缺口查询。这里**不再**接受 studentId 查询参数：原先谁都能
     * 传任意学号读别人的缺口，和 listAcademicRecords 是同一个越权面
     * （b-verifier.md B-F6）。主体一律取 X-Subject-Id。
     */
    @GetMapping("/credit-gap")
    public Envelope<AuditOutcome> creditGap(
        @RequestHeader(value = "X-Request-Id", required = false) String requestId,
        @RequestHeader(value = "X-Subject-Id", required = false) String subjectId,
        @RequestParam String planId) {
        AuditOutcome outcome = auditEvaluator.evaluate(subjects.require(subjectId), planId);
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
