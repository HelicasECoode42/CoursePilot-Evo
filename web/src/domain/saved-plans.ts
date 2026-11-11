/**
 * 「保存到本机浏览器」的方案副本（纯函数 + 一层 localStorage 包装）。
 *
 * 边界（见 AGENTS.md）：
 *  - 只保存页面已经显示过的方案事实：课程号、课程名、学分、必修/选修、班次号、
 *    教师、时间（结构化 meetings 与原文展示）、判决摘要、学期说明；
 *  - 不保存成绩、学校导入数据、凭据、令牌、完整 Prompt 或推荐理由的模型原文；
 *  - 副本只供回看，页面必须标明「非最新核验结果」；
 *  - 所有读写都包在 try/catch 里：隐私模式、禁用存储或配额满时，页面照常工作，只是保存失败。
 */

import type { Meeting, PlanningContext } from "../contracts";

export const SAVED_PLANS_KEY = "coursepilot.savedPlans.v1";
export const SAVED_PLANS_LIMIT = 20;
export const SAVED_PLAN_NOTICE = "本机保存的副本，非最新核验结果";

export interface SavedPlanCourse {
  courseCode: string;
  name: string | null;
  credits: number | null;
  tag: "必修" | "选修" | null;
  classId: string | null;
  teacherText: string;
  /** 结果页上显示的完整时间文字。 */
  timeText: string;
  meetings: Meeting[];
}

export interface SavedPlan {
  id: string;
  savedAt: string;
  planId: string;
  /** 页面上的方案序号（从 1 开始）。 */
  planNumber: number;
  /** 是否为换班或删除课程后的版本。 */
  edited: boolean;
  courses: SavedPlanCourse[];
  /** 保存时的判决摘要：范围与判决原样保存，label 是页面当时显示的文字。 */
  verdict: { scope: string | null; verdict: string | null; label: string };
  planningContext: PlanningContext | null;
}

export type SavedPlanInput = Omit<SavedPlan, "id" | "savedAt">;

/** 只复制白名单字段，避免把整个结果对象（含原始诊断）写进本机。 */
export function buildSavedPlan(
  input: SavedPlanInput,
  id: string,
  now: Date,
): SavedPlan {
  return {
    id,
    savedAt: now.toISOString(),
    planId: input.planId,
    planNumber: input.planNumber,
    edited: input.edited,
    courses: input.courses.map((course) => ({
      courseCode: course.courseCode,
      name: course.name,
      credits: course.credits,
      tag: course.tag,
      classId: course.classId,
      teacherText: course.teacherText,
      timeText: course.timeText,
      meetings: course.meetings.map((meeting) => ({
        dayOfWeek: meeting.dayOfWeek,
        sectionStart: meeting.sectionStart,
        sectionEnd: meeting.sectionEnd,
        weeks: [...meeting.weeks],
      })),
    })),
    verdict: {
      scope: input.verdict.scope,
      verdict: input.verdict.verdict,
      label: input.verdict.label,
    },
    planningContext:
      input.planningContext === null
        ? null
        : {
            targetTerm: input.planningContext.targetTerm,
            timetableReferenceSnapshotId:
              input.planningContext.timetableReferenceSnapshotId,
            timetableReferenceTermId:
              input.planningContext.timetableReferenceTermId,
            timetableSourceValidation:
              input.planningContext.timetableSourceValidation,
          },
  };
}

export function newSavedPlanId(): string {
  return `saved-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

/* ---------- 读入时校验：localStorage 可能被改坏，坏条目直接丢弃 ---------- */

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isMeeting(value: unknown): value is Meeting {
  return (
    isRecord(value) &&
    typeof value.dayOfWeek === "number" &&
    typeof value.sectionStart === "number" &&
    typeof value.sectionEnd === "number" &&
    Array.isArray(value.weeks) &&
    value.weeks.every((week) => typeof week === "number")
  );
}

function isCourse(value: unknown): value is SavedPlanCourse {
  return (
    isRecord(value) &&
    typeof value.courseCode === "string" &&
    (value.name === null || typeof value.name === "string") &&
    (value.credits === null || typeof value.credits === "number") &&
    (value.tag === null || value.tag === "必修" || value.tag === "选修") &&
    (value.classId === null || typeof value.classId === "string") &&
    typeof value.teacherText === "string" &&
    typeof value.timeText === "string" &&
    Array.isArray(value.meetings) &&
    value.meetings.every(isMeeting)
  );
}

function isSavedPlan(value: unknown): value is SavedPlan {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.savedAt === "string" &&
    typeof value.planId === "string" &&
    typeof value.planNumber === "number" &&
    typeof value.edited === "boolean" &&
    Array.isArray(value.courses) &&
    value.courses.every(isCourse) &&
    isRecord(value.verdict) &&
    typeof value.verdict.label === "string" &&
    (value.planningContext === null || isRecord(value.planningContext))
  );
}

/** 解析存储内容；不是数组或条目不合格时只保留合格的部分。 */
export function parseSavedPlans(raw: unknown): SavedPlan[] {
  if (!Array.isArray(raw)) return [];
  return raw.filter(isSavedPlan).slice(0, SAVED_PLANS_LIMIT);
}

/* ---------- 存储包装：所有访问都可能抛错 ---------- */

type PlanStorage = Pick<Storage, "getItem" | "setItem">;

/** 取浏览器的 localStorage；访问本身可能抛错（隐私模式、被禁用），此时返回 null。 */
export function defaultSavedPlanStorage(): PlanStorage | null {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}

export function loadSavedPlans(storage: PlanStorage | null): SavedPlan[] {
  if (storage === null) return [];
  try {
    const text = storage.getItem(SAVED_PLANS_KEY);
    if (text === null) return [];
    return parseSavedPlans(JSON.parse(text));
  } catch {
    return [];
  }
}

function writeSavedPlans(
  storage: PlanStorage | null,
  plans: SavedPlan[],
): boolean {
  if (storage === null) return false;
  try {
    storage.setItem(SAVED_PLANS_KEY, JSON.stringify(plans));
    return true;
  } catch {
    return false;
  }
}

export type SaveResult =
  | { ok: true; plans: SavedPlan[] }
  | { ok: false; reason: "LIMIT" | "STORAGE"; plans: SavedPlan[] };

/** 新副本放在最前面。数量到上限时拒绝保存，不悄悄挤掉旧副本。 */
export function saveNewPlan(
  plan: SavedPlan,
  storage: PlanStorage | null,
): SaveResult {
  const current = loadSavedPlans(storage);
  if (current.length >= SAVED_PLANS_LIMIT) {
    return { ok: false, reason: "LIMIT", plans: current };
  }
  const next = [plan, ...current];
  if (!writeSavedPlans(storage, next)) {
    return { ok: false, reason: "STORAGE", plans: current };
  }
  return { ok: true, plans: next };
}

export function deleteSavedPlan(
  id: string,
  storage: PlanStorage | null,
): SavedPlan[] {
  const current = loadSavedPlans(storage);
  const next = current.filter((plan) => plan.id !== id);
  // 写不进去时保留原列表，页面上不会出现「已删除」但下次打开又回来的情况。
  return writeSavedPlans(storage, next) ? next : current;
}
