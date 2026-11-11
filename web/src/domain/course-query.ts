/**
 * 结果页「搜索班次」的输入解析（纯函数）。
 *
 * 服务端的课程号只接受 ASCII 字母数字开头、含 . _ : - 的串（Java 的 requireId）。
 * 学生常输入课程名（如「数据库」）；这些字不能当课程号发出去，要先在课程目录里找到唯一课程号。
 */

import type { Course } from "../contracts";

/** 与服务端 requireId 一致的课程号格式。 */
export const COURSE_CODE_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$/;

export type ResolvedCourseQuery =
  | { ok: true; code: string }
  | { ok: false; message: string; candidates: Course[] };

/** 最多列出几门同名候选，超过时补「等」。 */
const LISTED_CANDIDATES = 5;

/**
 * 课程号格式正确就直接用；否则按课程名到目录里查（search 由调用方注入，通常是
 * api.listCourses 的 query 参数）。只有唯一匹配的课程号才会返回 ok。
 */
export async function resolveCourseQuery(
  typed: string,
  search: ((text: string) => Promise<readonly Course[]>) | null,
): Promise<ResolvedCourseQuery> {
  if (COURSE_CODE_PATTERN.test(typed)) return { ok: true, code: typed };
  if (search === null) {
    return {
      ok: false,
      message: "请输入课程名或课程号，从列表中选择课程。",
      candidates: [],
    };
  }
  const items = await search(typed);
  const byCode = new Map<string, Course>();
  for (const item of items) {
    if (
      COURSE_CODE_PATTERN.test(item.courseCode) &&
      !byCode.has(item.courseCode)
    )
      byCode.set(item.courseCode, item);
  }
  const unique = [...byCode.values()];
  if (unique.length === 0) {
    return {
      ok: false,
      message: `课程目录里没有找到「${typed}」。请输入课程名或课程号，从列表中选择课程。`,
      candidates: [],
    };
  }
  if (unique.length > 1) {
    const listed = unique
      .slice(0, LISTED_CANDIDATES)
      .map((item) => `${item.courseCode} ${item.name}`)
      .join("、");
    const more = unique.length > LISTED_CANDIDATES ? " 等" : "";
    return {
      ok: false,
      message: `「${typed}」对应 ${unique.length} 门课，请从下面选择：${listed}${more}`,
      candidates: unique,
    };
  }
  return { ok: true, code: unique[0]!.courseCode };
}
