/**
 * 课程号 → 课程名 的查表与折叠显示。
 *
 * 为什么需要：界面上到处是裸课程号。核对结果里一口气列出
 * 「00864096、00914006、00944008、01014016…」十六个号，补录的课程行里也只有
 * 「已选：00944008」——学生和开发者都认不出那是什么课。课程名一直在课程目录里，
 * 只是没有被用上。
 */

import type { Course } from "../contracts";
import { usableName } from "./school-categories";

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

/** 一门课的名字与学分。名字为空时不构成事实，见 buildCourseFactIndex。 */
export type CourseFact = { name: string; credits: number | null };

export type CourseFactLookup = (courseCode: string) => CourseFact | null;

export type CourseFactSource = {
  courseCode: string;
  name: string | null | undefined;
  credits?: number | null;
};

/**
 * 合并多个来源的课程事实。来源按优先级排列，同一课程号取第一个有可用名字的来源，
 * 名字与学分一起取自同一来源，不混用两边的数据。
 */
export function buildCourseFactIndex(
  sources: ReadonlyArray<readonly CourseFactSource[]>,
): Map<string, CourseFact> {
  const facts = new Map<string, CourseFact>();
  for (const source of sources) {
    for (const item of source) {
      if (facts.has(item.courseCode)) continue;
      const name = usableName(item.name);
      if (!name) continue;
      facts.set(item.courseCode, { name, credits: item.credits ?? null });
    }
  }
  return facts;
}

/**
 * 已选、优先考虑等列表里的课程标签，形如「课程名（课程号）· 3 学分」。
 * 查不到名字时只写「课程号 08305092（名称未加载）」，绝不把课程号写两遍。
 */
export function describeSelectedCourse(
  courseCode: string,
  fact: CourseFact | null,
): string {
  if (!fact) return `课程号 ${courseCode}（名称未加载）`;
  const credits = fact.credits === null ? "学分未知" : `${fact.credits} 学分`;
  return `${fact.name}（${courseCode}）· ${credits}`;
}
