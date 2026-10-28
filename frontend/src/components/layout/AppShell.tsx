import { useEffect, useMemo, useRef, useState, type ComponentType, type ReactNode, type SVGProps } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/app/providers/AuthProvider";
import { useTheme } from "@/app/providers/ThemeProvider";
import { EnvSwitcher } from "@/components/layout/EnvSwitcher";
import { mediaSrc } from "@/services/media/mediaSrc";
import {
  IconBell,
  IconBox,
  IconBuilding,
  IconCertificate,
  IconClaim,
  IconChart,
  IconChevronDown,
  IconFileText,
  IconGrid,
  IconHome,
  IconLayers,
  IconMoon,
  IconPayments,
  IconPhone,
  IconPlus,
  IconSettings,
  IconShield,
  IconSliders,
  IconSun,
  IconUsers,
} from "@/components/ui/icons";

type IconComponent = ComponentType<SVGProps<SVGSVGElement> & { title?: string }>;

type NavLeaf = {
  to: string;
  label: string;
  icon: IconComponent;
  permission?: string;
  /** Show if the user has any of these permissions (OR). */
  anyPermission?: string[];
  end?: boolean;
};

type NavGroup = {
  id: string;
  label: string;
  icon: IconComponent;
  children: NavLeaf[];
};

type NavEntry =
  | { kind: "link"; item: NavLeaf }
  | { kind: "group"; group: NavGroup };

const NAV: NavEntry[] = [
  { kind: "link", item: { to: "/app", label: "Home", icon: IconHome, end: true } },
  { kind: "link", item: { to: "/app/quote", label: "Quote", icon: IconPlus, permission: "proposal:create" } },
  {
    kind: "group",
    group: {
      id: "portfolio",
      label: "Portfolio",
      icon: IconLayers,
      children: [
        { to: "/app/customers", label: "Customers", icon: IconUsers, permission: "customer:read" },
        { to: "/app/intermediaries", label: "Agents", icon: IconUsers, permission: "agent:read" },
        { to: "/app/products", label: "Products", icon: IconBox, permission: "product:read" },
        { to: "/app/proposals", label: "Proposals", icon: IconFileText, permission: "proposal:read" },
        { to: "/app/policies", label: "Policies", icon: IconShield, permission: "policy:read" },
        {
          to: "/app/certificates",
          label: "Certificates",
          icon: IconCertificate,
          permission: "certificate:read",
        },
        { to: "/app/claims", label: "Claims", icon: IconClaim, permission: "claim:read" },
      ],
    },
  },
  {
    kind: "group",
    group: {
      id: "finance",
      label: "Finance",
      icon: IconPayments,
      children: [
        { to: "/app/payments", label: "Payments", icon: IconPayments, permission: "payment:read" },
        {
          to: "/app/commission-ledger",
          label: "Commission ledger",
          icon: IconPayments,
          anyPermission: [
            "commission:read",
            "commission:manage",
            "commission:payout",
            "settings:manage",
            "tenant:manage",
          ],
        },
        { to: "/app/reports", label: "Reports", icon: IconChart, permission: "reports:read" },
      ],
    },
  },
  {
    kind: "group",
    group: {
      id: "admin",
      label: "Admin",
      icon: IconSliders,
      children: [
        {
          to: "/app/users",
          label: "Users",
          icon: IconUsers,
          anyPermission: ["user:read", "user:create", "user:update", "user:disable"],
        },
        { to: "/app/branches", label: "Branches", icon: IconBuilding, permission: "branch:manage" },
        { to: "/app/notifications", label: "Alerts", icon: IconBell, permission: "notification:read" },
        {
          to: "/app/ussd",
          label: "USSD",
          icon: IconPhone,
          anyPermission: ["ussd:read", "ussd:manage", "ussd:analytics"],
        },
        { to: "/app/audit", label: "Audit", icon: IconFileText, permission: "audit:read" },
        {
          to: "/app/settings",
          label: "Configuration",
          icon: IconSettings,
          anyPermission: [
            "platform:config:manage",
            "platform:tenant:manage",
            "role:manage",
            "tenant:manage",
            "settings:manage",
          ],
        },
        { to: "/app/platform", label: "Platform", icon: IconGrid, permission: "platform:tenant:manage" },
      ],
    },
  },
];

