package com.coursepilot.verifier.application;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.coursepilot.verifier.persistence.entity.SchoolProgressSnapshot;
import com.coursepilot.verifier.persistence.entity.IdempotencyEntry;
import com.coursepilot.verifier.persistence.repo.IdempotencyEntryRepository;
import com.coursepilot.verifier.persistence.repo.SchoolProgressSnapshotRepository;
import com.coursepilot.verifier.web.InvalidRecordInput;
import com.coursepilot.verifier.web.AccessDenied;
import com.coursepilot.verifier.web.RecordConflict;
import com.coursepilot.verifier.web.dto.RecordDtos;
import com.coursepilot.verifier.web.dto.SchoolProgressDtos;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.HashSet;
import java.util.List;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Pattern;

/** Persists the source report and replaces the session transcript atomically. */
@Service
public class SchoolProgressService {
    private static final int MAX_NODES = 1000;
    private static final int MAX_COURSES = 1000;
    private static final Pattern ID = Pattern.compile("^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$");

    private final SchoolProgressSnapshotRepository snapshots;
    private final IdempotencyEntryRepository idempotency;
    private final AcademicRecordService records;
    private final ObjectMapper mapper;

    public SchoolProgressService(SchoolProgressSnapshotRepository snapshots,
                                 IdempotencyEntryRepository idempotency,
                                 AcademicRecordService records, ObjectMapper mapper) {
        this.snapshots = snapshots;
        this.idempotency = idempotency;
        this.records = records;
        this.mapper = mapper;
    }

    @Transactional
    public SchoolProgressDtos.ImportResult importSnapshot(String subjectId, String key,
            SchoolProgressDtos.ImportRequest input) {
        validate(input);
        String scopedKey = key == null ? null : "school-progress:" + hashText(key);
        String requestDigest = hashObject(input);
        if (scopedKey != null) {
            var priorRequest = idempotency.findByStudentIdAndIdemKey(subjectId, scopedKey);
            if (priorRequest.isPresent()) {
                if (!priorRequest.get().getRequestDigest().equals(requestDigest)) {
                    throw new RecordConflict("同一幂等键不能用于不同的学业进度内容");
                }
                return replay(priorRequest.get().getResponseJson());
            }
        }
        String contentHash = hash(input.curriculumSnapshotId(), input.snapshot());
        var previous = snapshots.findBySubjectIdAndContentHash(subjectId, contentHash);
        if (previous.isPresent()) {
            SchoolProgressDtos.ImportResult reused = result(previous.get(), true);
            saveIdempotency(subjectId, scopedKey, requestDigest, reused);
            return reused;
        }

        Map<String, RecordDtos.CompletedCourse> uniqueCourses = new LinkedHashMap<>();
        for (SchoolProgressDtos.Course course : input.snapshot().courses()) {
            if ("NOT_TAKEN".equals(course.outcome())) continue;
            RecordDtos.Outcome outcome = switch (course.outcome()) {
                case "PASSED" -> RecordDtos.Outcome.PASSED;
                case "FAILED" -> RecordDtos.Outcome.FAILED;
                case "IN_PROGRESS" -> RecordDtos.Outcome.IN_PROGRESS;
                default -> RecordDtos.Outcome.UNKNOWN;
            };
            String term = completedTerm(course);
            String keyForCourseAttempt = course.courseCode() + "\u0000" + (term == null ? "?" : term);
            Double earnedCredits = outcome == RecordDtos.Outcome.PASSED && course.credits() != null
                ? course.credits().doubleValue() : null;
            RecordDtos.CompletedCourse mapped = new RecordDtos.CompletedCourse(
                course.courseCode(), earnedCredits, outcome, term);
            RecordDtos.CompletedCourse prior = uniqueCourses.putIfAbsent(keyForCourseAttempt, mapped);
            if (prior != null && (!prior.outcome().equals(mapped.outcome())
                    || !java.util.Objects.equals(prior.earnedCredits(), mapped.earnedCredits()))) {
                uniqueCourses.put(keyForCourseAttempt, new RecordDtos.CompletedCourse(
                    course.courseCode(), null, RecordDtos.Outcome.UNKNOWN, term));
            }
        }
        var inputRecord = new RecordDtos.AcademicRecordInput("1.0", input.curriculumSnapshotId(),
            new ArrayList<>(uniqueCourses.values()), false, "USER_IMPORT");
        RecordDtos.AcademicRecord academicRecord = records.submit(subjectId,
            key == null ? null : "school-record:" + hashText(key), inputRecord);
        Instant importedAt = Instant.now();
        String snapshotJson = write(input.snapshot());
        String recordJson = write(academicRecord);
        SchoolProgressSnapshot saved = snapshots.saveAndFlush(new SchoolProgressSnapshot(UUID.randomUUID().toString(),
            subjectId, contentHash, importedAt, snapshotJson, recordJson));
        SchoolProgressDtos.ImportResult created = result(saved, false);
        saveIdempotency(subjectId, scopedKey, requestDigest, created);
        return created;
    }

    @Transactional(readOnly = true)
    public SchoolProgressDtos.ImportResult latest(String subjectId) {
        return snapshots.findFirstBySubjectIdOrderByImportedAtDesc(subjectId)
            .map(snapshot -> result(snapshot, true))
            .orElseThrow(() -> new AccessDenied("尚无已保存的学业进度"));
    }

