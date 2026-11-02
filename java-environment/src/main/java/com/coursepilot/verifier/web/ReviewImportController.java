package com.coursepilot.verifier.web;

import com.coursepilot.verifier.persistence.entity.ReviewNote;
import com.coursepilot.verifier.persistence.repo.ReviewNoteRepository;
import com.fasterxml.jackson.databind.JsonNode;
import jakarta.transaction.Transactional;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.regex.Pattern;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/reviews")
public class ReviewImportController {
    private static final Pattern ID = Pattern.compile("^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$");
    private static final Set<String> FIELDS = Set.of("reviewNoteId", "courseCode", "teacherKey", "termId", "sourceKind", "publishedAt", "sourceUrl", "excerpt", "dimensions", "matchStatus", "sourceRefId");
    private static final Set<String> IMPORT_FIELDS = Set.of("teacherDisplayName");
    private final ReviewNoteRepository repository;
    private final SubjectGuard subjects;
    private final String adminKey;

    public ReviewImportController(ReviewNoteRepository repository, SubjectGuard subjects,
                                  @Value("${coursepilot.admin-key:}") String adminKey) {
        this.repository = repository;
        this.subjects = subjects;
        this.adminKey = adminKey;
    }

    @PostMapping("/import")
    @Transactional
    public ResponseEntity<Envelope<?>> importReviews(@RequestHeader("X-Request-Id") String requestId,
        @RequestHeader("X-Subject-Id") String subjectId,
        @RequestHeader(value = "X-Admin-Key", required = false) String presentedKey,
        @RequestBody JsonNode body) {
        subjects.require(subjectId);
        if (adminKey == null || adminKey.isBlank() || presentedKey == null ||
            !MessageDigest.isEqual(adminKey.getBytes(StandardCharsets.UTF_8), presentedKey.getBytes(StandardCharsets.UTF_8))) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body(Envelope.error(requestId, "ADMIN_KEY_INVALID", "管理员密钥缺失或无效", null, false));
        }
        try {
            if (!ID.matcher(requestId).matches() || !body.isObject() || body.size() != 2 ||
                !"1.0".equals(body.path("schemaVersion").asText()) || !body.path("notes").isArray() ||
                body.path("notes").size() < 1 || body.path("notes").size() > 200) throw new IllegalArgumentException();
            List<ReviewNote> records = new ArrayList<>();
            Set<String> ids = new HashSet<>();
            for (JsonNode n : body.path("notes")) {
                if (!n.isObject() || (n.size() != FIELDS.size() && n.size() != FIELDS.size() + 1)) throw new IllegalArgumentException();
                for (String field : FIELDS) if (!n.has(field)) throw new IllegalArgumentException();
                var fieldNames = n.fieldNames();
                while (fieldNames.hasNext()) {
                    String field = fieldNames.next();
                    if (!FIELDS.contains(field) && !IMPORT_FIELDS.contains(field)) throw new IllegalArgumentException();
                }
                String id = id(n, "reviewNoteId", false), course = id(n, "courseCode", false);
                String teacher = id(n, "teacherKey", true), term = id(n, "termId", true), sourceRef = id(n, "sourceRefId", false);
                if (!ids.add(id) || !n.path("excerpt").isTextual() || n.path("excerpt").asText().isEmpty() || n.path("excerpt").asText().length() > 1500) throw new IllegalArgumentException();
                ReviewNote.SourceKind kind = ReviewNote.SourceKind.valueOf(n.path("sourceKind").asText());
                String match = n.path("matchStatus").asText();
                if (!Set.of("COURSE_ONLY", "UNVERIFIED", "COURSE_TEACHER_MATCHED").contains(match)) throw new IllegalArgumentException();
                if ("COURSE_TEACHER_MATCHED".equals(match) && teacher == null) throw new IllegalArgumentException();
                Instant published = n.get("publishedAt").isNull() ? null : Instant.parse(n.get("publishedAt").asText());
                String url = n.get("sourceUrl").isNull() ? null : n.get("sourceUrl").asText();
                if (url != null) {
                    URI source = URI.create(url);
                    if (url.length() > 1000 || source.getHost() == null ||
                        !Set.of("http", "https").contains(source.getScheme())) throw new IllegalArgumentException();
                }
                if (!n.path("dimensions").isArray() || n.path("dimensions").size() > 8) throw new IllegalArgumentException();
                List<ReviewNote.Dimension> dimensions = new ArrayList<>();
                for (JsonNode dimension : n.path("dimensions")) dimensions.add(ReviewNote.Dimension.valueOf(dimension.asText()));
                ReviewNote note = new ReviewNote(id, course, teacher, term, kind, published, url, n.path("excerpt").asText(), dimensions);
                note.setImportProvenance(sourceRef, match);
                JsonNode displayName = n.get("teacherDisplayName");
                if (displayName != null && !displayName.isNull()) {
                    if (!displayName.isTextual() || displayName.asText().isBlank() || displayName.asText().length() > 120) throw new IllegalArgumentException();
                    note.setTeacherDisplayName(displayName.asText());
                }
                records.add(note);
            }
            repository.saveAll(records);
            return ResponseEntity.status(HttpStatus.CREATED).body(Envelope.ok(requestId, new ImportResult(records.size())));
        } catch (IllegalArgumentException ex) {
            return ResponseEntity.badRequest().body(Envelope.error(requestId, "INVALID_REVIEW_IMPORT", "评价导入格式不合法", null, false));
        }
    }
    private static String id(JsonNode node, String field, boolean nullable) {
        JsonNode value = node.get(field);
        if (nullable && value.isNull()) return null;
        if (!value.isTextual() || !ID.matcher(value.asText()).matches()) throw new IllegalArgumentException();
        return value.asText();
    }
    public record ImportResult(int importedCount) {}
}
