package com.coursepilot.verifier.web;

import com.coursepilot.verifier.application.TimeParser;
import com.coursepilot.verifier.domain.MeetingTime;
import com.coursepilot.verifier.persistence.entity.Course;
import com.coursepilot.verifier.persistence.entity.CourseOffering;
import com.coursepilot.verifier.persistence.entity.CurriculumCourse;
import com.coursepilot.verifier.web.dto.CatalogDtos;
import com.coursepilot.verifier.web.dto.CatalogDtos.Meeting;
import com.coursepilot.verifier.web.dto.CatalogDtos.ParseStatus;
import org.springframework.stereotype.Component;

import java.util.List;

/**
 * 把持久化实体映射成契约形状的 DTO。
 *
 * 时间只从 meetingTextRaw 由唯一的 TimeParser 重新解析（AGENTS.md：Java 重新解析
 * meetingTextRaw，不信任任何外部给的 meetings / parseStatus）。解析失败时如实标
 * UNPARSED 并给空 meetings，绝不能当成「没有时间所以不冲突」。
 */
@Component
public class CatalogAssembler {

    /** 实体里 teacher / category 允许为空；契约要求非空字符串，缺失时写字面量 UNKNOWN，不编造。 */
    static final String UNKNOWN_TEXT = "UNKNOWN";

    private final TimeParser timeParser;

    public CatalogAssembler(TimeParser timeParser) {
        this.timeParser = timeParser;
    }

    public CatalogDtos.Course toCourse(Course c) {
        return new CatalogDtos.Course(
            c.getCourseCode(),
            c.getName(),
            c.getCredits(),
            orUnknown(c.getCategory()),
            // 当前实体没有快照关联，来源只能落到课程行本身。它是库内记录的引用，
            // 不是培养方案或教务来源的真实出处。
            List.of("course:" + c.getCourseCode()));
    }

    public CatalogDtos.Course toCourse(CurriculumCourse membership) {
        return new CatalogDtos.Course(
            membership.getCourse().getCourseCode(),
            membership.getName(),
            membership.getCredits(),
            membership.getCategory(),
            List.of(membership.getSourceReference().getRefId()),
            membership.getSuggestedTerm());
    }

    public CatalogDtos.CourseOffering toOffering(CourseOffering o) {
        String raw = o.getMeetingTextRaw() == null ? "" : o.getMeetingTextRaw();
        TimeParser.ParseOutcome outcome = timeParser.parse(raw);

        ParseStatus status;
        List<Meeting> meetings;
        if (outcome.isOutOfContract()) {
            // 时间能读出，但超出契约上限（上限由 TimeParser 判定）：不能原样返回。
            status = ParseStatus.INVALID;
            meetings = List.of();
        } else if (!outcome.isOk()) {
            // 解析不出来：未解析 + 空 meetings。调用方必须据此判为未知，不能判为无冲突。
            status = ParseStatus.UNPARSED;
            meetings = List.of();
        } else {
            status = ParseStatus.PARSED;
            meetings = outcome.getMeetings().stream().map(CatalogAssembler::toMeeting).toList();
        }

        return new CatalogDtos.CourseOffering(
            o.getCourseCode(),
            o.getOfferingId(),
            null,                        // 当前没有教师主键
            orUnknown(o.getTeacher()),
            null,                        // 实体没有学分
            null,                        // 实体没有容量
            raw,
            meetings,
            status,
            "offering:" + o.getOfferingId());
    }

    private static Meeting toMeeting(MeetingTime m) {
        return new Meeting(
            m.getDayOfWeek(),
            m.getStartSection(),
            m.getEndSection(),
            m.getWeeks().stream().sorted().toList());
    }

    private static String orUnknown(String value) {
        return (value == null || value.isBlank()) ? UNKNOWN_TEXT : value;
    }
}
