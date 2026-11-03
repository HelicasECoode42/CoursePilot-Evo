package com.coursepilot.verifier.web.dto;

import java.time.Instant;
import java.util.List;

/**
 * 契约形状的教师课程意愿对象与评价证据 DTO。字段名与必填项逐条对照
 * contracts/schemas/domain.schema.json 的 TeacherCourseOption / ReviewNote，
 * 以及 contracts/java.openapi.json 的 listTeacherCourseOptions / searchReviews 的 data 形状。
 *
 * 不得把 JPA 实体直接返回：实体有自增或内部字段（如 bindingId、studentId 之类），
 * 必须经 TeacherReviewAssembler 映射到这里，只输出契约字段。
 */
public final class TeacherReviewDtos {

    private TeacherReviewDtos() {}

    /** contracts: TeacherCourseOption.availability。 */
    public enum Availability { CURRENT_VERIFIED, HISTORICAL_ONLY, UNKNOWN }

    /** contracts: ReviewNote.sourceKind。 */
    public enum SourceKind { OFFICIAL_SYLLABUS, USER_IMPORT, EXTERNAL_LINK, SYNTHETIC }

    /** contracts: ReviewNote.dimensions 的 items。数组形式，不是单个枚举。 */
    public enum Dimension { GRADING, ATTENDANCE, WORKLOAD, EXAM, GROUP_WORK, PRESENTATION, TEACHING, OVERALL }

    /** contracts: ReviewNote.matchStatus。 */
    public enum MatchStatus { COURSE_TEACHER_MATCHED, COURSE_ONLY, UNVERIFIED }

    /** contracts: TeacherCourseOption.factSource。 */
    public enum FactSource { TEACHER_BINDING, OFFERING_SNAPSHOT }

    /** contracts: TeacherCourseOption.offeringSourceValidation（开课快照的 sourceValidation）。 */
    public enum SourceValidation { VERIFIED, UNVERIFIED, SYNTHETIC }

    /**
     * contracts: TeacherCourseOption。后五个字段是可选的新增项（见 contracts/README.md 变更记录）：
     * 键始终输出，无值时为 null；TEACHER_BINDING 行这四项为 null。
     */
    public record TeacherCourseOption(
        String courseCode,
        String teacherKey,
        String teacherDisplayName,
        Availability availability,
        List<String> reviewNoteIds,
        List<String> classIds,
        String courseName,
        Integer sectionCount,
        String offeringSnapshotId,
        SourceValidation offeringSourceValidation,
        FactSource factSource) {

        /** 培养快照登记的教师绑定（种子路径）。 */
        public static TeacherCourseOption binding(String courseCode, String teacherKey, String teacherDisplayName,
                                                  Availability availability, List<String> reviewNoteIds,
                                                  List<String> classIds, String courseName) {
            return new TeacherCourseOption(courseCode, teacherKey, teacherDisplayName, availability,
                reviewNoteIds, classIds, courseName, null, null, null, FactSource.TEACHER_BINDING);
        }
    }

    /** listTeacherCourseOptions 的 data。nextCursor 为 null 表示没有下一页，字段必须存在。 */
    public record TeacherCourseOptionList(List<TeacherCourseOption> items, String nextCursor) {}

    /** contracts: ReviewNote。teacherKey、termId、publishedAt、sourceUrl 允许为 null，键仍必须输出。 */
    public record ReviewNote(
        String reviewNoteId,
        String courseCode,
        String teacherKey,
        String termId,
        SourceKind sourceKind,
        Instant publishedAt,
        String sourceUrl,
        String excerpt,
        String teacherDisplayName,
        List<Dimension> dimensions,
        MatchStatus matchStatus,
        String sourceRefId) {}

    /** searchReviews 的 data。 */
    public record ReviewNoteList(List<ReviewNote> items, String nextCursor) {}
}
