package com.coursepilot.verifier.web;

import com.coursepilot.verifier.web.dto.AuditDto;
import org.springframework.web.bind.annotation.*;
import java.math.BigDecimal;
import java.util.List;

@RestController
@RequestMapping("/api/v1/requirements")
public class RequirementsController {

    @PostMapping("/audit")
    public Envelope<AuditDto.AuditResult> audit(
        @RequestHeader(value = "X-Request-Id", required = false) String requestId,
        @RequestBody AuditDto.AuditRequest request) {

        // 组长要求：先把形状立起来，state 全返回 UNKNOWN，写明原因
        AuditDto.AuditItem item = new AuditDto.AuditItem(
            "必修", new BigDecimal("10.0"), BigDecimal.ZERO, new BigDecimal("10.0"), "UNKNOWN"
        );

        AuditDto.AuditResult result = new AuditDto.AuditResult(
            "UNKNOWN",
            List.of(item),
            List.of("当前未接入真实学业记录数据源，无法进行学分核算")
        );

        return Envelope.ok(requestId, result);
    }
}