function filterLeaf(item: NavLeaf, hasPermission: (code: string) => boolean) {
  if (item.anyPermission?.length) {
    return item.anyPermission.some((code) => hasPermission(code));
  }
  return !item.permission || hasPermission(item.permission);
}

function pathActive(pathname: string, to: string, end?: boolean) {
  if (end) return pathname === to;
  return pathname === to || pathname.startsWith(`${to}/`);
}

const OPEN_DELAY_MS = 75;
const CLOSE_DELAY_MS = 180;
const SWITCH_DELAY_MS = 40;

type MenuController = {
  openId: string | null;
  requestOpen: (id: string) => void;
  requestClose: (id: string) => void;
  toggle: (id: string) => void;
  closeAll: () => void;
};

function useMenuController(): MenuController {
  const [openId, setOpenId] = useState<string | null>(null);
  const openIdRef = useRef<string | null>(null);
  const openTimer = useRef<number | null>(null);
  const closeTimer = useRef<number | null>(null);

  useEffect(() => {
    openIdRef.current = openId;
  }, [openId]);

  function clearTimers() {
    if (openTimer.current != null) {
      window.clearTimeout(openTimer.current);
      openTimer.current = null;
    }
    if (closeTimer.current != null) {
      window.clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  }

  useEffect(() => () => clearTimers(), []);

  useEffect(() => {
    if (!openId) return;

    function onPointerDown(event: MouseEvent) {
      const target = event.target as HTMLElement | null;
      if (target?.closest(".topbar-dd, .topbar-profile")) return;
      clearTimers();
      setOpenId(null);
    }

    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        clearTimers();
        setOpenId(null);
      }
    }

    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [openId]);

  function requestOpen(id: string) {
    clearTimers();
    const current = openIdRef.current;
    if (current === id) return;
    // Switching between menus: quick handoff so panels never stack
    const delay = current ? SWITCH_DELAY_MS : OPEN_DELAY_MS;
    openTimer.current = window.setTimeout(() => {
      setOpenId(id);
      openTimer.current = null;
    }, delay);
  }

  function requestClose(id: string) {
    clearTimers();
    closeTimer.current = window.setTimeout(() => {
      setOpenId((prev) => (prev === id ? null : prev));
      closeTimer.current = null;
    }, CLOSE_DELAY_MS);
  }

  function toggle(id: string) {
    clearTimers();
    setOpenId((prev) => (prev === id ? null : id));
  }

  function closeAll() {
    clearTimers();
    setOpenId(null);
  }

  return { openId, requestOpen, requestClose, toggle, closeAll };
}

function NavDropdown({
  id,
  label,
  icon: Icon,
  children,
  active,
  open,
  onRequestOpen,
  onRequestClose,
  onToggle,
  onNavigate,
}: {
  id: string;
  label: string;
  icon: IconComponent;
  children: NavLeaf[];
  active: boolean;
  open: boolean;
  onRequestOpen: (id: string) => void;
  onRequestClose: (id: string) => void;
  onToggle: (id: string) => void;
  onNavigate: () => void;
}) {
  return (
    <div
      className={`topbar-dd${open ? " is-open" : ""}${active ? " is-active" : ""}`}
      onMouseEnter={() => onRequestOpen(id)}
      onMouseLeave={() => onRequestClose(id)}
    >
      <button
        type="button"
        className="topbar-dd-trigger"
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => onToggle(id)}
        onFocus={() => onRequestOpen(id)}
      >
        <Icon className="topbar-nav-icon" />
        <span>{label}</span>
        <IconChevronDown />
      </button>
      <div className="topbar-dd-menu" role="menu" aria-hidden={!open}>
        {children.map((item) => {
          const ItemIcon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              tabIndex={open ? 0 : -1}
              role="menuitem"
              className={({ isActive }) => `topbar-dd-item${isActive ? " is-selected" : ""}`}
              onClick={onNavigate}
            >
              <ItemIcon className="topbar-nav-icon" />
              <span>{item.label}</span>
            </NavLink>
          );
        })}
      </div>
    </div>
  );
}

