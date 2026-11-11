/**
 * 学校报告的类别与课程名字的显示规则（纯函数，不碰 Vue）。
 *
 * 为什么需要：真实导入的学校快照里，类别名和课程名经常是空串（扩展抓取时
 * 子类别的标题没读出来），界面上就只剩空白的项目符号和「 · 2200R200」。
 * 这里统一规定：名字读不出来时写明「读不出来」，不编造，也不让一行变成空白；
 * 课程名能从学校报告或课程目录里补到的，就补上。
 */
import type { AuditResult } from "../contracts";
import { explainAuditUnknown } from "./academic-record";
import type { CourseNameLookup } from "./course-names";
import { unmodeledRuleCount, unmodeledRuleLine } from "./plan-sections";
import type {
  SchoolProgressCourse,
  SchoolProgressNode,
  SchoolProgressOutcome,
} from "./school-progress";

export const UNREAD_CATEGORY_NAME = "类别名未读出";
export const UNREAD_COURSE_NAME = "课程名未读出";
export const OTHER_CATEGORY_LABEL = "其他";

const OTHER_GROUP_KEY = "__other__";

/**
 * 只要含有字母或数字就算读到了名字。纯空白、空串、只剩括号标点（如扩展抓到的 "()"）
 * 都按没读到处理。
 */
export function usableName(raw: unknown): string | null {
  if (typeof raw !== "string") return null;
  const trimmed = raw.trim();
  return /[\p{L}\p{N}]/u.test(trimmed) ? trimmed : null;
}

export function nodeName(node: SchoolProgressNode): string {
  return usableName(node.name) ?? UNREAD_CATEGORY_NAME;
}

/** 学校报告给了这一层的任何学分值（要求/已获/还差）。 */
export function hasAnyCredit(node: SchoolProgressNode): boolean {
  return (
    node.requiredCredits !== null ||
    node.earnedCredits !== null ||
    node.remainingCredits !== null
  );
}

/** 有子类别的节点。 */
export function hasChildNodes(
  nodeId: string,
  nodes: readonly SchoolProgressNode[],
): boolean {
  return nodes.some((node) => node.parentId === nodeId);
}

/**
 * 这一层有没有可显示的内容：数字、子类别或课程任一即可。
 * 三者都没有的类别（学校页面只留了个空标题）不展示。
 */
export function nodeHasContent(
  node: SchoolProgressNode,
  nodes: readonly SchoolProgressNode[],
  courses: readonly SchoolProgressCourse[],
): boolean {
  return (
    hasAnyCredit(node) ||
    hasChildNodes(node.nodeId, nodes) ||
    courses.some((course) => course.nodeId === node.nodeId)
  );
}

/** 名字含「主修」的顶层节点；没有则为 null。 */
export function majorRootOf(
  nodes: readonly SchoolProgressNode[],
): SchoolProgressNode | null {
  return (
    nodes.find(
      (node) => node.parentId === null && nodeName(node).includes("主修"),
    ) ?? null
  );
}

/**
 * 第一级类别：有主修时是主修下的直接子类别，否则是顶层节点。
 * 只保留有内容的（见 nodeHasContent）。
 */
export function firstLevelNodes(
  nodes: readonly SchoolProgressNode[],
  courses: readonly SchoolProgressCourse[],
): SchoolProgressNode[] {
  const root = majorRootOf(nodes);
  const parentId = root ? root.nodeId : null;
  return nodes.filter(
    (node) =>
      node.parentId === parentId && nodeHasContent(node, nodes, courses),
  );
}

/**
 * 顶层摘要：只列主修下第一级子类别各自的还差值（按还差从大到小），
 * 不跨层累加，父类与子类不会重复计算。没有还差或没有主修时返回 ""。
 */
export function remainingSummaryLine(
  nodes: readonly SchoolProgressNode[],
): string {
  const root = majorRootOf(nodes);
  if (root === null) return "";
  const items = nodes
    .filter(
      (node) =>
        node.parentId === root.nodeId &&
        node.remainingCredits !== null &&
        node.remainingCredits > 0,
    )
    .sort((a, b) => (b.remainingCredits ?? 0) - (a.remainingCredits ?? 0));
  if (items.length === 0) return "";
  return `按学校报告还差：${items
    .map((node) => `${nodeName(node)} ${node.remainingCredits}`)
    .join("、")}`;
}

