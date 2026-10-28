import type { ReactNode, SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { title?: string };

function IconBase({ title, children, ...props }: IconProps & { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="1em"
      height="1em"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden={title ? undefined : true}
      role={title ? "img" : undefined}
      {...props}
    >
      {title ? <title>{title}</title> : null}
      {children}
    </svg>
  );
}

export function IconAlert(props: IconProps) {
  return (
    <IconBase {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8v5" />
      <circle cx="12" cy="16.25" r="0.85" fill="currentColor" stroke="none" />
    </IconBase>
  );
}

export function IconCheckCircle(props: IconProps) {
  return (
    <IconBase {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="m8.2 12.2 2.5 2.5 5.1-5.2" />
    </IconBase>
  );
}

export function IconWarning(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M12 3.8 21 19.2H3L12 3.8Z" />
      <path d="M12 9.2v4.4" />
      <circle cx="12" cy="16.35" r="0.85" fill="currentColor" stroke="none" />
    </IconBase>
  );
}

export function IconXCircle(props: IconProps) {
  return (
    <IconBase {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="m9 9 6 6M15 9l-6 6" />
    </IconBase>
  );
}

export function IconSearch(props: IconProps) {
  return (
    <IconBase {...props}>
      <circle cx="11" cy="11" r="6.5" />
      <path d="m16.2 16.2 3.3 3.3" />
    </IconBase>
  );
}

export function IconEye(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M2.6 12s3.5-6.4 9.4-6.4 9.4 6.4 9.4 6.4-3.5 6.4-9.4 6.4S2.6 12 2.6 12Z" />
      <circle cx="12" cy="12" r="2.5" />
    </IconBase>
  );
}

export function IconEyeOff(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M3.2 4.2 19.8 20.8" />
      <path d="M10 6.2A8.8 8.8 0 0 1 12 5.6c5.9 0 9.4 6.4 9.4 6.4a16 16 0 0 1-3.4 3.9" />
      <path d="M6.7 7.9A15.2 15.2 0 0 0 2.6 12s3.5 6.4 9.4 6.4c1.3 0 2.6-.3 3.8-.8" />
      <path d="M10.1 10.2a2.5 2.5 0 0 0 3.7 3.4" />
    </IconBase>
  );
}

export function IconBell(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M6.2 16.5h11.6M12 3.5a5.5 5.5 0 0 1 5.5 5.5v2.2c0 .9.3 1.8.9 2.5l.8.9H4.8l.8-.9c.6-.7.9-1.6.9-2.5V9A5.5 5.5 0 0 1 12 3.5Z" />
      <path d="M10 16.5a2 2 0 0 0 4 0" />
    </IconBase>
  );
}

export function IconSun(props: IconProps) {
  return (
    <IconBase {...props}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2.8v2.2M12 19v2.2M2.8 12h2.2M19 12h2.2M5.1 5.1l1.6 1.6M17.3 17.3l1.6 1.6M18.9 5.1l-1.6 1.6M6.7 17.3l-1.6 1.6" />
    </IconBase>
  );
}

export function IconMoon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M19.5 13.4A7.5 7.5 0 0 1 10.6 4.5 7.6 7.6 0 1 0 19.5 13.4Z" />
    </IconBase>
  );
}

export function IconCalendar(props: IconProps) {
  return (
    <IconBase {...props}>
      <rect x="3.5" y="5" width="17" height="15.5" rx="2" />
      <path d="M8 3.5v3M16 3.5v3M3.5 10h17" />
    </IconBase>
  );
}

export function IconChevronDown(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="m6 9 6 6 6-6" />
    </IconBase>
  );
}

export function IconChevronLeft(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="m15 6-6 6 6 6" />
    </IconBase>
  );
}

export function IconChevronRight(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="m9 6 6 6-6 6" />
    </IconBase>
  );
}

export function IconPlus(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M12 5v14M5 12h14" />
    </IconBase>
  );
}

/** Quote / new proposal — clipboard with plus. */
export function IconQuote(props: IconProps) {
  return (
    <IconBase {...props}>
      <rect x="7" y="4.5" width="10" height="3" rx="1" />
      <path d="M9 5.2H8A2.5 2.5 0 0 0 5.5 7.7v10.8A2.5 2.5 0 0 0 8 21h8a2.5 2.5 0 0 0 2.5-2.5V7.7A2.5 2.5 0 0 0 16 5.2h-1" />
      <path d="M12 11v5.5M9.25 13.75h5.5" />
    </IconBase>
  );
}

