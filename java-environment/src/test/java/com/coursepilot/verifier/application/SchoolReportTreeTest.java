package com.coursepilot.verifier.application;

import static org.junit.jupiter.api.Assertions.*;

import com.coursepilot.verifier.web.dto.SchoolProgressDtos;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/** 学校树（虚构数据，按真实嵌套形状构造）的同名取舍、读全判定与课程祖先归类。 */
class SchoolReportTreeTest {

  private static final Set<String> CURRICULUM = Set.of("公共基础课", "通识课", "必修", "专业选修");

  @Test
  @DisplayName("同名类别取最浅层：一级「公共基础课」采用，子节点同名的 54/54 被忽略")
  void shallowestSameNameWins() {
    SchoolReport report = SchoolReport.from(snapshot(List.of(
        node("root", null, "主修", null, null, null),
        node("pub", "root", "公共基础课", 98, 97, 1),
        node("pubChild", "pub", "公共基础课", 54, 54, 0)), List.of()));

    SchoolReport.Category c = report.category("公共基础课").orElseThrow();
    assertEquals(new BigDecimal("98"), c.required());
    assertEquals(new BigDecimal("97"), c.earned());
    assertEquals(new BigDecimal("1"), c.remaining());
  }

  @Test
  @DisplayName("同名且同为最浅层：视为歧义，不做类别映射")
  void sameShallowestDepthIsAmbiguous() {
    SchoolReport report = SchoolReport.from(snapshot(List.of(
        node("root", null, "主修", null, null, null),
        node("a", "root", "公共基础课", 10, 5, 5),
        node("b", "root", "公共基础课", 20, 5, 15)), List.of()));

    assertTrue(report.category("公共基础课").isEmpty());
  }

  @Test
  @DisplayName("纯分组节点（无学分数字）不阻止读全")
  void pureGroupingNodesDoNotBlockFullyRead() {
    SchoolReport report = SchoolReport.from(snapshot(List.of(
        node("root", null, "主修", null, null, null),
        node("other", null, "其他课程", null, null, null),
        node("pub", "root", "公共基础课", 98, 97, 1)),
        List.of(course("pub", "CS101", "PASSED", "3"))));
    assertTrue(report.fullyRead());
  }

  @Test
  @DisplayName("显示了部分学分数字的节点未读全：fullyRead 为 false")
  void partiallyShownNodeBlocksFullyRead() {
    SchoolReport report = SchoolReport.from(snapshot(List.of(
        node("root", null, "主修", null, null, null),
        node("pub", "root", "公共基础课", 98, null, 1)),
        List.of(course("pub", "CS101", "PASSED", "3"))));
    assertFalse(report.fullyRead());
  }

  @Test
  @DisplayName("课程状态未知仍不算读全")
  void unknownOutcomeBlocksFullyRead() {
    SchoolReport report = SchoolReport.from(snapshot(List.of(
        node("root", null, "主修", null, null, null),
        node("pub", "root", "公共基础课", 98, 97, 1)),
        List.of(course("pub", "CS101", "UNKNOWN", "3"))));
    assertFalse(report.fullyRead());
  }

  @Test
  @DisplayName("通选课 -> 人文社科类通识课 -> 通识课：沿祖先链归到培养类别「通识课」")
  void courseUnderSubNodeClassifiedByAncestor() {
    SchoolReport report = SchoolReport.from(snapshot(List.of(
        node("root", null, "主修", null, null, null),
        node("ge", "root", "通识课", 4, 2, 2),
        node("hss", "ge", "人文社科类通识课", null, null, null),
        node("tx", "hss", "通选课", null, null, null)),
        List.of(course("tx", "GE101", "PASSED", "2"))));
    assertEquals("通识课", report.categoryOfCourse("GE101", CURRICULUM));
  }

  @Test
  @DisplayName("体育1 挂在「体育」下、体育在「公共基础课」下：归到公共基础课（体育不是培养类别）")
  void peCourseClassifiedUnderPublicBasic() {
    SchoolReport report = SchoolReport.from(snapshot(List.of(
        node("root", null, "主修", null, null, null),
        node("pub", "root", "公共基础课", 98, 97, 1),
        node("pe", "pub", "体育", null, null, null),
        node("pe1", "pe", "体育1", null, null, null)),
        List.of(course("pe1", "PE001", "PASSED", "1"))));
    assertEquals("公共基础课", report.categoryOfCourse("PE001", CURRICULUM));
  }

  @Test
  @DisplayName("祖先链上没有培养类别：不归类")
  void noCurriculumAncestorGivesNull() {
    SchoolReport report = SchoolReport.from(snapshot(List.of(
        node("root", null, "其他课程", null, null, null),
        node("x", "root", "杂项", null, null, null)),
        List.of(course("x", "ZZ1", "PASSED", "1"))));
    assertNull(report.categoryOfCourse("ZZ1", CURRICULUM));
  }

  @Test
  @DisplayName("同一课程在两处分别归到不同培养类别：视为歧义")
  void conflictingAncestorsGiveNull() {
    SchoolReport report = SchoolReport.from(snapshot(List.of(
        node("root", null, "主修", null, null, null),
        node("pub", "root", "公共基础课", 98, 97, 1),
        node("y", "pub", "杂项二", null, null, null),
        node("elective", "root", "专业选修", 10, 0, 10)),
        List.of(course("y", "ZZ2", "PASSED", "1"),
                course("elective", "ZZ2", "PASSED", "1"))));
    assertNull(report.categoryOfCourse("ZZ2", CURRICULUM));
  }

  private static SchoolProgressDtos.Snapshot snapshot(List<SchoolProgressDtos.Node> nodes,
                                                      List<SchoolProgressDtos.Course> courses) {
    return new SchoolProgressDtos.Snapshot("coursepilot-shu-academic-progress", 1,
        Instant.parse("2026-10-29T00:00:00Z"), "synthetic fixture", nodes, courses);
  }

  private static SchoolProgressDtos.Node node(String id, String parent, String name,
                                              Integer required, Integer earned, Integer remaining) {
    return new SchoolProgressDtos.Node(id, parent, "s-" + id, true, name,
        dec(required), dec(earned), dec(remaining));
  }

  /** 课程挂在学校节点 nodeId 下。 */
  private static SchoolProgressDtos.Course course(String nodeId, String code, String outcome,
                                                  String credits) {
    return new SchoolProgressDtos.Course(nodeId, code, "虚构" + code, new BigDecimal(credits),
        outcome, null, null, null, null, null, null, null);
  }

  private static BigDecimal dec(Integer v) {
    return v == null ? null : BigDecimal.valueOf(v);
  }
}
