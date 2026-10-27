package com.coursepilot.verifier.web;

import com.coursepilot.verifier.application.*;
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

    private final TimeParser timeParser;
    private final ConflictChecker conflictChecker;
    private final TranscriptRepository transcriptRepository;

    public VerificationController(TimeParser timeParser, ConflictChecker conflictChecker, TranscriptRepository transcriptRepository) {
        this.timeParser = timeParser;
        this.conflictChecker = conflictChecker;
        this.transcriptRepository = transcriptRepository;
    }

    @PostMapping("/parse-time")
    public Envelope<TimeParser.ParseOutcome> parseTime(@RequestHeader(value = "X-Request-Id", required = false) String requestId,
                                                       @RequestBody Map<String, String> body) {
        TimeParser.ParseOutcome outcome = timeParser.parse(body.get("meetingTextRaw"));
        return outcome.isOk() ? Envelope.ok(requestId, outcome) : Envelope.unknown(requestId, outcome, outcome.getReason());
    }

    @PostMapping("/conflicts")
    public Envelope<ConflictResult> conflicts(@RequestHeader(value = "X-Request-Id", required = false) String requestId,
                                              @RequestBody List<String> offeringIds) {
        ConflictResult result = conflictChecker.check(offeringIds);
        boolean unknownOnly = !result.hasKnownConflict() && result.hasUnknownParticipant();
        return unknownOnly ? Envelope.unknown(requestId, result, result.getReason()) : Envelope.ok(requestId, result);
    }

    @PostMapping("/plans/validate")
    public Envelope<PlanValidationDto.PlanValidationResult> validatePlan(
        @RequestHeader(value = "X-Request-Id", required = false) String requestId,
        @RequestHeader("X-Subject-Id") String subjectId,
        @RequestBody PlanValidationDto.PlanValidationRequest request) {

        if (request.snapshotId() == null || request.snapshotId().isBlank()) {
            return Envelope.unknown(requestId, new PlanValidationDto.PlanValidationResult("UNKNOWN", List.of(), List.of("缺少合格当期快照")), "缺少快照");
        }

        Transcript transcript = transcriptRepository.findByStudentId(subjectId);
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
}
