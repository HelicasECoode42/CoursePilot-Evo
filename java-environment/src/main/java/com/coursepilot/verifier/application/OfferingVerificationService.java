package com.coursepilot.verifier.application;

import com.coursepilot.verifier.persistence.entity.CurriculumSnapshot;
import com.coursepilot.verifier.persistence.entity.OfferingVerificationAudit;
import com.coursepilot.verifier.persistence.repo.CurriculumSnapshotRepository;
import com.coursepilot.verifier.persistence.repo.OfferingVerificationAuditRepository;
import com.fasterxml.jackson.databind.JsonNode;
import java.time.Clock;
import java.time.Instant;
import java.util.Locale;
import java.util.Set;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 开课快照的人工抽样核验（契约 verifyOfferingSnapshot）。
 *
 * 规则（AGENTS.md：上传者标签不能自动 VERIFIED，核验是另一步的独立结论）：
 * 1. 只接受 OFFERING 快照；SYNTHETIC 快照不可核验（422）。
 * 2. 核验人与上传人相同（忽略大小写与空白）→ 422，不写记录。
 * 3. 错误数不得超过样本数（422）；样本数至少 30（契约 minimum，违反为 400）。
 * 4. errorCount / sampleSize ≤ 2% 为 VERIFIED，否则为 REJECTED。判定用整数乘法：errorCount × 50 ≤ sampleSize。
 * 5. 无论结论如何都写一条审计记录；快照的 sourceValidation 以最近一次结论为准。
 *
 * 不做的事：不核验班次内容本身，不校验样本文件内容（只保存其 SHA-256 作为指纹）。
 */
@Service
public class OfferingVerificationService {

    public static final int MIN_SAMPLE = 30;
    public static final int MAX_SAMPLE = 100000;
    public static final int MAX_NOTE = 500;
    private static final Set<String> FIELDS =
        Set.of("schemaVersion", "verifierName", "uploaderName", "sampleSize", "errorCount", "sampleFileSha256", "note");
    private static final Set<String> REQUIRED =
        Set.of("schemaVersion", "verifierName", "uploaderName", "sampleSize", "errorCount", "sampleFileSha256");

    private final CurriculumSnapshotRepository snapshots;
    private final OfferingVerificationAuditRepository audits;
    private final Clock clock;

    public OfferingVerificationService(CurriculumSnapshotRepository snapshots,
                                       OfferingVerificationAuditRepository audits) {
        this.snapshots = snapshots;
        this.audits = audits;
        this.clock = Clock.systemUTC();
    }

    /** 解析请求体。结构不合法抛 Rejected(SCHEMA)，语义不合法在 verify 中抛 SEMANTIC。 */
    public Request parse(JsonNode body) {
        if (body == null || !body.isObject()) throw schema("body", "请求体必须是对象");
        var names = body.fieldNames();
        while (names.hasNext()) {
            String name = names.next();
            if (!FIELDS.contains(name)) throw schema(name, "包含契约未声明的字段");
        }
        for (String required : REQUIRED) {
            if (!body.has(required)) throw schema(required, "缺少必填字段");
        }
        JsonNode version = body.get("schemaVersion");
        if (!version.isTextual() || !"1.0".equals(version.asText())) throw schema("schemaVersion", "schemaVersion 必须为 1.0");
        String verifier = text(body, "verifierName", 120);
        String uploader = text(body, "uploaderName", 120);
        int sampleSize = integer(body.get("sampleSize"), MIN_SAMPLE, MAX_SAMPLE, "sampleSize");
        int errorCount = integer(body.get("errorCount"), 0, MAX_SAMPLE, "errorCount");
        String sha = body.get("sampleFileSha256").isTextual() ? body.get("sampleFileSha256").asText() : null;
        if (sha == null || !sha.matches("^[a-f0-9]{64}$")) throw schema("sampleFileSha256", "必须是 64 位小写十六进制 SHA-256");
        String note = null;
        JsonNode noteNode = body.get("note");
        if (noteNode != null && !noteNode.isNull()) {
            if (!noteNode.isTextual() || noteNode.asText().length() > MAX_NOTE) throw schema("note", "note 必须是不超过 500 字符的字符串或 null");
            note = noteNode.asText();
        }
        return new Request(verifier, uploader, sampleSize, errorCount, sha, note);
    }

