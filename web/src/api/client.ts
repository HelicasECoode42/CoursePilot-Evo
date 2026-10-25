import Ajv2020 from "ajv/dist/2020";
import addFormats from "ajv-formats";
import domainSchema from "../../../contracts/schemas/domain.schema.json";
import { SCHEMA_VERSION } from "../contracts";
import type {
  AcademicRecord,
  AcademicRecordInput,
  AcademicRecordList,
  AuditResult,
  Envelope,
  PlanningAnswer,
  PlanningRequest,
  ReviewNote,
  RunReport,
  SessionOfferingList,
  SessionPlanReplaceInput,
  SessionPlanReplacement,
  SessionResult,
  SnapshotSummary,
  TeacherCourseOption,
} from "../contracts";

export type ApiFailureKind =
  | "network"
  | "timeout"
  | "http"
  | "invalid_response"
  | "aborted";

export class ApiFailure extends Error {
  constructor(
    message: string,
    readonly kind: ApiFailureKind,
    readonly status: number | null = null,
    readonly code: string | null = null,
    readonly retryable = false,
  ) {
    super(message);
    this.name = "ApiFailure";
  }
}

export interface SessionView {
  sessionId: string;
  expiresAt: string;
}

export interface CurriculumResult {
  items: SnapshotSummary[];
  unknownMessages: string[];
}

/**
 * envelope 的业务状态，只有 OK 和 UNKNOWN（docs/04）。UNKNOWN 表示快照缺失或非当前，
 * 是无法确认；这时列表为空也不能说成「确定没有」。
 */
export type BusinessStatus = "OK" | "UNKNOWN";

/**
 * 带业务状态的列表结果。status 必填：空 items 只有在 OK 时才是确定的「没有」，
 * UNKNOWN 时是「无法确认」。fixture 的空数组是确定结果，所以显式给 OK。
 */
export type SessionOfferingSearch = SessionOfferingList & {
  status: BusinessStatus;
};
export type TeacherCourseOptionSearch = {
  items: TeacherCourseOption[];
  status: BusinessStatus;
};
export type ReviewNoteSearch = {
  items: ReviewNote[];
  status: BusinessStatus;
};

