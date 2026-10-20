package com.coursepilot.verifier.domain;

import java.util.List;

public class AuditOutcome {

    public enum Status { PASS, FAIL, UNKNOWN }

    private final Status status;
    private final List<String> reasons;

    public AuditOutcome(Status status, List<String> reasons) {
        this.status = status;
        this.reasons = reasons;
    }

    public Status getStatus() { return status; }
    public List<String> getReasons() { return reasons; }
}
