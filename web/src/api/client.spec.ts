import { describe, expect, it, vi } from "vitest";
import { createApiClient } from "./index";
import { ApiFailure, HttpApiClient } from "./client";
import type {
  AdviceChatAnswer,
  AdviceChatRequest,
  PlanningRequest,
} from "../contracts";

function envelope(status: string, data: unknown, issues: unknown[] = []) {
  return {
    schemaVersion: "1.0",
    requestId: "request-1",
    traceId: null,
    status,
    data,
    provenance: [],
    issues,
  };
}

const session = {
  sessionId: "session-123",
  sessionToken: "token-0123456789abcdef0123456789abcdef",
  expiresAt: "2099-01-01T00:00:00Z",
};
const sessionResponse = () => response(201, envelope("OK", session));

const curriculum = {
  snapshotId: "curriculum-2026",
  kind: "CURRICULUM",
  state: "PUBLISHED",
  sourceKind: "CURRICULUM_FILE",
  termId: null,
  createdAt: "2026-10-01T00:00:00Z",
  sourceValidation: "VERIFIED",
};

function response(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("HTTP API client", () => {
  it("simulation accepts synthetic and unverified curriculum files", async () => {
    const synthetic = {
      ...curriculum,
      snapshotId: "demo",
      sourceKind: "SYNTHETIC",
      sourceValidation: "SYNTHETIC",
    };
    const mismatched = {
      ...synthetic,
      snapshotId: "mismatch",
      sourceValidation: "VERIFIED",
    };
    const unverified = {
      ...curriculum,
      snapshotId: "imported",
      sourceValidation: "UNVERIFIED",
    };
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(sessionResponse())
      .mockResolvedValueOnce(
        response(
          200,
          envelope("OK", {
            items: [curriculum, synthetic, mismatched, unverified],
          }),
        ),
      );
    const client = createApiClient("simulation", {
      baseUrl: "http://127.0.0.1:8000",
      fetcher,
    });
    await client.createSession();
    expect(
      (await client.listCurricula()).items.map((item) => item.snapshotId),
    ).toEqual(["demo", "imported"]);
    expect(client.mode).toBe("simulation");
  });
  it("creates an anonymous session from the documented envelope and keeps bearer out of URLs", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(response(201, envelope("OK", session)));
    const client = new HttpApiClient("http://127.0.0.1:8000", fetcher);

    await expect(client.createSession()).resolves.toMatchObject({
      sessionId: session.sessionId,
    });
    const [url, options] = fetcher.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:8000/api/v1/sessions");
    expect(options.method).toBe("POST");
    expect(options.credentials).toBe("omit");
    expect((options.headers as Headers).get("Authorization")).toBeNull();
    expect((options.headers as Headers).get("X-Request-Id")).toMatch(
      /^web-[A-Za-z0-9]+$/,
    );
  });

  it("uses bearer auth for curriculum reads and preserves only published curriculum snapshots", async () => {
    const syntheticCurriculum = {
      ...curriculum,
      snapshotId: "fixture-curriculum",
      sourceKind: "SYNTHETIC" as const,
      sourceValidation: "SYNTHETIC" as const,
    };
    const contradictorySyntheticCurriculum = {
      ...curriculum,
      snapshotId: "mislabelled-synthetic-curriculum",
      sourceKind: "SYNTHETIC" as const,
      sourceValidation: "VERIFIED" as const,
    };
    const offering = {
      ...curriculum,
      snapshotId: "offering-2026",
      kind: "OFFERING",
    };
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(sessionResponse())
      .mockResolvedValueOnce(
        response(
          200,
          envelope("OK", {
            items: [
              curriculum,
              syntheticCurriculum,
              contradictorySyntheticCurriculum,
              offering,
            ],
          }),
        ),
      );
    const client = new HttpApiClient("http://127.0.0.1:8000", fetcher);

    const created = await client.createSession();
    expect(created).toEqual({
      sessionId: session.sessionId,
      expiresAt: session.expiresAt,
    });
    expect(JSON.stringify(created)).not.toContain(session.sessionToken);
    await expect(client.listCurricula()).resolves.toEqual({
      items: [curriculum],
      unknownMessages: [],
    });
    const [url, options] = fetcher.mock.calls[1] as [string, RequestInit];
    expect(url).toContain("/api/v1/curriculum-snapshots");
    expect((options.headers as Headers).get("Authorization")).toBe(
      `Bearer ${session.sessionToken}`,
    );
  });

  it("reduces UNKNOWN curriculum issues to a safe, student-facing status", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(sessionResponse())
      .mockResolvedValueOnce(
        response(
          200,
          envelope("UNKNOWN", { items: [curriculum] }, [
            {
              code: "SOURCE_UNVERIFIED",
              message: "provider stack details must not reach the student",
              field: null,
              retryable: false,
            },
          ]),
        ),
      );
    const client = new HttpApiClient("http://127.0.0.1:8000", fetcher);
    await client.createSession();

    await expect(client.listCurricula()).resolves.toMatchObject({
      items: [curriculum],
      unknownMessages: ["部分培养方案资料暂不可用，当前只列出可用资料。"],
    });
  });

  it("converts a 401 envelope into a session-expired error without echoing auth data", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(sessionResponse())
      .mockResolvedValueOnce(
        response(
          401,
          envelope("UNAUTHORIZED", null, [
            {
              code: "SESSION_EXPIRED",
              message: "please do not expose token",
              field: null,
              retryable: false,
            },
          ]),
        ),
      );
    const client = new HttpApiClient("http://127.0.0.1:8000", fetcher);

    await client.createSession();
    await expect(client.listCurricula()).rejects.toMatchObject({
      name: "ApiFailure",
      status: 401,
      message: "本次会话已失效，请重新开始。",
    });
  });

  it("retains retryable service error semantics from a valid error envelope", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      response(
        503,
        envelope("ERROR", null, [
          {
            code: "UPSTREAM_DOWN",
            message: "服务暂时不可用",
            field: null,
            retryable: true,
          },
        ]),
      ),
    );
    const client = new HttpApiClient("http://127.0.0.1:8000", fetcher);

    await expect(client.createSession()).rejects.toMatchObject({
      status: 503,
      code: "UPSTREAM_DOWN",
      retryable: true,
      message: "服务暂时不可用，请稍后重试。",
    });
  });

  it("keeps a retryable HTTP status actionable when a gateway returns a non-envelope body", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(new Response("upstream unavailable", { status: 503 }));
    const client = new HttpApiClient("http://127.0.0.1:8000", fetcher);

    await expect(client.createSession()).rejects.toMatchObject({
      status: 503,
      retryable: true,
      message: "服务暂时不可用，请稍后重试。",
    });
  });

  it("rejects malformed successful responses and does not fall back to fixture data", async () => {
    const fetcher = vi.fn().mockResolvedValue(response(201, { data: session }));
    const client = new HttpApiClient("http://127.0.0.1:8000", fetcher);

    await expect(client.createSession()).rejects.toMatchObject({
      kind: "invalid_response",
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("reports transport failure instead of returning demonstration data", async () => {
    const fetcher = vi.fn().mockRejectedValue(new TypeError("socket failed"));
    const client = new HttpApiClient("http://127.0.0.1:8000", fetcher);

    const failure = await client
      .createSession()
      .catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(ApiFailure);
    expect(failure).toMatchObject({ kind: "network", retryable: true });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("distinguishes a timeout from a user cancellation", async () => {
    const fetcher = vi.fn<typeof fetch>(async (input, options) => {
      expect(String(input)).toContain("/api/v1/sessions");
      return new Promise<Response>((_resolve, reject) => {
        options?.signal?.addEventListener("abort", () =>
          reject(new DOMException("Aborted", "AbortError")),
        );
      });
    });
    const client = new HttpApiClient("http://127.0.0.1:8000", fetcher, 5);

    await expect(client.createSession()).rejects.toMatchObject({
      kind: "timeout",
      retryable: true,
    });
  });

  it("does not send a request when the caller already canceled", async () => {
    const fetcher = vi.fn();
    const client = new HttpApiClient("http://127.0.0.1:8000", fetcher);
    const controller = new AbortController();
    controller.abort();

    await expect(client.createSession(controller.signal)).rejects.toMatchObject(
      {
        kind: "aborted",
      },
    );
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("does not let an aborted late session response replace the current bearer token", async () => {
    let resolveLate!: (value: Response) => void;
    const lateResponse = new Promise<Response>((resolve) => {
      resolveLate = resolve;
    });
    const fetcher = vi
      .fn()
      .mockReturnValueOnce(lateResponse)
      .mockResolvedValueOnce(
        response(
          201,
          envelope("OK", {
            ...session,
            sessionId: "session-current",
            sessionToken: "current-token-0123456789abcdef0123456789abcdef",
          }),
        ),
      )
      .mockResolvedValueOnce(response(200, envelope("OK", { items: [] })));
    const client = new HttpApiClient("http://127.0.0.1:8000", fetcher);
    const oldController = new AbortController();
    const staleRequest = client.createSession(oldController.signal);
    oldController.abort();

    await client.createSession();
    resolveLate(response(201, envelope("OK", session)));
    await expect(staleRequest).rejects.toMatchObject({ kind: "aborted" });
    await client.listCurricula();
    const [curriculumUrl, options] = fetcher.mock.calls[2] as [
      string,
      RequestInit,
    ];
    expect(curriculumUrl).toContain("/api/v1/curriculum-snapshots");
    expect((options.headers as Headers).get("Authorization")).toBe(
      "Bearer current-token-0123456789abcdef0123456789abcdef",
    );
  });

  it("selects fixtures only when explicitly configured", async () => {
    const fetcher = vi.fn().mockRejectedValue(new TypeError("offline"));
    const httpClient = createApiClient("http", { fetcher });
    await expect(httpClient.createSession()).rejects.toMatchObject({
      kind: "network",
    });
    expect(fetcher).toHaveBeenCalledTimes(1);

    const fixtureClient = createApiClient("fixture");
    expect(fixtureClient.mode).toBe("fixture");
    await expect(fixtureClient.createSession()).resolves.toMatchObject({
      sessionId: "fixture-session-e1",
    });
  });

  it("uses the site's API proxy by default", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(response(201, envelope("OK", session)));
    const client = createApiClient("http", { fetcher });
    await client.createSession();
    expect(fetcher.mock.calls[0][0]).toBe("/api/v1/sessions");
  });

  it("gives the planning request a timeout longer than the 45s server budget", async () => {
    // C 的 Budget.deadline_ms 是 45000。页面若沿用默认 8 秒，真实规划会被自己掐断，
    // 而且症状看起来像后端太慢。这里断言规划请求用的是更长的超时。
    vi.useFakeTimers();
    try {
      const fetcher = vi
        .fn()
        .mockResolvedValueOnce(response(201, envelope("OK", session)))
        .mockImplementationOnce(() => new Promise(() => {}));
      const client = new HttpApiClient("http://127.0.0.1:8000", fetcher);
      await client.createSession();
      void client.submitPlanning(planningRequest, "key-1").catch(() => {});
      await Promise.resolve();

      const [, planningOptions] = fetcher.mock.calls[1] as [
        string,
        RequestInit,
      ];

      // 默认超时是 8 秒：走到 9 秒还没被掐断，说明规划请求没有沿用默认值。
      await vi.advanceTimersByTimeAsync(9_000);
      expect(planningOptions.signal?.aborted).toBe(false);

      // 服务端预算 45 秒：走到 46 秒仍未被掐断，正常规划才不会被页面自己截断。
      await vi.advanceTimersByTimeAsync(37_000);
      expect(planningOptions.signal?.aborted).toBe(false);

      // 但也不是永不超时。
      await vi.advanceTimersByTimeAsync(10_000);
      expect(planningOptions.signal?.aborted).toBe(true);
    } finally {
      vi.useRealTimers();
    }
  });

  it("treats a business UNKNOWN envelope as success, not as an error", async () => {
    // docs/04：成功响应是「成功或业务 UNKNOWN」。UNKNOWN 是数据缺失不是查询失败，
    // 页面要照常读 data 再按未知展示。
    const fetcher = vi
      .fn()
      .mockResolvedValue(response(201, envelope("UNKNOWN", session)));
    const client = new HttpApiClient("http://127.0.0.1:8000", fetcher);
    await expect(client.createSession()).resolves.toMatchObject({
      sessionId: session.sessionId,
    });
  });

  it("calls fetch with a global this so a browser native fetch is not rejected", async () => {
    // 浏览器的 window.fetch 会校验调用时的 this 必须是 window，否则抛
    // TypeError: Illegal invocation。Node 的 fetch 和 vi.fn() 都不做这个校验，
    // 所以这里用一个会自行检查 this 的假 fetch 来重建浏览器的行为；否则这类
    // 回归在 Node 下永远测不出来。
    const seenThis: unknown[] = [];
    const nativeLike = function (this: unknown) {
      seenThis.push(this);
      if (this !== undefined && this !== globalThis) {
        throw new TypeError(
          "Failed to execute 'fetch' on 'Window': Illegal invocation",
        );
      }
      return Promise.resolve(response(201, envelope("OK", session)));
    } as unknown as typeof fetch;

    const client = new HttpApiClient("http://127.0.0.1:8000", nativeLike);

    await expect(client.createSession()).resolves.toMatchObject({
      sessionId: session.sessionId,
    });
    expect(seenThis).toHaveLength(1);
    expect(seenThis[0]).toBe(globalThis);
  });

  it("defaults to the global fetch rather than an unbound reference", async () => {
    const original = globalThis.fetch;
    const calls: unknown[] = [];
    globalThis.fetch = function (this: unknown) {
      calls.push(this);
      return Promise.resolve(response(201, envelope("OK", session)));
    } as unknown as typeof fetch;
    try {
      const client = new HttpApiClient("http://127.0.0.1:8000");
      await expect(client.createSession()).resolves.toMatchObject({
        sessionId: session.sessionId,
      });
      expect(calls[0]).toBe(globalThis);
    } finally {
      globalThis.fetch = original;
    }
  });
});

const record = {
  academicRecordId: "record-1",
  revision: 1,
  curriculumSnapshotId: "curriculum-2026",
  completedCourses: [],
  transcriptComplete: false,
  sourceKind: "USER_IMPORT",
  createdAt: "2026-10-01T00:00:00Z",
};

const audit = {
  curriculumSnapshotId: "curriculum-2026",
  academicRecordId: "record-1",
  recordRevision: 1,
  transcriptComplete: false,
  requirements: [],
  suggestedCourseCodes: [],
  unknowns: [],
};

const answer = {
  taskId: "task-1",
  traceId: "trace-1",
  decision: "UNABLE_TO_VERIFY",
  academicAudit: audit,
  recommendations: [],
  clarification: null,
  unknowns: [],
  usage: { inputTokens: null, outputTokens: null, toolCalls: 0, elapsedMs: 5 },
};

const planningRequest: PlanningRequest = {
  schemaVersion: "1.0",
  curriculumSnapshotId: "curriculum-2026",
  offeringSnapshotId: null,
  academicRecordId: "record-1",
  mode: "REAL",
  promptText: "",
  intent: {
    motives: ["GPA"],
    priorityOrder: ["GPA"],
    hardConstraints: [],
    softPreferences: [],
    pinnedTeacherCoursePairs: [],
    interestTags: [],
    careerDirectionIds: [],
  },
  previousPlanId: null,
};

async function authedClient(fetcher: ReturnType<typeof vi.fn>) {
  const client = new HttpApiClient("http://127.0.0.1:8000", fetcher);
  await client.createSession();
  return client;
}

describe("HTTP API client · advice chat", () => {
  it("posts the documented request with bearer, request ID, and idempotency headers", async () => {
    const answer: AdviceChatAnswer = {
      schemaVersion: "1.0",
      reply: "回答",
      question: null,
      courses: [],
      suggestions: [],
      schoolProgress: null,
      unknowns: [],
      usage: { inputTokens: 1, outputTokens: 2, toolCalls: 1, elapsedMs: 20 },
    };
    const body: AdviceChatRequest = {
      schemaVersion: "1.0",
      curriculumSnapshotId: "curriculum-2026",
      academicRecordId: null,
      mode: "REAL",
      message: "问题",
      history: [],
      interestText: "",
      selectedCourseCodes: [],
      preferredCourseCodes: [],
    };
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(sessionResponse())
      .mockResolvedValueOnce(response(200, envelope("OK", answer)));
    const client = await authedClient(fetcher);
    await expect(client.adviceChat(body, "idem-advice-1")).resolves.toEqual(
      answer,
    );
    const [url, options] = fetcher.mock.calls[1] as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:8000/api/v1/advice/chat");
    expect(options.method).toBe("POST");
    expect(JSON.parse(String(options.body))).toEqual(body);
    expect((options.headers as Headers).get("Authorization")).toBe(
      `Bearer ${session.sessionToken}`,
    );
    expect((options.headers as Headers).get("Idempotency-Key")).toBe(
      "idem-advice-1",
    );
  });
});

describe("HTTP API client · E2 academic records, audit and planning", () => {
  it("treats an empty session record list as a normal state, not an error", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(sessionResponse())
      .mockResolvedValue(response(200, envelope("OK", { items: [] })));
    const client = await authedClient(fetcher);

    await expect(client.listSessionRecords()).resolves.toEqual({ items: [] });
    const [url, options] = fetcher.mock.calls[1] as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:8000/api/v1/academic-records");
    expect(options.method).toBe("GET");
    expect((options.headers as Headers).get("Authorization")).toBe(
      `Bearer ${session.sessionToken}`,
    );
    expect((options.headers as Headers).get("Idempotency-Key")).toBeNull();
  });

  it("returns session records and rejects ones that break the contract", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(sessionResponse())
      .mockResolvedValue(response(200, envelope("OK", { items: [record] })));
    const client = await authedClient(fetcher);
    await expect(client.listSessionRecords()).resolves.toEqual({
      items: [record],
    });

    const badFetcher = vi
      .fn()
      .mockResolvedValueOnce(sessionResponse())
      .mockResolvedValue(
        response(200, envelope("OK", { items: [{ ...record, revision: 0 }] })),
      );
    const badClient = await authedClient(badFetcher);
    await expect(badClient.listSessionRecords()).rejects.toMatchObject({
      kind: "invalid_response",
    });
  });

  it("saves a record with an Idempotency-Key and returns the server-issued id", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(sessionResponse())
      .mockResolvedValue(response(201, envelope("OK", record)));
    const client = await authedClient(fetcher);

    await expect(
      client.saveSessionRecord(
        {
          schemaVersion: "1.0",
          curriculumSnapshotId: "curriculum-2026",
          completedCourses: [],
          transcriptComplete: false,
          sourceKind: "USER_IMPORT",
        },
        "key-record-1",
      ),
    ).resolves.toMatchObject({ academicRecordId: "record-1" });

    const [, options] = fetcher.mock.calls[1] as [string, RequestInit];
    expect(options.method).toBe("POST");
    expect((options.headers as Headers).get("Idempotency-Key")).toBe(
      "key-record-1",
    );
    expect(JSON.parse(String(options.body))).toMatchObject({
      schemaVersion: "1.0",
      curriculumSnapshotId: "curriculum-2026",
    });
  });

  it("posts the documented AuditRequest shape", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(sessionResponse())
      .mockResolvedValue(response(200, envelope("OK", audit)));
    const client = await authedClient(fetcher);

    await expect(
      client.auditRequirements("curriculum-2026", "record-1"),
    ).resolves.toMatchObject({ academicRecordId: "record-1" });

    const [url, options] = fetcher.mock.calls[1] as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:8000/api/v1/requirements/audit");
    expect(JSON.parse(String(options.body))).toEqual({
      schemaVersion: "1.0",
      curriculumSnapshotId: "curriculum-2026",
      academicRecordId: "record-1",
    });
  });

  it("submits planning with an Idempotency-Key and passes the decision through unchanged", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(sessionResponse())
      .mockResolvedValue(response(200, envelope("OK", answer)));
    const client = await authedClient(fetcher);

    await expect(
      client.submitPlanning(planningRequest, "key-plan-1"),
    ).resolves.toMatchObject({ decision: "UNABLE_TO_VERIFY" });

    const [url, options] = fetcher.mock.calls[1] as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:8000/api/v1/planning");
    expect((options.headers as Headers).get("Idempotency-Key")).toBe(
      "key-plan-1",
    );
    expect(JSON.parse(String(options.body))).toMatchObject({
      academicRecordId: "record-1",
      mode: "REAL",
    });
  });

  it("surfaces a planning conflict as a non-retryable http failure", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(sessionResponse())
      .mockResolvedValue(
        response(
          409,
          envelope("CONFLICT", {}, [
            {
              code: "REQUEST_IN_PROGRESS",
              message: "同一请求仍在执行",
              field: "Idempotency-Key",
              retryable: true,
            },
          ]),
        ),
      );
    const client = await authedClient(fetcher);

    await expect(
      client.submitPlanning(planningRequest, "key-plan-2"),
    ).rejects.toMatchObject({ kind: "http", status: 409 });
  });

  it("refuses to call E2 endpoints before a session exists", async () => {
    const fetcher = vi.fn();
    const client = new HttpApiClient("http://127.0.0.1:8000", fetcher);
    await expect(client.listSessionRecords()).rejects.toMatchObject({
      status: 401,
      code: "UNAUTHORIZED",
    });
    await expect(
      client.submitPlanning(planningRequest, "key-plan-3"),
    ).rejects.toMatchObject({ status: 401 });
    expect(fetcher).not.toHaveBeenCalled();
  });
});

