import { createPinia, setActivePinia } from "pinia";
import { flushPromises } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { SnapshotSummary } from "../contracts";
import { ApiFailure, type CoursePilotApiClient } from "../api/client";
import {
  readSavedSession,
  SAVED_SESSION_KEY,
  writeSavedSession,
  type KeyValueStorage,
  type SavedPlanningSession,
} from "../domain/session-restore";
import { emptyPlanningDraft } from "../domain/question-flow";
import { createPlanningStore } from "./planning";

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

const TOKEN = "s".repeat(64);
const curriculum: SnapshotSummary = {
  snapshotId: "curriculum-cs-2026",
  kind: "CURRICULUM",
  state: "PUBLISHED",
  sourceKind: "CURRICULUM_FILE",
  termId: null,
  createdAt: "2026-10-01T00:00:00Z",
  sourceValidation: "VERIFIED",
};

function client(overrides: Partial<CoursePilotApiClient> = {}) {
  let token: string | null = null;
  const base = {
    mode: "http",
    createSession: vi.fn(async () => {
      token = TOKEN;
      return { sessionId: "session:1", expiresAt: "2099-01-01T00:00:00Z" };
    }),
    listCurricula: vi.fn(async () => ({
      items: [curriculum],
      unknownMessages: [],
    })),
    listOfferingSnapshots: vi.fn(async () => ({
      items: [],
      unknownMessages: [],
    })),
    clearSession: vi.fn(() => {
      token = null;
    }),
    restoreSession: vi.fn((value: string) => {
      token = value;
    }),
    currentSessionToken: vi.fn(() => token),
    fixtureAcademicRecordId: vi.fn(() => null),
    ...overrides,
  } as unknown as CoursePilotApiClient;
  return base;
}

function savedState(): SavedPlanningSession {
  return {
    sessionId: "session:1",
    sessionToken: TOKEN,
    expiresAt: "2099-01-01T00:00:00Z",
    selectedCurriculumId: curriculum.snapshotId,
    selectedOfferingSnapshotId: null,
    selectedRecordId: null,
    draft: {
      ...emptyPlanningDraft(),
      selectedCourseCodes: ["CS101", "CS102"],
      motives: ["GRADUATION"],
    },
    planningResult: null,
    editedPlans: {},
    teacherPickDisplayNames: {},
  } as unknown as SavedPlanningSession;
}

describe("刷新后恢复会话与草稿", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("令牌仍有效时恢复草稿与所选课程，状态回到 ready", async () => {
    const storage = new MemoryStorage();
    writeSavedSession(storage, savedState());
    const api = client();
    const store = createPlanningStore(api, storage)();

    await store.restoreSavedSession();

    expect(api.restoreSession).toHaveBeenCalledWith(TOKEN);
    expect(store.sessionStatus).toBe("ready");
    expect(store.sessionId).toBe("session:1");
    expect(store.draft.selectedCourseCodes).toEqual(["CS101", "CS102"]);
    expect(store.draft.motives).toEqual(["GRADUATION"]);
    expect(store.selectedCurriculumId).toBe(curriculum.snapshotId);
  });

  it("服务端 401（过期或服务重启）：清空草稿、清除保存、提示会话已过期，不静默新建", async () => {
    const storage = new MemoryStorage();
    writeSavedSession(storage, savedState());
    const api = client({
      listCurricula: vi.fn(async () => {
        throw new ApiFailure("令牌无效", "http", 401, "UNAUTHORIZED");
      }),
    });
    const store = createPlanningStore(api, storage)();

    await store.restoreSavedSession();

    expect(store.sessionStatus).toBe("expired");
    expect(store.errorMessage).toBe("会话已过期，请重新开始。");
    expect(store.draft.selectedCourseCodes).toEqual([]);
    expect(api.createSession).not.toHaveBeenCalled();
    expect(storage.getItem(SAVED_SESSION_KEY)).toBeNull();
  });

  it("网络错误：保留令牌与草稿，状态为 error，之后可以直接重试而不新建会话", async () => {
    const storage = new MemoryStorage();
    writeSavedSession(storage, savedState());
    const api = client({
      listCurricula: vi.fn(async () => {
        throw new ApiFailure("网络不通", "network");
      }),
    });
    const store = createPlanningStore(api, storage)();

    await store.restoreSavedSession();

    expect(store.sessionStatus).toBe("error");
    expect(store.draft.selectedCourseCodes).toEqual(["CS101", "CS102"]);
    expect(readSavedSession(storage)).not.toBeNull();
  });

  it("已过期的保存记录直接丢弃", async () => {
    const storage = new MemoryStorage();
    writeSavedSession(storage, {
      ...savedState(),
      expiresAt: "2000-01-01T00:00:00Z",
    });
    const api = client();
    const store = createPlanningStore(api, storage)();

    await store.restoreSavedSession();

    expect(api.restoreSession).not.toHaveBeenCalled();
    expect(store.sessionStatus).toBe("idle");
    expect(storage.getItem(SAVED_SESSION_KEY)).toBeNull();
  });

  it("恢复尚未完成时，页面发起的 startSession 等待恢复结束，而不是报告建立会话失败", async () => {
    const storage = new MemoryStorage();
    writeSavedSession(storage, savedState());
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const api = client({
      listCurricula: vi.fn(async () => {
        await gate;
        return { items: [curriculum], unknownMessages: [] };
      }),
    });
    const store = createPlanningStore(api, storage)();

    const restoring = store.restoreSavedSession();
    const starting = store.startSession();
    release();
    await Promise.all([restoring, starting]);

    expect(store.sessionStatus).toBe("ready");
    expect(store.errorMessage).toBe("");
    expect(api.createSession).not.toHaveBeenCalled();
  });

  it("没有传入存储时不持久化、不恢复（测试与演示路径不受影响）", async () => {
    const api = client();
    const store = createPlanningStore(api)();
    await store.startSession();
    await flushPromises();
    expect(store.sessionStatus).toBe("ready");
    await store.restoreSavedSession();
    expect(api.restoreSession).not.toHaveBeenCalled();
  });

  it("建立会话后自动写入本标签页存储，草稿变化也会同步", async () => {
    const storage = new MemoryStorage();
    const store = createPlanningStore(client(), storage)();
    await store.startSession();
    await flushPromises();
    store.updateDraft("selectedCourseCodes", ["CS103"]);
    await flushPromises();

    const back = readSavedSession(storage);
    expect(back?.sessionId).toBe("session:1");
    expect(back?.sessionToken).toBe(TOKEN);
    expect(back?.draft.selectedCourseCodes).toEqual(["CS103"]);
  });
});
