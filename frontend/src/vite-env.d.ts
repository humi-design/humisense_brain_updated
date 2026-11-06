/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE?: string;
  readonly VITE_API_TARGET?: string;
  readonly VITE_TENANT_ID?: string;
  readonly VITE_USER_ID?: string;
  readonly VITE_USER_ROLE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
