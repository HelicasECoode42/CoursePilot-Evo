import type { Course } from "../contracts";

/** 为什么「按年级生成」一门都没列出来。三种 0 的原因完全不同，不能混成一句话。 */
export type YearSuggestionGap =
  | { kind: "none" }
  | { kind: "first-year" }
  | { kind: "no-suggested-term" }
  | { kind: "nothing-before-year" };

/** 根据建议修读学年列出待学生确认的基础课，不视为已取得成绩。 */
export function coursesSuggestedBeforeYear(
  courses: readonly Course[],
  year: number,
): Course[] {
  const counts = new Map<string, number>();
  for (const course of courses)
    counts.set(course.courseCode, (counts.get(course.courseCode) ?? 0) + 1);
  const years: Record<string, number> = {
    一: 1,
    二: 2,
    三: 3,
    四: 4,
    "1": 1,
    "2": 2,
    "3": 3,
    "4": 4,
  };
  return courses.filter((course) => {
    const term = course.suggestedTerm?.trim() ?? "";
    const match =
      /^第([一二三四1-4])学年(?:\s*第(?:[一二三四五六七八九十]+|\d{1,2})学期)?$/.exec(
        term,
      );
    return (
      Boolean(match) &&
      years[match![1]] < year &&
      ["公共基础课", "学科基础课"].includes(course.category) &&
      counts.get(course.courseCode) === 1 &&
      !/xx$/i.test(course.courseCode)
    );
  });
}

/**
 * 解释「按年级生成」为什么是空的。
 *
 * 实测踩到的坑：SYN_0263… 这份快照是早一轮导入发布的，105 门课的
 * suggestedTerm 全是 null，于是不管选哪个年级都是 0 门。页面原先统一显示
 * 「没有可按年级自动整理的基础课程」，看起来像功能坏了，其实是这份培养方案
 * 根本没有建议学期这项数据。必须把它和「大一本来就没有更早的学年」分开说。
 */
export function describeYearSuggestionGap(
  courses: readonly Course[],
  year: number,
): YearSuggestionGap {
  if (coursesSuggestedBeforeYear(courses, year).length > 0)
    return { kind: "none" };
  if (courses.length > 0 && courses.every((c) => !c.suggestedTerm?.trim()))
    return { kind: "no-suggested-term" };
  if (year <= 1) return { kind: "first-year" };
  return { kind: "nothing-before-year" };
}
