import { useEffect } from "react";
import { useLocation } from "react-router-dom";

/** Smoothly return to the top whenever a page route first opens. */
export function ScrollToTop() {
  const { pathname } = useLocation();

  useEffect(() => {
    const reduceMotion =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    window.scrollTo({
      top: 0,
      left: 0,
      behavior: reduceMotion ? "auto" : "smooth",
    });
  }, [pathname]);

  return null;
}
