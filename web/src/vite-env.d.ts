/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_PORTAL_DATA_MODE?: "live" | "mock";
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
