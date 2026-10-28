import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/app/providers/AuthProvider";
import {
  IconAlert,
  IconBadge,
  IconCalendar,
  IconChevronDown,
  IconChevronRight,
  IconFileText,
  IconFollowUp,
  IconHome,
  IconPlus,
  IconUser,
} from "@/components/ui/icons";
import { RequiredAvatarModal } from "@/features/dashboard/RequiredAvatarModal";
import {
  overviewApi,
  type OverviewPeriodKey,
  type OverviewRecentActivity,
  type OverviewRecentApplication,
  type OverviewSummary,
} from "@/services/overview/overviewApi";
import { claimSourceLabel, claimStatusLabel, formatDay, statusBadgeClass } from "@/features/claims/status";
import { mediaSrc } from "@/services/media/mediaSrc";
import { ucwords } from "@/utils/ucwords";

const PERIODS: { key: OverviewPeriodKey; label: string }[] = [
  { key: "7d", label: "Last 7 days" },
  { key: "30d", label: "Last 30 days" },
  { key: "90d", label: "Last 90 days" },
  { key: "ytd", label: "Year to date" },
];

function formatRangeDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function formatDateRange(startIso: string, endIso: string): string {
  return `${formatRangeDate(startIso)} – ${formatRangeDate(endIso)}`;
}

function money(value: number | null | undefined, currency = "KES"): string {
  const n = Number(value ?? 0);
  if (!Number.isFinite(n)) return "—";
  return `${currency} ${n.toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  })}`;
}

