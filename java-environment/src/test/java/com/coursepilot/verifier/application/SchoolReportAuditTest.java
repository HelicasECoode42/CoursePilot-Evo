package com.coursepilot.verifier.application;

import static org.junit.jupiter.api.Assertions.*;

import com.coursepilot.verifier.persistence.entity.Course;
import com.coursepilot.verifier.persistence.entity.CurriculumCourse;
import com.coursepilot.verifier.persistence.entity.CurriculumSnapshot;
import com.coursepilot.verifier.persistence.entity.Requirement;
import com.coursepilot.verifier.persistence.entity.SchoolProgressSnapshot;
import com.coursepilot.verifier.persistence.entity.Transcript;
import com.coursepilot.verifier.persistence.entity.TranscriptCourse;
import com.coursepilot.verifier.persistence.repo.CourseRepository;
import com.coursepilot.verifier.persistence.repo.CurriculumCourseRepository;
import com.coursepilot.verifier.persistence.repo.CurriculumSnapshotRepository;
import com.coursepilot.verifier.persistence.repo.RequirementRepository;
import com.coursepilot.verifier.persistence.repo.SchoolProgressSnapshotRepository;
import com.coursepilot.verifier.persistence.repo.TranscriptRepository;
import com.coursepilot.verifier.web.dto.AuditDtos;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;

/**
 * 学校报告与本地核对的衔接（owner 决定：本地核对必须与导入的学校报告同步）。
 *   - 在读课不计学分、不让类别判 UNKNOWN
 *   - 学校同名类别直接采用学校口径（SCHOOL_REPORT），课程不在课程库也不影响
 *   - 课程不在课程库但学校报告给出类别：按学校类别归类，不再报「无法归类」
 *   - 学校导入读全：学业记录按完整处理，并标注依据
 *   - 没有同名类别：回退本地核对（LOCAL）
 */
@SpringBootTest
@Transactional
class SchoolReportAuditTest {

  @Autowired AuditResultAssembler assembler;
  @Autowired RequirementRepository requirementRepo;
  @Autowired CourseRepository courseRepo;
  @Autowired TranscriptRepository transcriptRepo;
  @Autowired CurriculumSnapshotRepository snapshotRepo;
  @Autowired CurriculumCourseRepository curriculumCourses;
  @Autowired SchoolProgressSnapshotRepository schoolSnapshots;

  private static final String PLAN = "plan-school";
  private static final String STUDENT = "stu-school";
  private static final String NODE_PE = "{\"nodeId\":\"pe\",\"parentId\":null,\"schoolNodeId\":\"1\",\"leaf\":true,"
      + "\"name\":\"体育\",\"requiredCredits\":6,\"earnedCredits\":6,\"remainingCredits\":0}";

  @BeforeEach
  void createTestSnapshot() {
    if (snapshotRepo.findById(PLAN).isEmpty()) {
      snapshotRepo.save(new CurriculumSnapshot(PLAN, CurriculumSnapshot.Kind.CURRICULUM,
          CurriculumSnapshot.State.PUBLISHED, CurriculumSnapshot.SourceKind.SYNTHETIC,
          CurriculumSnapshot.SourceValidation.SYNTHETIC, null, Instant.parse("2025-09-01T00:00:00Z")));
    }
  }

  @Test
  @DisplayName("学校同名类别直接采用学校学分：课程不在课程库也能判满足，source=SCHOOL_REPORT")
  void schoolCategoryDecidesEvenWhenCoursesAreNotInCatalog() {
    requirementRepo.save(new Requirement(PLAN, "体育", 6.0));
    saveSchool(STUDENT, "[" + NODE_PE + "]",
        course("PE1", "pe", "PASSED", 2) + "," + course("PE2", "pe", "PASSED", 2) + ","
            + course("PE3", "pe", "PASSED", 2));
    transcript(true, row("PE1", 2.0, TranscriptCourse.Outcome.PASSED, 1),
        row("PE2", 2.0, TranscriptCourse.Outcome.PASSED, 1),
        row("PE3", 2.0, TranscriptCourse.Outcome.PASSED, 1));

    AuditDtos.AuditResult result = assembler.assemble(PLAN, STUDENT);
    AuditDtos.AuditItem item = onlyItem(result);
    assertEquals(AuditDtos.State.SATISFIED, item.state());
    assertEquals(0.0, item.gapCredits());
    assertEquals(6.0, item.earnedCredits());
    assertEquals(6.0, item.requiredCredits());
    assertEquals(AuditDtos.Source.SCHOOL_REPORT, item.source());
    assertEquals(List.of("PE1", "PE2", "PE3"), item.courseCodes());
    assertTrue(result.unknowns().stream().noneMatch(i -> i.code().equals("COURSE_NOT_IN_CATALOG")),
        "学校已给出类别的课程不应报「无法归类」");
  }

