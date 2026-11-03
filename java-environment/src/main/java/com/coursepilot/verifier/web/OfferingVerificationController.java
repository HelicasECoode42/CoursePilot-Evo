package com.coursepilot.verifier.web;

import com.coursepilot.verifier.application.OfferingVerificationService;
import com.coursepilot.verifier.application.OfferingVerificationService.OfferingVerificationRejected;
import com.fasterxml.jackson.databind.JsonNode;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.regex.Pattern;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 契约端点 verifyOfferingSnapshot：POST /api/v1/offering-snapshots/{snapshotId}/verification。
 *
 * 鉴权顺序与导入一致：服务密钥（ServiceKeyFilter）→ 主体 → 请求号 → 管理员密钥 → 请求体。
 * 成功（含 REJECTED 结论）返回 200 与 OfferingVerificationResult；业务拒绝返回 Envelope 错误。
 */
@RestController
@RequestMapping("/api/v1/offering-snapshots")
public class OfferingVerificationController {
    private static final Pattern ID = Pattern.compile("^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$");

    private final OfferingVerificationService verifier;
    private final SubjectGuard subjects;
    private final String adminKey;

    public OfferingVerificationController(
        OfferingVerificationService verifier,
        SubjectGuard subjects,
        @Value("${coursepilot.admin-key:}") String adminKey) {
        this.verifier = verifier;
        this.subjects = subjects;
        this.adminKey = adminKey == null ? "" : adminKey;
    }

    @PostMapping("/{snapshotId}/verification")
    public ResponseEntity<Envelope<VerificationView>> verify(
        @PathVariable("snapshotId") String snapshotId,
        @RequestHeader("X-Request-Id") String requestId,
        @RequestHeader("X-Subject-Id") String subjectId,
        @RequestHeader(value = "X-Admin-Key", required = false) String presentedAdminKey,
        @RequestBody JsonNode body) {
        subjects.require(subjectId);
        if (!ID.matcher(requestId).matches()) {
            return error(HttpStatus.BAD_REQUEST, requestId, "INVALID_REQUEST_ID", "X-Request-Id 格式不合法", "X-Request-Id");
        }
        if (!ID.matcher(snapshotId).matches()) {
            return error(HttpStatus.BAD_REQUEST, requestId, "INVALID_INPUT", "snapshotId 格式不合法", "snapshotId");
        }
        if (adminKey.isBlank()) {
            return error(HttpStatus.SERVICE_UNAVAILABLE, requestId, "ADMIN_KEY_NOT_CONFIGURED", "服务端未配置管理员密钥", null);
        }
        if (presentedAdminKey == null || !constantTimeEquals(adminKey, presentedAdminKey)) {
            return error(HttpStatus.UNAUTHORIZED, requestId, "ADMIN_KEY_INVALID", "缺少或错误的 X-Admin-Key", null);
        }
        try {
            OfferingVerificationService.Request req = verifier.parse(body);
            var result = verifier.verify(snapshotId, req, requestId);
            return ResponseEntity.ok(Envelope.ok(requestId, new VerificationView(
                result.snapshotId(), result.verificationId(), result.outcome(), result.sourceValidation(),
                result.sampleSize(), result.errorCount(), result.verifiedAt().toString())));
        } catch (OfferingVerificationRejected ex) {
            HttpStatus status = switch (ex.kind()) {
                case SCHEMA -> HttpStatus.BAD_REQUEST;
                case SEMANTIC -> HttpStatus.UNPROCESSABLE_ENTITY;
                case NOT_FOUND -> HttpStatus.NOT_FOUND;
            };
            return error(status, requestId, ex.code(), ex.getMessage(), ex.field());
        }
    }

    private static boolean constantTimeEquals(String expected, String presented) {
        return MessageDigest.isEqual(
            expected.getBytes(StandardCharsets.UTF_8), presented.getBytes(StandardCharsets.UTF_8));
    }

    private static <T> ResponseEntity<Envelope<T>> error(
        HttpStatus status, String requestId, String code, String message, String field) {
        return ResponseEntity.status(status).body(Envelope.error(requestId, code, message, field, false));
    }

    /** 契约 OfferingVerificationResult。 */
    public record VerificationView(String snapshotId, String verificationId, String outcome,
                                   String sourceValidation, int sampleSize, int errorCount, String verifiedAt) {}
}
