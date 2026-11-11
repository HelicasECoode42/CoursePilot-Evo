/**
 * 加课接口（POST /api/v1/session-plans/add-course）的错误码 → 学生看得懂的话。
 * 只翻译服务端给出的码；码不认识时返回 null，由调用方用通用文案兜底。
 */
const ADD_COURSE_MESSAGES: Record<string, string> = {
  COURSE_ALREADY_IN_PLAN: "这门课已在方案里。",
  COURSE_ALREADY_TAKEN: "你已修过或正在修这门课，不能再加入方案。",
  PLAN_FULL: "方案已满（30 门课），先删除一门课再加。",
  OFFERING_SNAPSHOT_MISSING: "本学期开课资料暂时缺失，无法加课，请稍后再试。",
};

export function addCourseMessage(code: string | null): string | null {
  if (code === null) return null;
  return ADD_COURSE_MESSAGES[code] ?? null;
}