  @Test
  @DisplayName("学校同名类别未修满：UNSATISFIED，缺口取学校剩余学分，在读学分单列")
  void schoolCategoryReportsSchoolRemainingAndInProgress() {
    requirementRepo.save(new Requirement(PLAN, "体育", 6.0));
    String node = "{\"nodeId\":\"pe\",\"parentId\":null,\"schoolNodeId\":\"1\",\"leaf\":true,"
        + "\"name\":\"体育\",\"requiredCredits\":6,\"earnedCredits\":2,\"remainingCredits\":4}";
    saveSchool(STUDENT, "[" + node + "]", course("PE5", "pe", "PASSED", 2) + ","
        + course("PE6", "pe", "IN_PROGRESS", 2));
    transcript(true, row("PE5", 2.0, TranscriptCourse.Outcome.PASSED, 1),
        row("PE6", null, TranscriptCourse.Outcome.IN_PROGRESS, 1));

    AuditDtos.AuditItem item = onlyItem(assembler.assemble(PLAN, STUDENT));
    assertEquals(AuditDtos.State.UNSATISFIED, item.state());
    assertEquals(4.0, item.gapCredits());
    assertEquals(2.0, item.earnedCredits());
    assertEquals(2.0, item.inProgressCredits(), "在读课学分取自学校报告，不计入已修");
    assertEquals(AuditDtos.Source.SCHOOL_REPORT, item.source());
  }

  @Test
  @DisplayName("培养方案不匹配的学校报告不参与核对")
  void schoolReportFromDifferentCurriculumIsIgnored() {
    requirementRepo.save(new Requirement(PLAN, "体育", 6.0));
    saveSchool(STUDENT, "[" + NODE_PE + "]", course("PE10", "pe", "PASSED", 2), "plan-other");
    transcript(false, row("PE1", 2.0, TranscriptCourse.Outcome.PASSED, 1));

    AuditDtos.AuditResult result = assembler.assemble(PLAN, STUDENT);
    AuditDtos.AuditItem item = onlyItem(result);
    assertEquals(AuditDtos.Source.LOCAL, item.source());
    assertEquals(AuditDtos.State.UNKNOWN, item.state());
    assertFalse(result.transcriptComplete());
  }

  @Test
  @DisplayName("课程不在课程库，但学校报告给出类别：按学校类别归类，本地类别也能满足")
  void courseOutsideCatalogIsClassifiedBySchoolLink() {
    requirementRepo.save(new Requirement(PLAN, "实践", 2.0));
    // 学校有同名「实践」节点但学分未读全（没有 remaining），所以不走学校口径，只借用归类。
    String node = "{\"nodeId\":\"sj\",\"parentId\":null,\"schoolNodeId\":\"9\",\"leaf\":true,"
        + "\"name\":\"实践\",\"requiredCredits\":null,\"earnedCredits\":null,\"remainingCredits\":null}";
    saveSchool(STUDENT, "[" + NODE_PE + "," + node + "]", course("XP1", "sj", "PASSED", 2));
    transcript(true, row("XP1", 2.0, TranscriptCourse.Outcome.PASSED, 1));

    AuditDtos.AuditResult result = assembler.assemble(PLAN, STUDENT);
    AuditDtos.AuditItem item = onlyItem(result);
    assertEquals(AuditDtos.State.SATISFIED, item.state());
    assertEquals(AuditDtos.Source.LOCAL, item.source());
    assertEquals(List.of("XP1"), item.courseCodes());
    assertTrue(result.unknowns().stream().noneMatch(i -> i.code().equals("COURSE_NOT_IN_CATALOG")));
  }

  @Test
  @DisplayName("学校导入读全：学业记录按完整处理，依据标为 SCHOOL_IMPORT_FULL，未满足的要求给出确定缺口")
  void fullyReadImportMakesTranscriptComplete() {
    requirementRepo.save(new Requirement(PLAN, "必修", 10.0));
    course("CM1", "必修课", 3.0, "必修");
    saveSchool(STUDENT, "[" + NODE_PE + "]", course("PE7", "pe", "PASSED", 2));
    transcript(false, row("CM1", 3.0, TranscriptCourse.Outcome.PASSED, 1));

    AuditDtos.AuditResult result = assembler.assemble(PLAN, STUDENT);
    assertTrue(result.transcriptComplete());
    assertEquals(AuditDtos.TranscriptCompleteSource.SCHOOL_IMPORT_FULL, result.transcriptCompleteSource());
    assertTrue(result.unknowns().stream().noneMatch(i -> i.code().equals("TRANSCRIPT_COMPLETENESS_UNKNOWN")));
    AuditDtos.AuditItem item = onlyItem(result);
    assertEquals(AuditDtos.State.UNSATISFIED, item.state(), "完整后未满足即为确定缺口");
    assertEquals(7.0, item.gapCredits());
  }

