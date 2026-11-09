import QRCode from "qrcode";
import { useEffect, useState } from "react";
import { IconDownload } from "@/components/ui/icons";
import { marketingPublicSiteUrl, useMarketingPwa } from "@/features/marketing/useMarketingPwa";

type Panel = "closed" | "install" | "qr";

export function MarketingInstallDock() {
  const { canInstall, installed, iosHint, installApp } = useMarketingPwa();
  const [panel, setPanel] = useState<Panel>("closed");
  const [qrDataUrl, setQrDataUrl] = useState<string>("");
  const [installNote, setInstallNote] = useState<string>("");
  const siteUrl = marketingPublicSiteUrl();

  useEffect(() => {
    let cancelled = false;
    QRCode.toDataURL(siteUrl, {
      width: 220,
      margin: 1,
      color: { dark: "#1b1464", light: "#ffffff" },
      errorCorrectionLevel: "M",
    })
      .then((url) => {
        if (!cancelled) setQrDataUrl(url);
      })
      .catch(() => {
        if (!cancelled) setQrDataUrl("");
      });
    return () => {
      cancelled = true;
    };
  }, [siteUrl]);

  async function onInstall() {
    const result = await installApp();
    if (result === "ios") {
      setInstallNote("On iPhone, tap Share, then Add to Home Screen.");
      setPanel("install");
      return;
    }
    if (result === "unavailable") {
      setInstallNote("Use your browser menu to install this site, or open it on Chrome or Edge.");
      setPanel("install");
      return;
    }
    if (result === "accepted") {
      setInstallNote("Star Serve is ready on your device.");
      setPanel("install");
    }
  }

  function toggle(next: Panel) {
    setPanel((current) => (current === next ? "closed" : next));
    if (next !== "install") setInstallNote("");
  }

  return (
    <div className="mkt-dock" aria-live="polite">
      {panel !== "closed" ? (
        <div className="mkt-dock-panel" role="dialog" aria-label={panel === "qr" ? "Site QR code" : "Install app"}>
          <div className="mkt-dock-panel-head">
            <p className="mkt-eyebrow">{panel === "qr" ? "Scan to open" : "Get the app"}</p>
            <button type="button" className="mkt-dock-close" onClick={() => setPanel("closed")} aria-label="Close">
              Close
            </button>
          </div>

          {panel === "qr" ? (
            <div className="mkt-dock-qr">
              {qrDataUrl ? (
                <img src={qrDataUrl} alt={`QR code for ${siteUrl}`} width={180} height={180} />
              ) : (
                <div className="mkt-dock-qr-fallback">Preparing QR code…</div>
              )}
              <p className="mkt-dock-copy">Scan to open Star Serve Insurance Agency on your phone.</p>
              <a className="mkt-dock-url" href={siteUrl} target="_blank" rel="noopener noreferrer">
                {siteUrl.replace(/^https?:\/\//, "")}
              </a>
            </div>
          ) : (
            <div className="mkt-dock-install">
              <p className="mkt-dock-copy">
                {installed
                  ? "Star Serve is already installed on this device."
                  : iosHint
                    ? "Add Star Serve to your Home Screen for quick access to cover and support."
                    : "Install Star Serve for a fast, app like experience on this device."}
              </p>
              {!installed ? (
                <button type="button" className="mkt-btn mkt-btn-primary mkt-dock-install-btn" onClick={onInstall}>
                  {canInstall || iosHint ? "Install Star Serve" : "How to install"}
                </button>
              ) : null}
              {installNote ? <p className="mkt-dock-note">{installNote}</p> : null}
            </div>
          )}
        </div>
      ) : null}

      <div className="mkt-dock-actions">
        <button
          type="button"
          className={`mkt-dock-fab${panel === "qr" ? " is-active" : ""}`}
          aria-expanded={panel === "qr"}
          aria-label="Show site QR code"
          onClick={() => toggle("qr")}
        >
          <span className="mkt-dock-fab-qr" aria-hidden="true" />
          <span className="mkt-dock-fab-label">QR</span>
        </button>
        <button
          type="button"
          className={`mkt-dock-fab mkt-dock-fab--primary${panel === "install" ? " is-active" : ""}`}
          aria-expanded={panel === "install"}
          aria-label="Install Star Serve app"
          onClick={() => {
            if (canInstall) {
              void onInstall();
              return;
            }
            toggle("install");
          }}
        >
          <IconDownload />
          <span className="mkt-dock-fab-label">{installed ? "App" : "Install"}</span>
        </button>
      </div>
    </div>
  );
}
