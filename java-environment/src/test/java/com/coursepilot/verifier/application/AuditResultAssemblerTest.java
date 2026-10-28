package com.coursepilot.verifier.application;

import static org.junit.jupiter.api.Assertions.*;

import com.coursepilot.verifier.persistence.entity.Course;
import com.coursepilot.verifier.persistence.entity.Requirement;
import com.coursepilot.verifier.persistence.entity.Transcript;
import com.coursepilot.verifier.persistence.entity.TranscriptCourse;
import com.coursepilot.verifier.persistence.repo.CourseRepository;
import com.coursepilot.verifier.persistence.repo.RequirementRepository;
import com.coursepilot.verifier.persistence.repo.TranscriptRepository;
import com.coursepilot.verifier.web.dto.AuditDtos;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.transaction.annotation.Transactional;

/**
 * 契约形状的学业核对。重点是几条红线：
 *   - 学分未知的类别必须是 UNKNOWN，不能当 0 也不能算满足（AGENTS.md：unknown 不能通过）
 *   - 重修只计一次
 *   - 缺口为负时归零，不出现负数学分
 *   - 在修 / 结果未知的课程不能让缺口说成确定
 */
@SpringBootTest
@Transactional
class AuditResultAssemblerTest {

  @Autowired AuditResultAssembler assembler;
  @Autowired RequirementRepository requirementRepo;
  @Autowired CourseRepository courseRepo;
  @Autowired TranscriptRepository transcriptRepo;

  private static final String PLAN = "plan-test";
  private static final String STUDENT = "stu-test";

  /** requirementId 是 ASCII 主键，按类别找项要靠 requiredCredits 与 courseCodes 定位。 */
  private AuditDtos.AuditItem onlyItem(AuditDtos.AuditResult result) {
    assertEquals(1, result.requirements().size(), "本用例只种了一条要求");
    return result.requirements().get(0);
  }

  @Test
  @DisplayName("学分够：SATISFIED，缺口为 0")
  void satisfied() {
    requirementRepo.save(new Requirement(PLAN, "通识", 4.0));
    courseRepo.save(new Course("C1", "通识课", 4.0, "通识"));
    transcript(true, row("C1", 4.0, TranscriptCourse.Outcome.PASSED, 1));

    AuditDtos.AuditResult result = assembler.assemble(PLAN, STUDENT);
    AuditDtos.AuditItem item = onlyItem(result);
    assertEquals(AuditDtos.State.SATISFIED, item.state());
    assertEquals(0.0, item.gapCredits());
    assertEquals(4.0, item.earnedCredits());
  }

  @Test
  @DisplayName("学分不够：UNSATISFIED，缺口是差额")
  void unsatisfied() {
    requirementRepo.save(new Requirement(PLAN, "专选", 24.0));
    courseRepo.save(new Course("C2", "专选课", 3.0, "专选"));
    transcript(true, row("C2", 3.0, TranscriptCourse.Outcome.PASSED, 1));

    AuditDtos.AuditItem item = onlyItem(assembler.assemble(PLAN, STUDENT));
    assertEquals(AuditDtos.State.UNSATISFIED, item.state());
    assertEquals(21.0, item.gapCredits());
  }

  @Test
  @DisplayName("学分未知的类别必须是 UNKNOWN，不能当 0 算成缺口")
  void unknownCreditsBlockTheCategory() {
    requirementRepo.save(new Requirement(PLAN, "实践", 2.0));
    courseRepo.save(new Course("C3", "实践课", null, "实践"));
    transcript(true, row("C3", null, TranscriptCourse.Outcome.PASSED, 1));

    AuditDtos.AuditResult result = assembler.assemble(PLAN, STUDENT);
    assertEquals(AuditDtos.State.UNKNOWN, onlyItem(result).state());
    assertTrue(result.unknowns().stream().anyMatch(i -> i.code().equals("CREDITS_UNKNOWN")));
  }

  @Test
  @DisplayName("重修只计一次，不重复累加学分")
  void retakeCountsOnce() {
    requirementRepo.save(new Requirement(PLAN, "数学", 4.0));
    courseRepo.save(new Course("C4", "高数", 4.0, "数学"));
    transcript(true,
        row("C4", 4.0, TranscriptCourse.Outcome.PASSED, 1),
        row("C4", 4.0, TranscriptCourse.Outcome.PASSED, 2));

    AuditDtos.AuditItem item = onlyItem(assembler.assemble(PLAN, STUDENT));
    assertEquals(4.0, item.earnedCredits(), "重修被重复累加了");
    assertEquals(AuditDtos.State.SATISFIED, item.state());
  }

  @Test
  @DisplayName("未通过的课程不计入已修学分")
  void failedCourseDoesNotCount() {
    requirementRepo.save(new Requirement(PLAN, "物理", 4.0));
    courseRepo.save(new Course("C5", "大物", 4.0, "物理"));
    transcript(true, row("C5", 4.0, TranscriptCourse.Outcome.FAILED, 1));

    AuditDtos.AuditItem item = onlyItem(assembler.assemble(PLAN, STUDENT));
    assertEquals(0.0, item.earnedCredits());
    assertEquals(AuditDtos.State.UNSATISFIED, item.state());
  }

