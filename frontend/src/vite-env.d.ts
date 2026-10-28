/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Default / legacy single API base (include /api/v1). Public URL only. */
  readonly VITE_API_BASE_URL: string;
  readonly VITE_APP_NAME: string;
  /** Per-environment API bases — public HTTPS URLs, never database credentials. */
  readonly VITE_API_URL_DEVELOPMENT?: string;
  readonly VITE_API_URL_STAGING?: string;
  readonly VITE_API_URL_PRODUCTION?: string;
  readonly VITE_API_URL_BACKUP?: string;
  readonly VITE_DEFAULT_API_ENV?: "development" | "staging" | "production" | "backup";
  /** Set "true" to skip the production confirmation dialog (still never ships DB secrets). */
  readonly VITE_ALLOW_PRODUCTION_ENV_SWITCH?: string;
  /** Public SPA origins for agent QR links (welcome screen). */
  readonly VITE_WEB_URL_DEVELOPMENT?: string;
  readonly VITE_WEB_URL_STAGING?: string;
  readonly VITE_WEB_URL_PRODUCTION?: string;
  readonly VITE_WEB_URL_BACKUP?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