/**
 * 从根到本类别的路径，如「通识课 › 思想政治理论课」。
 * 上级名字读不出时仍写「类别名未读出」，保证层级看得出来。
 */
export function nodePathLabel(
  nodeId: string,
  nodes: readonly SchoolProgressNode[],
): string {
  const byId = new Map(nodes.map((node) => [node.nodeId, node]));
  const parts: string[] = [];
  const seen = new Set<string>();
  let current = byId.get(nodeId);
  while (current && !seen.has(current.nodeId)) {
    seen.add(current.nodeId);
    parts.unshift(nodeName(current));
    current = current.parentId ? byId.get(current.parentId) : undefined;
  }
  return parts.join(" › ");
}

export function courseDisplayName(
  courseCode: string,
  name: unknown,
  lookupName?: CourseNameLookup,
): string {
  return (
    usableName(name) ??
    usableName(lookupName?.(courseCode)) ??
    UNREAD_COURSE_NAME
  );
}

/** 「课程名 · 课程号」；课程名确实查不到时只给课程号，不编。 */
export function courseTitle(courseCode: string, name: string | null): string {
  return name ? `${name} · ${courseCode}` : courseCode;
}

export const SCHOOL_OUTCOME_LABELS: Record<SchoolProgressOutcome, string> = {
  PASSED: "已修",
  FAILED: "未通过",
  IN_PROGRESS: "在读",
  NOT_TAKEN: "未修",
  UNKNOWN: "状态待确认",
};

export function creditsLabel(credits: number | null): string {
  return credits === null ? "学分待确认" : `${credits} 学分`;
}

export type LearnedCourse = {
  courseCode: string;
  name: string;
  credits: number | null;
  statusLabel: string;
};

export type LearnedGroup = {
  key: string;
  label: string;
  items: LearnedCourse[];
};

type RecordCourseLike = {
  courseCode: string;
  earnedCredits: number | null;
  outcome: SchoolProgressOutcome;
};

/**
 * 「我学了什么」按学校类别分组。
 *
 * 课程挂在哪个学校类别下，就进哪一组（同一课程号可能出现在多个类别里，各算一行）。
 * 学校报告里没有类别归属的课程，以及只在学业记录里出现、学校报告没有的课程，
 * 都放到最后的「其他」组。
 */
export function groupLearnedCourses(input: {
  nodes: readonly SchoolProgressNode[];
  courses: readonly SchoolProgressCourse[];
  recordCourses: readonly RecordCourseLike[];
  lookupName?: CourseNameLookup;
}): LearnedGroup[] {
  const { nodes, courses, recordCourses, lookupName } = input;
  const nodeIds = new Set(nodes.map((node) => node.nodeId));
  const order = new Map(nodes.map((node, index) => [node.nodeId, index]));
  const groups = new Map<string, LearnedGroup>();
  const schoolCodes = new Set<string>();

  const push = (key: string, label: string, item: LearnedCourse) => {
    const group = groups.get(key);
    if (group) group.items.push(item);
    else groups.set(key, { key, label, items: [item] });
  };

  for (const course of courses) {
    schoolCodes.add(course.courseCode);
    const known = nodeIds.has(course.nodeId);
    push(
      known ? course.nodeId : OTHER_GROUP_KEY,
      known ? nodePathLabel(course.nodeId, nodes) : OTHER_CATEGORY_LABEL,
      {
        courseCode: course.courseCode,
        name: courseDisplayName(course.courseCode, course.name, lookupName),
        credits: course.credits,
        statusLabel: SCHOOL_OUTCOME_LABELS[course.outcome],
      },
    );
  }

  const seenOther = new Set<string>();
  for (const record of recordCourses) {
    if (schoolCodes.has(record.courseCode)) continue;
    if (seenOther.has(record.courseCode)) continue;
    seenOther.add(record.courseCode);
    push(OTHER_GROUP_KEY, OTHER_CATEGORY_LABEL, {
      courseCode: record.courseCode,
      name: courseDisplayName(record.courseCode, null, lookupName),
      credits: record.earnedCredits,
      statusLabel: SCHOOL_OUTCOME_LABELS[record.outcome],
    });
  }

  const rank = (key: string) =>
    key === OTHER_GROUP_KEY ? Number.MAX_SAFE_INTEGER : (order.get(key) ?? 0);
  return [...groups.values()].sort((a, b) => rank(a.key) - rank(b.key));
}

