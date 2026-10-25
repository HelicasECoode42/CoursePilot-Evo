package com.coursepilot.verifier.web.dto;

import java.math.BigDecimal;
import java.util.List;

public class AuditDto {
    public record AuditRequest(String studentId, String planId) {}

    public record AuditResult(String status, List<AuditItem> items, List<String> unknowns) {}

    public record AuditItem(String category, BigDecimal required, BigDecimal earned, BigDecimal gap, String state) {}
}
