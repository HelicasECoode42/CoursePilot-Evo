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

/**
 * 完整性说明。未声明完整时，必须让学生预期会有「无法确认」项，
 * 而不是以为系统会给出确定结论。
 */
export function describeCompleteness(
  record: Pick<AcademicRecord, "transcriptComplete">,
): string {
  return record.transcriptComplete
    ? "已声明记录完整。"
    : "未声明完整，无法判断的要求会显示为「无法确认」。";
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