/** Portfolio / book of business — stacked layers. */
export function IconLayers(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="m12 3.6 8 4.2-8 4.2-8-4.2 8-4.2Z" />
      <path d="m4 12.2 8 4.2 8-4.2" />
      <path d="m4 16.4 8 4.2 8-4.2" />
    </IconBase>
  );
}

/** Finance — overlapping coins (currency-agnostic). */
export function IconBanknote(props: IconProps) {
  return (
    <IconBase {...props}>
      <circle cx="9.2" cy="9.2" r="5.7" />
      <path d="M14.6 8.4a5.7 5.7 0 1 1-6.2 6.2" />
      <path d="M9.2 6.6v5.2M7.5 8.4h3.4" />
    </IconBase>
  );
}

/** Admin — horizontal sliders. */
export function IconSliders(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M4 7h8M16 7h4" />
      <path d="M14 5v4" />
      <path d="M4 12h4M12 12h8" />
      <path d="M8 10v4" />
      <path d="M4 17h10M18 17h2" />
      <path d="M16 15v4" />
    </IconBase>
  );
}

export function IconPayments(props: IconProps) {
  return (
    <IconBase {...props}>
      <rect x="2.8" y="5.5" width="18.4" height="13" rx="2.4" />
      <path d="M2.8 10h18.4" />
      <path d="M7 15.2h3.6" />
      <path d="M13.2 15.2h3.8" />
    </IconBase>
  );
}

export function IconWallet(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M4 8.2A2.7 2.7 0 0 1 6.7 5.5h10.6A2.7 2.7 0 0 1 20 8.2v8.1A2.7 2.7 0 0 1 17.3 19H6.7A2.7 2.7 0 0 1 4 16.3V8.2Z" />
      <path d="M15.2 12.5H20v-2.4h-4.8a1.2 1.2 0 1 0 0 2.4Z" />
      <circle cx="16.6" cy="12.5" r="0.7" fill="currentColor" stroke="none" />
    </IconBase>
  );
}

export function IconTrend(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M4 16.5 9.5 11l3.5 3.5L20 7.5" />
      <path d="M14.5 7.5H20V13" />
    </IconBase>
  );
}

export function IconUser(props: IconProps) {
  return (
    <IconBase {...props}>
      <circle cx="12" cy="8" r="3.25" />
      <path d="M5.5 18.25c1.15-2.85 3.35-4.25 6.5-4.25s5.35 1.4 6.5 4.25" />
    </IconBase>
  );
}

export function IconUsers(props: IconProps) {
  return (
    <IconBase {...props}>
      <circle cx="9" cy="8" r="3" />
      <circle cx="16.5" cy="9" r="2.4" />
      <path d="M3.5 18.5c.8-2.8 2.9-4.2 5.5-4.2s4.7 1.4 5.5 4.2" />
      <path d="M14.2 14.8c1.7-.4 3.4.2 4.3 2.2" />
    </IconBase>
  );
}

export function IconFileText(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M7 3.5h7.5L19 8v12.5a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4.5a1 1 0 0 1 1-1Z" />
      <path d="M14 3.5V8h4.5M9 12h6M9 15.5h6" />
    </IconBase>
  );
}

export function IconDownload(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M12 4v10.5" />
      <path d="m8.2 11.2 3.8 3.8 3.8-3.8" />
      <path d="M5.5 18.5h13" />
    </IconBase>
  );
}

export function IconCertificate(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M8 3.5h8a2 2 0 0 1 2 2v13l-3-1.5-3 1.5-3-1.5-3 1.5v-13a2 2 0 0 1 2-2Z" />
      <path d="M9 8.5h6M9 12h6" />
    </IconBase>
  );
}

export function IconHome(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M4 10.2 12 3.6l8 6.6v9.2a1.6 1.6 0 0 1-1.6 1.6h-3.9v-6.2h-4.9v6.2H5.6A1.6 1.6 0 0 1 4 19.4V10.2Z" />
    </IconBase>
  );
}

