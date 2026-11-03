/**
 * 候选课程「本学期是否开课」的判断（纯函数）。
 *
 * 只数班次，不做任何时间计算：班次来自所选开课快照的 Java 查询结果。
 * 快照里没有这门课的班次，就是「未开」；查询本身 UNKNOWN 或失败，就是「无法确认」，
 * 两者不能混为一谈。
 */

import type { CourseOffering } from "../contracts";

export type OfferingAvailability =
  | { state: "OFFERED"; sections: number }
  | { state: "NOT_OFFERED" }
  | { state: "UNKNOWN"; reason: string };

/**
 * 业务状态为 OK 时，按 classId 去重数班次。空数组在 OK 下就是「所选快照里没有这门课」。
 * 调用方在业务状态为 UNKNOWN 时不要调用它，应直接给 UNKNOWN。
 */
export function availabilityFromOfferings(
  items: readonly CourseOffering[],
  courseCode: string,
): OfferingAvailability {
  const classIds = new Set(
    items
      .filter((item) => item.courseCode === courseCode)
      .map((item) => item.classId),
  );
  if (classIds.size === 0) return { state: "NOT_OFFERED" };
  return { state: "OFFERED", sections: classIds.size };
}

/** 排序键：已开课在前，无法确认（含尚未查询）居中，未开在后。 */
export function availabilityRank(
  availability: OfferingAvailability | undefined,
): number {
  if (availability?.state === "OFFERED") return 0;
  if (availability?.state === "NOT_OFFERED") return 2;
  return 1;
}

/** 稳定排序：同一层内保持原有顺序（相关度、课程号）。 */
export function sortByAvailability<T extends { courseCode: string }>(
  courses: readonly T[],
  lookup: (courseCode: string) => OfferingAvailability | undefined,
): T[] {
  return courses
    .map((course, index) => ({
      course,
      index,
      rank: availabilityRank(lookup(course.courseCode)),
    }))
    .sort((a, b) => a.rank - b.rank || a.index - b.index)
    .map((entry) => entry.course);
}

/** 页面上一行的说明文字。 */
export function availabilityLabel(
  availability: OfferingAvailability | undefined,
): string {
  if (availability === undefined) return "开课情况未查询";
  if (availability.state === "OFFERED")
    return `本学期开 ${availability.sections} 个班`;
  if (availability.state === "NOT_OFFERED") return "本学期未开";
  return "开课情况无法确认";
}
