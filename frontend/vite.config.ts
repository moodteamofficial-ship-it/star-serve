import { defineConfig, loadEnv, type ProxyOptions } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import type { IncomingMessage } from "node:http";

const LOCAL_API_FALLBACK = "http://127.0.0.1:8000";
const STAGING_FALLBACK =
  "https://starserve-api-staging-233389149626.europe-west1.run.app";
const PRODUCTION_FALLBACK = "https://starserve-api.onrender.com";

/**
 * Cloud Run sets SameSite=None; Secure (correct for HTTPS). Browsers reject
 * those cookies on http://localhost, so rewrite only in this local proxy —
 * production / Render cookies are unchanged.
 */
function rewriteProxiedCookies(proxyRes: IncomingMessage): void {
  const raw = proxyRes.headers["set-cookie"];
  if (!raw) return;
  const cookies = (Array.isArray(raw) ? raw : [raw]).map((cookie) =>
    cookie
      .replace(/;\s*Secure/gi, "")
      .replace(/;\s*Partitioned/gi, "")
      .replace(/;\s*SameSite=None/gi, "; SameSite=Lax")
      .replace(/;\s*Domain=[^;]*/gi, ""),
  );
  proxyRes.headers["set-cookie"] = cookies;
}

function apiProxy(target: string, rewriteFrom?: string): ProxyOptions {
  const isLocal = /^https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/i.test(target);
  const proxy: ProxyOptions = {
    target,
    changeOrigin: true,
    secure: !isLocal,
    // Match Cloud Run request timeout so long certificate issuance is not
    // dropped by the local Vite proxy while Definite is still working.
    timeout: 180_000,
    proxyTimeout: 180_000,
    configure(proxyServer) {
      proxyServer.on("proxyRes", (proxyRes) => {
        rewriteProxiedCookies(proxyRes);
      });
    },
  };
  if (rewriteFrom) {
    proxy.rewrite = (requestPath) =>
      requestPath.replace(new RegExp(`^${rewriteFrom}`), "/api");
  }
  return proxy;
}

function normalizeViteBase(raw: string | undefined): string {
  const value = (raw || "/").trim() || "/";
  if (value === "/") return "/";
  const withLead = value.startsWith("/") ? value : `/${value}`;
  return withLead.endsWith("/") ? withLead : `${withLead}/`;
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const localApi = (env.DEV_PROXY_LOCAL || LOCAL_API_FALLBACK).replace(/\/$/, "");
  const staging = (env.DEV_PROXY_STAGING || STAGING_FALLBACK).replace(/\/$/, "");
  const production = (env.DEV_PROXY_PRODUCTION || PRODUCTION_FALLBACK).replace(/\/$/, "");
  // Render custom domain mounts the SPA under /dashboard/; Cloud Run stays at /.
  const base = normalizeViteBase(env.VITE_BASE_PATH || process.env.VITE_BASE_PATH);

  // Localhost default: /api → local uvicorn. Remote planes stay opt-in via Data switcher.
  const proxy = {
    "/api": apiProxy(localApi),
    "/health": apiProxy(localApi),
    "/staging-api": apiProxy(staging, "/staging-api"),
    "/prod-api": apiProxy(production, "/prod-api"),
  };

  return {
    base,
    plugins: [react()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "src"),
      },
    },
    build: {
      // Never ship source maps to the browser in staging/production builds.
      sourcemap: false,
    },
    server: {
      port: 5173,
      proxy,
    },
    preview: {
      port: 5173,
      proxy,
    },
  };
});
