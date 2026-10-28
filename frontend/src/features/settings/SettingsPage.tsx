import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ComponentType,
  type ReactNode,
  type SVGProps,
} from "react";
import { createPortal } from "react-dom";
import { useAuth } from "@/app/providers/AuthProvider";
import { PhoneField } from "@/components/ui/PhoneField";
import { Select } from "@/components/ui/Select";
import {
  IconBadge,
  IconBell,
  IconBox,
  IconBriefcase,
  IconCheckCircle,
  IconGlobe,
  IconPayments,
  IconPower,
  IconShield,
  IconUsers,
  IconWarning,
  IconXCircle,
} from "@/components/ui/icons";
import { DEFAULT_PHONE_COUNTRY, fromE164, toE164 } from "@/components/ui/phoneCountries";
import { commissionApi } from "@/services/commissions/commissionApi";
import { tenantApi } from "@/services/tenants/tenantApi";
import {
  referenceApi,
  rolesApi,
  systemConfigApi,
  type RoleRow,
} from "@/services/systemConfig/systemConfigApi";

type TabId =
  | "system"
  | "services"
  | "channels"
  | "countries"
  | "roles"
  | "agency"
  | "commissions";
type TabIcon = ComponentType<SVGProps<SVGSVGElement>>;

const TAB_LABELS: Record<TabId, string> = {
  system: "System",
  services: "Services",
  channels: "Channels",
  countries: "Countries",
  roles: "Roles",
  agency: "Agency",
  commissions: "Commissions",
};

const TAB_ICONS: Record<TabId, TabIcon> = {
  system: IconPower,
  services: IconBox,
  channels: IconBell,
  countries: IconGlobe,
  roles: IconUsers,
  agency: IconBriefcase,
  commissions: IconPayments,
};

const SERVICE_META: Record<string, { title: string; subtitle: string }> = {
  quoting: {
    title: "Quoting",
    subtitle: "Create, price, and manage insurance quotes",
  },
  payments: {
    title: "Payments",
    subtitle: "Collect premiums and process payment flows",
  },
  notifications: {
    title: "Notifications",
    subtitle: "Send system and customer notifications",
  },
  issuance: {
    title: "Issuance",
    subtitle: "Issue policies from approved quotes",
  },
  reports: {
    title: "Reports",
    subtitle: "Generate operational and compliance reports",
  },
  certificates: {
    title: "Certificates",
    subtitle: "Produce and download policy certificates",
  },
  claims: {
    title: "Claims",
    subtitle: "Open, vet, approve, and settle insurance claims",
  },
};

const CHANNEL_META: Record<string, { title: string; subtitle: string }> = {
  SMS: {
    title: "SMS",
    subtitle: "Text messages to customer phone numbers",
  },
  EMAIL: {
    title: "Email",
    subtitle: "Transactional and alert emails",
  },
  WHATSAPP: {
    title: "WhatsApp",
    subtitle: "WhatsApp Business messaging",
  },
  PUSH: {
    title: "Push",
    subtitle: "In-app and device push alerts",
  },
};

type ConfigNotice = {
  id: number;
  kind: "ok" | "warn" | "error";
  title: string;
  subtitle: string;
};

let noticeSeq = 0;
const noticeListeners = new Set<(notice: ConfigNotice) => void>();

function publishConfigNotice(kind: ConfigNotice["kind"], title: string, subtitle: string) {
  const notice: ConfigNotice = { id: ++noticeSeq, kind, title, subtitle };
  noticeListeners.forEach((listener) => listener(notice));
}

function notifyConfigSuccess(title: string, subtitle: string) {
  publishConfigNotice("ok", title, subtitle);
}

function notifyConfigWarning(title: string, subtitle: string) {
  publishConfigNotice("warn", title, subtitle);
}

function notifyConfigError(error: unknown, title = "Could not save") {
  const subtitle =
    error instanceof Error && error.message.trim()
      ? error.message
      : "Something went wrong. Please try again.";
  publishConfigNotice("error", title, subtitle);
}

function ConfigToastIcon({ kind }: { kind: ConfigNotice["kind"] }) {
  if (kind === "ok") return <IconCheckCircle className="config-toast-float-glyph" />;
  if (kind === "warn") return <IconWarning className="config-toast-float-glyph" />;
  return <IconXCircle className="config-toast-float-glyph" />;
}

function ConfigToastHost() {
  const [toast, setToast] = useState<ConfigNotice | null>(null);
  const [leaving, setLeaving] = useState(false);
  const hideTimer = useRef<number | null>(null);
  const leaveTimer = useRef<number | null>(null);
  const remainingMs = useRef(6000);
  const startedAt = useRef(0);
  const hovered = useRef(false);

  function clearHideTimer() {
    if (hideTimer.current) {
      window.clearTimeout(hideTimer.current);
      hideTimer.current = null;
    }
  }

  function clearLeaveTimer() {
    if (leaveTimer.current) {
      window.clearTimeout(leaveTimer.current);
      leaveTimer.current = null;
    }
  }

  function beginExit() {
    if (hovered.current) return;
    clearHideTimer();
    setLeaving(true);
    clearLeaveTimer();
    leaveTimer.current = window.setTimeout(() => {
      setToast(null);
      setLeaving(false);
    }, 280);
  }

  function armHideTimer(ms: number) {
    clearHideTimer();
    remainingMs.current = ms;
    startedAt.current = Date.now();
    hideTimer.current = window.setTimeout(() => beginExit(), ms);
  }

  useEffect(() => {
    const onNotice = (notice: ConfigNotice) => {
      clearHideTimer();
      clearLeaveTimer();
      hovered.current = false;
      setLeaving(false);
      setToast(notice);
      armHideTimer(6000);
    };
    noticeListeners.add(onNotice);
    return () => {
      noticeListeners.delete(onNotice);
      clearHideTimer();
      clearLeaveTimer();
    };
  }, []);

  if (!toast || typeof document === "undefined") return null;

  return createPortal(
    <div
      className={`config-toast-float is-${toast.kind}${leaving ? " is-leaving" : ""}`}
      role="status"
      aria-live="polite"
      onMouseEnter={() => {
        hovered.current = true;
        if (hideTimer.current) {
          remainingMs.current = Math.max(0, remainingMs.current - (Date.now() - startedAt.current));
          clearHideTimer();
        }
      }}
      onMouseLeave={() => {
        hovered.current = false;
        armHideTimer(remainingMs.current > 0 ? remainingMs.current : 1800);
      }}
    >
      <span className="config-toast-float-accent" aria-hidden="true" />
      <div className="config-toast-float-body">
        <span className="config-toast-float-icon" aria-hidden="true">
          <ConfigToastIcon kind={toast.kind} />
        </span>
        <div className="config-toast-float-copy">
          <p className="config-toast-float-title">{toast.title}</p>
          <p className="config-toast-float-sub">{toast.subtitle}</p>
        </div>
      </div>
    </div>,
    document.body,
  );
}

