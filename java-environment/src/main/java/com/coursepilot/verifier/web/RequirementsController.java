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

    public RequirementsController(AuditResultAssembler assembler) {
        this.assembler = assembler;
    }

    @PostMapping("/audit")
    public Envelope<AuditDtos.AuditResult> audit(
        @RequestHeader(value = "X-Request-Id", required = false) String requestId,
        @RequestBody AuditDtos.AuditRequest request) {

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
