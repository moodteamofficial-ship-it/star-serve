import { useEffect, useRef, useState } from "react";
import {
  isRequestActive,
  subscribeRequestActivity,
} from "@/services/api/requestActivity";

const MIN_VISIBLE_MS = 280;
const FADE_OUT_MS = 420;

type Phase = "hidden" | "in" | "out";

/**
 * Fixed top shuttle bar — same motion as the sign-in screen.
 * Activates for mutating backend requests (create/update/delete) and explicit holds — not reads.
 */
export function TopLoader() {
  const [phase, setPhase] = useState<Phase>(() => (isRequestActive() ? "in" : "hidden"));
  const shownAtRef = useRef(0);
  const hideTimerRef = useRef<number | null>(null);
  const fadeTimerRef = useRef<number | null>(null);
  const phaseRef = useRef(phase);

  useEffect(() => {
    phaseRef.current = phase;
  }, [phase]);

  useEffect(() => {
    function clearHideTimer() {
      if (hideTimerRef.current != null) {
        window.clearTimeout(hideTimerRef.current);
        hideTimerRef.current = null;
      }
    }

    function clearFadeTimer() {
      if (fadeTimerRef.current != null) {
        window.clearTimeout(fadeTimerRef.current);
        fadeTimerRef.current = null;
      }
    }

    function show() {
      clearHideTimer();
      clearFadeTimer();
      if (phaseRef.current !== "in") shownAtRef.current = Date.now();
      setPhase("in");
    }

    function beginHide() {
      const elapsed = Date.now() - shownAtRef.current;
      const wait = Math.max(0, MIN_VISIBLE_MS - elapsed);
      clearHideTimer();
      clearFadeTimer();
      hideTimerRef.current = window.setTimeout(() => {
        setPhase("out");
        hideTimerRef.current = null;
        fadeTimerRef.current = window.setTimeout(() => {
          setPhase("hidden");
          fadeTimerRef.current = null;
        }, FADE_OUT_MS);
      }, wait);
    }

    function sync() {
      if (isRequestActive()) show();
      else if (phaseRef.current === "in") beginHide();
    }

    sync();
    return subscribeRequestActivity(sync);
  }, []);

  useEffect(() => {
    return () => {
      if (hideTimerRef.current != null) window.clearTimeout(hideTimerRef.current);
      if (fadeTimerRef.current != null) window.clearTimeout(fadeTimerRef.current);
    };
  }, []);

  const busy = phase === "in";

  return (
    <div
      className={`top-loader top-loader--${phase}`}
      aria-hidden={!busy}
      aria-busy={busy}
    >
      <div className="top-loader-bar" />
    </div>
  );
}
