import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vitest/config";

// `npm run dev:fixture` 走 --mode fixture，页面用合成数据，不需要后端。
// 没有用 .env.fixture 文件：仓库的 .gitignore 排除了 .env.*，那种做法提交
// 不进来，队友 clone 下去就跑不了。

// COURSEPILOT_TUNNEL_HOST 可以是逗号分隔的多个域名（例如裸域名和 www）。
// dev 与 preview 共用同一份白名单，公网隧道访问时 Host 头才能通过校验。
const tunnelHosts = (process.env.COURSEPILOT_TUNNEL_HOST ?? "")
  .split(",")
  .map((host) => host.trim())
  .filter((host) => host.length > 0);

// 只用于 `vite preview`（公网演示的生产构建）。dev 服务器保持原样，
// 因为 HMR 需要内联脚本与 WebSocket，不能套这套策略。
const PREVIEW_CSP = [
  "default-src 'self'",
  // ajv 在运行时用 new Function 编译校验函数（domain 契约校验），需要 unsafe-eval。
  // 这是已知的放宽；根治办法是构建时预编译 ajv（standalone），之后可删掉这一项。
  "script-src 'self' 'unsafe-eval'",
  // Vue 的 :style 绑定写入的是 style 属性，需要 unsafe-inline；脚本不放行内联。
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self'",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const PREVIEW_HEADERS = {
  "Content-Security-Policy": PREVIEW_CSP,
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
};

export default defineConfig(({ mode }) => ({
  plugins: [vue()],
  define:
    mode === "fixture"
      ? { "import.meta.env.VITE_COURSEPILOT_MODE": JSON.stringify("fixture") }
      : {},
  build: {
    // 公网演示不发布 sourcemap，避免把源码结构和注释暴露给访问者。
    sourcemap: false,
    rollupOptions: {
      treeshake: {
        moduleSideEffects: (id) => !id.endsWith("/src/api/fixture-client.ts"),
      },
    },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": process.env.COURSEPILOT_API_PROXY || "http://127.0.0.1:8000",
    },
    ...(tunnelHosts.length > 0 ? { allowedHosts: tunnelHosts } : {}),
  },
  preview: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": process.env.COURSEPILOT_API_PROXY || "http://127.0.0.1:8000",
    },
    headers: PREVIEW_HEADERS,
    ...(tunnelHosts.length > 0 ? { allowedHosts: tunnelHosts } : {}),
  },
  test: {
    environment: "jsdom",
    clearMocks: true,
    restoreMocks: true,
  },
}));