    @Transactional
    public Result verify(String snapshotId, Request req, String requestId) {
        CurriculumSnapshot snapshot = snapshots.findById(snapshotId)
            .filter(s -> s.getKind() == CurriculumSnapshot.Kind.OFFERING)
            .orElseThrow(() -> new OfferingVerificationRejected(OfferingVerificationRejected.Kind.NOT_FOUND,
                "SNAPSHOT_NOT_FOUND", "开课快照不存在", "snapshotId"));
        if (snapshot.getSourceKind() == CurriculumSnapshot.SourceKind.SYNTHETIC
            || snapshot.getSourceValidation() == CurriculumSnapshot.SourceValidation.SYNTHETIC) {
            throw new OfferingVerificationRejected(OfferingVerificationRejected.Kind.SEMANTIC,
                "SYNTHETIC_NOT_VERIFIABLE", "模拟快照不可核验", "snapshotId");
        }
        if (normalizePerson(req.verifierName()).equals(normalizePerson(req.uploaderName()))) {
            throw new OfferingVerificationRejected(OfferingVerificationRejected.Kind.SEMANTIC,
                "VERIFIER_IS_UPLOADER", "核验人不能与上传人相同", "verifierName");
        }
        if (req.errorCount() > req.sampleSize()) {
            throw new OfferingVerificationRejected(OfferingVerificationRejected.Kind.SEMANTIC,
                "ERROR_COUNT_EXCEEDS_SAMPLE", "错误数不能超过样本数", "errorCount");
        }

        boolean passed = (long) req.errorCount() * 50L <= req.sampleSize();   // 错误率 <= 2%
        String outcome = passed ? "VERIFIED" : "REJECTED";
        Instant now = clock.instant();
        String verificationId = "OVR_" + UUID.randomUUID().toString().replace("-", "");

        audits.save(new OfferingVerificationAudit(verificationId, snapshotId, req.verifierName(),
            req.uploaderName(), req.sampleSize(), req.errorCount(), req.sampleFileSha256(), outcome,
            req.note(), requestId, now));
        snapshot.applyVerification(passed);
        snapshots.save(snapshot);

        return new Result(snapshotId, verificationId, outcome, snapshot.getSourceValidation().name(),
            req.sampleSize(), req.errorCount(), now);
    }

    static String normalizePerson(String name) {
        return name.replaceAll("\\s+", "").toLowerCase(Locale.ROOT);
    }

    // ------------------------------------------------------------ 小工具

    private static String text(JsonNode node, String field, int max) {
        JsonNode v = node.get(field);
        if (v == null || !v.isTextual() || v.asText().isBlank() || v.asText().length() > max) {
            throw schema(field, field + " 必须是 1 到 " + max + " 字符的非空字符串");
        }
        return v.asText();
    }

    private static int integer(JsonNode v, int min, int max, String field) {
        if (v == null || !v.isIntegralNumber() || !v.canConvertToInt() || v.asInt() < min || v.asInt() > max) {
            throw schema(field, field + " 必须是 " + min + " 到 " + max + " 之间的整数");
        }
        return v.asInt();
    }

    private static OfferingVerificationRejected schema(String field, String message) {
        return new OfferingVerificationRejected(OfferingVerificationRejected.Kind.SCHEMA, "INVALID_INPUT", message, field);
    }

    public record Request(String verifierName, String uploaderName, int sampleSize, int errorCount,
                          String sampleFileSha256, String note) {}

    public record Result(String snapshotId, String verificationId, String outcome, String sourceValidation,
                         int sampleSize, int errorCount, Instant verifiedAt) {}

    public static final class OfferingVerificationRejected extends RuntimeException {
        public enum Kind { SCHEMA, SEMANTIC, NOT_FOUND }

        private final Kind kind;
        private final String code;
        private final String field;

        public OfferingVerificationRejected(Kind kind, String code, String message, String field) {
            super(message);
            this.kind = kind;
            this.code = code;
            this.field = field;
        }

        public Kind kind() { return kind; }
        public String code() { return code; }
        public String field() { return field; }
    }
}