export function SettingsPage() {
  const { hasPermission } = useAuth();
  const canPlatform =
    hasPermission("platform:config:manage") || hasPermission("platform:tenant:manage");
  const canConfigWrite =
    hasPermission("platform:config:manage") || hasPermission("platform:tenant:manage");
  const canRoles = hasPermission("role:manage");
  const canAgency = hasPermission("tenant:manage") || hasPermission("settings:manage");
  const canCommissions =
    hasPermission("commission:manage") ||
    hasPermission("commission:read") ||
    hasPermission("settings:manage") ||
    hasPermission("tenant:manage");
  const canCommissionWrite =
    hasPermission("commission:manage") || hasPermission("settings:manage");

  const tabs = useMemo(() => {
    const list: TabId[] = [];
    if (canPlatform) list.push("system", "services", "channels", "countries");
    if (canRoles) list.push("roles");
    if (canAgency) list.push("agency");
    if (canCommissions) list.push("commissions");
    return list;
  }, [canPlatform, canRoles, canAgency, canCommissions]);

  const [tab, setTab] = useState<TabId | null>(null);
  const active = tab && tabs.includes(tab) ? tab : (tabs[0] ?? null);

  if (!tabs.length) {
    return (
      <section className="config-page configuration-page">
        <h1 className="config-title">Configuration</h1>
        <p className="config-empty">You do not have permission to manage configuration.</p>
      </section>
    );
  }

  return (
    <section className="config-page configuration-page">
      <ConfigToastHost />
      <h1 className="config-title">Configuration</h1>

      <div className="config-shell">
        <nav className="config-rail" aria-label="Configuration sections">
          {tabs.map((id) => {
            const Icon = TAB_ICONS[id];
            return (
              <button
                key={id}
                type="button"
                className={`config-rail-item${active === id ? " is-active" : ""}`}
                aria-current={active === id ? "page" : undefined}
                onClick={() => setTab(id)}
              >
                <span className="config-rail-icon" aria-hidden="true">
                  <Icon />
                </span>
                <span className="config-rail-label">{TAB_LABELS[id]}</span>
              </button>
            );
          })}
        </nav>

        <div
          className={`config-stage${active === "system" || active === "services" || active === "channels" || active === "countries" || active === "agency" || active === "commissions" ? " config-stage--fill" : ""}`}
          key={active}
        >
          {active === "system" ? <SystemTab canWrite={canConfigWrite} /> : null}
          {active === "services" ? <ServicesTab canWrite={canConfigWrite} /> : null}
          {active === "channels" ? <ChannelsTab canWrite={canConfigWrite} /> : null}
          {active === "countries" ? <CountriesTab canWrite={canConfigWrite} /> : null}
          {active === "roles" ? <RolesTab /> : null}
          {active === "agency" ? <AgencyTab /> : null}
          {active === "commissions" ? (
            <CommissionsTab canWrite={canCommissionWrite} />
          ) : null}
        </div>
      </div>
    </section>
  );
}

function useSystemConfig() {
  return useQuery({
    queryKey: ["system-config"],
    queryFn: async () => (await systemConfigApi.snapshot()).data,
  });
}

function ConfigCard({
  children,
  footer,
  className = "",
}: {
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
}) {
  return (
    <div className={`config-card${className ? ` ${className}` : ""}`}>
      <div className="config-card-body">{children}</div>
      {footer ? <div className="config-card-footer">{footer}</div> : null}
    </div>
  );
}

function SaveFooter({
  reason,
  onReasonChange,
  onSave,
  saveLabel,
  disabled,
  pending,
  danger,
}: {
  reason: string;
  onReasonChange: (v: string) => void;
  onSave: () => void;
  saveLabel: string;
  disabled?: boolean;
  pending?: boolean;
  danger?: boolean;
}) {
  return (
    <>
      <input
        className="config-footer-input"
        value={reason}
        disabled={pending}
        onChange={(e) => onReasonChange(e.target.value)}
        placeholder="Reason for change"
        maxLength={512}
      />
      <button
        type="button"
        className={`config-btn${danger ? " config-btn--danger" : ""}`}
        disabled={pending || disabled}
        onClick={onSave}
      >
        {saveLabel}
      </button>
    </>
  );
}

function Switch({
  checked,
  disabled,
  onChange,
  label,
}: {
  checked: boolean;
  disabled?: boolean;
  onChange: (next: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      className={`config-switch${checked ? " is-on" : ""}`}
      disabled={disabled}
      onClick={() => onChange(!checked)}
    >
      <span className="config-switch-thumb" />
    </button>
  );
}

function ControlRow({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <div className="config-row">
      <div className="config-row-copy">
        <span className="config-row-label">{title}</span>
        {subtitle ? <span className="config-row-sub">{subtitle}</span> : null}
      </div>
      <div className="config-row-control">{children}</div>
    </div>
  );
}

function ConfigRowsSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div className="config-list" aria-busy="true">
      {Array.from({ length: count }, (_, index) => (
        <div key={`config-row-skeleton-${index}`} className="config-row config-row--skeleton">
          <div className="config-row-copy">
            <span className="skeleton-block skeleton-block--title" />
            <span className="skeleton-block skeleton-block--meta" />
          </div>
          <span className="skeleton-block config-skeleton-switch" />
        </div>
      ))}
    </div>
  );
}

