package com.coursepilot.verifier.web;

import com.coursepilot.verifier.application.SchoolProgressService;
import com.coursepilot.verifier.web.dto.SchoolProgressDtos;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/school-progress")
public class SchoolProgressController {
    private final SubjectGuard subjects;
    private final SchoolProgressService progress;

    public SchoolProgressController(SubjectGuard subjects, SchoolProgressService progress) {
        this.subjects = subjects;
        this.progress = progress;
    }

    @PutMapping
    public ResponseEntity<Envelope<SchoolProgressDtos.ImportResult>> save(
            @RequestHeader(value = "X-Request-Id", required = false) String requestId,
            @RequestHeader(value = "X-Subject-Id", required = false) String subjectId,
            @RequestHeader(value = "Idempotency-Key") String idempotencyKey,
            @RequestBody SchoolProgressDtos.ImportRequest body) {
        String subject = subjects.require(subjectId);
        var result = progress.importSnapshot(subject, idempotencyKey, body);
        return ResponseEntity.status(HttpStatus.OK).body(Envelope.ok(requestId, result));
    }

    @GetMapping
    public Envelope<SchoolProgressDtos.ImportResult> read(
            @RequestHeader(value = "X-Request-Id", required = false) String requestId,
            @RequestHeader(value = "X-Subject-Id", required = false) String subjectId) {
        return Envelope.ok(requestId, progress.latest(subjects.require(subjectId)));
    }
}
