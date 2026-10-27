package com.coursepilot.verifier.web;

import com.fasterxml.jackson.annotation.JsonInclude;

import java.util.List;
import java.util.UUID;

@JsonInclude(JsonInclude.Include.ALWAYS)
public class Envelope<T> {

    private String schemaVersion = "1.0";
    private String requestId;
    // 契约（domain.schema.json 的 Envelope）要求 traceId 与 provenance 必填。
    private String traceId;
    private String status;          // OK / UNKNOWN / ERROR
    private T data;
    private List<SourceRef> provenance = List.of();
    private List<Issue> issues = List.of();

    public static <T> Envelope<T> ok(String requestId, T data) {
        Envelope<T> e = new Envelope<>();
        e.requestId = requestId != null ? requestId : UUID.randomUUID().toString();
        e.traceId = UUID.randomUUID().toString();
        e.status = "OK";
        e.data = data;
        return e;
    }

    public static <T> Envelope<T> unknown(String requestId, T data, String message) {
        Envelope<T> e = new Envelope<>();
        e.requestId = requestId != null ? requestId : UUID.randomUUID().toString();
        e.traceId = UUID.randomUUID().toString();
        e.status = "UNKNOWN";
        e.data = data;
        e.issues = List.of(new Issue("VERIFICATION_UNKNOWN", message, null, false));
        return e;
    }

    public static <T> Envelope<T> error(String requestId, String code,
                                        String message, String field, boolean retryable) {
        Envelope<T> e = new Envelope<>();
        e.requestId = requestId != null ? requestId : UUID.randomUUID().toString();
        e.traceId = UUID.randomUUID().toString();
        e.status = "ERROR";
        e.data = null;
        e.issues = List.of(new Issue(code, message, field, retryable));
        return e;
    }

    public String getSchemaVersion() { return schemaVersion; }
    public String getRequestId() { return requestId; }
    public String getTraceId() { return traceId; }
    public String getStatus() { return status; }
    public T getData() { return data; }
    public List<SourceRef> getProvenance() { return provenance; }
    public List<Issue> getIssues() { return issues; }

    public record Issue(String code, String message, String field, boolean retryable) {}

    /** contracts: SourceRef。当前还没有来源登记，先留空数组而不是省略字段。 */
    public record SourceRef(String kind, String refId, String snapshotId) {}
}
