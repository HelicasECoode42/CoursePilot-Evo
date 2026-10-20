package com.coursepilot.verifier.web;

import com.fasterxml.jackson.annotation.JsonInclude;

import java.util.List;
import java.util.UUID;

@JsonInclude(JsonInclude.Include.ALWAYS)
public class Envelope<T> {

    private String schemaVersion = "1.0";
    private String requestId;
    private String status;          // OK / UNKNOWN / ERROR
    private T data;
    private List<Issue> issues;

    public static <T> Envelope<T> ok(String requestId, T data) {
        Envelope<T> e = new Envelope<>();
        e.requestId = requestId != null ? requestId : UUID.randomUUID().toString();
        e.status = "OK";
        e.data = data;
        return e;
    }

    public static <T> Envelope<T> unknown(String requestId, T data, String message) {
        Envelope<T> e = new Envelope<>();
        e.requestId = requestId != null ? requestId : UUID.randomUUID().toString();
        e.status = "UNKNOWN";
        e.data = data;
        e.issues = List.of(new Issue("VERIFICATION_UNKNOWN", message, null, false));
        return e;
    }

    public static <T> Envelope<T> error(String requestId, String code,
                                        String message, String field, boolean retryable) {
        Envelope<T> e = new Envelope<>();
        e.requestId = requestId != null ? requestId : UUID.randomUUID().toString();
        e.status = "ERROR";
        e.data = null;
        e.issues = List.of(new Issue(code, message, field, retryable));
        return e;
    }

    public String getSchemaVersion() { return schemaVersion; }
    public String getRequestId() { return requestId; }
    public String getStatus() { return status; }
    public T getData() { return data; }
    public List<Issue> getIssues() { return issues; }

    public record Issue(String code, String message, String field, boolean retryable) {}
}
