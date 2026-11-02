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

describe("拒绝的原因要能看出是哪一项", () => {
  // 扩展 extract.js 真实返回的形状：注意它还多带一个 categories 字段。
  const fromExtension = () => ({
    format: "coursepilot-shu-academic-progress",
    version: 1,
    capturedAt: "2026-10-29T12:00:00.000Z",
    source: "上海大学学生学业情况查询",
    nodes: [
      {
        nodeId: "node-1",
        parentId: null,
        schoolNodeId: "98",
        leaf: true,
        name: "公共基础课",
        requiredCredits: 36,
        earnedCredits: 12,
        remainingCredits: 24,
      },
    ],
    categories: [
      {
        nodeId: "node-1",
        parentId: null,
        schoolNodeId: "98",
        leaf: true,
        name: "公共基础课",
        requiredCredits: 36,
        earnedCredits: 12,
        remainingCredits: 24,
      },
    ],
    courses: [
      {
        nodeId: "node-1",
        courseCode: "01064246",
        name: "大学化学",
        credits: 2,
        outcome: "PASSED",
        completedYear: "2025-2026",
        completedTerm: "1",
        grade: null,
        makeup: null,
        retake: null,
        suggestedYear: null,
        suggestedTerm: null,
      },
    ],
  });

  it("扩展导出的原样文件能通过（含它多带的 categories 字段）", () => {
    const snapshot = schoolProgressFromBridge(fromExtension());
    expect(snapshot.nodes).toHaveLength(1);
    expect(snapshot.courses[0].courseCode).toBe("01064246");
  });

  it("format 不对时说出读到的是什么", () => {
    const bad = { ...fromExtension(), format: "something-else" };
    expect(() => schoolProgressFromBridge(bad)).toThrowError(/something-else/);
  });

  it("version 不对时点名 version，而不是笼统说格式不正确", () => {
    const bad = { ...fromExtension(), version: 2 };
    expect(() => schoolProgressFromBridge(bad)).toThrowError(/version/);
  });

  it("类别树为空时说清多半是页面没加载完", () => {
    const bad = { ...fromExtension(), nodes: [] };
    expect(() => schoolProgressFromBridge(bad)).toThrowError(/还没加载完/);
  });

  it("缺 courses 时点名 courses", () => {
    const bad = { ...fromExtension() } as Record<string, unknown>;
    delete bad.courses;
    expect(() => schoolProgressFromBridge(bad)).toThrowError(/courses/);
  });

  it("八种原因不再共用同一句话", () => {
    const messages = new Set<string>();
    const variants: Record<string, unknown>[] = [
      { ...fromExtension(), format: "x" },
      { ...fromExtension(), version: 9 },
      { ...fromExtension(), capturedAt: 1 },
      { ...fromExtension(), source: null },
      { ...fromExtension(), nodes: "no" },
      { ...fromExtension(), nodes: [] },
      { ...fromExtension(), courses: "no" },
    ];
    for (const variant of variants) {
      try {
        schoolProgressFromBridge(variant);
      } catch (error) {
        messages.add((error as Error).message);
      }
    }
    expect(messages.size).toBe(variants.length);
  });
});
