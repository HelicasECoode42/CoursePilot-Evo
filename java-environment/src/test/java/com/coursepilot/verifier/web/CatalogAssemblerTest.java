package com.coursepilot.verifier.web;

import static org.junit.jupiter.api.Assertions.*;

import com.coursepilot.verifier.application.TimeParser;
import com.coursepilot.verifier.persistence.entity.Course;
import com.coursepilot.verifier.persistence.entity.CourseOffering;
import com.coursepilot.verifier.web.dto.CatalogDtos;
import com.coursepilot.verifier.web.dto.CatalogDtos.ParseStatus;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class CatalogAssemblerTest {

    private final CatalogAssembler assembler = new CatalogAssembler(new TimeParser());

    private static CourseOffering offering(String id, String teacher, String raw) {
        return new CourseOffering(id, "CS101", teacher, raw, "SYNTHETIC");
    }

    @Test
    @DisplayName("Course 映射：字段对齐契约，sourceRefIds 指向课程行，学分允许 null")
    void courseMapping() {
        CatalogDtos.Course c = assembler.toCourse(new Course("CS103", "操作系统", null, "必修"));
        assertEquals("CS103", c.courseCode());
        assertEquals("操作系统", c.name());
        assertNull(c.credits());
        assertEquals("必修", c.category());
        assertEquals(List.of("course:CS103"), c.sourceRefIds());
    }

    @Test
    @DisplayName("Course 的空类别写 UNKNOWN，不留空字符串")
    void blankCategoryBecomesUnknown() {
        assertEquals("UNKNOWN", assembler.toCourse(new Course("CS1", "X", 1.0, null)).category());
        assertEquals("UNKNOWN", assembler.toCourse(new Course("CS1", "X", 1.0, " ")).category());
    }

    @Test
    @DisplayName("Offering 字段映射：classId 来自 offeringId，teacherText 来自 teacher，教师主键/学分/容量为 null")
    void offeringFieldMapping() {
        CatalogDtos.CourseOffering o = assembler.toOffering(offering("O_CS101_01", "张老师", "周一第1-2节{第1-16周}"));
        assertEquals("CS101", o.courseCode());
        assertEquals("O_CS101_01", o.classId());
        assertEquals("张老师", o.teacherText());
        assertNull(o.teacherKey());
        assertNull(o.credits());
        assertNull(o.capacity());
        assertEquals("周一第1-2节{第1-16周}", o.meetingTextRaw());
        assertEquals("offering:O_CS101_01", o.sourceRefId());
    }

    @Test
    @DisplayName("空教师写 UNKNOWN")
    void nullTeacherBecomesUnknown() {
        CatalogDtos.CourseOffering o = assembler.toOffering(offering("O1", null, "周一第1节{第1-16周}"));
        assertEquals("UNKNOWN", o.teacherText());
    }

    @Test
    @DisplayName("可解析的 meetingTextRaw：由 TimeParser 得出 meetings，parseStatus=PARSED，周次升序")
    void parsedMeetings() {
        CatalogDtos.CourseOffering o = assembler.toOffering(offering("O1", "张老师", "周一第1-2节{第1-16周}"));
        assertEquals(ParseStatus.PARSED, o.parseStatus());
        assertEquals(1, o.meetings().size());
        CatalogDtos.Meeting m = o.meetings().get(0);
        assertEquals(1, m.dayOfWeek());
        assertEquals(1, m.sectionStart());
        assertEquals(2, m.sectionEnd());
        assertEquals(16, m.weeks().size());
        assertEquals(1, m.weeks().get(0));
        assertEquals(16, m.weeks().get(15));
    }

    @Test
    @DisplayName("一周两段的写法：两段都保留，不因只认第一段而静默丢掉")
    void multipleBlocksKeptInOrder() {
        CatalogDtos.CourseOffering o = assembler.toOffering(
            offering("O1", "张老师", "星期一第1-2节{第1-16周},星期三第3-4节{第1-16周}"));
        assertEquals(ParseStatus.PARSED, o.parseStatus());
        assertEquals(2, o.meetings().size());
        assertEquals(3, o.meetings().get(1).dayOfWeek());
        assertEquals(3, o.meetings().get(1).sectionStart());
        assertEquals(4, o.meetings().get(1).sectionEnd());
    }

    @Test
    @DisplayName("解析不了的时间：UNPARSED + 空 meetings，不能当成没有时间")
    void unparseableIsUnparsedNotEmptyFree() {
        CatalogDtos.CourseOffering o = assembler.toOffering(offering("O_CS103_01", "王老师", "时间待定"));
        assertEquals(ParseStatus.UNPARSED, o.parseStatus());
        assertTrue(o.meetings().isEmpty());
        assertEquals("时间待定", o.meetingTextRaw());
    }

    @Test
    @DisplayName("空 meetingTextRaw 同样是 UNPARSED")
    void blankRawIsUnparsed() {
        CatalogDtos.CourseOffering o = assembler.toOffering(offering("O1", "张老师", null));
        assertEquals(ParseStatus.UNPARSED, o.parseStatus());
        assertEquals("", o.meetingTextRaw());
        assertTrue(o.meetings().isEmpty());
    }

    @Test
    @DisplayName("解析出的节次超出契约上限（64）：INVALID + 空 meetings，不原样返回")
    void sectionOutOfContractIsInvalid() {
        CatalogDtos.CourseOffering o = assembler.toOffering(offering("O1", "张老师", "周一第1-70节{第1-16周}"));
        assertEquals(ParseStatus.INVALID, o.parseStatus());
        assertTrue(o.meetings().isEmpty());
    }

    @Test
    @DisplayName("解析出的周次超出契约上限（60）：INVALID")
    void weekOutOfContractIsInvalid() {
        CatalogDtos.CourseOffering o = assembler.toOffering(offering("O1", "张老师", "周一第1-2节{第1-99周}"));
        assertEquals(ParseStatus.INVALID, o.parseStatus());
        assertTrue(o.meetings().isEmpty());
    }

    @Test
    @DisplayName("节次数字过大：UNPARSED 且不抛异常（与冲突判定一样是未知）")
    void hugeSectionNumberIsUnparsed() {
        CatalogDtos.CourseOffering o = assertDoesNotThrow(() ->
            assembler.toOffering(offering("O1", "张老师", "星期一第99999999999节{1周}")));
        assertEquals(ParseStatus.UNPARSED, o.parseStatus());
        assertTrue(o.meetings().isEmpty());
    }

    @Test
    @DisplayName("周次 0 超出契约下界：INVALID")
    void weekZeroIsInvalid() {
        CatalogDtos.CourseOffering o = assembler.toOffering(offering("O1", "张老师", "周一第1-2节{0-3周}"));
        assertEquals(ParseStatus.INVALID, o.parseStatus());
        assertTrue(o.meetings().isEmpty());
    }
}
