import { useEffect, useId, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/app/providers/AuthProvider";
import { IconChevronDown } from "@/components/ui/icons";
import {
  type ApiEnvironment,
  dataPlaneForEnv,
  dataPlaneLabel,
  envLabel,
  getStoredApiEnvironment,
  readEnvEndpoints,
  setStoredApiEnvironment,
} from "@/services/api/envTarget";
import { authApi } from "@/services/auth/authApi";

/**
 * Per-user (browser) switch between Staging, Live, and Backup data planes.
 * Each target is a different API host with its own server-side DATABASE_URL.
 * Credentials never leave the backend; switching only changes the public API base URL.
 */
export function EnvSwitcher({ open: menuOpen = true }: { open?: boolean }) {
  const queryClient = useQueryClient();
  const { logout, user } = useAuth();
  const [env, setEnv] = useState<ApiEnvironment>(() => getStoredApiEnvironment());
  const [expanded, setExpanded] = useState(false);
  const listId = useId();
  const endpoints = readEnvEndpoints();
  const plane = dataPlaneForEnv(env);
  const allowProductionSwitch =
    import.meta.env.VITE_ALLOW_PRODUCTION_ENV_SWITCH === "true";

  useEffect(() => {
    if (!menuOpen) setExpanded(false);
  }, [menuOpen]);

  async function onChange(next: ApiEnvironment) {
    if (next === env) {
      setExpanded(false);
      return;
    }
    if (next === "production" && !allowProductionSwitch) {
      const ok = window.confirm(
        "Switch to Live data? This uses production customer data. Continue only if you intend to.",
      );
      if (!ok) return;
    }
    if (next === "backup") {
      const ok = window.confirm(
        "Switch to Backup data? This is a restored / archival copy — treat it as read-mostly. Continue?",
      );
      if (!ok) return;
    }

    setStoredApiEnvironment(next);
    setEnv(next);
    queryClient.clear();

    if (user) {
      try {
        await authApi.setPreferredEnv(next);
      } catch {
        /* continue — local switch still applies */
      }
      try {
        await logout();
      } catch {
        /* ignore — target host may differ */
      }
    }

    window.location.reload();
  }

  const options: ApiEnvironment[] = ["development", "staging", "production", "backup"];

  return (
    <div
      className={`env-switcher${expanded ? " is-expanded" : ""}`}
      data-env={env}
      data-plane={plane}
    >
      <button
        type="button"
        className="env-switcher-trigger"
        aria-expanded={expanded}
        aria-controls={listId}
        tabIndex={menuOpen ? 0 : -1}
        onClick={() => setExpanded((v) => !v)}
      >
        <span className="env-switcher-copy">
          <span className="env-switcher-kicker">Data</span>
          <strong className="env-switcher-title">
            {env === "development" ? envLabel(env) : dataPlaneLabel(plane)}
          </strong>
        </span>
        <IconChevronDown className="env-switcher-chevron" />
      </button>

      <div
        id={listId}
        className="env-switcher-panel"
        role="listbox"
        aria-label="Data plane"
        aria-hidden={!expanded}
      >
        {/* {!isolated ? (
          <p className="env-switcher-hint">
            Staging, Live, and Backup should use distinct API hosts. Set VITE_API_URL_* (or run
            docker api-staging / api-live / api-backup) for real isolation.
          </p>
        ) : null} */}
        {options.map((value) => {
          const selected = value === env;
          const disabled = !endpoints[value];
          return (
            <button
              key={value}
              type="button"
              role="option"
              aria-selected={selected}
              className={`env-switcher-option${selected ? " is-selected" : ""}`}
              disabled={disabled || !expanded}
              tabIndex={expanded && menuOpen ? 0 : -1}
              onClick={() => void onChange(value)}
            >
              <span className="env-switcher-option-label">{envLabel(value)}</span>
              {selected ? <span className="env-switcher-option-check" aria-hidden="true" /> : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}
