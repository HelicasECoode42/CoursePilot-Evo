package com.coursepilot.verifier.application;

import static org.junit.jupiter.api.Assertions.*;

import com.coursepilot.verifier.domain.MeetingTime;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * TimeParser 是 B-F4 的唯一实现。重点不是「能解析」，而是
 * 「解析不了时必须说未知，不许默认整学期」——docs/04：缺时间不是不冲突。
 */
class TimeParserTest {

  private final TimeParser parser = new TimeParser();

  @Test
  @DisplayName("常见写法：星期、节次区间、周次区间都能解析")
  void parsesCommonForm() {
    TimeParser.ParseOutcome outcome = parser.parse("周一第1-2节{第1-16周}");
    assertTrue(outcome.isOk(), outcome.getReason());
    List<MeetingTime> meetings = outcome.getMeetings();
    assertEquals(1, meetings.size());
    MeetingTime m = meetings.get(0);
    assertEquals(1, m.getDayOfWeek());
    assertEquals(1, m.getStartSection());
    assertEquals(2, m.getEndSection());
    assertEquals(16, m.getWeeks().size());
  }

  @Test
  @DisplayName("离散周次用逗号分隔")
  void parsesDiscreteWeeks() {
    TimeParser.ParseOutcome outcome = parser.parse("周三第5节{第1,3,5周}");
    assertTrue(outcome.isOk(), outcome.getReason());
    assertEquals(List.of(1, 3, 5), List.copyOf(outcome.getMeetings().get(0).getWeeks()));
  }

  @Test
  @DisplayName("空文本返回未知，不返回空课表当作没课")
  void blankIsUnknown() {
    assertFalse(parser.parse("").isOk());
    assertFalse(parser.parse(null).isOk());
  }

  @Test
  @DisplayName("缺周次返回未知，不默认整学期")
  void missingWeeksIsUnknown() {
    TimeParser.ParseOutcome outcome = parser.parse("周一第1-2节"); // 没有 {} 周次块
    assertFalse(outcome.isOk());
    assertTrue(outcome.getMeetings().isEmpty());
  }

  @Test
  @DisplayName("节次倒置、周次倒置都按未知处理")
  void invertedRangesAreUnknown() {
    assertFalse(parser.parse("周一第5-2节{第1-16周}").isOk());
    assertFalse(parser.parse("周一第1-2节{第16-1周}").isOk());
  }

  @Test
  @DisplayName("真实快照的完整写法：星期三第3-4节{1-16周(单)}")
  void parsesRealSnapshotForm() {
    // docs/course-offering-snapshot.example.json 里的实际写法。
    TimeParser.ParseOutcome outcome = parser.parse("星期三第3-4节{1-16周(单)}");
    assertTrue(outcome.isOk(), outcome.getReason());
    MeetingTime m = outcome.getMeetings().get(0);
    assertEquals(3, m.getDayOfWeek());
    assertEquals(3, m.getStartSection());
    assertEquals(4, m.getEndSection());
    assertEquals(List.of(1, 3, 5, 7, 9, 11, 13, 15), List.copyOf(m.getWeeks()));
  }

  @Test
  @DisplayName("双周标记只保留偶数周")
  void parsesEvenWeeks() {
    TimeParser.ParseOutcome outcome = parser.parse("星期二第1-2节{1-8周(双)}");
    assertTrue(outcome.isOk(), outcome.getReason());
    assertEquals(List.of(2, 4, 6, 8), List.copyOf(outcome.getMeetings().get(0).getWeeks()));
  }

  @Test
  @DisplayName("「星期日」与「星期天」都是 7")
  void sundayBothSpellings() {
    assertEquals(7, parser.parse("星期日第1节{1周}").getMeetings().get(0).getDayOfWeek());
    assertEquals(7, parser.parse("星期天第1节{1周}").getMeetings().get(0).getDayOfWeek());
  }

  @Test
  @DisplayName("单双周过滤后周次为空时报未知，不返回空课表")
  void emptyAfterParityFilterIsUnknown() {
    // 2-2 周只有第 2 周，取单周后为空；这时不能说「没课」，要说未知。
    assertFalse(parser.parse("周一第1节{2-2周(单)}").isOk());
  }

  @Test
  @DisplayName("无法识别的残余片段不被静默丢掉")
  void unparsedRemainderIsUnknown() {
    assertFalse(parser.parse("周一第1-2节{待定}").isOk());
  }
}
