package com.coursepilot.verifier.application;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.coursepilot.verifier.domain.ConflictResult;
import com.coursepilot.verifier.persistence.entity.CourseOffering;
import com.coursepilot.verifier.persistence.repo.CourseOfferingRepository;
import com.coursepilot.verifier.web.CatalogAssembler;
import com.coursepilot.verifier.web.dto.CatalogDtos;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;
import org.springframework.transaction.annotation.Transactional;

/**
 * ConflictChecker.check() 的回归。
 *
 * 这个入口原先一条测试都没有——只有 MeetingTime.conflictsWith 被直接测过，
 * 所以下面两个故障在「测试全绿」的情况下存在了很久：
 *   1. 时间列表按 findAllById 的返回顺序建，班次名却按入参顺序取，
 *      两个顺序不一致时点错班次；
 *   2. 同一个班次传两次会被 findAllById 合并，然后被误报成「班次不存在」。
 */
@SpringBootTest
@TestPropertySource(properties = "spring.datasource.url=jdbc:h2:mem:conflicttest;DB_CLOSE_DELAY=-1")
@Transactional
class ConflictCheckerServiceTest {

  @Autowired private ConflictChecker checker;
  @Autowired private CourseOfferingRepository offeringRepo;
  @Autowired private CatalogAssembler catalog;

  private void save(String id, String courseCode, String time) {
    offeringRepo.save(new CourseOffering(id, courseCode, "某老师", time, "SYNTHETIC"));
  }

  @Test
  @DisplayName("报出来的必须是真正相撞的那两个班次")
  void namesTheOfferingsThatActuallyClash() {
    save("O_A", "A", "周一第1-2节{第1-16周}");
    save("O_B", "B", "周一第2-3节{第1-16周}");   // 与 O_A 在第 2 节相撞
    save("O_X", "X", "时间待定");                  // 解析不出时间，不可能和谁相撞

    // 刻意把时间待定的那个排在最前，让入参顺序和仓库返回顺序不一致。
    ConflictResult result = checker.check(List.of("O_X", "O_A", "O_B"));

    assertTrue(result.hasKnownConflict(), result.getReason());
    assertTrue(result.getReason().contains("O_A") && result.getReason().contains("O_B"),
        "应当点名 O_A 与 O_B，实际：" + result.getReason());
    assertFalse(result.getReason().contains("O_X 与") || result.getReason().contains("与 O_X"),
        "O_X 时间都解析不出来，不可能是冲突方，实际：" + result.getReason());
  }

  @Test
  @DisplayName("同一个班次传两次不算「班次不存在」")
  void duplicateIdIsNotMissingData() {
    save("O_A", "A", "周一第1-2节{第1-16周}");

    ConflictResult result = checker.check(List.of("O_A", "O_A"));

    assertFalse(result.hasKnownConflict());
    assertFalse(result.getReason().contains("不存在"),
        "重复 ID 不该被说成缺数据，实际：" + result.getReason());
  }

  @Test
  @DisplayName("真的缺班次时要说清少的是哪个")
  void missingOfferingIsNamed() {
    save("O_A", "A", "周一第1-2节{第1-16周}");

    ConflictResult result = checker.check(List.of("O_A", "O_NOPE"));

    assertFalse(result.hasKnownConflict());
    assertTrue(result.hasUnknownParticipant());
    assertTrue(result.getReason().contains("O_NOPE"), result.getReason());
  }

  @Test
  @DisplayName("一周上两次的课，第二段相撞也要判出来")
  void secondBlockClashIsDetected() {
    // 这条依赖 TimeParser 逐段解析。原先只认第一段时，这里会被判成无冲突。
    save("O_A", "A", "周一第1-2节{第1-16周},周三第5-6节{第1-16周}");
    save("O_C", "C", "周三第6-7节{第1-16周}");   // 只和 O_A 的第二段相撞

    ConflictResult result = checker.check(List.of("O_A", "O_C"));

    assertTrue(result.hasKnownConflict(),
        "周三第 6 节重叠，应当判冲突。实际：" + result.getReason());
  }

  @Test
  @DisplayName("时间解析不出来是未知，不是「不冲突」")
  void unparsableTimeIsUnknownNotConflictFree() {
    save("O_X", "X", "时间待定");
    save("O_A", "A", "周一第1-2节{第1-16周}");

    ConflictResult result = checker.check(List.of("O_X", "O_A"));

    assertFalse(result.hasKnownConflict());
    assertTrue(result.hasUnknownParticipant(), "必须标记存在未知参与者");
  }

  @Test
  @DisplayName("超出契约上限的时间：目录与冲突判定结论一致，都是未知，不拿它判冲突")
  void outOfContractTimeIsUnknownInBothViews() {
    // 回归：目录说 INVALID，冲突判定却原先把节次 70 当有效时间，和 O_A 判成已知冲突。
    save("O_BIG", "BIG", "周一第1-70节{第1-16周}");
    save("O_A", "A", "周一第1-2节{第1-16周}");   // 与 O_BIG 在第 1-2 节时间上相交

    CatalogDtos.CourseOffering catalogView =
        catalog.toOffering(offeringRepo.findById("O_BIG").orElseThrow());
    assertEquals(CatalogDtos.ParseStatus.INVALID, catalogView.parseStatus());
    assertTrue(catalogView.meetings().isEmpty());

    ConflictResult result = checker.check(List.of("O_BIG", "O_A"));
    assertFalse(result.hasKnownConflict(),
        "超限班次不能当有效时间判冲突，实际：" + result.getReason());
    assertTrue(result.hasUnknownParticipant(), result.getReason());
  }
}
