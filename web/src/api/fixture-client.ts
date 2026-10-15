import type {
  AcademicRecord,
  AcademicRecordInput,
  AcademicRecordList,
  AuditResult,
  PlanningAnswer,
  PlanningRequest,
} from "../contracts";
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
const DEMO_RECORD_ID = "fixture-academic-record-e1";
const DEMO_CURRICULUM_ID = "fixture-curriculum-computer-science";

const DEMO_CURRICULA: CurriculumResult = {
  items: [
    {
      snapshotId: DEMO_CURRICULUM_ID,
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

/** 虚构学业记录。三态刻意都给一份，用来演示「已满足 / 未满足 / 无法确认」必须分开。 */
const DEMO_RECORD: AcademicRecord = {
  academicRecordId: DEMO_RECORD_ID,
  revision: 1,
  curriculumSnapshotId: DEMO_CURRICULUM_ID,
  completedCourses: [
    {
      courseCode: "CS101",
      earnedCredits: 4,
      outcome: "PASSED",
      completedTerm: "2024-2025-1",
    },
    {
      courseCode: "MATH201",
      earnedCredits: null,
      outcome: "IN_PROGRESS",
      completedTerm: null,
    },
    {
      courseCode: "PHYS110",
      earnedCredits: null,
      outcome: "UNKNOWN",
      completedTerm: null,
    },
  ],
  transcriptComplete: false,
  sourceKind: "SYNTHETIC",
  createdAt: "2026-10-01T00:00:00Z",
};

const DEMO_AUDIT: AuditResult = {
  curriculumSnapshotId: DEMO_CURRICULUM_ID,
  academicRecordId: DEMO_RECORD_ID,
  recordRevision: DEMO_RECORD.revision,
  transcriptComplete: DEMO_RECORD.transcriptComplete,
  requirements: [
    {
      requirementId: "req:major-core",
      courseCodes: ["CS101"],
      requiredCredits: 4,
      earnedCredits: 4,
      gapCredits: 0,
      state: "SATISFIED",
      sourceRefIds: ["source:fixture"],
    },
    {
      requirementId: "req:math-core",
      courseCodes: ["MATH201"],
      requiredCredits: 3,
      earnedCredits: 0,
      gapCredits: 3,
      state: "UNSATISFIED",
      sourceRefIds: ["source:fixture"],
    },
    {
      requirementId: "req:physics",
      courseCodes: ["PHYS110"],
      requiredCredits: 3,
      earnedCredits: null,
      gapCredits: null,
      state: "UNKNOWN",
      sourceRefIds: ["source:fixture"],
    },
  ],
  suggestedCourseCodes: ["MATH201"],
  unknowns: [
    {
      code: "FIXTURE_DATA",
      message: "当前是演示模式，核对结果来自虚构样例，不是真实培养规则计算。",
      field: null,
      retryable: false,
    },
  ],
};

/**
 * 演示模式不生成课程推荐：没有核验器就不该有候选。
 * 结果页的候选渲染由单测用替身客户端覆盖，不由学生可见的演示模式承担。
 */
const DEMO_ANSWER: PlanningAnswer = {
  taskId: "fixture-task-e2",
  traceId: "fixture-trace-e2",
  decision: "UNABLE_TO_VERIFY",
  academicAudit: DEMO_AUDIT,
  recommendations: [],
  clarification: null,
  unknowns: [
    {
      code: "FIXTURE_DATA",
      message: "演示模式没有核验器，不生成课程候选；请开启真实服务再试。",
      field: null,
      retryable: false,
    },
  ],
  usage: { inputTokens: null, outputTokens: null, toolCalls: 0, elapsedMs: 0 },
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

  async listSessionRecords(signal?: AbortSignal): Promise<AcademicRecordList> {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    if (!this.sessionToken)
      throw new Error("Fixture session has not been created");
    return { items: [structuredClone(DEMO_RECORD)] };
  }

  async saveSessionRecord(
    input: AcademicRecordInput,
    _idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<AcademicRecord> {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    if (!this.sessionToken)
      throw new Error("Fixture session has not been created");
    return {
      ...structuredClone(DEMO_RECORD),
      revision: DEMO_RECORD.revision + 1,
      curriculumSnapshotId: input.curriculumSnapshotId,
      completedCourses: input.completedCourses,
      transcriptComplete: input.transcriptComplete,
      sourceKind: input.sourceKind,
    };
  }

  async auditRequirements(
    curriculumSnapshotId: string,
    academicRecordId: string,
    signal?: AbortSignal,
  ): Promise<AuditResult> {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    if (!this.sessionToken)
      throw new Error("Fixture session has not been created");
    return {
      ...structuredClone(DEMO_AUDIT),
      curriculumSnapshotId,
      academicRecordId,
    };
  }

  async submitPlanning(
    _request: PlanningRequest,
    _idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<PlanningAnswer> {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    if (!this.sessionToken)
      throw new Error("Fixture session has not been created");
    return structuredClone(DEMO_ANSWER);
  }

  fixtureAcademicRecordId(): string {
    return DEMO_RECORD_ID;
  }
}
