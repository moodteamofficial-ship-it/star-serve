import { useQuery } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode, type SVGProps } from "react";
import { useAuth } from "@/app/providers/AuthProvider";
import {
  IconAlert,
  IconChevronRight,
  IconPayments,
  IconSearch,
} from "@/components/ui/icons";
import { paymentApi, walletApi } from "@/services/payments/paymentApi";

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
    .replace(/_/g, " ")
    .trim()
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function statusTone(status: string) {
  const key = status.trim().toUpperCase();
  if (key === "SUCCESS" || key === "SETTLED" || key === "COMPLETED") return "active";
  if (key === "PENDING" || key === "PROCESSING" || key === "INITIATED") return "pending";
  if (key === "FAILED" || key === "CANCELLED" || key === "EXPIRED") return "inactive";
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

function formatMoneyParts(
  value: string | number | null | undefined,
  currency = "KES",
): { amount: string; currency: string } | null {
  if (value == null || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(n)) {
    return { amount: String(value), currency };
  }
  return {
    amount: n.toLocaleString("en-KE", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }),
    currency,
  };
}

function MoneyValue({
  value,
  currency = "KES",
  className = "",
}: {
  value: string | number | null | undefined;
  currency?: string;
  className?: string;
}) {
  const parts = formatMoneyParts(value, currency);
  if (!parts) return <span className={`money-value ${className}`.trim()}>—</span>;
  return (
    <span className={`money-value ${className}`.trim()}>
      <span className="money-value__currency">{parts.currency}</span>
      <span className="money-value__amount">{parts.amount}</span>
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
      <table className="customers-table payments-table">
        <thead>
          <tr>
            <th scope="col">Reference</th>
            <th scope="col">Status</th>
            <th scope="col">Method</th>
            <th scope="col">Agent</th>
            <th scope="col">Amount</th>
            <th scope="col">Receipt</th>
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: count }, (_, index) => (
            <tr key={`payment-skeleton-${index}`} className="customers-table-row--skeleton">
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

export function PaymentsPage() {
  const { hasPermission } = useAuth();
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);

  useEffect(() => {
    setPage(1);
  }, [q]);

  const canReadWallet = hasPermission("wallet:read");

  const payments = useQuery({
    queryKey: ["payments", q, page],
    queryFn: async () =>
      (await paymentApi.list({ q: q || undefined, page, limit: PAGE_SIZE })).data,
    placeholderData: (previous) => previous,
  });
  const wallet = useQuery({
    queryKey: ["wallet"],
    queryFn: async () => (await walletApi.me()).data,
    enabled: canReadWallet,
  });

  const items = payments.data?.items ?? [];
  const total = payments.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const rangeStart = total === 0 ? 0 : (safePage - 1) * PAGE_SIZE + 1;
  const rangeEnd = total === 0 ? 0 : Math.min(safePage * PAGE_SIZE, total);
  const canPrev = safePage > 1;
  const canNext = safePage < totalPages;
  const successCount = items.filter((row) => row.status === "SUCCESS").length;
  const pendingCount = items.filter((row) => row.status === "PENDING").length;
  const currency = wallet.data?.currency || items[0]?.currency || "KES";
  const balanceParts = canReadWallet
    ? formatMoneyParts(wallet.data?.available_balance, wallet.data?.currency || currency)
    : null;

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  const footer = (
    <div className="customers-footer">
      <div className="customers-pager-meta customers-footer-range">
        {total === 0 ? "0 of 0" : `${rangeStart}–${rangeEnd} of ${total}`}
      </div>
      <div className="customers-pager" aria-label="Payment pagination">
        <button
          type="button"
          className="customers-pager-btn"
          aria-label="Previous page"
          disabled={!canPrev || payments.isFetching}
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
          disabled={!canNext || payments.isFetching}
          onClick={() => setPage((p) => p + 1)}
        >
          <IconChevronRight />
        </button>
      </div>
    </div>
  );

  return (
    <section className="config-page customers-page payments-page">
      <h1 className="config-title">Payments</h1>

      <div className="customers-top">
        <div className="customers-stat-grid" aria-live="polite">
          <article className="customers-stat-card">
            <span className="customers-stat-label">All payments</span>
            <strong className="customers-stat-value">{total.toLocaleString()}</strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Success</span>
            <strong className="customers-stat-value">{successCount.toLocaleString()}</strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Pending</span>
            <strong className="customers-stat-value">{pendingCount.toLocaleString()}</strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Wallet</span>
            <strong className="customers-stat-value customers-stat-value--money">
              {balanceParts ? (
                <MoneyValue
                  value={wallet.data?.available_balance}
                  currency={wallet.data?.currency || currency}
                />
              ) : (
                "—"
              )}
            </strong>
          </article>
        </div>

        <div className="customers-search-card">
          <label className="config-field customers-search">
            <span className="config-sr-only">Search payments</span>
            <span className="customers-search-shell">
              <IconSearch className="customers-search-icon" />
              <input
                type="search"
                placeholder="Search reference or receipt"
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
          {payments.isLoading && !payments.data ? <DirectorySkeleton /> : null}

          {payments.isError ? (
            <div className="customers-empty" role="alert">
              <span className="customers-empty-icon is-error" aria-hidden="true">
                <IconAlert />
              </span>
              <p className="customers-empty-title">Couldn’t load payments</p>
              <p className="customers-empty-copy">Try again in a moment.</p>
            </div>
          ) : null}

          {!(payments.isLoading && !payments.data) && !payments.isError ? (
            items.length > 0 ? (
              <div className="customers-table-wrap">
                <table className="customers-table payments-table">
                  <thead>
                    <tr>
                      <th scope="col">Reference</th>
                      <th scope="col">Status</th>
                      <th scope="col">Method</th>
                      <th scope="col">Agent</th>
                      <th scope="col">Amount</th>
                      <th scope="col">Receipt</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((row) => {
                      const isAgent =
                        row.commission_beneficiary === "AGENT" ||
                        Boolean(row.agent_code?.trim()) ||
                        Boolean(row.intermediary_id);
                      const agentLabel = isAgent
                        ? row.intermediary_name?.trim() || "Agent"
                        : "Star Serve";
                      const agentMeta = isAgent
                        ? row.agent_code?.trim() || "Agent"
                        : "House";
                      return (
                        <tr key={row.id} className="payments-table-row">
                          <td>
                            <div className="customers-table-person">
                              <span
                                className="customers-avatar customers-avatar--empty"
                                aria-hidden="true"
                              >
                                <IconPayments />
                              </span>
                              <div className="customers-table-person-text">
                                <span className="customers-tag customers-tag--id payments-ref">
                                  {row.reference}
                                </span>
                                <div className="customers-table-meta">
                                  <span className="customers-date">
                                    {formatShortDate(row.updated_at || row.created_at)}
                                  </span>
                                </div>
                              </div>
                            </div>
                          </td>
                          <td>
                            <span
                              className={`customers-status-dot customers-status-dot--${statusTone(row.status)}`}
                            >
                              <span className="customers-status-dot__mark" aria-hidden="true" />
                              {ucwords(row.status)}
                            </span>
                          </td>
                          <td>
                            <span className="payments-method-badge">{ucwords(row.method)}</span>
                          </td>
                          <td>
                            <span
                              className={`payments-agent-badge${isAgent ? "" : " is-house"}`}
                              title={`${agentLabel} · ${agentMeta}`}
                            >
                              <span className="payments-agent-badge-name">{agentLabel}</span>
                              <span className="payments-agent-badge-meta">{agentMeta}</span>
                            </span>
                          </td>
                          <td>
                            <span
                              className={`payments-amount-badge${
                                statusTone(row.status) === "active"
                                  ? " payments-amount-badge--success"
                                  : statusTone(row.status) === "pending"
                                    ? " payments-amount-badge--pending"
                                    : " payments-amount-badge--muted"
                              }`}
                            >
                              <MoneyValue
                                className="payments-amount"
                                value={row.amount}
                                currency={row.currency}
                              />
                            </span>
                          </td>
                          <td>
                            {row.provider_receipt ? (
                              <span className="customers-tag customers-tag--id payments-receipt">
                                {row.provider_receipt}
                              </span>
                            ) : (
                              <span className="payments-receipt payments-receipt--empty">—</span>
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
                  {q.trim() ? <IconSearch /> : <IconPayments />}
                </span>
                <p className="customers-empty-title">
                  {q.trim() ? "No matches" : "No payments yet"}
                </p>
                <p className="customers-empty-copy">
                  {q.trim()
                    ? "Try another reference or receipt."
                    : "Successful premiums will show up here."}
                </p>
              </div>
            )
          ) : null}
        </DirectoryCard>
      </div>
    </section>
  );
}
