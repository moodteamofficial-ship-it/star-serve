import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, Outlet, useLocation } from "react-router-dom";
import { useTheme } from "@/app/providers/ThemeProvider";
import { publicAsset } from "@/app/router/basePath";
import { IconMoon, IconSun } from "@/components/ui/icons";
import { MarketingInstallDock } from "@/features/marketing/MarketingInstallDock";
import { MarketingNavSkeleton } from "@/features/marketing/MarketingSkeletons";
import { isExternalMarketingLink, resolveMarketingLink } from "@/features/marketing/resolveLink";
import { websiteApi } from "@/services/website/websiteApi";
import "./marketing.css";

type NavItemData = { label: string; kind: string; value: string };

function navButtonClass(kind: string): string | null {
  if (kind === "quote") return "welcome-action welcome-action--primary";
  if (kind === "agent_register") return "welcome-action welcome-action--ghost";
  return null;
}

function normalizePath(path: string): string {
  const cleaned = path.split("?")[0].split("#")[0].trim() || "/";
  if (cleaned === "/") return "/";
  return cleaned.replace(/\/+$/, "") || "/";
}

function isActiveNavPath(pathname: string, href: string): boolean {
  const current = normalizePath(pathname);
  const target = normalizePath(href);
  if (target === "/") return current === "/";
  return current === target || current.startsWith(`${target}/`);
}

function NavItem({ label, kind, value, onNavigate }: NavItemData & { onNavigate?: () => void }) {
  const location = useLocation();
  const href = resolveMarketingLink(kind, value);
  const external = isExternalMarketingLink(kind);
  const btnClass = navButtonClass(kind);
  const active = !external && !btnClass && isActiveNavPath(location.pathname, href);
  const className = [
    btnClass ?? "mkt-nav-link",
    active ? "is-active" : "",
  ]
    .filter(Boolean)
    .join(" ");

  const close = () => onNavigate?.();

  if (external) {
    return (
      <a className={className} href={href} onClick={close}>
        {label}
      </a>
    );
  }
  return (
    <Link
      className={className}
      to={href}
      onClick={close}
      aria-current={active ? "page" : undefined}
    >
      {label}
    </Link>
  );
}

function NavList({
  items,
  className,
  onNavigate,
}: {
  items: NavItemData[];
  className: string;
  onNavigate?: () => void;
}) {
  return (
    <nav className={className} aria-label="Primary">
      {items.map((item) => (
        <NavItem key={`${item.label}-${item.value}`} {...item} onNavigate={onNavigate} />
      ))}
    </nav>
  );
}

export function MarketingLayout() {
  const { theme, toggleTheme } = useTheme();
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["website", "bootstrap"],
    queryFn: async () => (await websiteApi.bootstrap()).data,
    staleTime: 5 * 60_000,
    gcTime: 30 * 60_000,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });

  const header = data?.navigation?.header ?? [];
  const outletContext = {
    bootstrap: data,
    bootstrapLoading: isLoading,
    bootstrapError: isError,
  };

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    document.body.style.overflow = menuOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [menuOpen]);

  const closeMenu = () => setMenuOpen(false);

  return (
    <div className="mkt-shell">
      <header className={`mkt-header${scrolled ? " is-scrolled" : ""}`}>
        <div className="mkt-header-inner">
          <Link to="/" className="mkt-brand" onClick={closeMenu}>
            <img src={publicAsset("star-serve-logo.png")} alt="Star Serve Insurance Agency" />
          </Link>
          {isLoading ? <MarketingNavSkeleton /> : null}
          {!isLoading && header.length > 0 ? (
            <NavList items={header} className="mkt-nav mkt-nav--desktop" />
          ) : null}
          <div className="mkt-header-tools">
            <button
              type="button"
              className="mkt-theme-btn"
              onClick={toggleTheme}
              aria-label={theme === "light" ? "Switch to dark mode" : "Switch to light mode"}
            >
              {theme === "light" ? <IconMoon /> : <IconSun />}
            </button>
            <button
              type="button"
              className="mkt-nav-toggle"
              aria-expanded={menuOpen}
              aria-controls="mkt-mobile-nav"
              onClick={() => setMenuOpen((open) => !open)}
            >
              {menuOpen ? "Close" : "Menu"}
            </button>
          </div>
        </div>
        {!isLoading && header.length > 0 ? (
          <div id="mkt-mobile-nav" className={`mkt-nav-mobile${menuOpen ? " is-open" : ""}`}>
            <NavList items={header} className="mkt-nav" onNavigate={closeMenu} />
          </div>
        ) : null}
        {!isLoading && header.length === 0 ? (
          <p className="mkt-banner mkt-banner--warn">Navigation unavailable</p>
        ) : null}
      </header>
      {isError ? (
        <p className="mkt-banner mkt-banner--warn">
          We could not load site content. Please try again shortly.
        </p>
      ) : null}
      <Outlet context={outletContext} />
      <footer className="mkt-footer">
        <p>© {new Date().getFullYear()} Star Serve Insurance Agency</p>
        {data?.settings?.location ? <p>{data.settings.location}</p> : null}
      </footer>
      <MarketingInstallDock />
    </div>
  );
}
