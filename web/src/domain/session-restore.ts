/**
 * 页面刷新后的会话恢复：把会话令牌、规划草稿和当前结果存在本标签页的 sessionStorage 里。
 *
 * 只存标识与学生自己填的答案，不存成绩、学校凭据或评价原文以外的任何身份材料。
 * 每个读写都包在 try/catch 里：隐私模式、存储被禁用或配额满时，页面照常工作，只是刷新后不能恢复。
 * 恢复出来的令牌仍要用一次只读请求确认（401 即已过期），不能因为本地有记录就认为有效。
 */

import type { PlanningAnswer, SessionPlanEditResult } from "../contracts";
import type { PlanningDraft } from "./question-flow";

export const SAVED_SESSION_KEY = "coursepilot.session.v1";

export interface SavedPlanningSession {
  sessionId: string;
  sessionToken: string;
  expiresAt: string;
  selectedCurriculumId: string | null;
  selectedOfferingSnapshotId: string | null;
  selectedRecordId: string | null;
  draft: PlanningDraft;
  planningResult: PlanningAnswer | null;
  /** 键为原推荐的 planId；值是服务端确认的编辑版本（含新 planId 与判决）。 */
  editedPlans: Record<string, SessionPlanEditResult>;
  teacherPickDisplayNames: Record<string, string>;
}

/** sessionStorage 的最小接口，便于测试时替换成内存实现。 */
export interface KeyValueStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

/** 取本标签页的 sessionStorage；访问本身可能抛错（被浏览器禁用），这时返回 null。 */
export function defaultSessionStorage(): KeyValueStorage | null {
  try {
    const storage = globalThis.sessionStorage;
    return storage ?? null;
  } catch {
    return null;
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** 只检查恢复页面必需的形状；内容错误交给服务端与页面的既有校验。 */
function isSavedSession(value: unknown): value is SavedPlanningSession {
  if (!isObject(value)) return false;
  const draft = value.draft;
  return (
    typeof value.sessionId === "string" &&
    typeof value.sessionToken === "string" &&
    value.sessionToken.length >= 32 &&
    value.sessionToken.length <= 512 &&
    typeof value.expiresAt === "string" &&
    isObject(draft) &&
    Array.isArray(draft.motives) &&
    Array.isArray(draft.selectedCourseCodes) &&
    Array.isArray(draft.preferredCourseCodes) &&
    isObject(value.editedPlans) &&
    isObject(value.teacherPickDisplayNames) &&
    (value.planningResult === null || isObject(value.planningResult))
  );
}

export function readSavedSession(
  storage: KeyValueStorage | null,
): SavedPlanningSession | null {
  if (storage === null) return null;
  try {
    const raw = storage.getItem(SAVED_SESSION_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    return isSavedSession(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export function writeSavedSession(
  storage: KeyValueStorage | null,
  saved: SavedPlanningSession,
): void {
  if (storage === null) return;
  try {
    storage.setItem(SAVED_SESSION_KEY, JSON.stringify(saved));
  } catch {
    // 配额满或被禁用：本次不保存，页面继续在内存中工作。
  }
}

export function clearSavedSession(storage: KeyValueStorage | null): void {
  if (storage === null) return;
  try {
    storage.removeItem(SAVED_SESSION_KEY);
  } catch {
    // 无法清除时，下次读取会因为过期或校验失败而被丢弃。
  }
}

/** 过期时间是否仍在将来；无法解析的时间视为已过期。 */
export function isStillValidUntil(expiresAt: string, now: number): boolean {
  const expiry = Date.parse(expiresAt);
  return Number.isFinite(expiry) && expiry > now;
}