function SystemTab({ canWrite }: { canWrite: boolean }) {
  const queryClient = useQueryClient();
  const config = useSystemConfig();
  const [reason, setReason] = useState("");
  const op = config.data?.operational;
  const enabled = op?.enabled === true;
  const reasonOk = reason.trim().length >= 3;
  const mutate = useMutation({
    mutationFn: (next: boolean) =>
      systemConfigApi.setOperational({
        enabled: next,
        reason: reason.trim(),
        expected_version: op?.version ?? 1,
      }),
    onSuccess: async (_data, next) => {
      setReason("");
      await queryClient.invalidateQueries({ queryKey: ["system-config"] });
      if (next) {
        notifyConfigSuccess(
          "Platform online",
          "The platform is live for all tenants.",
        );
      } else {
        notifyConfigWarning(
          "Platform offline",
          "Non-platform users can no longer access the platform.",
        );
      }
    },
    onError: (error) => notifyConfigError(error, "Could not update platform status"),
  });

  function requestToggle(next: boolean) {
    if (!canWrite || mutate.isPending || !reasonOk) return;
    if (!next && !window.confirm("Turn the platform off for non-platform users?")) return;
    mutate.mutate(next);
  }

  return (
    <div
      className={`config-system${config.isLoading ? " is-loading" : enabled ? " is-on" : " is-off"}`}
      aria-busy={config.isLoading || undefined}
    >
      <div className="config-system-main">
        <div className="config-system-status">
          {config.isLoading ? (
            <div className="config-system-hero config-system-hero--skeleton">
              <span className="skeleton-block config-skeleton-system-state" />
              <span className="skeleton-block config-skeleton-system-lead" />
            </div>
          ) : (
            <div className="config-system-hero">
              <div className={`config-system-headline${enabled ? " is-on" : " is-off"}`}>
                <span
                  className={`customers-status-badge config-system-status-badge customers-status-badge--${
                    enabled ? "active" : "inactive"
                  }`}
                >
                  <span className="customers-status-dot__mark" aria-hidden="true" />
                  {enabled ? "Online" : "Offline"}
                </span>
              </div>
              <p className="config-system-lead">
                {enabled
                  ? "The platform is live for all tenants."
                  : "The platform is offline for non-platform users."}
              </p>
              {op?.reason && !enabled ? (
                <p className="config-system-note">
                  <span className="customers-tag claims-agency-badge">{op.reason}</span>
                </p>
              ) : null}
            </div>
          )}
        </div>
      </div>

      {canWrite ? (
        <div className="config-system-footer">
          {config.isLoading ? (
            <>
              <span className="skeleton-block config-skeleton-system-input" />
              <div className="config-system-btns">
                <span className="skeleton-block config-skeleton-system-btn" />
                <span className="skeleton-block config-skeleton-system-btn" />
              </div>
            </>
          ) : (
            <>
              <input
                className="config-system-input"
                value={reason}
                disabled={mutate.isPending}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Reason for change"
                maxLength={512}
              />
              <div className="config-system-btns">
                <button
                  type="button"
                  className="config-system-btn config-system-btn--on"
                  disabled={mutate.isPending || !reasonOk || enabled}
                  onClick={() => requestToggle(true)}
                >
                  Turn on
                </button>
                <button
                  type="button"
                  className="config-system-btn config-system-btn--off"
                  disabled={mutate.isPending || !reasonOk || !enabled}
                  onClick={() => requestToggle(false)}
                >
                  Turn off
                </button>
              </div>
            </>
          )}
        </div>
      ) : (
        <div className="config-system-footer config-system-footer--readonly">
          <p className="config-muted">Read only</p>
        </div>
      )}
    </div>
  );
}

function ServicesTab({ canWrite }: { canWrite: boolean }) {
  const queryClient = useQueryClient();
  const config = useSystemConfig();
  const [draft, setDraft] = useState<Record<string, boolean>>({});
  const [reason, setReason] = useState("");
  const version = config.data?.services.version ?? 1;

  useEffect(() => {
    if (config.data?.services.services) setDraft({ ...config.data.services.services });
  }, [config.data]);

  const mutate = useMutation({
    mutationFn: () =>
      systemConfigApi.setServices({
        services: draft,
        reason: reason.trim(),
        expected_version: version,
      }),
    onSuccess: async () => {
      setReason("");
      await queryClient.invalidateQueries({ queryKey: ["system-config"] });
      notifyConfigSuccess("Services updated", "Platform service availability has been saved.");
    },
    onError: (error) => notifyConfigError(error, "Could not update services"),
  });

  return (
    <ConfigCard
      className="config-card--scene"
      footer={
        canWrite ? (
          <SaveFooter
            reason={reason}
            onReasonChange={setReason}
            onSave={() => mutate.mutate()}
            saveLabel="Save"
            disabled={reason.trim().length < 3}
            pending={mutate.isPending}
          />
        ) : (
          <p className="config-muted">Read only</p>
        )
      }
    >
      <header className="config-scene-header">
        <h2 className="config-scene-title">Services</h2>
        <p className="config-scene-lead">
          Enable or disable platform capabilities for all tenants.
        </p>
      </header>
      {config.isLoading ? (
        <ConfigRowsSkeleton count={Object.keys(SERVICE_META).length} />
      ) : (
        <div className="config-list">
          {Object.entries(SERVICE_META).map(([key, meta]) => (
            <ControlRow key={key} title={meta.title} subtitle={meta.subtitle}>
              <Switch
                label={meta.title}
                checked={Boolean(draft[key])}
                disabled={!canWrite || mutate.isPending}
                onChange={(next) => setDraft((prev) => ({ ...prev, [key]: next }))}
              />
            </ControlRow>
          ))}
        </div>
      )}
    </ConfigCard>
  );
}

function ChannelsTab({ canWrite }: { canWrite: boolean }) {
  const queryClient = useQueryClient();
  const config = useSystemConfig();
  const [draft, setDraft] = useState<Record<string, boolean>>({});
  const [reason, setReason] = useState("");
  const version = config.data?.notification_channels.version ?? 1;

  useEffect(() => {
    const channels = config.data?.notification_channels.channels;
    if (!channels) return;
    const next: Record<string, boolean> = {};
    for (const [k, v] of Object.entries(channels)) next[k] = Boolean(v.enabled);
    setDraft(next);
  }, [config.data]);

  const mutate = useMutation({
    mutationFn: () =>
      systemConfigApi.setNotificationChannels({
        channels: Object.fromEntries(
          Object.entries(draft).map(([k, enabled]) => [k, { enabled }]),
        ),
        reason: reason.trim(),
        expected_version: version,
      }),
    onSuccess: async () => {
      setReason("");
      await queryClient.invalidateQueries({ queryKey: ["system-config"] });
      notifyConfigSuccess(
        "Channels updated",
        "Notification channel availability has been saved.",
      );
    },
    onError: (error) => notifyConfigError(error, "Could not update channels"),
  });

  return (
    <ConfigCard
      className="config-card--scene"
      footer={
        canWrite ? (
          <SaveFooter
            reason={reason}
            onReasonChange={setReason}
            onSave={() => mutate.mutate()}
            saveLabel="Save"
            disabled={reason.trim().length < 3}
            pending={mutate.isPending}
          />
        ) : (
          <p className="config-muted">Read only</p>
        )
      }
    >
      <header className="config-scene-header">
        <h2 className="config-scene-title">Channels</h2>
        <p className="config-scene-lead">
          Choose which notification channels are available platform wide.
        </p>
      </header>
      {config.isLoading ? (
        <ConfigRowsSkeleton count={Object.keys(CHANNEL_META).length || 4} />
      ) : (
        <div className="config-list">
          {Object.keys(draft).map((key) => {
            const meta = CHANNEL_META[key] ?? {
              title: key,
              subtitle: "Notification channel",
            };
            return (
              <ControlRow key={key} title={meta.title} subtitle={meta.subtitle}>
                <Switch
                  label={meta.title}
                  checked={Boolean(draft[key])}
                  disabled={!canWrite || mutate.isPending}
                  onChange={(next) => setDraft((prev) => ({ ...prev, [key]: next }))}
                />
              </ControlRow>
            );
          })}
        </div>
      )}
    </ConfigCard>
  );
}

