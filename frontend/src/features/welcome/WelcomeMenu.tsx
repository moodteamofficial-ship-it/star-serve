import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  IconBox,
  IconChevronDown,
  IconClaim,
  IconFollowUp,
  IconGrid,
  IconLogin,
  IconUsers,
} from "@/components/ui/icons";

type WelcomeMenuProps = {
  onReportClaim: () => void;
  onFollowUp: () => void;
};

type MenuItem = {
  key: string;
  label: string;
  hint: string;
  icon: ReactNode;
  primary?: boolean;
  onSelect: () => void;
};

/** Single header button that groups the guest actions into a dropdown. */
export function WelcomeMenu({ onReportClaim, onFollowUp }: WelcomeMenuProps) {
  const navigate = useNavigate();
  const onAgentPage = useLocation().pathname.replace(/\/+$/, "").endsWith("/register-agent");
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const menuId = useId();

  const items: MenuItem[] = [
    {
      key: "claim",
      label: "Report claim",
      hint: "Tell us what happened",
      icon: <IconClaim />,
      onSelect: onReportClaim,
    },
    {
      key: "followup",
      label: "Follow up",
      hint: "Check on an existing claim",
      icon: <IconFollowUp />,
      onSelect: onFollowUp,
    },
    onAgentPage
      ? {
          key: "products",
          label: "Back to products",
          hint: "Get a quote for your cover",
          icon: <IconBox />,
          onSelect: () => navigate("/"),
        }
      : {
          key: "agent",
          label: "Become an agent",
          hint: "Apply to sell with us",
          icon: <IconUsers />,
          onSelect: () => navigate("/register-agent"),
        },
    {
      key: "signin",
      label: "Sign in",
      hint: "Agents and staff",
      icon: <IconLogin />,
      primary: true,
      onSelect: () => navigate("/login"),
    },
  ];

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKey);
    itemRefs.current[0]?.focus();
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function select(item: MenuItem) {
    setOpen(false);
    item.onSelect();
  }

  function onMenuKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const nodes = itemRefs.current.filter(Boolean) as HTMLButtonElement[];
    const index = nodes.indexOf(document.activeElement as HTMLButtonElement);
    const move = (next: number) => {
      event.preventDefault();
      nodes[(next + nodes.length) % nodes.length]?.focus();
    };
    if (event.key === "ArrowDown") move(index + 1);
    else if (event.key === "ArrowUp") move(index - 1);
    else if (event.key === "Home") move(0);
    else if (event.key === "End") move(nodes.length - 1);
    else if (event.key === "Tab") setOpen(false);
  }

  return (
    <div ref={rootRef} className={`welcome-menu${open ? " is-open" : ""}`}>
      <button
        ref={triggerRef}
        type="button"
        className="welcome-action welcome-action--primary welcome-menu-trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((value) => !value)}
      >
        <IconGrid />
        <span className="welcome-menu-trigger-label">Menu</span>
        <IconChevronDown className="welcome-menu-chevron" />
      </button>
      {open ? (
        <div
          id={menuId}
          role="menu"
          aria-label="Welcome menu"
          className="welcome-menu-panel"
          onKeyDown={onMenuKeyDown}
        >
          {items.map((item, index) => (
            <button
              key={item.key}
              ref={(node) => {
                itemRefs.current[index] = node;
              }}
              type="button"
              role="menuitem"
              className={`welcome-menu-item${item.primary ? " welcome-menu-item--primary" : ""}`}
              onClick={() => select(item)}
            >
              <span className="welcome-menu-item-icon" aria-hidden="true">
                {item.icon}
              </span>
              <span className="welcome-menu-item-copy">
                <strong>{item.label}</strong>
                <em>{item.hint}</em>
              </span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
