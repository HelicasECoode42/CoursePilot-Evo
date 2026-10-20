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
  SessionResult,
  SnapshotSummary,
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

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
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
