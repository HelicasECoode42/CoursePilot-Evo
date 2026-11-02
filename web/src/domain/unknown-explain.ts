/**
 * 未知项的学生可读文案（结果页用）。
 *
 * 规则：
 *   - 只翻译，不判断：是否未知、是否冲突都由 Java 决定，这里只说明「为什么无法确认」
 *     以及「学生现在能做什么」。
 *   - 代码以 Java 实际发出的为准（例如 UNMODELED_CURRICULUM_RULES，不是前端早先的 UNMODELED_RULE）。
 *   - PENDING_COURSE 的 message 只有课程号，这里从课程名表补上课程名，逐门列出，
 *     不再用一句笼统的「有一项课程信息无法确认」。
 */

import type { Issue } from "../contracts";

const GENERIC =
  "这一项暂时无法确认。可以展开排查详情查看原因，或调整条件后重新核验。";

export const UNKNOWN_EXPLANATIONS: Record<string, string> = {
  FAKE_MODEL:
    "当前建议由演示模型生成。这只是流程演示，不代表真实模型的判断，可以只把课程与班次当作参考。",
  FAKE_TOOL:
    "当前核验使用演示数据，无法确认真实课程与班次。可以把结果当作流程演示来看，不要据此安排真实选课。",
  OFFERING_UNAVAILABLE:
    "没有取得目标学期的班次资料，无法确认上课时间是否冲突。可以稍后重试，或回到第一步换一份开课资料。",
  OFFERING_SNAPSHOT_MISSING:
    "方案没有可用的班次资料，无法确认上课时间。可以回到第一步选择有班次资料的开课版本后重新生成。",
  TIMETABLE_UNVERIFIED:
    "还有课程没有选定班次，或班次不是模拟来源，所以上课时间未核验，不能判为通过。可以为每门课选定班次后重新核验。",
  TIME_UNPARSEABLE:
    "部分班次的上课时间无法识别，无法确认是否冲突。可以在结果页换一个同课程的班次后重新核验。",
  TIME_UNPARSED:
    "部分班次的上课时间无法识别，无法确认是否冲突。可以在结果页换一个同课程的班次后重新核验。",
  CLASS_NOT_FOUND:
    "方案中的班次不在当前开课资料中，无法完成核验。可以在结果页换一个班次后重新核验。",
  PIN_TEACHER_UNKNOWN:
    "指定的教师无法从当前资料中确认。可以在目标里放宽教师要求，或改选其他教师的班次。",
  CONSTRAINT_UNVERIFIABLE:
    "部分限制条件缺少核验所需的资料。可以在目标里放宽该条件，或补充相应资料后重新生成。",
  COURSE_FACTS_UNKNOWN:
    "部分课程信息无法确认。可以检查该课程是否在所选培养方案中。",
  CREDITS_UNKNOWN:
    "部分课程学分未知，无法完成学分相关核对。可以在学业资料里为该课程补填学分。",
  CREDITS_SCOPE_UNSUPPORTED:
    "当前核验范围无法确认学分要求。学分是否达标请以培养方案原文为准。",
  CURRICULUM_NOT_FOUND:
    "所选培养方案资料无法读取。可以回到第一步重新选择培养方案。",
  ACADEMIC_RECORD_EMPTY:
    "还没有可用于核对的学业记录。可以在学业资料里补充已修课程。",
  TRANSCRIPT_COMPLETENESS_UNKNOWN:
    "已修课程可能没有填全，暂时无法确定剩余要求。可以在学业资料里确认是否已经填完整。",
  REQUIREMENT_SOURCE_REFS_MISSING:
    "部分培养要求缺少可核对的来源。可以对照培养方案原文自行确认。",
  UNMODELED_CURRICULUM_RULES:
    "培养方案中有部分规则系统尚未纳入自动核对（例如只限选、组选、学期限制）。请以培养方案原文为准，系统不会替你判定这些规则。",
  PENDING_COURSE_UNCATEGORIZED:
    "有一门课程尚未出结果，而且系统无法确定它属于哪个类别，所以所有要求的缺口都暂不能确定。可以在学业资料里确认它的结果，并检查课程是否在培养方案中。",
};

/** 与某一份方案的核验判决绑定的未知项：换班重新核验后，旧判决里的这些项不再适用。 */
const VERIFICATION_LEVEL_CODES = new Set([
  "TIMETABLE_UNVERIFIED",
  "TIME_UNPARSEABLE",
  "TIME_UNPARSED",
  "CLASS_NOT_FOUND",
  "UNMODELED_CURRICULUM_RULES",
  "PIN_TEACHER_UNKNOWN",
  "CONSTRAINT_UNVERIFIABLE",
  "OFFERING_UNAVAILABLE",
  "OFFERING_SNAPSHOT_MISSING",
]);

export function isVerificationLevelUnknown(code: string): boolean {
  return VERIFICATION_LEVEL_CODES.has(code);
}

/** Java 的 PENDING_COURSE message 形如「课程 CODE 在修或结果未知，CATEGORY 类别的缺口不能确定」。 */
const PENDING_COURSE_PATTERN =
  /课程 (\S+) 在修或结果未知(?:，(.+?) 类别的缺口不能确定)?/;

function pendingCourseText(
  issue: Issue,
  courseNames: Readonly<Record<string, string>>,
): string {
  const match = PENDING_COURSE_PATTERN.exec(issue.message);
  if (!match) return GENERIC;
  const code = match[1];
  const category = match[2];
  const name = courseNames[code];
  const label = name && name !== code ? `${name}（${code}）` : code;
  const categoryText = category
    ? `${category}类别的缺口暂不能确定`
    : "相关类别的缺口暂不能确定";
  return `${label} 在修或结果未知，${categoryText}。可以在学业资料里把它标为已修、未修或在修，确认后再核对。`;
}

/**
 * 把一条未知项翻译成学生可读的一句话。
 * courseNames 为课程号到课程名的表；读不到时只显示课程号，不编造课程名。
 */
export function explainUnknownIssue(
  issue: Issue,
  courseNames: Readonly<Record<string, string>> = {},
): string {
  if (issue.code === "PENDING_COURSE")
    return pendingCourseText(issue, courseNames);
  return UNKNOWN_EXPLANATIONS[issue.code] ?? GENERIC;
}
