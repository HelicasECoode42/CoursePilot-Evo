import { describe, expect, it } from "vitest";
import { emptyPlanningDraft } from "./question-flow";
import {
  clearSavedSession,
  isStillValidUntil,
  readSavedSession,
  SAVED_SESSION_KEY,
  writeSavedSession,
  type KeyValueStorage,
  type SavedPlanningSession,
} from "./session-restore";

class MemoryStorage implements KeyValueStorage {
  readonly data = new Map<string, string>();
  getItem(key: string) {
    return this.data.get(key) ?? null;
  }
  setItem(key: string, value: string) {
    this.data.set(key, value);
  }
  removeItem(key: string) {
    this.data.delete(key);
  }
}

const TOKEN = "t".repeat(64);

function saved(
  overrides: Partial<SavedPlanningSession> = {},
): SavedPlanningSession {
  return {
    sessionId: "session:abc",
    sessionToken: TOKEN,
    expiresAt: "2099-01-01T00:00:00Z",
    selectedCurriculumId: "curriculum-cs-2026",
    selectedOfferingSnapshotId: "offering-2026-1",
    selectedRecordId: "record:1",
    draft: { ...emptyPlanningDraft(), selectedCourseCodes: ["CS101"] },
    planningResult: null,
    editedPlans: {},
    teacherPickDisplayNames: {},
    ...overrides,
  };
}

describe("sessionStorage 中的会话恢复", () => {
  it("写入后可以原样读回，草稿与所选课程都保留", () => {
    const storage = new MemoryStorage();
    writeSavedSession(storage, saved());
    const back = readSavedSession(storage);
    expect(back?.sessionId).toBe("session:abc");
    expect(back?.draft.selectedCourseCodes).toEqual(["CS101"]);
    expect(back?.selectedOfferingSnapshotId).toBe("offering-2026-1");
  });

  it("清除后读不到，且不影响其他键", () => {
    const storage = new MemoryStorage();
    storage.setItem("other", "keep");
    writeSavedSession(storage, saved());
    clearSavedSession(storage);
    expect(readSavedSession(storage)).toBeNull();
    expect(storage.getItem("other")).toBe("keep");
  });

  it("形状不对、JSON 损坏或令牌长度异常时丢弃，不抛错", () => {
    const storage = new MemoryStorage();
    storage.setItem(SAVED_SESSION_KEY, "{not json");
    expect(readSavedSession(storage)).toBeNull();
    storage.setItem(SAVED_SESSION_KEY, JSON.stringify({ sessionId: "x" }));
    expect(readSavedSession(storage)).toBeNull();
    writeSavedSession(storage, saved({ sessionToken: "short" }));
    expect(readSavedSession(storage)).toBeNull();
  });

  it("存储不可用（为空或读写都抛错）时静默退化，页面仍可工作", () => {
    const broken: KeyValueStorage = {
      getItem() {
        throw new Error("denied");
      },
      setItem() {
        throw new Error("quota");
      },
      removeItem() {
        throw new Error("denied");
      },
    };
    expect(() => writeSavedSession(broken, saved())).not.toThrow();
    expect(() => clearSavedSession(broken)).not.toThrow();
    expect(readSavedSession(broken)).toBeNull();
    expect(readSavedSession(null)).toBeNull();
    expect(() => writeSavedSession(null, saved())).not.toThrow();
  });

  it("过期时间判断：过去或无法解析都视为无效", () => {
    expect(isStillValidUntil("2099-01-01T00:00:00Z", Date.now())).toBe(true);
    expect(isStillValidUntil("2000-01-01T00:00:00Z", Date.now())).toBe(false);
    expect(isStillValidUntil("not a date", Date.now())).toBe(false);
  });

  it("不保存成绩或学校凭据这类字段（只有 id 与学生自己的答案）", () => {
    const storage = new MemoryStorage();
    writeSavedSession(storage, saved());
    const raw = storage.getItem(SAVED_SESSION_KEY) ?? "";
    expect(raw).not.toMatch(/password|credential|grade|outcome/i);
  });
});
