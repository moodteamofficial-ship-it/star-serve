import { useEffect, useState } from "react";

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

function publicPath(file: string): string {
  const base = String(import.meta.env.BASE_URL || "/");
  const normalized = file.replace(/^\/+/, "");
  if (base === "/") return `/${normalized}`;
  return `${base.replace(/\/+$/, "")}/${normalized}`;
}

function isIos(): boolean {
  if (typeof navigator === "undefined") return false;
  return /iphone|ipad|ipod/i.test(navigator.userAgent);
}

function isStandalone(): boolean {
  if (typeof window === "undefined") return false;
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    ("standalone" in navigator &&
      Boolean((navigator as Navigator & { standalone?: boolean }).standalone))
  );
}

export function useMarketingPwa() {
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [installed, setInstalled] = useState(isStandalone());
  const [iosHint, setIosHint] = useState(false);

  useEffect(() => {
    const manifest = document.createElement("link");
    manifest.rel = "manifest";
    manifest.href = publicPath("site.webmanifest");
    document.head.appendChild(manifest);

    const theme = document.createElement("meta");
    theme.name = "theme-color";
    theme.content = "#30a82c";
    document.head.appendChild(theme);

    const apple = document.createElement("meta");
    apple.name = "apple-mobile-web-app-capable";
    apple.content = "yes";
    document.head.appendChild(apple);

    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register(publicPath("sw.js")).catch(() => {
        /* Local HTTP or unsupported browsers may reject registration. */
      });
    }

    const onPrompt = (event: Event) => {
      event.preventDefault();
      setDeferredPrompt(event as BeforeInstallPromptEvent);
    };
    const onInstalled = () => {
      setInstalled(true);
      setDeferredPrompt(null);
    };

    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    setInstalled(isStandalone());
    setIosHint(isIos() && !isStandalone());

    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
      manifest.remove();
      theme.remove();
      apple.remove();
    };
  }, []);

  async function installApp(): Promise<"accepted" | "dismissed" | "unavailable" | "ios"> {
    if (installed) return "accepted";
    if (iosHint) return "ios";
    if (!deferredPrompt) return "unavailable";
    await deferredPrompt.prompt();
    const choice = await deferredPrompt.userChoice;
    setDeferredPrompt(null);
    if (choice.outcome === "accepted") setInstalled(true);
    return choice.outcome;
  }

  return {
    canInstall: Boolean(deferredPrompt) && !installed,
    installed,
    iosHint,
    installApp,
  };
}

export function marketingPublicSiteUrl(): string {
  const fromEnv = (import.meta.env.VITE_MARKETING_PUBLIC_URL || "").trim().replace(/\/$/, "");
  if (fromEnv) return fromEnv;
  if (typeof window !== "undefined") {
    const host = window.location.hostname;
    if (host === "localhost" || host === "127.0.0.1") {
      return "https://www.starserveinsuranceagency.com";
    }
    if (host.includes("starserveinsuranceagency.com")) {
      return window.location.origin;
    }
  }
  return "https://www.starserveinsuranceagency.com";
}
