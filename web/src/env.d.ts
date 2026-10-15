/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_COURSEPILOT_MODE?: "http" | "fixture";
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
