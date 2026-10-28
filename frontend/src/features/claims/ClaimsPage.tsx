import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/app/providers/AuthProvider";
import { IconChevronLeft, IconChevronRight, IconClaim, IconSearch } from "@/components/ui/icons";
import { claimApi, type ClaimListItem } from "@/services/claims/claimApi";
import { claimStatusLabel, claimStatusTone, money } from "@/features/claims/status";

const PAGE_SIZE = 10;

const QUEUES: { id: string; label: string; anyOf?: string[] }[] = [
  { id: "mine", label: "My assigned" },
  { id: "intake", label: "Guest intake", anyOf: ["claim:vet", "claim:assign"] },
  { id: "vetting", label: "Vetting", anyOf: ["claim:vet"] },
  { id: "information", label: "Information", anyOf: ["claim:request_information"] },
  { id: "approval", label: "Approvals", anyOf: ["claim:approve"] },
  { id: "definite", label: "Insurer", anyOf: ["claim:forward"] },
  { id: "payment", label: "Payments", anyOf: ["claim:payment:read"] },
  { id: "payment_failed", label: "Payment failures", anyOf: ["claim:payment:read"] },
];

function formatRole(code?: string | null) {
  if (!code) return "—";
  return code.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function queueHint(queue: string) {
  if (queue === "intake") {
    return {
      title: "No guest claims waiting",
      copy: "Reports filed from the welcome screen appear here until an officer picks them up.",
    };
  }
  if (queue === "mine") {
    return {
      title: "Nothing assigned to you",
      copy: "Claims you own will show here. Guest reports start in Guest intake.",
    };
  }
  return {
    title: "This queue is clear",
    copy: "Nothing needs attention here right now.",
  };
}

function ClaimsStatsSkeleton() {
  return (
    <div className="customers-stat-grid" aria-busy="true" aria-label="Loading claim totals">
      {["Visible", "Open", "Assigned to me", "Desk"].map((label) => (
        <article key={label} className="customers-stat-card">
          <span className="customers-stat-label">{label}</span>
          <strong className="customers-stat-value">
            <span className="skeleton-block skeleton-block--title" />
          </strong>
        </article>
      ))}
    </div>
  );
}

function ClaimsTableSkeleton({ count = PAGE_SIZE }: { count?: number }) {
  return (
    <div className="customers-table-wrap" aria-busy="true" aria-label="Loading claims">
      <table className="customers-table claims-table claims-table-skel">
        <thead>
          <tr>
            <th scope="col">Claim</th>
            <th scope="col">Status</th>
            <th scope="col">Agency</th>
            <th scope="col">Vehicle</th>
            <th scope="col">Amount</th>
            <th scope="col">Owner</th>
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: count }, (_, index) => (
            <tr key={`claim-skeleton-${index}`}>
              <td>
                <div className="claims-link">
                  <span className="skeleton-block claims-skel-name" />
                  <span className="skeleton-block claims-skel-sub" />
                </div>
              </td>
              <td>
                <span className="skeleton-block claims-skel-status" />
              </td>
              <td>
                <span className="skeleton-block claims-skel-agency" />
              </td>
              <td>
                <span className="skeleton-block claims-skel-plate" />
              </td>
              <td>
                <span className="skeleton-block claims-skel-amount" />
              </td>
              <td>
                <span className="skeleton-block claims-skel-owner" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ClaimRow({ row }: { row: ClaimListItem }) {
  const tone = claimStatusTone(row.status);
  const amount = money(row.claimed_amount, row.currency);
  return (
    <tr>
      <td>
        <Link to={`/app/claims/${row.id}`} className="claims-link">
          <span className="customers-tag customers-tag--id claims-number">{row.claim_number}</span>
          <span className="customers-table-meta">
            <span className="claims-table-muted">{row.customer_name || "Claimant"}</span>
            {row.channel === "GUEST" ? (
              <span className="customers-tag customers-tag--kra">Guest</span>
            ) : null}
          </span>
        </Link>
      </td>
      <td>
        <span className={`customers-status-badge customers-status-badge--${tone}`}>
          <span className="customers-status-dot__mark" aria-hidden="true" />
          {claimStatusLabel(row.status)}
        </span>
      </td>
      <td>
        {row.agency_name ? (
          <span className="customers-tag claims-agency-badge">{row.agency_name}</span>
        ) : (
          <span className="customers-table-empty">—</span>
        )}
      </td>
      <td>
        {row.vehicle_registration ? (
          <span className="customers-tag customers-tag--id">{row.vehicle_registration}</span>
        ) : (
          <span className="customers-table-empty">—</span>
        )}
      </td>
      <td>
        <span
          className={`claims-amount-badge${amount === "—" ? "" : " claims-amount-badge--value"}`}
        >
          {amount}
        </span>
      </td>
      <td>
        <span
          className={`claims-owner-badge${row.assigned_to_name ? "" : " claims-owner-badge--empty"}`}
        >
          {row.assigned_to_name || "Unassigned"}
        </span>
      </td>
    </tr>
  );
}

export function ClaimsPage() {
  const { hasPermission } = useAuth();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [queue, setQueue] = useState("intake");

  const tabs = useMemo(
    () => QUEUES.filter((item) => !item.anyOf || item.anyOf.some((code) => hasPermission(code))),
    [hasPermission],
  );
  const activeQueue = tabs.some((item) => item.id === queue) ? queue : tabs[0]?.id ?? "mine";

  useEffect(() => {
    setPage(1);
  }, [q, activeQueue]);

  const dashboard = useQuery({
    queryKey: ["claims-dashboard"],
    queryFn: async () => (await claimApi.dashboard()).data,
    staleTime: 15_000,
  });

  const list = useQuery({
    queryKey: ["claims", q, page, activeQueue],
    queryFn: async () =>
      (
        await claimApi.list({
          q: q || undefined,
          page,
          limit: PAGE_SIZE,
          assigned_to_me: activeQueue === "mine",
          queue: activeQueue === "mine" ? undefined : activeQueue,
        })
      ).data,
    placeholderData: (previous) => previous,
    staleTime: 10_000,
  });

  const items = list.data?.items ?? [];
  const total = list.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const rangeStart = total === 0 ? 0 : (safePage - 1) * PAGE_SIZE + 1;
  const rangeEnd = total === 0 ? 0 : Math.min(safePage * PAGE_SIZE, total);
  const counts = dashboard.data?.status_counts ?? {};
  const visibleCount = Object.values(counts).reduce((sum, n) => sum + n, 0);
  const openCount = Object.entries(counts)
    .filter(
      ([status]) =>
        !["CLOSED", "CANCELLED", "WITHDRAWN", "REJECTED", "VETTING_FAILED", "DEFINITE_REJECTED"].includes(
          status,
        ),
    )
    .reduce((sum, [, n]) => sum + n, 0);
  const assignedTotal = dashboard.data?.assigned_total ?? 0;
  const empty = queueHint(activeQueue);
  const canCreate = hasPermission("claim:create");
  const statsLoading = dashboard.isLoading && !dashboard.data;
  const tableLoading = (list.isLoading && !list.data) || (list.isFetching && list.isPlaceholderData);

  function queueCount(id: string) {
    if (id === "mine") return assignedTotal;
    return (
      dashboard.data?.queue_counts?.[id] ??
      dashboard.data?.queues?.[id]?.length ??
      0
    );
  }

  return (
    <section className="config-page customers-page claims-page">
      <h1 className="config-title">Claims</h1>

      <div className="customers-top">
        {statsLoading ? (
          <ClaimsStatsSkeleton />
        ) : (
          <div className="customers-stat-grid" aria-live="polite">
            <article className="customers-stat-card">
              <span className="customers-stat-label">Visible</span>
              <strong className="customers-stat-value">{visibleCount.toLocaleString()}</strong>
            </article>
            <article className="customers-stat-card">
              <span className="customers-stat-label">Open</span>
              <strong className="customers-stat-value">{openCount.toLocaleString()}</strong>
            </article>
            <article className="customers-stat-card">
              <span className="customers-stat-label">Assigned to me</span>
              <strong className="customers-stat-value">{assignedTotal.toLocaleString()}</strong>
            </article>
            <article className="customers-stat-card">
              <span className="customers-stat-label">Desk</span>
              <strong className="customers-stat-value claims-role">
                <span className="customers-status-badge customers-status-badge--suspended">
                  {formatRole(dashboard.data?.role_code)}
                </span>
              </strong>
            </article>
          </div>
        )}

        <div className="customers-search-card">
          <label className="config-field customers-search">
            <span className="config-sr-only">Search claims</span>
            <span className="customers-search-shell">
              <IconSearch className="customers-search-icon" />
              <input
                type="search"
                placeholder="Search claim number or registration"
                value={q}
                onChange={(event) => setQ(event.target.value)}
                autoComplete="off"
              />
            </span>
          </label>
          {canCreate ? (
            <button
              type="button"
              className="config-btn customers-toolbar-add"
              onClick={() => navigate("/app/claims/new")}
            >
              + Open claim
            </button>
          ) : null}
        </div>

        <div className="claims-queues" role="tablist" aria-label="Claim queues">
          {tabs.map((item) => {
            const count = queueCount(item.id);
            const selected = activeQueue === item.id;
            return (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={selected}
                className={selected ? "is-active" : ""}
                onClick={() => setQueue(item.id)}
              >
                <span>{item.label}</span>
                {statsLoading ? (
                  <em className="claims-queue-skel" aria-hidden="true">
                    <span className="skeleton-block" />
                  </em>
                ) : count > 0 ? (
                  <em>{count}</em>
                ) : null}
              </button>
            );
          })}
        </div>
      </div>

      <div className="config-stage config-stage--fill">
        <div className="config-card config-card--scene">
          <div className="config-card-body">
            {tableLoading ? (
              <ClaimsTableSkeleton />
            ) : items.length === 0 ? (
              <div className="customers-empty">
                <span className="customers-empty-icon" aria-hidden="true">
                  <IconClaim />
                </span>
                <p className="customers-empty-title">{empty.title}</p>
                <p className="customers-empty-copy">{empty.copy}</p>
              </div>
            ) : (
              <div className="customers-table-wrap">
                <table className="customers-table claims-table">
                  <thead>
                    <tr>
                      <th scope="col">Claim</th>
                      <th scope="col">Status</th>
                      <th scope="col">Agency</th>
                      <th scope="col">Vehicle</th>
                      <th scope="col">Amount</th>
                      <th scope="col">Owner</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((row) => (
                      <ClaimRow key={row.id} row={row} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          <div className="config-card-footer">
            <div className="customers-footer">
              <div className="customers-pager-meta customers-footer-range">
                {tableLoading ? (
                  <span className="skeleton-block claims-skel-range" />
                ) : total === 0 ? (
                  "0 of 0"
                ) : (
                  `${rangeStart}–${rangeEnd} of ${total}`
                )}
              </div>
              <div className="customers-pager" aria-label="Claim pagination">
                <button
                  type="button"
                  className="customers-pager-btn"
                  aria-label="Previous page"
                  disabled={safePage <= 1 || list.isFetching}
                  onClick={() => setPage((current) => Math.max(1, current - 1))}
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
                  disabled={safePage >= totalPages || list.isFetching}
                  onClick={() => setPage((current) => current + 1)}
                >
                  <IconChevronRight />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
