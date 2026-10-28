import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { useAuth } from "@/app/providers/AuthProvider";
import { Modal } from "@/components/ui/Modal";
import { IconAlert, IconPayments, IconSearch } from "@/components/ui/icons";
import { ApiError } from "@/services/api/client";
import { commissionApi, type CommissionAccount } from "@/services/commissions/commissionApi";
import { referralApi } from "@/services/commissions/referralApi";

function formatMoney(value: string | number | null | undefined, currency = "KES") {
  if (value == null || value === "") return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(n)) return `${currency} ${value}`;
  return `${currency} ${n.toLocaleString("en-KE", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function DirectoryCard({ children }: { children: ReactNode }) {
  return (
    <div className="config-card config-card--scene">
      <div className="config-card-body">{children}</div>
    </div>
  );
}

function entryKindBadgeClass(kind: string): string {
  const key = kind.trim().toUpperCase();
  if (key === "HOUSE") return "commissions-ledger-kind commissions-ledger-kind--house";
  if (key === "PAYOUT") return "commissions-ledger-kind commissions-ledger-kind--payout";
  if (key === "ACCRUAL") return "commissions-ledger-kind commissions-ledger-kind--accrual";
  if (key === "ADJUSTMENT") return "commissions-ledger-kind commissions-ledger-kind--adjustment";
  return "commissions-ledger-kind";
}

function formatEntryKindLabel(kind: string): string {
  const key = kind.trim().toUpperCase();
  if (key === "HOUSE") return "House";
  if (key === "PAYOUT") return "Payout";
  if (key === "ACCRUAL") return "Accrual";
  if (key === "ADJUSTMENT") return "Adjustment";
  return kind;
}

function MoneyParts({
  value,
  currency = "KES",
}: {
  value: string | number | null | undefined;
  currency?: string;
}) {
  if (value == null || value === "") return <span className="money-value">—</span>;
  const n = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(n)) {
    return (
      <span className="money-value">
        <span className="money-value__currency">{currency}</span>
        <span className="money-value__amount">{String(value)}</span>
      </span>
    );
  }
  return (
    <span className="money-value">
      <span className="money-value__currency">{currency}</span>
      <span className="money-value__amount">
        {n.toLocaleString("en-KE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </span>
    </span>
  );
}

type LedgerTab = "agents" | "customers" | "house";

const LEDGER_TABS: { id: LedgerTab; label: string }[] = [
  { id: "agents", label: "Agents" },
  { id: "customers", label: "Customers" },
  { id: "house", label: "Star Serve" },
];

function parseTab(value: string | null): LedgerTab {
  return value === "customers" || value === "house" ? value : "agents";
}

function isNotFound(error: unknown) {
  return error instanceof ApiError && error.status === 404;
}

function StatCard({
  label,
  loading = false,
  children,
}: {
  label: string;
  loading?: boolean;
  children: ReactNode;
}) {
  return (
    <article className="customers-stat-card">
      <span className="customers-stat-label">{label}</span>
      <strong className="customers-stat-value customers-stat-value--money">
        {loading ? <span className="skeleton-block commissions-stat-skel" aria-hidden="true" /> : children}
      </strong>
    </article>
  );
}

type SkeletonCell = "person" | "name" | "count" | "money" | "action" | "ref" | "date" | "kind" | "text";

function TableSkeleton({
  columns,
  rows = 5,
  className = "",
}: {
  columns: { label: string; cell: SkeletonCell; srOnly?: boolean }[];
  rows?: number;
  className?: string;
}) {
  return (
    <div className="customers-table-wrap commissions-ledger-table-wrap" aria-busy="true">
      <table className={`customers-table commissions-ledger-table ${className}`.trim()}>
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col.label} scope="col">
                {col.srOnly ? <span className="config-sr-only">{col.label}</span> : col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }, (_, index) => (
            <tr key={index} className="customers-table-row--skeleton">
              {columns.map((col) => (
                <td
                  key={col.label}
                  className={
                    col.cell === "money"
                      ? "commissions-ledger-amount"
                      : col.cell === "action"
                        ? "commissions-ledger-actions"
                        : undefined
                  }
                >
                  {col.cell === "person" ? (
                    <div className="customers-table-person">
                      <span className="skeleton-block customers-avatar-skeleton" />
                      <div className="customers-table-person-text">
                        <span className="skeleton-block skeleton-block--title" />
                        <span className="skeleton-block customers-meta-skeleton" />
                      </div>
                    </div>
                  ) : col.cell === "name" ? (
                    <div className="customers-table-person-text">
                      <span className="skeleton-block skeleton-block--title" />
                      <span className="skeleton-block customers-meta-skeleton" />
                    </div>
                  ) : (
                    <span className={`skeleton-block commissions-skel commissions-skel--${col.cell}`} />
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const ACCOUNT_SKELETON_COLUMNS: { label: string; cell: SkeletonCell; srOnly?: boolean }[] = [
  { label: "Account", cell: "person" },
  { label: "Accrued", cell: "money" },
  { label: "Paid", cell: "money" },
  { label: "Balance", cell: "money" },
  { label: "Actions", cell: "action", srOnly: true },
];

const REFERRAL_SKELETON_COLUMNS: { label: string; cell: SkeletonCell }[] = [
  { label: "Customer", cell: "name" },
  { label: "Referrals", cell: "count" },
  { label: "Earned", cell: "money" },
  { label: "Used", cell: "money" },
  { label: "Balance", cell: "money" },
];

const STATEMENT_SKELETON_COLUMNS: { label: string; cell: SkeletonCell }[] = [
  { label: "Ref", cell: "ref" },
  { label: "Date", cell: "date" },
  { label: "Type", cell: "kind" },
  { label: "Description", cell: "text" },
  { label: "Amount", cell: "money" },
  { label: "Balance", cell: "money" },
];

function ErrorState({
  title,
  error,
  onRetry,
}: {
  title: string;
  error: unknown;
  onRetry: () => void;
}) {
  return (
    <div className="customers-empty" role="alert">
      <span className="customers-empty-icon is-error" aria-hidden="true">
        <IconAlert />
      </span>
      <p className="customers-empty-title">{title}</p>
      <p className="customers-empty-copy">
        {isNotFound(error)
          ? "Available after the next deploy."
          : error instanceof ApiError
            ? error.message
            : "Try again in a moment."}
      </p>
      {isNotFound(error) ? null : (
        <button type="button" className="config-btn commissions-ledger-retry" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

function EmptyState({ title, copy }: { title: string; copy: string }) {
  return (
    <div className="customers-empty" role="status">
      <span className="customers-empty-icon" aria-hidden="true">
        <IconPayments />
      </span>
      <p className="customers-empty-title">{title}</p>
      <p className="customers-empty-copy">{copy}</p>
    </div>
  );
}

function PanelHead({ title, copy, children }: { title: string; copy: string; children?: ReactNode }) {
  return (
    <header className="commissions-panel-head">
      <div className="commissions-panel-head-copy">
        <h2>{title}</h2>
        <p>{copy}</p>
      </div>
      {children}
    </header>
  );
}

function AccountsTable({
  rows,
  onStatement,
}: {
  rows: CommissionAccount[];
  onStatement: (key: string) => void;
}) {
  return (
    <div className="customers-table-wrap commissions-ledger-table-wrap">
      <table className="customers-table commissions-ledger-table">
        <thead>
          <tr>
            <th scope="col">Account</th>
            <th scope="col">Accrued</th>
            <th scope="col">Paid</th>
            <th scope="col">Balance</th>
            <th scope="col">
              <span className="config-sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const key = row.intermediary_id ?? "house";
            const isHouse = !row.intermediary_id;
            const balanceN = Number(row.balance) || 0;
            return (
              <tr key={key}>
                <td>
                  <div className="customers-table-person">
                    <span
                      className={`customers-avatar customers-avatar--empty${isHouse ? "" : " commissions-ledger-avatar"}`}
                      aria-hidden="true"
                    >
                      <IconPayments />
                    </span>
                    <div className="customers-table-person-text">
                      <span className="customers-table-name">{row.name}</span>
                      <div className="customers-table-meta">
                        {isHouse ? (
                          <span className="commissions-ledger-kind commissions-ledger-kind--house">House</span>
                        ) : (
                          <span className="customers-tag customers-tag--id">{row.agent_code || "Agent"}</span>
                        )}
                        <span className="commissions-ledger-lines-badge">{row.entry_count} lines</span>
                      </div>
                    </div>
                  </div>
                </td>
                <td className="commissions-ledger-amount">
                  <span className="commissions-ledger-amount-badge commissions-ledger-amount-badge--credit">
                    <MoneyParts value={row.accrued_total} currency={row.currency} />
                  </span>
                </td>
                <td className="commissions-ledger-amount">
                  <span className="commissions-ledger-amount-badge commissions-ledger-amount-badge--debit">
                    <MoneyParts value={row.paid_total} currency={row.currency} />
                  </span>
                </td>
                <td className="commissions-ledger-amount">
                  <span
                    className={`commissions-ledger-amount-badge${
                      balanceN > 0
                        ? " commissions-ledger-amount-badge--balance"
                        : " commissions-ledger-amount-badge--muted"
                    }`}
                  >
                    <MoneyParts value={row.balance} currency={row.currency} />
                  </span>
                </td>
                <td className="commissions-ledger-actions">
                  <button
                    type="button"
                    className="config-btn config-btn--ghost commissions-ledger-stmt-btn"
                    onClick={() => onStatement(key)}
                  >
                    Statement
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function CommissionAccountsPanel({
  tab,
  rows,
  loading,
  error,
  onRetry,
  onStatement,
}: {
  tab: "agents" | "house";
  rows: CommissionAccount[];
  loading: boolean;
  error: unknown;
  onRetry: () => void;
  onStatement: (key: string) => void;
}) {
  const totals = rows.reduce(
    (acc, row) => {
      acc.balance += Number(row.balance) || 0;
      acc.accrued += Number(row.accrued_total) || 0;
      acc.paid += Number(row.paid_total) || 0;
      acc.lines += row.entry_count || 0;
      return acc;
    },
    { balance: 0, accrued: 0, paid: 0, lines: 0 },
  );
  const currency = rows[0]?.currency || "KES";
  const isAgents = tab === "agents";

  return (
    <>
      <div className="customers-top">
        <div className="customers-stat-grid" aria-live="polite">
          {isAgents ? (
            <StatCard label="Agents" loading={loading}>{rows.length.toLocaleString()}</StatCard>
          ) : (
            <StatCard label="Ledger lines" loading={loading}>{totals.lines.toLocaleString()}</StatCard>
          )}
          <StatCard label={isAgents ? "Accrued" : "Earned"} loading={loading}>
            <MoneyParts value={totals.accrued} currency={currency} />
          </StatCard>
          <StatCard label={isAgents ? "Paid out" : "Withdrawn"} loading={loading}>
            <MoneyParts value={totals.paid} currency={currency} />
          </StatCard>
          <StatCard label={isAgents ? "Outstanding" : "Balance"} loading={loading}>
            <MoneyParts value={totals.balance} currency={currency} />
          </StatCard>
        </div>
      </div>

      <div className="config-stage config-stage--fill">
        <DirectoryCard>
          <PanelHead
            title={isAgents ? "Agent commissions" : "Star Serve commission"}
            copy={
              isAgents
                ? "Cash earned per paid certificate."
                : "Kept on sales without an agent."
            }
          />
          {loading ? (
            <TableSkeleton columns={ACCOUNT_SKELETON_COLUMNS} rows={isAgents ? 5 : 1} />
          ) : error ? (
            <ErrorState title="Couldn’t load ledger" error={error} onRetry={onRetry} />
          ) : rows.length === 0 ? (
            <EmptyState
              title={isAgents ? "No agent commission yet" : "No Star Serve commission yet"}
              copy={
                isAgents
                  ? "Shows after an agent’s first paid sale."
                  : "Shows after the first direct sale."
              }
            />
          ) : (
            <AccountsTable rows={rows} onStatement={onStatement} />
          )}
        </DirectoryCard>
      </div>
    </>
  );
}

function CustomerReferralCredits() {
  const [query, setQuery] = useState("");
  const referrals = useQuery({
    queryKey: ["referral-accounts", query.trim()],
    queryFn: async () => (await referralApi.listAccounts(query.trim() || undefined)).data,
    retry: (count, err) => !isNotFound(err) && count < 2,
  });
  const allRows = referrals.data?.items ?? [];
  const rows = allRows.filter((row) => query.trim() || row.referrals > 0 || Number(row.balance) > 0);
  const totals = allRows.reduce(
    (acc, row) => {
      acc.referrals += row.referrals || 0;
      acc.earned += Number(row.earned_total) || 0;
      acc.used += Number(row.redeemed_total) || 0;
      acc.balance += Number(row.balance) || 0;
      return acc;
    },
    { referrals: 0, earned: 0, used: 0, balance: 0 },
  );

  return (
    <>
      <div className="customers-top">
        <div className="customers-stat-grid" aria-live="polite">
          <StatCard label="Referrals" loading={referrals.isLoading}>{totals.referrals.toLocaleString()}</StatCard>
          <StatCard label="Credit earned" loading={referrals.isLoading}>
            <MoneyParts value={totals.earned} />
          </StatCard>
          <StatCard label="Used as discount" loading={referrals.isLoading}>
            <MoneyParts value={totals.used} />
          </StatCard>
          <StatCard label="Unused credit" loading={referrals.isLoading}>
            <MoneyParts value={totals.balance} />
          </StatCard>
        </div>
      </div>

      <div className="config-stage config-stage--fill">
        <DirectoryCard>
          <PanelHead
            title="Customer referral credits"
            copy="Discount on the customer’s next cover. Not paid out."
          >
          <label className="config-field customers-search commissions-panel-search">
            <span className="config-sr-only">Search referral credits</span>
            <span className="customers-search-shell">
              <IconSearch className="customers-search-icon" />
              <input
                type="search"
                placeholder="Search code, name, ID or phone"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                autoComplete="off"
              />
            </span>
          </label>
          </PanelHead>
          {referrals.isLoading ? (
            <TableSkeleton columns={REFERRAL_SKELETON_COLUMNS} />
          ) : referrals.isError ? (
            <ErrorState
              title="Couldn’t load referral credits"
              error={referrals.error}
              onRetry={() => void referrals.refetch()}
            />
          ) : rows.length === 0 ? (
            <EmptyState
              title={query.trim() ? "No matching customers" : "No referral credits yet"}
              copy={query.trim() ? "Try another code, name, ID or phone." : "Shows after the first referred sale."}
            />
          ) : (
            <div className="customers-table-wrap commissions-ledger-table-wrap">
              <table className="customers-table commissions-ledger-table">
                <thead>
                  <tr>
                    <th scope="col">Customer</th>
                    <th scope="col">Referrals</th>
                    <th scope="col">Earned</th>
                    <th scope="col">Used</th>
                    <th scope="col">Balance</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.referral_code}>
                      <td>
                        <div className="customers-table-person-text">
                          <span className="customers-table-name">{row.holder_name || row.id_number}</span>
                          <div className="customers-table-meta">
                            <span className="customers-tag customers-tag--id">{row.referral_code}</span>
                            {row.phone ? <span>{row.phone}</span> : null}
                          </div>
                        </div>
                      </td>
                      <td>{row.referrals.toLocaleString()}</td>
                      <td className="commissions-ledger-amount">
                        <span className="commissions-ledger-amount-badge commissions-ledger-amount-badge--credit">
                          <MoneyParts value={row.earned_total} />
                        </span>
                      </td>
                      <td className="commissions-ledger-amount">
                        <span className="commissions-ledger-amount-badge commissions-ledger-amount-badge--debit">
                          <MoneyParts value={row.redeemed_total} />
                        </span>
                      </td>
                      <td className="commissions-ledger-amount">
                        <span
                          className={`commissions-ledger-amount-badge${
                            Number(row.balance) > 0
                              ? " commissions-ledger-amount-badge--balance"
                              : " commissions-ledger-amount-badge--muted"
                          }`}
                        >
                          <MoneyParts value={row.balance} />
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </DirectoryCard>
      </div>
    </>
  );
}

export function CommissionLedgerPage() {
  const { hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const canRead =
    hasPermission("commission:read") ||
    hasPermission("commission:manage") ||
    hasPermission("settings:manage") ||
    hasPermission("tenant:manage");
  const canPayout = hasPermission("commission:payout");

  const [searchParams, setSearchParams] = useSearchParams();
  const tab = parseTab(searchParams.get("tab"));
  const [statementKey, setStatementKey] = useState("");

  function selectTab(next: LedgerTab) {
    const params = new URLSearchParams(searchParams);
    if (next === "agents") params.delete("tab");
    else params.set("tab", next);
    setSearchParams(params, { replace: true });
  }
  const [actionError, setActionError] = useState<string | null>(null);

  const accounts = useQuery({
    queryKey: ["commission-accounts"],
    queryFn: async () => (await commissionApi.listAccounts()).data,
    enabled: canRead,
  });

  const statement = useQuery({
    queryKey: ["commission-statement", statementKey],
    queryFn: async () => {
      if (statementKey === "house") {
        return (await commissionApi.statement({ house: true })).data;
      }
      return (await commissionApi.statement({ intermediary_id: statementKey })).data;
    },
    enabled: canRead && Boolean(statementKey),
  });

  const payout = useMutation({
    mutationFn: async () => {
      if (statementKey === "house") {
        return commissionApi.payout({ house: true });
      }
      return commissionApi.payout({ intermediary_id: statementKey });
    },
    onSuccess: async () => {
      setActionError(null);
      await queryClient.invalidateQueries({ queryKey: ["commission-accounts"] });
      await queryClient.invalidateQueries({ queryKey: ["commission-statement"] });
    },
    onError: (error) => {
      setActionError(error instanceof ApiError ? error.message : "Could not record payout");
    },
  });

  const accountItems = accounts.data?.items ?? [];
  const agentRows = useMemo(() => accountItems.filter((row) => row.intermediary_id), [accountItems]);
  const houseRows = useMemo(() => accountItems.filter((row) => !row.intermediary_id), [accountItems]);
  const activeAccount: CommissionAccount | undefined = accountItems.find(
    (row) => (row.intermediary_id ?? "house") === statementKey,
  );

  function openStatement(key: string) {
    setActionError(null);
    setStatementKey(key);
  }

  function closeStatement() {
    if (payout.isPending) return;
    setStatementKey("");
    setActionError(null);
  }

  if (!canRead) {
    return (
      <section className="config-page">
        <h1 className="config-title">Commission ledger</h1>
        <p className="config-empty">You do not have permission to view commission balances.</p>
      </section>
    );
  }

  return (
    <section className="config-page customers-page commissions-ledger-page">
      <header className="customers-page-header">
        <div>
          <h1 className="config-title">Commission ledger</h1>
          {/* <p className="customers-page-subtitle">
            Accruals, payouts, and balances by agent account.
          </p> */}
        </div>
      </header>

      <div className="commissions-ledger-tabs" role="tablist" aria-label="Commission parties">
        {LEDGER_TABS.map((item) => {
          const count = item.id === "agents" ? agentRows.length : 0;
          const selected = tab === item.id;
          return (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={selected}
              className={selected ? "is-active" : ""}
              onClick={() => selectTab(item.id)}
            >
              <span>{item.label}</span>
              {count ? <em>{count}</em> : null}
            </button>
          );
        })}
      </div>

      {tab === "customers" ? (
        <CustomerReferralCredits />
      ) : (
        <CommissionAccountsPanel
          tab={tab}
          rows={tab === "agents" ? agentRows : houseRows}
          loading={accounts.isLoading}
          error={accounts.isError ? accounts.error : null}
          onRetry={() => void accounts.refetch()}
          onStatement={openStatement}
        />
      )}

      <Modal
        open={Boolean(statementKey)}
        size="xl"
        panelClassName="commissions-ledger-statement-modal"
        title={
          statement.data
            ? `Statement · ${statement.data.account.name}`
            : activeAccount
              ? `Statement · ${activeAccount.name}`
              : "Statement"
        }
        subtitle={
          statement.data ? (
            <span className="commissions-ledger-statement-sub">
              <span className="commissions-ledger-balance-chip">
                Opening {formatMoney(statement.data.opening_balance)}
              </span>
              <span className="commissions-ledger-balance-chip commissions-ledger-balance-chip--closing">
                Closing {formatMoney(statement.data.closing_balance)}
              </span>
              {statement.data.account.agent_code ? (
                <span className="customers-tag customers-tag--id">
                  {statement.data.account.agent_code}
                </span>
              ) : null}
            </span>
          ) : (
            "Loading commission lines…"
          )
        }
        icon={<IconPayments />}
        onClose={closeStatement}
        bodyClassName="intermediaries-modal-body commissions-ledger-modal-body"
        footer={
          <>
            <button
              type="button"
              className="secondary"
              disabled={payout.isPending}
              onClick={closeStatement}
            >
              Close
            </button>
            {canPayout ? (
              <button
                type="button"
                disabled={
                  payout.isPending ||
                  !statement.data ||
                  Number(statement.data.closing_balance) <= 0
                }
                onClick={() => payout.mutate()}
              >
                {payout.isPending ? "Recording…" : "Record payout"}
              </button>
            ) : null}
          </>
        }
      >
        {actionError ? (
          <p className="commissions-ledger-modal-error" role="alert">
            {actionError}
          </p>
        ) : null}
        {statement.isLoading || (statementKey && !statement.data && !statement.isError) ? (
          <TableSkeleton
            columns={STATEMENT_SKELETON_COLUMNS}
            rows={6}
            className="commissions-ledger-table--statement"
          />
        ) : statement.isError ? (
          <div className="customers-empty" role="alert">
            <span className="customers-empty-icon is-error" aria-hidden="true">
              <IconAlert />
            </span>
            <p className="customers-empty-title">Couldn’t load statement</p>
            <p className="customers-empty-copy">
              {statement.error instanceof ApiError
                ? statement.error.message
                : "Try again in a moment."}
            </p>
          </div>
        ) : statement.data && statement.data.entries.length === 0 ? (
          <div className="customers-empty" role="status">
            <p className="customers-empty-title">No lines in this period</p>
          </div>
        ) : statement.data ? (
          <div className="customers-table-wrap commissions-ledger-table-wrap">
            <table className="customers-table commissions-ledger-table commissions-ledger-table--statement">
              <thead>
                <tr>
                  <th scope="col">Ref</th>
                  <th scope="col">Date</th>
                  <th scope="col">Type</th>
                  <th scope="col">Description</th>
                  <th scope="col">Amount</th>
                  <th scope="col">Balance</th>
                </tr>
              </thead>
              <tbody>
                {statement.data.entries.map((entry) => (
                  <tr key={entry.id}>
                    <td>
                      <span className="customers-tag customers-tag--id commissions-ledger-ref">
                        {entry.statement_ref}
                      </span>
                    </td>
                    <td>{new Date(entry.occurred_at).toLocaleDateString("en-GB", {
                      day: "numeric",
                      month: "short",
                      year: "numeric",
                    })}</td>
                    <td>
                      <span className={entryKindBadgeClass(entry.entry_kind)}>
                        {formatEntryKindLabel(entry.entry_kind)}
                      </span>
                    </td>
                    <td>{entry.description}</td>
                    <td
                      className={`commissions-ledger-amount${
                        entry.direction === "DEBIT"
                          ? " commissions-ledger-amount--debit"
                          : " commissions-ledger-amount--credit"
                      }`}
                    >
                      <span
                        className={`commissions-ledger-amount-badge${
                          entry.direction === "DEBIT"
                            ? " commissions-ledger-amount-badge--debit"
                            : " commissions-ledger-amount-badge--credit"
                        }`}
                      >
                        {entry.direction === "DEBIT" ? "−" : "+"}
                        {formatMoney(entry.amount, entry.currency)}
                      </span>
                    </td>
                    <td className="commissions-ledger-amount">
                      {formatMoney(entry.balance_after, entry.currency)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </Modal>
    </section>
  );
}
