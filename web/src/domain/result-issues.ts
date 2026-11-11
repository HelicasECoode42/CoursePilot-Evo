/**
 * 结果页的问题归组与顶部徽标（纯函数，无 IO、无框架依赖）。
 *
 * 目标：同一门课的问题只出现在它自己的课程卡片上，且只出现一次；
 * 与任何课程都无关的方案级问题，只放进顶部「展开看明细」里，去重后列出。
 *
 * 只归类与去重，不判断通过或冲突：判决仍由 Java 给出，展示口径仍由 answer-display 与 plan-sections 决定。
 */

import type { Issue, PlanSection } from "../contracts";
import {
  JAVA_UNASSIGNED_REASON,
  PENDING_COURSE_PATTERN,
  sectionNotAssignedReason,
} from "./unknown-explain";
import type { SectionTone } from "./plan-sections";

/** 课程卡片上的一行问题。 */
export interface CourseIssueLine {
  key: string;
  /** 违规（Java 判定不满足）还是未知（无法确认）。 */
  kind: "violation" | "unknown" | "unplaced";
  text: string;
}

export interface GroupedIssues {
  /** 课程号 → 该课程的问题行（每门课的未排进课表只出现一次）。 */
  byCourse: Record<string, CourseIssueLine[]>;
  /** 与具体课程无关的方案级问题，已去重。 */
  planLevel: CourseIssueLine[];
}

/** 课程号在消息里的边界匹配：前后不能紧贴字母或数字，避免 CS10 命中 CS103。 */
function mentionIndex(message: string, code: string): number {
  const escaped = code.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = new RegExp(`(?<![A-Za-z0-9])${escaped}(?![A-Za-z0-9])`).exec(
    message,
  );
  return match === null ? -1 : match.index;
}

/** 消息里提到课程号、且确实与单门课有关的代码（其余代码即使提到课程号，也按方案级处理）。 */
export const COURSE_SCOPED_CODES = new Set([
  "TIME_UNPARSEABLE",
  "TIME_UNPARSED",
  "CLASS_NOT_FOUND",
  "CLASS_NOT_SELECTED",
  "PIN_TEACHER_UNKNOWN",
  "CREDITS_UNKNOWN",
  "COURSE_FACTS_UNKNOWN",
  "TIME_CONFLICT",
]);

/**
 * 判断一条问题说的是方案里的哪一门课，取不到返回 null（归为方案级）。
 * 1. 未排进课表（Python/Java 两种格式）与「在修或结果未知」直接解析课程号；
 * 2. 其他问题：消息里恰好提到一门方案课程（或多门时取最先出现的，它通常是主语）。
 */
export function courseCodeOfIssue(
  issue: Issue,
  planCodes: readonly string[],
): string | null {
  const unplaced = sectionNotAssignedReason(issue);
  if (unplaced !== null) return unplaced.courseCode;
  const pending = PENDING_COURSE_PATTERN.exec(issue.message);
  if (pending !== null) return pending[1];
  // 其他代码只有确定与课程有关时才归到课程上；例如 FAKE_MODEL 的 courseCodes 只是数据说明，仍是方案级。
  if (!COURSE_SCOPED_CODES.has(issue.code)) return null;
  let best: { code: string; index: number } | null = null;
  for (const code of planCodes) {
    const index = mentionIndex(issue.message, code);
    if (index < 0) continue;
    if (best === null || index < best.index) best = { code, index };
  }
  return best?.code ?? null;
}

/**
 * 把违规与未知项归到课程或方案级。
 *   - 未排进课表：同一门课的 SECTION_UNASSIGNED 与 SECTION_NOT_ASSIGNED 只留一行，原因取更具体的一个（Python 给出的原因优先）；
 *   - 其他同一门课的问题按文字去重；
 *   - 方案级问题按文字去重。
 * explain 把未知项翻译成学生文案（课程名等上下文由调用方注入）。
 */