const weeks = Array.from({ length: 16 }, (_, index) => index + 1);

const offering = {
  courseCode: "CS103",
  classId: "CS103-02",
  teacherKey: "teacher-wang-03",
  teacherText: "王芳（测试数据）",
  credits: 3,
  capacity: 60,
  meetingTextRaw: "周二 3-4 节 1-16 周",
  meetings: [{ dayOfWeek: 2, sectionStart: 3, sectionEnd: 4, weeks }],
  parseStatus: "PARSED",
  sourceRefId: "source:offering-cs103-02",
};

const teacherOption = {
  courseCode: "CS103",
  teacherKey: "teacher-wang-03",
  teacherDisplayName: "王芳（测试数据）",
  availability: "UNKNOWN",
  reviewNoteIds: ["review-cs103-wang-01"],
  classIds: ["CS103-02"],
};

const reviewNote = {
  reviewNoteId: "review-cs103-zhang-01",
  courseCode: "CS103",
  teacherKey: "teacher-zhang-02",
  termId: "2024-2025-1",
  sourceKind: "SYNTHETIC",
  publishedAt: "2025-01-10T00:00:00Z",
  sourceUrl: null,
  excerpt: "（测试数据）作业量适中。",
  dimensions: ["WORKLOAD"],
  matchStatus: "COURSE_TEACHER_MATCHED",
  sourceRefId: "source:review-cs103-zhang-01",
};

