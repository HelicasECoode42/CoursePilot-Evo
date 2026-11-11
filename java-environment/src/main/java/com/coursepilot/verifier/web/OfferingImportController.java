package com.coursepilot.verifier.web;

import com.coursepilot.verifier.application.OfferingImportService;
import com.coursepilot.verifier.application.OfferingImportService.OfferingImportRejected;
import com.coursepilot.verifier.web.dto.ImportDtos;
import com.fasterxml.jackson.databind.JsonNode;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.List;
import java.util.regex.Pattern;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 契约端点 importOfferings：POST /api/v1/offering-snapshots/import。
 *
 * 鉴权顺序与培养方案导入一致：服务密钥（ServiceKeyFilter）→ 主体 → 管理员密钥 → 请求体。
 * SYNTHETIC 来源另需 coursepilot.import.synthetic.enabled=true，与培养方案的合成导入开关相同。
 * 成功返回 ImportResult（snapshotId / state / reused / issues）；失败统一为 Envelope 错误。
 */
@RestController
@RequestMapping("/api/v1/offering-snapshots")
public class OfferingImportController {
    private static final Pattern ID = Pattern.compile("^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$");

    private final OfferingImportService importer;
    private final SubjectGuard subjects;
    private final String adminKey;
    private final boolean syntheticImportEnabled;

    public OfferingImportController(
        OfferingImportService importer,
        SubjectGuard subjects,
        @Value("${coursepilot.admin-key:}") String adminKey,
        @Value("${coursepilot.import.synthetic.enabled:false}") boolean syntheticImportEnabled) {
        this.importer = importer;
        this.subjects = subjects;
        this.adminKey = adminKey == null ? "" : adminKey;
        this.syntheticImportEnabled = syntheticImportEnabled;
    }

    @PostMapping("/import")
    public ResponseEntity<Envelope<ImportDtos.ImportResult>> importOfferings(
        @RequestHeader("X-Request-Id") String requestId,
        @RequestHeader("X-Subject-Id") String subjectId,
        @RequestHeader(value = "X-Admin-Key", required = false) String presentedAdminKey,
        @RequestBody JsonNode body) {
        subjects.require(subjectId);
        if (!ID.matcher(requestId).matches()) {
            return error(HttpStatus.BAD_REQUEST, requestId, "INVALID_REQUEST_ID", "X-Request-Id 格式不合法", "X-Request-Id");
        }
        if (adminKey.isBlank()) {
            return error(HttpStatus.SERVICE_UNAVAILABLE, requestId, "ADMIN_KEY_NOT_CONFIGURED", "服务端未配置管理员密钥", null);
        }
        if (presentedAdminKey == null || !constantTimeEquals(adminKey, presentedAdminKey)) {
            return error(HttpStatus.UNAUTHORIZED, requestId, "ADMIN_KEY_INVALID", "缺少或错误的 X-Admin-Key", null);
        }
        try {
            OfferingImportService.Draft draft = importer.parse(body);
            if ("SYNTHETIC".equals(draft.sourceKind()) && !syntheticImportEnabled) {
                return error(HttpStatus.FORBIDDEN, requestId, "SYNTHETIC_IMPORT_DISABLED", "本地合成开课导入未启用", "sourceKind");
            }
            OfferingImportService.Result published = importer.publish(draft);
            List<Envelope.Issue> issues = published.issues().stream()
                .map(i -> new Envelope.Issue(i.code(), i.message(), i.field(), false))
                .toList();
            var result = new ImportDtos.ImportResult(published.snapshotId(), "PUBLISHED", published.reused(), issues);
            return ResponseEntity.ok(Envelope.ok(requestId, result));
        } catch (OfferingImportRejected ex) {
            HttpStatus status = switch (ex.kind()) {
                case SCHEMA -> HttpStatus.BAD_REQUEST;
                case SEMANTIC -> HttpStatus.UNPROCESSABLE_ENTITY;
                case CONFLICT -> HttpStatus.CONFLICT;
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
}
