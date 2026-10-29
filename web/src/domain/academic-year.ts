import type { Course } from "../contracts";

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
