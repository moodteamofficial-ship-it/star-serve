import { useEffect, useState, type FormEvent, type ReactNode, type TransitionEvent } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";
import { useAuth } from "@/app/providers/AuthProvider";
import { useTheme } from "@/app/providers/ThemeProvider";
import { FormError } from "@/components/ui/FormError";
import { IconChevronLeft, IconEye, IconEyeOff, IconMoon, IconSun } from "@/components/ui/icons";
import { ApiError } from "@/services/api/client";
import { holdTopLoader } from "@/services/api/requestActivity";
import { formatCountdown, isLoginLockedError, parseLockUntilMs } from "@/services/auth/loginLock";

const SIGN_IN_MIN_MS = 400;
const OPEN_SKELETON_MS = 1000;

function wait(ms: number) {
  return new Promise<void>((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

/** Only allow in-app relative paths after sign-in. */
function safeNextPath(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) return "/app";
  if (!raw.startsWith("/app")) return "/app";
  return raw;
}

export function LoginPage() {
  const { user, login } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const [searchParams] = useSearchParams();
  const nextPath = safeNextPath(searchParams.get("next"));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorTitle, setErrorTitle] = useState("Sign-in failed");
  const [lockUntilMs, setLockUntilMs] = useState<number | null>(null);
  const [nowMs, setNowMs] = useState(() => Date.now());
  /** Keeps error markup mounted while the card collapses. */
  const [shownError, setShownError] = useState<string | null>(null);
  const [shownErrorTitle, setShownErrorTitle] = useState("Sign-in failed");
  const [shownLockUntilMs, setShownLockUntilMs] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);
  /** Keep form mounted while top bar runs; only navigate after min duration. */
  const [holdRedirect, setHoldRedirect] = useState(false);
  const [openReady, setOpenReady] = useState(false);

  const errorOpen = Boolean(error);
  const lockActive = shownLockUntilMs != null && shownLockUntilMs > nowMs;
  const remainingSeconds =
    shownLockUntilMs != null ? Math.max(0, (shownLockUntilMs - nowMs) / 1000) : 0;

  useEffect(() => {
    const t = window.setTimeout(() => setOpenReady(true), OPEN_SKELETON_MS);
    return () => window.clearTimeout(t);
  }, []);

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

  if (user && !holdRedirect) return <Navigate to={nextPath} replace />;

  function onErrorSlotTransitionEnd(e: TransitionEvent<HTMLDivElement>) {
    if (e.target !== e.currentTarget) return;
    if (!error) {
      setShownError(null);
      setShownLockUntilMs(null);
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (submitting) return;

    setSubmitting(true);
    setError(null);
    setErrorTitle("Sign-in failed");
    setLockUntilMs(null);
    setHoldRedirect(true);

    const started = Date.now();
    const releaseLoader = holdTopLoader();
    let loginError: string | null = null;
    let loginErrorTitle = "Sign-in failed";
    let nextLockUntil: number | null = null;

    try {
      await login(email, password);
    } catch (err) {
      if (err instanceof ApiError) {
        loginError = err.message;
        if (isLoginLockedError(err)) {
          loginErrorTitle = "Temporarily locked";
          nextLockUntil = parseLockUntilMs(err);
          loginError = "Too many failed sign-in attempts.";
        }
      } else {
        loginError = "Unable to sign in";
      }
    }

    const remaining = SIGN_IN_MIN_MS - (Date.now() - started);
    if (remaining > 0) await wait(remaining);
    releaseLoader();

    if (loginError) {
      setErrorTitle(loginErrorTitle);
      setLockUntilMs(nextLockUntil);
      setError(loginError);
      setHoldRedirect(false);
      setSubmitting(false);
      return;
    }

    setHoldRedirect(false);
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
          <span className="auth-lock-retry">You can try signing in again.</span>
        )}
      </span>
    );
  }

  return (
    <div className="auth-shell" aria-busy={submitting || !openReady}>
      <Link
        to="/"
        className="auth-back"
        aria-label="Back to home"
        tabIndex={submitting ? -1 : 0}
        aria-disabled={submitting || undefined}
        onClick={(e) => {
          if (submitting) e.preventDefault();
        }}
      >
        <IconChevronLeft />
      </Link>
      <Link to="/" className="brand-logo-link brand-logo-link--auth">
        <img
          src={`${import.meta.env.BASE_URL}star-serve-logo.png?v=3`}
          alt="Star Serve Insurance Agency"
          className="brand-logo brand-logo--auth"
        />
      </Link>
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
        <div className={`auth-panel-inner${openReady ? " auth-panel-inner--ready" : ""}`}>
          {!openReady ? (
            <>
              <div className="auth-copy auth-copy--skeleton" aria-hidden="true">
                <span className="skeleton-block auth-skel-title" />
                <span className="skeleton-block auth-skel-lede" />
              </div>
              <div className="auth-card" aria-hidden="true">
                <div className="auth-form auth-form--skeleton">
                  <div className="auth-skel-field">
                    <span className="skeleton-block auth-skel-caption" />
                    <span className="skeleton-block auth-skel-input" />
                  </div>
                  <div className="auth-skel-field">
                    <span className="skeleton-block auth-skel-caption auth-skel-caption--wide" />
                    <span className="skeleton-block auth-skel-input" />
                  </div>
                  <span className="skeleton-block auth-skel-submit" />
                </div>
              </div>
            </>
          ) : (
            <>
              <div className="auth-copy">
                <h1>Sign in</h1>
                <p className="lede">Secure insurance operations for your agency.</p>
              </div>
              <div className={`auth-card${errorOpen ? " auth-card--error-open" : ""}`}>
                <form onSubmit={onSubmit} className="auth-form">
                  <label>
                    <span className="field-caption">Email</span>
                    <input
                      type="email"
                      autoComplete="username"
                      placeholder="you@agency.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      required
                      disabled={submitting}
                    />
                  </label>
                  <label>
                    <span className="field-caption">Password</span>
                    <div className="auth-password-field">
                      <input
                        type={showPassword ? "text" : "password"}
                        autoComplete="current-password"
                        placeholder="Enter your password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        required
                        minLength={8}
                        disabled={submitting}
                      />
                      <button
                        type="button"
                        className="auth-password-toggle"
                        onClick={() => setShowPassword((open) => !open)}
                        disabled={submitting}
                        aria-label={showPassword ? "Hide password" : "Show password"}
                        aria-pressed={showPassword}
                      >
                        {showPassword ? <IconEyeOff /> : <IconEye />}
                      </button>
                    </div>
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
                    disabled={submitting}
                  >
                    {submitting ? (
                      <>
                        <span className="auth-submit-spinner" aria-hidden="true" />
                        <span className="auth-submit-label">Signing in…</span>
                      </>
                    ) : (
                      <span className="auth-submit-label">Sign in</span>
                    )}
                  </button>
                </form>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
