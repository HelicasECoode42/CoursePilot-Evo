package com.coursepilot.verifier.application;

import static org.junit.jupiter.api.Assertions.*;

import com.coursepilot.verifier.domain.MeetingTime;
import java.time.Duration;
import java.util.Collections;
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
  @DisplayName("一周上两次的课要解析出两段，不能只认第一段")
  void parsesMultipleBlocks() {
    // 回归：原先分别 find 星期/节次/周次各取第一个匹配，周三那段被静默丢掉
    // 还返回 ok，冲突检查就会把实际撞课的两门课判成不冲突。
    TimeParser.ParseOutcome outcome = parser.parse("星期一第1-2节{1-16周},星期三第3-4节{1-16周}");
    assertTrue(outcome.isOk(), outcome.getReason());
    assertEquals(2, outcome.getMeetings().size());
    assertEquals(1, outcome.getMeetings().get(0).getDayOfWeek());
    assertEquals(3, outcome.getMeetings().get(1).getDayOfWeek());
    assertEquals(3, outcome.getMeetings().get(1).getStartSection());
    assertEquals(4, outcome.getMeetings().get(1).getEndSection());
  }

  @Test
  @DisplayName("分号、顿号、无分隔符的多段写法都要认全")
  void parsesMultipleBlocksWithVariousSeparators() {
    assertEquals(2, parser.parse("周一第1-2节{第1-16周};周四第7-8节{第1-16周}")
        .getMeetings().size());
    assertEquals(2, parser.parse("周一第1-2节{第1-16周}、周四第7-8节{第1-16周}")
        .getMeetings().size());
    assertEquals(2, parser.parse("周一第1-2节{第1-16周}周四第7-8节{第1-16周}")
        .getMeetings().size());
  }

  @Test
  @DisplayName("多段里各段的单双周独立生效")
  void parityAppliesPerBlock() {
    TimeParser.ParseOutcome outcome =
        parser.parse("周一第1-2节{1-8周(单)},周三第1-2节{1-8周(双)}");
    assertTrue(outcome.isOk(), outcome.getReason());
    assertEquals(List.of(1, 3, 5, 7), List.copyOf(outcome.getMeetings().get(0).getWeeks()));
    assertEquals(List.of(2, 4, 6, 8), List.copyOf(outcome.getMeetings().get(1).getWeeks()));
  }

  @Test
  @DisplayName("认出一段但还剩看不懂的文本时报未知，不返回残缺课表")
  void partialRecognitionIsUnknown() {
    // 少一段时间会让冲突检查漏判，比直接说未知危险。docs/09：解析失败不得被当「无冲突」。
    TimeParser.ParseOutcome outcome = parser.parse("周一第1-2节{1-16周},周三第3-4节待定");
    assertFalse(outcome.isOk());
    assertTrue(outcome.getMeetings().isEmpty());
  }

  @Test
  @DisplayName("无法识别的残余片段不被静默丢掉")
  void unparsedRemainderIsUnknown() {
    assertFalse(parser.parse("周一第1-2节{待定}").isOk());
  }

  @Test
  @DisplayName("超大节次数字不抛异常，返回未知（调用方不能借此让服务返回 500）")
  void hugeSectionNumberIsUnknownNotException() {
    // 回归：start 的 Integer.parseInt 原先在 try 外面，99999999999 会以 NumberFormatException 逃出 parse()。
    TimeParser.ParseOutcome single = assertDoesNotThrow(
        () -> parser.parse("星期一第99999999999节{1周}"));
    assertFalse(single.isOk());
    assertFalse(single.isOutOfContract(), "数字放不进 int 时按无法识别处理，不是超限：" + single.getReason());
    assertTrue(single.getMeetings().isEmpty());

    TimeParser.ParseOutcome range = assertDoesNotThrow(
        () -> parser.parse("周一第1-99999999999节{第1-16周}"));
    assertFalse(range.isOk());
    assertTrue(range.getMeetings().isEmpty());
  }

  @Test
  @DisplayName("超大周次区间不展开：{1-999999999周} 直接判超限，且很快返回")
  void hugeWeekRangeIsNotExpanded() {
    // 回归：原先会把 999999999 个周次全部塞进 TreeSet。超时保护只防挂起，不能证明没展开，
    // 所以再断言结果：超限、meetings 为空。
    TimeParser.ParseOutcome outcome = assertTimeoutPreemptively(Duration.ofSeconds(5),
        () -> parser.parse("周一第1-2节{1-999999999周}"));
    assertTrue(outcome.isOutOfContract(), outcome.getReason());
    assertTrue(outcome.getMeetings().isEmpty());
  }

  @Test
  @DisplayName("周次下界：0 和 0-3 都超限，不再被接受")
  void weekBelowOneIsOutOfContract() {
    assertTrue(parser.parse("周一第1节{0周}").isOutOfContract());
    assertTrue(parser.parse("周一第1节{0-3周}").isOutOfContract());
  }

  @Test
  @DisplayName("周次上限 60：第 60 周可用，61 周超限")
  void weekUpperBound() {
    assertTrue(parser.parse("周一第1节{第60周}").isOk());
    assertTrue(parser.parse("周一第1节{第1-60周}").isOk());
    assertTrue(parser.parse("周一第1节{第61周}").isOutOfContract());
    assertTrue(parser.parse("周一第1节{第1-61周}").isOutOfContract());
  }

  @Test
  @DisplayName("节次上限 64：第 64 节可用，65 节或第 0 节超限")
  void sectionBounds() {
    assertTrue(parser.parse("周一第1-64节{1周}").isOk());
    assertTrue(parser.parse("周一第1-65节{1周}").isOutOfContract());
    assertTrue(parser.parse("周一第0节{1周}").isOutOfContract());
  }

  @Test
  @DisplayName("段数上限 40：第 40 段可用，第 41 段超限")
  void meetingCountBound() {
    String block = "周一第1节{1周}";
    assertTrue(parser.parse(String.join(",", Collections.nCopies(40, block))).isOk());
    assertTrue(parser.parse(String.join(",", Collections.nCopies(41, block))).isOutOfContract());
  }

  @Test
  @DisplayName("超限结论不带 meetings，且不是 ok")
  void outOfContractCarriesNoMeetings() {
    TimeParser.ParseOutcome outcome = parser.parse("周一第1-70节{第1-16周}");
    assertFalse(outcome.isOk());
    assertTrue(outcome.isOutOfContract());
    assertTrue(outcome.getMeetings().isEmpty());
  }
}
