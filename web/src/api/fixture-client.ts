import type {
  CoursePilotApiClient,
  CurriculumResult,
  SessionView,
} from "./client";

const DEMO_SESSION: SessionView = {
  sessionId: "fixture-session-e1",
  expiresAt: "2099-01-01T00:00:00Z",
};
const DEMO_SESSION_TOKEN = "fixture-token-0123456789abcdef0123456789abcdef";

const DEMO_CURRICULA: CurriculumResult = {
  items: [
    {
      snapshotId: "fixture-curriculum-computer-science",
      kind: "CURRICULUM",
      state: "PUBLISHED",
      sourceKind: "SYNTHETIC",
      termId: null,
      createdAt: "2026-10-01T00:00:00Z",
      sourceValidation: "SYNTHETIC",
    },
  ],
  unknownMessages: [],
};

export class FixtureApiClient implements CoursePilotApiClient {
  readonly mode = "fixture" as const;
  private sessionToken: string | null = null;

  clearSession(): void {
    this.sessionToken = null;
  }

  async createSession(signal?: AbortSignal): Promise<SessionView> {
    this.sessionToken = null;
    await new Promise<void>((resolve, reject) => {
      const timeout = setTimeout(resolve, 60);
      signal?.addEventListener(
        "abort",
        () => {
          clearTimeout(timeout);
          reject(new DOMException("Aborted", "AbortError"));
        },
        { once: true },
      );
    });
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    this.sessionToken = DEMO_SESSION_TOKEN;
    return { ...DEMO_SESSION };
  }

  async listCurricula(signal?: AbortSignal): Promise<CurriculumResult> {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    if (!this.sessionToken)
      throw new Error("Fixture session has not been created");
    return { items: [...DEMO_CURRICULA.items], unknownMessages: [] };
  }

  fixtureAcademicRecordId(): string {
    return "fixture-academic-record-e1";
  }
}
