import { describe, expect, it } from "vitest";
import type { AuditItem, AuditResult, CompletedCourse } from "../contracts";
import {
  auditSourceLabel,
  buildRecordInput,
  describeCompleteness,
  duplicateCourseCodes,
  groupAuditItems,
  inProgressNote,
  inProgressSummary,
  needsCompleteCheckbox,
  recordSourceLabel,
} from "./academic-record";

function item(requirementId: string, state: AuditItem["state"]): AuditItem {
  return {
    requirementId,
    // 这个 helper 测的是分组逻辑，类别名无关；显式给 null 以证明「没有类别时退回序号」也要能跑。
    category: null,
    courseCodes: [],
    requiredCredits: null,
    earnedCredits: null,
    gapCredits: null,
    state,
    sourceRefIds: [],
  };
}

describe("groupAuditItems", () => {
  it("orders groups as gap, unknown, satisfied", () => {
    const groups = groupAuditItems([
      item("req:satisfied", "SATISFIED"),
      item("req:unknown", "UNKNOWN"),
      item("req:gap", "UNSATISFIED"),
    ]);
    expect(groups.map((group) => group.key)).toEqual([
      "unsatisfied",
      "unknown",
      "satisfied",
    ]);
  });

  it("never places an UNKNOWN item in the satisfied group", () => {
    const groups = groupAuditItems([item("req:unknown", "UNKNOWN")]);
    expect(groups).toHaveLength(1);
    expect(groups[0].key).toBe("unknown");
    expect(groups[0].items.map((entry) => entry.requirementId)).toEqual([
      "req:unknown",
    ]);
  });

  it("omits empty groups", () => {
    const groups = groupAuditItems([item("req:gap", "UNSATISFIED")]);
    expect(groups.map((group) => group.key)).toEqual(["unsatisfied"]);
  });

  it("returns nothing for an empty audit", () => {
    expect(groupAuditItems([])).toEqual([]);
  });
});

describe("describeCompleteness", () => {
  it("warns that incomplete records produce unknown items", () => {
    expect(describeCompleteness({ transcriptComplete: false })).toContain(
      "无法确认",
    );
  });

  it("states completeness when the student declared it", () => {
    expect(describeCompleteness({ transcriptComplete: true })).toContain(
      "已声明记录完整",
    );
  });
});

describe("duplicateCourseCodes", () => {
  const course = (code: string): CompletedCourse => ({
    courseCode: code,
    earnedCredits: null,
    outcome: "PASSED",
    completedTerm: null,
  });

  it("finds repeated codes after trimming", () => {
    expect(duplicateCourseCodes([course("CS101"), course(" CS101 ")])).toEqual([
      "CS101",
    ]);
  });

  it("ignores blank rows so half-filled drafts are not reported", () => {
    expect(duplicateCourseCodes([course(""), course("  ")])).toEqual([]);
  });

  it("reports each duplicate once", () => {
    expect(
      duplicateCourseCodes([course("A"), course("A"), course("A")]),
    ).toEqual(["A"]);
  });
});

describe("buildRecordInput", () => {
  it("trims codes, keeps unknown credits as null and marks USER_IMPORT", () => {
    const input = buildRecordInput(
      "curriculum-1",
      [
        {
          courseCode: "  MATH201 ",
          earnedCredits: null,
          outcome: "IN_PROGRESS",
          completedTerm: null,
        },
      ],
      false,
    );
    expect(input).toEqual({
      schemaVersion: "1.0",
      curriculumSnapshotId: "curriculum-1",
      completedCourses: [
        {
          courseCode: "MATH201",
          earnedCredits: null,
          outcome: "IN_PROGRESS",
          completedTerm: null,
        },
      ],
      transcriptComplete: false,
      sourceKind: "USER_IMPORT",
    });
  });

  it("does not alias the caller's array", () => {
    const courses: CompletedCourse[] = [
      {
        courseCode: "A",
        earnedCredits: 1,
        outcome: "PASSED",
        completedTerm: null,
      },
    ];
    const input = buildRecordInput("curriculum-1", courses, true);
    expect(input.completedCourses).not.toBe(courses);
  });
});

