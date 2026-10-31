import { FixtureApiClient } from "./fixture-client";
import { HttpApiClient, type CoursePilotApiClient } from "./client";

export type ApiMode = "http" | "fixture" | "simulation";

export function createApiClient(
  mode: ApiMode,
  options: {
    baseUrl?: string;
    fetcher?: typeof fetch;
    timeoutMs?: number;
  } = {},
): CoursePilotApiClient {
  if (mode === "fixture") {
    // 合成数据只给开发服务器和测试用。生产构建里 import.meta.env.DEV 为 false，
    // 这里的 new FixtureApiClient() 会被打包器删掉，fixture 数据不进公开的包。
    if (!import.meta.env.DEV) {
      throw new Error("fixture 模式只在开发服务器（dev / vitest）可用");
    }
    return new FixtureApiClient();
  }
  // Route through the website's /api proxy unless an explicit backend is configured.
  const baseUrl = options.baseUrl?.trim() || "/";
  return new HttpApiClient(baseUrl, options.fetcher, options.timeoutMs, mode);
}

const configuredMode = import.meta.env.VITE_COURSEPILOT_MODE ?? "http";
if (
  configuredMode !== "http" &&
  configuredMode !== "fixture" &&
  configuredMode !== "simulation"
) {
  throw new Error("VITE_COURSEPILOT_MODE must be http, fixture or simulation");
}

export const api = createApiClient(configuredMode, {
  baseUrl: import.meta.env.VITE_API_BASE_URL,
});