    private void validate(SchoolProgressDtos.ImportRequest input) {
        if (input == null || !"1.0".equals(input.schemaVersion())
                || !validId(input.curriculumSnapshotId())) {
            throw new InvalidRecordInput("body", "学业进度请求格式不合法");
        }
        SchoolProgressDtos.Snapshot s = input.snapshot();
        if (s == null || !"coursepilot-shu-academic-progress".equals(s.format())
                || !Integer.valueOf(1).equals(s.version()) || s.capturedAt() == null
                || s.source() == null || s.source().isBlank() || s.source().length() > 200
                || s.nodes() == null || s.nodes().isEmpty() || s.nodes().size() > MAX_NODES
                || s.courses() == null || s.courses().size() > MAX_COURSES) {
            throw new InvalidRecordInput("snapshot", "学校学业进度结构不合法");
        }
        Set<String> ids = new HashSet<>();
        for (var node : s.nodes()) {
            if (node == null || !validId(node.nodeId()) || !ids.add(node.nodeId())
                    || node.name() == null || node.name().isBlank() || node.name().length() > 200
                    || node.leaf() == null || !validCredits(node.requiredCredits())
                    || !validCredits(node.earnedCredits()) || !validCredits(node.remainingCredits())) {
                throw new InvalidRecordInput("snapshot.nodes", "类别节点格式不合法或重复");
            }
        }
        for (var node : s.nodes()) {
            if (node.nodeId().equals(node.parentId())
                    || (node.parentId() != null && !ids.contains(node.parentId()))) {
                throw new InvalidRecordInput("snapshot.nodes.parentId", "父类别不存在");
            }
        }
        for (var course : s.courses()) {
            if (course == null || !ids.contains(course.nodeId()) || !validId(course.courseCode())
                    || course.name() == null || course.name().isBlank() || course.name().length() > 200
                    || !validCredits(course.credits()) || course.outcome() == null
                    || !Set.of("PASSED", "FAILED", "IN_PROGRESS", "NOT_TAKEN", "UNKNOWN").contains(course.outcome())) {
                throw new InvalidRecordInput("snapshot.courses", "课程明细格式不合法");
            }
        }
    }

    private static boolean validCredits(java.math.BigDecimal value) {
        return value == null || (value.signum() >= 0 && value.compareTo(new java.math.BigDecimal("1000")) <= 0
            && value.scale() <= 2);
    }

    private static boolean validId(String value) {
        return value != null && ID.matcher(value).matches();
    }

    private String hash(String curriculumSnapshotId, SchoolProgressDtos.Snapshot snapshot) {
        try {
            HashContent content = new HashContent(curriculumSnapshotId,
                new SnapshotHashContent(snapshot.format(), snapshot.version(), snapshot.source(),
                    snapshot.nodes(), snapshot.courses()));
            byte[] bytes = mapper.writeValueAsBytes(content);
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (JsonProcessingException | NoSuchAlgorithmException e) {
            throw new IllegalStateException("无法摘要学校学业快照", e);
        }
    }

    private String hashObject(Object value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                .digest(mapper.writeValueAsBytes(value)));
        } catch (JsonProcessingException | NoSuchAlgorithmException e) {
            throw new IllegalStateException("无法摘要学业导入请求", e);
        }
    }

    private void saveIdempotency(String subjectId, String key, String requestDigest,
                                 SchoolProgressDtos.ImportResult result) {
        if (key == null) return;
        idempotency.saveAndFlush(new IdempotencyEntry(subjectId, key, requestDigest,
            write(result), Instant.now()));
    }

    private SchoolProgressDtos.ImportResult replay(String value) {
        try { return mapper.readValue(value, SchoolProgressDtos.ImportResult.class); }
        catch (JsonProcessingException e) { throw new IllegalStateException("学业导入幂等记录无法读取", e); }
    }

    private record HashContent(String curriculumSnapshotId, SnapshotHashContent snapshot) {}
    private record SnapshotHashContent(String format, Integer version, String source,
                                       List<SchoolProgressDtos.Node> nodes,
                                       List<SchoolProgressDtos.Course> courses) {}

    private String write(Object value) {
        try { return mapper.writeValueAsString(value); }
        catch (JsonProcessingException e) { throw new IllegalStateException("无法保存学业快照", e); }
    }

    private SchoolProgressDtos.ImportResult result(SchoolProgressSnapshot entity, boolean reused) {
        try {
            var snapshot = mapper.readValue(entity.getSnapshotJson(), SchoolProgressDtos.Snapshot.class);
            var record = mapper.readValue(entity.getAcademicRecordJson(), RecordDtos.AcademicRecord.class);
            return new SchoolProgressDtos.ImportResult(new SchoolProgressDtos.Receipt(
                entity.getSchoolProgressId(), entity.getContentHash(), entity.getImportedAt(), reused),
                snapshot, record);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("已保存的学业快照无法读取", e);
        }
    }

    private static String completedTerm(SchoolProgressDtos.Course course) {
        if (course.completedYear() == null || course.completedTerm() == null) return null;
        String value = course.completedYear().trim() + ":" + course.completedTerm().trim();
        return validId(value) ? value : null;
    }

    private static String hashText(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                .digest(value.getBytes(java.nio.charset.StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("无法摘要幂等键", e);
        }
    }
}
