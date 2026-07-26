/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_SIM_API_URL?: string;
  readonly VITE_SIM_RUN_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