export type UnknownGroupKey =
  | "not-in-catalog"
  | "pending"
  | "transcript"
  | "rules"
  | "other";

export type UnknownGroup = {
  key: UnknownGroupKey;
  headline: string;
  courses: Array<{ courseCode: string; name: string | null }>;
  notes: string[];
};

export type UnknownSummary = {
  headline: string;
  groups: UnknownGroup[];
};

const CIRCLED = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨"];

const NOT_IN_CATALOG_CODES = new Set([
  "COURSE_NOT_IN_CATALOG",
  "COURSE_CATEGORY_MISSING",
]);
const PENDING_CODES = new Set([
  "PENDING_COURSE",
  "PENDING_COURSE_UNCATEGORIZED",
]);

/** 核对消息以「课程 XXX 」开头；读不出课程号就返回 null。 */
function courseCodeFromMessage(message: string): string | null {
  const match = message.match(/^课程 (\S+) /);
  return match?.[1] ?? null;
}

/**
 * 把本地核对的无法确认项按原因分组，给一段摘要。
 *
 * 不隐藏未知：每一条都落在某一组里（分组后的数量仍是精确的），
 * 也不把未知折成「已满足」或「0 门」。
 */
export function summarizeAuditUnknowns(
  audit: Pick<AuditResult, "unknowns" | "transcriptComplete">,
  lookupName: CourseNameLookup,
): UnknownSummary {
  const catalog: UnknownGroup = {
    key: "not-in-catalog",
    headline: "",
    courses: [],
    notes: [],
  };
  const pending: UnknownGroup = {
    key: "pending",
    headline: "",
    courses: [],
    notes: [],
  };
  const rules: UnknownGroup = {
    key: "rules",
    headline: "",
    courses: [],
    notes: [],
  };
  const other: UnknownGroup = {
    key: "other",
    headline: "",
    courses: [],
    notes: [],
  };
  const addCourse = (group: UnknownGroup, courseCode: string) => {
    if (group.courses.some((item) => item.courseCode === courseCode)) return;
    group.courses.push({
      courseCode,
      name: usableName(lookupName(courseCode)),
    });
  };

  let ruleCount = 0;
  for (const issue of audit.unknowns) {
    if (NOT_IN_CATALOG_CODES.has(issue.code)) {
      const code = courseCodeFromMessage(issue.message);
      if (code) addCourse(catalog, code);
      else catalog.notes.push(issue.message);
    } else if (PENDING_CODES.has(issue.code)) {
      const code = courseCodeFromMessage(issue.message);
      if (code) addCourse(pending, code);
      else pending.notes.push(issue.message);
    } else if (issue.code === "UNMODELED_CURRICULUM_RULES") {
      ruleCount += unmodeledRuleCount(issue);
      rules.notes.push(unmodeledRuleLine(issue));
    } else {
      other.notes.push(explainAuditUnknown(issue.code, issue.message));
    }
  }

  catalog.headline = `${catalog.courses.length || catalog.notes.length} 门课无法归入本专业培养要求（不在课程库或类别为空，以学校报告为准）`;
  pending.headline = `${pending.courses.length || pending.notes.length} 门在读或结果未知的课程尚未出成绩`;
  rules.headline = `${ruleCount || rules.notes.length} 条培养方案规则需人工确认`;
  other.headline = `${other.notes.length} 项其他无法确认`;
  const transcript: UnknownGroup = {
    key: "transcript",
    headline: "尚未勾选「记录已完整」",
    courses: [],
    notes: [],
  };

  const ordered: UnknownGroup[] = [catalog, pending];
  if (!audit.transcriptComplete) ordered.push(transcript);
  ordered.push(rules, other);
  const groups = ordered.filter(
    (group) =>
      group.courses.length > 0 ||
      group.notes.length > 0 ||
      group.key === "transcript",
  );
  const headline =
    groups.length === 0
      ? "本地核对没有报告无法确认的项目。"
      : `本地核对暂无法给出结论：${groups
          .map(
            (group, index) =>
              `${CIRCLED[index] ?? `${index + 1}.`} ${group.headline}`,
          )
          .join("；")}`;
  return { headline, groups };
}