const runReport = {
  runId: "run-e7",
  harnessVersion: "test-harness-v0",
  parentVersion: null,
  decision: "BASELINE",
  heldOutScore: null,
  averageInputTokens: null,
  averageOutputTokens: null,
  averageToolCalls: null,
  averageLatencyMs: null,
  failureCategories: ["TEST_NO_EVALUATION"],
};

const replaceInput = {
  previousPlanId: "plan-1",
  courseCode: "CS103",
  selectedClassId: "CS103-02",
};

const planConstraint = {
  kind: "BLOCK_DAY",
  courseCode: null,
  teacherKey: null,
  dayOfWeek: 5,
  section: null,
  value: null,
  sourceText: "周五不排课（测试数据）",
};

function planVerification(verdict: "VALID" | "UNKNOWN") {
  return {
    verifierResultId: "verifier-test",
    verdict,
    scope: "SIMULATION",
    curriculumSnapshotId: "curriculum-2026",
    offeringSnapshotId: "offering-2026",
    recordRevision: 1,
    violations: [],
    unknownChecks:
      verdict === "UNKNOWN"
        ? [
            {
              code: "CLASS_NOT_SELECTED",
              message: "CS103 尚未选定班次（测试数据）",
              field: null,
              retryable: false,
            },
          ]
        : [],
    performedChecks: ["PLAN_TIME_OVERLAP"],
    sourceRefIds: [],
  };
}

