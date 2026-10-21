package com.coursepilot.verifier.web;

import com.coursepilot.verifier.application.AuditResultAssembler;
import com.coursepilot.verifier.web.dto.AuditDtos;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 契约端点：POST /api/v1/requirements/audit（contracts/java.openapi.json）。
 *
 * C 模块的 ToolClient 按契约调用这个路径。原有的
 * GET /api/v1/verification/credit-gap 保留不动，它返回的是内部的 AuditOutcome，
 * 适合本地排查；对外一律以本端点为准。
 */
@RestController
@RequestMapping("/api/v1/requirements")
public class RequirementsController {

    private final AuditResultAssembler assembler;
    private final SubjectGuard subjects;

    public RequirementsController(AuditResultAssembler assembler, SubjectGuard subjects) {
        this.assembler = assembler;
        this.subjects = subjects;
    }

    @PostMapping("/audit")
    public Envelope<AuditDtos.AuditResult> audit(
        @RequestHeader(value = "X-Request-Id", required = false) String requestId,
        @RequestHeader(value = "X-Subject-Id", required = false) String subjectId,
        @RequestBody AuditDtos.AuditRequest request) {

        // 先判归属再核对：请求体里的 academicRecordId 必须属于当前主体，
        // 否则别人只要知道一个记录 ID 就能核对出对方的已修课程清单。
        subjects.requireOwnRecord(subjectId, request.academicRecordId());

        AuditDtos.AuditResult result =
            assembler.assemble(request.curriculumSnapshotId(), request.academicRecordId());

        // 契约：数据缺失是业务未知，不是查询失败。有未知项就用 UNKNOWN 封套，
        // 但 data 照常返回，消费方据此展示「无法确认」而不是报错。
        boolean hasUnknown = !result.unknowns().isEmpty()
            || result.requirements().stream()
                .anyMatch(item -> item.state() == AuditDtos.State.UNKNOWN);

        return hasUnknown
            ? Envelope.unknown(requestId, result, "存在无法确认的项，详见 unknowns")
            : Envelope.ok(requestId, result);
    }
}
