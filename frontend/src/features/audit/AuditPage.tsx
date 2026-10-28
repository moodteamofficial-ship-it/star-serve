import { useQuery } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode, type SVGProps } from "react";
import { Modal } from "@/components/ui/Modal";
import {
  IconAlert,
  IconBadge,
  IconChevronRight,
  IconFileText,
  IconSearch,
  IconUser,
} from "@/components/ui/icons";
import { auditApi, type AuditEvent } from "@/services/audit/auditApi";
import { mediaSrc } from "@/services/media/mediaSrc";

const PAGE_SIZE = 10;

function IconChevronLeft(props: SVGProps<SVGSVGElement>) {
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
      aria-hidden="true"
      {...props}
    >
      <path d="m14.5 6-6 6 6 6" />
    </svg>
  );
}

function ucwords(value: string | null | undefined) {
  if (!value) return "";
  return value
    .replace(/[._]/g, " ")
    .trim()
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function resultTone(result: string) {
  const key = result.trim().toUpperCase();
  if (key === "SUCCESS" || key === "OK" || key === "ALLOWED") return "active";
  if (key === "DENIED" || key === "FAILED" || key === "ERROR" || key === "REJECTED") {
    return "inactive";
  }
  if (key === "PENDING" || key === "PARTIAL") return "pending";
  return "neutral";
}

function formatShortDateTime(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatTimeAgo(value: string | null | undefined, nowMs: number) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  const seconds = Math.round((nowMs - date.getTime()) / 1000);
  if (seconds < 5) return "Just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  const weeks = Math.floor(days / 7);
  if (weeks < 5) return `${weeks}w ago`;
  return date.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function shortId(value?: string | null) {
  if (!value) return null;
  return value.slice(0, 8);
}

function actorLabel(row: AuditEvent) {
  const name = row.actor_name?.trim();
  if (name) return name;
  if (row.user_id) return `User ${shortId(row.user_id)}`;
  return "System";
}

function ActorAvatar({ row }: { row: AuditEvent }) {
  const [imgFailed, setImgFailed] = useState(false);
  const trimmed = mediaSrc(row.actor_avatar_url) || "";
  const showPhoto = Boolean(trimmed) && !imgFailed;
  const label = actorLabel(row);

  useEffect(() => {
    setImgFailed(false);
  }, [trimmed]);

  if (showPhoto) {
    return (
      <img
        src={trimmed}
        alt=""
        className="customers-avatar customers-avatar--photo"
        onError={() => setImgFailed(true)}
      />
    );
  }

  if (!row.user_id) {
    return (
      <span className="customers-avatar customers-avatar--empty" aria-hidden="true" title={label}>
        <IconBadge />
      </span>
    );
  }

  return (
    <span className="customers-avatar customers-avatar--empty" aria-hidden="true" title={label}>
      <IconUser />
    </span>
  );
}

/** Turn auth.refresh / intermediary.create into a readable past-tense clause. */
function actionClause(action: string, resource: string) {
  const raw = action.trim().toLowerCase();
  const known: Record<string, string> = {
    "auth.login": "signed in",
    "auth.logout": "signed out",
    "auth.refresh": "refreshed their session",
    "auth.unlock": "unlocked their session",
    "insurance.reference_sync": "synced insurance reference data",
    "wallet.debit": "debited the wallet",
    "wallet.top_up": "topped up the wallet",
    "wallet.topup": "topped up the wallet",
    "policy.activate_via_payment": "activated a policy via payment",
    "certificate.generate": "generated a certificate",
    "intermediary.create": "created an intermediary",
    "intermediary.approve": "approved an intermediary",
    "customer.create": "created a customer",
    "proposal.create": "created a proposal",
    "proposal.approve": "approved a proposal",
    "payment.initiate": "initiated a payment",
    "notification.send": "sent a notification",
    "report.run": "ran a report",
  };
  if (known[raw]) return known[raw];

  const parts = raw.split(".");
  const verb = parts.at(-1) || raw;
  const verbMap: Record<string, string> = {
    create: "created",
    update: "updated",
    delete: "deleted",
    approve: "approved",
    reject: "rejected",
    cancel: "cancelled",
    activate: "activated",
    generate: "generated",
    sync: "synced",
    send: "sent",
    retry: "retried",
    debit: "debited",
    credit: "credited",
    login: "signed in",
    logout: "signed out",
    refresh: "refreshed",
    run: "ran",
  };
  const past = verbMap[verb] || ucwords(verb).toLowerCase();
  const resourceLabel = ucwords(resource || parts[0] || "resource").toLowerCase();
  if (["signed in", "signed out"].includes(past)) return past;
  return `${past} ${resourceLabel}`;
}

function activitySummary(row: AuditEvent) {
  return `${actorLabel(row)} ${actionClause(row.action, row.resource)}`;
}

function DirectoryCard({
  children,
  footer,
}: {
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="config-card config-card--scene">
      <div className="config-card-body">{children}</div>
      {footer ? <div className="config-card-footer">{footer}</div> : null}
    </div>
  );
}

function DirectorySkeleton({ count = 5 }: { count?: number }) {
  return (
    <div className="customers-table-wrap" aria-busy="true">
      <table className="customers-table audit-table">
        <thead>
          <tr>
            <th scope="col">Activity</th>
            <th scope="col">Result</th>
            <th scope="col">Resource</th>
            <th scope="col">When</th>
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: count }, (_, index) => (
            <tr key={`audit-skeleton-${index}`} className="customers-table-row--skeleton">
              <td>
                <div className="customers-table-person">
                  <span className="skeleton-block customers-avatar-skeleton" />
                  <div className="customers-table-person-text">
                    <span className="skeleton-block skeleton-block--title" />
                    <span className="skeleton-block customers-meta-skeleton" />
                  </div>
                </div>
              </td>
              <td>
                <span className="skeleton-block customers-status-skeleton" />
              </td>
              <td>
                <span className="skeleton-block skeleton-block--meta" />
              </td>
              <td>
                <span className="skeleton-block skeleton-block--meta" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function AuditPage() {
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [viewTarget, setViewTarget] = useState<AuditEvent | null>(null);
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    setPage(1);
  }, [q]);

  useEffect(() => {
    const id = window.setInterval(() => setNowMs(Date.now()), 30_000);
    return () => window.clearInterval(id);
  }, []);

  const list = useQuery({
    queryKey: ["audit", q, page],
    queryFn: async () =>
      (await auditApi.list({ q: q || undefined, page, limit: PAGE_SIZE })).data,
    placeholderData: (previous) => previous,
  });

  const items = list.data?.items ?? [];
  const total = list.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const rangeStart = total === 0 ? 0 : (safePage - 1) * PAGE_SIZE + 1;
  const rangeEnd = total === 0 ? 0 : Math.min(safePage * PAGE_SIZE, total);
  const canPrev = safePage > 1;
  const canNext = safePage < totalPages;
  const successCount = items.filter((row) => row.result.toUpperCase() === "SUCCESS").length;
  const failedCount = items.filter((row) =>
    ["FAILED", "DENIED", "ERROR", "REJECTED"].includes(row.result.toUpperCase()),
  ).length;
  const authCount = items.filter((row) => row.action.toLowerCase().startsWith("auth.")).length;

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  const footer = (
    <div className="customers-footer">
      <div className="customers-pager-meta customers-footer-range">
        {total === 0 ? "0 of 0" : `${rangeStart}–${rangeEnd} of ${total}`}
      </div>
      <div className="customers-pager" aria-label="Audit pagination">
        <button
          type="button"
          className="customers-pager-btn"
          aria-label="Previous page"
          disabled={!canPrev || list.isFetching}
          onClick={() => setPage((p) => Math.max(1, p - 1))}
        >
          <IconChevronLeft />
        </button>
        <span className="customers-pager-page" aria-current="page">
          {safePage}
        </span>
        <button
          type="button"
          className="customers-pager-btn"
          aria-label="Next page"
          disabled={!canNext || list.isFetching}
          onClick={() => setPage((p) => p + 1)}
        >
          <IconChevronRight />
        </button>
      </div>
    </div>
  );

  return (
    <section className="config-page customers-page audit-page">
      <h1 className="config-title">Audit logs</h1>

      <div className="customers-top">
        <div className="customers-stat-grid" aria-live="polite">
          <article className="customers-stat-card">
            <span className="customers-stat-label">All events</span>
            <strong className="customers-stat-value">{total.toLocaleString()}</strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Success</span>
            <strong className="customers-stat-value">{successCount.toLocaleString()}</strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Failed</span>
            <strong className="customers-stat-value">{failedCount.toLocaleString()}</strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Auth</span>
            <strong className="customers-stat-value">{authCount.toLocaleString()}</strong>
          </article>
        </div>

        <div className="customers-search-card">
          <label className="config-field customers-search">
            <span className="config-sr-only">Search audit events</span>
            <span className="customers-search-shell">
              <IconSearch className="customers-search-icon" />
              <input
                type="search"
                placeholder="Search action or resource"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                autoComplete="off"
              />
            </span>
          </label>
        </div>
      </div>

      <div className="config-stage config-stage--fill">
        <DirectoryCard footer={footer}>
          {list.isLoading && !list.data ? <DirectorySkeleton /> : null}

          {list.isError ? (
            <div className="customers-empty" role="alert">
              <span className="customers-empty-icon is-error" aria-hidden="true">
                <IconAlert />
              </span>
              <p className="customers-empty-title">Couldn’t load audit events</p>
              <p className="customers-empty-copy">Try again in a moment.</p>
            </div>
          ) : null}

          {!(list.isLoading && !list.data) && !list.isError ? (
            items.length > 0 ? (
              <div className="customers-table-wrap">
                <table className="customers-table audit-table">
                  <thead>
                    <tr>
                      <th scope="col">Activity</th>
                      <th scope="col">Result</th>
                      <th scope="col">Resource</th>
                      <th scope="col">When</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((row) => {
                      const idHint = shortId(row.resource_id);
                      const absolute = formatShortDateTime(row.created_at);
                      return (
                        <tr key={row.id}>
                          <td>
                            <button
                              type="button"
                              className="audit-row-btn"
                              onClick={() => setViewTarget(row)}
                            >
                              <span className="customers-table-person">
                                <ActorAvatar row={row} />
                                <span className="customers-table-person-text">
                                  <span className="customers-table-name">
                                    {activitySummary(row)}
                                  </span>
                                  <span className="customers-table-meta">
                                    <span className="customers-tag customers-tag--id">
                                      {ucwords(row.action)}
                                    </span>
                                  </span>
                                </span>
                              </span>
                            </button>
                          </td>
                          <td>
                            <span
                              className={`customers-status-badge customers-status-badge--${resultTone(row.result)}`}
                            >
                              <span className="customers-status-dot__mark" aria-hidden="true" />
                              {ucwords(row.result)}
                            </span>
                          </td>
                          <td>
                            <div className="audit-resource">
                              <span className="customers-tag audit-resource-badge">
                                {ucwords(row.resource)}
                              </span>
                              {idHint ? (
                                <span className="customers-tag customers-tag--id">{idHint}</span>
                              ) : null}
                            </div>
                          </td>
                          <td>
                            <time
                              className="customers-date-badge audit-time-ago"
                              dateTime={row.created_at}
                              title={absolute}
                            >
                              {formatTimeAgo(row.created_at, nowMs)}
                            </time>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="customers-empty" role="status">
                <span className="customers-empty-icon" aria-hidden="true">
                  {q.trim() ? <IconSearch /> : <IconFileText />}
                </span>
                <p className="customers-empty-title">
                  {q.trim() ? "No matches" : "No audit events yet"}
                </p>
                <p className="customers-empty-copy">
                  {q.trim()
                    ? "Try another action or resource."
                    : "Tenant events will appear here as they are recorded."}
                </p>
              </div>
            )
          ) : null}
        </DirectoryCard>
      </div>

      <Modal
        open={Boolean(viewTarget)}
        size="lg"
        title={viewTarget ? activitySummary(viewTarget) : "Event"}
        subtitle={
          viewTarget
            ? `${ucwords(viewTarget.result)} · ${formatTimeAgo(viewTarget.created_at, nowMs)} · ${formatShortDateTime(viewTarget.created_at)}`
            : undefined
        }
        icon={<IconBadge />}
        onClose={() => setViewTarget(null)}
        bodyClassName="intermediaries-modal-body"
        footer={
          <button type="button" className="secondary" onClick={() => setViewTarget(null)}>
            Close
          </button>
        }
      >
        {viewTarget ? (
          <div className="audit-detail">
            <div className="audit-detail-block">
              <span className="audit-detail-label">Actor</span>
              <div className="audit-detail-actor">
                <ActorAvatar row={viewTarget} />
                <strong className="audit-detail-value">{actorLabel(viewTarget)}</strong>
              </div>
            </div>
            <div className="audit-detail-block">
              <span className="audit-detail-label">Action</span>
              <strong className="audit-detail-value">{ucwords(viewTarget.action)}</strong>
              <p className="audit-detail-copy">{actionClause(viewTarget.action, viewTarget.resource)}</p>
            </div>
            <div className="audit-detail-block">
              <span className="audit-detail-label">Resource</span>
              <strong className="audit-detail-value">
                {ucwords(viewTarget.resource)}
                {viewTarget.resource_id ? ` · ${viewTarget.resource_id}` : ""}
              </strong>
            </div>
            {viewTarget.message ? (
              <div className="audit-detail-block">
                <span className="audit-detail-label">Message</span>
                <p className="audit-detail-copy">{viewTarget.message}</p>
              </div>
            ) : null}
            {viewTarget.ip_address ? (
              <div className="audit-detail-block">
                <span className="audit-detail-label">IP address</span>
                <strong className="audit-detail-value audit-detail-value--mono">
                  {viewTarget.ip_address}
                </strong>
              </div>
            ) : null}
            {viewTarget.request_id ? (
              <div className="audit-detail-block">
                <span className="audit-detail-label">Request</span>
                <strong className="audit-detail-value audit-detail-value--mono">
                  {viewTarget.request_id}
                </strong>
              </div>
            ) : null}
            {viewTarget.metadata && Object.keys(viewTarget.metadata).length > 0 ? (
              <div className="audit-detail-block">
                <span className="audit-detail-label">Metadata</span>
                <div className="audit-detail-tags">
                  {Object.entries(viewTarget.metadata).map(([key, value]) => (
                    <span key={key} className="customers-tag customers-tag--kra">
                      {ucwords(key)} · {String(value)}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        ) : null}
      </Modal>
    </section>
  );
}