function HeaderIconButton({
  label,
  onClick,
  active,
  badge,
  children,
}: {
  label: string;
  onClick: () => void;
  active?: boolean;
  badge?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      className={`topbar-icon-btn${active ? " is-active" : ""}`}
      aria-label={label}
      title={label}
      onClick={onClick}
    >
      {children}
      {badge ? <span className="topbar-icon-badge" aria-hidden="true" /> : null}
    </button>
  );
}

function ProfileMenu({
  name,
  email,
  initials,
  avatarUrl,
  open,
  onRequestOpen,
  onRequestClose,
  onToggle,
  onLogout,
}: {
  name: string;
  email: string;
  initials: string;
  avatarUrl?: string | null;
  open: boolean;
  onRequestOpen: (id: string) => void;
  onRequestClose: (id: string) => void;
  onToggle: (id: string) => void;
  onLogout: () => void;
}) {
  const [imgFailed, setImgFailed] = useState(false);
  const id = "profile";
  const photoSrc = mediaSrc(avatarUrl);
  const showPhoto = Boolean(photoSrc) && !imgFailed;

  useEffect(() => {
    setImgFailed(false);
  }, [photoSrc]);

  return (
    <div
      className={`topbar-profile${open ? " is-open" : ""}`}
      onMouseEnter={() => onRequestOpen(id)}
      onMouseLeave={() => onRequestClose(id)}
    >
      <button
        type="button"
        className="topbar-profile-trigger"
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label="Account menu"
        onClick={() => onToggle(id)}
        onFocus={() => onRequestOpen(id)}
      >
        {showPhoto ? (
          <img
            src={photoSrc!}
            alt=""
            className="topbar-avatar topbar-avatar--photo"
            onError={() => setImgFailed(true)}
          />
        ) : (
          <span className="topbar-avatar" aria-hidden="true">
            {initials}
          </span>
        )}
      </button>

      <div className="topbar-profile-menu" role="menu" aria-hidden={!open}>
        <div className="topbar-profile-meta">
          {showPhoto ? (
            <img src={photoSrc!} alt="" className="topbar-avatar topbar-avatar--photo topbar-avatar--lg" />
          ) : (
            <span className="topbar-avatar topbar-avatar--lg" aria-hidden="true">
              {initials}
            </span>
          )}
          <div className="topbar-profile-copy">
            <strong>{name}</strong>
            <em>{email}</em>
          </div>
        </div>
        <div className="topbar-profile-env">
          <EnvSwitcher open={open} />
        </div>
        <button
          type="button"
          className="topbar-profile-action"
          role="menuitem"
          tabIndex={open ? 0 : -1}
          onClick={onLogout}
        >
          Sign out
        </button>
      </div>
    </div>
  );
}

