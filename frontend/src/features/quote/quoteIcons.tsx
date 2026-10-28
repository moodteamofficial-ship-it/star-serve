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
      strokeWidth="1.6"
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

export function IconPackage(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M12 3 20 7.5v9L12 21l-8-4.5v-9L12 3Z" />
      <path d="M12 12 20 7.5M12 12v9M12 12 4 7.5" />
    </IconBase>
  );
}

export function IconUser(props: IconProps) {
  return (
    <IconBase {...props}>
      <circle cx="12" cy="8" r="3.25" />
      <path d="M5.5 19.5c1.6-3 4-4.5 6.5-4.5s4.9 1.5 6.5 4.5" />
    </IconBase>
  );
}

export function IconCar(props: IconProps) {
  return (
    <IconBase data-icon="car" {...props}>
      <path d="M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9C18.7 10.6 16 10 16 10s-1.3-1.4-2.2-2.3c-.5-.4-1.1-.7-1.8-.7H5c-.6 0-1.1.4-1.4.9l-1.4 2.9A3.7 3.7 0 0 0 2 12v4c0 .6.4 1 1 1h2" />
      <circle cx="7" cy="17" r="2" />
      <path d="M9 17h6" />
      <circle cx="17" cy="17" r="2" />
    </IconBase>
  );
}

export function IconWallet(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M3.5 8.5A2.5 2.5 0 0 1 6 6h12.5A1.5 1.5 0 0 1 20 7.5V9" />
      <rect x="3.5" y="9" width="17" height="10" rx="2" />
      <circle cx="16.5" cy="14" r="1.25" fill="currentColor" stroke="none" />
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

export function IconCheck(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="m5 12.5 4.5 4.5L19 7.5" />
    </IconBase>
  );
}

export function IconChevron(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="m9 6 6 6-6 6" />
    </IconBase>
  );
}

export function IconBus(props: IconProps) {
  return (
    <IconBase {...props}>
      <rect x="5" y="3.5" width="14" height="14" rx="2.5" />
      <path d="M5 10.5h14M8 17.5v2M16 17.5v2M8 13.5h.01M16 13.5h.01" />
    </IconBase>
  );
}

export function IconTruck(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M3 7.5h10v9H3z" />
      <path d="M13 11.5h4.5L20 14.5v2H13v-5Z" />
      <circle cx="7" cy="17.5" r="1.75" />
      <circle cx="16.5" cy="17.5" r="1.75" />
    </IconBase>
  );
}

export function IconMotorcycle(props: IconProps) {
  return (
    <IconBase data-icon="motorcycle" {...props}>
      <path d="M2 16a3 3 0 1 0 6 0a3 3 0 1 0-6 0m14 0a3 3 0 1 0 6 0a3 3 0 1 0-6 0m-8.5-2h5l4-4H6m1.5 4l4-4" />
      <path d="M13 6h2l1.5 3 2 4" />
    </IconBase>
  );
}

export function IconTaxi(props: IconProps) {
  return (
    <IconBase data-icon="taxi" {...props}>
      <path d="M10 2h4" />
      <path d="m21 8-2 2-1.5-3.7A2 2 0 0 0 15.646 5H8.4a2 2 0 0 0-1.903 1.257L5 10 3 8" />
      <path d="M7 14h.01" />
      <path d="M17 14h.01" />
      <rect width="18" height="8" x="3" y="10" rx="2" />
      <path d="M5 18v2" />
      <path d="M19 18v2" />
    </IconBase>
  );
}

export function IconPrivateHire(props: IconProps) {
  return (
    <IconBase data-icon="private-hire" {...props}>
      <path d="m21 8-2 2-1.5-3.7A2 2 0 0 0 15.646 5H8.4a2 2 0 0 0-1.903 1.257L5 10 3 8" />
      <path d="M7 14h.01" />
      <path d="M17 14h.01" />
      <rect width="18" height="8" x="3" y="10" rx="2" />
      <path d="M5 18v2" />
      <path d="M19 18v2" />
    </IconBase>
  );
}

export function IconTukTuk(props: IconProps) {
  return (
    <IconBase data-icon="tuk-tuk" {...props}>
      {/* Tall dome canopy — distinctive tuk tuk roof */}
      <path d="M2.8 15.5V9.5C2.8 6.2 5.4 3.8 9 3.8h3.6c2.9 0 4.9 1.9 4.9 4.7v2.2" />
      {/* Motorcycle nose / cowling */}
      <path d="M17.5 10.7h2.4c.8 0 1.5.7 1.5 1.5v3.3h-5.2" />
      {/* Cabin floor + open side window belt */}
      <path d="M2.8 15.5h12.4" />
      <path d="M2.8 10.7h14.7" />
      {/* Driver / passenger pillar */}
      <path d="M11.2 3.8v11.7" />
      {/* Handlebars */}
      <path d="M20.6 10.7 22.2 8.6" />
      <path d="M19.6 13h2.6" />
      {/* Rear + front wheels */}
      <circle cx="7" cy="17.3" r="1.9" />
      <circle cx="18.8" cy="17.3" r="1.9" />
    </IconBase>
  );
}

export function IconLayers(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="m12 4 8 4.5-8 4.5-8-4.5L12 4Z" />
      <path d="m4 13.5 8 4.5 8-4.5" />
      <path d="m4 17 8 4.5 8-4.5" />
    </IconBase>
  );
}

const CATEGORY_ICON_MAP: Array<{ match: RegExp; Icon: (props: IconProps) => JSX.Element }> = [
  { match: /private\s*hire/i, Icon: IconPrivateHire },
  { match: /taxi|cab/i, Icon: IconTaxi },
  { match: /tuk\s*tuk|tuktuk/i, Icon: IconTukTuk },
  { match: /psv|bus|matatu/i, Icon: IconBus },
  { match: /commercial|truck|lorry|goods/i, Icon: IconTruck },
  { match: /motor\s*cycle|motorcycle|bike|boda/i, Icon: IconMotorcycle },
  { match: /car|motor/i, Icon: IconCar },
];

export function categoryIcon(category: string) {
  const found = CATEGORY_ICON_MAP.find((row) => row.match.test(category));
  return found?.Icon ?? IconLayers;
}