function CountriesTab({ canWrite }: { canWrite: boolean }) {
  const queryClient = useQueryClient();
  const countries = useQuery({
    queryKey: ["reference-countries"],
    queryFn: async () => (await referenceApi.countries()).data,
  });
  const currencies = useQuery({
    queryKey: ["reference-currencies"],
    queryFn: async () => (await referenceApi.currencies()).data,
    enabled: canWrite,
  });
  const [iso2, setIso2] = useState("");
  const [name, setName] = useState("");
  const [phoneCode, setPhoneCode] = useState("");
  const [currencyCode, setCurrencyCode] = useState("KES");
  const [showAdd, setShowAdd] = useState(false);

  const create = useMutation({
    mutationFn: () =>
      referenceApi.createCountry({
        iso2: iso2.trim().toUpperCase(),
        name: name.trim(),
        phone_code: phoneCode.trim() || undefined,
        currency_code: currencyCode || undefined,
      }),
    onSuccess: async () => {
      const createdName = name.trim();
      setIso2("");
      setName("");
      setPhoneCode("");
      setShowAdd(false);
      await queryClient.invalidateQueries({ queryKey: ["reference-countries"] });
      await queryClient.invalidateQueries({ queryKey: ["phone-countries"] });
      notifyConfigSuccess(
        "Country added",
        createdName
          ? `${createdName} is now available for quoting and customers.`
          : "The country is now available for quoting and customers.",
      );
    },
    onError: (error) => notifyConfigError(error, "Could not add country"),
  });

  const toggle = useMutation({
    mutationFn: ({
      id,
      status,
    }: {
      id: string;
      status: string;
      label: string;
    }) => referenceApi.updateCountry(id, { status }),
    onSuccess: async (_data, vars) => {
      await queryClient.invalidateQueries({ queryKey: ["reference-countries"] });
      await queryClient.invalidateQueries({ queryKey: ["phone-countries"] });
      if (vars.status === "ACTIVE") {
        notifyConfigSuccess("Country enabled", `${vars.label} is available again.`);
      } else {
        notifyConfigWarning("Country disabled", `${vars.label} is no longer available.`);
      }
    },
    onError: (error) => notifyConfigError(error, "Could not update country"),
  });

  const currencyOptions = useMemo(
    () =>
      (currencies.data?.items ?? []).map((c) => ({
        value: c.code,
        label: `${c.code} ${c.name}`,
      })),
    [currencies.data],
  );

  return (
    <ConfigCard
      className="config-card--scene"
      footer={
        canWrite && !showAdd ? (
          <button
            type="button"
            className="config-btn config-btn--ghost config-btn--flex"
            onClick={() => setShowAdd(true)}
          >
            Add country
          </button>
        ) : !canWrite ? (
          <p className="config-muted">Read only</p>
        ) : undefined
      }
    >
      <header className="config-scene-header">
        <h2 className="config-scene-title">Countries</h2>
        <p className="config-scene-lead">
          Manage which countries are available for quoting and customer records.
        </p>
      </header>
      {countries.isLoading ? (
        <ConfigRowsSkeleton count={6} />
      ) : (
        <div className="config-list">
          {(countries.data?.items ?? []).map((row) => (
            <ControlRow
              key={row.id}
              title={row.name}
              subtitle={`${row.iso2}${row.phone_code ? ` ${row.phone_code}` : ""}`}
            >
              {canWrite ? (
                <Switch
                  label={`${row.name} active`}
                  checked={row.status === "ACTIVE"}
                  disabled={toggle.isPending}
                  onChange={(next) =>
                    toggle.mutate({
                      id: row.id,
                      status: next ? "ACTIVE" : "DISABLED",
                      label: row.name,
                    })
                  }
                />
              ) : (
                <span
                  className={`customers-status-badge customers-status-badge--${
                    row.status === "ACTIVE" ? "active" : "inactive"
                  }`}
                >
                  <span className="customers-status-dot__mark" aria-hidden="true" />
                  {row.status === "ACTIVE" ? "On" : "Off"}
                </span>
              )}
            </ControlRow>
          ))}
        </div>
      )}

      {canWrite && showAdd ? (
        <div className="config-form">
          <label className="config-field">
            <span>ISO2</span>
            <input required value={iso2} maxLength={2} onChange={(e) => setIso2(e.target.value)} />
          </label>
          <label className="config-field">
            <span>Name</span>
            <input required value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="config-field">
            <span>Phone</span>
            <input value={phoneCode} onChange={(e) => setPhoneCode(e.target.value)} placeholder="+254" />
          </label>
          <Select
            label="Currency"
            value={currencyCode}
            onChange={setCurrencyCode}
            options={currencyOptions}
            searchable
            required
            fieldClassName="config-field"
          />
          <div className="config-form-actions">
            <button
              type="button"
              className="config-btn config-btn--ghost config-btn--flex"
              onClick={() => setShowAdd(false)}
            >
              Cancel
            </button>
            <button
              type="button"
              className="config-btn config-btn--flex"
              disabled={create.isPending || iso2.trim().length !== 2 || name.trim().length < 2}
              onClick={() => create.mutate()}
            >
              Create
            </button>
          </div>
        </div>
      ) : null}
    </ConfigCard>
  );
}



const PERMISSION_CATEGORY_LABELS: Record<string, string> = {
  agent: "Agents",
  audit: "Audit",
  branch: "Branches",
  certificate: "Certificates",
  customer: "Customers",
  job: "Jobs",
  notification: "Notifications",
  payment: "Payments",
  platform: "Platform",
  policy: "Policies",
  product: "Products",
  proposal: "Proposals",
  reports: "Reports",
  role: "Roles",
  settings: "Settings",
  tenant: "Tenant",
  user: "Users",
  wallet: "Wallet",
  other: "Other",
};

