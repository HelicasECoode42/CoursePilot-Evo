import { describe, expect, it } from "vitest";
import type { AuditItem, CompletedCourse } from "../contracts";
import {
  buildRecordInput,
  describeCompleteness,
  duplicateCourseCodes,
  groupAuditItems,
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
