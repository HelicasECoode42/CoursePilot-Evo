import { FixtureApiClient } from "./fixture-client";
import { HttpApiClient, type CoursePilotApiClient } from "./client";

export type ApiMode = "http" | "fixture";

export function createApiClient(
  mode: ApiMode,
  options: {
    baseUrl?: string;
    fetcher?: typeof fetch;
    timeoutMs?: number;
  } = {},
): CoursePilotApiClient {
  if (mode === "fixture") return new FixtureApiClient();
  const baseUrl = options.baseUrl?.trim() || "http://127.0.0.1:8000";
  return new HttpApiClient(baseUrl, options.fetcher, options.timeoutMs);
}

const configuredMode = import.meta.env.VITE_COURSEPILOT_MODE ?? "http";
if (configuredMode !== "http" && configuredMode !== "fixture") {
  throw new Error("VITE_COURSEPILOT_MODE must be http or fixture");
}

export const api = createApiClient(configuredMode, {
  baseUrl: import.meta.env.VITE_API_BASE_URL,
});
