package com.coursepilot.verifier.application;

import static org.junit.jupiter.api.Assertions.*;

import com.coursepilot.verifier.domain.MeetingTime;
import java.util.Set;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * 冲突判定：docs/04「冲突=同星期∩节次相交∩周次相交；单双周不交不冲突；
 * 缺时间不是不冲突」。
 */
class ConflictCheckerTest {

  private static MeetingTime at(int day, int start, int end, Integer... weeks) {
    return new MeetingTime(day, start, end, Set.of(weeks));
  }

  @Test
  @DisplayName("同星期、节次相交、周次相交才算冲突")
  void overlapsOnAllThreeAxes() {
    assertTrue(at(1, 1, 2, 1, 2, 3).conflictsWith(at(1, 2, 3, 3, 4)));
  }

  @Test
  @DisplayName("不同星期不冲突")
  void differentDayNeverConflicts() {
    assertFalse(at(1, 1, 2, 1, 2).conflictsWith(at(2, 1, 2, 1, 2)));
  }

  @Test
  @DisplayName("节次不相交不冲突")
  void disjointSectionsDoNotConflict() {
    assertFalse(at(1, 1, 2, 1, 2).conflictsWith(at(1, 3, 4, 1, 2)));
  }

  @Test
  @DisplayName("单双周不相交不冲突")
  void alternatingWeeksDoNotConflict() {
    assertFalse(at(1, 1, 2, 1, 3, 5).conflictsWith(at(1, 1, 2, 2, 4, 6)));
  }

  @Test
  @DisplayName("节次相邻但不重叠不算冲突")
  void adjacentSectionsDoNotConflict() {
    assertFalse(at(1, 1, 2, 1).conflictsWith(at(1, 3, 4, 1)));
  }
}
