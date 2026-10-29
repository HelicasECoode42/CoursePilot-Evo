import { describe, expect, it } from "vitest";
import { schoolProgressFromBridge } from "./school-progress";

const base = {
  format: "coursepilot-shu-academic-progress",
  version: 1,
  capturedAt: "2026-10-29T00:00:00Z",
  source: "fictional fixture",
  nodes: [
    {
      nodeId: "parent",
      parentId: null,
      schoolNodeId: "98",
      leaf: false,
      name: "公共基础课",
      requiredCredits: 12,
      earnedCredits: 6,
      remainingCredits: 6,
    },
    {
      nodeId: "child",
      parentId: "parent",
      schoolNodeId: "54",
      leaf: true,
      name: "公共基础课",
      requiredCredits: 4,
      earnedCredits: 2,
      remainingCredits: 2,
    },
  ],
  courses: [
    {
      nodeId: "child",
      courseCode: "CS001",
      name: "虚构课程",
      credits: 2,
      outcome: "UNKNOWN",
      completedYear: null,
      completedTerm: null,
      grade: null,
      makeup: null,
      retake: null,
      suggestedYear: null,
      suggestedTerm: null,
    },
  ],
  // The installed extension retains this summary alias for its download preview;
  // the POST payload mapper must strip it because the backend schema is closed.
  categories: [
    {
      name: "公共基础课",
      requiredCredits: 12,
      earnedCredits: 6,
      remainingCredits: 6,
    },
  ],
};

describe("school progress bridge mapping", () => {
  it("retains same-named parent and child nodes and UNKNOWN course outcomes", () => {
    const snapshot = schoolProgressFromBridge(base);
    expect(
      snapshot.nodes.map((node) => [
        node.nodeId,
        node.parentId,
        node.schoolNodeId,
      ]),
    ).toEqual([
      ["parent", null, "98"],
      ["child", "parent", "54"],
    ]);
    expect(snapshot.courses[0]?.outcome).toBe("UNKNOWN");
    expect(snapshot).not.toHaveProperty("categories");
    expect(snapshot.nodes[0]).not.toHaveProperty("categories");
  });

  it("rejects broken parent references and unrecognized outcomes", () => {
    expect(() =>
      schoolProgressFromBridge({
        ...base,
        nodes: [base.nodes[0], { ...base.nodes[1], parentId: "missing" }],
      }),
    ).toThrow("类别父子关系不完整");
    expect(() =>
      schoolProgressFromBridge({
        ...base,
        courses: [{ ...base.courses[0], outcome: "PASSED_BY_GRADE" }],
      }),
    ).toThrow("课程明细格式不正确");
  });
});
