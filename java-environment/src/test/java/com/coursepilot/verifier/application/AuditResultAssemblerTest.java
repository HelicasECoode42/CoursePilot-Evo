package com.coursepilot.verifier.application;

import static org.junit.jupiter.api.Assertions.*;

import com.coursepilot.verifier.persistence.entity.AcademicRecord;
import com.coursepilot.verifier.persistence.entity.Course;
import com.coursepilot.verifier.persistence.entity.Requirement;
import com.coursepilot.verifier.persistence.repo.AcademicRecordRepository;
import com.coursepilot.verifier.persistence.repo.CourseRepository;
import com.coursepilot.verifier.persistence.repo.RequirementRepository;
import com.coursepilot.verifier.web.dto.AuditDtos;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.transaction.annotation.Transactional;

/**
 * 契约形状的学业核对。重点是三条红线：
 *   - 学分未知的类别必须是 UNKNOWN，不能当 0 也不能算满足（AGENTS.md：unknown 不能通过）
 *   - 重修只计一次
 *   - 缺口为负时归零，不出现负数学分
 */
@SpringBootTest
@Transactional
class AuditResultAssemblerTest {

  @Autowired AuditResultAssembler assembler;
  @Autowired RequirementRepository requirementRepo;
  @Autowired CourseRepository courseRepo;
  @Autowired AcademicRecordRepository recordRepo;

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
    recordRepo.save(record("C1", true, 4.0, 1));

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
    recordRepo.save(record("C2", true, 3.0, 1));

    AuditDtos.AuditItem item = onlyItem(assembler.assemble(PLAN, STUDENT));
    assertEquals(AuditDtos.State.UNSATISFIED, item.state());
    assertEquals(21.0, item.gapCredits());
  }

  @Test
  @DisplayName("学分未知的类别必须是 UNKNOWN，不能当 0 算成缺口")
  void unknownCreditsBlockTheCategory() {
    requirementRepo.save(new Requirement(PLAN, "实践", 2.0));
    courseRepo.save(new Course("C3", "实践课", null, "实践"));
    recordRepo.save(record("C3", true, null, 1));

    AuditDtos.AuditResult result = assembler.assemble(PLAN, STUDENT);
    assertEquals(AuditDtos.State.UNKNOWN, onlyItem(result).state());
    assertTrue(result.unknowns().stream().anyMatch(i -> i.code().equals("CREDITS_UNKNOWN")));
  }

  @Test
  @DisplayName("重修只计一次，不重复累加学分")
  void retakeCountsOnce() {
    requirementRepo.save(new Requirement(PLAN, "数学", 4.0));
    courseRepo.save(new Course("C4", "高数", 4.0, "数学"));
    recordRepo.save(record("C4", true, 4.0, 1));
    recordRepo.save(record("C4", true, 4.0, 2));

    AuditDtos.AuditItem item = onlyItem(assembler.assemble(PLAN, STUDENT));
    assertEquals(4.0, item.earnedCredits(), "重修被重复累加了");
    assertEquals(AuditDtos.State.SATISFIED, item.state());
  }

  @Test
  @DisplayName("未通过的课程不计入已修学分")
  void failedCourseDoesNotCount() {
    requirementRepo.save(new Requirement(PLAN, "物理", 4.0));
    courseRepo.save(new Course("C5", "大物", 4.0, "物理"));
    recordRepo.save(record("C5", false, 4.0, 1));

    AuditDtos.AuditItem item = onlyItem(assembler.assemble(PLAN, STUDENT));
    assertEquals(0.0, item.earnedCredits());
    assertEquals(AuditDtos.State.UNSATISFIED, item.state());
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
  @DisplayName("完整性与修订号未建模时如实返回未确认，不填假值")
  void completenessIsReportedAsUnknown() {
    requirementRepo.save(new Requirement(PLAN, "通识", 1.0));
    AuditDtos.AuditResult result = assembler.assemble(PLAN, STUDENT);
    assertFalse(result.transcriptComplete());
    assertTrue(result.unknowns().stream()
        .anyMatch(i -> i.code().equals("TRANSCRIPT_COMPLETENESS_UNKNOWN")));
  }

  private AcademicRecord record(String courseCode, boolean passed, Double credits, int attempt) {
    AcademicRecord r = new AcademicRecord();
    r.setStudentId(STUDENT);
    r.setCourseCode(courseCode);
    r.setPassed(passed);
    r.setCreditsEarned(credits);
    r.setAttemptNo(attempt);
    return r;
  }
}
