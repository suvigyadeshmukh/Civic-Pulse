/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL for REST API calls (default: /api/v1). */
  readonly VITE_API_BASE_URL: string;
  /** Base URL for WebSocket connections (default: ws://localhost:8000/ws). */
  readonly VITE_WS_BASE_URL: string;
  /** String flag ("true" | "false") enabling deterministic API fixtures. */
  readonly VITE_USE_API_MOCKS: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