function replacement(verdict: "VALID" | "UNKNOWN") {
  return {
    previousPlanId: "plan-1",
    planId: "plan-2",
    items: [
      { courseCode: "CS102", teacherKey: "teacher-li-01", classId: "CS102-01" },
      {
        courseCode: "CS103",
        teacherKey: "teacher-wang-03",
        classId: "CS103-02",
      },
    ],
    hardConstraints: [planConstraint],
    verification: planVerification(verdict),
  };
}

describe("HTTP API client · E4 offerings, replacement, teachers, reviews and report", () => {
  it("searches offerings with GET query parameters and passes an OK list through with status OK", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(sessionResponse())
      .mockResolvedValueOnce(
        response(
          200,
          envelope("OK", {
            previousPlanId: "plan-1",
            courseCode: "CS103",
            items: [offering],
          }),
        ),
      );
    const client = await authedClient(fetcher);

    await expect(
      client.searchSessionOfferings("plan-1", "CS103"),
    ).resolves.toEqual({
      previousPlanId: "plan-1",
      courseCode: "CS103",
      items: [offering],
      status: "OK",
    });
    const [url, options] = fetcher.mock.calls[1] as [string, RequestInit];
    expect(url).toBe(
      "http://127.0.0.1:8000/api/v1/session-offerings?previousPlanId=plan-1&courseCode=CS103",
    );
    expect(options.method).toBe("GET");
    expect((options.headers as Headers).get("Authorization")).toBe(
      `Bearer ${session.sessionToken}`,
    );
  });

  it("keeps an UNKNOWN offering search as status UNKNOWN, not as a confirmed empty list", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(sessionResponse())
      .mockResolvedValueOnce(
        response(
          200,
          envelope("UNKNOWN", {
            previousPlanId: "plan-1",
            courseCode: "CS103",
            items: [],
          }),
        ),
      );
    const client = await authedClient(fetcher);

    const result = await client.searchSessionOfferings("plan-1", "CS103");
    expect(result.items).toEqual([]);
    expect(result.status).toBe("UNKNOWN");
  });

  it("posts the replacement with an Idempotency-Key and returns the server verdict unchanged", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(sessionResponse())
      .mockResolvedValueOnce(
        response(200, envelope("OK", replacement("VALID"))),
      );
    const client = await authedClient(fetcher);

    await expect(
      client.replaceSessionPlanItem(replaceInput, "key-replace-1"),
    ).resolves.toEqual(replacement("VALID"));
    const [url, options] = fetcher.mock.calls[1] as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:8000/api/v1/session-plans/replace");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body as string)).toEqual(replaceInput);
    expect((options.headers as Headers).get("Idempotency-Key")).toBe(
      "key-replace-1",
    );
    expect((options.headers as Headers).get("Authorization")).toBe(
      `Bearer ${session.sessionToken}`,
    );
  });

  it("accepts a replacement whose envelope is UNKNOWN and keeps the UNKNOWN verdict visible", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(sessionResponse())
      .mockResolvedValueOnce(
        response(200, envelope("UNKNOWN", replacement("UNKNOWN"))),
      );
    const client = await authedClient(fetcher);

    const result = await client.replaceSessionPlanItem(
      replaceInput,
      "key-replace-2",
    );
    expect(result.verification.verdict).toBe("UNKNOWN");
    expect(result.verification.unknownChecks).toHaveLength(1);
  });

  it("accepts an explicit empty-plan result from deterministic course removal", async () => {
    const edit = {
      previousPlanId: "plan-before",
      planId: "plan-empty",
      items: [],
      hardConstraints: [],
      verification: null,
      empty: true,
    };
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(sessionResponse())
      .mockResolvedValueOnce(response(200, envelope("OK", edit)));
    const client = await authedClient(fetcher);
    await expect(
      client.removeSessionPlanCourse(
        { previousPlanId: edit.previousPlanId, courseCode: "CS101" },
        "key-remove-1",
      ),
    ).resolves.toEqual(edit);
    const [url, options] = fetcher.mock.calls[1] as [string, RequestInit];
    expect(url).toBe(
      "http://127.0.0.1:8000/api/v1/session-plans/remove-course",
    );
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body as string)).toEqual({
      previousPlanId: "plan-before",
      courseCode: "CS101",
    });
  });

  it("lists teacher options by snapshot and leaves courseCode out of the query when it is null", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(sessionResponse())
      .mockResolvedValueOnce(
        response(200, envelope("OK", { items: [teacherOption] })),
      );
    const client = await authedClient(fetcher);

    const result = await client.listTeacherCourseOptions(
      "curriculum-2026",
      null,
    );
    expect(result.items).toEqual([teacherOption]);
    expect(result.status).toBe("OK");
    const [url, options] = fetcher.mock.calls[1] as [string, RequestInit];
    expect(url).toBe(
      "http://127.0.0.1:8000/api/v1/teacher-course-options?curriculumSnapshotId=curriculum-2026",
    );
    expect(url).not.toContain("null");
    expect(options.method).toBe("GET");
  });

  it("lists curriculum courses with a cursor for the next page", async () => {
    const course = {
      courseCode: "CS103",
      name: "数据结构",
      credits: 3,
      category: "专业基础",
      sourceRefIds: ["source:curriculum-cs103"],
    };
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(sessionResponse())
      .mockResolvedValueOnce(
        response(200, envelope("OK", { items: [course], nextCursor: "next" })),
      );
    const client = await authedClient(fetcher);

    await expect(client.listCourses("curriculum-2026")).resolves.toEqual({
      items: [course],
      nextCursor: "next",
    });
    const [url, options] = fetcher.mock.calls[1] as [string, RequestInit];
    expect(url).toBe(
      "http://127.0.0.1:8000/api/v1/courses?curriculumSnapshotId=curriculum-2026&limit=100",
    );
    expect(options.method).toBe("GET");
  });

  it("sends the course search query and cursor, and omits an empty query", async () => {
    const course = {
      courseCode: "08305009",
      name: "数据结构",
      credits: 3,
      category: "学科基础课",
      sourceRefIds: ["source:curriculum-08305009"],
    };
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(sessionResponse())
      .mockResolvedValueOnce(
        response(200, envelope("OK", { items: [course], nextCursor: null })),
      )
      .mockResolvedValueOnce(
        response(200, envelope("OK", { items: [], nextCursor: null })),
      );
    const client = await authedClient(fetcher);

    await client.listCourses(
      "curriculum-2026",
      "page-2",
      undefined,
      " 数据结构 ",
    );
    const [searchUrl] = fetcher.mock.calls[1] as [string, RequestInit];
    expect(searchUrl).toContain("query=%E6%95%B0%E6%8D%AE%E7%BB%93%E6%9E%84");
    expect(searchUrl).toContain("cursor=page-2");
    expect(searchUrl).not.toContain("+");

    await client.listCourses("curriculum-2026", null, undefined, "   ");
    const [plainUrl] = fetcher.mock.calls[2] as [string, RequestInit];
    expect(plainUrl).not.toContain("query");
    expect(plainUrl).not.toContain("null");
  });

  it("keeps an UNKNOWN teacher list as status UNKNOWN, not as a confirmed empty list", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(sessionResponse())
      .mockResolvedValueOnce(response(200, envelope("UNKNOWN", { items: [] })));
    const client = await authedClient(fetcher);

    const result = await client.listTeacherCourseOptions(
      "curriculum-2026",
      "CS103",
    );
    expect(result.items).toEqual([]);
    expect(result.status).toBe("UNKNOWN");
    const [url] = fetcher.mock.calls[1] as [string, RequestInit];
    expect(url).toContain("courseCode=CS103");
  });

  it("searches reviews by course and leaves teacherKey out of the query when it is null", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(sessionResponse())
      .mockResolvedValueOnce(
        response(200, envelope("OK", { items: [reviewNote] })),
      );
    const client = await authedClient(fetcher);

    await expect(client.searchReviews("CS103", null)).resolves.toEqual({
      items: [reviewNote],
      status: "OK",
    });
    const [url, options] = fetcher.mock.calls[1] as [string, RequestInit];
    expect(url).toBe(
      "http://127.0.0.1:8000/api/v1/reviews/search?courseCode=CS103",
    );
    expect(options.method).toBe("GET");
  });

  it("loads all review pages before returning results", async () => {
    const second = { ...reviewNote, reviewNoteId: "review-second" };
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(sessionResponse())
      .mockResolvedValueOnce(
        response(200, envelope("OK", { items: [reviewNote], nextCursor: "5" })),
      )
      .mockResolvedValueOnce(
        response(200, envelope("OK", { items: [second], nextCursor: null })),
      );
    const client = await authedClient(fetcher);
    const result = await client.searchReviews("CS103", null);
    expect(result.items.map((note) => note.reviewNoteId)).toEqual([
      reviewNote.reviewNoteId,
      "review-second",
    ]);
    expect((fetcher.mock.calls[2] as [string, RequestInit])[0]).toContain(
      "cursor=5",
    );
  });

  it("keeps an UNKNOWN review search as status UNKNOWN, not as a failure or a confirmed empty list", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(sessionResponse())
      .mockResolvedValueOnce(response(200, envelope("UNKNOWN", { items: [] })));
    const client = await authedClient(fetcher);

    await expect(
      client.searchReviews("CS103", "teacher-wang-03"),
    ).resolves.toEqual({ items: [], status: "UNKNOWN" });
  });

  it("requests a run report with the run id encoded in the path", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(sessionResponse())
      .mockResolvedValueOnce(
        response(200, envelope("OK", { ...runReport, runId: "run/e7" })),
      );
    const client = await authedClient(fetcher);

    await expect(client.getRunReport("run/e7")).resolves.toMatchObject({
      runId: "run/e7",
    });
    const [url, options] = fetcher.mock.calls[1] as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:8000/api/v1/reports/runs/run%2Fe7");
    expect(options.method).toBe("GET");
  });

  it("does not turn an UNKNOWN run report into a failure", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(sessionResponse())
      .mockResolvedValueOnce(response(200, envelope("UNKNOWN", runReport)));
    const client = await authedClient(fetcher);

    await expect(client.getRunReport("run-e7")).resolves.toEqual(runReport);
  });

  it("explains a 403 from the report endpoint as a permission problem", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(sessionResponse())
      .mockResolvedValueOnce(
        response(
          403,
          envelope("FORBIDDEN", null, [
            {
              code: "ADMIN_KEY_REQUIRED",
              message: "report requires an admin key",
              field: null,
              retryable: false,
            },
          ]),
        ),
      );
    const client = await authedClient(fetcher);

    await expect(client.getRunReport("run-e7")).rejects.toMatchObject({
      status: 403,
      code: "ADMIN_KEY_REQUIRED",
      message: "当前会话没有查看这些资料的权限。",
    });
  });
});

