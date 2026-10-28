import { useEffect, useId, useRef, useState, type FormEvent, type ReactNode, type TransitionEvent } from "react";
import { useAuth } from "@/app/providers/AuthProvider";
import { useTheme } from "@/app/providers/ThemeProvider";
import { FormError } from "@/components/ui/FormError";
import { IconMoon, IconSun } from "@/components/ui/icons";
import { ApiError } from "@/services/api/client";
import { mediaSrc } from "@/services/media/mediaSrc";
import { formatCountdown, isLoginLockedError, parseLockUntilMs } from "@/services/auth/loginLock";
import type { UserPublic } from "@/services/auth/authApi";

const UNLOCK_MIN_MS = 400;

function wait(ms: number) {
  return new Promise<void>((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function initialsFor(user: UserPublic): string {
  const source = user.full_name || user.email || "SS";
  const parts = source.trim().split(/\s+/);
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  return source.slice(0, 2).toUpperCase();
}

/** First letter of the local part + stars, domain kept so the account is recognizable. */
function maskEmail(email: string): string {
  const value = email.trim();
  const at = value.lastIndexOf("@");
  if (at <= 0 || at === value.length - 1) return "***";
  const local = value.slice(0, at);
  const domain = value.slice(at + 1);
  const stars = "*".repeat(Math.max(3, Math.min(Math.max(local.length - 1, 0), 6)));
  return `${local[0]}${stars}@${domain}`;
}

export function ScreenLockOverlay({
  user,
  onUnlocked,
}: {
  user: UserPublic;
  onUnlocked: () => void;
}) {
  const { login, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const titleId = useId();
  const overlayRef = useRef<HTMLDivElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [errorTitle, setErrorTitle] = useState("Unlock failed");
  const [lockUntilMs, setLockUntilMs] = useState<number | null>(null);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [shownError, setShownError] = useState<string | null>(null);
  const [shownErrorTitle, setShownErrorTitle] = useState("Unlock failed");
  const [shownLockUntilMs, setShownLockUntilMs] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [imgFailed, setImgFailed] = useState(false);

  const errorOpen = Boolean(error);
  const lockActive = shownLockUntilMs != null && shownLockUntilMs > nowMs;
  const remainingSeconds =
    shownLockUntilMs != null ? Math.max(0, (shownLockUntilMs - nowMs) / 1000) : 0;
  const formDisabled = submitting || lockActive;
  const initials = initialsFor(user);
  const photoSrc = mediaSrc(user.avatar_url);
  const showPhoto = Boolean(photoSrc) && !imgFailed;

  useEffect(() => {
    setImgFailed(false);
  }, [photoSrc]);

  useEffect(() => {
    if (error) {
      setShownError(error);
      setShownErrorTitle(errorTitle);
      setShownLockUntilMs(lockUntilMs);
      return;
    }
    const t = window.setTimeout(() => {
      setShownError(null);
      setShownLockUntilMs(null);
    }, 450);
    return () => window.clearTimeout(t);
  }, [error, errorTitle, lockUntilMs]);

  useEffect(() => {
    if (shownLockUntilMs == null) return;
    setNowMs(Date.now());
    const id = window.setInterval(() => setNowMs(Date.now()), 250);
    return () => window.clearInterval(id);
  }, [shownLockUntilMs]);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const t = window.setTimeout(() => passwordRef.current?.focus(), 40);
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";
    document.documentElement.classList.add("idle-lock-active");

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        return;
      }
      if (event.key !== "Tab") return;
      const root = overlayRef.current;
      if (!root) return;
      const focusable = Array.from(
        root.querySelectorAll<HTMLElement>("button:not([disabled]), input:not([disabled])"),
      ).filter((el) => el.tabIndex !== -1 && !el.closest(".idle-lock-username"));
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    function onPointerOrKey(event: Event) {
      const root = overlayRef.current;
      if (!root) return;
      if (event.target instanceof Node && root.contains(event.target)) return;
      event.preventDefault();
      event.stopPropagation();
      passwordRef.current?.focus();
    }

    document.addEventListener("keydown", onKeyDown, true);
    document.addEventListener("pointerdown", onPointerOrKey, true);
    return () => {
      window.clearTimeout(t);
      document.removeEventListener("keydown", onKeyDown, true);
      document.removeEventListener("pointerdown", onPointerOrKey, true);
      document.body.style.overflow = overflow;
      document.documentElement.classList.remove("idle-lock-active");
      previous?.focus?.();
    };
  }, []);

  function onErrorSlotTransitionEnd(e: TransitionEvent<HTMLDivElement>) {
    if (e.target !== e.currentTarget) return;
    if (!error) {
      setShownError(null);
      setShownLockUntilMs(null);
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (formDisabled) return;

    setSubmitting(true);
    setError(null);
    setErrorTitle("Unlock failed");
    setLockUntilMs(null);

    const started = Date.now();
    let unlockError: string | null = null;
    let unlockErrorTitle = "Unlock failed";
    let nextLockUntil: number | null = null;

    try {
      await login(user.email, password);
    } catch (err) {
      if (err instanceof ApiError) {
        if (isLoginLockedError(err)) {
          unlockErrorTitle = "Temporarily locked";
          nextLockUntil = parseLockUntilMs(err);
          unlockError = "Too many failed sign-in attempts.";
        } else {
          unlockError = "Incorrect password.";
        }
      } else {
        unlockError = "Unable to unlock";
      }
    }

    const remaining = UNLOCK_MIN_MS - (Date.now() - started);
    if (remaining > 0) await wait(remaining);

    if (unlockError) {
      setErrorTitle(unlockErrorTitle);
      setLockUntilMs(nextLockUntil);
      setError(unlockError);
      setPassword("");
      setSubmitting(false);
      window.setTimeout(() => passwordRef.current?.focus(), 40);
      return;
    }

    onUnlocked();
  }

  let lockBody: ReactNode = shownError;
  if (shownError && shownLockUntilMs != null) {
    lockBody = (
      <span className="auth-lock-body">
        <span className="auth-lock-message">{shownError}</span>
        {lockActive ? (
          <span className="auth-lock-retry">
            Try again in <time className="auth-lock-countdown">{formatCountdown(remainingSeconds)}</time>
          </span>
        ) : (
          <span className="auth-lock-retry">You can try unlocking again.</span>
        )}
      </span>
    );
  }

  return (
    <div
      ref={overlayRef}
      className="idle-lock auth-shell"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      aria-busy={submitting}
    >
      <span className="brand-logo-link brand-logo-link--auth idle-lock-brand">
        <img
          src={`${import.meta.env.BASE_URL}star-serve-logo.png?v=3`}
          alt="Star Serve Insurance Agency"
          className="brand-logo brand-logo--auth"
        />
      </span>
      <button
        type="button"
        className="theme-toggle theme-toggle--auth-icon"
        onClick={toggleTheme}
        disabled={submitting}
        aria-label={theme === "light" ? "Switch to dark mode" : "Switch to light mode"}
      >
        {theme === "light" ? <IconMoon /> : <IconSun />}
      </button>
      <div className="auth-panel">
        <div className="auth-panel-inner">
          <div className="auth-copy">
            <h1 id={titleId}>Welcome back</h1>
            <p className="lede">This session is locked after a period of inactivity.</p>
          </div>
          <div className={`auth-card${errorOpen ? " auth-card--error-open" : ""}`}>
            <div className="idle-lock-identity">
              {showPhoto ? (
                <img
                  src={photoSrc!}
                  alt=""
                  className="topbar-avatar topbar-avatar--photo topbar-avatar--lg"
                  onError={() => setImgFailed(true)}
                />
              ) : (
                <span className="topbar-avatar topbar-avatar--lg" aria-hidden="true">
                  {initials}
                </span>
              )}
              <div className="idle-lock-identity-copy">
                <strong>{user.full_name || maskEmail(user.email)}</strong>
                <em>{maskEmail(user.email)}</em>
              </div>
            </div>
            <form onSubmit={onSubmit} className="auth-form">
              <label className="idle-lock-username" aria-hidden="true">
                <span className="field-caption">Email</span>
                <input
                  type="email"
                  autoComplete="username"
                  value={user.email}
                  readOnly
                  tabIndex={-1}
                  hidden
                />
              </label>
              <label>
                <span className="field-caption">Password</span>
                <input
                  ref={passwordRef}
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={8}
                  disabled={formDisabled}
                />
              </label>
              <div
                className={`auth-error-slot${errorOpen ? " auth-error-slot--open" : ""}`}
                onTransitionEnd={onErrorSlotTransitionEnd}
              >
                <div className="auth-error-slot-inner">
                  {shownError ? (
                    <FormError
                      title={shownErrorTitle}
                      className={`auth-form-error${shownLockUntilMs != null ? " auth-form-error--lock" : ""}`}
                    >
                      {lockBody}
                    </FormError>
                  ) : null}
                </div>
              </div>
              <button
                type="submit"
                className={`auth-submit${submitting ? " auth-submit--loading" : ""}`}
                disabled={formDisabled}
              >
                {submitting ? (
                  <>
                    <span className="auth-submit-spinner" aria-hidden="true" />
                    <span className="auth-submit-label">Unlocking…</span>
                  </>
                ) : (
                  <span className="auth-submit-label">Unlock</span>
                )}
              </button>
              <button
                type="button"
                className="idle-lock-signout"
                disabled={submitting}
                onClick={() => void logout()}
              >
                Sign out
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
