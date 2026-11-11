import { describe, expect, it } from "vitest";
import type { SchoolProgressNode } from "./school-progress";
import {
  courseDisplayName,
  groupLearnedCourses,
  nodePathLabel,
  summarizeAuditUnknowns,
  usableName,
  UNREAD_CATEGORY_NAME,
  UNREAD_COURSE_NAME,
} from "./school-categories";

const node = (
  nodeId: string,
  parentId: string | null,
  name: string,
): SchoolProgressNode => ({
  nodeId,
  parentId,
  schoolNodeId: null,
  leaf: false,
  name,
  requiredCredits: null,
  earnedCredits: null,
  remainingCredits: null,
});

describe("名字是否读到", () => {
  it("空串、空白和只剩括号的名字都算没读到", () => {
    expect(usableName("")).toBeNull();
    expect(usableName("   ")).toBeNull();
    expect(usableName("()")).toBeNull();
    expect(usableName(null)).toBeNull();
    expect(usableName(" 通识课 ")).toBe("通识课");
    expect(usableName("1")).toBe("1");
  });
});

describe("类别路径", () => {
  it("每一层都带上名字；上级读不出名字时仍写明未读出", () => {
    const nodes = [
      node("a", null, ""),
      node("b", "a", "思想政治理论课"),
      node("c", "b", ""),
    ];
    expect(nodePathLabel("c", nodes)).toBe(
      `${UNREAD_CATEGORY_NAME} › 思想政治理论课 › ${UNREAD_CATEGORY_NAME}`,
    );
  });

  it("循环父子关系不会死循环", () => {
    const nodes = [node("a", "b", "甲"), node("b", "a", "乙")];
    expect(nodePathLabel("a", nodes)).toBe("乙 › 甲");
  });
});

describe("课程名", () => {
  it("学校报告没有名字时用课程目录补，都没有就写未读出", () => {
    const lookup = (code: string) => (code === "CS1" ? "高等数学" : null);
    expect(courseDisplayName("CS1", "", lookup)).toBe("高等数学");
    expect(courseDisplayName("CS2", "", lookup)).toBe(UNREAD_COURSE_NAME);
    expect(courseDisplayName("CS2", "学校名", lookup)).toBe("学校名");
  });
});

describe("我学了什么按类别分组", () => {
  const nodes = [
    node("gen", null, "通识课"),
    node("gen-sub", "gen", ""),
    node("pe", null, "体育"),
  ];
  const courses = [
    {
      nodeId: "gen-sub",
      courseCode: "G001",
      name: "",
      credits: 2,
      outcome: "PASSED" as const,
      completedYear: null,
      completedTerm: null,
      grade: null,
      makeup: null,
      retake: null,
      suggestedYear: null,
      suggestedTerm: null,
    },
    {
      nodeId: "pe",
      courseCode: "P001",
      name: "体育1",
      credits: null,
      outcome: "IN_PROGRESS" as const,
      completedYear: null,
      completedTerm: null,
      grade: null,
      makeup: null,
      retake: null,
      suggestedYear: null,
      suggestedTerm: null,
    },
  ];

  it("按课程挂靠的类别分组，状态用已修/在读/未通过", () => {
    const groups = groupLearnedCourses({
      nodes,
      courses,
      recordCourses: [],
      lookupName: () => null,
    });
    expect(groups.map((group) => group.label)).toEqual([
      `通识课 › ${UNREAD_CATEGORY_NAME}`,
      "体育",
    ]);
    expect(groups[0]?.items[0]).toEqual({
      courseCode: "G001",
      name: UNREAD_COURSE_NAME,
      credits: 2,
      statusLabel: "已修",
    });
    expect(groups[1]?.items[0]?.statusLabel).toBe("在读");
  });

  it("没有类别归属或学校报告没有的课程放进最后的「其他」", () => {
    const groups = groupLearnedCourses({
      nodes,
      courses: [{ ...courses[1]!, nodeId: "missing" }],
      recordCourses: [
        { courseCode: "P001", earnedCredits: null, outcome: "PASSED" },
        { courseCode: "X999", earnedCredits: 3, outcome: "FAILED" },
      ],
      lookupName: (code) => (code === "X999" ? "手动补录课" : null),
    });
    expect(groups.map((group) => group.label)).toEqual(["其他"]);
    expect(groups[0]?.items.map((item) => item.courseCode)).toEqual([
      "P001",
      "X999",
    ]);
    expect(groups[0]?.items[1]?.name).toBe("手动补录课");
    expect(groups[0]?.items[1]?.statusLabel).toBe("未通过");
  });

  it("只有学业记录、没有学校报告时全部归入其他", () => {
    const groups = groupLearnedCourses({
      nodes: [],
      courses: [],
      recordCourses: [
        { courseCode: "A1", earnedCredits: 2, outcome: "PASSED" },
      ],
    });
    expect(groups).toHaveLength(1);
    expect(groups[0]?.label).toBe("其他");
  });
});

describe("本地核对无法确认项的分组摘要", () => {
  const issue = (code: string, message: string) => ({
    code,
    message,
    field: "completedCourses",
    retryable: false,
  });

  it("把不在课程库、在读、规则、其他分开计数，并给出一段摘要", () => {
    const unknowns = [
      issue("COURSE_NOT_IN_CATALOG", "课程 A1 不在课程库中，无法归类"),
      issue("COURSE_NOT_IN_CATALOG", "课程 A2 不在课程库中，无法归类"),
      issue(
        "PENDING_COURSE",
        "课程 B1 在修或结果未知，通识 类别的缺口不能确定",
      ),
      issue(
        "UNMODELED_CURRICULUM_RULES",
        "本培养方案有 6 条规则系统未建模、不参与核验（原表位置：规则表第1行）",
      ),
      issue("CREDITS_UNKNOWN", "课程 C1 学分未知"),
    ];
    const names: Record<string, string> = { A1: "大学英语" };
    const summary = summarizeAuditUnknowns(
      { unknowns, transcriptComplete: false },
      (code) => names[code] ?? null,
    );
    expect(summary.headline.startsWith("本地核对暂无法给出结论：")).toBe(true);
    expect(summary.headline).toContain("① 2 门课无法归入");
    expect(summary.headline).toContain("② 1 门在读或结果未知的课程尚未出成绩");
    expect(summary.headline).toContain("③ 尚未勾选「记录已完整」");
    expect(summary.headline).toContain("④ 6 条培养方案规则需人工确认");
    expect(summary.headline).toContain("⑤ 1 项其他无法确认");
    const catalog = summary.groups.find(
      (group) => group.key === "not-in-catalog",
    );
    expect(catalog?.courses).toEqual([
      { courseCode: "A1", name: "大学英语" },
      { courseCode: "A2", name: null },
    ]);
  });

  it("记录已完整且没有未知项时直说没有", () => {
    const summary = summarizeAuditUnknowns(
      { unknowns: [], transcriptComplete: true },
      () => null,
    );
    expect(summary.groups).toEqual([]);
    expect(summary.headline).toBe("本地核对没有报告无法确认的项目。");
  });
});
