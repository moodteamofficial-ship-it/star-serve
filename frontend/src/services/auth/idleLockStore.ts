/** Persisted idle-lock state — shared across tabs for the signed-in user. */

export const IDLE_LOCK_MS = 8 * 60 * 1000;
export const IDLE_LOCK_STORAGE_KEY = "ss_idle_lock";

export type IdleLockSnapshot = {
  userId: string;
  locked: boolean;
  lastActivityAt: number;
};

function isSnapshot(value: unknown): value is IdleLockSnapshot {
  if (!value || typeof value !== "object") return false;
  const row = value as IdleLockSnapshot;
  return (
    typeof row.userId === "string" &&
    typeof row.locked === "boolean" &&
    typeof row.lastActivityAt === "number"
  );
}

export function readIdleLockSnapshot(): IdleLockSnapshot | null {
  try {
    const raw = window.localStorage.getItem(IDLE_LOCK_STORAGE_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    return isSnapshot(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export function writeIdleLockSnapshot(snapshot: IdleLockSnapshot): void {
  try {
    window.localStorage.setItem(IDLE_LOCK_STORAGE_KEY, JSON.stringify(snapshot));
  } catch {
    // Private mode / quota — in-memory lock still applies in this tab.
  }
}

export function clearIdleLockStore(): void {
  try {
    window.localStorage.removeItem(IDLE_LOCK_STORAGE_KEY);
  } catch {
    // ignore
  }
}

export function shouldLockForUser(userId: string, now = Date.now()): boolean {
  const snap = readIdleLockSnapshot();
  if (!snap || snap.userId !== userId) return false;
  if (snap.locked) return true;
  return now - snap.lastActivityAt >= IDLE_LOCK_MS;
}
