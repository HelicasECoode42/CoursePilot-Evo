package com.coursepilot.verifier.web;

import com.coursepilot.verifier.application.AuditResultAssembler;
import com.coursepilot.verifier.web.dto.AuditDtos;
import com.coursepilot.verifier.persistence.entity.Transcript;
import com.coursepilot.verifier.persistence.repo.TranscriptRepository;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/requirements")
public class RequirementsController {

    private final SubjectGuard subjects;
    private final TranscriptRepository transcriptRepository;
    private final AuditResultAssembler assembler; // 引入远端要求的组装器

    public RequirementsController(SubjectGuard subjects, TranscriptRepository transcriptRepository, AuditResultAssembler assembler) {
        this.subjects = subjects;
        this.transcriptRepository = transcriptRepository;
        this.assembler = assembler;
    }

    @PostMapping("/audit")
    public Envelope<AuditDtos.AuditResult> audit(
        @RequestHeader(value = "X-Request-Id", required = false) String requestId,
        @RequestHeader(value = "X-Subject-Id", required = false) String subjectId,
        @RequestBody AuditDtos.AuditRequest request) {

        // 1. 鉴权拦截
        String verifiedSubjectId = subjects.require(subjectId);

        // 2. 对象级授权：校验记录是否属于当前学生
        if (request.academicRecordId() != null) {
            Transcript t = transcriptRepository.findByStudentId(verifiedSubjectId);
            if (t == null || !t.getAcademicRecordId().equals(request.academicRecordId())) {
                return Envelope.unknown(requestId, new AuditDtos.AuditResult("", "", 0, false, null, null, null), "越权拦截");
            }
        }

        // 3. 调用组长的核心算法
        AuditDtos.AuditResult result = assembler.assemble(request.planId(), request.academicRecordId());

        return Envelope.ok(requestId, result);
    }
}
