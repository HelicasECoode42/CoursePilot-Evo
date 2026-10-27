package com.coursepilot.verifier.web;

import com.coursepilot.verifier.application.*;
import com.coursepilot.verifier.domain.AuditOutcome;
import com.coursepilot.verifier.domain.ConflictResult;
import com.coursepilot.verifier.persistence.entity.CompletedCourse;
import com.coursepilot.verifier.persistence.entity.Transcript;
import com.coursepilot.verifier.persistence.repo.TranscriptRepository;
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
    private final SubjectGuard subjects; // 远端的鉴权组件
    private final TranscriptRepository transcriptRepository; // 你的新功能组件

    public VerificationController(AuditEvaluator auditEvaluator,
                                  TimeParser timeParser,
                                  ConflictChecker conflictChecker,
                                  SubjectGuard subjects,
                                  TranscriptRepository transcriptRepository) {
        this.auditEvaluator = auditEvaluator;
        this.timeParser = timeParser;
        this.conflictChecker = conflictChecker;
        this.subjects = subjects;
        this.transcriptRepository = transcriptRepository;
    }

    @GetMapping("/credit-gap")
    public Envelope<AuditOutcome> creditGap(
        @RequestHeader(value = "X-Request-Id", required = false) String requestId,
        @RequestHeader(value = "X-Subject-Id", required = false) String subjectId,
        @RequestParam String planId) {
        // 使用远端的 SubjectGuard 获取安全的主体 ID
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
        boolean unknownOnly = !result.hasKnownConflict() && result.hasUnknownParticipant();
        return wrap(requestId, result, unknownOnly, result.getReason());
    }

    // === 下面是你本地新增的 validatePlan，融合了远端的 SubjectGuard ===
    @PostMapping("/plans/validate")
    public Envelope<PlanValidationDto.PlanValidationResult> validatePlan(
        @RequestHeader(value = "X-Request-Id", required = false) String requestId,
        @RequestHeader(value = "X-Subject-Id", required = false) String subjectId,
        @RequestBody PlanValidationDto.PlanValidationRequest request) {

        // 1. 先用远端的 Guard 验明正身
        String verifiedSubjectId = subjects.require(subjectId);

        if (request.snapshotId() == null || request.snapshotId().isBlank()) {
            return Envelope.unknown(requestId, new PlanValidationDto.PlanValidationResult("UNKNOWN", List.of(), List.of("缺少合格当期快照")), "缺少快照");
        }

        Transcript transcript = transcriptRepository.findByStudentId(verifiedSubjectId);
        if (transcript == null) return Envelope.unknown(requestId, new PlanValidationDto.PlanValidationResult("UNKNOWN", List.of(), List.of("无学业记录")), "无学业记录");

        List<String> earned = transcript.getCompletedCourses().stream().map(CompletedCourse::getCourseCode).toList();
        for (PlanValidationDto.PlanItem item : request.planItems()) {
            if (!earned.contains(item.courseCode())) {
                return Envelope.unknown(requestId, new PlanValidationDto.PlanValidationResult("UNKNOWN", List.of(), List.of("越权或未修课程: " + item.courseCode())), "越权拦截");
            }
        }

        List<PlanValidationDto.ConflictItem> conflicts = new ArrayList<>();
        List<String> unknowns = new ArrayList<>();
        List<com.coursepilot.verifier.domain.MeetingTime> parsedTimes = new ArrayList<>();

        for (PlanValidationDto.PlanItem item : request.planItems()) {
            TimeParser.ParseOutcome outcome = timeParser.parse(item.meetingTextRaw());
            if (!outcome.isOk()) unknowns.add("班次 " + item.classId() + " 时间未知：" + outcome.getReason());
            else parsedTimes.addAll(outcome.getMeetings());
        }

        for (int i = 0; i < parsedTimes.size(); i++) {
            for (int j = i + 1; j < parsedTimes.size(); j++) {
                if (parsedTimes.get(i).conflictsWith(parsedTimes.get(j))) {
                    conflicts.add(new PlanValidationDto.ConflictItem("未知", "未知", "时间冲突", "时间重叠"));
                }
            }
        }

        if (request.hardConstraints() != null && request.hardConstraints().contains("周五")) {
            for (com.coursepilot.verifier.domain.MeetingTime mt : parsedTimes) {
                if (mt.getDayOfWeek() == 5) conflicts.add(new PlanValidationDto.ConflictItem("未知", "硬约束", "HARD_CONSTRAINT", "占用周五"));
            }
        }

        if (!conflicts.isEmpty()) return Envelope.ok(requestId, new PlanValidationDto.PlanValidationResult("INVALID", conflicts, unknowns));
        if (!unknowns.isEmpty()) return Envelope.unknown(requestId, new PlanValidationDto.PlanValidationResult("UNKNOWN", conflicts, unknowns), "存在未知数据");
        return Envelope.ok(requestId, new PlanValidationDto.PlanValidationResult("VALID", List.of(), List.of()));
    }

    private <T> Envelope<T> wrap(String requestId, T data, boolean unknown, String message) {
        return unknown ? Envelope.unknown(requestId, data, message) : Envelope.ok(requestId, data);
    }
}
