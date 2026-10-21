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
  @DisplayName("真实快照用「星期三」而非「周三」，当前解析不了，必须报未知不能静默当无课")
  void realSnapshotDayWordIsUnknownForNow() {
    // docs/course-offering-snapshot.example.json 的实际写法：星期三第3-4节{1-16周(单)}
    // 现在 DAY 正则只认「周X」，这条应当返回未知而不是漏解析。接入真实班次前需要支持。
    TimeParser.ParseOutcome outcome = parser.parse("星期三第3-4节{1-16周}");
    assertFalse(outcome.isOk(), "若将来支持「星期X」写法，请把这条改成正例");
  }

  @Test
  @DisplayName("单双周标记当前解析不了，必须报未知")
  void alternatingWeekMarkerIsUnknownForNow() {
    // 真实写法带 (单)/(双)。docs/04：单双周不交不冲突，所以这个标记不能丢。
    TimeParser.ParseOutcome outcome = parser.parse("周三第3-4节{1-16周(单)}");
    assertFalse(outcome.isOk(), "若将来支持单双周，请把这条改成正例并断言周次只剩奇数");
  }

  @Test
  @DisplayName("无法识别的残余片段不被静默丢掉")
  void unparsedRemainderIsUnknown() {
    assertFalse(parser.parse("周一第1-2节{待定}").isOk());
  }
}
