import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ComponentType,
  type SVGProps,
} from "react";
import { useAuth } from "@/app/providers/AuthProvider";
import {
  IconChart,
  IconFileText,
  IconGrid,
  IconList,
  IconPhone,
  IconSettings,
  IconSliders,
} from "@/components/ui/icons";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { ApiError } from "@/services/api/client";
import { ussdApi, type UssdConfig } from "@/services/ussd/ussdApi";
import "./ussd.css";

const ANALYTICS_PERIOD_OPTIONS = [
  { value: "today", label: "Today" },
  { value: "yesterday", label: "Yesterday" },
  { value: "last_7_days", label: "Last 7 days" },
  { value: "last_30_days", label: "Last 30 days" },
];

const ANALYTICS_WORKFLOW_OPTIONS = [
  { value: "MOTOR_QUOTE", label: "Motor quote funnel" },
  { value: "REPORT_CLAIM", label: "Report claim funnel" },
  { value: "FOLLOW_UP_CLAIM", label: "Follow up funnel" },
];

const ANALYTICS_TRAFFIC_OPTIONS = [
  { value: "live", label: "Live only" },
  { value: "all", label: "Live + simulator" },
];

const SESSION_SOURCE_OPTIONS = [
  { value: "all", label: "All sessions" },
  { value: "test", label: "Test only" },
  { value: "live", label: "Live only" },
];

const PROVIDER_KIND_OPTIONS = [
  { value: "BIRDVIEW", label: "Birdview (*652#)" },
  { value: "SIMULATOR", label: "Simulator" },
  { value: "GENERIC_FORM", label: "Generic form (AT shaped)" },
  { value: "AFRICAS_TALKING", label: "Africa's Talking" },
];

function workflowLabel(action: unknown) {
  const key = String(action || "").trim();
  if (!key) return "—";
  return (
    ANALYTICS_WORKFLOW_OPTIONS.find((option) => option.value === key)?.label.replace(
      / funnel$/i,
      "",
    ) || key.replaceAll("_", " ")
  );
}

type Tab =
  | "overview"
  | "menus"
  | "simulator"
  | "analytics"
  | "sessions"
  | "provider"
  | "audit";

/** Live dial-in short code for the StarServe main menu. */
const USSD_SERVICE_CODE = "*652*6#";