export interface CoursePilotApiClient {
  readonly mode: "http" | "fixture";
  createSession(signal?: AbortSignal): Promise<SessionView>;
  listCurricula(signal?: AbortSignal): Promise<CurriculumResult>;
  /** E2 / E-F1：列出本会话已有的学业记录。items 为空数组是正常业务状态。 */
  listSessionRecords(signal?: AbortSignal): Promise<AcademicRecordList>;
  /** E2 / E-F1：缺记录时才补录。academicRecordId 由服务端生成并返回。 */
  saveSessionRecord(
    input: AcademicRecordInput,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<AcademicRecord>;
  /** E2 / E-F1：学业核对。未知项由服务端在 unknowns 里说明。 */
  auditRequirements(
    curriculumSnapshotId: string,
    academicRecordId: string,
    signal?: AbortSignal,
  ): Promise<AuditResult>;
  /** E2 / E-F4：提交规划请求，返回 CLARIFY / RECOMMENDATIONS / UNABLE_TO_VERIFY。 */
  submitPlanning(
    request: PlanningRequest,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<PlanningAnswer>;
  /**
   * E4：本会话方案中某门课可替换的开课班次。items 为空是正常状态，候选不构成核验结论。
   * status 为 UNKNOWN 时班次资料无法确认，空数组不代表这门课没有班次。
   */
  searchSessionOfferings(
    previousPlanId: string,
    courseCode: string,
    signal?: AbortSignal,
  ): Promise<SessionOfferingSearch>;
  /**
   * E4：把方案里的一门课换成学生选中的班次，并由服务端对整份新方案重新核验。
   * 请求必须带 Idempotency-Key；判决原样返回，不能被页面改写。
   */
  replaceSessionPlanItem(
    body: SessionPlanReplaceInput,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<SessionPlanReplacement>;
  /**
   * E4：查询教师与课程的对应。契约要求 curriculumSnapshotId；courseCode 传 null 表示
   * 不按课程过滤。只返回第一页（契约默认 limit），nextCursor 暂不翻页。
   * status 为 UNKNOWN 时教师资料无法确认，空数组不代表没有可比较的教师。
   */
  listTeacherCourseOptions(
    curriculumSnapshotId: string,
    courseCode: string | null,
    signal?: AbortSignal,
  ): Promise<TeacherCourseOptionSearch>;
  /**
   * E4：检索课程（可选教师）的评价证据。teacherKey 传 null 表示不按教师过滤。
   * status 为 UNKNOWN 时评价资料无法确认，空数组不代表没有找到评价。
   */
  searchReviews(
    courseCode: string,
    teacherKey: string | null,
    signal?: AbortSignal,
  ): Promise<ReviewNoteSearch>;
  /** E4：受限的老师运行报告。服务端还要求管理密钥，浏览器端拿不到时会得到 403，页面需要照实说明。 */
  getRunReport(runId: string, signal?: AbortSignal): Promise<RunReport>;
  clearSession(): void;
  fixtureAcademicRecordId(): string | null;
}

const ajv = new Ajv2020({ allErrors: true, strict: false });
addFormats(ajv);
ajv.addSchema(domainSchema, "coursepilot-domain-v1");
const validateEnvelope = ajv.getSchema("coursepilot-domain-v1#/$defs/Envelope");
const validateSession = ajv.getSchema(
  "coursepilot-domain-v1#/$defs/SessionResult",
);
const validateSnapshot = ajv.getSchema(
  "coursepilot-domain-v1#/$defs/SnapshotSummary",
);
const validateAcademicRecord = ajv.getSchema(
  "coursepilot-domain-v1#/$defs/AcademicRecord",
);
const validateAuditResult = ajv.getSchema(
  "coursepilot-domain-v1#/$defs/AuditResult",
);
const validatePlanningAnswer = ajv.getSchema(
  "coursepilot-domain-v1#/$defs/PlanningAnswer",
);
const validateCourseOffering = ajv.getSchema(
  "coursepilot-domain-v1#/$defs/CourseOffering",
);
const validatePlanItem = ajv.getSchema("coursepilot-domain-v1#/$defs/PlanItem");
const validateConstraint = ajv.getSchema(
  "coursepilot-domain-v1#/$defs/Constraint",
);
const validatePlanValidation = ajv.getSchema(
  "coursepilot-domain-v1#/$defs/PlanValidation",
);
const validateTeacherCourseOption = ajv.getSchema(
  "coursepilot-domain-v1#/$defs/TeacherCourseOption",
);
const validateReviewNote = ajv.getSchema(
  "coursepilot-domain-v1#/$defs/ReviewNote",
);
const validateRunReport = ajv.getSchema(
  "coursepilot-domain-v1#/$defs/RunReport",
);

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * 拼查询串时跳过 null 和 undefined，让可选参数真的不出现在 URL 里，
 * 而不是变成字面量 "null"。
 */
function withQuery(
  path: string,
  params: Record<string, string | null | undefined>,
): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined) search.set(key, value);
  }
  const query = search.toString();
  return query ? `${path}?${query}` : path;
}

/** 数组中每一项都要过对应的 Ajv 校验；空数组直接通过，空是合法的业务状态。 */
function everyValid(
  items: unknown[],
  validate: ((value: unknown) => boolean) | undefined,
): boolean {
  return items.every((item) => Boolean(validate?.(item)));
}

function parseEnvelope(value: unknown): Envelope<unknown> {
  if (!validateEnvelope?.(value)) {
    throw new ApiFailure(
      "服务返回的数据格式不完整，请稍后重试。",
      "invalid_response",
    );
  }
  return value as Envelope<unknown>;
}

