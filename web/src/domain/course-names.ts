/**
 * 课程号 → 课程名 的查表与折叠显示。
 *
 * 为什么需要：界面上到处是裸课程号。核对结果里一口气列出
 * 「00864096、00914006、00944008、01014016…」十六个号，补录的课程行里也只有
 * 「已选：00944008」——学生和开发者都认不出那是什么课。课程名一直在课程目录里，
 * 只是没有被用上。
 */

import type { Course } from "../contracts";

export type CourseNameLookup = (courseCode: string) => string | null;

/** 从课程目录建查表。同号不同名（体育1-6 这种）时保留第一条，并在后面标注还有几门同号。 */
export function buildCourseNameIndex(
  courses: readonly Course[],
): Record<string, string> {
  const byCode = new Map<string, string[]>();
  for (const course of courses) {
    const names = byCode.get(course.courseCode);
    if (names) {
      if (!names.includes(course.name)) names.push(course.name);
    } else {
      byCode.set(course.courseCode, [course.name]);
    }
  }
  const index: Record<string, string> = {};
  for (const [code, names] of byCode) {
    index[code] =
      names.length === 1
        ? names[0]
        : `${names[0]} 等 ${names.length} 门同号课程`;
  }
  return index;
}

/** 「课程号 · 课程名」。查不到名字就只给号，不编。 */
export function describeCourse(
  courseCode: string,
  lookup: CourseNameLookup,
): string {
  const name = lookup(courseCode);
  return name ? `${courseCode} · ${name}` : courseCode;
}

export type CourseCodeList = {
  shown: string[];
  hiddenCount: number;
};

/**
 * 长列表折叠。
 *
 * 核对结果里「公共基础课」能列出十六个课程号，连成一行没人读得完。默认只给前几门，
 * 其余折起来，并明确说还有几门——不是悄悄截断。
 */
export function limitCourseCodes(
  courseCodes: readonly string[],
  limit: number,
  expanded: boolean,
): CourseCodeList {
  if (expanded || courseCodes.length <= limit) {
    return { shown: [...courseCodes], hiddenCount: 0 };
  }
  return {
    shown: courseCodes.slice(0, limit),
    hiddenCount: courseCodes.length - limit,
  };
}
