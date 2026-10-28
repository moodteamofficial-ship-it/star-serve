import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode, type SVGProps } from "react";
import { useAuth } from "@/app/providers/AuthProvider";
import { Modal } from "@/components/ui/Modal";
import {
  IconAlert,
  IconCheckCircle,
  IconChevronRight,
  IconSearch,
  IconShield,
  IconXCircle,
} from "@/components/ui/icons";
import { policyApi, type Policy } from "@/services/policies/policyApi";

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
  const map: Record<string, string> = {
    ACTIVE: "Active",
    PENDING_PAYMENT: "Pending payment",
    PENDING_CERTIFICATE: "Pending certificate",
    CANCELLED: "Cancelled",
    EXPIRED: "Expired",
  };
  if (map[key]) return map[key];
  return status
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function statusTone(status: string) {
  const key = status.trim().toUpperCase();
  if (key === "ACTIVE") return "active";
  if (key === "PENDING_PAYMENT" || key === "PENDING_CERTIFICATE") return "pending";
  if (key === "CANCELLED" || key === "EXPIRED") return "inactive";
  return "neutral";
}

function formatShortDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function formatMoney(value: string | number | null | undefined, currency = "KES") {
  if (value == null || value === "") return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(n)) return `${currency} ${value}`;
  return `${currency} ${n.toLocaleString("en-KE", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function canActivatePolicy(row: Policy, canUpdate: boolean) {
  return canUpdate && row.status === "PENDING_PAYMENT";
}

function canCancelPolicy(row: Policy, canCancel: boolean) {
  return (
    canCancel &&
    ["ACTIVE", "PENDING_PAYMENT", "PENDING_CERTIFICATE"].includes(row.status)
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
      <table className="customers-table policies-table policies-table--actions">
        <thead>
          <tr>
            <th scope="col">Policy</th>
            <th scope="col">Status</th>
            <th scope="col">Vehicle</th>
            <th scope="col">Premium</th>
            <th scope="col">Updated</th>
            <th scope="col">
              <span className="config-sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: count }, (_, index) => (
            <tr key={`policy-skeleton-${index}`} className="customers-table-row--skeleton">
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

export function PoliciesPage() {
  const { hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [activateTarget, setActivateTarget] = useState<Policy | null>(null);
  const [cancelTarget, setCancelTarget] = useState<Policy | null>(null);

  useEffect(() => {
    setPage(1);
  }, [q]);

  const canUpdate = hasPermission("policy:update");
  const canCancel = hasPermission("policy:cancel");

  const list = useQuery({
    queryKey: ["policies", q, page],
    queryFn: async () =>
      (await policyApi.list({ q: q || undefined, page, limit: PAGE_SIZE })).data,
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
  const activeCount = items.filter((row) => row.status === "ACTIVE").length;
  const pendingCount = items.filter((row) =>
    ["PENDING_PAYMENT", "PENDING_CERTIFICATE"].includes(row.status),
  ).length;
  const cancelledCount = items.filter((row) => row.status === "CANCELLED").length;
  const showActions = items.some(
    (row) => canActivatePolicy(row, canUpdate) || canCancelPolicy(row, canCancel),
  );

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  const activate = useMutation({
    mutationFn: (id: string) => policyApi.activate(id),
    onSuccess: async () => {
      setActivateTarget(null);
      await queryClient.invalidateQueries({ queryKey: ["policies"] });
    },
  });

  const cancel = useMutation({
    mutationFn: (id: string) => policyApi.cancel(id, "INSURED_REQUEST"),
    onSuccess: async () => {
      setCancelTarget(null);
      await queryClient.invalidateQueries({ queryKey: ["policies"] });
    },
  });

  const footer = (
    <div className="customers-footer">
      <div className="customers-pager-meta customers-footer-range">
        {total === 0 ? "0 of 0" : `${rangeStart}–${rangeEnd} of ${total}`}
      </div>
      <div className="customers-pager" aria-label="Policy pagination">
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
    <section className="config-page customers-page policies-page">
      <h1 className="config-title">Policies</h1>

      <div className="customers-top">
        <div className="customers-stat-grid" aria-live="polite">
          <article className="customers-stat-card">
            <span className="customers-stat-label">All policies</span>
            <strong className="customers-stat-value">{total.toLocaleString()}</strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Active</span>
            <strong className="customers-stat-value">{activeCount.toLocaleString()}</strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Pending</span>
            <strong className="customers-stat-value">{pendingCount.toLocaleString()}</strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Cancelled</span>
            <strong className="customers-stat-value">{cancelledCount.toLocaleString()}</strong>
          </article>
        </div>

        <div className="customers-search-card">
          <label className="config-field customers-search">
            <span className="config-sr-only">Search policies</span>
            <span className="customers-search-shell">
              <IconSearch className="customers-search-icon" />
              <input
                type="search"
                placeholder="Search policy number or registration"
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
              <p className="customers-empty-title">Couldn’t load policies</p>
              <p className="customers-empty-copy">Try again in a moment.</p>
            </div>
          ) : null}

          {!(list.isLoading && !list.data) && !list.isError ? (
            items.length > 0 ? (
              <div className="customers-table-wrap">
                <table
                  className={`customers-table policies-table${showActions ? " policies-table--actions" : ""}`}
                >
                  <thead>
                    <tr>
                      <th scope="col">Policy</th>
                      <th scope="col">Status</th>
                      <th scope="col">Vehicle</th>
                      <th scope="col">Premium</th>
                      <th scope="col">Updated</th>
                      {showActions ? (
                        <th scope="col">
                          <span className="config-sr-only">Actions</span>
                        </th>
                      ) : null}
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((row) => {
                      const tone = statusTone(row.status);
                      const showActivate = canActivatePolicy(row, canUpdate);
                      const showCancel = canCancelPolicy(row, canCancel);
                      return (
                        <tr key={row.id}>
                          <td>
                            <div className="customers-table-person">
                              <span
                                className="customers-avatar customers-avatar--empty"
                                aria-hidden="true"
                              >
                                <IconShield />
                              </span>
                              <div className="customers-table-person-text">
                                <span className="customers-tag customers-tag--id policies-number">
                                  {row.policy_number}
                                </span>
                                <div className="customers-table-meta">
                                  {row.product_code ? (
                                    <span className="customers-tag customers-tag--id">
                                      {row.product_code}
                                    </span>
                                  ) : null}
                                  {row.cover_option ? (
                                    <span className="customers-tag customers-tag--kra">
                                      {row.cover_option}
                                    </span>
                                  ) : null}
                                </div>
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
                            <span className="customers-tag customers-tag--id">
                              {row.vehicle_registration}
                            </span>
                          </td>
                          <td>
                            <span
                              className={`policies-premium-badge${
                                row.gross_premium != null && row.gross_premium !== ""
                                  ? " policies-premium-badge--value"
                                  : ""
                              }`}
                            >
                              {formatMoney(row.gross_premium)}
                            </span>
                          </td>
                          <td>
                            <span className="customers-date-badge">
                              {formatShortDate(row.updated_at || row.created_at)}
                            </span>
                          </td>
                          {showActions ? (
                            <td>
                              <div className="policies-actions">
                                <span className="policies-actions-slot">
                                  {showActivate ? (
                                    <button
                                      type="button"
                                      className="intermediaries-approve-btn"
                                      disabled={activate.isPending}
                                      onClick={() => setActivateTarget(row)}
                                    >
                                      Activate
                                    </button>
                                  ) : null}
                                </span>
                                <span className="policies-actions-slot">
                                  {showCancel ? (
                                    <button
                                      type="button"
                                      className="policies-cancel-btn"
                                      disabled={cancel.isPending}
                                      onClick={() => setCancelTarget(row)}
                                    >
                                      Cancel
                                    </button>
                                  ) : null}
                                </span>
                              </div>
                            </td>
                          ) : null}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="customers-empty" role="status">
                <span className="customers-empty-icon" aria-hidden="true">
                  {q.trim() ? <IconSearch /> : <IconShield />}
                </span>
                <p className="customers-empty-title">
                  {q.trim() ? "No matches" : "No policies yet"}
                </p>
                <p className="customers-empty-copy">
                  {q.trim()
                    ? "Try another policy number or registration."
                    : "Issue a policy from an approved proposal."}
                </p>
              </div>
            )
          ) : null}
        </DirectoryCard>
      </div>

      <Modal
        open={Boolean(activateTarget)}
        title={
          activateTarget
            ? `Activate ${activateTarget.policy_number}?`
            : "Activate"
        }
        subtitle="Marks payment as confirmed."
        icon={<IconCheckCircle />}
        onClose={() => {
          if (!activate.isPending) setActivateTarget(null);
        }}
        bodyClassName="intermediaries-modal-body"
        footer={
          <>
            <button
              type="button"
              className="secondary"
              disabled={activate.isPending}
              onClick={() => setActivateTarget(null)}
            >
              Back
            </button>
            <button
              type="button"
              disabled={!activateTarget || activate.isPending}
              onClick={() => {
                if (activateTarget) activate.mutate(activateTarget.id);
              }}
            >
              {activate.isPending ? "Activating…" : "Activate"}
            </button>
          </>
        }
      >
        {activateTarget ? (
          <div className="intermediaries-confirm">
            <div className="intermediaries-confirm-person">
              <span className="customers-avatar customers-avatar--empty" aria-hidden="true">
                <IconShield />
              </span>
              <div className="customers-table-person-text">
                <span className="customers-table-name">
                  {activateTarget.policy_number}
                </span>
                <div className="customers-table-meta">
                  <span className="customers-tag customers-tag--id">
                    {activateTarget.vehicle_registration}
                  </span>
                  <span className="customers-tag customers-tag--kra">
                    {formatMoney(activateTarget.gross_premium)}
                  </span>
                </div>
              </div>
            </div>
          </div>
        ) : null}
      </Modal>

      <Modal
        open={Boolean(cancelTarget)}
        title={
          cancelTarget ? `Cancel ${cancelTarget.policy_number}?` : "Cancel"
        }
        subtitle="This cannot be undone."
        icon={<IconXCircle />}
        onClose={() => {
          if (!cancel.isPending) setCancelTarget(null);
        }}
        bodyClassName="intermediaries-modal-body"
        footer={
          <>
            <button
              type="button"
              className="secondary"
              disabled={cancel.isPending}
              onClick={() => setCancelTarget(null)}
            >
              Keep
            </button>
            <button
              type="button"
              className="policies-confirm-cancel"
              disabled={!cancelTarget || cancel.isPending}
              onClick={() => {
                if (cancelTarget) cancel.mutate(cancelTarget.id);
              }}
            >
              {cancel.isPending ? "Cancelling…" : "Cancel policy"}
            </button>
          </>
        }
      >
        {cancelTarget ? (
          <div className="intermediaries-confirm">
            <div className="intermediaries-confirm-person">
              <span className="customers-avatar customers-avatar--empty" aria-hidden="true">
                <IconShield />
              </span>
              <div className="customers-table-person-text">
                <span className="customers-table-name">
                  {cancelTarget.policy_number}
                </span>
                <div className="customers-table-meta">
                  <span className="customers-tag customers-tag--id">
                    {cancelTarget.vehicle_registration}
                  </span>
                  <span className="customers-tag customers-tag--kra">
                    {statusLabel(cancelTarget.status)}
                  </span>
                </div>
              </div>
            </div>
          </div>
        ) : null}
      </Modal>
    </section>
  );
}