  @Test
  @DisplayName("在修的课程不计学分，相应类别的缺口不能确定，判 UNKNOWN 而不是 UNSATISFIED")
  void inProgressCourseMakesGapUnknown() {
    requirementRepo.save(new Requirement(PLAN, "实践", 10.0));
    courseRepo.save(new Course("C6", "实践课", 2.0, "实践"));
    transcript(true, row("C6", null, TranscriptCourse.Outcome.IN_PROGRESS, 1));

    AuditDtos.AuditResult result = assembler.assemble(PLAN, STUDENT);
    AuditDtos.AuditItem item = onlyItem(result);
    assertEquals(0.0, item.earnedCredits(), "在修课程不能计入已修学分");
    assertEquals(AuditDtos.State.UNKNOWN, item.state());
    assertTrue(result.unknowns().stream().anyMatch(i -> i.code().equals("PENDING_COURSE")));
  }

  @Test
  @DisplayName("结果未知的课程同样不计学分；待定类别若已满足，仍判满足")
  void unknownOutcomeDoesNotLowerASatisfiedCategory() {
    requirementRepo.save(new Requirement(PLAN, "通识", 4.0));
    courseRepo.save(new Course("C7", "通识甲", 4.0, "通识"));
    courseRepo.save(new Course("C8", "通识乙", 2.0, "通识"));
    transcript(true,
        row("C7", 4.0, TranscriptCourse.Outcome.PASSED, 1),
        row("C8", null, TranscriptCourse.Outcome.UNKNOWN, 1));

    AuditDtos.AuditItem item = onlyItem(assembler.assemble(PLAN, STUDENT));
    assertEquals(4.0, item.earnedCredits());
    assertEquals(AuditDtos.State.SATISFIED, item.state(), "学分只增不减，已满足就是满足");
  }

  @Test
  @DisplayName("同一课程先未通过、后在修：没有通过记录，仍按待定处理")
  void failedThenInProgressIsStillPending() {
    requirementRepo.save(new Requirement(PLAN, "工程", 4.0));
    courseRepo.save(new Course("C9", "工程课", 4.0, "工程"));
    transcript(true,
        row("C9", 4.0, TranscriptCourse.Outcome.FAILED, 1),
        row("C9", null, TranscriptCourse.Outcome.IN_PROGRESS, 2));

    AuditDtos.AuditItem item = onlyItem(assembler.assemble(PLAN, STUDENT));
    assertEquals(0.0, item.earnedCredits());
    assertEquals(AuditDtos.State.UNKNOWN, item.state());
  }

  @Test
  @DisplayName("培养方案不存在时给出未知，不返回空的已满足")
  void missingCurriculumIsUnknown() {
    AuditDtos.AuditResult result = assembler.assemble("plan-does-not-exist", STUDENT);
    assertTrue(result.requirements().isEmpty());
    assertTrue(result.unknowns().stream().anyMatch(i -> i.code().equals("CURRICULUM_NOT_FOUND")));
  }

  @Test
  @DisplayName("requirementId 与 sourceRefIds 必须满足契约格式，否则 C 侧校验会整条拒掉")
  void idsMatchContractPattern() {
    requirementRepo.save(new Requirement(PLAN, "通识", 4.0));
    AuditDtos.AuditResult result = assembler.assemble(PLAN, STUDENT);
    AuditDtos.AuditItem item = onlyItem(result);

    // contracts/schemas/domain.schema.json：^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$
    String pattern = "^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$";
    assertTrue(item.requirementId().matches(pattern),
        "requirementId 含非法字符（类别名是中文，不能直接拼进 id）：" + item.requirementId());
    // sourceRefIds minItems=1：每条结论都要可追溯。
    assertFalse(item.sourceRefIds().isEmpty(), "sourceRefIds 不能为空");
    item.sourceRefIds().forEach(ref ->
        assertTrue(ref.matches(pattern), "sourceRefId 含非法字符：" + ref));
  }

  @Test
  @DisplayName("未声明完整：transcriptComplete 如实为 false，并记入 unknowns")
  void incompleteTranscriptIsReported() {
    requirementRepo.save(new Requirement(PLAN, "通识", 1.0));
    transcript(false);
    AuditDtos.AuditResult result = assembler.assemble(PLAN, STUDENT);
    assertFalse(result.transcriptComplete());
    assertTrue(result.unknowns().stream()
        .anyMatch(i -> i.code().equals("TRANSCRIPT_COMPLETENESS_UNKNOWN")));
  }

  @Test
  @DisplayName("声明完整：transcriptComplete 读聚合里的真实值 true，不再记完整性未知")
  void completeTranscriptIsReported() {
    requirementRepo.save(new Requirement(PLAN, "通识", 1.0));
    transcript(true);
    AuditDtos.AuditResult result = assembler.assemble(PLAN, STUDENT);
    assertTrue(result.transcriptComplete());
    assertTrue(result.unknowns().stream()
        .noneMatch(i -> i.code().equals("TRANSCRIPT_COMPLETENESS_UNKNOWN")));
  }

