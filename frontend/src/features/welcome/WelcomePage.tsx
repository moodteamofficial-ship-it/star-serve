import { useState } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "@/app/providers/AuthProvider";
import { QuoteWizardPage, type GuestHeroCopy } from "@/features/quote/QuoteWizardPage";
import { WelcomeClaimModals } from "@/features/welcome/WelcomeClaimModals";
import { WelcomeTopbar } from "@/features/welcome/WelcomeTopbar";

/** Public first screen — quote, guest claim, and guest follow-up. */
export function WelcomePage() {
  const { user } = useAuth();
  const [claimMode, setClaimMode] = useState<"claim" | "followup" | null>(null);
  const [heroCopy, setHeroCopy] = useState<GuestHeroCopy | null>(null);

  if (user) return <Navigate to="/app" replace />;

  return (
    <div className="welcome-shell">
      <WelcomeTopbar
        onReportClaim={() => setClaimMode("claim")}
        onFollowUp={() => setClaimMode("followup")}
      />
      <main className="content welcome-content">
        <header className="welcome-hero">
          <h1
            className={
              heroCopy?.title
                ? "welcome-hero-title welcome-hero-title--compact"
                : "welcome-hero-title"
            }
          >
            {heroCopy?.title ?? (
              <>
                Just <span className="welcome-hero-accent">one</span> touch
              </>
            )}
          </h1>
          {heroCopy?.subtitle ? (
            <p className="welcome-hero-subtitle">{heroCopy.subtitle}</p>
          ) : heroCopy ? null : (
            <p className="welcome-hero-subtitle">
              Pick a class, see your premium live, and get covered with your certificate included.
            </p>
          )}
        </header>
        <QuoteWizardPage guest onHeadlineChange={setHeroCopy} />
      </main>
      <WelcomeClaimModals mode={claimMode} onClose={() => setClaimMode(null)} />
    </div>
  );
}
