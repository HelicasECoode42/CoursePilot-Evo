import { createPinia, disposePinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  AcademicRecord,
  AcademicRecordInput,
  AdviceChatAnswer,
  AuditResult,
  CompletedCourse,
  PlanningAnswer,
  PlanningRequest,
  SnapshotSummary,
} from "../contracts";
import { ApiFailure, type CoursePilotApiClient } from "../api/client";
import type {
  SchoolProgressImportResult,
  SchoolProgressSnapshot,
} from "../domain/school-progress";
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
    listCourses: vi.fn(async () => ({ items: [], nextCursor: null })),
    listCareerDirections: vi.fn(async () => []),
    listCurricula: vi.fn(async () => ({
      items: [curriculum],
      unknownMessages: [],
    })),
    listOfferingSnapshots: vi.fn(async () => ({
      items: [],
      unknownMessages: [],
    })),
    clearSession: vi.fn(),
    fixtureAcademicRecordId: vi.fn(() => null),
    listSessionRecords: vi.fn(async () => ({ items: [] })),
    removeSessionPlanCourse: vi.fn(async (body) => ({
      previousPlanId: body.previousPlanId,
      planId: "plan-empty",
      items: [],
      hardConstraints: [],
      verification: null,
      empty: true,
    })),
    saveSchoolProgress: vi.fn(async () => {
      throw new Error("not used in this test");
    }),
    importSchoolProgress: vi.fn(async () => {
      throw new Error("not used in this test");
    }),
    getSchoolProgress: vi.fn(async () => null),
    saveSessionRecord: vi.fn(async (input) => ({
      academicRecordId: "record-1",
      revision: 1,
      curriculumSnapshotId: input.curriculumSnapshotId,
      completedCourses: input.completedCourses,
      transcriptComplete: input.transcriptComplete,
      sourceKind: input.sourceKind,
      createdAt: "2026-10-01T00:00:00Z",
    })),
    auditRequirements: vi.fn(
      async (curriculumSnapshotId, academicRecordId) => ({
        curriculumSnapshotId,
        academicRecordId,
        recordRevision: 1,
        transcriptComplete: false,
        requirements: [],
        suggestedCourseCodes: [],
        unknowns: [],
      }),
    ),
    submitPlanning: vi.fn(async () => {
      throw new ApiFailure("stub 未实现规划", "invalid_response");
    }),
    adviceChat: vi.fn(async () => {
      throw new ApiFailure("stub 未实现对话", "invalid_response");
    }),
    // E4 方法在这份 store 测试里用不到，统一给出明确的未实现错误。
    searchSessionOfferings: vi.fn(async () => {
      throw new ApiFailure("stub 未实现班次搜索", "invalid_response");
    }),
    replaceSessionPlanItem: vi.fn(async () => {
      throw new ApiFailure("stub 未实现换班次", "invalid_response");
    }),
    listTeacherCourseOptions: vi.fn(async () => {
      throw new ApiFailure("stub 未实现教师查询", "invalid_response");
    }),
    searchReviews: vi.fn(async () => {
      throw new ApiFailure("stub 未实现评价检索", "invalid_response");
    }),
    getRunReport: vi.fn(async () => {
      throw new ApiFailure("stub 未实现运行报告", "invalid_response");
    }),
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

  it("sends a chat message and adopts interest and preferred courses only after explicit confirmation", async () => {
    const answer: AdviceChatAnswer = {
      schemaVersion: "1.0",
      reply: "可先了解这门课程。",
      question: null,
      courses: [
        {
          courseCode: "CS201",
          name: "数据分析",
          credits: 3,
          category: "专业选修课",
          reason: "与方向相关",
          reviewNoteIds: [],
          reviews: [],
          reviewStatus: "NONE",
        },
      ],
      suggestions: [
        {
          suggestionId: "s-interest",
          kind: "INTEREST",
          label: "采用兴趣",
          value: "数据分析",
        },
        {
          suggestionId: "s-prefer",
          kind: "PREFER_COURSE",
          label: "优先考虑课程",
          value: "CS201",
        },
      ],
      schoolProgress: null,
      unknowns: [],
      usage: {
        inputTokens: 10,
        outputTokens: 20,
        toolCalls: 1,
        elapsedMs: 100,
      },
    };
    const adviceChat = vi.fn(async () => answer);
    const store = createPlanningStore(fakeClient({ adviceChat }))();
    await store.startSession();
    expect(await store.sendAdviceMessage("想了解数据分析方向")).toBe(true);
    expect(store.adviceMessages.map((item) => item.role)).toEqual([
      "user",
      "assistant",
    ]);
    expect(store.adviceMessages[1]?.text).toBe(answer.reply);
    expect(store.draft.careerText).toBe("");
    expect(store.draft.preferredCourseCodes).toEqual([]);
    expect(store.adoptAdviceSuggestion(answer, "s-interest")).toBe(true);
    expect(store.adoptAdviceSuggestion(answer, "s-interest")).toBe(true);
    expect(store.draft.careerText).toBe("数据分析");
    expect(store.adoptAdviceSuggestion(answer, "s-prefer")).toBe(true);
    expect(store.adoptAdviceSuggestion(answer, "s-prefer")).toBe(true);
    expect(store.draft.preferredCourseCodes).toEqual(["CS201"]);
    expect(store.draft.selectedCourseCodes).toEqual([]);
  });

  it("retries a failed identical chat request with the same idempotency key", async () => {
    const answer: AdviceChatAnswer = {
      schemaVersion: "1.0",
      reply: "已收到。",
      question: null,
      courses: [],
      suggestions: [],
      schoolProgress: null,
      unknowns: [],
      usage: {
        inputTokens: null,
        outputTokens: null,
        toolCalls: 0,
        elapsedMs: 0,
      },
    };
    const adviceChat = vi
      .fn()
      .mockRejectedValueOnce(
        new ApiFailure("连接失败", "network", null, null, true),
      )
      .mockResolvedValueOnce(answer);
    const store = createPlanningStore(fakeClient({ adviceChat }))();
    await store.startSession();
    expect(await store.sendAdviceMessage("原问题")).toBe(false);
    expect(store.adviceFailure?.retryMode).toBe("same-key");
    expect(store.adviceBusy).toBe(false);
    expect(store.advicePendingMessage).toBe("");
    expect(await store.retryAdviceMessage()).toBe(true);
    expect(adviceChat).toHaveBeenCalledTimes(2);
    expect(adviceChat.mock.calls[0]?.[1]).toBe(adviceChat.mock.calls[1]?.[1]);
    expect(adviceChat.mock.calls[0]?.[0]).toEqual(
      adviceChat.mock.calls[1]?.[0],
    );
  });

  it("tells the student the session advice budget is spent and offers no retry that cannot succeed", async () => {
    const adviceChat = vi
      .fn()
      .mockRejectedValue(
        new ApiFailure(
          "本会话累计 output token 已达上限，请新建会话",
          "http",
          503,
          "BUDGET_EXCEEDED",
        ),
      );
    const store = createPlanningStore(fakeClient({ adviceChat }))();
    await store.startSession();
    expect(await store.sendAdviceMessage("再问一个问题")).toBe(false);
    expect(store.adviceFailure?.retryMode).toBe("none");
    expect(store.adviceError).toContain("对话额度已用完");
    expect(store.adviceError).not.toContain("重新生成");
    expect(await store.retryAdviceMessage()).toBe(false);
    expect(await store.regenerateAdviceMessage()).toBe(false);
    expect(adviceChat).toHaveBeenCalledTimes(1);
  });

  it("uses a new explicit key to regenerate terminal model failures and preserves adopted preferences", async () => {
    const answer: AdviceChatAnswer = {
      schemaVersion: "1.0",
      reply: "建议数据分析方向。",
      question: null,
      courses: [],
      suggestions: [
        {
          suggestionId: "interest-data",
          kind: "INTEREST",
          label: "采用数据分析兴趣",
          value: "数据分析",
        },
      ],
      schoolProgress: null,
      unknowns: [],
      usage: {
        inputTokens: null,
        outputTokens: null,
        toolCalls: 0,
        elapsedMs: 0,
      },
    };
    const repaired: AdviceChatAnswer = { ...answer, reply: "重新生成的回答" };
    const terminalFailure = new ApiFailure(
      "旧的接口通用文案",
      "http",
      422,
      "MODEL_INVALID_OUTPUT",
    );
    const adviceChat = vi
      .fn()
      .mockResolvedValueOnce(answer)
      .mockRejectedValueOnce(terminalFailure)
      .mockRejectedValueOnce(terminalFailure)
      .mockResolvedValueOnce(repaired);
    const store = createPlanningStore(fakeClient({ adviceChat }))();
    await store.startSession();
    await store.sendAdviceMessage("先聊兴趣");
    expect(store.adoptAdviceSuggestion(answer, "interest-data")).toBe(true);
    expect(await store.sendAdviceMessage("接口输出失败的问题")).toBe(false);
    expect(store.adviceFailure?.retryMode).toBe("regenerate");
    expect(store.adviceError).toContain("可重新生成回答");
    expect(store.adviceError).not.toContain("没有写入任何方案");
    expect(store.adviceBusy).toBe(false);
    expect(store.advicePendingMessage).toBe("");
    expect(store.adviceMessages.map((item) => item.text)).not.toContain(
      "接口输出失败的问题",
    );

    expect(await store.sendAdviceMessage("接口输出失败的问题")).toBe(false);
    expect(adviceChat).toHaveBeenCalledTimes(2);
    expect(await store.retryAdviceMessage()).toBe(false);
    expect(adviceChat).toHaveBeenCalledTimes(3);
    expect(adviceChat.mock.calls[1]?.[1]).toBe(adviceChat.mock.calls[2]?.[1]);
    expect(store.adviceFailure?.retryMode).toBe("regenerate");

    expect(await store.regenerateAdviceMessage()).toBe(true);
    expect(adviceChat).toHaveBeenCalledTimes(4);
    expect(adviceChat.mock.calls[2]?.[1]).not.toBe(
      adviceChat.mock.calls[3]?.[1],
    );
    expect(adviceChat.mock.calls[2]?.[0]).toEqual(
      adviceChat.mock.calls[3]?.[0],
    );
    expect(store.draft.careerText).toBe("数据分析");
    expect(store.adviceFailure).toBeNull();
    expect(store.adviceMessages.map((item) => item.text)).toEqual([
      "先聊兴趣",
      "建议数据分析方向。",
      "接口输出失败的问题",
      "重新生成的回答",
    ]);
  });

  it("sends an edited failed question as a new request without adding the failed text to history", async () => {
    const answer: AdviceChatAnswer = {
      schemaVersion: "1.0",
      reply: "修改后的回答",
      question: null,
      courses: [],
      suggestions: [],
      schoolProgress: null,
      unknowns: [],
      usage: {
        inputTokens: null,
        outputTokens: null,
        toolCalls: 0,
        elapsedMs: 0,
      },
    };
    const adviceChat = vi
      .fn()
      .mockRejectedValueOnce(
        new ApiFailure("模型校验失败", "http", 422, "MODEL_INVALID_OUTPUT"),
      )
      .mockResolvedValueOnce(answer);
    const store = createPlanningStore(fakeClient({ adviceChat }))();
    await store.startSession();
    await store.sendAdviceMessage("原始问题");
    expect(await store.sendAdviceMessage("修改后的问题")).toBe(true);
    expect(adviceChat.mock.calls[0]?.[1]).not.toBe(
      adviceChat.mock.calls[1]?.[1],
    );
    expect(adviceChat.mock.calls[1]?.[0].message).toBe("修改后的问题");
    expect(adviceChat.mock.calls[1]?.[0].history).toEqual([]);
  });

  it("ignores duplicate send clicks while one chat request is pending", async () => {
    const pending = deferred<AdviceChatAnswer>();
    const adviceChat = vi.fn(() => pending.promise);
    const store = createPlanningStore(fakeClient({ adviceChat }))();
    await store.startSession();
    const first = store.sendAdviceMessage("单条问题");
    expect(await store.sendAdviceMessage("单条问题")).toBe(false);
    expect(adviceChat).toHaveBeenCalledTimes(1);
    pending.resolve({
      schemaVersion: "1.0",
      reply: "回答",
      question: null,
      courses: [],
      suggestions: [],
      schoolProgress: null,
      unknowns: [],
      usage: {
        inputTokens: null,
        outputTokens: null,
        toolCalls: 0,
        elapsedMs: 0,
      },
    });
    expect(await first).toBe(true);
  });

  it("does not adopt a course that the subsequently loaded record marks passed or in progress", async () => {
    const answer: AdviceChatAnswer = {
      schemaVersion: "1.0",
      reply: "课程建议",
      question: null,
      courses: [
        {
          courseCode: "CS201",
          name: "数据分析",
          credits: 3,
          category: "专业选修课",
          reason: "方向相关",
          reviewNoteIds: [],
          reviews: [],
          reviewStatus: "NONE",
        },
      ],
      suggestions: [
        {
          suggestionId: "s-select",
          kind: "SELECT_COURSE",
          label: "选入",
          value: "CS201",
        },
      ],
      schoolProgress: null,
      unknowns: [],
      usage: {
        inputTokens: null,
        outputTokens: null,
        toolCalls: 0,
        elapsedMs: 0,
      },
    };
    const store = createPlanningStore(
      fakeClient({ adviceChat: vi.fn(async () => answer) }),
    )();
    await store.startSession();
    await store.sendAdviceMessage("问题");
    store.$patch({
      selectedRecordId: "record-current",
      records: [
        {
          academicRecordId: "record-current",
          revision: 1,
          curriculumSnapshotId: curriculum.snapshotId,
          completedCourses: [
            {
              courseCode: "CS201",
              earnedCredits: 3,
              outcome: "IN_PROGRESS",
              completedTerm: null,
            },
          ],
          transcriptComplete: true,
          sourceKind: "USER_IMPORT",
          createdAt: "2026-10-01T00:00:00Z",
        },
      ],
    });
    expect(store.adoptAdviceSuggestion(answer, "s-select")).toBe(false);
    expect(store.draft.selectedCourseCodes).toEqual([]);
    expect(store.adviceError).toContain("正在修读");
    expect(store.adviceMessages).toHaveLength(2);
  });

  it("clears chat history and adopted choices when the curriculum changes", async () => {
    const answer: AdviceChatAnswer = {
      schemaVersion: "1.0",
      reply: "回答",
      question: null,
      courses: [],
      suggestions: [],
      schoolProgress: null,
      unknowns: [],
      usage: {
        inputTokens: null,
        outputTokens: null,
        toolCalls: 0,
        elapsedMs: 0,
      },
    };
    const store = createPlanningStore(
      fakeClient({
        adviceChat: vi.fn(async () => answer),
      }),
    )();
    await store.startSession();
    await store.sendAdviceMessage("问题");
    store.$patch({
      curricula: [
        ...store.curricula,
        { ...curriculum, snapshotId: "other-curriculum" },
      ],
    });
    store.chooseCurriculum("other-curriculum");
    expect(store.adviceMessages).toEqual([]);
    expect(store.adoptedAdviceSuggestions).toEqual([]);
  });

  it("ignores a late answer from the previous curriculum without clearing the new request state", async () => {
    const first = deferred<AdviceChatAnswer>();
    const second = deferred<AdviceChatAnswer>();
    const adviceChat = vi
      .fn()
      .mockImplementationOnce(() => first.promise)
      .mockImplementationOnce(() => second.promise);
    const store = createPlanningStore(fakeClient({ adviceChat }))();
    await store.startSession();
    const requestA = store.sendAdviceMessage("问题 A");
    store.$patch({
      curricula: [
        ...store.curricula,
        { ...curriculum, snapshotId: "other-curriculum" },
      ],
    });
    store.chooseCurriculum("other-curriculum");
    const requestB = store.sendAdviceMessage("问题 B");

    first.resolve({
      schemaVersion: "1.0",
      reply: "回答 A",
      question: null,
      courses: [],
      suggestions: [],
      schoolProgress: null,
      unknowns: [],
      usage: {
        inputTokens: null,
        outputTokens: null,
        toolCalls: 0,
        elapsedMs: 0,
      },
    });
    await requestA;
    expect(store.adviceBusy).toBe(true);
    expect(store.adviceMessages).toEqual([]);
    expect(store.advicePendingMessage).toBe("问题 B");

    second.resolve({
      schemaVersion: "1.0",
      reply: "回答 B",
      question: null,
      courses: [],
      suggestions: [],
      schoolProgress: null,
      unknowns: [],
      usage: {
        inputTokens: null,
        outputTokens: null,
        toolCalls: 0,
        elapsedMs: 0,
      },
    });
    await requestB;
    expect(store.adviceBusy).toBe(false);
    expect(store.adviceMessages.map((item) => item.text)).toEqual([
      "问题 B",
      "回答 B",
    ]);
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
      listOfferingSnapshots: vi.fn(async () => ({
        items: [],
        unknownMessages: [],
      })),
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

  it("keeps teacher display names out of the draft and clears them with the session", () => {
    const store = createPlanningStore(fakeClient())();
    store.$patch({
      sessionStatus: "ready",
      sessionId: "session-display-name",
    });
    store.setTeacherPickDisplayName("CS101", "T_ZHANG", "张老师");
    store.updateDraft("teacherPicks", [
      { courseCode: "CS101", teacherKey: "T_ZHANG", mode: "MUST" },
    ]);

    expect(store.teacherPickDisplayNames["CS101::T_ZHANG"]).toBe("张老师");
    expect(store.draft.teacherPicks).toEqual([
      { courseCode: "CS101", teacherKey: "T_ZHANG", mode: "MUST" },
    ]);

    store.invalidateSession("会话已过期。");
    expect(store.teacherPickDisplayNames).toEqual({});
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

  describe("submitPlan", () => {
    const answer: PlanningAnswer = {
      taskId: "task-1",
      traceId: "trace-1",
      decision: "UNABLE_TO_VERIFY",
      academicAudit: {
        curriculumSnapshotId: "curriculum-1",
        academicRecordId: "record-1",
        recordRevision: 1,
        transcriptComplete: false,
        requirements: [],
        suggestedCourseCodes: [],
        unknowns: [],
      },
      recommendations: [],
      clarification: null,
      unknowns: [],
      usage: {
        inputTokens: null,
        outputTokens: null,
        toolCalls: 0,
        elapsedMs: 1,
      },
    };

    /** Ready session + verified curriculum + complete answers + a record id. */
    function submittableStore(overrides: Partial<CoursePilotApiClient> = {}) {
      const client = fakeClient({
        fixtureAcademicRecordId: vi.fn(() => "record-1"),
        ...overrides,
      });
      const store = createPlanningStore(client)();
      store.$patch({
        sessionStatus: "ready",
        sessionId: "real-session",
        expiresAt: "2099-01-01T00:00:00Z",
        curricula: [curriculum],
        selectedCurriculumId: curriculum.snapshotId,
        draft: {
          ...store.draft,
          motives: ["GPA"],
          priorityOrder: ["GPA"],
          classPreferencesReviewed: true,
          prioritiesConfirmed: true,
          mustReviewed: true,
          preferReviewed: true,
        },
      });
      return store;
    }

    /** 记录每次提交的请求与幂等键，供断言使用。 */
    function recordingSubmitter() {
      const calls: Array<{ request: PlanningRequest; key: string }> = [];
      const mock = vi.fn(async (request: PlanningRequest, key: string) => {
        calls.push({ request, key });
        return answer;
      });
      return { mock, calls };
    }

    it("retries a supported tradeoff with a new key and preserves hard requirements", async () => {
      const clarify: PlanningAnswer = {
        ...answer,
        decision: "CLARIFY",
        clarification: {
          questionId: "tradeoff:teacher-vs-schedule",
          text: "请确认教师与硬时间的优先顺序。",
          choices: [
            { value: "KEEP_TEACHER", label: "先保留指定教师" },
            { value: "KEEP_SCHEDULE", label: "先保证硬时间" },
          ],
          allowFreeText: false,
          requiredFor: ["teacher_vs_schedule"],
        },
      };
      const calls: Array<{ request: PlanningRequest; key: string }> = [];
      const submitPlanning = vi.fn(
        async (request: PlanningRequest, key: string) => {
          calls.push({ request, key });
          return calls.length === 1 ? clarify : answer;
        },
      );
      const store = submittableStore({ submitPlanning });
      store.$patch({
        draft: {
          ...store.draft,
          teacherPicks: [
            { courseCode: "CS101", teacherKey: "teacher:demo", mode: "MUST" },
          ],
          mustSlots: ["5-1"],
        },
      });

      await store.submitPlan();
      expect(store.planningResult?.decision).toBe("CLARIFY");
      expect(
        store.answerTradeoffClarification(
          "tradeoff:teacher-vs-schedule",
          "KEEP_SCHEDULE",
        ),
      ).toBe(true);
      expect(
        store.answerTradeoffClarification(
          "tradeoff:teacher-vs-schedule",
          "KEEP_SCHEDULE",
        ),
      ).toBe(false);
      await store.submitPlan();

      expect(calls).toHaveLength(2);
      expect(calls[1].key).not.toBe(calls[0].key);
      expect(calls[1].request.intent.priorityOrder).toEqual([
        "GPA",
        "SCHEDULE",
        "SPECIFIC_TEACHER",
      ]);
      expect(calls[1].request.intent.pinnedTeacherCoursePairs).toEqual([
        { courseCode: "CS101", teacherKey: "teacher:demo", mode: "MUST" },
      ]);
      expect(calls[1].request.intent.hardConstraints).toHaveLength(1);
      expect(calls[1].request.intent.hardConstraints[0].kind).toBe(
        "BLOCK_SLOT",
      );
      expect(store.planningResult).toEqual(answer);
    });

    it("submits a general clarification answer in promptText with a new key and keeps hard constraints", async () => {
      const clarify: PlanningAnswer = {
        ...answer,
        decision: "CLARIFY",
        clarification: {
          questionId: "clarify:attendance",
          text: "你更倾向哪种上课安排？",
          choices: [
            { value: "few_days", label: "集中在较少天数" },
            { value: "short_days", label: "每天课时较少" },
          ],
          allowFreeText: true,
          requiredFor: ["schedule"],
        },
      };
      const calls: Array<{ request: PlanningRequest; key: string }> = [];
      const store = submittableStore({
        submitPlanning: vi.fn(async (request: PlanningRequest, key: string) => {
          calls.push({ request, key });
          return calls.length === 1 ? clarify : answer;
        }),
      });
      store.$patch({
        draft: {
          ...store.draft,
          teacherPicks: [
            { courseCode: "CS101", teacherKey: "teacher:demo", mode: "MUST" },
          ],
          mustSlots: ["5-1"],
        },
      });
      await store.submitPlan();
      expect(store.answerClarification("clarify:attendance", "few_days")).toBe(
        true,
      );
      expect(store.planningResult).toBeNull();
      await store.submitPlan();

      expect(calls).toHaveLength(2);
      expect(calls[1].key).not.toBe(calls[0].key);
      expect(calls[1].request.promptText).toContain("作为不可信用户内容处理");
      expect(calls[1].request.promptText).toContain("回答：few_days");
      expect(calls[1].request.intent.pinnedTeacherCoursePairs).toEqual([
        { courseCode: "CS101", teacherKey: "teacher:demo", mode: "MUST" },
      ]);
      expect(calls[1].request.intent.hardConstraints).toEqual(
        calls[0].request.intent.hardConstraints,
      );
      expect(store.planningResult).toEqual(answer);
    });

    it("requires questionnaire updates when clarification targets structured intent fields", async () => {
      const clarify: PlanningAnswer = {
        ...answer,
        decision: "CLARIFY",
        clarification: {
          questionId: "goal:missing",
          text: "请补充你的选课目标。",
          choices: [],
          allowFreeText: true,
          requiredFor: ["motives"],
        },
      };
      const submitPlanning = vi.fn(async () => clarify);
      const store = submittableStore({ submitPlanning });
      await store.submitPlan();

      expect(store.answerClarification("goal:missing", "GPA")).toBe(false);
      expect(store.clarificationError).toContain("返回问卷");
      expect(submitPlanning).toHaveBeenCalledTimes(1);
    });

    it("retains earlier answers when the model asks a second clarification", async () => {
      const clarify = (id: string): PlanningAnswer => ({
        ...answer,
        decision: "CLARIFY",
        clarification: {
          questionId: id,
          text: id,
          choices: [],
          allowFreeText: true,
          requiredFor: [],
        },
      });
      const calls: PlanningRequest[] = [];
      const store = submittableStore({
        submitPlanning: vi.fn(async (request: PlanningRequest) => {
          calls.push(request);
          return calls.length === 1
            ? clarify("first")
            : calls.length === 2
              ? clarify("second")
              : answer;
        }),
      });
      await store.submitPlan();
      expect(store.answerClarification("first", "第一条回答")).toBe(true);
      await store.submitPlan();
      expect(store.answerClarification("second", "第二条回答")).toBe(true);
      await store.submitPlan();
      expect(calls[2].promptText).toContain("第一条回答");
      expect(calls[2].promptText).toContain("第二条回答");
      expect(calls[2].intent.hardConstraints).toEqual(
        calls[0].intent.hardConstraints,
      );
    });

    it("rejects repeated or unknown clarification IDs and refuses overflowing priorities", async () => {
      const clarify: PlanningAnswer = {
        ...answer,
        decision: "CLARIFY",
        clarification: {
          questionId: "tradeoff:teacher-vs-schedule",
          text: "请确认教师与硬时间的优先顺序。",
          choices: [
            { value: "KEEP_TEACHER", label: "先保留指定教师" },
            { value: "KEEP_SCHEDULE", label: "先保证硬时间" },
          ],
          allowFreeText: false,
          requiredFor: ["teacher_vs_schedule"],
        },
      };
      const store = submittableStore({
        submitPlanning: vi.fn(async () => clarify),
      });
      const tenGoals: string[] = [
        "GPA",
        "LOW_WORKLOAD",
        "LOW_ATTENDANCE",
        "GOOD_REVIEWS",
        "INTEREST",
        "CAREER",
        "POSTGRAD",
        "CREDIT_PROGRESS",
        "CUSTOM-1",
        "CUSTOM-2",
      ];
      store.$patch({
        planningResult: clarify,
        draft: {
          ...store.draft,
          motives: ["GPA"],
          priorityOrder: tenGoals as typeof store.draft.priorityOrder,
        },
      });

      expect(
        store.answerTradeoffClarification("other-question", "KEEP_SCHEDULE"),
      ).toBe(false);
      expect(
        store.answerTradeoffClarification(
          "tradeoff:teacher-vs-schedule",
          "KEEP_SCHEDULE",
        ),
      ).toBe(false);
      expect(store.clarificationError).toContain("达到上限");
      expect(store.planningResult?.decision).toBe("CLARIFY");
      expect(store.draft.priorityOrder).toEqual(tenGoals);
    });

    it("fits a missing tradeoff label at the ten-priority contract limit", () => {
      const clarify: PlanningAnswer = {
        ...answer,
        decision: "CLARIFY",
        clarification: {
          questionId: "tradeoff:teacher-vs-schedule",
          text: "请确认教师与硬时间的优先顺序。",
          choices: [
            { value: "KEEP_TEACHER", label: "先保留指定教师" },
            { value: "KEEP_SCHEDULE", label: "先保证硬时间" },
          ],
          allowFreeText: false,
          requiredFor: ["teacher_vs_schedule"],
        },
      };
      const priorities = [
        "GPA",
        "LOW_WORKLOAD",
        "LOW_ATTENDANCE",
        "GOOD_REVIEWS",
        "SPECIFIC_TEACHER",
        "INTEREST",
        "CAREER",
        "POSTGRAD",
        "CREDIT_PROGRESS",
      ];
      const store = submittableStore();
      store.$patch({
        planningResult: clarify,
        draft: {
          ...store.draft,
          motives: priorities as PlanningRequest["intent"]["motives"],
          priorityOrder: priorities as typeof store.draft.priorityOrder,
        },
      });

      expect(
        store.answerTradeoffClarification(
          "tradeoff:teacher-vs-schedule",
          "KEEP_TEACHER",
        ),
      ).toBe(true);
      expect(store.preparePlanningHandoff()).toMatchObject({ ok: true });
      expect(store.planningHandoff?.intent.priorityOrder).toHaveLength(10);
      expect(store.planningHandoff?.intent.priorityOrder).toContain("SCHEDULE");
      expect(store.planningHandoff?.intent.priorityOrder).toContain(
        "SPECIFIC_TEACHER",
      );
      expect(store.planningHandoff?.intent.priorityOrder).toContain(
        "CREDIT_PROGRESS",
      );
    });

    it("submits the built request once and keeps the answer", async () => {
      const { mock, calls } = recordingSubmitter();
      const store = submittableStore({ submitPlanning: mock });

      await store.submitPlan();

      expect(mock).toHaveBeenCalledTimes(1);
      expect(calls[0].request.mode).toBe("REAL");
      expect(calls[0].request.academicRecordId).toBe("record-1");
      expect(calls[0].key).toMatch(/^web-[A-Za-z0-9]+$/);
      expect(store.submitStatus).toBe("ready");
      expect(store.planningResult).toEqual(answer);
    });

    it("ignores a repeated click while a submission is in flight", async () => {
      const pending = deferred<PlanningAnswer>();
      const submitPlanning = vi.fn(() => pending.promise);
      const store = submittableStore({ submitPlanning });

      const inFlight = store.submitPlan();
      await store.submitPlan();
      expect(submitPlanning).toHaveBeenCalledTimes(1);
      expect(store.submitStatus).toBe("submitting");

      pending.resolve(answer);
      await inFlight;
      expect(store.submitStatus).toBe("ready");
    });

    it("submits nothing while required context is missing", async () => {
      const submitPlanning = vi.fn();
      const store = createPlanningStore(fakeClient({ submitPlanning }))();

      await store.submitPlan();

      expect(submitPlanning).not.toHaveBeenCalled();
      expect(store.planningHandoff).toBeNull();
      expect(store.submitStatus).toBe("idle");
    });

    it("reuses the idempotency key on retry and rotates it after a change", async () => {
      const { mock, calls } = recordingSubmitter();
      const store = submittableStore({ submitPlanning: mock });

      await store.submitPlan();
      await store.submitPlan();
      expect(calls[1].key).toBe(calls[0].key);

      store.updateDraft("careerText", "改成数据方向");
      await store.submitPlan();
      expect(calls[2].key).not.toBe(calls[0].key);
    });

    it("discards a late answer once the student changes a condition", async () => {
      const pending = deferred<PlanningAnswer>();
      const submitPlanning = vi.fn(() => pending.promise);
      const store = submittableStore({ submitPlanning });

      const inFlight = store.submitPlan();
      store.updateDraft("careerText", "换一个方向");
      pending.resolve(answer);
      await inFlight;

      expect(store.planningResult).toBeNull();
      expect(store.submitStatus).toBe("idle");
    });

    it("surfaces a failed submission without keeping a stale answer", async () => {
      const submitPlanning = vi
        .fn()
        .mockRejectedValue(
          new ApiFailure(
            "服务暂时不可用，请稍后重试。",
            "http",
            503,
            null,
            true,
          ),
        );
      const store = submittableStore({ submitPlanning });

      await store.submitPlan();

      expect(store.submitStatus).toBe("error");
      expect(store.submitError).toContain("稍后重试");
      expect(store.planningResult).toBeNull();
    });

    it("expires the session when planning answers 401", async () => {
      const submitPlanning = vi
        .fn()
        .mockRejectedValue(
          new ApiFailure("会话不存在或已过期", "http", 401, "UNAUTHORIZED"),
        );
      const store = submittableStore({ submitPlanning });

      await store.submitPlan();

      expect(store.sessionStatus).toBe("expired");
      expect(store.planningResult).toBeNull();
    });
  });

  describe("academic records and audit", () => {
    const savedRecord: AcademicRecord = {
      academicRecordId: "record-1",
      revision: 1,
      curriculumSnapshotId: curriculum.snapshotId,
      completedCourses: [],
      transcriptComplete: false,
      sourceKind: "USER_IMPORT",
      createdAt: "2026-10-01T00:00:00Z",
    };

    const auditResult: AuditResult = {
      curriculumSnapshotId: curriculum.snapshotId,
      academicRecordId: "record-1",
      recordRevision: 1,
      transcriptComplete: false,
      requirements: [
        {
          requirementId: "req:major-core",
          category: "必修",
          courseCodes: ["CS101"],
          requiredCredits: 4,
          earnedCredits: 4,
          gapCredits: 0,
          state: "SATISFIED",
          sourceRefIds: [],
        },
        {
          requirementId: "req:physics",
          category: "必修",
          courseCodes: ["PHYS110"],
          requiredCredits: 3,
          earnedCredits: null,
          gapCredits: null,
          state: "UNKNOWN",
          sourceRefIds: [],
        },
      ],
      suggestedCourseCodes: [],
      unknowns: [],
    };

    const schoolSnapshot: SchoolProgressSnapshot = {
      format: "coursepilot-shu-academic-progress",
      version: 1,
      capturedAt: "2026-10-29T00:00:00Z",
      source: "fictional fixture",
      nodes: [
        {
          nodeId: "school-node-1",
          parentId: null,
          schoolNodeId: "98",
          leaf: true,
          name: "公共基础课",
          requiredCredits: 4,
          earnedCredits: 2,
          remainingCredits: 2,
        },
      ],
      courses: [
        {
          nodeId: "school-node-1",
          courseCode: "CP001",
          name: "虚构课程",
          credits: 2,
          outcome: "UNKNOWN",
          completedYear: null,
          completedTerm: null,
          grade: null,
          makeup: null,
          retake: null,
          suggestedYear: null,
          suggestedTerm: null,
        },
      ],
    };

    const schoolResult: SchoolProgressImportResult = {
      receipt: {
        schoolProgressId: "school-progress-1",
        contentHash: "a".repeat(64),
        importedAt: "2026-10-29T00:00:00Z",
        reused: false,
      },
      snapshot: schoolSnapshot,
      academicRecord: savedRecord,
    };

    function readyStore(overrides: Partial<CoursePilotApiClient> = {}) {
      const client = fakeClient(overrides);
      const store = createPlanningStore(client)();
      store.$patch({
        sessionStatus: "ready",
        sessionId: "real-session",
        expiresAt: "2099-01-01T00:00:00Z",
        curricula: [curriculum],
        selectedCurriculumId: curriculum.snapshotId,
      });
      return { client, store };
    }

    it("accepts USER_IMPORT through simulation HTTP while keeping planning mode SIMULATION", async () => {
      const saveSchoolProgress = vi.fn(async () => schoolResult);
      const { store } = readyStore({ mode: "simulation", saveSchoolProgress });

      const imported = await store.importSchoolProgress(schoolSnapshot);

      expect(imported).toBe(true);
      expect(saveSchoolProgress).toHaveBeenCalledOnce();
      expect(store.schoolProgress?.academicRecord.sourceKind).toBe(
        "USER_IMPORT",
      );
      expect(store.selectedRecord?.sourceKind).toBe("USER_IMPORT");
      expect(store.planningMode).toBe("SIMULATION");
    });

    it("does not send school data through the fixture client", async () => {
      const saveSchoolProgress = vi.fn(async () => schoolResult);
      const { store } = readyStore({ mode: "fixture", saveSchoolProgress });

      const imported = await store.importSchoolProgress(schoolSnapshot);

      expect(imported).toBe(false);
      expect(saveSchoolProgress).not.toHaveBeenCalled();
      expect(store.schoolProgressStatus).toBe("error");
    });

    it("drops a delayed school progress response after the selected curriculum changes", async () => {
      const delayed = deferred<SchoolProgressImportResult | null>();
      const getSchoolProgress = vi
        .fn()
        .mockImplementationOnce(() => delayed.promise)
        .mockResolvedValueOnce(null);
      const { store } = readyStore({ getSchoolProgress });
      const secondCurriculum = {
        ...curriculum,
        snapshotId: "curriculum-other",
      };
      store.$patch({ curricula: [curriculum, secondCurriculum] });

      const oldLoad = store.loadSchoolProgress();
      store.chooseCurriculum(secondCurriculum.snapshotId);
      delayed.resolve(schoolResult);
      await oldLoad;
      await Promise.resolve();

      expect(getSchoolProgress).toHaveBeenCalledTimes(2);
      expect(store.selectedCurriculumId).toBe(secondCurriculum.snapshotId);
      expect(store.schoolProgress).toBeNull();
    });

    /** 一份答完的问卷，用来让 preparePlanningHandoff 真的能产出请求。 */
    function answerEveryQuestion(
      store: ReturnType<typeof readyStore>["store"],
    ) {
      store.$patch({
        draft: {
          ...store.draft,
          motives: ["GPA"],
          priorityOrder: ["GPA"],
          classPreferencesReviewed: true,
          prioritiesConfirmed: true,
          mustReviewed: true,
          preferReviewed: true,
        },
      });
    }

    it("treats an empty record list as ready, not as a failure", async () => {
      const { store } = readyStore();

      await store.loadRecords();

      expect(store.recordsStatus).toBe("ready");
      expect(store.records).toEqual([]);
      expect(store.recordsError).toBe("");
      expect(store.selectedRecord).toBeNull();
    });

    it("selects the first record returned for this session", async () => {
      const { store } = readyStore({
        listSessionRecords: vi.fn(async () => ({ items: [savedRecord] })),
      });

      await store.loadRecords();

      expect(store.selectedRecordId).toBe("record-1");
      expect(store.selectedRecord?.revision).toBe(1);
    });

    it("expires the session when the record list answers 401", async () => {
      const { store } = readyStore({
        listSessionRecords: vi
          .fn()
          .mockRejectedValue(
            new ApiFailure("会话不存在或已过期", "http", 401, "UNAUTHORIZED"),
          ),
      });

      await store.loadRecords();

      expect(store.sessionStatus).toBe("expired");
      expect(store.records).toEqual([]);
    });

    it("saves a new record and makes it the selected one", async () => {
      const courses: CompletedCourse[] = [
        {
          courseCode: "CS101",
          earnedCredits: 4,
          outcome: "PASSED",
          completedTerm: "2024-2025-1",
        },
      ];
      const saveSessionRecord = vi.fn<
        (input: AcademicRecordInput, key: string) => Promise<AcademicRecord>
      >(async () => savedRecord);
      const { store } = readyStore({ saveSessionRecord });

      await expect(store.saveRecord(courses, false)).resolves.toBe(true);

      expect(saveSessionRecord).toHaveBeenCalledTimes(1);
      const [input, key] = saveSessionRecord.mock.calls[0];
      expect(input.sourceKind).toBe("USER_IMPORT");
      expect(input.completedCourses).toEqual(courses);
      expect(key).toMatch(/^web-[A-Za-z0-9]+$/);
      expect(store.selectedRecordId).toBe("record-1");
      expect(store.recordsStatus).toBe("ready");
    });

    it("marks backend simulation records as synthetic and submits simulation mode", async () => {
      const { client, store } = readyStore({ mode: "simulation" });
      await expect(store.saveRecord([], false)).resolves.toBe(true);
      expect(
        vi.mocked(client.saveSessionRecord).mock.calls[0][0].sourceKind,
      ).toBe("SYNTHETIC");
      answerEveryQuestion(store);
      expect(store.preparePlanningHandoff()).toMatchObject({ ok: true });
      expect(store.planningHandoff?.mode).toBe("SIMULATION");
    });

    it("ignores selecting a record that is not in this session", () => {
      const { store } = readyStore();
      store.$patch({ records: [savedRecord], selectedRecordId: "record-1" });

      store.selectRecord("record-other");

      expect(store.selectedRecordId).toBe("record-1");
    });

    it("refuses to audit without a selected record", async () => {
      const auditRequirements = vi.fn();
      const { store } = readyStore({ auditRequirements });

      await store.runAudit();

      expect(auditRequirements).not.toHaveBeenCalled();
      expect(store.auditStatus).toBe("error");
      expect(store.auditError).toContain("请先选择");
    });

    it("keeps the audit result and drops the previous handoff", async () => {
      const { store } = readyStore({
        listSessionRecords: vi.fn(async () => ({ items: [savedRecord] })),
        auditRequirements: vi.fn(async () => auditResult),
      });
      await store.loadRecords();
      answerEveryQuestion(store);
      store.preparePlanningHandoff();
      const before = store.planningHandoff;

      await store.runAudit();

      expect(before).not.toBeNull();
      expect(store.auditStatus).toBe("ready");
      expect(store.audit?.requirements).toHaveLength(2);
      expect(store.planningHandoff).toBeNull();
    });

    it("feeds the real record id into the planning request", async () => {
      const { store } = readyStore({
        listSessionRecords: vi.fn(async () => ({ items: [savedRecord] })),
      });
      answerEveryQuestion(store);
      await store.loadRecords();

      expect(store.preparePlanningHandoff()).toMatchObject({ ok: true });
      expect(store.planningHandoff?.academicRecordId).toBe("record-1");
    });

    it("drops records when the curriculum changes", async () => {
      const { store } = readyStore({
        listSessionRecords: vi.fn(async () => ({ items: [savedRecord] })),
      });
      await store.loadRecords();
      expect(store.records).toHaveLength(1);

      store.chooseCurriculum(curriculum.snapshotId);

      expect(store.records).toEqual([]);
      expect(store.selectedRecordId).toBeNull();
      expect(store.audit).toBeNull();
    });

    describe("record save, selection and stale results", () => {
      const retryCourses: CompletedCourse[] = [
        {
          courseCode: "CS101",
          earnedCredits: 4,
          outcome: "PASSED",
          completedTerm: "2024-2025-1",
        },
      ];
      const otherRecord: AcademicRecord = {
        academicRecordId: "record-2",
        revision: 1,
        curriculumSnapshotId: curriculum.snapshotId,
        completedCourses: [],
        transcriptComplete: false,
        sourceKind: "USER_IMPORT",
        createdAt: "2026-10-02T00:00:00Z",
      };
      const auditResult: AuditResult = {
        curriculumSnapshotId: curriculum.snapshotId,
        academicRecordId: "record-1",
        recordRevision: 1,
        transcriptComplete: false,
        requirements: [],
        suggestedCourseCodes: [],
        unknowns: [],
      };

      it("does not leave the record list stuck on loading when a reload is cancelled", async () => {
        // selectRecord 只作废在途请求、自己不发请求。被中止的 loadRecords 在 catch 里
        // 直接 return，不会再动 recordsStatus，所以作废时必须把它落回安定值。
        const second = deferred<{ items: AcademicRecord[] }>();
        const listSessionRecords = vi
          .fn()
          .mockResolvedValueOnce({ items: [savedRecord] })
          .mockReturnValueOnce(second.promise);
        const { store } = readyStore({ listSessionRecords });

        await store.loadRecords();
        expect(store.recordsStatus).toBe("ready");

        const reload = store.loadRecords();
        expect(store.recordsStatus).toBe("loading");

        store.selectRecord(savedRecord.academicRecordId);
        expect(store.recordsStatus).not.toBe("loading");

        second.resolve({ items: [savedRecord] });
        await reload;
        expect(store.recordsStatus).not.toBe("loading");
      });

      it("ignores a second save while the first one is still in flight", async () => {
        const pending = deferred<AcademicRecord>();
        const saveSessionRecord = vi.fn(() => pending.promise);
        const { store } = readyStore({ saveSessionRecord });

        const first = store.saveRecord(retryCourses, false);
        await expect(store.saveRecord(retryCourses, false)).resolves.toBe(
          false,
        );
        expect(saveSessionRecord).toHaveBeenCalledTimes(1);

        pending.resolve(savedRecord);
        await expect(first).resolves.toBe(true);
        expect(store.records).toHaveLength(1);
      });

      it("reuses the save key when retrying the same courses and rotates it after an edit", async () => {
        const saveSessionRecord = vi
          .fn<
            (input: AcademicRecordInput, key: string) => Promise<AcademicRecord>
          >()
          .mockRejectedValueOnce(
            new ApiFailure("请求超时，请重试。", "timeout"),
          )
          .mockResolvedValue(savedRecord);
        const { store } = readyStore({ saveSessionRecord });

        await expect(store.saveRecord(retryCourses, false)).resolves.toBe(
          false,
        );
        await expect(store.saveRecord(retryCourses, false)).resolves.toBe(true);
        const edited = [
          ...retryCourses,
          {
            courseCode: "MATH101",
            earnedCredits: 3,
            outcome: "PASSED" as const,
            completedTerm: "2024-2025-1",
          },
        ];
        await expect(store.saveRecord(edited, false)).resolves.toBe(true);

        const keys = saveSessionRecord.mock.calls.map(([, key]) => key);
        expect(keys).toHaveLength(3);
        expect(keys[1]).toBe(keys[0]);
        expect(keys[2]).not.toBe(keys[0]);
      });

      it("drops an audit that was in flight when the student switches records", async () => {
        const pending = deferred<AuditResult>();
        const { store } = readyStore({
          listSessionRecords: vi.fn(async () => ({
            items: [savedRecord, otherRecord],
          })),
          auditRequirements: vi.fn(() => pending.promise),
        });
        await store.loadRecords();

        const inFlight = store.runAudit();
        store.selectRecord("record-2");
        pending.resolve(auditResult);
        await inFlight;

        expect(store.selectedRecordId).toBe("record-2");
        expect(store.audit).toBeNull();
        expect(store.auditStatus).toBe("idle");
      });

      it("clears the previous audit when a saved record becomes the selected one", async () => {
        const { store } = readyStore({
          listSessionRecords: vi.fn(async () => ({ items: [savedRecord] })),
          auditRequirements: vi.fn(async () => auditResult),
          saveSessionRecord: vi.fn(async () => otherRecord),
        });
        await store.loadRecords();
        await store.runAudit();
        expect(store.auditStatus).toBe("ready");

        await expect(store.saveRecord(retryCourses, false)).resolves.toBe(true);

        expect(store.selectedRecordId).toBe("record-2");
        expect(store.audit).toBeNull();
        expect(store.auditStatus).toBe("idle");
      });

      it("clears a stale audit when reloading selects a different first record", async () => {
        const { store } = readyStore({
          listSessionRecords: vi
            .fn()
            .mockResolvedValueOnce({ items: [savedRecord] })
            .mockResolvedValueOnce({ items: [otherRecord] }),
          auditRequirements: vi.fn(async () => auditResult),
        });
        await store.loadRecords();
        await store.runAudit();
        expect(store.audit).not.toBeNull();

        await store.loadRecords();

        expect(store.selectedRecordId).toBe("record-2");
        expect(store.audit).toBeNull();
        expect(store.auditStatus).toBe("idle");
      });
    });
  });
});

/** 开课快照：真实模式只认已核验的，演示模式只认 SYNTHETIC（规则在 isCurriculumUsableForMode）。 */
function offering(
  snapshotId: string,
  sourceKind: SnapshotSummary["sourceKind"],
  sourceValidation: SnapshotSummary["sourceValidation"],
): SnapshotSummary {
  return {
    snapshotId,
    kind: "OFFERING",
    state: "PUBLISHED",
    sourceKind,
    termId: "2025-FALL",
    createdAt: "2025-08-15T00:00:00Z",
    sourceValidation,
  };
}

describe("offering snapshot selection", () => {
  let pinia: ReturnType<typeof createPinia>;

  beforeEach(() => {
    pinia = createPinia();
    setActivePinia(pinia);
  });

  afterEach(() => {
    disposePinia(pinia);
  });

  function startWith(
    offerings: SnapshotSummary[],
    overrides: Partial<CoursePilotApiClient> = {},
  ) {
    const client = fakeClient({
      listOfferingSnapshots: vi.fn(async () => ({
        items: offerings,
        unknownMessages: [],
      })),
      ...overrides,
    });
    const store = createPlanningStore(client)();
    return { client, store, start: () => store.startSession() };
  }

  it("auto-selects the only offering usable in real mode and passes it into the request", async () => {
    const only = offering("offer-verified", "BROWSER_SNAPSHOT", "VERIFIED");
    const { store, start } = startWith([only], {
      fixtureAcademicRecordId: vi.fn(() => "record-1"),
    });

    await start();

    expect(store.selectedOfferingSnapshotId).toBe("offer-verified");
    expect(
      store.usableOfferingSnapshots.map((item) => item.snapshotId),
    ).toEqual(["offer-verified"]);
    store.$patch({
      draft: {
        ...store.draft,
        motives: ["GPA"],
        priorityOrder: ["GPA"],
        classPreferencesReviewed: true,
        prioritiesConfirmed: true,
        mustReviewed: true,
        preferReviewed: true,
      },
    });
    const built = store.preparePlanningHandoff();
    expect(built).toMatchObject({ ok: true });
    expect(store.planningHandoff?.offeringSnapshotId).toBe("offer-verified");
  });

  it("does not auto-select an unverified offering in real mode", async () => {
    const { store, start } = startWith([
      offering("offer-unverified", "BROWSER_SNAPSHOT", "UNVERIFIED"),
    ]);

    await start();

    expect(store.selectedOfferingSnapshotId).toBeNull();
    expect(store.usableOfferingSnapshots).toEqual([]);
  });

  it("never offers a synthetic offering in real mode", async () => {
    const { store, start } = startWith([
      offering("offer-demo", "SYNTHETIC", "SYNTHETIC"),
    ]);

    await start();

    expect(store.selectedOfferingSnapshotId).toBeNull();
    expect(store.usableOfferingSnapshots).toEqual([]);
  });

  it("lets the user choose when several offerings are usable", async () => {
    const first = offering("offer-a", "BROWSER_SNAPSHOT", "VERIFIED");
    const second = offering("offer-b", "BROWSER_SNAPSHOT", "VERIFIED");
    const { store, start } = startWith([first, second]);

    await start();

    expect(store.selectedOfferingSnapshotId).toBeNull();
    store.chooseOfferingSnapshot("offer-unknown");
    expect(store.selectedOfferingSnapshotId).toBeNull();
    store.chooseOfferingSnapshot("offer-b");
    expect(store.selectedOfferingSnapshotId).toBe("offer-b");
  });

  it("leaves the selection empty when there are no offerings at all", async () => {
    const { store, start } = startWith([]);

    await start();

    expect(store.sessionStatus).toBe("ready");
    expect(store.selectedOfferingSnapshotId).toBeNull();
    expect(store.offeringSnapshots).toEqual([]);
  });

  it("in simulation mode auto-selects the synthetic offering and rejects verified real ones", async () => {
    const demo = offering("offer-demo", "SYNTHETIC", "SYNTHETIC");
    const real = offering("offer-real", "BROWSER_SNAPSHOT", "VERIFIED");
    const { store, start } = startWith([demo, real], { mode: "fixture" });

    await start();

    expect(store.planningMode).toBe("SIMULATION");
    expect(store.selectedOfferingSnapshotId).toBe("offer-demo");
    expect(
      store.usableOfferingSnapshots.map((item) => item.snapshotId),
    ).toEqual(["offer-demo"]);
    store.chooseOfferingSnapshot("offer-real");
    expect(store.selectedOfferingSnapshotId).toBe("offer-demo");
  });
});