  @Test
  @DisplayName("recordRevision 返回聚合里的真实修订号，每次写入递增")
  void recordRevisionIsReal() {
    requirementRepo.save(new Requirement(PLAN, "通识", 1.0));
    Transcript t = transcript(true);
    assertEquals(1, assembler.assemble(PLAN, STUDENT).recordRevision());

    t.revise(PLAN, true, Transcript.SourceKind.SYNTHETIC,
        Instant.parse("2025-10-01T00:00:00Z"), List.of());
    transcriptRepo.save(t);
    assertEquals(2, assembler.assemble(PLAN, STUDENT).recordRevision());
  }

  @Test
  @DisplayName("完全没有学业记录：所有要求 UNKNOWN，缺口不给确定值，不把未知当 0 判 UNSATISFIED")
  void noRecordMakesEveryRequirementUnknown() {
    requirementRepo.save(new Requirement(PLAN, "通识", 4.0));
    requirementRepo.save(new Requirement(PLAN, "必修", 10.0));

    AuditDtos.AuditResult result = assembler.assemble(PLAN, STUDENT);
    assertEquals(2, result.requirements().size());
    for (AuditDtos.AuditItem item : result.requirements()) {
      assertEquals(AuditDtos.State.UNKNOWN, item.state());
      assertNull(item.gapCredits(), "无记录时缺口不能是确定数字");
    }
    assertTrue(result.unknowns().stream().anyMatch(i -> i.code().equals("ACADEMIC_RECORD_EMPTY")));
  }

  @Test
  @DisplayName("未声明完整：未满足的要求判 UNKNOWN 且缺口不给值，已满足的仍 SATISFIED")
  void incompleteTranscriptMakesUnmetGapUnknown() {
    requirementRepo.save(new Requirement(PLAN, "通识", 4.0));
    requirementRepo.save(new Requirement(PLAN, "专选", 24.0));
    courseRepo.save(new Course("C10", "通识甲", 4.0, "通识"));
    courseRepo.save(new Course("C11", "专选甲", 3.0, "专选"));
    transcript(false,
        row("C10", 4.0, TranscriptCourse.Outcome.PASSED, 1),
        row("C11", 3.0, TranscriptCourse.Outcome.PASSED, 1));

    AuditDtos.AuditResult result = assembler.assemble(PLAN, STUDENT);
    AuditDtos.AuditItem general = byRequired(result, 4.0);
    AuditDtos.AuditItem elective = byRequired(result, 24.0);

    assertEquals(AuditDtos.State.SATISFIED, general.state(), "已满足不会因未声明完整而变不满足");
    assertEquals(0.0, general.gapCredits());
    assertEquals(AuditDtos.State.UNKNOWN, elective.state(), "未满足的要求不能判确定缺口");
    assertNull(elective.gapCredits(), "未声明完整时缺口不能是确定数字");
    assertEquals(3.0, elective.earnedCredits());
    assertTrue(result.unknowns().stream()
        .anyMatch(i -> i.code().equals("TRANSCRIPT_COMPLETENESS_UNKNOWN")));
  }

  @Test
  @DisplayName("FAILED 是确定事实：记录完整时仍判 UNSATISFIED，缺口是确定数字，不因此变 UNKNOWN")
  void failedCourseGivesDefiniteGap() {
    requirementRepo.save(new Requirement(PLAN, "物理", 4.0));
    courseRepo.save(new Course("C12", "大物甲", 4.0, "物理"));
    transcript(true, row("C12", 4.0, TranscriptCourse.Outcome.FAILED, 1));

    AuditDtos.AuditResult result = assembler.assemble(PLAN, STUDENT);
    AuditDtos.AuditItem item = onlyItem(result);
    assertEquals(AuditDtos.State.UNSATISFIED, item.state());
    assertEquals(4.0, item.gapCredits());
    assertTrue(result.unknowns().stream().noneMatch(i -> i.code().startsWith("PENDING")),
        "FAILED 不应产生待定项");
  }

  private static AuditDtos.AuditItem byRequired(AuditDtos.AuditResult result, double required) {
    return result.requirements().stream()
        .filter(i -> i.requiredCredits() == required)
        .findFirst()
        .orElseThrow(() -> new AssertionError("没有 requiredCredits=" + required + " 的要求项"));
  }

  /** 按给定课程行写入一份学业记录（同一主体只有一份）。 */
  private Transcript transcript(boolean complete, TranscriptCourse... rows) {
    Transcript t = new Transcript(STUDENT);
    t.revise(PLAN, complete, Transcript.SourceKind.SYNTHETIC,
        Instant.parse("2025-09-01T00:00:00Z"), List.of(rows));
    return transcriptRepo.save(t);
  }

  private static TranscriptCourse row(String courseCode, Double credits,
                                      TranscriptCourse.Outcome outcome, int attempt) {
    return new TranscriptCourse(courseCode, attempt,
        credits == null ? null : BigDecimal.valueOf(credits).setScale(2),
        outcome, null);
  }
}
