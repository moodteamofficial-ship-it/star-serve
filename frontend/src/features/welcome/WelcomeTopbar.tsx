import { useEffect, useState } from "react";
import { useTheme } from "@/app/providers/ThemeProvider";
import { IconMoon, IconSun } from "@/components/ui/icons";
import { WelcomeMenu } from "@/features/welcome/WelcomeMenu";

const MAIN_SITE_URL = "https://www.starserveinsuranceagency.com/";

type WelcomeTopbarProps = {
  onReportClaim: () => void;
  onFollowUp: () => void;
};

/** Public-site header shared by the welcome and agent registration pages. */
export function WelcomeTopbar({ onReportClaim, onFollowUp }: WelcomeTopbarProps) {
  const { theme, toggleTheme } = useTheme();
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => {
      setScrolled(window.scrollY > 12);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header className={`topbar welcome-topbar${scrolled ? " is-scrolled" : ""}`}>
      <div className="topbar-inner welcome-topbar-inner">
        <div className="topbar-brand">
          <a
            href={MAIN_SITE_URL}
            className="welcome-brand-link"
            aria-label="Star Serve Insurance Agency website"
          >
            <img
              src={`${import.meta.env.BASE_URL}star-serve-logo.png?v=3`}
              alt="Star Serve Insurance Agency"
              className="brand-logo brand-logo--topbar"
            />
          </a>
        </div>
        <div className="topbar-actions">
          <button
            type="button"
            className="topbar-icon-btn welcome-theme-btn"
            onClick={toggleTheme}
            aria-label={theme === "light" ? "Switch to dark mode" : "Switch to light mode"}
          >
            {theme === "light" ? <IconMoon /> : <IconSun />}
          </button>
          <WelcomeMenu onReportClaim={onReportClaim} onFollowUp={onFollowUp} />
        </div>
      </div>
    </header>
  );
}