function errorForResponse(
  status: number,
  envelope: Envelope<unknown> | null,
): ApiFailure {
  const issue = envelope?.issues[0];
  if (status === 401) {
    return new ApiFailure(
      "本次会话已失效，请重新开始。",
      "http",
      status,
      issue?.code ?? "UNAUTHORIZED",
    );
  }
  if (status === 403) {
    return new ApiFailure(
      "当前会话没有查看这些资料的权限。",
      "http",
      status,
      issue?.code ?? "FORBIDDEN",
    );
  }
  if (status === 404) {
    return new ApiFailure(
      "需要的资料暂不可用，请返回后重试。",
      "http",
      status,
      issue?.code ?? "NOT_FOUND",
    );
  }
  const retryable =
    issue?.retryable === true ||
    status === 408 ||
    status === 429 ||
    status === 503 ||
    status === 504;
  const fallback = retryable
    ? "服务暂时不可用，请稍后重试。"
    : "服务没有完成请求，请稍后重试。";
  return new ApiFailure(
    fallback,
    "http",
    status,
    issue?.code ?? null,
    retryable,
  );
}

/**
 * 契约（docs/04）规定成功响应是「成功或业务 UNKNOWN」。UNKNOWN 表示数据缺失，
 * 不是查询失败，页面要照常读 data 再按未知展示，不能当成错误抛出去。
 */
function isSuccessEnvelope(envelope: Envelope<unknown>): boolean {
  return envelope.status === "OK" || envelope.status === "UNKNOWN";
}

/** 只在 isSuccessEnvelope 通过之后调用，所以 status 只可能是 OK 或 UNKNOWN。 */
function businessStatus(envelope: Envelope<unknown>): BusinessStatus {
  return envelope.status === "UNKNOWN" ? "UNKNOWN" : "OK";
}

/**
 * 规划请求的超时。C 的运行预算是 45 秒（agent-runtime 的 Budget.deadline_ms），
 * 页面若沿用默认的 8 秒，接上真实服务后会把正常规划自己掐断，而且症状看起来
 * 像后端太慢。留出余量取 50 秒；查询类请求仍用默认超时。
 */
const PLANNING_TIMEOUT_MS = 50_000;

export class HttpApiClient implements CoursePilotApiClient {
  readonly mode = "http" as const;
  private readonly baseUrl: string;
  private readonly fetcher: typeof fetch;
  private sessionToken: string | null = null;

  constructor(
    baseUrl: string,
    fetcher: typeof fetch = globalThis.fetch,
    private readonly timeoutMs = 8_000,
  ) {
    // 浏览器的 window.fetch 是原生方法，调用时会校验 this 必须是 window。
    // 存成实例字段后用 this.fetcher(...) 调用，this 变成本实例，浏览器直接抛
    // TypeError: Illegal invocation，请求根本发不出去。Node 与 mock 都不做这个
    // 校验，所以单测全绿而真实浏览器全部失败。构造时绑定一次即可。
    this.fetcher = fetcher.bind(globalThis);
    this.baseUrl = baseUrl.replace(/\/+$/, "");
  }

  fixtureAcademicRecordId(): null {
    return null;
  }

  clearSession(): void {
    this.sessionToken = null;
  }

  async createSession(signal?: AbortSignal): Promise<SessionView> {
    const { response, envelope } = await this.request("/api/v1/sessions", {
      method: "POST",
      signal,
    });
    if (
      response.status !== 201 ||
      !isSuccessEnvelope(envelope) ||
      !validateSession?.(envelope.data)
    ) {
      if (
        response.status < 200 ||
        response.status >= 300 ||
        !isSuccessEnvelope(envelope)
      ) {
        throw errorForResponse(response.status, envelope);
      }
      throw new ApiFailure(
        "服务没有返回有效的会话信息，请稍后重试。",
        "invalid_response",
        response.status,
      );
    }
    const result = envelope.data as SessionResult;
    if (signal?.aborted) throw new ApiFailure("请求已取消。", "aborted");
    this.sessionToken = result.sessionToken;
    return { sessionId: result.sessionId, expiresAt: result.expiresAt };
  }

