import Ajv2020 from "ajv/dist/2020";
import addFormats from "ajv-formats";
import domainSchema from "../../../contracts/schemas/domain.schema.json";
import type { Envelope, SessionResult, SnapshotSummary } from "../contracts";

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

export class HttpApiClient implements CoursePilotApiClient {
  readonly mode = "http" as const;
  private readonly baseUrl: string;
  private sessionToken: string | null = null;

  constructor(
    baseUrl: string,
    private readonly fetcher: typeof fetch = fetch,
    private readonly timeoutMs = 8_000,
  ) {
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
      envelope.status !== "OK" ||
      !validateSession?.(envelope.data)
    ) {
      if (
        response.status < 200 ||
        response.status >= 300 ||
        envelope.status !== "OK"
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

  private async request(
    path: string,
    options: {
      method: "GET" | "POST";
      sessionToken?: string;
      signal?: AbortSignal;
    },
  ): Promise<{ response: Response; envelope: Envelope<unknown> }> {
    if (options.signal?.aborted)
      throw new ApiFailure("请求已取消。", "aborted");
    const controller = new AbortController();
    let timedOut = false;
    const timeout = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, this.timeoutMs);
    const abortFromCaller = () => controller.abort();
    options.signal?.addEventListener("abort", abortFromCaller, { once: true });
    const requestId = `web-${crypto.randomUUID().replaceAll("-", "")}`;
    const headers = new Headers({
      "X-Request-Id": requestId,
      Accept: "application/json",
    });
    if (options.sessionToken)
      headers.set("Authorization", `Bearer ${options.sessionToken}`);

    try {
      const response = await this.fetcher(`${this.baseUrl}${path}`, {
        method: options.method,
        headers,
        credentials: "omit",
        cache: "no-store",
        signal: controller.signal,
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