  @Test
  @DisplayName("学校类别缺少任一学分字段时不视为读全")
  void missingEarnedCreditsPreventCompleteness() {
    requirementRepo.save(new Requirement(PLAN, "体育", 6.0));
    String node = "{\"nodeId\":\"pe\",\"parentId\":null,\"schoolNodeId\":\"1\",\"leaf\":true,"
        + "\"name\":\"体育\",\"requiredCredits\":6,\"earnedCredits\":null,\"remainingCredits\":4}";
    saveSchool(STUDENT, "[" + node + "]", course("PE11", "pe", "PASSED", 2));
    transcript(false, row("PE11", 2.0, TranscriptCourse.Outcome.PASSED, 1));

    AuditDtos.AuditResult result = assembler.assemble(PLAN, STUDENT);
    assertFalse(result.transcriptComplete());
    assertNull(result.transcriptCompleteSource());
    AuditDtos.AuditItem item = onlyItem(result);
    assertEquals(AuditDtos.Source.LOCAL, item.source());
    assertEquals(AuditDtos.State.UNKNOWN, item.state());
    assertNull(item.gapCredits());
  }

  @Test
  @DisplayName("学校报告含未知课程状态：不算读全，仍按手动勾选")
  void partiallyReadImportKeepsManualCompleteness() {
    requirementRepo.save(new Requirement(PLAN, "必修", 10.0));
    course("CM2", "必修课", 3.0, "必修");
    saveSchool(STUDENT, "[" + NODE_PE + "]", course("PE8", "pe", "UNKNOWN", 2));
    transcript(false, row("CM2", 3.0, TranscriptCourse.Outcome.PASSED, 1));

    AuditDtos.AuditResult result = assembler.assemble(PLAN, STUDENT);
    assertFalse(result.transcriptComplete());
    assertNull(result.transcriptCompleteSource());
    assertTrue(result.unknowns().stream().anyMatch(i -> i.code().equals("TRANSCRIPT_COMPLETENESS_UNKNOWN")));
    assertEquals(AuditDtos.State.UNKNOWN, onlyItem(result).state());
  }

  @Test
  @DisplayName("没有同名学校类别：回退本地核对，source=LOCAL")
  void noSchoolMatchFallsBackToLocal() {
    requirementRepo.save(new Requirement(PLAN, "通识", 4.0));
    course("GE1", "通识课", 4.0, "通识");
    saveSchool(STUDENT, "[" + NODE_PE + "]", course("PE9", "pe", "PASSED", 2));
    transcript(true, row("GE1", 4.0, TranscriptCourse.Outcome.PASSED, 1));

    AuditDtos.AuditItem item = onlyItem(assembler.assemble(PLAN, STUDENT));
    assertEquals(AuditDtos.State.SATISFIED, item.state());
    assertEquals(4.0, item.earnedCredits());
    assertEquals(AuditDtos.Source.LOCAL, item.source());
    assertEquals(0.0, item.inProgressCredits());
  }

  private AuditDtos.AuditItem onlyItem(AuditDtos.AuditResult result) {
    assertEquals(1, result.requirements().size(), "本用例只种了一条要求");
    return result.requirements().get(0);
  }

  private void saveSchool(String subject, String nodesJson, String coursesJson) {
    saveSchool(subject, nodesJson, coursesJson, PLAN);
  }

  private void saveSchool(String subject, String nodesJson, String coursesJson, String reportCurriculumId) {
    String snapshotJson = "{\"format\":\"coursepilot-shu-academic-progress\",\"version\":1,"
        + "\"capturedAt\":\"2026-10-29T00:00:00Z\",\"source\":\"synthetic fixture\","
        + "\"nodes\":" + nodesJson + ",\"courses\":[" + coursesJson + "]}";
    schoolSnapshots.save(new SchoolProgressSnapshot(UUID.randomUUID().toString(), subject,
        UUID.randomUUID().toString().replace("-", ""), Instant.now(), snapshotJson,
        "{\"curriculumSnapshotId\":\"" + reportCurriculumId + "\"}"));
  }

  private static String course(String code, String nodeId, String outcome, int credits) {
    return "{\"nodeId\":\"" + nodeId + "\",\"courseCode\":\"" + code + "\",\"name\":\"虚构" + code
        + "\",\"credits\":" + credits + ",\"outcome\":\"" + outcome + "\",\"completedYear\":null,"
        + "\"completedTerm\":null,\"grade\":null,\"makeup\":null,\"retake\":null,"
        + "\"suggestedYear\":null,\"suggestedTerm\":null}";
  }

  private Transcript transcript(boolean complete, TranscriptCourse... rows) {
    Transcript t = new Transcript(STUDENT);
    t.revise(PLAN, complete, Transcript.SourceKind.SYNTHETIC,
        Instant.parse("2025-09-01T00:00:00Z"), List.of(rows));
    return transcriptRepo.save(t);
  }

  private static TranscriptCourse row(String courseCode, Double credits,
                                      TranscriptCourse.Outcome outcome, int attempt) {
    return new TranscriptCourse(courseCode, attempt,
        credits == null ? null : BigDecimal.valueOf(credits).setScale(2), outcome, null);
  }

  private void course(String code, String name, Double credits, String category) {
    Course saved = courseRepo.findById(code).orElseGet(() -> courseRepo.save(
        new Course(code, name, credits, category)));
    curriculumCourses.save(new CurriculumCourse(snapshotRepo.getReferenceById(PLAN), saved,
        name, credits, category, "SYNTHETIC", "synthetic:" + PLAN + ":" + code,
        "synthetic test fixture " + code, Instant.parse("2025-09-01T00:00:00Z")));
  }
}