function compact(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(value >= 10_000 ? 0 : 1)}k`;
  return String(value);
}

function deltaLabel(pct: number): string {
  if (pct > 0) return `↑ ${pct}%`;
  if (pct < 0) return `↓ ${Math.abs(pct)}%`;
  return "Flat";
}

function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  const diffMs = Date.now() - date.getTime();
  const mins = Math.round(diffMs / 60_000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 14) return `${days}d ago`;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function FeedAvatar({
  name,
  avatarUrl,
  fallback = "user",
}: {
  name?: string | null;
  avatarUrl?: string | null;
  fallback?: "user" | "system" | "file";
}) {
  const [imgFailed, setImgFailed] = useState(false);
  const src = mediaSrc(avatarUrl);
  const showPhoto = Boolean(src) && !imgFailed;
  const label = name?.trim() || "System";

  useEffect(() => {
    setImgFailed(false);
  }, [src]);

  if (showPhoto) {
    return (
      <img
        src={src!}
        alt=""
        className="customers-avatar customers-avatar--photo ov-feed-avatar"
        onError={() => setImgFailed(true)}
      />
    );
  }

  const Icon = fallback === "system" ? IconBadge : fallback === "file" ? IconFileText : IconUser;

  return (
    <span
      className="customers-avatar customers-avatar--empty ov-feed-avatar"
      aria-hidden="true"
      title={label}
    >
      <Icon />
    </span>
  );
}

function ActivityAvatar({ item }: { item: OverviewRecentActivity }) {
  const hasActor = Boolean(item.actor_name || item.actor_avatar_url);
  return (
    <FeedAvatar
      name={item.actor_name}
      avatarUrl={item.actor_avatar_url}
      fallback={hasActor ? "user" : item.kind === "customer" ? "user" : "system"}
    />
  );
}

function ApplicationAvatar({ app }: { app: OverviewRecentApplication }) {
  return (
    <FeedAvatar
      name={app.customer_name}
      avatarUrl={app.customer_avatar_url}
      fallback={app.customer_name ? "user" : "file"}
    />
  );
}

function OverviewCardHeadSkeleton({ withAction = true }: { withAction?: boolean }) {
  return (
    <header className="ov-card-head">
      <span className="skeleton-block skeleton-block--title ov-skel-title" />
      {withAction ? <span className="skeleton-block skeleton-block--meta ov-skel-chip" /> : null}
    </header>
  );
}

function OverviewStatStripSkeleton({
  count = 5,
  variant = "strip",
}: {
  count?: number;
  variant?: "strip" | "volume";
}) {
  return (
    <div className={variant === "volume" ? "ov-volume-stats" : "ov-stat-strip"}>
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="ov-stat">
          <span className="skeleton-block skeleton-block--meta" />
          <strong className="skeleton-block skeleton-block--title ov-skel-stat" />
        </div>
      ))}
    </div>
  );
}

function OverviewBarsSkeleton({ count = 12 }: { count?: number }) {
  const heights = [38, 62, 48, 74, 56, 84, 44, 70, 52, 66, 40, 78];
  return (
    <div className="ov-bars" aria-hidden="true">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="ov-bar">
          <span className="skeleton-block ov-skel-bar" style={{ height: `${heights[i % heights.length]}%` }} />
        </div>
      ))}
    </div>
  );
}

function OverviewFeedSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <ul className="ov-feed" aria-hidden="true">
      {Array.from({ length: rows }, (_, i) => (
        <li key={i}>
          <div className="ov-feed-row">
            <span className="skeleton-block customers-avatar-skeleton ov-feed-avatar" />
            <div className="ov-feed-copy">
              <span className="skeleton-block skeleton-block--title" />
              <span className="skeleton-block skeleton-block--meta" />
            </div>
            <div className="ov-feed-meta">
              <span className="skeleton-block skeleton-block--meta ov-skel-chip" />
              <span className="skeleton-block skeleton-block--meta ov-skel-time" />
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}

function OverviewBoardSkeleton() {
  return (
    <>
      <div className="overview-grid" aria-busy="true">
        <article className="ov-card ov-card--claims ov-card--skeleton">
          <OverviewCardHeadSkeleton />
          <div className="ov-volume-hero">
            <span className="skeleton-block ov-skel-metric" />
            <span className="skeleton-block skeleton-block--meta" />
          </div>
          <OverviewStatStripSkeleton count={3} />
          <OverviewStatStripSkeleton count={3} />
        </article>

        <article className="ov-card ov-card--followups ov-card--skeleton">
          <OverviewCardHeadSkeleton />
          <div className="ov-volume-hero">
            <span className="skeleton-block ov-skel-metric" />
            <span className="skeleton-block skeleton-block--meta" />
          </div>
          <OverviewStatStripSkeleton count={3} />
        </article>

        <article className="ov-card ov-card--book ov-card--skeleton">
          <OverviewCardHeadSkeleton />
          <div className="ov-volume-hero">
            <span className="skeleton-block ov-skel-metric" />
            <span className="skeleton-block skeleton-block--meta" />
          </div>
          <OverviewStatStripSkeleton count={3} />
          <OverviewStatStripSkeleton count={3} />
        </article>

        <article className="ov-card ov-card--payments ov-card--skeleton">
          <OverviewCardHeadSkeleton />
          <OverviewStatStripSkeleton count={5} />
          <OverviewBarsSkeleton count={14} />
        </article>

        <article className="ov-card ov-card--volume ov-card--skeleton">
          <OverviewCardHeadSkeleton />
          <div className="ov-volume-hero">
            <span className="skeleton-block ov-skel-metric" />
            <span className="skeleton-block skeleton-block--meta" />
          </div>
          <OverviewStatStripSkeleton count={3} />
          <div className="ov-breakdown ov-skel-breakdown">
            {Array.from({ length: 3 }, (_, i) => (
              <div key={i} className="ov-skel-track-row">
                <span className="skeleton-block skeleton-block--meta" />
                <span className="skeleton-block ov-skel-track" />
              </div>
            ))}
          </div>
        </article>

        <article className="ov-card ov-card--split ov-card--skeleton">
          <div className="ov-split-row">
            <OverviewCardHeadSkeleton />
            <div className="ov-split-copy">
              <span className="skeleton-block ov-skel-metric ov-skel-metric--sm" />
              <span className="skeleton-block skeleton-block--meta" />
              <span className="skeleton-block skeleton-block--meta" />
            </div>
            <div className="ov-spark is-empty" aria-hidden="true">
              {Array.from({ length: 7 }, (_, i) => (
                <span key={i} className="skeleton-block ov-skel-spark" />
              ))}
            </div>
          </div>
          <div className="ov-split-row">
            <OverviewCardHeadSkeleton />
            <div className="ov-split-copy">
              <span className="skeleton-block ov-skel-metric ov-skel-metric--sm" />
              <span className="skeleton-block skeleton-block--meta" />
            </div>
            <div className="ov-spark is-empty" aria-hidden="true">
              {Array.from({ length: 7 }, (_, i) => (
                <span key={i} className="skeleton-block ov-skel-spark" />
              ))}
            </div>
          </div>
        </article>
      </div>

      <div className="overview-secondary" aria-busy="true">
        <article className="ov-card ov-card--feed ov-card--applications ov-card--skeleton">
          <OverviewCardHeadSkeleton />
          <OverviewFeedSkeleton rows={5} />
        </article>

        <article className="ov-card ov-card--feed ov-card--activity ov-card--skeleton">
          <OverviewCardHeadSkeleton />
          <OverviewFeedSkeleton rows={5} />
        </article>
      </div>
    </>
  );
}

function sparkBars(values: number[], tone: "green" | "blue" | "ink" = "green") {
  const max = Math.max(...values, 1);
  const hasData = values.some((v) => v > 0);
  return (
    <div className={`ov-spark ov-spark--${tone}${hasData ? "" : " is-empty"}`} aria-hidden="true">
      {values.map((v, i) => (
        <span key={i} style={{ height: `${hasData ? Math.max(10, (v / max) * 100) : 12}%` }} />
      ))}
    </div>
  );
}

function OverviewStatCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <article className="customers-stat-card">
      <span className="customers-stat-label">{label}</span>
      <strong className="customers-stat-value">{value}</strong>
      {hint ? <span className="overview-stat-hint">{hint}</span> : null}
    </article>
  );
}

function OverviewStatCardSkeleton() {
  return (
    <article className="customers-stat-card customers-stat-card--skeleton" aria-hidden="true">
      <span className="customers-stat-label">
        <span className="skeleton-block ov-skel-stat-label" />
      </span>
      <strong className="customers-stat-value">
        <span className="skeleton-block ov-skel-stat-value" />
      </strong>
      <span className="overview-stat-hint">
        <span className="skeleton-block ov-skel-stat-hint" />
      </span>
    </article>
  );
}

function periodVolumeStats(data: OverviewSummary | undefined) {
  if (!data) return [];
  const cards: { label: string; value: string; hint?: string }[] = [];
  if (data.capabilities.customers && data.customers) {
    cards.push({
      label: "Customers",
      value: compact(data.customers.created_in_period),
      hint: `${compact(data.customers.total)} on file`,
    });
  }
  if (data.capabilities.proposals && data.proposals) {
    cards.push({
      label: "Proposals",
      value: compact(data.proposals.created_in_period),
      hint: `${compact(data.proposals.converted_in_period)} converted · ${compact(data.proposals.in_pipeline)} open`,
    });
  }
  if (data.capabilities.policies && data.policies) {
    cards.push({
      label: "Policies",
      value: compact(data.policies.created_in_period),
      hint: `${compact(data.policies.active)} in force`,
    });
  }
  if (data.capabilities.certificates && data.certificates) {
    cards.push({
      label: "Certificates",
      value: compact(data.certificates.generated_in_period),
      hint: data.certificates.pending
        ? `${compact(data.certificates.pending)} pending`
        : `${compact(data.certificates.generated)} generated`,
    });
  }
  return cards;
}

function headlineStats(data: OverviewSummary | undefined, agentView = false) {
  if (!data) return [];
  const cards: { label: string; value: string; hint?: string }[] = [];
  const currency =
    (typeof data.headline.currency === "string" && data.headline.currency) ||
    data.premium?.currency ||
    data.policies?.currency ||
    data.wallet?.currency ||
    "KES";

  if (data.capabilities.claims && data.claims) {
    cards.push({
      label: "Open claims",
      value: compact(data.claims.open),
      hint: agentView
        ? `${compact(data.claims.created_in_period)} opened in period`
        : data.followups?.overdue
          ? `${compact(data.followups.overdue)} overdue follow-ups`
          : `${compact(data.claims.unassigned)} unassigned`,
    });
  }
  if (data.capabilities.policies && data.policies) {
    cards.push({
      label: "Expiring 30d",
      value: compact(data.policies.expiring_30d),
      hint: `${compact(data.policies.pending_payment)} awaiting pay`,
    });
  }
  if (data.capabilities.proposals && data.proposals) {
    cards.push({
      label: "Pipeline premium",
      value: money(data.proposals.pipeline_premium, data.proposals.currency),
      hint: `${data.proposals.issuance_pct}% issuance ready`,
    });
  }
  if (data.capabilities.certificates && data.certificates && data.certificates.pending > 0) {
    cards.push({
      label: "Certificates",
      value: compact(data.certificates.pending),
      hint: `${compact(data.certificates.generated)} generated`,
    });
  }
  if (data.capabilities.policies && data.policies) {
    cards.push({
      label: "In-force premium",
      value: money(data.policies.in_force_premium, currency),
      hint: `${compact(data.policies.active)} active policies`,
    });
  }
  if (data.premium) {
    cards.push({
      label: "Collected",
      value: money(data.premium.gross, currency),
      hint: deltaLabel(data.premium.volume_delta_pct),
    });
  } else if (data.capabilities.payments && data.payments) {
    cards.push({
      label: "Settled",
      value: compact(data.payments.successful),
      hint: `${data.payments.success_rate}% success`,
    });
  } else if (data.wallet) {
    cards.push({
      label: "Wallet",
      value: money(data.wallet.available_balance, data.wallet.currency),
      hint: ucwords(data.wallet.status),
    });
  }
  if (data.capabilities.customers && data.customers) {
    cards.push({
      label: "Customers",
      value: compact(data.customers.total),
      hint: `+${compact(data.customers.created_in_period)} in period`,
    });
  }
  if (data.capabilities.certificates && data.certificates && data.certificates.pending <= 0) {
    cards.push({
      label: "Certificates",
      value: compact(data.certificates.generated),
      hint: `${compact(data.certificates.pending)} pending`,
    });
  }
  return cards.slice(0, 4);
}

export function DashboardPage() {
  const { hasPermission, user } = useAuth();
  const isSalesAgent = user?.role_code === "sales_agent";
  const [period, setPeriod] = useState<OverviewPeriodKey>("30d");
  const [periodMenuOpen, setPeriodMenuOpen] = useState(false);
  const periodMenuRef = useRef<HTMLDivElement>(null);

  const canQuote = hasPermission("proposal:create");

  useEffect(() => {
    if (!periodMenuOpen) return;
    function onPointerDown(event: MouseEvent) {
      if (!periodMenuRef.current?.contains(event.target as Node)) {
        setPeriodMenuOpen(false);
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setPeriodMenuOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [periodMenuOpen]);

  const summary = useQuery({
    queryKey: ["overview", "summary", period],
    queryFn: async () => (await overviewApi.summary(period)).data,
  });

  const data = summary.data;
  const caps = data?.capabilities;
  const stats = useMemo(() => headlineStats(data, isSalesAgent), [data, isSalesAgent]);
  const periodStats = useMemo(() => periodVolumeStats(data), [data]);
  const showClaims = Boolean(caps?.claims ?? hasPermission("claim:read"));
  const showClaimsCard = Boolean(showClaims && data?.claims);
  // Follow-ups are desk tasks; sales agents only open and track their own claims.
  const showFollowups = Boolean(showClaims && data?.followups && !isSalesAgent);
  const showBook = Boolean(caps?.policies && data?.policies);
  const showPayments = Boolean(caps?.payments && data?.payments);
  const showVolume = Boolean(data?.premium || (caps?.wallet && data?.wallet));
  const showSplit = Boolean((caps?.customers && data?.customers) || (caps?.agents && data?.agents));
  // The named-area layout assumes every card; otherwise flow cards into even columns.
  const autoGrid = !(
    showClaimsCard &&
    showFollowups &&
    showBook &&
    showPayments &&
    showVolume &&
    showSplit
  );
  const promoCta: { to: string; label: string; lead: boolean } | null =
    canQuote || caps?.quote
      ? { to: "/app/quote", label: "New quote", lead: true }
      : caps?.products
        ? { to: "/app/products", label: "Browse products", lead: false }
        : caps?.claim_create
          ? { to: "/app/claims/new", label: "Open a claim", lead: true }
          : null;

  const paymentBars = useMemo(() => {
    const daily = data?.payments?.daily ?? [];
    const max = Math.max(...daily.map((d) => d.count), 1);
    return daily.map((d) => ({
      height: d.count ? Math.max(8, (d.count / max) * 100) : 6,
      ok: d.count ? d.success / d.count : 0,
      count: d.count,
    }));
  }, [data?.payments?.daily]);

  const weekCustomerSpark = data?.customers?.week ?? [0, 0, 0, 0, 0, 0, 0];
  const weekClaimSpark = data?.claims?.week ?? [0, 0, 0, 0, 0, 0, 0];

  const hasAnySection = Boolean(data?.sections?.length);
  const hasSecondarySection = Boolean(
    data?.recent_applications?.length || data?.recent_activity?.length,
  );
  const loading = !summary.isError && (summary.isPending || (summary.isFetching && !data));

  return (
    <section className="config-page customers-page overview-page">
      <RequiredAvatarModal />
      <div className="overview-head">
        <h1 className="config-title">Overview</h1>
        <div className="overview-period" ref={periodMenuRef}>
          <div className="overview-range">
            <button
              type="button"
              className={`overview-range-btn${periodMenuOpen ? " is-open" : ""}`}
              aria-haspopup="listbox"
              aria-expanded={periodMenuOpen}
              onClick={() => setPeriodMenuOpen((open) => !open)}
            >
              <IconCalendar />
              <span>
                {data
                  ? formatDateRange(data.period.start, data.period.end)
                  : PERIODS.find((p) => p.key === period)?.label}
              </span>
              <IconChevronDown />
            </button>
            {periodMenuOpen ? (
              <div className="overview-range-menu" role="listbox" aria-label="Select period">
                {PERIODS.map((p) => (
                  <button
                    key={p.key}
                    type="button"
                    role="option"
                    aria-selected={period === p.key}
                    className={`overview-range-option${period === p.key ? " is-active" : ""}`}
                    onClick={() => {
                      setPeriod(p.key);
                      setPeriodMenuOpen(false);
                    }}
                  >
                    <span>{p.label}</span>
                  </button>
                ))}
              </div>
            ) : null}
          </div>
          {data ? (
            <>
              <span className="overview-compared">compared to</span>
              <div className="overview-range-btn overview-range-btn--static" aria-hidden="true">
                <IconCalendar />
                <span>{formatDateRange(data.period.compare_start, data.period.compare_end)}</span>
              </div>
            </>
          ) : loading ? (
            <>
              <span className="overview-compared">compared to</span>
              <span className="skeleton-block ov-skel-toolbar-range" aria-hidden="true" />
            </>
          ) : null}
        </div>
      </div>

      <div className="customers-top">
        {stats.length || loading ? (
          <div
            className="customers-stat-grid overview-stat-grid"
            aria-live={stats.length ? "polite" : undefined}
            aria-busy={loading || undefined}
          >
            <div className="overview-stat-metrics">
              {stats.length
                ? stats.map((card) => <OverviewStatCard key={card.label} {...card} />)
                : Array.from({ length: 4 }, (_, i) => <OverviewStatCardSkeleton key={i} />)}
            </div>
            {loading && !stats.length ? (
              <div className="ov-promo ov-promo--feature ov-card--skeleton" aria-hidden="true">
                <span className="skeleton-block ov-skel-promo-media" />
                <div className="ov-promo-copy">
                  <span className="skeleton-block skeleton-block--meta" />
                  <span className="skeleton-block skeleton-block--title" />
                  <span className="skeleton-block ov-skel-cta" />
                </div>
              </div>
            ) : (
              <article className="ov-promo ov-promo--feature">
                <div className="ov-promo-media">
                  <img
                    src={`${import.meta.env.BASE_URL}starserve-quote-promo.jpg?v=2`}
                    alt="Star Serve Insurance Agency reception"
                  />
                </div>
                <div className="ov-promo-copy">
                  <div className="ov-promo-heading">
                    <p className="ov-promo-kicker">Star Serve</p>
                    <strong>Digital car insurance</strong>
                  </div>
                  {promoCta ? (
                    <Link
                      className="config-btn customers-toolbar-add ov-promo-cta"
                      to={promoCta.to}
                    >
                      {promoCta.lead ? (
                        <>
                          <IconPlus />
                          {promoCta.label}
                        </>
                      ) : (
                        <>
                          {promoCta.label}
                          <IconChevronRight />
                        </>
                      )}
                    </Link>
                  ) : null}
                </div>
              </article>
            )}
          </div>
        ) : null}
        {periodStats.length || (loading && !periodStats.length) ? (
          <div
            className="overview-period-metrics"
            aria-label="Totals in the selected period"
            aria-live={periodStats.length ? "polite" : undefined}
            aria-busy={loading || undefined}
          >
            {periodStats.length
              ? periodStats.map((card) => <OverviewStatCard key={card.label} {...card} />)
              : Array.from({ length: 4 }, (_, i) => <OverviewStatCardSkeleton key={i} />)}
          </div>
        ) : null}
      </div>

      <div className="config-stage">
      {summary.isError ? (
        <div className="config-card config-card--scene">
          <div className="config-card-body">
            <div className="customers-empty" role="alert">
              <span className="customers-empty-icon is-error" aria-hidden="true">
                <IconAlert />
              </span>
              <p className="customers-empty-title">Couldn’t load overview</p>
              <p className="customers-empty-copy">Try again in a moment.</p>
            </div>
          </div>
        </div>
      ) : null}

      {!summary.isError && !loading && !hasAnySection ? (
        <div className="config-card config-card--scene">
          <div className="config-card-body">
            <div className="customers-empty" role="status">
              <span className="customers-empty-icon" aria-hidden="true">
                <IconHome />
              </span>
              <p className="customers-empty-title">Nothing to show yet</p>
              <p className="customers-empty-copy">
                Your role doesn’t include portfolio or finance read access. Ask an admin if you
                need overview metrics.
              </p>
            </div>
          </div>
        </div>
      ) : null}

      {!summary.isError && loading ? <OverviewBoardSkeleton /> : null}

      {!summary.isError && !loading && hasAnySection ? (
        <div className={`overview-grid${autoGrid ? " overview-grid--auto" : ""}`}>
          {showClaimsCard && data?.claims ? (
            <article className="ov-card ov-card--claims">
              <header className="ov-card-head">
                <h2 className="config-scene-title">{isSalesAgent ? "My claims" : "Claims desk"}</h2>
                <Link to="/app/claims" className="ov-more">
                  View claims
                  <IconChevronRight />
                </Link>
              </header>
              <div className="ov-volume-hero">
                <p className="ov-hero-metric">{compact(data.claims.open)}</p>
                <p className="ov-muted">
                  Open files · {money(data.claims.claimed_open, data.claims.currency)} claimed
                  {data.claims.approved_open
                    ? ` · ${money(data.claims.approved_open, data.claims.currency)} approved`
                    : ""}
                </p>
              </div>
              <div className="ov-volume-stats">
                <div className="ov-stat">
                  <span>Intake</span>
                  <strong>{compact(data.claims.intake)}</strong>
                </div>
                <div className="ov-stat">
                  <span>Assessing</span>
                  <strong>{compact(data.claims.assessing)}</strong>
                </div>
                <div className="ov-stat">
                  <span>With insurer</span>
                  <strong>{compact(data.claims.with_insurer)}</strong>
                </div>
              </div>
              {isSalesAgent ? (
                <div className="ov-volume-stats">
                  <div className="ov-stat">
                    <span>Settling</span>
                    <strong>{compact(data.claims.settling)}</strong>
                  </div>
                  <div className="ov-stat">
                    <span>Opened in period</span>
                    <strong>{compact(data.claims.created_in_period)}</strong>
                  </div>
                  <div className="ov-stat">
                    <span>Closed in period</span>
                    <strong>{compact(data.claims.closed_in_period)}</strong>
                  </div>
                </div>
              ) : (
                <>
                  <div className="ov-volume-stats">
                    <div className="ov-stat">
                      <span>Settling</span>
                      <strong>{compact(data.claims.settling)}</strong>
                    </div>
                    <div className="ov-stat">
                      <span>Unassigned</span>
                      <strong>{compact(data.claims.unassigned)}</strong>
                    </div>
                    <div className="ov-stat">
                      <span>Guest files</span>
                      <strong>{compact(data.claims.guest_open)}</strong>
                    </div>
                  </div>
                  <div className="ov-volume-stats">
                    <div className="ov-stat">
                      <span>Opened in period</span>
                      <strong>{compact(data.claims.created_in_period)}</strong>
                    </div>
                    <div className="ov-stat">
                      <span>Closed in period</span>
                      <strong>{compact(data.claims.closed_in_period)}</strong>
                    </div>
                    <div className="ov-stat">
                      <span>Guest intake</span>
                      <strong>{compact(data.claims.guest_intake)}</strong>
                    </div>
                  </div>
                </>
              )}
              {!isSalesAgent && data.claims.queues.some((row) => row.count > 0) ? (
                <ul className="ov-breakdown">
                  {data.claims.queues.map((row) => (
                    <li key={row.key}>
                      <div>
                        <strong>{row.label}</strong>
                        <span>
                          {compact(row.count)}
                          <em>{money(row.amount, data.claims!.currency)}</em>
                        </span>
                      </div>
                      <div className="ov-track">
                        <i
                          className="ov-track-fill ov-track-fill--green"
                          style={{
                            width: `${Math.max(
                              8,
                              Math.round((row.count / Math.max(data.claims!.open, 1)) * 100),
                            )}%`,
                          }}
                        />
                      </div>
                    </li>
                  ))}
                </ul>
              ) : null}
              {data.claims.recent.length ? (
                <ul className="ov-feed ov-claims-feed">
                  {data.claims.recent.map((row) => (
                    <li key={row.id}>
                      <Link to={`/app/claims/${row.id}`} className="ov-feed-row">
                        <div className="ov-feed-copy">
                          <strong>{row.claim_number}</strong>
                          <span>
                            {[
                              row.customer_name || "Unnamed claimant",
                              row.vehicle_registration,
                              money(row.claimed_amount, row.currency),
                            ]
                              .filter(Boolean)
                              .join(" · ")}
                          </span>
                        </div>
                        <div className="ov-feed-meta">
                          <span className={statusBadgeClass(row.status)}>{claimStatusLabel(row.status)}</span>
                          <em>
                            {row.assigned ? row.assigned_to_name || "Assigned" : "Unassigned"}
                            {row.channel === "GUEST" ? ` · ${claimSourceLabel(row.channel)}` : ""}
                          </em>
                        </div>
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="ov-muted ov-empty-inline">
                  {isSalesAgent ? "None of your claims are open." : "No open claims on the desk."}
                </p>
              )}
              {sparkBars(weekClaimSpark, "green")}
              {caps?.claim_create ? (
                <Link className="ov-insight-cta" to="/app/claims/new">
                  <IconPlus />
                  Open a claim
                </Link>
              ) : null}
            </article>
          ) : null}

          {showFollowups && data?.followups ? (
            <article className="ov-card ov-card--followups">
              <header className="ov-card-head">
                <h2 className="config-scene-title">Follow-ups</h2>
                <Link to="/app/claims" className="ov-more">
                  View tasks
                  <IconChevronRight />
                </Link>
              </header>
              <div className="ov-insight-hero">
                <p className="ov-hero-metric">{compact(data.followups.open)}</p>
                <p className="ov-muted">
                  Open tasks
                  {data.followups.overdue ? ` · ${compact(data.followups.overdue)} overdue` : ""}
                  {data.followups.due_soon ? ` · ${compact(data.followups.due_soon)} due this week` : ""}
                </p>
              </div>
              <div className="ov-volume-stats ov-insight-stats">
                <div className="ov-stat">
                  <span>Waiting on client</span>
                  <strong>{compact(data.followups.waiting_client)}</strong>
                </div>
                <div className="ov-stat">
                  <span>Waiting on desk</span>
                  <strong>{compact(data.followups.waiting_desk)}</strong>
                </div>
                <div className="ov-stat">
                  <span>Done in period</span>
                  <strong>{compact(data.followups.completed_in_period)}</strong>
                </div>
              </div>
              {data.followups.by_type.length ? (
                <ul className="ov-breakdown">
                  {data.followups.by_type.map((row) => (
                    <li key={row.type}>
                      <div>
                        <strong>{row.label}</strong>
                        <span>
                          {compact(row.count)}
                          <em>open</em>
                        </span>
                      </div>
                      <div className="ov-track">
                        <i
                          className="ov-track-fill ov-track-fill--green"
                          style={{
                            width: `${Math.max(
                              8,
                              Math.round((row.count / Math.max(data.followups!.open, 1)) * 100),
                            )}%`,
                          }}
                        />
                      </div>
                    </li>
                  ))}
                </ul>
              ) : null}
              {data.followups.recent.length ? (
                <ul className="ov-feed ov-claims-feed">
                  {data.followups.recent.map((row) => (
                    <li key={row.id}>
                      <Link to={`/app/claims/${row.claim_id}`} className="ov-feed-row">
                        <div className="ov-feed-copy">
                          <strong>{row.subject}</strong>
                          <span>
                            {[row.claim_number, row.customer_name, row.label].filter(Boolean).join(" · ")}
                          </span>
                        </div>
                        <div className="ov-feed-meta">
                          <span className={statusBadgeClass(row.overdue ? "OVERDUE" : row.due_at ? "DUE_SOON" : "OPEN")}>
                            {row.overdue ? "Overdue" : row.due_at ? `Due ${formatDay(row.due_at)}` : "Open"}
                          </span>
                          <em>{row.status === "PENDING_CLIENT" ? "Waiting on client" : "Waiting on desk"}</em>
                        </div>
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="ov-empty-panel" role="status">
                  <span className="ov-empty-panel-icon" aria-hidden="true">
                    <IconFollowUp />
                  </span>
                  <p className="ov-empty-panel-title">No open follow-ups</p>
                  <p className="ov-muted">The desk is clear — new tasks will show up here.</p>
                </div>
              )}
            </article>
          ) : null}

          {caps?.policies && data?.policies ? (
            <article className="ov-card ov-card--book">
              <header className="ov-card-head">
                <h2 className="config-scene-title">Book of business</h2>
                <Link to="/app/policies" className="ov-more">
                  View policies
                  <IconChevronRight />
                </Link>
              </header>
              <div className="ov-volume-hero">
                <p className="ov-hero-metric">
                  {money(data.policies.in_force_premium, data.policies.currency)}
                </p>
                <p className="ov-muted">
                  In-force premium · sum insured {money(data.policies.sum_insured, data.policies.currency)}
                </p>
              </div>
              <div className="ov-volume-stats">
                <div className="ov-stat">
                  <span>Active</span>
                  <strong>{compact(data.policies.active)}</strong>
                </div>
                <div className="ov-stat">
                  <span>Expiring 30d</span>
                  <strong>{compact(data.policies.expiring_30d)}</strong>
                </div>
                <div className="ov-stat">
                  <span>Avg premium</span>
                  <strong>{money(data.policies.avg_in_force_premium, data.policies.currency)}</strong>
                </div>
              </div>
              <div className="ov-volume-stats">
                <div className="ov-stat">
                  <span>Awaiting pay</span>
                  <strong>{compact(data.policies.pending_payment)}</strong>
                </div>
                <div className="ov-stat">
                  <span>Awaiting cert</span>
                  <strong>{compact(data.policies.pending_certificate)}</strong>
                </div>
                <div className="ov-stat">
                  <span>Cancelled</span>
                  <strong>{compact(data.policies.cancelled_in_period)}</strong>
                </div>
              </div>
              {data.policies.top_products.length ? (
                <ul className="ov-breakdown">
                  {data.policies.top_products.map((p) => (
                    <li key={p.code}>
                      <div>
                        <strong>{p.code}</strong>
                        <span>
                          {compact(p.count)}
                          <em>in force</em>
                        </span>
                      </div>
                      <div className="ov-track">
                        <i
                          className="ov-track-fill ov-track-fill--green"
                          style={{
                            width: `${Math.max(
                              8,
                              Math.round((p.count / Math.max(data.policies!.active, 1)) * 100),
                            )}%`,
                          }}
                        />
                      </div>
                    </li>
                  ))}
                </ul>
              ) : null}
            </article>
          ) : null}

          {caps?.payments && data?.payments ? (
            <article className="ov-card ov-card--payments">
              <header className="ov-card-head">
                <h2 className="config-scene-title">Payments</h2>
                <Link to="/app/payments" className="ov-more">
                  View payments
                  <IconChevronRight />
                </Link>
              </header>

              <div className="ov-stat-strip">
                <div className="ov-stat">
                  <span>Initiated</span>
                  <strong>{compact(data.payments.initiated)}</strong>
                </div>
                <div className="ov-stat">
                  <span>Successful</span>
                  <strong>{compact(data.payments.successful)}</strong>
                </div>
                <div className="ov-stat">
                  <span>Pending</span>
                  <strong>{compact(data.payments.pending)}</strong>
                </div>
                <div className="ov-stat">
                  <span>Failed</span>
                  <strong>{compact(data.payments.failed)}</strong>
                </div>
                <div className="ov-stat ov-stat--accent">
                  <span>Success rate</span>
                  <strong>{data.payments.success_rate}%</strong>
                </div>
              </div>

              {paymentBars.some((b) => b.count > 0) ? (
                <div className="ov-bars" role="img" aria-label="Payment volume by day">
                  {paymentBars.map((bar, i) => (
                    <div key={i} className="ov-bar" title={`${bar.count} payments`}>
                      <span className="ov-bar-fill" style={{ height: `${bar.height}%` }}>
                        <i style={{ height: `${Math.max(10, bar.ok * 100)}%` }} />
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="ov-muted ov-empty-inline">No payment activity in this period.</p>
              )}
            </article>
          ) : null}

          {data?.premium ? (
            <article className="ov-card ov-card--volume">
              <header className="ov-card-head">
                <h2 className="config-scene-title">Gross premium</h2>
                <span className="ov-badge">{deltaLabel(data.premium.volume_delta_pct)}</span>
              </header>

              <div className="ov-volume-hero">
                <p className="ov-hero-metric">{money(data.premium.gross, data.premium.currency)}</p>
                <p className="ov-muted">Settled premium collected in this period</p>
              </div>

              <div className="ov-volume-stats">
                <div className="ov-stat">
                  <span>Settled</span>
                  <strong>{compact(data.premium.settled)}</strong>
                </div>
                <div className="ov-stat">
                  <span>Avg premium</span>
                  <strong>{money(data.premium.avg, data.premium.currency)}</strong>
                </div>
                {data.premium.wallet_balance != null ? (
                  <div className="ov-stat">
                    <span>Wallet cash</span>
                    <strong>{money(data.premium.wallet_balance, data.premium.currency)}</strong>
                  </div>
                ) : null}
              </div>

              <ul className="ov-breakdown">
                {data.premium.channels
                  .filter((ch) => ch.amount > 0 || ch.key === "online" || ch.key === "wallet")
                  .map((ch) => (
                    <li key={ch.key}>
                      <div>
                        <strong>{ch.label}</strong>
                        <span>
                          {money(ch.amount, data.premium!.currency)}
                          <em>{ch.share}%</em>
                        </span>
                      </div>
                      <div className="ov-track">
                        <i
                          className={`ov-track-fill ov-track-fill--${
                            ch.key === "online" ? "green" : ch.key === "wallet" ? "blue" : "soft"
                          }`}
                          style={{ width: `${Math.max(ch.share, ch.amount > 0 ? 4 : 0)}%` }}
                        />
                      </div>
                    </li>
                  ))}
              </ul>
            </article>
          ) : caps?.wallet && data?.wallet ? (
            <article className="ov-card ov-card--volume">
              <header className="ov-card-head">
                <h2 className="config-scene-title">Agency wallet</h2>
              </header>
              <div className="ov-volume-hero">
                <p className="ov-hero-metric">
                  {money(data.wallet.available_balance, data.wallet.currency)}
                </p>
                <p className="ov-muted">Available balance · {ucwords(data.wallet.status)}</p>
              </div>
              <div className="ov-volume-stats">
                <div className="ov-stat">
                  <span>Ledger</span>
                  <strong>{money(data.wallet.ledger_balance, data.wallet.currency)}</strong>
                </div>
              </div>
              <Link to="/app/payments" className="ov-insight-cta">
                Open payments
                <IconChevronRight />
              </Link>
            </article>
          ) : null}

          {(caps?.customers && data?.customers) || (caps?.agents && data?.agents) ? (
            <article className="ov-card ov-card--split">
              {caps?.customers && data?.customers ? (
                <div className="ov-split-row">
                  <header className="ov-card-head ov-split-head">
                    <h2 className="config-scene-title">Customers</h2>
                    <Link to="/app/customers" className="ov-more">
                      View customers
                      <IconChevronRight />
                    </Link>
                  </header>
                  <div className="ov-split-copy">
                    <p className="ov-hero-metric ov-hero-metric--sm">
                      {compact(data.customers.total)}
                    </p>
                    <p className="ov-muted">
                      {data.customers.active} active · {data.customers.with_kra} with KRA ·{" "}
                      {data.customers.linked} linked
                    </p>
                    <p className="ov-muted">
                      +{data.customers.created_in_period} in period
                      {data.customers.peak_weekday
                        ? ` · peak ${data.customers.peak_weekday}`
                        : ""}
                    </p>
                  </div>
                  {sparkBars(weekCustomerSpark, "blue")}
                </div>
              ) : null}
              {caps?.agents && data?.agents ? (
                <div className="ov-split-row">
                  <header className="ov-card-head ov-split-head">
                    <h2 className="config-scene-title">Intermediaries</h2>
                    <Link to="/app/intermediaries" className="ov-more">
                      View agents
                      <IconChevronRight />
                    </Link>
                  </header>
                  <div className="ov-split-copy">
                    <p className="ov-hero-metric ov-hero-metric--sm">
                      {compact(data.agents.approved)}
                    </p>
                    <p className="ov-muted">
                      {data.agents.pending} pending · {data.agents.suspended} suspended · +
                      {data.agents.created_in_period} in period
                    </p>
                  </div>
                  {sparkBars(
                    [
                      data.agents.approved,
                      data.agents.pending,
                      data.agents.suspended,
                      data.agents.rejected,
                      data.agents.created_in_period,
                      data.agents.total,
                      data.agents.approved,
                    ],
                    "green",
                  )}
                </div>
              ) : null}
            </article>
          ) : null}
        </div>
      ) : null}

      {!summary.isError && !loading && hasSecondarySection ? (
        <div className="overview-secondary">
          {data?.recent_applications?.length ? (
            <article className="ov-card ov-card--feed ov-card--applications">
              <header className="ov-card-head">
                <h2 className="config-scene-title">Recent applications</h2>
                <Link to="/app/proposals" className="ov-more">
                  View proposals
                  <IconChevronRight />
                </Link>
              </header>
              <ul className="ov-feed">
                {data.recent_applications.slice(0, 5).map((app) => (
                  <li key={app.id}>
                    <div className="ov-feed-row">
                      <ApplicationAvatar app={app} />
                      <div className="ov-feed-copy">
                        <strong>{app.customer_name || app.product_code}</strong>
                        <span>
                          {app.product_code}
                          {app.cover_option ? ` · ${ucwords(app.cover_option)}` : ""} ·{" "}
                          {money(app.gross_premium, app.currency)}
                        </span>
                      </div>
                      <div className="ov-feed-meta">
                        <span className={statusBadgeClass(app.status)}>
                          {ucwords(app.status)}
                        </span>
                        <em>{relativeTime(app.updated_at || app.created_at)}</em>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </article>
          ) : null}

          {data?.recent_activity?.length ? (
            <article className="ov-card ov-card--feed ov-card--activity">
              <header className="ov-card-head">
                <h2 className="config-scene-title">Recent activity</h2>
                {caps?.audit ? (
                  <Link to="/app/audit" className="ov-more">
                    View audit
                    <IconChevronRight />
                  </Link>
                ) : null}
              </header>
              <ul className="ov-feed">
                {data.recent_activity.slice(0, 5).map((item) => (
                  <li key={item.id}>
                    <div className="ov-feed-row">
                      <ActivityAvatar item={item} />
                      <div className="ov-feed-copy">
                        <strong>{ucwords(item.title)}</strong>
                        <span>
                          {ucwords(item.detail)}
                          {item.actor_name ? ` · ${item.actor_name}` : ""}
                        </span>
                      </div>
                      <div className="ov-feed-meta">
                        <span className={statusBadgeClass(item.result)}>
                          {ucwords(item.result)}
                        </span>
                        <em>{relativeTime(item.created_at)}</em>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </article>
          ) : null}

        </div>
      ) : null}
      </div>
    </section>
  );
}
