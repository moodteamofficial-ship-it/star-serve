import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode, type SVGProps } from "react";
import { Modal } from "@/components/ui/Modal";
import {
  IconAlert,
  IconBriefcase,
  IconChevronRight,
  IconGrid,
  IconSearch,
  IconWarning,
} from "@/components/ui/icons";
import { platformApi } from "@/services/platform/platformApi";
import { tenantApi, type TenantSettings } from "@/services/tenants/tenantApi";

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

function statusLabel(status: string) {
  const key = status.trim().toUpperCase();
  if (key === "ACTIVE") return "Active";
  if (key === "SUSPENDED") return "Suspended";
  if (key === "DISABLED") return "Disabled";
  if (key === "ARCHIVED") return "Archived";
  return status
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function statusTone(status: string) {
  const key = status.trim().toUpperCase();
  if (key === "ACTIVE") return "active";
  if (key === "SUSPENDED") return "suspended";
  if (key === "DISABLED" || key === "ARCHIVED") return "inactive";
  return "neutral";
}

function dbModeLabel(mode: string) {
  const key = mode.trim().toUpperCase();
  if (key === "SHARED_DATABASE" || key === "SHARED") return "Shared";
  if (key === "DEDICATED_DATABASE" || key === "DEDICATED") return "Dedicated";
  return mode
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function dbModeTone(mode: string) {
  const key = mode.trim().toUpperCase();
  if (key.includes("DEDICATED")) return "suspended";
  return "neutral";
}

function AgencyAvatar({ name }: { name: string }) {
  return (
    <span className="customers-avatar customers-avatar--empty" aria-hidden="true" title={name}>
      <IconBriefcase />
    </span>
  );
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
      <table className="customers-table platform-table">
        <thead>
          <tr>
            <th scope="col">Agency</th>
            <th scope="col">Status</th>
            <th scope="col">DB mode</th>
            <th scope="col">
              <span className="config-sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: count }, (_, index) => (
            <tr key={`platform-skeleton-${index}`} className="customers-table-row--skeleton">
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

export function PlatformPage() {
  const queryClient = useQueryClient();
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [suspendTarget, setSuspendTarget] = useState<TenantSettings | null>(null);

  useEffect(() => {
    setPage(1);
  }, [q]);

  const metrics = useQuery({
    queryKey: ["platform-metrics"],
    queryFn: async () => (await platformApi.metrics()).data,
  });

  const tenants = useQuery({
    queryKey: ["platform-tenants", q, page],
    queryFn: async () =>
      (await tenantApi.list({ q: q || undefined, page, limit: PAGE_SIZE })).data,
    placeholderData: (previous) => previous,
  });

  const setStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      tenantApi.setStatus(id, status, "Platform admin action"),
    onSuccess: async () => {
      setSuspendTarget(null);
      await queryClient.invalidateQueries({ queryKey: ["platform-tenants"] });
      await queryClient.invalidateQueries({ queryKey: ["platform-metrics"] });
    },
  });

  const items = tenants.data?.items ?? [];
  const total = tenants.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const rangeStart = total === 0 ? 0 : (safePage - 1) * PAGE_SIZE + 1;
  const rangeEnd = total === 0 ? 0 : Math.min(safePage * PAGE_SIZE, total);
  const canPrev = safePage > 1;
  const canNext = safePage < totalPages;

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  const footer = (
    <div className="customers-footer">
      <div className="customers-pager-meta customers-footer-range">
        {total === 0 ? "0 of 0" : `${rangeStart}–${rangeEnd} of ${total}`}
      </div>
      <div className="customers-pager" aria-label="Agency pagination">
        <button
          type="button"
          className="customers-pager-btn"
          aria-label="Previous page"
          disabled={!canPrev || tenants.isFetching}
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
          disabled={!canNext || tenants.isFetching}
          onClick={() => setPage((p) => p + 1)}
        >
          <IconChevronRight />
        </button>
      </div>
    </div>
  );

  return (
    <section className="config-page customers-page platform-page">
      <h1 className="config-title">Platform</h1>

      <div className="customers-top">
        <div className="customers-stat-grid" aria-live="polite">
          <article className="customers-stat-card">
            <span className="customers-stat-label">Tenants</span>
            <strong className="customers-stat-value">
              {metrics.isLoading && !metrics.data
                ? "—"
                : (metrics.data?.tenants.total ?? 0).toLocaleString()}
            </strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Active</span>
            <strong className="customers-stat-value">
              {metrics.isLoading && !metrics.data
                ? "—"
                : (metrics.data?.tenants.active ?? 0).toLocaleString()}
            </strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Dedicated DB</span>
            <strong className="customers-stat-value">
              {metrics.isLoading && !metrics.data
                ? "—"
                : (metrics.data?.tenants.dedicated_database ?? 0).toLocaleString()}
            </strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Policies</span>
            <strong className="customers-stat-value">
              {metrics.isLoading && !metrics.data
                ? "—"
                : (metrics.data?.policies.total ?? 0).toLocaleString()}
            </strong>
          </article>
        </div>

        <div className="customers-search-card">
          <label className="config-field customers-search">
            <span className="config-sr-only">Search agencies</span>
            <span className="customers-search-shell">
              <IconSearch className="customers-search-icon" />
              <input
                type="search"
                placeholder="Search agencies"
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
          {tenants.isLoading && !tenants.data ? <DirectorySkeleton /> : null}

          {tenants.isError ? (
            <div className="customers-empty" role="alert">
              <span className="customers-empty-icon is-error" aria-hidden="true">
                <IconAlert />
              </span>
              <p className="customers-empty-title">Couldn’t load agencies</p>
              <p className="customers-empty-copy">Try again in a moment.</p>
            </div>
          ) : null}

          {!(tenants.isLoading && !tenants.data) && !tenants.isError ? (
            items.length > 0 ? (
              <div className="customers-table-wrap">
                <table className="customers-table platform-table">
                  <thead>
                    <tr>
                      <th scope="col">Agency</th>
                      <th scope="col">Status</th>
                      <th scope="col">DB mode</th>
                      <th scope="col">
                        <span className="config-sr-only">Actions</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((row) => {
                      const tone = statusTone(row.status);
                      const active = row.status.toUpperCase() === "ACTIVE";
                      return (
                        <tr key={row.id}>
                          <td>
                            <div className="customers-table-person">
                              <AgencyAvatar name={row.trading_name} />
                              <div className="customers-table-person-text">
                                <span className="customers-table-name">{row.trading_name}</span>
                                {row.legal_name && row.legal_name !== row.trading_name ? (
                                  <div className="customers-table-meta">
                                    <span className="customers-tag customers-tag--id">
                                      {row.legal_name}
                                    </span>
                                  </div>
                                ) : null}
                              </div>
                            </div>
                          </td>
                          <td>
                            <span
                              className={`customers-status-badge customers-status-badge--${tone}`}
                            >
                              <span className="customers-status-dot__mark" aria-hidden="true" />
                              {statusLabel(row.status)}
                            </span>
                          </td>
                          <td>
                            <span
                              className={`customers-status-badge customers-status-badge--${dbModeTone(row.database_mode)}`}
                            >
                              <span className="customers-status-dot__mark" aria-hidden="true" />
                              {dbModeLabel(row.database_mode)}
                            </span>
                          </td>
                          <td className="platform-actions">
                            {active ? (
                              <button
                                type="button"
                                className="platform-action-btn platform-action-btn--warn"
                                disabled={setStatus.isPending}
                                onClick={() => setSuspendTarget(row)}
                              >
                                Suspend
                              </button>
                            ) : (
                              <button
                                type="button"
                                className="platform-action-btn"
                                disabled={setStatus.isPending}
                                onClick={() =>
                                  setStatus.mutate({ id: row.id, status: "ACTIVE" })
                                }
                              >
                                Activate
                              </button>
                            )}
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
                  {q.trim() ? <IconSearch /> : <IconGrid />}
                </span>
                <p className="customers-empty-title">
                  {q.trim() ? "No matches" : "No agencies yet"}
                </p>
                <p className="customers-empty-copy">
                  {q.trim()
                    ? "Try another trading or legal name."
                    : "Tenant agencies will appear here when provisioned."}
                </p>
              </div>
            )
          ) : null}
        </DirectoryCard>
      </div>

      <Modal
        open={Boolean(suspendTarget)}
        title={suspendTarget ? `Suspend ${suspendTarget.trading_name}?` : "Suspend"}
        subtitle="Users on this agency will lose access until reactivated."
        icon={<IconWarning />}
        onClose={() => {
          if (!setStatus.isPending) setSuspendTarget(null);
        }}
        bodyClassName="intermediaries-modal-body"
        footer={
          <>
            <button
              type="button"
              className="secondary"
              disabled={setStatus.isPending}
              onClick={() => setSuspendTarget(null)}
            >
              Cancel
            </button>
            <button
              type="button"
              className="platform-suspend-confirm"
              disabled={setStatus.isPending || !suspendTarget}
              onClick={() => {
                if (!suspendTarget) return;
                setStatus.mutate({ id: suspendTarget.id, status: "SUSPENDED" });
              }}
            >
              {setStatus.isPending ? "Suspending…" : "Suspend"}
            </button>
          </>
        }
      >
        <p className="config-muted platform-suspend-copy">
          Users on this agency will lose access until you activate it again.
        </p>
      </Modal>
    </section>
  );
}