describe("recordSourceLabel", () => {
  it("手动补录（USER_IMPORT）标为手动补录，不叫虚构数据", () => {
    expect(recordSourceLabel("USER_IMPORT", false)).toBe("手动补录");
  });

  it("学校进度导入的记录单独说明", () => {
    expect(recordSourceLabel("USER_IMPORT", true)).toBe("学校进度导入");
  });

  it("只有 SYNTHETIC 才是虚构数据", () => {
    expect(recordSourceLabel("SYNTHETIC", false)).toBe("虚构数据");
    expect(recordSourceLabel("SYNTHETIC", true)).toBe("虚构数据");
  });
});

/** 形状与 Java AuditResult 一致（虚构数值）：来源、在读学分和完整性依据都来自学校报告同步。 */
const syncedAudit: AuditResult = {
  curriculumSnapshotId: "curr-fake",
  academicRecordId: "rec-fake",
  recordRevision: 2,
  transcriptComplete: true,
  transcriptCompleteSource: "SCHOOL_IMPORT_FULL",
  requirements: [
    {
      requirementId: "req-a",
      category: "学科基础课",
      courseCodes: [],
      requiredCredits: 40,
      earnedCredits: 6,
      gapCredits: 34,
      state: "UNSATISFIED",
      sourceRefIds: ["ref-a"],
      source: "SCHOOL_REPORT",
      inProgressCredits: 0,
    },
    {
      requirementId: "req-b",
      category: "专业选修课",
      courseCodes: ["FAKE-EL-01"],
      requiredCredits: 20,
      earnedCredits: 3,
      gapCredits: 17,
      state: "UNSATISFIED",
      sourceRefIds: ["ref-b"],
      source: "SCHOOL_REPORT",
      inProgressCredits: 3,
    },
    {
      requirementId: "req-c",
      category: "通识课",
      courseCodes: [],
      requiredCredits: 10,
      earnedCredits: 10,
      gapCredits: 0,
      state: "SATISFIED",
      sourceRefIds: ["ref-c"],
      source: "LOCAL",
      inProgressCredits: 0,
    },
  ],
  suggestedCourseCodes: [],
  unknowns: [],
};

describe("学校报告同步后的核对展示", () => {
  it("来源标签区分学校报告与本地核对，缺省按本地", () => {
    expect(auditSourceLabel({ source: "SCHOOL_REPORT" })).toBe("按学校报告");
    expect(auditSourceLabel({ source: "LOCAL" })).toBe("本地核对");
    expect(auditSourceLabel({})).toBe("本地核对");
  });

  it("在读学分单独汇总，不并入已获学分，并以分计算避免小数误差", () => {
    expect(inProgressSummary(syncedAudit.requirements)).toEqual({
      credits: 3,
      unknownCount: 0,
    });
    expect(
      inProgressSummary([
        { inProgressCredits: 0.1 },
        { inProgressCredits: 0.2 },
        { inProgressCredits: null },
      ]),
    ).toEqual({ credits: 0.3, unknownCount: 1 });
  });

  it("有在读学分时给出一句说明，没有时不占行", () => {
    expect(inProgressNote(syncedAudit.requirements)).toBe(
      "另有 3 学分在读，尚未计入已获学分",
    );
    expect(
      inProgressNote([{ inProgressCredits: 0 }, { inProgressCredits: 0 }]),
    ).toBeNull();
    expect(inProgressNote([{ inProgressCredits: null }])).toBe(
      "部分类别的在读学分待确认",
    );
  });

  it("学校导入已读全时说明按完整记录核对，且不再要求手动勾选", () => {
    expect(describeCompleteness(syncedAudit)).toBe(
      "学校导入已读全，按完整记录核对。",
    );
    expect(needsCompleteCheckbox(syncedAudit)).toBe(false);
  });

  it("手动声明或未声明完整时仍保留勾选入口", () => {
    const manual: AuditResult = {
      ...syncedAudit,
      transcriptComplete: true,
      transcriptCompleteSource: "MANUAL",
    };
    expect(describeCompleteness(manual)).toBe("已声明记录完整。");
    expect(needsCompleteCheckbox(manual)).toBe(false);

    const undeclared: AuditResult = {
      ...syncedAudit,
      transcriptComplete: false,
      transcriptCompleteSource: null,
    };
    expect(needsCompleteCheckbox(undeclared)).toBe(true);
    expect(describeCompleteness(undeclared)).toContain("未声明完整");
  });
});