export function AppShell() {
  const { user, logout, hasPermission } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const location = useLocation();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const menus = useMenuController();

  useEffect(() => {
    menus.closeAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- close on route change only
  }, [location.pathname]);

  const entries = useMemo(() => {
    return NAV.map((entry) => {
      if (entry.kind === "link") {
        return filterLeaf(entry.item, hasPermission) ? entry : null;
      }
      const children = entry.group.children
        .filter((child) => filterLeaf(child, hasPermission))
        .filter((child, index, arr) => arr.findIndex((c) => c.to === child.to) === index);
      if (!children.length) return null;
      return { kind: "group" as const, group: { ...entry.group, children } };
    }).filter(Boolean) as NavEntry[];
  }, [hasPermission]);

  const initials = useMemo(() => {
    const source = user?.full_name || user?.email || "SS";
    const parts = source.trim().split(/\s+/);
    if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
    return source.slice(0, 2).toUpperCase();
  }, [user]);

  const avatarUrl = user?.avatar_url ?? null;
  const canNotifications = hasPermission("notification:read");

  function closeMenu() {
    setMenuOpen(false);
    menus.closeAll();
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar-inner">
          <div className="topbar-brand">
            <Link to="/app" className="welcome-brand-link" aria-label="Go to dashboard home">
              <img
                src={`${import.meta.env.BASE_URL}star-serve-logo.png?v=3`}
                alt="Star Serve Insurance Agency"
                className="brand-logo brand-logo--topbar"
              />
            </Link>
          </div>

          <nav className="topbar-nav" aria-label="Primary">
            {entries.map((entry) => {
              if (entry.kind === "link") {
                const Icon = entry.item.icon;
                return (
                  <NavLink
                    key={entry.item.to}
                    to={entry.item.to}
                    end={entry.item.end}
                    onClick={closeMenu}
                    onMouseEnter={menus.closeAll}
                  >
                    <Icon className="topbar-nav-icon" />
                    <span>{entry.item.label}</span>
                  </NavLink>
                );
              }
              const active = entry.group.children.some((child) =>
                pathActive(location.pathname, child.to, child.end),
              );
              return (
                <NavDropdown
                  key={entry.group.id}
                  id={entry.group.id}
                  label={entry.group.label}
                  icon={entry.group.icon}
                  children={entry.group.children}
                  active={active}
                  open={menus.openId === entry.group.id}
                  onRequestOpen={menus.requestOpen}
                  onRequestClose={menus.requestClose}
                  onToggle={menus.toggle}
                  onNavigate={closeMenu}
                />
              );
            })}
          </nav>

          <div className="topbar-actions">
            {canNotifications ? (
              <HeaderIconButton
                label="Notifications"
                badge
                onClick={() => {
                  menus.closeAll();
                  navigate("/app/notifications");
                }}
              >
                <IconBell />
              </HeaderIconButton>
            ) : null}

            <HeaderIconButton
              label={theme === "light" ? "Switch to dark mode" : "Switch to light mode"}
              onClick={() => {
                menus.closeAll();
                toggleTheme();
              }}
            >
              {theme === "light" ? <IconMoon /> : <IconSun />}
            </HeaderIconButton>

            <button
              type="button"
              className="topbar-menu-btn"
              aria-expanded={menuOpen}
              aria-controls="mobile-nav"
              onClick={() => setMenuOpen((v) => !v)}
            >
              {menuOpen ? "Close" : "Menu"}
            </button>

            <ProfileMenu
              name={user?.full_name || user?.email || "Account"}
              email={user?.email || ""}
              initials={initials}
              avatarUrl={avatarUrl}
              open={menus.openId === "profile"}
              onRequestOpen={menus.requestOpen}
              onRequestClose={menus.requestClose}
              onToggle={menus.toggle}
              onLogout={() => {
                menus.closeAll();
                void logout();
              }}
            />
          </div>
        </div>

        {menuOpen ? (
          <nav id="mobile-nav" className="topbar-mobile-nav" aria-label="Mobile">
            {entries.map((entry) => {
              if (entry.kind === "link") {
                const Icon = entry.item.icon;
                return (
                  <NavLink
                    key={entry.item.to}
                    to={entry.item.to}
                    end={entry.item.end}
                    onClick={closeMenu}
                  >
                    <Icon className="topbar-nav-icon" />
                    <span>{entry.item.label}</span>
                  </NavLink>
                );
              }
              return (
                <div key={entry.group.id} className="topbar-mobile-group">
                  <p className="topbar-mobile-label">{entry.group.label}</p>
                  {entry.group.children.map((item) => {
                    const Icon = item.icon;
                    return (
                      <NavLink key={item.to} to={item.to} end={item.end} onClick={closeMenu}>
                        <Icon className="topbar-nav-icon" />
                        <span>{item.label}</span>
                      </NavLink>
                    );
                  })}
                </div>
              );
            })}
          </nav>
        ) : null}
      </header>

      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
