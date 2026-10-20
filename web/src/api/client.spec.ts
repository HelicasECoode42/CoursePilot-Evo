import { describe, expect, it, vi } from "vitest";
import { createApiClient } from "./index";
import { ApiFailure, HttpApiClient } from "./client";
import type { PlanningRequest } from "../contracts";

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
      unknownMessages: ["演示培养方案不会用于真实服务模式。"],
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
