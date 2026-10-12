import { createPinia, disposePinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SnapshotSummary } from "../contracts";
import { ApiFailure, type CoursePilotApiClient } from "../api/client";
import { createPlanningStore } from "./planning";

const curriculum: SnapshotSummary = {
  snapshotId: "curriculum-computer-science-2026",
  kind: "CURRICULUM",
  state: "PUBLISHED",
  sourceKind: "CURRICULUM_FILE",
  termId: null,
  createdAt: "2026-10-01T00:00:00Z",
  sourceValidation: "VERIFIED",
};

const session = (sessionId: string, expiresAt = "2099-01-01T00:00:00Z") => ({
  sessionId,
  expiresAt,
});

function fakeClient(
  overrides: Partial<CoursePilotApiClient> = {},
): CoursePilotApiClient {
  return {
    mode: "http",
    createSession: vi.fn(async () => session("session-1")),
    listCurricula: vi.fn(async () => ({
      items: [curriculum],
      unknownMessages: [],
    })),
    clearSession: vi.fn(),
    fixtureAcademicRecordId: vi.fn(() => null),
    ...overrides,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

describe("planning session store", () => {
  let pinias: ReturnType<typeof createPinia>[];

  beforeEach(() => {
    pinias = [createPinia()];
    const pinia = pinias[0];
    setActivePinia(pinia);
  });

  afterEach(() => {
    for (const pinia of pinias) disposePinia(pinia);
    vi.useRealTimers();
  });

  it("ignores repeated start clicks while session creation is pending", async () => {
    const pending = deferred<ReturnType<typeof session>>();
    const client = fakeClient({ createSession: vi.fn(() => pending.promise) });
    const store = createPlanningStore(client)();

    const first = store.startSession();
    await store.startSession();
    expect(client.createSession).toHaveBeenCalledTimes(1);
    pending.resolve(session("session-1"));
    await first;
    expect(store.sessionStatus).toBe("ready");
    expect(store.selectedCurriculumId).toBe(curriculum.snapshotId);
  });

  it("shows session creation failure and allows a fresh retry without fixture fallback", async () => {
    const createSession = vi
      .fn()
      .mockRejectedValueOnce(
        new ApiFailure(
          "暂时无法连接服务，请确认服务已启动后重试。",
          "network",
          null,
          null,
          true,
        ),
      )
      .mockResolvedValueOnce(session("session-retry"));
    const client = fakeClient({ createSession });
    const store = createPlanningStore(client)();

    await store.startSession();
    expect(store.sessionStatus).toBe("error");
    expect(store.curricula).toEqual([]);
    expect(store.errorMessage).toContain("确认服务已启动");
    expect(client.clearSession).toHaveBeenCalledOnce();

    await store.startSession();
    expect(createSession).toHaveBeenCalledTimes(2);
    expect(store.sessionStatus).toBe("ready");
  });

  it("drops a late successful session response after a newer session has started", async () => {
    const first = deferred<ReturnType<typeof session>>();
    const second = deferred<ReturnType<typeof session>>();
    const createSession = vi
      .fn()
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    const client = fakeClient({ createSession });
    const store = createPlanningStore(client)();

    const staleAttempt = store.startSession();
    store.invalidateSession("会话已重新开始。");
    const currentAttempt = store.startSession();
    second.resolve(session("session-current"));
    await currentAttempt;
    first.resolve(session("session-late"));
    await staleAttempt;

    expect(store.sessionId).toBe("session-current");
    expect(store.sessionStatus).toBe("ready");
  });

  it("expires the session, clears credentials and ignores a late curriculum response", async () => {
    vi.useFakeTimers();
    let bearer: string | null = null;
    let signalListStarted!: () => void;
    const listStarted = new Promise<void>((resolve) => {
      signalListStarted = resolve;
    });
    const lateCurricula = deferred<{
      items: SnapshotSummary[];
      unknownMessages: string[];
    }>();
    const client = fakeClient({
      createSession: vi.fn(async () => {
        bearer = "private-session-token";
        return session(
          "session-expiring",
          new Date(Date.now() + 1_000).toISOString(),
        );
      }),
      listCurricula: vi.fn(async () => {
        if (!bearer) {
          throw new ApiFailure("本次会话已失效，请重新开始。", "http", 401);
        }
        signalListStarted();
        return lateCurricula.promise;
      }),
      clearSession: vi.fn(() => {
        bearer = null;
      }),
    });
    const store = createPlanningStore(client)();
    store.setMotives(["LOW_WORKLOAD"]);
    const startup = store.startSession();
    await listStarted;

    await vi.advanceTimersByTimeAsync(2_000);

    expect(store.sessionStatus).toBe("expired");
    expect(store.sessionId).toBeNull();
    expect(store.curricula).toEqual([]);
    expect(store.draft.motives).toEqual(["LOW_WORKLOAD"]);
    expect(bearer).toBeNull();
    expect(client.clearSession).toHaveBeenCalledOnce();
    expect(store.preparePlanningHandoff()).toEqual({
      ok: false,
      missing: ["有效会话"],
    });

    lateCurricula.resolve({ items: [curriculum], unknownMessages: [] });
    await startup;
    expect(store.sessionStatus).toBe("expired");
    expect(store.sessionId).toBeNull();
    expect(store.curricula).toEqual([]);
  });

  it("rechecks expiresAt before preparing a handoff even before the timer callback runs", async () => {
    vi.useFakeTimers();
    let bearer: string | null = null;
    const client = fakeClient({
      createSession: vi.fn(async () => {
        bearer = "private-session-token";
        return session(
          "session-expiring",
          new Date(Date.now() + 1_000).toISOString(),
        );
      }),
      clearSession: vi.fn(() => {
        bearer = null;
      }),
    });
    const store = createPlanningStore(client)();
    await store.startSession();
    expect(store.sessionStatus).toBe("ready");

    vi.setSystemTime(Date.now() + 2_000);
    expect(store.preparePlanningHandoff()).toEqual({
      ok: false,
      missing: ["有效会话"],
    });
    expect(store.sessionStatus).toBe("expired");
    expect(store.sessionId).toBeNull();
    expect(bearer).toBeNull();
    expect(client.clearSession).toHaveBeenCalledOnce();
  });

  it("clears the expired-session blocker while rebuilding and after recovery", async () => {
    vi.useFakeTimers();
    const recoverySession = deferred<ReturnType<typeof session>>();
    const createSession = vi
      .fn()
      .mockImplementationOnce(async () =>
        session("session-short", new Date(Date.now() + 1_000).toISOString()),
      )
      .mockImplementationOnce(() => recoverySession.promise);
    const store = createPlanningStore(fakeClient({ createSession }))();
    await store.startSession();
    store.setMotives(["GPA"]);
    store.updateDraft("classPreferencesReviewed", true);
    store.updateDraft("mustReviewed", true);
    store.updateDraft("preferReviewed", true);
    store.confirmPriorities();

    expect(store.preparePlanningHandoff()).toEqual({
      ok: false,
      missing: ["学业记录"],
    });
    vi.setSystemTime(Date.now() + 2_000);
    expect(store.preparePlanningHandoff()).toEqual({
      ok: false,
      missing: ["有效会话"],
    });
    expect(store.handoffMissing).toEqual(["有效会话"]);

    const recovery = store.startSession();
    expect(store.sessionStatus).toBe("loading");
    expect(store.handoffMissing).toEqual([]);
    expect(store.planningHandoff).toBeNull();

    recoverySession.resolve(
      session("session-recovered", new Date(Date.now() + 60_000).toISOString()),
    );
    await recovery;

    expect(store.sessionStatus).toBe("ready");
    expect(store.handoffMissing).toEqual([]);
    expect(store.planningHandoff).toBeNull();
  });

  it("clears in-memory session credentials when the gateway reports 401", async () => {
    const client = fakeClient({
      listCurricula: vi.fn(async () => {
        throw new ApiFailure(
          "本次会话已失效，请重新开始。",
          "http",
          401,
          "SESSION_EXPIRED",
        );
      }),
    });
    const store = createPlanningStore(client)();

    await store.startSession();

    expect(store.sessionStatus).toBe("expired");
    expect(client.clearSession).toHaveBeenCalledOnce();
    expect(store.sessionId).toBeNull();
    expect(store.errorMessage).toContain("会话已失效");
  });

  it("keeps a retryable service failure actionable without fabricating curricula", async () => {
    const client = fakeClient({
      listCurricula: vi.fn(async () => {
        throw new ApiFailure(
          "服务暂时不可用，请稍后重试。",
          "http",
          503,
          "UPSTREAM_DOWN",
          true,
        );
      }),
    });
    const store = createPlanningStore(client)();

    await store.startSession();

    expect(store.sessionStatus).toBe("error");
    expect(store.curricula).toEqual([]);
    expect(store.errorMessage).toContain("请稍后重试");
  });

  it("keeps branch answers and review state when their triggering goal is removed", () => {
    const store = createPlanningStore(fakeClient())();
    store.setMotives(["CAREER", "INTEREST", "SCHEDULE", "GPA"]);
    store.updateDraft("careerText", "data science");
    store.updateDraft("interestTags", ["robotics"]);
    store.paintScheduleSlots(["4-2"], "must", "paint");
    store.paintScheduleSlots(["5-3"], "prefer", "paint");
    store.toggleClassPreference("LOWER_HOMEWORK");
    store.updateDraft("classPreferencesReviewed", true);
    store.setMotives(["GPA"]);

    expect(store.draft.careerText).toBe("data science");
    expect(store.draft.interestTags).toEqual(["robotics"]);
    expect(store.draft.mustSlots).toEqual(["4-2"]);
    expect(store.draft.preferSlots).toEqual(["5-3"]);
    expect(store.draft.classPreferences).toEqual(["LOWER_HOMEWORK"]);
    expect(store.draft.classPreferencesReviewed).toBe(true);
    expect(store.draft.priorityOrder).toEqual(["GPA"]);
    expect(store.draft.prioritiesConfirmed).toBe(false);
  });

  it("keeps both time answers through removing and reselecting the schedule goal", () => {
    const store = createPlanningStore(fakeClient())();
    store.setMotives(["SCHEDULE"]);
    store.paintScheduleSlots(["2-4"], "must", "paint");
    store.paintScheduleSlots(["5-7"], "prefer", "paint");
    // Any cell change clears both review flags (demo parity), so review last.
    store.updateDraft("mustReviewed", true);
    store.updateDraft("preferReviewed", true);

    const expectTimeAnswersKept = () => {
      expect(store.draft.mustSlots).toEqual(["2-4"]);
      expect(store.draft.mustReviewed).toBe(true);
      expect(store.draft.preferSlots).toEqual(["5-7"]);
      expect(store.draft.preferReviewed).toBe(true);
    };

    store.setMotives([]);
    expectTimeAnswersKept();

    store.setMotives(["SCHEDULE"]);
    expectTimeAnswersKept();
  });

  it("keeps must and prefer mutually exclusive for the same cell", () => {
    const store = createPlanningStore(fakeClient())();
    store.paintScheduleSlots(["3-2"], "prefer", "paint");
    expect(store.draft.preferSlots).toEqual(["3-2"]);
    expect(store.draft.mustSlots).toEqual([]);

    store.paintScheduleSlots(["3-2"], "must", "paint");
    expect(store.draft.mustSlots).toEqual(["3-2"]);
    expect(store.draft.preferSlots).toEqual([]);
  });

  it("switching strength never clears the other strength's cells", () => {
    const store = createPlanningStore(fakeClient())();
    store.paintScheduleSlots(["1-1"], "must", "paint");
    store.paintScheduleSlots(["2-2"], "prefer", "paint");
    store.paintScheduleSlots(["1-1"], "must", "erase");

    expect(store.draft.mustSlots).toEqual([]);
    expect(store.draft.preferSlots).toEqual(["2-2"]);
  });

  it("reports a fragmented schedule as an actionable hint instead of building a request", () => {
    const store = createPlanningStore(fakeClient())();
    const scattered: string[] = [];
    for (let day = 1; day <= 7; day += 1) {
      for (let section = day; section <= day + 4; section += 1) {
        scattered.push(`${day}-${section}`);
      }
    }
    store.$patch({
      sessionStatus: "ready",
      sessionId: "real-session",
      expiresAt: "2099-01-01T00:00:00Z",
      curricula: [curriculum],
      selectedCurriculumId: curriculum.snapshotId,
      draft: {
        ...store.draft,
        motives: ["SCHEDULE"],
        priorityOrder: ["SCHEDULE"],
        prioritiesConfirmed: true,
        classPreferencesReviewed: true,
        mustReviewed: true,
        preferReviewed: true,
        mustSlots: scattered,
      },
    });

    expect(store.preparePlanningHandoff()).toEqual({
      ok: false,
      missing: ["学业记录", "时间安排"],
      hints: [expect.stringContaining("上限 30")],
    });
    expect(store.planningHandoff).toBeNull();
    expect(store.handoffHints).toHaveLength(1);
    expect(store.handoffMissing).toEqual(["学业记录", "时间安排"]);
  });

  it("keeps class preferences and their review state when related goals change", () => {
    const store = createPlanningStore(fakeClient())();
    store.setMotives(["GPA", "LOW_WORKLOAD"]);
    store.toggleClassPreference("GRADING_FEEDBACK");
    store.updateDraft("classPreferencesReviewed", true);

    store.setMotives(["LOW_WORKLOAD"]);
    expect(store.draft.classPreferences).toEqual(["GRADING_FEEDBACK"]);
    expect(store.draft.classPreferencesReviewed).toBe(true);

    store.setMotives(["CAREER"]);
    expect(store.draft.classPreferences).toEqual(["GRADING_FEEDBACK"]);
    expect(store.draft.classPreferencesReviewed).toBe(true);
  });

  it("builds a fixture handoff while real mode reports missing academic records", () => {
    const fixtureClient = fakeClient({
      mode: "fixture",
      fixtureAcademicRecordId: () => "fixture-record-e1",
    });
    const fixtureStore = createPlanningStore(fixtureClient)();
    fixtureStore.$patch({
      sessionStatus: "ready",
      sessionId: "fixture-session",
      expiresAt: "2099-01-01T00:00:00Z",
      curricula: [
        {
          ...curriculum,
          sourceKind: "SYNTHETIC",
          sourceValidation: "SYNTHETIC",
        },
      ],
      selectedCurriculumId: curriculum.snapshotId,
      draft: {
        ...fixtureStore.draft,
        motives: ["GPA"],
        priorityOrder: ["GPA"],
        classPreferencesReviewed: true,
        prioritiesConfirmed: true,
        mustReviewed: true,
        preferReviewed: true,
      },
    });

    expect(fixtureStore.preparePlanningHandoff()).toMatchObject({ ok: true });
    expect(fixtureStore.planningHandoff?.academicRecordId).toBe(
      "fixture-record-e1",
    );
    expect(fixtureStore.planningHandoff?.mode).toBe("SIMULATION");

    const realPinia = createPinia();
    pinias.push(realPinia);
    setActivePinia(realPinia);
    const realStore = createPlanningStore(fakeClient())();
    realStore.$patch({
      sessionStatus: "ready",
      sessionId: "real-session",
      expiresAt: "2099-01-01T00:00:00Z",
      curricula: [curriculum],
      selectedCurriculumId: curriculum.snapshotId,
      draft: {
        ...realStore.draft,
        motives: ["GPA"],
        priorityOrder: ["GPA"],
        classPreferencesReviewed: true,
        prioritiesConfirmed: true,
        mustReviewed: true,
        preferReviewed: true,
      },
    });
    expect(realStore.preparePlanningHandoff()).toEqual({
      ok: false,
      missing: ["学业记录"],
    });
    expect(realStore.planningHandoff).toBeNull();
  });

  it("clears stale handoff missing labels when planning inputs or the session change", () => {
    const store = createPlanningStore(fakeClient())();
    const invalidations = [
      () => store.chooseCurriculum(curriculum.snapshotId),
      () => store.updateDraft("careerText", "data science"),
      () => store.setMotives(["CAREER", "GPA", "INTEREST"]),
      () => store.movePriority("CAREER", -1),
      () => store.invalidateSession("会话已过期。"),
    ];

    for (const invalidate of invalidations) {
      store.$patch({
        sessionStatus: "ready",
        sessionId: "real-session",
        expiresAt: "2099-01-01T00:00:00Z",
        curricula: [curriculum],
        selectedCurriculumId: curriculum.snapshotId,
        draft: {
          ...store.draft,
          motives: ["GPA", "CAREER"],
          priorityOrder: ["GPA", "CAREER"],
          classPreferencesReviewed: true,
          prioritiesConfirmed: true,
          mustReviewed: true,
          preferReviewed: true,
        },
      });

      expect(store.preparePlanningHandoff()).toEqual({
        ok: false,
        missing: ["学业记录"],
      });
      expect(store.handoffMissing).toEqual(["学业记录"]);

      invalidate();

      expect(store.planningHandoff).toBeNull();
      expect(store.handoffMissing).toEqual([]);
    }
  });
});
