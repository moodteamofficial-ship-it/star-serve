import { ApiError } from "@/services/api/client";

export function parseLockUntilMs(err: ApiError): number | null {
  const detail = Array.isArray(err.details) ? err.details[0] : null;
  if (!detail || typeof detail !== "object") return null;
  const row = detail as { locked_until?: string; retry_after_seconds?: number };
  if (typeof row.locked_until === "string") {
    const ts = Date.parse(row.locked_until);
    if (!Number.isNaN(ts)) return ts;
  }
  if (typeof row.retry_after_seconds === "number" && row.retry_after_seconds > 0) {
    return Date.now() + row.retry_after_seconds * 1000;
  }
  return null;
}

export function formatCountdown(totalSeconds: number): string {
  const s = Math.max(0, Math.ceil(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) {
    return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  }
  return `${m}:${String(sec).padStart(2, "0")}`;
}

export function isLoginLockedError(err: ApiError): boolean {
  return err.code === "LOGIN_LOCKED" || err.status === 429;
}