function humanizePermissionCategory(category: string): string {
  const key = category.trim().toLowerCase();
  if (PERMISSION_CATEGORY_LABELS[key]) return PERMISSION_CATEGORY_LABELS[key];
  return key
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function humanizePermissionCode(code: string): string {
  const action = code.split(":").pop() ?? code;
  return action
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function permissionLabel(p: { code: string; description?: string | null }): string {
  const description = p.description?.trim();
  return description || humanizePermissionCode(p.code);
}

function roleIconFor(role: RoleRow): TabIcon {
  const code = role.code.toLowerCase();
  if (code.includes("admin") || code.includes("platform") || role.is_system) return IconBadge;
  if (code.includes("agent") || code.includes("broker")) return IconBriefcase;
  if (code.includes("underwrit") || code.includes("risk")) return IconShield;
  return IconUsers;
}

function sortRolesByPrivilege(roles: RoleRow[]): RoleRow[] {
  return [...roles].sort((a, b) => {
    const diff = b.permissions.length - a.permissions.length;
    if (diff !== 0) return diff;
    return a.name.localeCompare(b.name);
  });
}

function RolesTab() {
  const { user, refreshUser } = useAuth();
  const queryClient = useQueryClient();
  const roles = useQuery({
    queryKey: ["config-roles"],
    queryFn: async () => (await rolesApi.list()).data,
  });
  const permissions = useQuery({
    queryKey: ["config-permissions"],
    queryFn: async () => (await rolesApi.permissions()).data,
  });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const didInitialSelect = useRef(false);
  const sortedRoles = useMemo(
    () => sortRolesByPrivilege(roles.data?.items ?? []),
    [roles.data?.items],
  );
  const selected: RoleRow | null =
    sortedRoles.find((r) => r.id === selectedId) ?? null;

  useEffect(() => {
    if (didInitialSelect.current || !sortedRoles.length) return;
    didInitialSelect.current = true;
    setSelectedId(sortedRoles[0].id);
  }, [sortedRoles]);

  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [permSection, setPermSection] = useState<string>("all");
  const [reason, setReason] = useState("");

  function toggleRole(roleId: string) {
    setSelectedId((prev) => (prev === roleId ? null : roleId));
  }

  function togglePermSection(section: string) {
    setPermSection((prev) => {
      if (section === "all") return "all";
      return prev === section ? "all" : section;
    });
  }

  useEffect(() => {
    if (selected) setChecked(new Set(selected.permissions));
  }, [selected]);

  useEffect(() => {
    setPermSection("all");
  }, [selected?.id]);

  const save = useMutation({
    mutationFn: () =>
      rolesApi.setPermissions(selected!.id, {
        permission_codes: Array.from(checked),
        reason: reason.trim(),
      }),
    onSuccess: async () => {
      const roleName = selected?.name ?? "Role";
      const editedOwnRole = selected?.id === user?.role_id;
      setReason("");
      try {
        await refreshUser();
      } catch {
        // Stay signed in; live authz applies on the next request.
      }
      await queryClient.invalidateQueries({ queryKey: ["config-roles"] });
      notifyConfigSuccess(
        "Permissions saved",
        editedOwnRole
          ? `${roleName} permissions are live.`
          : `${roleName} permissions have been updated.`,
      );
    },
    onError: (error) => notifyConfigError(error, "Could not save permissions"),
  });

  const setStatus = useMutation({
    mutationFn: (status: string) => rolesApi.update(selected!.id, { status }),
    onSuccess: async (_data, status) => {
      const roleName = selected?.name ?? "Role";
      await queryClient.invalidateQueries({ queryKey: ["config-roles"] });
      if (status === "ACTIVE") {
        notifyConfigSuccess("Role enabled", `${roleName} can be assigned again.`);
      } else {
        notifyConfigWarning("Role disabled", `${roleName} can no longer be assigned.`);
      }
    },
    onError: (error) => notifyConfigError(error, "Could not update role"),
  });

  const byCategory = useMemo(() => {
    const groups = new Map<string, { code: string; description?: string | null }[]>();
    for (const p of permissions.data?.items ?? []) {
      const cat = p.category || "other";
      const list = groups.get(cat) ?? [];
      list.push(p);
      groups.set(cat, list);
    }
    for (const list of groups.values()) {
      list.sort((a, b) => permissionLabel(a).localeCompare(permissionLabel(b)));
    }
    return Array.from(groups.entries()).sort(([catA, itemsA], [catB, itemsB]) => {
      const diff = itemsB.length - itemsA.length;
      if (diff !== 0) return diff;
      return humanizePermissionCategory(catA).localeCompare(humanizePermissionCategory(catB));
    });
  }, [permissions.data]);

  const visibleCategories = useMemo(() => {
    if (permSection === "all") return byCategory;
    return byCategory.filter(([category]) => category === permSection);
  }, [byCategory, permSection]);

  const totalPermissionCount = useMemo(
    () => byCategory.reduce((sum, [, items]) => sum + items.length, 0),
    [byCategory],
  );

  const rolesLoading = roles.isLoading;
  const permissionsLoading = permissions.isLoading;

  return (
    <div className="config-roles">
      <aside className="config-role-rail" aria-label="Roles" aria-busy={rolesLoading || undefined}>
        {rolesLoading
          ? Array.from({ length: 5 }, (_, index) => (
              <div key={`role-chip-skeleton-${index}`} className="config-role-chip config-role-chip--skeleton">
                <span className="skeleton-block config-skeleton-role-icon" />
                <span className="skeleton-block skeleton-block--title" />
              </div>
            ))
          : sortedRoles.map((role) => {
              const Icon = roleIconFor(role);
              const isActive = selectedId === role.id;
              return (
                <div key={role.id} className={`config-role-group${isActive ? " is-open" : ""}`}>
                  <button
                    type="button"
                    className={`config-role-chip${isActive ? " is-active" : ""}`}
                    onClick={() => toggleRole(role.id)}
                    aria-expanded={isActive}
                  >
                    <span className="config-role-chip-icon" aria-hidden="true">
                      <Icon />
                    </span>
                    <span className="config-role-chip-label">{role.name}</span>
                    <em className="config-role-chip-count" aria-hidden="true">
                      {role.permissions.length}
                    </em>
                  </button>
                  {isActive && !permissionsLoading && byCategory.length > 0 ? (
                    <nav className="config-role-sections" aria-label={`${role.name} permission sections`}>
                      <button
                        type="button"
                        className={`config-role-section${permSection === "all" ? " is-active" : ""}`}
                        onClick={() => togglePermSection("all")}
                      >
                        <span>All</span>
                        <em>{totalPermissionCount}</em>
                      </button>
                      {byCategory.map(([category, items]) => (
                        <button
                          key={category}
                          type="button"
                          className={`config-role-section${permSection === category ? " is-active" : ""}`}
                          onClick={() => togglePermSection(category)}
                        >
                          <span>{humanizePermissionCategory(category)}</span>
                          <em>{items.length}</em>
                        </button>
                      ))}
                    </nav>
                  ) : null}
                </div>
              );
            })}
      </aside>

      {selected || rolesLoading ? (
        <ConfigCard
          className="config-card--scene"
          footer={
            selected ? (
              <SaveFooter
                reason={reason}
                onReasonChange={setReason}
                onSave={() => save.mutate()}
                saveLabel="Save"
                disabled={reason.trim().length < 3 || checked.size === 0}
                pending={save.isPending}
              />
            ) : undefined
          }
        >
          <header className="config-scene-header">
            <h2 className="config-scene-title">Roles</h2>
            <p className="config-scene-lead">
              Enable or disable permissions per role. The server stores these
              assignments and enforces them on every request.
            </p>
          </header>

          {selected ? (
            <div className="config-role-head">
              <div className="config-role-head-title">
                <span className="config-role-chip-icon" aria-hidden="true">
                  {(() => {
                    const Icon = roleIconFor(selected);
                    return <Icon />;
                  })()}
                </span>
                <div className="config-role-head-copy">
                  <h3>{selected.name}</h3>
                  <p className="config-role-head-sub">
                    {permSection === "all"
                      ? selected.description?.trim() ||
                        `${checked.size} permission${checked.size === 1 ? "" : "s"} enabled`
                      : `${humanizePermissionCategory(permSection)} permissions`}
                  </p>
                </div>
              </div>
              <Switch
                label={`${selected.name} active`}
                checked={selected.status === "ACTIVE"}
                disabled={setStatus.isPending || selected.id === user?.role_id}
                onChange={(next) => setStatus.mutate(next ? "ACTIVE" : "DISABLED")}
              />
            </div>
          ) : (
            <div className="config-role-head config-role-head--skeleton">
              <div className="config-role-head-title">
                <span className="skeleton-block config-skeleton-role-icon" />
                <div className="config-role-head-copy">
                  <span className="skeleton-block skeleton-block--title" />
                  <span className="skeleton-block skeleton-block--meta" />
                </div>
              </div>
              <span className="skeleton-block config-skeleton-switch" />
            </div>
          )}

          {permissionsLoading ? (
            <div className="config-list" aria-busy="true">
              {Array.from({ length: 8 }, (_, index) => (
                <div key={`perm-skeleton-${index}`} className="config-row config-row--skeleton">
                  <div className="config-row-copy">
                    <span className="skeleton-block skeleton-block--title" />
                    <span className="skeleton-block skeleton-block--meta" />
                  </div>
                  <span className="skeleton-block config-skeleton-switch" />
                </div>
              ))}
            </div>
          ) : (
            <div className="config-perm-board">
              {permSection === "all" ? (
                <div className="config-perm-sections">
                  {visibleCategories.map(([category, items]) => (
                    <section
                      key={category}
                      id={`perm-group-${category}`}
                      className="config-perm-block"
                    >
                      <div className="config-perm-block-head">
                        <h4>{humanizePermissionCategory(category)}</h4>
                      </div>
                      <div className="config-list">
                        {items.map((p) => {
                          const title = permissionLabel(p);
                          return (
                            <ControlRow key={p.code} title={title}>
                              <Switch
                                label={title}
                                checked={checked.has(p.code)}
                                disabled={save.isPending}
                                onChange={(next) => {
                                  setChecked((prev) => {
                                    const copy = new Set(prev);
                                    if (next) copy.add(p.code);
                                    else copy.delete(p.code);
                                    return copy;
                                  });
                                }}
                              />
                            </ControlRow>
                          );
                        })}
                      </div>
                    </section>
                  ))}
                </div>
              ) : (
                <div className="config-list">
                  {(visibleCategories[0]?.[1] ?? []).map((p) => {
                    const title = permissionLabel(p);
                    return (
                      <ControlRow key={p.code} title={title}>
                        <Switch
                          label={title}
                          checked={checked.has(p.code)}
                          disabled={save.isPending}
                          onChange={(next) => {
                            setChecked((prev) => {
                              const copy = new Set(prev);
                              if (next) copy.add(p.code);
                              else copy.delete(p.code);
                              return copy;
                            });
                          }}
                        />
                      </ControlRow>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </ConfigCard>
      ) : !rolesLoading ? (
        <ConfigCard className="config-card--scene">
          <header className="config-scene-header">
            <h2 className="config-scene-title">Roles</h2>
            <p className="config-scene-lead">
              Select a role on the left to view and edit its permissions.
            </p>
          </header>
          <div className="customers-empty" role="status">
            <span className="customers-empty-icon" aria-hidden="true">
              <IconUsers />
            </span>
            <p className="customers-empty-title">No role selected</p>
            <p className="customers-empty-copy">Expand a role from the list to manage permissions.</p>
          </div>
        </ConfigCard>
      ) : null}
    </div>
  );
}


const AGENCY_COLOR_PRESETS = [
  "#39B54A",
  "#2A8F39",
  "#0B3D2E",
  "#1B1464",
  "#0F766E",
  "#0369A1",
  "#7C3AED",
  "#C2410C",
  "#B91C1C",
  "#171717",
] as const;

function clamp(n: number, min: number, max: number) {
  return Math.min(max, Math.max(min, n));
}

function normalizeHex(value: string): string | null {
  const raw = value.trim().toUpperCase();
  const withHash = raw.startsWith("#") ? raw : `#${raw}`;
  return /^#[0-9A-F]{6}$/.test(withHash) ? withHash : null;
}

function hexToHsv(hex: string): { h: number; s: number; v: number } {
  const normalized = normalizeHex(hex) ?? "#0B3D2E";
  const r = parseInt(normalized.slice(1, 3), 16) / 255;
  const g = parseInt(normalized.slice(3, 5), 16) / 255;
  const b = parseInt(normalized.slice(5, 7), 16) / 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const d = max - min;
  let h = 0;
  if (d !== 0) {
    if (max === r) h = ((g - b) / d) % 6;
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h *= 60;
    if (h < 0) h += 360;
  }
  const s = max === 0 ? 0 : d / max;
  return { h, s, v: max };
}

function hsvToHex(h: number, s: number, v: number): string {
  const c = v * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = v - c;
  let r = 0;
  let g = 0;
  let b = 0;
  if (h < 60) [r, g, b] = [c, x, 0];
  else if (h < 120) [r, g, b] = [x, c, 0];
  else if (h < 180) [r, g, b] = [0, c, x];
  else if (h < 240) [r, g, b] = [0, x, c];
  else if (h < 300) [r, g, b] = [x, 0, c];
  else [r, g, b] = [c, 0, x];
  const toHex = (n: number) =>
    Math.round((n + m) * 255)
      .toString(16)
      .padStart(2, "0")
      .toUpperCase();
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

function PrimaryColorPicker({
  value,
  onChange,
}: {
  value: string;
  onChange: (next: string) => void;
}) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const boardRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);
  const safe = normalizeHex(value) ?? "#0B3D2E";
  const hsv = useMemo(() => hexToHsv(safe), [safe]);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function commitHsv(next: { h?: number; s?: number; v?: number }) {
    const h = next.h ?? hsv.h;
    const s = next.s ?? hsv.s;
    const v = next.v ?? hsv.v;
    onChange(hsvToHex(h, s, v));
  }

  function pickFromBoard(clientX: number, clientY: number) {
    const board = boardRef.current;
    if (!board) return;
    const rect = board.getBoundingClientRect();
    const s = clamp((clientX - rect.left) / rect.width, 0, 1);
    const v = clamp(1 - (clientY - rect.top) / rect.height, 0, 1);
    commitHsv({ s, v });
  }

  return (
    <div className="config-color" ref={rootRef}>
      <button
        type="button"
        className={`config-color-swatch${open ? " is-open" : ""}`}
        style={{ backgroundColor: safe }}
        aria-label="Open color picker"
        aria-expanded={open}
        onClick={() => setOpen((prev) => !prev)}
      />
      <div className="config-color-meta">
        <input
          className="config-color-hex"
          value={value}
          onChange={(e) => onChange(e.target.value.toUpperCase())}
          onBlur={() => {
            const normalized = normalizeHex(value);
            if (normalized) onChange(normalized);
          }}
          spellCheck={false}
          maxLength={7}
          aria-label="Primary color hex"
        />
        <span className="config-color-hint">Custom brand accent</span>
      </div>

      {open ? (
        <div className="config-color-popover" role="dialog" aria-label="Choose primary color">
          <div
            ref={boardRef}
            className="config-color-board"
            style={{
              background: `
                linear-gradient(to top, #000, transparent),
                linear-gradient(to right, #fff, hsl(${hsv.h} 100% 50%))
              `,
            }}
            onPointerDown={(event) => {
              event.currentTarget.setPointerCapture(event.pointerId);
              pickFromBoard(event.clientX, event.clientY);
            }}
            onPointerMove={(event) => {
              if (!event.currentTarget.hasPointerCapture(event.pointerId)) return;
              pickFromBoard(event.clientX, event.clientY);
            }}
          >
            <span
              className="config-color-board-thumb"
              style={{
                left: `${hsv.s * 100}%`,
                top: `${(1 - hsv.v) * 100}%`,
                backgroundColor: safe,
              }}
            />
          </div>

          <label className="config-color-hue">
            <span className="config-sr-only">Hue</span>
            <input
              type="range"
              min={0}
              max={360}
              value={Math.round(hsv.h)}
              onChange={(e) => commitHsv({ h: Number(e.target.value) })}
              style={{
                background: `linear-gradient(
                  to right,
                  hsl(0 100% 50%),
                  hsl(60 100% 50%),
                  hsl(120 100% 50%),
                  hsl(180 100% 50%),
                  hsl(240 100% 50%),
                  hsl(300 100% 50%),
                  hsl(360 100% 50%)
                )`,
              }}
            />
          </label>

          <div className="config-color-presets" aria-label="Suggested colors">
            {AGENCY_COLOR_PRESETS.map((preset) => (
              <button
                key={preset}
                type="button"
                className={`config-color-preset${safe === preset ? " is-active" : ""}`}
                style={{ backgroundColor: preset }}
                aria-label={`Use ${preset}`}
                onClick={() => onChange(preset)}
              />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function AgencyTab() {
  const queryClient = useQueryClient();
  const settings = useQuery({
    queryKey: ["tenant-settings"],
    queryFn: async () => (await tenantApi.settings()).data,
  });
  const [tradingName, setTradingName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [phoneCountry, setPhoneCountry] = useState(DEFAULT_PHONE_COUNTRY);
  const [primaryColor, setPrimaryColor] = useState("#0B3D2E");

  useEffect(() => {
    if (!settings.data) return;
    setTradingName(settings.data.trading_name);
    setEmail(settings.data.email ?? "");
    const parsed = fromE164(settings.data.phone);
    setPhoneCountry(parsed.iso);
    setPhone(parsed.national);
    const color = settings.data.branding?.primaryColor;
    if (typeof color === "string") setPrimaryColor(color);
  }, [settings.data]);

  const save = useMutation({
    mutationFn: () =>
      tenantApi.updateSettings({
        trading_name: tradingName,
        email: email || undefined,
        phone: toE164(phoneCountry, phone) || undefined,
        branding: { primaryColor },
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["tenant-settings"] });
      notifyConfigSuccess(
        "Agency settings saved",
        "Trading details and branding are now up to date.",
      );
    },
    onError: (error) => notifyConfigError(error, "Could not save agency settings"),
  });

  return (
    <ConfigCard
      className="config-card--scene"
      footer={
        <button
          type="button"
          className="config-btn config-btn--flex"
          disabled={save.isPending || settings.isLoading}
          onClick={() => save.mutate()}
        >
          Save
        </button>
      }
    >
      <header className="config-scene-header">
        <h2 className="config-scene-title">Agency</h2>
        <p className="config-scene-lead">
          Update trading details and brand appearance for this agency.
        </p>
      </header>

      {settings.isLoading ? (
        <div className="config-agency-skeleton" aria-busy="true">
          <span className="skeleton-block config-skeleton-agency-name" />
          <div className="config-form">
            <div className="config-field">
              <span className="skeleton-block skeleton-block--meta" />
              <span className="skeleton-block config-skeleton-field" />
            </div>
            <div className="config-field">
              <span className="skeleton-block skeleton-block--meta" />
              <span className="skeleton-block config-skeleton-field" />
            </div>
            <div className="config-field config-field--wide">
              <span className="skeleton-block skeleton-block--meta" />
              <span className="skeleton-block config-skeleton-field" />
            </div>
            <div className="config-field config-field--wide">
              <span className="skeleton-block skeleton-block--meta" />
              <span className="skeleton-block config-skeleton-color" />
            </div>
          </div>
        </div>
      ) : (
        <>
          <p className="config-agency-name">{settings.data?.legal_name ?? "Agency"}</p>

          <div className="config-form">
            <label className="config-field">
              <span>Trading name</span>
              <input
                required
                value={tradingName}
                onChange={(e) => setTradingName(e.target.value)}
              />
            </label>
            <label className="config-field">
              <span>Email</span>
              <input value={email} onChange={(e) => setEmail(e.target.value)} />
            </label>
            <div className="config-field config-field--wide">
              <PhoneField
                label="Phone"
                value={phone}
                onChange={setPhone}
                country={phoneCountry}
                onCountryChange={setPhoneCountry}
              />
            </div>
            <div className="config-field config-field--wide">
              <span>Primary color</span>
              <PrimaryColorPicker value={primaryColor} onChange={setPrimaryColor} />
            </div>
          </div>
        </>
      )}
    </ConfigCard>
  );
}

function CommissionsTab({ canWrite }: { canWrite: boolean }) {
  const queryClient = useQueryClient();
  const settingsQ = useQuery({
    queryKey: ["commission-settings"],
    queryFn: async () => (await commissionApi.getSettings()).data,
  });
  const [certRate, setCertRate] = useState("0");
  const [claimRate, setClaimRate] = useState("0");
  const [cadence, setCadence] = useState("MONTHLY");
  const [enabled, setEnabled] = useState(true);
  const [notes, setNotes] = useState("");
  const [referralAmount, setReferralAmount] = useState("50");
  const [referralsEnabled, setReferralsEnabled] = useState(true);

  useEffect(() => {
    if (!settingsQ.data) return;
    setCertRate(String(settingsQ.data.certificate_rate_percent ?? "0"));
    setClaimRate(String(settingsQ.data.claim_rate_percent ?? "0"));
    setCadence(settingsQ.data.payout_cadence || "MONTHLY");
    setEnabled(Boolean(settingsQ.data.enabled));
    setNotes(settingsQ.data.notes ?? "");
    setReferralAmount(String(settingsQ.data.customer_referral_amount ?? "50"));
    setReferralsEnabled(settingsQ.data.customer_referrals_enabled ?? true);
  }, [settingsQ.data]);

  const save = useMutation({
    mutationFn: () =>
      commissionApi.updateSettings({
        certificate_rate_percent: Number(certRate) || 0,
        claim_rate_percent: Number(claimRate) || 0,
        payout_cadence: cadence,
        enabled,
        notes: notes.trim() || null,
        currency: settingsQ.data?.currency || "KES",
        customer_referral_amount: Math.max(0, Number(referralAmount) || 0),
        customer_referrals_enabled: referralsEnabled,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["commission-settings"] });
      notifyConfigSuccess(
        "Commission settings saved",
        "Rates and payout cadence apply to the next successful payments.",
      );
    },
    onError: (error) => notifyConfigError(error, "Could not save commission settings"),
  });

  return (
    <ConfigCard
      className="config-card--scene config-commissions-card"
      footer={
        canWrite ? (
          <button
            type="button"
            className="config-btn config-btn--flex"
            disabled={save.isPending || settingsQ.isLoading}
            onClick={() => save.mutate()}
          >
            {save.isPending ? "Saving…" : "Save rates"}
          </button>
        ) : null
      }
    >
      <header className="config-scene-header">
        <h2 className="config-scene-title">Agent commissions</h2>
        <p className="config-scene-lead">
          Set how much approved agents earn on paid certificates. With no agent code, the amount
          is retained by Star Serve. Ledger balances live under Finance → Commission ledger.
        </p>
      </header>

      {settingsQ.isLoading ? (
        <div className="config-agency-skeleton" aria-busy="true">
          <div className="config-form">
            {Array.from({ length: 4 }, (_, i) => (
              <div key={i} className={`config-field${i > 1 ? " config-field--wide" : ""}`}>
                <span className="skeleton-block skeleton-block--meta" />
                <span className="skeleton-block config-skeleton-field" />
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="config-form config-commissions-form">
          <label className="config-field">
            <span>Certificate rate (%)</span>
            <input
              type="number"
              min={0}
              max={100}
              step="0.01"
              disabled={!canWrite}
              value={certRate}
              onChange={(e) => setCertRate(e.target.value)}
            />
          </label>
          <label className="config-field">
            <span>Claim rate (%)</span>
            <input
              type="number"
              min={0}
              max={100}
              step="0.01"
              disabled={!canWrite}
              value={claimRate}
              onChange={(e) => setClaimRate(e.target.value)}
            />
          </label>
          <Select
            label="Payout cadence"
            value={cadence}
            disabled={!canWrite}
            onChange={setCadence}
            fieldClassName="config-field"
            options={[
              { value: "WEEKLY", label: "Weekly" },
              { value: "MONTHLY", label: "Monthly" },
            ]}
          />
          <div className="config-field config-commissions-switch">
            <span>Commissions enabled</span>
            <button
              type="button"
              className={`config-switch${enabled ? " is-on" : ""}`}
              role="switch"
              aria-checked={enabled}
              disabled={!canWrite}
              onClick={() => setEnabled((v) => !v)}
            >
              <span className="config-switch-thumb" aria-hidden="true" />
              <span className="config-sr-only">{enabled ? "On" : "Off"}</span>
            </button>
          </div>
          <label className="config-field">
            <span>Customer referral credit (KES, flat)</span>
            <input
              type="number"
              min={0}
              step="1"
              disabled={!canWrite}
              value={referralAmount}
              onChange={(e) => setReferralAmount(e.target.value)}
            />
          </label>
          <div className="config-field config-commissions-switch">
            <span>Customer referrals enabled</span>
            <button
              type="button"
              className={`config-switch${referralsEnabled ? " is-on" : ""}`}
              role="switch"
              aria-checked={referralsEnabled}
              disabled={!canWrite}
              onClick={() => setReferralsEnabled((v) => !v)}
            >
              <span className="config-switch-thumb" aria-hidden="true" />
              <span className="config-sr-only">{referralsEnabled ? "On" : "Off"}</span>
            </button>
          </div>
          <p className="config-field config-field--wide config-muted">
            Customers earn this flat credit each time someone buys cover with their referral code.
            Credit is not paid out; it comes off their next M-Pesa premium automatically.
          </p>
          <label className="config-field config-field--wide">
            <span>Notes</span>
            <textarea
              rows={2}
              disabled={!canWrite}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Optional plan notes for auditors"
            />
          </label>
        </div>
      )}
    </ConfigCard>
  );
}
