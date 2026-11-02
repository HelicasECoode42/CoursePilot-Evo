package com.coursepilot.verifier.application;

import com.coursepilot.verifier.persistence.entity.Transcript;
import com.coursepilot.verifier.persistence.entity.TranscriptCourse;
import com.coursepilot.verifier.web.dto.RecordDtos;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;

/** 实体、契约 DTO、请求摘要之间的转换。只做形状转换，不做业务判断。 */
final class AcademicRecordMapper {

    private AcademicRecordMapper() {}

    static RecordDtos.AcademicRecord toDto(Transcript t) {
        List<RecordDtos.CompletedCourse> courses = t.getCompletedCourses().stream()
            .map(c -> new RecordDtos.CompletedCourse(
                c.getCourseCode(),
                c.getEarnedCredits() == null ? null : c.getEarnedCredits().doubleValue(),
                RecordDtos.Outcome.valueOf(c.getOutcome().name()),
                c.getCompletedTerm()))
            .toList();
        return new RecordDtos.AcademicRecord(
            t.getAcademicRecordId(),
            t.getRevision(),
            t.getCurriculumSnapshotId(),
            courses,
            t.isTranscriptComplete(),
            t.getSourceKind().name(),
            t.getCreatedAt().toString());
    }

    /**
     * 输入的已修课程转实体。attemptNo 由服务端按出现顺序给：同一 courseCode
     * 第 n 次出现即第 n 次修读。契约输入里没有 attemptNo，不信任客户端自报。
     */
    static List<TranscriptCourse> toCourses(List<RecordDtos.CompletedCourse> input) {
        Map<String, Integer> seen = new HashMap<>();
        List<TranscriptCourse> out = new ArrayList<>(input.size());
        for (RecordDtos.CompletedCourse c : input) {
            int attempt = seen.merge(c.courseCode(), 1, Integer::sum);
            BigDecimal credits = c.earnedCredits() == null
                ? null : BigDecimal.valueOf(c.earnedCredits()).setScale(2);
            out.add(new TranscriptCourse(c.courseCode(), attempt, credits,
                TranscriptCourse.Outcome.valueOf(c.outcome().name()), c.completedTerm()));
        }
        return out;
    }

    /** 规范化请求内容的 SHA-256。字段顺序固定，缺省值用 "-"（契约的 pattern 不允许以 "-" 开头，不会冲突）。 */
    static String digest(RecordDtos.AcademicRecordInput in) {
        StringBuilder sb = new StringBuilder();
        sb.append(in.schemaVersion()).append('\n')
          .append(in.curriculumSnapshotId()).append('\n')
          .append(in.transcriptComplete()).append('\n')
          .append(in.sourceKind()).append('\n');
        for (RecordDtos.CompletedCourse c : in.completedCourses()) {
            sb.append(c.courseCode()).append('|')
              .append(c.earnedCredits() == null ? "-"
                  : BigDecimal.valueOf(c.earnedCredits()).stripTrailingZeros().toPlainString()).append('|')
              .append(c.outcome()).append('|')
              .append(c.completedTerm() == null ? "-" : c.completedTerm()).append('\n');
        }
        try {
            byte[] hash = MessageDigest.getInstance("SHA-256")
                .digest(sb.toString().getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(hash);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("JVM 缺少 SHA-256", e);
        }
    }
}