  async listCurricula(signal?: AbortSignal): Promise<CurriculumResult> {
    if (!this.sessionToken) {
      throw new ApiFailure("请先建立本次会话。", "http", 401, "UNAUTHORIZED");
    }
    const { response, envelope } = await this.request(
      "/api/v1/curriculum-snapshots",
      {
        method: "GET",
        sessionToken: this.sessionToken,
        signal,
      },
    );
    if (!response.ok) throw errorForResponse(response.status, envelope);
    if (envelope.status !== "OK" && envelope.status !== "UNKNOWN") {
      throw errorForResponse(response.status, envelope);
    }
    if (!isObject(envelope.data) || !Array.isArray(envelope.data.items)) {
      throw new ApiFailure(
        "服务返回的培养方案列表格式不完整。",
        "invalid_response",
        response.status,
      );
    }
    if (
      !envelope.data.items.every((item) => Boolean(validateSnapshot?.(item)))
    ) {
      throw new ApiFailure(
        "服务返回的培养方案信息不符合当前接口约定。",
        "invalid_response",
        response.status,
      );
    }
    const publishedCurricula = (
      envelope.data.items as SnapshotSummary[]
    ).filter(
      (item) => item.kind === "CURRICULUM" && item.state === "PUBLISHED",
    );
    const containsSynthetic = publishedCurricula.some(
      (item) =>
        item.sourceKind === "SYNTHETIC" ||
        item.sourceValidation === "SYNTHETIC",
    );
    const items = publishedCurricula.filter(
      (item) =>
        item.sourceKind !== "SYNTHETIC" &&
        item.sourceValidation !== "SYNTHETIC",
    );
    return {
      items,
      unknownMessages: [
        ...(envelope.status === "UNKNOWN"
          ? ["部分培养方案资料暂不可用，当前只列出可用资料。"]
          : []),
        ...(containsSynthetic ? ["演示培养方案不会用于真实服务模式。"] : []),
      ],
    };
  }

  private requireSession(): string {
    if (!this.sessionToken) {
      throw new ApiFailure("请先建立本次会话。", "http", 401, "UNAUTHORIZED");
    }
    return this.sessionToken;
  }

  async listSessionRecords(signal?: AbortSignal): Promise<AcademicRecordList> {
    const { response, envelope } = await this.request(
      "/api/v1/academic-records",
      { method: "GET", sessionToken: this.requireSession(), signal },
    );
    // 空 items 是业务状态，不是错误；只有非 OK 且非 UNKNOWN 才算系统错误。
    if (envelope.status !== "OK" && envelope.status !== "UNKNOWN") {
      throw errorForResponse(response.status, envelope);
    }
    const data = envelope.data;
    if (!isObject(data) || !Array.isArray(data.items)) {
      throw new ApiFailure(
        "服务返回的学业记录列表格式不完整。",
        "invalid_response",
        response.status,
      );
    }
    const items = data.items as unknown[];
    if (!items.every((item) => Boolean(validateAcademicRecord?.(item)))) {
      throw new ApiFailure(
        "服务返回的学业记录不符合当前接口约定。",
        "invalid_response",
        response.status,
      );
    }
    return { items: items as AcademicRecord[] };
  }