describe("HTTP API client offering snapshots", () => {
  it("reads /api/v1/offering-snapshots with bearer auth and keeps only published offerings", async () => {
    const publishedOffering = {
      ...curriculum,
      snapshotId: "offer-2025-fall",
      kind: "OFFERING",
      termId: "2025-FALL",
      sourceKind: "BROWSER_SNAPSHOT",
      sourceValidation: "UNVERIFIED",
    };
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(sessionResponse())
      .mockResolvedValueOnce(
        response(
          200,
          envelope("OK", {
            items: [publishedOffering, curriculum],
          }),
        ),
      );
    const client = new HttpApiClient("http://127.0.0.1:8000", fetcher);
    await client.createSession();

    const result = await client.listOfferingSnapshots();

    expect(result.items.map((item) => item.snapshotId)).toEqual([
      "offer-2025-fall",
    ]);
    const [url, options] = fetcher.mock.calls[1] as [string, RequestInit];
    expect(url).toContain("/api/v1/offering-snapshots");
    expect(url).not.toContain("curriculum-snapshots");
    expect((options.headers as Headers).get("Authorization")).toBe(
      `Bearer ${session.sessionToken}`,
    );
  });
});

describe("HTTP API client · 失败说明", () => {
  const planningRequest: PlanningRequest = {
    schemaVersion: "1.0",
    curriculumSnapshotId: "curriculum-2026",
    offeringSnapshotId: null,
    academicRecordId: "record-1",
    motives: ["EXPLORE"],
    constraints: [],
    selectedCourseCodes: [],
    priorityOrder: [],
  } as unknown as PlanningRequest;

  async function failWith(code: string, retryable = false) {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(sessionResponse())
      .mockResolvedValueOnce(
        response(
          422,
          envelope("ERROR", {}, [
            { code, message: "服务端的原文", field: null, retryable },
          ]),
        ),
      );
    const client = new HttpApiClient(
      "http://127.0.0.1:8000",
      fetcher as unknown as typeof fetch,
    );
    await client.createSession();
    return client
      .submitPlanning(planningRequest, "idem-explained-1")
      .catch((error) => error);
  }

  it("输出被截断时不说「请稍后重试」，因为重试一定还是一样", async () => {
    // 实测：真实规划两次都因 finish_reason=length 失败，页面却只说
    // 「服务没有完成请求，请稍后重试」，学生只会一直点重试。
    const error = await failWith("MODEL_OUTPUT_TRUNCATED");
    expect(error).toBeInstanceOf(ApiFailure);
    expect(error.message).toContain("输出预算截断");
    expect(error.message).toContain("重试不会有帮助");
    expect(error.message).not.toContain("请稍后重试");
  });

  it("没有专门说明的失败仍然走原来的兜底文案", async () => {
    const error = await failWith("SOMETHING_ELSE");
    expect(error.message).toBe("服务没有完成请求，请稍后重试。");
  });
});
