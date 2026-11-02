package com.coursepilot.verifier.web;

import com.coursepilot.verifier.application.TeacherReviewAssembler;
import com.coursepilot.verifier.web.dto.TeacherReviewDtos;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.regex.Pattern;

/**
 * 契约端点：listTeacherCourseOptions 与 searchReviews（contracts/java.openapi.json）。
 *
 * 参数格式和范围在这里校验（不合法 400 INVALID_QUERY）。归属由 X-Subject-Id 经 SubjectGuard 确认，
 * 调用方的服务密钥由 ServiceKeyFilter 确认，两道都不在这里重复实现。
 */
@RestController
@RequestMapping("/api/v1")
public class TeacherReviewController {

    /** 契约 ^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$，最长 120。 */
    private static final Pattern ID = Pattern.compile("^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$");
    /** 游标是十进制偏移量，限定位数防止溢出。 */
    private static final Pattern OFFSET_CURSOR = Pattern.compile("^[0-9]{1,9}$");

    private static final int OPTION_DEFAULT_LIMIT = 20;
    private static final int OPTION_MAX_LIMIT = 100;
    private static final int REVIEW_DEFAULT_LIMIT = 5;
    private static final int REVIEW_MAX_LIMIT = 10;
    private static final int QUERY_MAX_LENGTH = 200;

    private final TeacherReviewAssembler assembler;
    private final SubjectGuard subjects;

    public TeacherReviewController(TeacherReviewAssembler assembler, SubjectGuard subjects) {
        this.assembler = assembler;
        this.subjects = subjects;
    }

    @GetMapping("/teacher-course-options")
    public Envelope<TeacherReviewDtos.TeacherCourseOptionList> teacherCourseOptions(
        @RequestHeader(value = "X-Request-Id", required = false) String requestId,
        @RequestHeader(value = "X-Subject-Id", required = false) String subjectId,
        @RequestParam String curriculumSnapshotId,
        @RequestParam(required = false) String courseCode,
        @RequestParam(required = false) String query,
        @RequestParam(required = false) Integer limit,
        @RequestParam(required = false) String cursor) {
        subjects.require(subjectId);

        requireId("curriculumSnapshotId", curriculumSnapshotId);
        requireOptionalId("courseCode", courseCode);
        if (query != null && (query.isEmpty() || query.length() > QUERY_MAX_LENGTH)) {
            throw new InvalidQuery("query", "query 长度须在 1 到 " + QUERY_MAX_LENGTH + " 之间");
        }
        int size = limitOrDefault("limit", limit, OPTION_DEFAULT_LIMIT, OPTION_MAX_LIMIT);
        int offset = offsetOf(cursor);

        TeacherReviewDtos.TeacherCourseOptionList result =
            assembler.listOptions(curriculumSnapshotId, courseCode, query, size, offset);

        // 与 requirements/audit 一致：有业务未知项时用 UNKNOWN 封套，data 照常返回。
        boolean hasUnknown = result.items().stream()
            .anyMatch(i -> i.availability() == TeacherReviewDtos.Availability.UNKNOWN);
        return hasUnknown
            ? Envelope.unknown(requestId, result, "存在无法判断开课状态的教师，详见 availability")
            : Envelope.ok(requestId, result);
    }

    @GetMapping("/reviews/search")
    public Envelope<TeacherReviewDtos.ReviewNoteList> searchReviews(
        @RequestHeader(value = "X-Request-Id", required = false) String requestId,
        @RequestHeader(value = "X-Subject-Id", required = false) String subjectId,
        @RequestParam String courseCode,
        @RequestParam(required = false) String teacherKey,
        @RequestParam(required = false) String termId,
        @RequestParam(required = false) Integer limit,
        @RequestParam(required = false) String cursor) {
        subjects.require(subjectId);

        requireId("courseCode", courseCode);
        requireOptionalId("teacherKey", teacherKey);
        requireOptionalId("termId", termId);
        int size = limitOrDefault("limit", limit, REVIEW_DEFAULT_LIMIT, REVIEW_MAX_LIMIT);

        return Envelope.ok(requestId, assembler.search(courseCode, teacherKey, termId, size, offsetOf(cursor)));
    }

    private static void requireId(String field, String value) {
        if (value == null || !ID.matcher(value).matches()) {
            throw new InvalidQuery(field, field + " 缺失或格式不合法");
        }
    }

    private static void requireOptionalId(String field, String value) {
        if (value != null && !ID.matcher(value).matches()) {
            throw new InvalidQuery(field, field + " 格式不合法");
        }
    }

    private static int limitOrDefault(String field, Integer value, int dflt, int max) {
        if (value == null) {
            return dflt;
        }
        if (value < 1 || value > max) {
            throw new InvalidQuery(field, field + " 须在 1 到 " + max + " 之间");
        }
        return value;
    }

    private static int offsetOf(String cursor) {
        if (cursor == null) {
            return 0;
        }
        if (!OFFSET_CURSOR.matcher(cursor).matches()) {
            throw new InvalidQuery("cursor", "cursor 格式不合法");
        }
        return Integer.parseInt(cursor);
    }
}
