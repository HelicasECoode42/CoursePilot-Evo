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

/**
 * 顶层字段逐项检查。
 *
 * 原先八个不同的原因共用一句「学业资料格式不正确。」，学生和维护者都看不出
 * 是哪一项不对——2026-10-29 用户把扩展下载的 JSON 传回来被拒，就是卡在这里，
 * 而那句话没有提供任何可追查的信息。现在每一项单独报，并带上实际读到的值。
 */
function describeTopLevelProblem(raw: Record<string, unknown>): string | null {
  if (raw.format !== "coursepilot-shu-academic-progress")
    return `这个文件的 format 是 ${JSON.stringify(raw.format)}，不是扩展导出的 "coursepilot-shu-academic-progress"。`;
  if (raw.version !== 1)
    return `这个文件的 version 是 ${JSON.stringify(raw.version)}，当前只认 1。扩展版本和页面对不上时会这样。`;
  if (typeof raw.capturedAt !== "string")
    return "缺少 capturedAt（抓取时间），这个文件不像是扩展导出的完整文件。";
  if (typeof raw.source !== "string")
    return "缺少 source（来源页面），这个文件不像是扩展导出的完整文件。";
  if (!Array.isArray(raw.nodes))
    return "缺少 nodes（学校类别树），没有它没法把课程归到类别里。";
  if (raw.nodes.length === 0)
    return "nodes（学校类别树）是空的。多半是导出时教务页面的类别树还没加载完，回到那一页等它显示出来再导一次。";
  if (!Array.isArray(raw.courses))
    return "缺少 courses（课程明细），没有它没法知道你修过哪些课。";
  return null;
}

export function schoolProgressFromBridge(
  value: unknown,
): SchoolProgressSnapshot {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error(
      "这个文件的最外层不是一个 JSON 对象，不是扩展导出的学业进度文件。",
    );
  const raw = value as Record<string, unknown>;
  const problem = describeTopLevelProblem(raw);
  if (problem !== null) throw new Error(problem);
  // describeTopLevelProblem 已经确认过这两个是数组，但检查搬到函数里之后
  // TypeScript 的收窄跟不过来，这里把类型接回去。
  const rawNodes = raw.nodes as unknown[];
  const rawCourses = raw.courses as unknown[];

  const nodes: SchoolProgressNode[] = rawNodes.map((item) => {
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

  const courses: SchoolProgressCourse[] = rawCourses.map((item) => {
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
    capturedAt: raw.capturedAt as string,
    source: raw.source as string,
    nodes,
    courses,
  };
}
