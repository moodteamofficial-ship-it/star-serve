import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useAuth } from "@/app/providers/AuthProvider";
import { ScreenLockOverlay } from "@/components/layout/ScreenLockOverlay";
import {
  IDLE_LOCK_MS,
  IDLE_LOCK_STORAGE_KEY,
  readIdleLockSnapshot,
  shouldLockForUser,
  writeIdleLockSnapshot,
} from "@/services/auth/idleLockStore";

const ACTIVITY_EVENTS = [
  "mousedown",
  "mousemove",
  "keydown",
  "scroll",
  "touchstart",
  "pointerdown",
  "wheel",
] as const;

const ACTIVITY_WRITE_MS = 1000;

export function IdleLockProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const userId = user?.id ?? null;
  const [locked, setLocked] = useState(() => (userId ? shouldLockForUser(userId) : false));
  const lockedRef = useRef(locked);
  const lastActivityAt = useRef(Date.now());
  const lastWriteAt = useRef(0);
  const lockTimer = useRef<number | null>(null);
  const concealRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    lockedRef.current = locked;
  }, [locked]);

  useEffect(() => {
    const el = concealRef.current;
    if (el) el.inert = locked;
  }, [locked]);

  const persist = useCallback(
    (nextLocked: boolean, activityAt: number) => {
      if (!userId) return;
      writeIdleLockSnapshot({
        userId,
        locked: nextLocked,
        lastActivityAt: activityAt,
      });
    },
    [userId],
  );

  const lockNow = useCallback(() => {
    if (!userId || lockedRef.current) return;
    lockedRef.current = true;
    if (lockTimer.current != null) {
      window.clearTimeout(lockTimer.current);
      lockTimer.current = null;
    }
    persist(true, lastActivityAt.current);
    setLocked(true);
  }, [persist, userId]);

  const scheduleLock = useCallback(() => {
    if (lockTimer.current != null) {
      window.clearTimeout(lockTimer.current);
      lockTimer.current = null;
    }
    if (!userId || lockedRef.current) return;
    const remaining = IDLE_LOCK_MS - (Date.now() - lastActivityAt.current);
    if (remaining <= 0) {
      lockNow();
      return;
    }
    lockTimer.current = window.setTimeout(() => {
      lockTimer.current = null;
      lockNow();
    }, remaining);
  }, [lockNow, userId]);

  const markActivity = useCallback(() => {
    if (!userId || lockedRef.current) return;
    const now = Date.now();
    lastActivityAt.current = now;
    if (now - lastWriteAt.current >= ACTIVITY_WRITE_MS) {
      lastWriteAt.current = now;
      persist(false, now);
    }
    scheduleLock();
  }, [persist, scheduleLock, userId]);

  const unlock = useCallback(() => {
    if (!userId) return;
    const now = Date.now();
    lastActivityAt.current = now;
    lastWriteAt.current = now;
    lockedRef.current = false;
    persist(false, now);
    setLocked(false);
  }, [persist, userId]);

  useEffect(() => {
    if (!userId) {
      setLocked(false);
      return;
    }

    const snap = readIdleLockSnapshot();
    const now = Date.now();
    const alreadyLocked = shouldLockForUser(userId, now);
    lastActivityAt.current =
      snap?.userId === userId ? snap.lastActivityAt : now;
    lastWriteAt.current = now;
    setLocked(alreadyLocked);
    persist(alreadyLocked, lastActivityAt.current);
    if (!alreadyLocked) scheduleLock();

    return () => {
      if (lockTimer.current != null) {
        window.clearTimeout(lockTimer.current);
        lockTimer.current = null;
      }
    };
  }, [persist, scheduleLock, userId]);

  useEffect(() => {
    if (!userId || locked) return;

    scheduleLock();

    function onActivity() {
      markActivity();
    }

    function onVisibility() {
      if (document.visibilityState !== "visible") return;
      if (Date.now() - lastActivityAt.current >= IDLE_LOCK_MS) {
        lockNow();
        return;
      }
      scheduleLock();
    }

    for (const event of ACTIVITY_EVENTS) {
      document.addEventListener(event, onActivity, { capture: true, passive: true });
    }
    window.addEventListener("focus", onVisibility);
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pageshow", onVisibility);

    return () => {
      for (const event of ACTIVITY_EVENTS) {
        document.removeEventListener(event, onActivity, true);
      }
      window.removeEventListener("focus", onVisibility);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pageshow", onVisibility);
    };
  }, [lockNow, locked, markActivity, scheduleLock, userId]);

  useEffect(() => {
    if (!userId) return;

    function onStorage(event: StorageEvent) {
      if (event.key !== IDLE_LOCK_STORAGE_KEY) return;
      const snap = readIdleLockSnapshot();
      if (!snap || snap.userId !== userId) return;
      lastActivityAt.current = snap.lastActivityAt;
      if (snap.locked) {
        lockedRef.current = true;
        setLocked(true);
        return;
      }
      lockedRef.current = false;
      setLocked(false);
      scheduleLock();
    }

    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [scheduleLock, userId]);

  if (!user) return children;

  return (
    <>
      <div
        ref={concealRef}
        className={locked ? "idle-lock-conceal" : undefined}
        aria-hidden={locked || undefined}
      >
        {children}
      </div>
      {locked
        ? createPortal(<ScreenLockOverlay user={user} onUnlocked={unlock} />, document.body)
        : null}
    </>
  );
}