  async saveSessionRecord(
    input: AcademicRecordInput,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<AcademicRecord> {
    const { response, envelope } = await this.request(
      "/api/v1/academic-records",
      {
        method: "POST",
        sessionToken: this.requireSession(),
        signal,
        body: input,
        idempotencyKey,
      },
    );
    if (!isSuccessEnvelope(envelope)) {
      throw errorForResponse(response.status, envelope);
    }
    if (!validateAcademicRecord?.(envelope.data)) {
      throw new ApiFailure(
        "服务返回的学业记录不符合当前接口约定。",
        "invalid_response",
        response.status,
      );
    }
    return envelope.data as AcademicRecord;
  }

  async auditRequirements(
    curriculumSnapshotId: string,
    academicRecordId: string,
    signal?: AbortSignal,
  ): Promise<AuditResult> {
    const { response, envelope } = await this.request(
      "/api/v1/requirements/audit",
      {
        method: "POST",
        sessionToken: this.requireSession(),
        signal,
        body: {
          schemaVersion: SCHEMA_VERSION,
          curriculumSnapshotId,
          academicRecordId,
        },
      },
    );
    if (!isSuccessEnvelope(envelope)) {
      throw errorForResponse(response.status, envelope);
    }
    if (!validateAuditResult?.(envelope.data)) {
      throw new ApiFailure(
        "服务返回的学业核对结果不符合当前接口约定。",
        "invalid_response",
        response.status,
      );
    }
    return envelope.data as AuditResult;
  }

  async submitPlanning(
    request: PlanningRequest,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<PlanningAnswer> {
    const { response, envelope } = await this.request("/api/v1/planning", {
      method: "POST",
      sessionToken: this.requireSession(),
      signal,
      body: request,
      idempotencyKey,
      timeoutMs: PLANNING_TIMEOUT_MS,
    });
    if (!isSuccessEnvelope(envelope)) {
      throw errorForResponse(response.status, envelope);
    }
    if (!validatePlanningAnswer?.(envelope.data)) {
      throw new ApiFailure(
        "服务返回的规划结果不符合当前接口约定。",
        "invalid_response",
        response.status,
      );
    }
    return envelope.data as PlanningAnswer;
  }

  async searchSessionOfferings(
    previousPlanId: string,
    courseCode: string,
    signal?: AbortSignal,
  ): Promise<SessionOfferingSearch> {
    const { response, envelope } = await this.request(
      withQuery("/api/v1/session-offerings", { previousPlanId, courseCode }),
      { method: "GET", sessionToken: this.requireSession(), signal },
    );
    // 空 items 是业务状态；只有非 OK 且非 UNKNOWN 才算系统错误。
    // UNKNOWN 要靠 status 传给页面，否则空数组会被当成「确定没有班次」。
    if (!isSuccessEnvelope(envelope)) {
      throw errorForResponse(response.status, envelope);
    }
    const data = envelope.data;
    if (
      !isObject(data) ||
      data.previousPlanId !== previousPlanId ||
      data.courseCode !== courseCode ||
      !Array.isArray(data.items) ||
      !everyValid(data.items, validateCourseOffering)
    ) {
      throw new ApiFailure(
        "服务返回的开课班次不符合当前接口约定。",
        "invalid_response",
        response.status,
      );
    }
    return {
      ...(envelope.data as SessionOfferingList),
      status: businessStatus(envelope),
    };
  }

  async replaceSessionPlanItem(
    body: SessionPlanReplaceInput,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<SessionPlanReplacement> {
    const { response, envelope } = await this.request(
      "/api/v1/session-plans/replace",
      {
        method: "POST",
        sessionToken: this.requireSession(),
        signal,
        body,
        idempotencyKey,
      },
    );
    if (!isSuccessEnvelope(envelope)) {
      throw errorForResponse(response.status, envelope);
    }
    const data = envelope.data;
    if (
      !isObject(data) ||
      data.previousPlanId !== body.previousPlanId ||
      typeof data.planId !== "string" ||
      !Array.isArray(data.items) ||
      !everyValid(data.items, validatePlanItem) ||
      !Array.isArray(data.hardConstraints) ||
      !everyValid(data.hardConstraints, validateConstraint) ||
      !validatePlanValidation?.(data.verification)
    ) {
      throw new ApiFailure(
        "服务返回的换班次结果不符合当前接口约定。",
        "invalid_response",
        response.status,
      );
    }
    return envelope.data as SessionPlanReplacement;
  }

  async listTeacherCourseOptions(
    curriculumSnapshotId: string,
    courseCode: string | null,
    signal?: AbortSignal,
  ): Promise<TeacherCourseOptionSearch> {
    const { response, envelope } = await this.request(
      withQuery("/api/v1/teacher-course-options", {
        curriculumSnapshotId,
        courseCode,
      }),
      { method: "GET", sessionToken: this.requireSession(), signal },
    );
    if (!isSuccessEnvelope(envelope)) {
      throw errorForResponse(response.status, envelope);
    }
    const data = envelope.data;
    if (
      !isObject(data) ||
      !Array.isArray(data.items) ||
      !everyValid(data.items, validateTeacherCourseOption)
    ) {
      throw new ApiFailure(
        "服务返回的教师课程信息不符合当前接口约定。",
        "invalid_response",
        response.status,
      );
    }
    return {
      items: data.items as TeacherCourseOption[],
      status: businessStatus(envelope),
    };
  }

  async searchReviews(
    courseCode: string,
    teacherKey: string | null,
    signal?: AbortSignal,
  ): Promise<ReviewNoteSearch> {
    const { response, envelope } = await this.request(
      withQuery("/api/v1/reviews/search", { courseCode, teacherKey }),
      { method: "GET", sessionToken: this.requireSession(), signal },
    );
    if (!isSuccessEnvelope(envelope)) {
      throw errorForResponse(response.status, envelope);
    }
    const data = envelope.data;
    if (
      !isObject(data) ||
      !Array.isArray(data.items) ||
      !everyValid(data.items, validateReviewNote)
    ) {
      throw new ApiFailure(
        "服务返回的评价证据不符合当前接口约定。",
        "invalid_response",
        response.status,
      );
    }
    return {
      items: data.items as ReviewNote[],
      status: businessStatus(envelope),
    };
  }

  async getRunReport(runId: string, signal?: AbortSignal): Promise<RunReport> {
    const { response, envelope } = await this.request(
      `/api/v1/reports/runs/${encodeURIComponent(runId)}`,
      { method: "GET", sessionToken: this.requireSession(), signal },
    );
    if (!isSuccessEnvelope(envelope)) {
      throw errorForResponse(response.status, envelope);
    }
    if (!validateRunReport?.(envelope.data)) {
      throw new ApiFailure(
        "服务返回的运行报告不符合当前接口约定。",
        "invalid_response",
        response.status,
      );
    }
    return envelope.data as RunReport;
  }

  private async request(
    path: string,
    options: {
      method: "GET" | "POST";
      sessionToken?: string;
      signal?: AbortSignal;
      body?: unknown;
      idempotencyKey?: string;
      /** 覆盖默认超时。规划请求要等服务端跑完预算，见 PLANNING_TIMEOUT_MS。 */
      timeoutMs?: number;
    },
  ): Promise<{ response: Response; envelope: Envelope<unknown> }> {
    if (options.signal?.aborted)
      throw new ApiFailure("请求已取消。", "aborted");
    const controller = new AbortController();
    let timedOut = false;
    const timeout = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, options.timeoutMs ?? this.timeoutMs);
    const abortFromCaller = () => controller.abort();
    options.signal?.addEventListener("abort", abortFromCaller, { once: true });
    const requestId = `web-${crypto.randomUUID().replaceAll("-", "")}`;
    const headers = new Headers({
      "X-Request-Id": requestId,
      Accept: "application/json",
    });
    if (options.sessionToken)
      headers.set("Authorization", `Bearer ${options.sessionToken}`);
    if (options.idempotencyKey)
      headers.set("Idempotency-Key", options.idempotencyKey);
    if (options.body !== undefined)
      headers.set("Content-Type", "application/json");

    try {
      const response = await this.fetcher(`${this.baseUrl}${path}`, {
        method: options.method,
        headers,
        credentials: "omit",
        cache: "no-store",
        signal: controller.signal,
        body:
          options.body === undefined ? undefined : JSON.stringify(options.body),
      });
      let body: unknown;
      try {
        body = await response.json();
      } catch {
        if (!response.ok) throw errorForResponse(response.status, null);
        throw new ApiFailure(
          "服务返回的数据无法读取，请稍后重试。",
          "invalid_response",
          response.status,
        );
      }
      let envelope: Envelope<unknown>;
      try {
        envelope = parseEnvelope(body);
      } catch (error) {
        if (!response.ok) throw errorForResponse(response.status, null);
        throw error;
      }
      if (!response.ok) throw errorForResponse(response.status, envelope);
      return { response, envelope };
    } catch (error) {
      if (error instanceof ApiFailure) throw error;
      if (timedOut)
        throw new ApiFailure(
          "连接服务超时，请检查服务后重试。",
          "timeout",
          null,
          null,
          true,
        );
      if (options.signal?.aborted)
        throw new ApiFailure("请求已取消。", "aborted");
      if (error instanceof DOMException && error.name === "AbortError") {
        throw new ApiFailure("请求已取消。", "aborted");
      }
      throw new ApiFailure(
        "暂时无法连接服务，请确认服务已启动后重试。",
        "network",
        null,
        null,
        true,
      );
    } finally {
      clearTimeout(timeout);
      options.signal?.removeEventListener("abort", abortFromCaller);
    }
  }
}
