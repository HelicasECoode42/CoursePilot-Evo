package com.coursepilot.verifier.web;

import com.coursepilot.verifier.application.AcademicRecordService;
import com.coursepilot.verifier.web.dto.RecordDtos;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/**
 * 学业记录三个端点（contracts: listAcademicRecords / getAcademicRecord / 写入）。
 * 归属一律由 X-Subject-Id 派生，不接受调用方自报 studentId。
 */
@RestController
@RequestMapping("/api/v1")
public class AcademicRecordController {

    private final SubjectGuard subjects;
    private final AcademicRecordService records;

    public AcademicRecordController(SubjectGuard subjects, AcademicRecordService records) {
        this.subjects = subjects;
        this.records = records;
    }

    /** data = { items: [...] }。主体没有记录时 items 为空数组，返回 200。 */
    @GetMapping("/academic-records")
    public Envelope<RecordDtos.RecordList> list(
        @RequestHeader(value = "X-Request-Id", required = false) String requestId,
        @RequestHeader(value = "X-Subject-Id", required = false) String subjectId) {
        String subject = subjects.require(subjectId);
        return Envelope.ok(requestId, new RecordDtos.RecordList(records.listFor(subject)));
    }

    /** 先判归属：不是本主体的记录一律 404，不回 403。 */
    @GetMapping("/academic-records/{recordId}")
    public Envelope<RecordDtos.AcademicRecord> record(
        @RequestHeader(value = "X-Request-Id", required = false) String requestId,
        @RequestHeader(value = "X-Subject-Id", required = false) String subjectId,
        @PathVariable String recordId) {
        String subject = subjects.require(subjectId);
        subjects.requireOwnRecord(subject, recordId);
        RecordDtos.AcademicRecord found = records.findFor(subject)
            .orElseThrow(() -> new AccessDenied("学业记录 " + recordId + " 不存在"));
        return Envelope.ok(requestId, found);
    }

    /**
     * 写入。Idempotency-Key 必填（缺失由 MissingRequestHeaderException 给 400）。
     * 成功返回 201 与契约 AcademicRecord；同键同内容的重复提交回放原答复。
     */
    @PostMapping("/academic-records")
    public ResponseEntity<Envelope<RecordDtos.AcademicRecord>> submit(
        @RequestHeader(value = "X-Request-Id", required = false) String requestId,
        @RequestHeader(value = "X-Subject-Id", required = false) String subjectId,
        @RequestHeader("Idempotency-Key") String idempotencyKey,
        @RequestBody RecordDtos.AcademicRecordInput body) {
        String subject = subjects.require(subjectId);
        RecordDtos.AcademicRecord created = records.submit(subject, idempotencyKey, body);
        return ResponseEntity.status(HttpStatus.CREATED).body(Envelope.ok(requestId, created));
    }
}
