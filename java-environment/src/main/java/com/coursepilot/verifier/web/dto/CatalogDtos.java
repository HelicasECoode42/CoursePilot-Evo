package com.coursepilot.verifier.web.dto;

import java.util.List;

/**
 * 契约形状的课程目录 DTO，字段名与必填项逐条对照
 * contracts/schemas/domain.schema.json 的 Course / CourseOffering / Meeting，
 * 以及 contracts/java.openapi.json 的 listCourses / listOfferings 的 data 形状。
 *
 * 这一层只负责「摆对形状」，不改数据库实体（实体的字段名与契约不同，
 * 例如实体的 teacher 对应契约的 teacherText）。映射逻辑在 web/CatalogAssembler。
 */
public final class CatalogDtos {

    private CatalogDtos() {}

    /** contracts: Meeting。sectionStart/sectionEnd 为 1..64，weeks 为 1..60 的去重整数。 */
    public record Meeting(
        int dayOfWeek,
        int sectionStart,
        int sectionEnd,
        List<Integer> weeks) {}

    /** contracts: CourseOffering.parseStatus。 */
    public enum ParseStatus { PARSED, UNPARSED, INVALID }

    /** contracts: Course */
    public record Course(
        String courseCode,
        String name,
        Double credits,
        String category,
        List<String> sourceRefIds) {}

    /**
     * contracts: CourseOffering。
     * teacherKey、credits、capacity 当前实体没有对应数据，恒为 null。
     */
    public record CourseOffering(
        String courseCode,
        String classId,
        String teacherKey,
        String teacherText,
        Double credits,
        Integer capacity,
        String meetingTextRaw,
        List<Meeting> meetings,
        ParseStatus parseStatus,
        String sourceRefId) {}

    /** listCourses 的分页 data；nextCursor 为下一页偏移量，没有下一页时为 null。 */
    public record CourseList(List<Course> items, String nextCursor) {}

    /** listOfferings 的 data。 */
    public record OfferingList(List<CourseOffering> items) {}
}
