import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vitest/config";

// `npm run dev:fixture` 走 --mode fixture，页面用合成数据，不需要后端。
// 没有用 .env.fixture 文件：仓库的 .gitignore 排除了 .env.*，那种做法提交
// 不进来，队友 clone 下去就跑不了。
export default defineConfig(({ mode }) => ({
  plugins: [vue()],
  define:
    mode === "fixture"
      ? { "import.meta.env.VITE_COURSEPILOT_MODE": JSON.stringify("fixture") }
      : {},
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
  },
  test: {
    environment: "jsdom",
    clearMocks: true,
    restoreMocks: true,
  },
}));