export function IconBuilding(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M5 20V5.5A1.5 1.5 0 0 1 6.5 4h7A1.5 1.5 0 0 1 15 5.5V20" />
      <path d="M15 9h2.5A1.5 1.5 0 0 1 19 10.5V20" />
      <path d="M3.5 20h17" />
      <path d="M8 8h2M8 11.5h2M8 15h2" />
    </IconBase>
  );
}

export function IconBriefcase(props: IconProps) {
  return (
    <IconBase {...props}>
      <rect x="3.5" y="7.8" width="17" height="11.7" rx="2.2" />
      <path d="M9.2 7.8V6.3A1.8 1.8 0 0 1 11 4.5h2a1.8 1.8 0 0 1 1.8 1.8v1.5" />
      <path d="M3.5 12.4h17" />
      <path d="M10.5 12.4v1.4a1.5 1.5 0 0 0 3 0v-1.4" />
    </IconBase>
  );
}

export function IconBox(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M12 3.4 20 7.8v8.4L12 20.6 4 16.2V7.8L12 3.4Z" />
      <path d="M12 12.1 20 7.8M12 12.1 4 7.8M12 12.1v8.5" />
    </IconBase>
  );
}

export function IconChart(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M4 19.2h16" />
      <path d="M7.2 16.2V11" />
      <path d="M12 16.2V7.5" />
      <path d="M16.8 16.2v-3.2" />
    </IconBase>
  );
}

export function IconSettings(props: IconProps) {
  return (
    <IconBase {...props}>
      <circle cx="12" cy="12" r="3.1" />
      <path d="M12 3.4v2.1M12 18.5v2.1M4.9 6.4l1.5 1.5M17.6 16.1l1.5 1.5M3.4 12h2.1M18.5 12h2.1M4.9 17.6l1.5-1.5M17.6 7.9l1.5-1.5" />
    </IconBase>
  );
}

export function IconPencil(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M13.4 5.6 18.4 10.6" />
      <path d="M5.2 16.4 15.1 6.5a1.6 1.6 0 0 1 2.3 0l.1.1a1.6 1.6 0 0 1 0 2.3L7.6 18.8 4 19.9l1.2-3.5Z" />
    </IconBase>
  );
}

export function IconShield(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M12 3.4 19.2 6.2v5.1c0 4.5-3 7.5-7.2 9.1-4.2-1.6-7.2-4.6-7.2-9.1V6.2L12 3.4Z" />
      <path d="m9.2 11.8 1.9 1.9 3.7-3.7" />
    </IconBase>
  );
}

export function IconPower(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M12 3.5v8" />
      <path d="M7.2 6.8a6.5 6.5 0 1 0 9.6 0" />
    </IconBase>
  );
}

export function IconLogin(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M10 3.5H6.8A2.3 2.3 0 0 0 4.5 5.8v12.4A2.3 2.3 0 0 0 6.8 20.5H10" />
      <path d="M10.5 12H20" />
      <path d="m16.2 8.2 3.8 3.8-3.8 3.8" />
    </IconBase>
  );
}

export function IconClaim(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M8 4.5h5.2L16.5 7.8V19a1.5 1.5 0 0 1-1.5 1.5H8A1.5 1.5 0 0 1 6.5 19V6A1.5 1.5 0 0 1 8 4.5Z" />
      <path d="M13 4.6V8h3.3" />
      <path d="M9 12h5.5M9 15.2h3.8" />
    </IconBase>
  );
}

export function IconFollowUp(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M4.8 11.2a7.2 7.2 0 0 1 12.1-4.4" />
      <path d="M16.9 4.8v3.2h-3.2" />
      <path d="M19.2 12.8a7.2 7.2 0 0 1-12.1 4.4" />
      <path d="M7.1 19.2v-3.2h3.2" />
    </IconBase>
  );
}

export function IconList(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M9.6 7h10" />
      <path d="M9.6 12h10" />
      <path d="M9.6 17h10" />
      <circle cx="5.3" cy="7" r="1.15" />
      <circle cx="5.3" cy="12" r="1.15" />
      <circle cx="5.3" cy="17" r="1.15" />
    </IconBase>
  );
}

