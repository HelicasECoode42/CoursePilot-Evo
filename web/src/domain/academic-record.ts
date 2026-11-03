/**
 * 学业记录与学业核对的纯规则（E-F1）。
 *
 * 页面只消费这里的结果，不自己判断「已满足 / 未满足 / 无法确认」，
 * 也不把未知折算成 0 或「已满足」。
 */

import type {
  AcademicRecord,
  AcademicRecordInput,
  AuditItem,
  AuditResult,
  CompletedCourse,
} from "../contracts";
import { SCHEMA_VERSION } from "../contracts";

export type AuditGroupKey = "unsatisfied" | "unknown" | "satisfied";

export interface AuditGroup {
  key: AuditGroupKey;
  label: string;
  items: AuditItem[];
}

/** 先讲缺口，再讲无法确认，最后才是已满足；空组不出现。 */
const GROUP_ORDER: readonly AuditGroupKey[] = [
  "unsatisfied",
  "unknown",
  "satisfied",
];

const GROUP_LABELS: Record<AuditGroupKey, string> = {
  unsatisfied: "还差的要求",
  unknown: "无法确认的要求",
  satisfied: "已满足的要求",
};

function groupOf(item: AuditItem): AuditGroupKey {
  switch (item.state) {
    case "SATISFIED":
      return "satisfied";
    case "UNSATISFIED":
      return "unsatisfied";
    default:
      // UNKNOWN 单独成组：不许并进「已满足」，也不许折成缺口。
      return "unknown";
  }
}

/**
 * 把核对项分成三组。UNKNOWN 与 SATISFIED 永远不在同一组，
 * 因此页面无法把「无法确认」渲染成「已满足」。
 */
export function groupAuditItems(items: readonly AuditItem[]): AuditGroup[] {
  return GROUP_ORDER.map((key) => ({
    key,
    label: GROUP_LABELS[key],
    items: items.filter((item) => groupOf(item) === key),
  })).filter((group) => group.items.length > 0);
}

/** 核对项的数字来源：学校报告同名类别（SCHOOL_REPORT）或本地课程折算（LOCAL）。缺省按 LOCAL。 */
export function auditSourceLabel(item: Pick<AuditItem, "source">): string {
  return item.source === "SCHOOL_REPORT" ? "按学校报告" : "本地核对";
}

/**
 * 在读学分汇总（不计入已获学分）。以分为单位累加，避免小数误差。
 * unknownCount 为在读学分未知（null）或未提供的类别数。
 */
export function inProgressSummary(
  items: readonly Pick<AuditItem, "inProgressCredits">[],
): { credits: number; unknownCount: number } {
  let cents = 0;
  let unknownCount = 0;
  for (const item of items) {
    if (typeof item.inProgressCredits === "number") {
      cents += Math.round(item.inProgressCredits * 100);
    } else {
      unknownCount += 1;
    }
  }
  return { credits: cents / 100, unknownCount };
}

/** 在读学分的一句说明；没有在读学分且都已知时返回 null，不在页面上占行。 */
export function inProgressNote(
  items: readonly Pick<AuditItem, "inProgressCredits">[],
): string | null {
  const { credits, unknownCount } = inProgressSummary(items);
  const parts: string[] = [];
  if (credits > 0) parts.push(`另有 ${credits} 学分在读，尚未计入已获学分`);
  if (unknownCount > 0 && credits === 0) {
    parts.push("部分类别的在读学分待确认");
  }
  return parts.length > 0 ? parts.join("；") : null;
}

/**
 * 完整性说明。未声明完整时，必须让学生预期会有「无法确认」项，
 * 而不是以为系统会给出确定结论。学校导入已读全时，按完整记录核对。
 */
export function describeCompleteness(
  record: Pick<AcademicRecord, "transcriptComplete"> & {
    transcriptCompleteSource?: "SCHOOL_IMPORT_FULL" | "MANUAL" | null;
  },
): string {
  if (
    record.transcriptComplete &&
    record.transcriptCompleteSource === "SCHOOL_IMPORT_FULL"
  ) {
    return "学校导入已读全，按完整记录核对。";
  }
  return record.transcriptComplete
    ? "已声明记录完整。"
    : "未声明完整，无法判断的要求会显示为「无法确认」。";
}

/** 学校导入已读全时不再需要学生手动勾选「记录已完整」。 */
export function needsCompleteCheckbox(
  audit: Pick<AuditResult, "transcriptComplete" | "transcriptCompleteSource">,
): boolean {
  return (
    !audit.transcriptComplete &&
    audit.transcriptCompleteSource !== "SCHOOL_IMPORT_FULL"
  );
}

/** Use the student-facing explanation already defined for common audit UNKNOWN codes. */
export function explainAuditUnknown(code: string, fallback: string): string {
  if (code === "TRANSCRIPT_COMPLETENESS_UNKNOWN")
    return "已修课程可能还未填全，暂时无法确定剩余要求。";
  if (code === "REQUIREMENT_SOURCE_REFS_MISSING")
    return "部分培养要求缺少可核对的来源，暂时无法确定。";
  return fallback;
}

/** 返回重复出现的课程编号，前端只提前拦这一类明显错误。 */
export function duplicateCourseCodes(
  courses: readonly CompletedCourse[],
): string[] {
  const seen = new Set<string>();
  const duplicates = new Set<string>();
  for (const course of courses) {
    const code = course.courseCode.trim();
    if (code === "") continue;
    if (seen.has(code)) duplicates.add(code);
    seen.add(code);
  }
  return [...duplicates];
}

/**
 * 草稿 -> 可提交的 AcademicRecordInput。
 * 未知的学分与学期保持 null，不写成 0；课程编号去空白后提交。
 */
export function buildRecordInput(
  curriculumSnapshotId: string,
  courses: readonly CompletedCourse[],
  transcriptComplete: boolean,
): AcademicRecordInput {
  return {
    schemaVersion: SCHEMA_VERSION,
    curriculumSnapshotId,
    completedCourses: courses.map((course) => ({
      ...course,
      courseCode: course.courseCode.trim(),
    })),
    transcriptComplete,
    sourceKind: "USER_IMPORT",
  };
}

/**
 * 学业记录的来源标签。后端 sourceKind 只有 USER_IMPORT 与 SYNTHETIC：
 * 手动补录和学校进度导入都是 USER_IMPORT，前者标「手动补录」，后者由调用方说明来自学校进度。
 * 只有 SYNTHETIC 才是虚构数据。
 */
export function recordSourceLabel(
  sourceKind: AcademicRecord["sourceKind"],
  fromSchoolProgress: boolean,
): string {
  if (sourceKind === "SYNTHETIC") return "虚构数据";
  return fromSchoolProgress ? "学校进度导入" : "手动补录";
}