export function groupIssues(
  violations: readonly Issue[],
  unknowns: readonly Issue[],
  planCodes: readonly string[],
  explain: (issue: Issue) => string,
): GroupedIssues {
  const byCourse: Record<string, CourseIssueLine[]> = {};
  const planLevel: CourseIssueLine[] = [];
  const seenPlan = new Set<string>();
  const seenCourse = new Set<string>();
  const unplacedReason = new Map<
    string,
    { reason: string; specific: boolean }
  >();

  const push = (courseCode: string | null, line: CourseIssueLine) => {
    if (courseCode === null) {
      if (seenPlan.has(line.text)) return;
      seenPlan.add(line.text);
      planLevel.push(line);
      return;
    }
    const fingerprint = `${courseCode}\u0000${line.text}`;
    if (seenCourse.has(fingerprint)) return;
    seenCourse.add(fingerprint);
    (byCourse[courseCode] ??= []).push(line);
  };

  for (const issue of [...violations, ...unknowns]) {
    const isViolation = violations.includes(issue);
    const unplaced = sectionNotAssignedReason(issue);
    if (unplaced !== null) {
      // 只记原因，最后统一写一行；Python 的具体原因覆盖 Java 的通用原因。
      const specific = issue.code === "SECTION_NOT_ASSIGNED";
      const current = unplacedReason.get(unplaced.courseCode);
      if (current === undefined || (specific && !current.specific)) {
        unplacedReason.set(unplaced.courseCode, {
          reason: unplaced.reason,
          specific,
        });
      }
      continue;
    }
    const courseCode = courseCodeOfIssue(issue, planCodes);
    if (issue.code === "CLASS_NOT_SELECTED" && courseCode !== null) {
      // 与 SECTION_UNASSIGNED 同义（演示数据与旧格式），归入「未排进课表」，只写一行。
      if (!unplacedReason.has(courseCode)) {
        unplacedReason.set(courseCode, {
          reason: JAVA_UNASSIGNED_REASON,
          specific: false,
        });
      }
      continue;
    }
    const text = isViolation ? issue.message : explain(issue);
    push(courseCode, {
      key: `${issue.code}:${courseCode ?? "plan"}`,
      kind: isViolation ? "violation" : "unknown",
      text,
    });
  }

  for (const [courseCode, { reason }] of unplacedReason) {
    const text =
      reason === JAVA_UNASSIGNED_REASON
        ? "未排进课表：还没有选定班次"
        : `未排进课表：${reason}`;
    push(courseCode, { key: `unplaced:${courseCode}`, kind: "unplaced", text });
  }
  return { byCourse, planLevel };
}

/** 顶部徽标的文案与颜色档位。 */
export interface SectionBadge {
  scope: PlanSection["scope"] | "OVERALL";
  label: string;
  tone: SectionTone;
}

/**
 * 两个分项的徽标：「课表：无法确认 · 人工核验中」「毕业要求：需人工确认 6 条」这类。
 * toneOf 由调用方给出（它决定什么时候能显示「通过」，见 answer-display 门禁）；
 * officialUnverified 为真时，课表的无法确认后面加上「人工核验中」。
 */
export function sectionBadges(
  sections: readonly PlanSection[],
  toneOf: (section: PlanSection) => SectionTone,
  officialUnverified: boolean,
): SectionBadge[] {
  return sections.map((section) => {
    const tone = toneOf(section);
    const violations = countDistinct(section.violations);
    const unknowns = countDistinct(section.unknownChecks);
    if (section.scope === "TIMETABLE") {
      const label =
        section.verdict === "VALID"
          ? tone === "pass"
            ? "通过"
            : "待确认"
          : section.verdict === "INVALID"
            ? "不通过"
            : officialUnverified
              ? "无法确认 · 人工核验中"
              : "无法确认";
      return { scope: "TIMETABLE", label: `课表：${label}`, tone };
    }
    const label =
      section.verdict === "VALID"
        ? tone === "pass"
          ? "通过"
          : "待确认"
        : section.verdict === "INVALID"
          ? `不满足 ${violations || 1} 条`
          : `需人工确认 ${unknowns || 1} 条`;
    return { scope: "CURRICULUM", label: `毕业要求：${label}`, tone };
  });
}

function countDistinct(issues: readonly Issue[]): number {
  return new Set(issues.map((issue) => `${issue.code}\u0000${issue.message}`))
    .size;
}

/** 没有分项（旧后端）时的单个徽标，文字直接用核验视图的结论（不另起一套措辞）。 */
export function overallBadge(label: string, tone: SectionTone): SectionBadge {
  return { scope: "OVERALL", label, tone };
}

/** 课程类别标签：只认「必修」「选修」两个字样，其余不标，不猜。 */
export function requirementTag(
  category: string | null | undefined,
): "必修" | "选修" | null {
  if (!category) return null;
  if (category.includes("必修")) return "必修";
  if (category.includes("选修")) return "选修";
  return null;
}

/** 布局断点：与 styles.css 中的媒体查询保持一致（1024px 以上为两栏）。 */
export const WIDE_LAYOUT_MIN_WIDTH = 1024;

export function isWideLayout(width: number): boolean {
  return width >= WIDE_LAYOUT_MIN_WIDTH;
}
