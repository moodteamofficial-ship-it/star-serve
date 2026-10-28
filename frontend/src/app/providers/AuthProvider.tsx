import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { ApiError } from "@/services/api/client";
import { authApi, type UserPublic } from "@/services/auth/authApi";
import { clearIdleLockStore } from "@/services/auth/idleLockStore";
import { setSessionUserHandler } from "@/services/auth/sessionBridge";
import {
  getStoredApiEnvironment,
  syncStoredEnvFromUser,
  type ApiEnvironment,
} from "@/services/api/envTarget";

type AuthState = {
  user: UserPublic | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<UserPublic | null>;
  hasPermission: (code: string) => boolean;
};

function isUnauthenticated(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserPublic | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setSessionUserHandler((next) => {
      if (!next) clearIdleLockStore();
      setUser(next);
    });
    return () => setSessionUserHandler(null);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const bootDeadline = window.setTimeout(() => {
      if (!cancelled) setLoading(false);
    }, 8_000);

    (async () => {
      try {
        // apiRequest auto-refreshes on 401, then retries /me with the new access cookie
        const res = await authApi.me();
        if (cancelled) return;
        const user = res.data;
        const preferred = (user.preferred_app_env || user.app_env) as ApiEnvironment;
        const needsReload = syncStoredEnvFromUser(preferred, user.app_env);
        if (needsReload) {
          const guardKey = "ss_env_reload";
          const token = `${preferred}:${getStoredApiEnvironment()}`;
          if (sessionStorage.getItem(guardKey) !== token) {
            sessionStorage.setItem(guardKey, token);
            window.location.reload();
            return;
          }
        } else {
          sessionStorage.removeItem("ss_env_reload");
        }
        setUser(user);
      } catch {
        if (!cancelled) {
          clearIdleLockStore();
          setUser(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      window.clearTimeout(bootDeadline);
    };
  }, []);

  const refreshUser = useCallback(async () => {
    try {
      const res = await authApi.me();
      setUser(res.data);
      return res.data;
    } catch (error) {
      if (isUnauthenticated(error)) {
        clearIdleLockStore();
        setUser(null);
        return null;
      }
      throw error;
    }
  }, []);

  // Keep shell permissions aligned with live DB authz without ending the session.
  useEffect(() => {
    if (loading || !user) return;

    let cancelled = false;
    async function syncPermissions() {
      try {
        const next = await refreshUser();
        if (cancelled || !next) return;
      } catch {
        // 403/5xx/network: keep the signed-in shell; the next request enforces live authz.
      }
    }

    function onVisible() {
      if (document.visibilityState === "visible") void syncPermissions();
    }

    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);
    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onVisible);
    };
  }, [loading, refreshUser, user?.id]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await authApi.login(email, password);
    setUser(res.data.user);
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      clearIdleLockStore();
      setUser(null);
    }
  }, []);

  const hasPermission = useCallback(
    (code: string) => {
      const perms = user?.permissions;
      if (!perms?.length) return false;
      return perms.includes(code) || perms.includes("*:*");
    },
    [user],
  );

  const value = useMemo(
    () => ({ user, loading, login, logout, refreshUser, hasPermission }),
    [user, loading, login, logout, refreshUser, hasPermission],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