/** Render USSD text with numbered menu option labels in bold. */
function UssdScreenText({ text }: { text: string }) {
  const lines = text.split("\n");
  const isMenuList = lines.some((line) => /^\d{1,2}\.\s+/.test(line));
  return (
    <div
      className={[
        "ussd-phone-screen-text",
        isMenuList ? "ussd-phone-screen-text--menu" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {lines.map((line, index) => {
        const option = line.match(/^(\d{1,2})\.\s+(.+)$/);
        if (option) {
          return (
            <div key={index} className="ussd-phone-screen-line ussd-phone-screen-line--opt">
              <span className="ussd-phone-screen-opt">
                {option[1]}. <strong>{option[2]}</strong>
              </span>
            </div>
          );
        }
        const more = line.match(/^(99)\s+(.+)$/);
        if (more) {
          return (
            <div key={index} className="ussd-phone-screen-line ussd-phone-screen-line--opt">
              <span className="ussd-phone-screen-opt">
                {more[1]} <strong>{more[2]}</strong>
              </span>
            </div>
          );
        }
        return (
          <div key={index} className="ussd-phone-screen-line">
            {line || "\u00a0"}
          </div>
        );
      })}
    </div>
  );
}

type TabIcon = ComponentType<SVGProps<SVGSVGElement> & { title?: string }>;

const TAB_META: {
  id: Tab;
  label: string;
  permission?: string;
  icon: TabIcon;
}[] = [
  { id: "overview", label: "Overview", permission: "ussd:read", icon: IconGrid },
  { id: "menus", label: "Menu builder", permission: "ussd:manage", icon: IconList },
  { id: "simulator", label: "Simulator", permission: "ussd:manage", icon: IconPhone },
  { id: "analytics", label: "Analytics", permission: "ussd:analytics", icon: IconChart },
  { id: "sessions", label: "Sessions", permission: "ussd:read", icon: IconSliders },
  { id: "provider", label: "Provider", permission: "ussd:manage", icon: IconSettings },
  { id: "audit", label: "Audit", permission: "ussd:manage", icon: IconFileText },
];

function errMessage(err: unknown) {
  if (err instanceof ApiError || err instanceof Error) return err.message;
  return "Something went wrong";
}

function statusTone(status: string) {
  const key = status.trim().toUpperCase();
  if (key === "PUBLISHED" || key === "COMPLETED" || key === "ACTIVE") return "active";
  if (key === "DRAFT" || key === "PENDING") return "pending";
  if (key === "FAILED" || key === "TERMINATED" || key === "TIMED_OUT") return "inactive";
  return "neutral";
}

function UssdStatCardSkeleton({ count }: { count: number }) {
  return (
    <>
      {Array.from({ length: count }, (_, index) => (
        <article
          key={`ussd-stat-skel-${index}`}
          className="customers-stat-card customers-stat-card--skeleton"
          aria-hidden="true"
        >
          <span className="skeleton-block skeleton-block--meta ussd-skel-stat-label" />
          <strong className="skeleton-block skeleton-block--title ussd-skel-stat-value" />
        </article>
      ))}
    </>
  );
}

function UssdTableSkeleton({
  columns,
  rows = 6,
}: {
  columns: number;
  rows?: number;
}) {
  return (
    <div className="customers-table-wrap" aria-busy="true" aria-hidden="true">
      <table className="customers-table">
        <thead>
          <tr>
            {Array.from({ length: columns }, (_, index) => (
              <th key={`ussd-th-skel-${index}`} scope="col">
                <span className="skeleton-block skeleton-block--meta ussd-skel-th" />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }, (_, row) => (
            <tr key={`ussd-row-skel-${row}`} className="customers-table-row--skeleton">
              {Array.from({ length: columns }, (_, col) => (
                <td key={`ussd-cell-skel-${row}-${col}`}>
                  <span
                    className={`skeleton-block ${
                      col === 0 ? "skeleton-block--title" : "skeleton-block--meta"
                    }`}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function OverviewBodySkeleton() {
  return (
    <div className="ussd-overview-skeleton" aria-busy="true" aria-hidden="true">
      <div className="ussd-overview-meta">
        <div>
          <span className="skeleton-block skeleton-block--meta ussd-skel-meta-label" />
          <span className="skeleton-block skeleton-block--title ussd-skel-meta-value" />
        </div>
        <div>
          <span className="skeleton-block skeleton-block--meta ussd-skel-meta-label" />
          <span className="skeleton-block skeleton-block--title ussd-skel-meta-value ussd-skel-meta-value--wide" />
        </div>
      </div>
      <div className="customers-stat-grid ussd-overview-stats">
        <UssdStatCardSkeleton count={6} />
      </div>
      <span className="skeleton-block skeleton-block--meta ussd-skel-help" />
    </div>
  );
}

function MenusBodySkeleton() {
  return (
    <div className="ussd-menus ussd-menus--skeleton" aria-busy="true" aria-hidden="true">
      <aside className="ussd-menus-aside">
        <span className="skeleton-block skeleton-block--meta ussd-skel-aside-label" />
        <ul className="ussd-config-list">
          {Array.from({ length: 4 }, (_, index) => (
            <li key={`ussd-menu-skel-${index}`}>
              <div className="ussd-config-row ussd-config-row--skeleton">
                <span className="ussd-config-row-copy">
                  <span className="skeleton-block skeleton-block--title" />
                  <span className="skeleton-block skeleton-block--meta" />
                </span>
                <span className="skeleton-block customers-status-skeleton" />
              </div>
            </li>
          ))}
        </ul>
      </aside>
      <div className="ussd-menus-editor">
        <div className="ussd-section-head">
          <div className="ussd-skel-editor-head">
            <span className="skeleton-block skeleton-block--title ussd-skel-editor-title" />
            <span className="skeleton-block skeleton-block--meta ussd-skel-editor-sub" />
          </div>
          <div className="ussd-actions">
            <span className="skeleton-block ussd-skel-btn" />
            <span className="skeleton-block ussd-skel-btn" />
          </div>
        </div>
        <div className="config-form">
          <div className="config-field config-field--wide">
            <span className="skeleton-block skeleton-block--meta ussd-skel-field-label" />
            <span className="skeleton-block config-skeleton-field" />
          </div>
          <div className="config-field config-field--wide">
            <span className="skeleton-block skeleton-block--meta ussd-skel-field-label" />
            <span className="skeleton-block ussd-skel-textarea" />
          </div>
        </div>
      </div>
    </div>
  );
}

function SimulatorScreenSkeleton() {
  return (
    <div className="ussd-phone-screen-skel" aria-busy="true" aria-hidden="true">
      <span className="skeleton-block skeleton-block--title ussd-skel-phone-line" />
      <span className="skeleton-block skeleton-block--meta ussd-skel-phone-line ussd-skel-phone-line--sm" />
      <span className="skeleton-block skeleton-block--meta ussd-skel-phone-line" />
      <span className="skeleton-block skeleton-block--meta ussd-skel-phone-line ussd-skel-phone-line--md" />
      <span className="skeleton-block skeleton-block--meta ussd-skel-phone-line ussd-skel-phone-line--sm" />
    </div>
  );
}

function ProviderBodySkeleton() {
  return (
    <div className="ussd-provider-skeleton" aria-busy="true" aria-hidden="true">
      <div className="ussd-provider-meta">
        <div>
          <span className="skeleton-block skeleton-block--meta ussd-skel-meta-label" />
          <span className="skeleton-block skeleton-block--title ussd-skel-meta-value ussd-skel-meta-value--wide" />
        </div>
        <div>
          <span className="skeleton-block skeleton-block--meta ussd-skel-meta-label" />
          <span className="skeleton-block customers-status-skeleton" />
        </div>
      </div>
      <div className="config-form ussd-provider-form">
        <div className="config-field">
          <span className="skeleton-block skeleton-block--meta ussd-skel-field-label" />
          <span className="skeleton-block config-skeleton-field" />
        </div>
        <div className="config-field">
          <span className="skeleton-block skeleton-block--meta ussd-skel-field-label" />
          <span className="skeleton-block config-skeleton-field" />
        </div>
        <div className="config-field config-field--wide">
          <span className="skeleton-block skeleton-block--meta ussd-skel-field-label" />
          <span className="skeleton-block config-skeleton-field" />
        </div>
      </div>
    </div>
  );
}

export function UssdPage() {
  const { hasPermission } = useAuth();
  const tabs = TAB_META.filter((t) => !t.permission || hasPermission(t.permission));
  const [tab, setTab] = useState<Tab | null>(null);
  const active = tab && tabs.some((t) => t.id === tab) ? tab : (tabs[0]?.id ?? null);
  const canRead = hasPermission("ussd:read") || hasPermission("ussd:manage");

  if (!canRead || !active) {
    return (
      <section className="config-page configuration-page ussd-page">
        <h1 className="config-title">USSD</h1>
        <p className="config-empty">You do not have permission to view the USSD channel.</p>
      </section>
    );
  }

  return (
    <section className="config-page configuration-page ussd-page">
      <h1 className="config-title">USSD</h1>
      <p className="ussd-lede">
        Manage the dial-in channel ({USSD_SERVICE_CODE}), menus, simulator, and analytics for
        StarServe Insurance.
      </p>

      <div className="config-shell">
        <nav className="config-rail" aria-label="USSD sections">
          {tabs.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                type="button"
                className={`config-rail-item${active === item.id ? " is-active" : ""}`}
                aria-current={active === item.id ? "page" : undefined}
                onClick={() => setTab(item.id)}
              >
                <span className="config-rail-icon" aria-hidden="true">
                  <Icon />
                </span>
                <span className="config-rail-label">{item.label}</span>
              </button>
            );
          })}
        </nav>

        <div className="config-stage config-stage--fill" key={active}>
          {active === "overview" ? <OverviewPanel /> : null}
          {active === "menus" ? <MenusPanel /> : null}
          {active === "simulator" ? <SimulatorPanel /> : null}
          {active === "analytics" ? <AnalyticsPanel /> : null}
          {active === "sessions" ? <SessionsPanel /> : null}
          {active === "provider" ? <ProviderPanel /> : null}
          {active === "audit" ? <AuditPanel /> : null}
        </div>
      </div>
    </section>
  );
}

function OverviewPanel() {
  const query = useQuery({
    queryKey: ["ussd-overview"],
    queryFn: async () => (await ussdApi.overview()).data,
  });
  const health = query.data?.health;
  const metrics = (query.data?.metrics || {}) as Record<string, number | string>;
  const serviceOk = !query.error && String(health?.service || "").toLowerCase() === "ok";
  const providerKind = String(health?.provider_kind || "—").replaceAll("_", " ");
  const callbackPath = String(
    health?.callback_url ||
      health?.callback_path ||
      "https://quote.starserveinsuranceagency.com/api/v1/ussd/callback",
  );

  return (
    <div className="config-card config-card--scene ussd-panel ussd-overview-card">
      <div className="config-card-body">
        <header className="config-scene-header ussd-overview-header">
          <div className="ussd-overview-header-copy">
            <h2 className="config-scene-title">Overview</h2>
            <p className="config-scene-lead">
              Channel health for {USSD_SERVICE_CODE}. Live traffic only in the 7-day metrics.
            </p>
          </div>
          <span
            className={`customers-status-badge customers-status-badge--${
              query.isLoading ? "pending" : serviceOk ? "active" : "inactive"
            }`}
          >
            <span className="customers-status-dot__mark" aria-hidden="true" />
            {query.isLoading ? "Checking" : serviceOk ? "Online" : "Unavailable"}
          </span>
        </header>

        {query.error ? (
          <div className="customers-empty ussd-overview-empty" role="alert">
            <p className="customers-empty-title">Overview unavailable</p>
            <p className="customers-empty-copy">{errMessage(query.error)}</p>
          </div>
        ) : null}

        {query.isLoading && !query.error ? <OverviewBodySkeleton /> : null}

        {!query.isLoading && !query.error ? (
          <>
            <div className="ussd-overview-meta">
              <div>
                <span className="ussd-menus-aside-label">Short code</span>
                <p className="ussd-mono">{USSD_SERVICE_CODE}</p>
              </div>
              <div>
                <span className="ussd-menus-aside-label">Callback path</span>
                <p className="ussd-mono">{callbackPath}</p>
              </div>
            </div>

            <div className="customers-stat-grid ussd-overview-stats" aria-live="polite">
              <article className="customers-stat-card">
                <span className="customers-stat-label">Published menu</span>
                <strong className="customers-stat-value">
                  {health?.published_version != null ? `v${health.published_version}` : "—"}
                </strong>
              </article>
              <article className="customers-stat-card">
                <span className="customers-stat-label">Provider</span>
                <strong className="customers-stat-value">
                  {health?.provider_enabled ? providerKind : `${providerKind} · off`}
                </strong>
              </article>
              <article className="customers-stat-card">
                <span className="customers-stat-label">Sessions (7d)</span>
                <strong className="customers-stat-value">
                  {Number(metrics.total_sessions ?? 0).toLocaleString()}
                </strong>
              </article>
              <article className="customers-stat-card">
                <span className="customers-stat-label">Unique access</span>
                <strong className="customers-stat-value">
                  {Number(metrics.unique_access_count ?? 0).toLocaleString()}
                </strong>
              </article>
              <article className="customers-stat-card">
                <span className="customers-stat-label">Completion rate</span>
                <strong className="customers-stat-value">
                  {String(metrics.session_completion_rate ?? 0)}%
                </strong>
              </article>
              <article className="customers-stat-card">
                <span className="customers-stat-label">Validation failures</span>
                <strong className="customers-stat-value">
                  {Number(metrics.validation_failures ?? 0).toLocaleString()}
                </strong>
              </article>
            </div>

            <p className="ussd-help">
              Unique access counts distinct pseudonymized phone hashes, not verified people.
            </p>
          </>
        ) : null}
      </div>
    </div>
  );
}

function MenusPanel() {
  const qc = useQueryClient();
  const configs = useQuery({
    queryKey: ["ussd-configs"],
    queryFn: async () => (await ussdApi.configs()).data.items,
  });
  const items = configs.data || [];
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [welcome, setWelcome] = useState("");
  const [optionsJson, setOptionsJson] = useState("");

  const active = useMemo(() => {
    if (!items.length) return null;
    if (selectedId) {
      const match = items.find((c) => c.id === selectedId);
      if (match) return match;
    }
    return items.find((c) => c.status === "DRAFT") || items.find((c) => c.status === "PUBLISHED") || items[0];
  }, [items, selectedId]);

  const syncEditor = (cfg: UssdConfig) => {
    setSelectedId(cfg.id);
    setWelcome(cfg.welcome_text);
    setOptionsJson(JSON.stringify(cfg.definition?.screens?.main?.options || [], null, 2));
  };

  useEffect(() => {
    if (!active) return;
    if (selectedId === active.id && welcome) return;
    setSelectedId(active.id);
    setWelcome(active.welcome_text);
    setOptionsJson(JSON.stringify(active.definition?.screens?.main?.options || [], null, 2));
    // Only re-sync when the selected version identity changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active?.id]);

  const createDraft = useMutation({
    mutationFn: () => ussdApi.createDraft(`Draft ${new Date().toLocaleString()}`),
    onSuccess: async (res) => {
      await qc.invalidateQueries({ queryKey: ["ussd-configs"] });
      await qc.invalidateQueries({ queryKey: ["ussd-audit"] });
      syncEditor(res.data);
    },
  });

  const save = useMutation({
    mutationFn: async () => {
      if (!active || active.status !== "DRAFT") throw new Error("Create a draft first");
      const options = JSON.parse(optionsJson);
      const definition = structuredClone(active.definition || { screens: {} });
      definition.screens = definition.screens || {};
      definition.screens.main = {
        ...(definition.screens.main || {}),
        title: welcome,
        options,
      };
      return ussdApi.updateConfig(active.id, { welcome_text: welcome, definition });
    },
    onSuccess: async (res) => {
      await qc.invalidateQueries({ queryKey: ["ussd-configs"] });
      await qc.invalidateQueries({ queryKey: ["ussd-audit"] });
      syncEditor(res.data);
    },
  });

  const publish = useMutation({
    mutationFn: async () => {
      if (!active || active.status !== "DRAFT") throw new Error("Select a draft to publish");
      return ussdApi.publish(active.id);
    },
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["ussd-configs"] });
      await qc.invalidateQueries({ queryKey: ["ussd-overview"] });
      await qc.invalidateQueries({ queryKey: ["ussd-audit"] });
    },
  });

  const actionError = save.error || publish.error || createDraft.error;
  const isLoading = configs.isLoading && !configs.data;

  return (
    <div className="config-card config-card--scene ussd-menus-card">
      <div className="config-card-body">
        <header className="config-scene-header ussd-menus-header">
          <div className="ussd-menus-header-copy">
            <h2 className="config-scene-title">Menu builder</h2>
            <p className="config-scene-lead">
              Edit welcome text and menu options, then publish for new USSD sessions.
            </p>
          </div>
          <button
            type="button"
            className="config-btn"
            onClick={() => createDraft.mutate()}
            disabled={createDraft.isPending || isLoading}
          >
            {createDraft.isPending ? "Creating…" : "New draft"}
          </button>
        </header>

        {isLoading ? <MenusBodySkeleton /> : null}

        {configs.isError ? (
          <div className="customers-empty" role="alert">
            <p className="customers-empty-title">Couldn’t load menus</p>
            <p className="customers-empty-copy">{errMessage(configs.error)}</p>
          </div>
        ) : null}

        {!isLoading && !configs.isError && !items.length ? (
          <div className="customers-empty ussd-menus-empty">
            <p className="customers-empty-title">No menu configuration yet</p>
            <p className="customers-empty-copy">
              Create a draft to set the welcome message and the three main options customers see on
              dial-in.
            </p>
            <button
              type="button"
              className="config-btn"
              onClick={() => createDraft.mutate()}
              disabled={createDraft.isPending}
            >
              Create first draft
            </button>
          </div>
        ) : null}

        {!isLoading && !configs.isError && items.length > 0 && active ? (
          <div className="ussd-menus">
            <aside className="ussd-menus-aside" aria-label="Configuration versions">
              <div className="ussd-menus-aside-label">Versions</div>
              <ul className="ussd-config-list">
                {items.map((cfg) => {
                  const isActive = active.id === cfg.id;
                  return (
                    <li key={cfg.id}>
                      <button
                        type="button"
                        className={`ussd-config-row${isActive ? " is-active" : ""}`}
                        onClick={() => syncEditor(cfg)}
                        aria-current={isActive ? "true" : undefined}
                      >
                        <span className="ussd-config-row-copy">
                          <strong>v{cfg.version}</strong>
                          <span>{cfg.name}</span>
                        </span>
                        <span
                          className={`customers-status-badge customers-status-badge--${statusTone(cfg.status)}`}
                        >
                          <span className="customers-status-dot__mark" aria-hidden="true" />
                          {cfg.status}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </aside>

            <div className="ussd-menus-editor">
              <div className="ussd-section-head">
                <div>
                  <h3 className="ussd-section-title">
                    {active.status === "DRAFT" ? "Edit draft" : "Published menu"} v{active.version}
                  </h3>
                  <p className="ussd-section-sub">{active.name}</p>
                </div>
                <div className="ussd-actions">
                  <button
                    type="button"
                    className="config-btn config-btn--ghost"
                    onClick={() => save.mutate()}
                    disabled={active.status !== "DRAFT" || save.isPending}
                  >
                    {save.isPending ? "Saving…" : "Save draft"}
                  </button>
                  <button
                    type="button"
                    className="config-btn"
                    onClick={() => publish.mutate()}
                    disabled={active.status !== "DRAFT" || publish.isPending}
                  >
                    {publish.isPending ? "Publishing…" : "Publish"}
                  </button>
                </div>
              </div>

              <div className="config-form">
                <label className="config-field config-field--wide">
                  <span>Welcome text</span>
                  <input
                    value={welcome}
                    onChange={(e) => setWelcome(e.target.value)}
                    disabled={active.status !== "DRAFT"}
                  />
                </label>
                <label className="config-field config-field--wide">
                  <span>Main menu options (JSON)</span>
                  <textarea
                    rows={14}
                    value={optionsJson}
                    onChange={(e) => setOptionsJson(e.target.value)}
                    disabled={active.status !== "DRAFT"}
                    spellCheck={false}
                  />
                </label>
              </div>

              {actionError ? (
                <p className="customers-empty-copy" role="alert">
                  {errMessage(actionError)}
                </p>
              ) : null}
              <p className="ussd-help">
                Workflow actions must be MOTOR_QUOTE, REPORT_CLAIM or FOLLOW_UP_CLAIM. Active
                sessions stay on their pinned configuration version after publish.
              </p>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

type SimStep = { input: string; responseType: string };

/** Map a keypad reply to the option label shown on the previous USSD screen. */
function resolveSimHistoryLabel(previousScreen: string, raw: string): string {
  const trimmed = raw.trim();
  if (!trimmed) return "Start";
  if (!previousScreen) return trimmed;
  for (const line of previousScreen.split("\n")) {
    const option = line.match(/^(\d{1,2})\.\s+(.+)$/);
    if (option && option[1] === trimmed) {
      return `${option[1]}. ${option[2].trim()}`;
    }
    const more = line.match(/^(99)\s+(.+)$/);
    if (more && more[1] === trimmed) {
      return `${more[1]} ${more[2].trim()}`;
    }
  }
  return trimmed;
}

function SimulatorPanel() {
  const [sessionId, setSessionId] = useState("");
  const [msisdn, setMsisdn] = useState("0712345678");
  const [input, setInput] = useState(USSD_SERVICE_CODE);
  const [screen, setScreen] = useState("");
  const [responseType, setResponseType] = useState("");
  const [history, setHistory] = useState<SimStep[]>([]);
  const screenRef = useRef(screen);
  screenRef.current = screen;
  const started = Boolean(sessionId || screen);

  const send = useMutation({
    mutationFn: async (payload: { text?: string | null; restart?: boolean }) => {
      const res = await ussdApi.simulator({
        session_id: payload.restart ? undefined : sessionId || undefined,
        msisdn,
        text: payload.restart ? null : payload.text,
        restart: payload.restart,
        service_code: USSD_SERVICE_CODE,
      });
      return res.data;
    },
    onSuccess: (data, vars) => {
      const previousScreen = screenRef.current;
      setSessionId(data.session_id);
      setScreen(data.text);
      setResponseType(data.response_type);
      const label = vars.restart
        ? USSD_SERVICE_CODE
        : resolveSimHistoryLabel(previousScreen, vars.text ?? "");
      setHistory((prev) =>
        (vars.restart ? [] : prev)
          .concat({ input: label, responseType: data.response_type })
          .slice(-12),
      );
      setInput("");
    },
  });

  function submitInput() {
    if (!started) {
      send.mutate({ restart: true });
      return;
    }
    send.mutate({ text: input });
  }

  function endSession() {
    setSessionId("");
    setScreen("");
    setResponseType("");
    setHistory([]);
    setInput(USSD_SERVICE_CODE);
  }

  return (
    <div className="config-card config-card--scene ussd-sim-card">
      <div className="config-card-body">
        <header className="config-scene-header ussd-sim-header">
          <div className="ussd-sim-header-copy">
            <h2 className="config-scene-title">Phone simulator</h2>
            <p className="config-scene-lead">
              Safe test dials, excluded from production analytics.
            </p>
          </div>
          <button
            type="button"
            className="config-btn"
            onClick={() => send.mutate({ restart: true })}
            disabled={send.isPending}
          >
            {started ? "Restart session" : "Start session"}
          </button>
        </header>

        <div className="ussd-sim-layout">
          <div className="ussd-phone" aria-label="USSD phone simulator">
            <div className="ussd-phone-btn ussd-phone-btn--silent" aria-hidden="true" />
            <div className="ussd-phone-btn ussd-phone-btn--vol-up" aria-hidden="true" />
            <div className="ussd-phone-btn ussd-phone-btn--vol-down" aria-hidden="true" />
            <div className="ussd-phone-btn ussd-phone-btn--power" aria-hidden="true" />

            <div className="ussd-phone-shell">
              <div className="ussd-phone-glass">
                <div className="ussd-phone-island" aria-hidden="true" />

                <div className="ussd-phone-statusbar" aria-hidden="true">
                  <span className="ussd-phone-time">9:41</span>
                  <span className="ussd-phone-indicators">
                    <span className="ussd-phone-signal" />
                    <span className="ussd-phone-wifi" />
                    <span className="ussd-phone-battery" />
                  </span>
                </div>

                <div className="ussd-phone-stage">
                  <div className="ussd-phone-screen">
                    <div className="ussd-phone-screen-label">
                      <span>StarServe</span>
                      <span>
                        {responseType === "END"
                          ? "Session ended"
                          : started
                            ? "USSD"
                            : "Ready"}
                      </span>
                    </div>
                    <div className="ussd-phone-screen-body">
                      {send.isPending ? (
                        <SimulatorScreenSkeleton />
                      ) : screen ? (
                        <UssdScreenText text={screen} />
                      ) : (
                        <p className="ussd-phone-screen-idle">
                          Dial <strong>{USSD_SERVICE_CODE}</strong>, then tap{" "}
                          <strong>Call</strong>.
                        </p>
                      )}
                    </div>
                    <div className="ussd-phone-screen-reply">
                      <input
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        placeholder={started ? "Reply…" : USSD_SERVICE_CODE}
                        disabled={send.isPending || responseType === "END"}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") submitInput();
                        }}
                        aria-label="USSD reply"
                      />
                    </div>
                  </div>

                  <div className="ussd-phone-touchpad">
                    <div className="ussd-keypad" aria-label="On-screen keypad">
                      {(
                        [
                          ["1", ""],
                          ["2", "ABC"],
                          ["3", "DEF"],
                          ["4", "GHI"],
                          ["5", "JKL"],
                          ["6", "MNO"],
                          ["7", "PQRS"],
                          ["8", "TUV"],
                          ["9", "WXYZ"],
                          ["*", ""],
                          ["0", "+"],
                          ["#", ""],
                        ] as const
                      ).map(([key, letters]) => (
                        <button
                          key={key}
                          type="button"
                          className={[
                            letters ? "" : "ussd-keypad-key--solo",
                            key === "*" ? "ussd-keypad-key--star" : "",
                          ]
                            .filter(Boolean)
                            .join(" ") || undefined}
                          disabled={responseType === "END"}
                          onClick={() => setInput((v) => v + key)}
                        >
                          <span>{key}</span>
                          {letters ? <small>{letters}</small> : null}
                        </button>
                      ))}
                    </div>
                    <div className="ussd-phone-actions">
                      <button
                        type="button"
                        className="ussd-phone-action ussd-phone-action--back"
                        onClick={() => {
                          if (started) endSession();
                          else setInput((v) => v.slice(0, -1));
                        }}
                        disabled={send.isPending || (!started && !input)}
                        aria-label={started ? "End session" : "Delete digit"}
                      >
                        <svg
                          className="ussd-phone-action-icon"
                          viewBox="0 0 24 24"
                          aria-hidden="true"
                        >
                          <path
                            fill="currentColor"
                            d="M19 5H9.5L2.7 12l6.8 7H19a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2Z"
                          />
                        </svg>
                      </button>
                      <button
                        type="button"
                        className="ussd-phone-action ussd-phone-action--call"
                        onClick={submitInput}
                        disabled={
                          send.isPending ||
                          (started && responseType !== "END" && !input.trim()) ||
                          responseType === "END"
                        }
                        aria-label={started ? "Send reply" : "Start session"}
                      >
                        <span>{send.isPending ? "…" : started ? "OK" : "Call"}</span>
                      </button>
                    </div>
                  </div>

                  <div className="ussd-phone-home" aria-hidden="true" />
                </div>
              </div>
            </div>
          </div>

          <div className="ussd-sim-side">
            <label className="config-field">
              <span>Test MSISDN</span>
              <input
                value={msisdn}
                onChange={(e) => setMsisdn(e.target.value)}
                inputMode="tel"
                autoComplete="tel"
              />
            </label>

            <div className="ussd-sim-meta">
              <div>
                <span className="ussd-menus-aside-label">Session</span>
                <p className="ussd-mono">{sessionId || "Not started"}</p>
              </div>
              <div>
                <span className="ussd-menus-aside-label">Response</span>
                <p>
                  <span
                    className={`customers-status-badge customers-status-badge--${
                      responseType === "END" ? "inactive" : responseType ? "active" : "neutral"
                    }`}
                  >
                    <span className="customers-status-dot__mark" aria-hidden="true" />
                    {responseType || "Idle"}
                  </span>
                </p>
              </div>
            </div>

            <div className="ussd-sim-history">
              <div className="ussd-section-head">
                <h3 className="ussd-section-title">Step history</h3>
              </div>
              {history.length ? (
                <ol className="ussd-history-list">
                  {history.map((step, idx) => (
                    <li key={`${idx}-${step.input}-${step.responseType}`}>
                      <span className="ussd-history-step">{idx + 1}</span>
                      <span className="ussd-history-copy">
                        <strong>{step.input}</strong>
                        <span>{step.responseType}</span>
                      </span>
                    </li>
                  ))}
                </ol>
              ) : (
                <div className="customers-empty ussd-sim-history-empty">
                  <p className="customers-empty-title">No steps yet</p>
                  <p className="customers-empty-copy">
                    Start a session, then use the keypad or type a reply.
                  </p>
                </div>
              )}
            </div>

            {send.error ? (
              <p className="customers-empty-copy" role="alert">
                {errMessage(send.error)}
              </p>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

function AnalyticsPanel() {
  const [period, setPeriod] = useState("last_7_days");
  const [workflow, setWorkflow] = useState("MOTOR_QUOTE");
  const [traffic, setTraffic] = useState("all");
  const includeTest = traffic === "all";
  const query = useQuery({
    queryKey: ["ussd-analytics", period, workflow, includeTest],
    queryFn: async () => (await ussdApi.analytics(period, workflow, includeTest)).data,
  });
  const overview = (query.data?.overview || {}) as Record<string, unknown>;
  const funnel = query.data?.funnel as
    | {
        stages?: Array<Record<string, unknown>>;
        insight?: string;
        summary?: Record<string, unknown>;
      }
    | null
    | undefined;
  const stages = funnel?.stages || [];
  // When a workflow is selected, cards follow that funnel (same source as the table).
  const cards = (funnel?.summary || overview) as Record<string, unknown>;
  const sessionsCount = Number(cards.sessions ?? cards.total_sessions ?? 0);
  const completionRate = String(cards.session_completion_rate ?? 0);
  const abandonmentRate = String(cards.session_abandonment_rate ?? 0);

  return (
    <div className="config-card config-card--scene ussd-panel ussd-analytics-card">
      <div className="config-card-body">
        <header className="config-scene-header ussd-analytics-header">
          <div className="ussd-analytics-header-copy">
            <h2 className="config-scene-title">Analytics</h2>
            <p className="config-scene-lead">
              {includeTest
                ? "Session and funnel metrics, including simulator tests."
                : "Session and funnel metrics for live dials only."}
            </p>
          </div>
          <div className="ussd-analytics-filters config-form">
            <Select
              label="Period"
              fieldClassName="config-field"
              value={period}
              onChange={setPeriod}
              options={ANALYTICS_PERIOD_OPTIONS}
              searchable={false}
            />
            <Select
              label="Workflow"
              fieldClassName="config-field"
              value={workflow}
              onChange={setWorkflow}
              options={ANALYTICS_WORKFLOW_OPTIONS}
              searchable={false}
            />
            <Select
              label="Traffic"
              fieldClassName="config-field"
              value={traffic}
              onChange={setTraffic}
              options={ANALYTICS_TRAFFIC_OPTIONS}
              searchable={false}
            />
          </div>
        </header>

        {query.error ? (
          <p className="customers-empty-copy" role="alert">
            {errMessage(query.error)}
          </p>
        ) : null}

        {query.isLoading ? (
          <>
            <div className="customers-stat-grid ussd-analytics-stats" aria-busy="true">
              <UssdStatCardSkeleton count={4} />
            </div>
            <div className="ussd-analytics-table-block">
              <div className="ussd-section-head ussd-analytics-table-head">
                <h3 className="ussd-section-title">Funnel steps</h3>
                <p className="ussd-section-sub">
                  {
                    ANALYTICS_WORKFLOW_OPTIONS.find((option) => option.value === workflow)?.label ||
                    "Workflow"
                  }
                </p>
              </div>
              <UssdTableSkeleton columns={5} rows={7} />
            </div>
          </>
        ) : (
          <>
            <div className="customers-stat-grid ussd-analytics-stats" aria-live="polite">
              <article className="customers-stat-card">
                <span className="customers-stat-label">Sessions</span>
                <strong className="customers-stat-value">
                  {sessionsCount.toLocaleString()}
                </strong>
              </article>
              <article className="customers-stat-card">
                <span className="customers-stat-label">Completion</span>
                <strong className="customers-stat-value">{completionRate}%</strong>
              </article>
              <article className="customers-stat-card">
                <span className="customers-stat-label">Abandonment</span>
                <strong className="customers-stat-value">{abandonmentRate}%</strong>
              </article>
              <article className="customers-stat-card">
                <span className="customers-stat-label">Duplicates</span>
                <strong className="customers-stat-value">
                  {Number(overview.duplicate_callbacks ?? 0).toLocaleString()}
                </strong>
              </article>
            </div>

            {funnel?.insight ? <p className="ussd-insight">{funnel.insight}</p> : null}

            <div className="ussd-analytics-table-block">
              <div className="ussd-section-head ussd-analytics-table-head">
                <h3 className="ussd-section-title">Funnel steps</h3>
                <p className="ussd-section-sub">
                  {
                    ANALYTICS_WORKFLOW_OPTIONS.find((option) => option.value === workflow)?.label ||
                    "Workflow"
                  }
                </p>
              </div>

              {stages.length ? (
                <div className="customers-table-wrap">
                  <table className="customers-table">
                    <thead>
                      <tr>
                        <th scope="col">Step</th>
                        <th scope="col">Entered</th>
                        <th scope="col">Completed</th>
                        <th scope="col">Validation fail</th>
                        <th scope="col">Abandon %</th>
                      </tr>
                    </thead>
                    <tbody>
                      {stages.map((row) => (
                        <tr key={String(row.step_id)}>
                          <td>{String(row.step_id)}</td>
                          <td>{String(row.entered ?? 0)}</td>
                          <td>{String(row.completed ?? 0)}</td>
                          <td>{String(row.validation_failed ?? 0)}</td>
                          <td>{String(row.step_abandonment_rate ?? 0)}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : !query.error ? (
                <div className="customers-empty ussd-analytics-empty">
                  <p className="customers-empty-title">No funnel events yet</p>
                  <p className="customers-empty-copy">
                    {includeTest
                      ? "Run the phone simulator, or wait for live dials in this period."
                      : "No live dials in this period. Switch Traffic to Live + simulator to see test runs."}
                  </p>
                </div>
              ) : null}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function formatSessionWhen(value: unknown) {
  const raw = String(value || "").trim();
  if (!raw) return "—";
  return raw.slice(0, 19).replace("T", " ");
}

function SessionDetailSkeleton() {
  return (
    <div className="ussd-session-detail" aria-busy="true" aria-hidden="true">
      <div className="ussd-session-detail-grid">
        {Array.from({ length: 8 }, (_, index) => (
          <div key={`ussd-session-skel-${index}`} className="ussd-session-detail-block">
            <span className="skeleton-block skeleton-block--meta ussd-skel-field-label" />
            <span className="skeleton-block skeleton-block--title ussd-skel-meta-value ussd-skel-meta-value--wide" />
          </div>
        ))}
      </div>
      <div className="ussd-session-detail-block">
        <span className="skeleton-block skeleton-block--meta ussd-skel-field-label" />
        <span className="skeleton-block ussd-skel-textarea" />
      </div>
    </div>
  );
}

function SessionDetailBody({ data }: { data: Record<string, unknown> }) {
  const answers = (data.answers || {}) as Record<string, unknown>;
  const answerEntries = Object.entries(answers).filter(
    ([, value]) => value !== null && value !== undefined && String(value).trim() !== "",
  );
  const lastMessage = String(data.last_message || "").trim();

  return (
    <div className="ussd-session-detail">
      <div className="ussd-session-detail-grid">
        <div className="ussd-session-detail-block">
          <span className="ussd-session-detail-label">Status</span>
          <span
            className={`customers-status-badge customers-status-badge--${statusTone(String(data.status || ""))}`}
          >
            <span className="customers-status-dot__mark" aria-hidden="true" />
            {String(data.status || "—").replaceAll("_", " ")}
          </span>
        </div>
        <div className="ussd-session-detail-block">
          <span className="ussd-session-detail-label">Source</span>
          <span
            className={`customers-status-badge customers-status-badge--${
              data.is_test ? "pending" : "active"
            }`}
          >
            <span className="customers-status-dot__mark" aria-hidden="true" />
            {data.is_test ? "Test" : "Live"}
          </span>
        </div>
        <div className="ussd-session-detail-block">
          <span className="ussd-session-detail-label">MSISDN</span>
          <strong className="ussd-session-detail-value ussd-mono">
            {String(data.msisdn_masked || "—")}
          </strong>
        </div>
        <div className="ussd-session-detail-block">
          <span className="ussd-session-detail-label">Workflow</span>
          <strong className="ussd-session-detail-value">
            {workflowLabel(data.workflow_action)}
          </strong>
        </div>
        <div className="ussd-session-detail-block">
          <span className="ussd-session-detail-label">Step</span>
          <strong className="ussd-session-detail-value">
            {String(data.workflow_step || data.current_screen_key || "—")}
          </strong>
        </div>
        <div className="ussd-session-detail-block">
          <span className="ussd-session-detail-label">Menu version</span>
          <strong className="ussd-session-detail-value">
            {data.config_version != null ? `v${data.config_version}` : "—"}
          </strong>
        </div>
        <div className="ussd-session-detail-block">
          <span className="ussd-session-detail-label">Started</span>
          <strong className="ussd-session-detail-value ussd-mono">
            {formatSessionWhen(data.created_at)}
          </strong>
        </div>
        <div className="ussd-session-detail-block">
          <span className="ussd-session-detail-label">Completed</span>
          <strong className="ussd-session-detail-value ussd-mono">
            {formatSessionWhen(data.completed_at)}
          </strong>
        </div>
      </div>

      {data.termination_reason ? (
        <div className="ussd-session-detail-block">
          <span className="ussd-session-detail-label">Termination</span>
          <p className="ussd-session-detail-copy">
            {String(data.termination_reason).replaceAll("_", " ")}
          </p>
        </div>
      ) : null}

      {lastMessage ? (
        <div className="ussd-session-detail-block">
          <span className="ussd-session-detail-label">Last message</span>
          <pre className="ussd-session-detail-message">{lastMessage}</pre>
        </div>
      ) : null}

      {answerEntries.length ? (
        <div className="ussd-session-detail-block">
          <span className="ussd-session-detail-label">Answers</span>
          <div className="ussd-session-detail-tags">
            {answerEntries.map(([key, value]) => (
              <span key={key} className="customers-tag customers-tag--kra">
                {key.replaceAll("_", " ")} · {String(value)}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      <div className="ussd-session-detail-meta">
        <span>History depth · {Number(data.history_depth ?? 0)}</span>
        {data.last_response_type ? (
          <span>Response · {String(data.last_response_type)}</span>
        ) : null}
        {data.correlation_id ? (
          <span className="ussd-mono">Corr · {String(data.correlation_id).slice(0, 12)}</span>
        ) : null}
      </div>
    </div>
  );
}

function SessionsPanel() {
  const [source, setSource] = useState("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ["ussd-sessions"],
    queryFn: async () => (await ussdApi.sessions(true)).data.items,
  });
  const detail = useQuery({
    queryKey: ["ussd-session", selectedId],
    queryFn: async () => (await ussdApi.session(String(selectedId))).data,
    enabled: Boolean(selectedId),
  });
  const rows = useMemo(() => {
    const items = query.data || [];
    if (source === "test") return items.filter((row) => Boolean(row.is_test));
    if (source === "live") return items.filter((row) => !row.is_test);
    return items;
  }, [query.data, source]);
  const selectedRow = rows.find((row) => String(row.id) === selectedId) || null;
  const detailData = detail.data || selectedRow;

  return (
    <>
      <div className="config-card config-card--scene ussd-panel ussd-sessions-card">
        <div className="config-card-body">
          <header className="config-scene-header ussd-sessions-header">
            <div className="ussd-sessions-header-copy">
              <h2 className="config-scene-title">Sessions</h2>
              <p className="config-scene-lead">Recent dial-in sessions, including simulator tests.</p>
            </div>
            <div className="ussd-sessions-filters config-form">
              <Select
                label="Source"
                fieldClassName="config-field"
                value={source}
                onChange={setSource}
                options={SESSION_SOURCE_OPTIONS}
                searchable={false}
              />
            </div>
          </header>

          {query.error ? (
            <p className="customers-empty-copy" role="alert">
              {errMessage(query.error)}
            </p>
          ) : null}

          {query.isLoading ? <UssdTableSkeleton columns={5} rows={8} /> : null}

          {!query.isLoading && rows.length ? (
            <div className="customers-table-wrap">
              <table className="customers-table ussd-sessions-table">
                <thead>
                  <tr>
                    <th scope="col">When</th>
                    <th scope="col">MSISDN</th>
                    <th scope="col">Status</th>
                    <th scope="col">Workflow</th>
                    <th scope="col">Source</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => {
                    const id = String(row.id);
                    const open = () => setSelectedId(id);
                    return (
                      <tr
                        key={id}
                        className="ussd-session-row"
                        tabIndex={0}
                        aria-label={`Open session ${String(row.msisdn_masked || id)}`}
                        onClick={open}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            open();
                          }
                        }}
                      >
                        <td className="ussd-mono">{formatSessionWhen(row.created_at)}</td>
                        <td className="ussd-mono">{String(row.msisdn_masked || "—")}</td>
                        <td>
                          <span
                            className={`customers-status-badge customers-status-badge--${statusTone(String(row.status || ""))}`}
                          >
                            <span className="customers-status-dot__mark" aria-hidden="true" />
                            {String(row.status || "—").replaceAll("_", " ")}
                          </span>
                        </td>
                        <td>{workflowLabel(row.workflow_action)}</td>
                        <td>
                          <span
                            className={`customers-status-badge customers-status-badge--${
                              row.is_test ? "pending" : "active"
                            }`}
                          >
                            <span className="customers-status-dot__mark" aria-hidden="true" />
                            {row.is_test ? "Test" : "Live"}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : !query.isLoading && !query.error ? (
            <div className="customers-empty ussd-sessions-empty">
              <p className="customers-empty-title">No sessions yet</p>
              <p className="customers-empty-copy">Use the simulator to create test traffic.</p>
            </div>
          ) : null}
        </div>
      </div>

      <Modal
        open={Boolean(selectedId)}
        size="lg"
        title={selectedRow ? String(selectedRow.msisdn_masked || "Session") : "Session"}
        subtitle={
          selectedRow
            ? `${workflowLabel(selectedRow.workflow_action)} · ${formatSessionWhen(selectedRow.created_at)}`
            : undefined
        }
        icon={<IconPhone />}
        onClose={() => setSelectedId(null)}
        panelClassName="ussd-session-modal"
        bodyClassName="ussd-session-modal-body"
        footer={
          <button type="button" className="secondary" onClick={() => setSelectedId(null)}>
            Close
          </button>
        }
      >
        {detail.isLoading && !detail.data ? <SessionDetailSkeleton /> : null}
        {detail.error ? (
          <p className="customers-empty-copy" role="alert">
            {errMessage(detail.error)}
          </p>
        ) : null}
        {!detail.isLoading && detailData ? <SessionDetailBody data={detailData} /> : null}
      </Modal>
    </>
  );
}

function ProviderPanel() {
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ["ussd-provider"],
    queryFn: async () => (await ussdApi.provider()).data,
  });
  const [serviceCode, setServiceCode] = useState("");
  const [secret, setSecret] = useState("");
  const [kind, setKind] = useState("");
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    if (!query.data || hydrated) return;
    setKind(String(query.data.provider_kind || "BIRDVIEW"));
    setServiceCode(String(query.data.service_code || USSD_SERVICE_CODE));
    setHydrated(true);
  }, [query.data, hydrated]);

  const save = useMutation({
    mutationFn: () =>
      ussdApi.updateProvider({
        provider_kind: kind || "BIRDVIEW",
        service_code: serviceCode || USSD_SERVICE_CODE,
        auth_secret: secret || undefined,
        enabled: true,
      }),
    onSuccess: async () => {
      setSecret("");
      setHydrated(false);
      await qc.invalidateQueries({ queryKey: ["ussd-provider"] });
      await qc.invalidateQueries({ queryKey: ["ussd-audit"] });
    },
  });

  const data = query.data || {};
  const callbackPath = String(
    data.callback_url ||
      data.callback_path ||
      "https://quote.starserveinsuranceagency.com/api/v1/ussd/callback",
  );
  const secretSet = Boolean(data.has_auth_secret);

  return (
    <div className="config-card config-card--scene ussd-panel ussd-provider-card">
      <div className="config-card-body">
        <header className="config-scene-header ussd-provider-header">
          <div className="ussd-provider-header-copy">
            <h2 className="config-scene-title">Provider</h2>
            <p className="config-scene-lead">
              Birdview dial-in settings for {USSD_SERVICE_CODE}. Share the HTTPS callback URL to go
              live.
            </p>
          </div>
          <button
            type="button"
            className="config-btn"
            onClick={() => save.mutate()}
            disabled={save.isPending || query.isLoading}
          >
            {save.isPending ? "Saving…" : "Save"}
          </button>
        </header>

        {query.error ? (
          <p className="customers-empty-copy" role="alert">
            {errMessage(query.error)}
          </p>
        ) : null}

        {query.isLoading ? <ProviderBodySkeleton /> : null}

        {!query.isLoading && !query.error ? (
          <>
            <div className="ussd-provider-meta">
              <div>
                <span className="ussd-menus-aside-label">Callback URL (GET)</span>
                <p className="ussd-mono">{callbackPath}</p>
              </div>
              <div>
                <span className="ussd-menus-aside-label">Callback secret</span>
                <p>
                  <span
                    className={`customers-status-badge customers-status-badge--${
                      secretSet ? "active" : "neutral"
                    }`}
                  >
                    <span className="customers-status-dot__mark" aria-hidden="true" />
                    {secretSet ? "Set" : "Not set"}
                  </span>
                </p>
              </div>
            </div>

            <div className="config-form ussd-provider-form">
              <Select
                label="Provider kind"
                fieldClassName="config-field"
                value={kind || "BIRDVIEW"}
                onChange={setKind}
                options={PROVIDER_KIND_OPTIONS}
                searchable={false}
              />
              <label className="config-field">
                <span>Service code</span>
                <input
                  value={serviceCode}
                  onChange={(e) => setServiceCode(e.target.value)}
                  placeholder={USSD_SERVICE_CODE}
                  autoComplete="off"
                />
              </label>
              <label className="config-field config-field--wide">
                <span>Rotate callback secret</span>
                <input
                  type="password"
                  value={secret}
                  onChange={(e) => setSecret(e.target.value)}
                  placeholder="Optional for Birdview. Leave blank to keep current"
                  autoComplete="new-password"
                />
              </label>
            </div>

            <p className="ussd-help">
              Birdview calls this URL with SESSIONID, MSISDN, USSDCODE and INPUT (latest input only).
              Responses are plain text starting with CON or END, always HTTP 200.
            </p>
          </>
        ) : null}

        {save.error ? (
          <p className="customers-empty-copy" role="alert">
            {errMessage(save.error)}
          </p>
        ) : null}
        {save.isSuccess ? (
          <p className="ussd-help" role="status">
            Provider settings saved.
          </p>
        ) : null}
      </div>
    </div>
  );
}

function auditActionLabel(action: unknown) {
  const key = String(action || "").trim();
  const map: Record<string, string> = {
    "ussd.config_create": "Menu draft created",
    "ussd.config_update": "Menu draft updated",
    "ussd.config_publish": "Menu published",
    "ussd.provider_update": "Provider updated",
  };
  return map[key] || key.replace(/^ussd\./, "").replaceAll("_", " ") || "—";
}

function auditResourceLabel(resource: unknown, resourceId: unknown) {
  const name = String(resource || "").trim();
  const id = String(resourceId || "").trim();
  const pretty =
    name === "ussd_menu_config"
      ? "Menu config"
      : name === "ussd_provider_setting"
        ? "Provider"
        : name.replaceAll("_", " ") || "—";
  if (!id) return pretty;
  return `${pretty} · ${id.slice(0, 8)}`;
}

function AuditPanel() {
  const query = useQuery({
    queryKey: ["ussd-audit"],
    queryFn: async () => (await ussdApi.audit()).data?.items ?? [],
    refetchOnMount: "always",
  });
  const rows = query.data ?? [];

  return (
    <div className="config-card config-card--scene ussd-panel ussd-audit-card">
      <div className="config-card-body">
        <header className="config-scene-header ussd-audit-header">
          <div className="ussd-audit-header-copy">
            <h2 className="config-scene-title">Audit</h2>
            <p className="config-scene-lead">
              Menu publishes and provider changes for this tenant.
            </p>
          </div>
        </header>

        {query.error ? (
          <p className="customers-empty-copy" role="alert">
            {errMessage(query.error)}
          </p>
        ) : null}

        {query.isLoading ? <UssdTableSkeleton columns={4} rows={6} /> : null}

        {!query.isLoading && rows.length ? (
          <div className="customers-table-wrap">
            <table className="customers-table">
              <thead>
                <tr>
                  <th scope="col">When</th>
                  <th scope="col">Action</th>
                  <th scope="col">Resource</th>
                  <th scope="col">Actor</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={String(row.id)}>
                    <td className="ussd-mono">
                      {String(row.created_at || "").slice(0, 19).replace("T", " ") || "—"}
                    </td>
                    <td>{auditActionLabel(row.action)}</td>
                    <td>
                      <span className="ussd-clip" title={String(row.resource_id || "")}>
                        {auditResourceLabel(row.resource, row.resource_id)}
                      </span>
                    </td>
                    <td>
                      {row.actor_name
                        ? String(row.actor_name)
                        : row.actor_user_id
                          ? String(row.actor_user_id).slice(0, 8)
                          : "System"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : !query.isLoading && !query.error ? (
          <div className="customers-empty ussd-audit-empty">
            <p className="customers-empty-title">No audit events yet</p>
            <p className="customers-empty-copy">
              Menu publishes and provider updates will appear here.
            </p>
          </div>
        ) : null}
      </div>
    </div>
  );
}
