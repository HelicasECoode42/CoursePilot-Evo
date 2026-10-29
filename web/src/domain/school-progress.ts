import type { AcademicRecord } from "../contracts";

export type SchoolProgressOutcome =
  | "PASSED"
  | "FAILED"
  | "IN_PROGRESS"
  | "NOT_TAKEN"
  | "UNKNOWN";

export type SchoolProgressNode = {
  nodeId: string;
  parentId: string | null;
  schoolNodeId: string | null;
  leaf: boolean;
  name: string;
  requiredCredits: number | null;
  earnedCredits: number | null;
  remainingCredits: number | null;
};

export type SchoolProgressCourse = {
  nodeId: string;
  courseCode: string;
  name: string;
  credits: number | null;
  outcome: SchoolProgressOutcome;
  completedYear: string | null;
  completedTerm: string | null;
  grade: string | null;
  makeup: string | null;
  retake: string | null;
  suggestedYear: string | null;
  suggestedTerm: string | null;
};

export type SchoolProgressSnapshot = {
  format: "coursepilot-shu-academic-progress";
  version: 1;
  capturedAt: string;
  source: string;
  nodes: SchoolProgressNode[];
  courses: SchoolProgressCourse[];
};

export type SchoolProgressImportRequest = {
  schemaVersion: "1.0";
  curriculumSnapshotId: string;
  snapshot: SchoolProgressSnapshot;
};

export type SchoolProgressImportResult = {
  receipt: {
    schoolProgressId: string;
    contentHash: string;
    importedAt: string;
    reused: boolean;
  };
  snapshot: SchoolProgressSnapshot;
  academicRecord: AcademicRecord;
};

export function schoolProgressFromBridge(
  value: unknown,
): SchoolProgressSnapshot {
  if (!value || typeof value !== "object")
    throw new Error("学业资料格式不正确。");
  const raw = value as Record<string, unknown>;
  if (
    raw.format !== "coursepilot-shu-academic-progress" ||
    raw.version !== 1 ||
    typeof raw.capturedAt !== "string" ||
    typeof raw.source !== "string" ||
    !Array.isArray(raw.nodes) ||
    raw.nodes.length === 0 ||
    !Array.isArray(raw.courses)
  )
    throw new Error("学业资料格式不正确。");

  const nodes: SchoolProgressNode[] = raw.nodes.map((item) => {
    if (!item || typeof item !== "object")
      throw new Error("类别节点格式不正确。");
    const node = item as Record<string, unknown>;
    if (
      typeof node.nodeId !== "string" ||
      !(node.parentId === null || typeof node.parentId === "string") ||
      !(node.schoolNodeId === null || typeof node.schoolNodeId === "string") ||
      typeof node.leaf !== "boolean" ||
      typeof node.name !== "string" ||
      ![node.requiredCredits, node.earnedCredits, node.remainingCredits].every(
        (credit) =>
          credit === null ||
          (typeof credit === "number" &&
            Number.isFinite(credit) &&
            credit >= 0),
      )
    )
      throw new Error("类别节点格式不正确。");
    return {
      nodeId: node.nodeId,
      parentId: node.parentId,
      schoolNodeId: node.schoolNodeId,
      leaf: node.leaf,
      name: node.name,
      requiredCredits: node.requiredCredits,
      earnedCredits: node.earnedCredits,
      remainingCredits: node.remainingCredits,
    } as SchoolProgressNode;
  });
  const nodeIds = new Set(nodes.map((node) => node.nodeId));
  if (
    nodeIds.size !== nodes.length ||
    nodes.some((node) => node.parentId && !nodeIds.has(node.parentId))
  )
    throw new Error("类别父子关系不完整。");

  const courses: SchoolProgressCourse[] = raw.courses.map((item) => {
    if (!item || typeof item !== "object")
      throw new Error("课程明细格式不正确。");
    const course = item as Record<string, unknown>;
    const outcomes: SchoolProgressOutcome[] = [
      "PASSED",
      "FAILED",
      "IN_PROGRESS",
      "NOT_TAKEN",
      "UNKNOWN",
    ];
    if (
      typeof course.nodeId !== "string" ||
      !nodeIds.has(course.nodeId) ||
      typeof course.courseCode !== "string" ||
      typeof course.name !== "string" ||
      !(
        course.credits === null ||
        (typeof course.credits === "number" &&
          Number.isFinite(course.credits) &&
          course.credits >= 0)
      ) ||
      !outcomes.includes(course.outcome as SchoolProgressOutcome)
    )
      throw new Error("课程明细格式不正确。");
    for (const field of [
      "completedYear",
      "completedTerm",
      "grade",
      "makeup",
      "retake",
      "suggestedYear",
      "suggestedTerm",
    ])
      if (!(course[field] === null || typeof course[field] === "string"))
        throw new Error("课程明细格式不正确。");
    return {
      nodeId: course.nodeId,
      courseCode: course.courseCode,
      name: course.name,
      credits: course.credits,
      outcome: course.outcome,
      completedYear: course.completedYear,
      completedTerm: course.completedTerm,
      grade: course.grade,
      makeup: course.makeup,
      retake: course.retake,
      suggestedYear: course.suggestedYear,
      suggestedTerm: course.suggestedTerm,
    } as SchoolProgressCourse;
  });

  return {
    format: "coursepilot-shu-academic-progress",
    version: 1,
    capturedAt: raw.capturedAt,
    source: raw.source,
    nodes,
    courses,
  };
}