export function IconNote(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M7 4.4h7.4L18.6 8.6V19a1.6 1.6 0 0 1-1.6 1.6H7A1.6 1.6 0 0 1 5.4 19V6A1.6 1.6 0 0 1 7 4.4Z" />
      <path d="M14.2 4.5V9h4.3" />
      <path d="M8.6 12.2h6.4M8.6 15.4h4.6" />
    </IconBase>
  );
}

export function IconGlobe(props: IconProps) {
  return (
    <IconBase {...props}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M3.5 12h17M12 3.5c2.4 2.6 3.6 5.5 3.6 8.5s-1.2 5.9-3.6 8.5c-2.4-2.6-3.6-5.5-3.6-8.5s1.2-5.9 3.6-8.5Z" />
    </IconBase>
  );
}

export function IconBadge(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M12 3.2 14.2 4.4l2.5-.4.9 2.3 2.3.9-.4 2.5L21 12l-1.2 2.2.4 2.5-2.3.9-.9 2.3-2.5-.4L12 20.8l-2.2-1.2-2.5.4-.9-2.3-2.3-.9.4-2.5L3 12l1.2-2.2-.4-2.5 2.3-.9.9-2.3 2.5.4L12 3.2Z" />
      <path d="m9.2 12 1.8 1.8 3.8-3.8" />
    </IconBase>
  );
}

export function IconGrid(props: IconProps) {
  return (
    <IconBase {...props}>
      <rect x="4" y="4" width="6.5" height="6.5" rx="1.2" />
      <rect x="13.5" y="4" width="6.5" height="6.5" rx="1.2" />
      <rect x="4" y="13.5" width="6.5" height="6.5" rx="1.2" />
      <rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.2" />
    </IconBase>
  );
}

export function IconPhone(props: IconProps) {
  const { title, ...rest } = props;
  return (
    <svg
      viewBox="0 0 24 24"
      width="1em"
      height="1em"
      fill="currentColor"
      aria-hidden={title ? undefined : true}
      role={title ? "img" : undefined}
      {...rest}
    >
      {title ? <title>{title}</title> : null}
      <path d="M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z" />
    </svg>
  );
}

export function IconMail(props: IconProps) {
  const { title, ...rest } = props;
  return (
    <svg
      viewBox="0 0 24 24"
      width="1em"
      height="1em"
      fill="currentColor"
      aria-hidden={title ? undefined : true}
      role={title ? "img" : undefined}
      {...rest}
    >
      {title ? <title>{title}</title> : null}
      <path d="M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2Zm-.4 4.25-7.07 4.42c-.32.2-.74.2-1.06 0L4.4 8.25a.75.75 0 1 1 .8-1.27L12 11.15l6.8-4.17a.75.75 0 1 1 .8 1.27Z" />
    </svg>
  );
}

export function IconWhatsApp(props: IconProps) {
  const { title, ...rest } = props;
  return (
    <svg
      viewBox="0 0 24 24"
      width="1em"
      height="1em"
      fill="currentColor"
      aria-hidden={title ? undefined : true}
      role={title ? "img" : undefined}
      {...rest}
    >
      {title ? <title>{title}</title> : null}
      <path d="M12.04 2C6.58 2 2.15 6.37 2.15 11.75c0 2.07.66 3.99 1.79 5.56L2 22l4.86-1.87a10.1 10.1 0 0 0 5.18 1.42h.01c5.46 0 9.89-4.37 9.89-9.75S17.5 2 12.04 2Zm5.77 13.81c-.24.67-1.39 1.24-1.92 1.32-.49.07-1.12.1-1.81-.11-.42-.13-.96-.31-1.65-.61-2.9-1.25-4.79-4.16-4.93-4.35-.14-.19-1.15-1.53-1.15-2.92 0-1.39.73-2.07.99-2.35.26-.28.57-.35.76-.35h.55c.18 0 .42-.07.65.5.24.58.81 2 .88 2.14.07.14.12.31.02.5-.1.19-.14.31-.28.48-.14.17-.3.37-.42.5-.14.14-.28.29-.12.57.16.28.71 1.17 1.53 1.89 1.05.93 1.94 1.22 2.22 1.36.28.14.44.12.61-.07.16-.19.71-.83.9-1.11.19-.28.38-.23.65-.14.26.1 1.68.79 1.97.94.28.14.47.21.54.33.07.12.07.71-.17 1.38Z" />
    </svg>
  );
}
