import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type FormEvent, type ReactNode, type SVGProps } from "react";
import { useAuth } from "@/app/providers/AuthProvider";
import { AnimatedFormError } from "@/components/ui/AnimatedFormError";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import {
  IconAlert,
  IconBriefcase,
  IconCheckCircle,
  IconChevronRight,
  IconFileText,
  IconSearch,
  IconShield,
} from "@/components/ui/icons";
import { ApiError } from "@/services/api/client";
import { customerApi } from "@/services/customers/customerApi";
import { productApi } from "@/services/products/productApi";
import { proposalApi, type Proposal } from "@/services/proposals/proposalApi";

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
    DRAFT: "Draft",
    PREMIUM_CALCULATED: "Quoted",
    DOUBLE_INSURANCE_CHECKED: "Checked",
    SUBMITTED: "Submitted",
    APPROVED: "Approved",
    REJECTED: "Rejected",
    CANCELLED: "Cancelled",
    CONVERTED: "Converted",
  };
  if (map[key]) return map[key];
  return status
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function statusTone(status: string) {
  const key = status.trim().toUpperCase();
  if (key === "CONVERTED" || key === "APPROVED") return "active";
  if (key === "SUBMITTED" || key === "PREMIUM_CALCULATED" || key === "DOUBLE_INSURANCE_CHECKED") {
    return "pending";
  }
  if (key === "REJECTED" || key === "CANCELLED") return "inactive";
  if (key === "DRAFT") return "neutral";
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
      <table className="customers-table proposals-table">
        <thead>
          <tr>
            <th scope="col">Vehicle</th>
            <th scope="col">Status</th>
            <th scope="col">Product</th>
            <th scope="col">Premium</th>
            <th scope="col">Updated</th>
            <th scope="col">
              <span className="config-sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: count }, (_, index) => (
            <tr key={`proposal-skeleton-${index}`} className="customers-table-row--skeleton">
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

export function ProposalsPage() {
  const { hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [approveTarget, setApproveTarget] = useState<Proposal | null>(null);
  const [issueTarget, setIssueTarget] = useState<Proposal | null>(null);
  const [form, setForm] = useState({
    customer_id: "",
    product_code: "MOTOR_COMP",
    cover_option: "Comprehensive",
    cover_period: "12",
    vehicle_registration: "",
    vehicle_make: "TOYOTA",
    vehicle_model: "",
    sum_insured: "1500000",
  });

  useEffect(() => {
    setPage(1);
  }, [q]);

  const canCreate = hasPermission("proposal:create");
  const canApprove = hasPermission("proposal:approve");
  const canIssue = hasPermission("policy:create");

  const customers = useQuery({
    queryKey: ["customers-mini"],
    queryFn: async () => (await customerApi.list({ limit: 100 })).data,
    enabled: canCreate && hasPermission("customer:read") && showAdd,
  });
  const products = useQuery({
    queryKey: ["products"],
    queryFn: async () => (await productApi.listProducts()).data,
    enabled: canCreate && hasPermission("product:read") && showAdd,
  });
  const makes = useQuery({
    queryKey: ["vehicle-makes"],
    queryFn: async () => (await productApi.listMakes()).data,
    enabled: canCreate && hasPermission("product:read") && showAdd,
  });
  const list = useQuery({
    queryKey: ["proposals", q, page],
    queryFn: async () =>
      (await proposalApi.list({ q: q || undefined, page, limit: PAGE_SIZE })).data,
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
  const convertedCount = items.filter((row) => row.status === "CONVERTED").length;
  const submittedCount = items.filter((row) => row.status === "SUBMITTED").length;
  const approvedCount = items.filter((row) => row.status === "APPROVED").length;
  const showActions = items.some(
    (row) =>
      (canApprove && row.status === "SUBMITTED") ||
      (canIssue && row.status === "APPROVED"),
  );

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  function resetForm() {
    setForm({
      customer_id: "",
      product_code: products.data?.[0]?.code ?? "MOTOR_COMP",
      cover_option: products.data?.[0]?.cover_options?.[0] ?? "Comprehensive",
      cover_period: "12",
      vehicle_registration: "",
      vehicle_make: makes.data?.[0]?.code ?? "TOYOTA",
      vehicle_model: "",
      sum_insured: "1500000",
    });
    setError(null);
  }

  useEffect(() => {
    if (!showAdd) return;
    const firstProduct = products.data?.[0];
    const firstMake = makes.data?.[0];
    setForm((prev) => ({
      ...prev,
      product_code: prev.product_code || firstProduct?.code || "MOTOR_COMP",
      cover_option:
        prev.cover_option ||
        firstProduct?.cover_options?.[0] ||
        "Comprehensive",
      vehicle_make: prev.vehicle_make || firstMake?.code || "TOYOTA",
    }));
  }, [showAdd, products.data, makes.data]);

  const selectedProduct = (products.data ?? []).find((p) => p.code === form.product_code);
  const coverOptions = selectedProduct?.cover_options?.length
    ? selectedProduct.cover_options
    : [form.cover_option || "Comprehensive"];

  const customerOptions = useMemo(
    () =>
      (customers.data?.items ?? []).map((c) => ({
        value: c.id,
        label: `${c.first_name} ${c.last_name} (${c.id_number})`,
      })),
    [customers.data?.items],
  );

  const productOptions = useMemo(
    () =>
      (products.data ?? []).map((p) => ({
        value: p.code,
        label: p.name,
      })),
    [products.data],
  );

  const coverOptionItems = useMemo(
    () =>
      coverOptions.map((option) => ({
        value: option,
        label: option,
      })),
    [coverOptions],
  );

  const makeOptions = useMemo(
    () =>
      (makes.data ?? []).map((m) => ({
        value: m.code,
        label: m.name,
      })),
    [makes.data],
  );

  const create = useMutation({
    mutationFn: async () => {
      const key = crypto.randomUUID();
      return proposalApi.create(
        {
          customer_id: form.customer_id,
          product_code: form.product_code,
          cover_option: form.cover_option,
          cover_period: form.cover_period,
          vehicle_registration: form.vehicle_registration.trim().toUpperCase(),
          vehicle_make: form.vehicle_make,
          vehicle_model: form.vehicle_model.trim() || undefined,
          sum_insured: form.sum_insured.trim() === "" ? 0 : Number(form.sum_insured),
          transaction_type: "NEW",
        },
        key,
      );
    },
    onMutate: () => {
      setError(null);
    },
    onSuccess: async () => {
      resetForm();
      setShowAdd(false);
      setPage(1);
      await queryClient.invalidateQueries({ queryKey: ["proposals"] });
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "Unable to create proposal");
    },
  });

  const approve = useMutation({
    mutationFn: (id: string) => proposalApi.approve(id),
    onSuccess: async () => {
      setApproveTarget(null);
      await queryClient.invalidateQueries({ queryKey: ["proposals"] });
    },
  });

  const issue = useMutation({
    mutationFn: (id: string) => proposalApi.issuePolicy(id),
    onSuccess: async () => {
      setIssueTarget(null);
      await queryClient.invalidateQueries({ queryKey: ["proposals"] });
      await queryClient.invalidateQueries({ queryKey: ["policies"] });
    },
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    create.mutate();
  }

  const footer = (
    <div className="customers-footer">
      <div className="customers-pager-meta customers-footer-range">
        {total === 0 ? "0 of 0" : `${rangeStart}–${rangeEnd} of ${total}`}
      </div>
      <div className="customers-pager" aria-label="Proposal pagination">
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
    <section className="config-page customers-page proposals-page">
      <h1 className="config-title">Proposals</h1>

      <div className="customers-top">
        <div className="customers-stat-grid" aria-live="polite">
          <article className="customers-stat-card">
            <span className="customers-stat-label">All proposals</span>
            <strong className="customers-stat-value">{total.toLocaleString()}</strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Converted</span>
            <strong className="customers-stat-value">{convertedCount.toLocaleString()}</strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Submitted</span>
            <strong className="customers-stat-value">{submittedCount.toLocaleString()}</strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Approved</span>
            <strong className="customers-stat-value">{approvedCount.toLocaleString()}</strong>
          </article>
        </div>

        <div className="customers-search-card">
          <label className="config-field customers-search">
            <span className="config-sr-only">Search proposals</span>
            <span className="customers-search-shell">
              <IconSearch className="customers-search-icon" />
              <input
                type="search"
                placeholder="Search registration or product"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                autoComplete="off"
              />
            </span>
          </label>
          {canCreate ? (
            <button
              type="button"
              className="config-btn customers-toolbar-add"
              onClick={() => {
                resetForm();
                setShowAdd(true);
              }}
            >
              + New proposal
            </button>
          ) : null}
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
              <p className="customers-empty-title">Couldn’t load proposals</p>
              <p className="customers-empty-copy">Try again in a moment.</p>
            </div>
          ) : null}

          {!(list.isLoading && !list.data) && !list.isError ? (
            items.length > 0 ? (
              <div className="customers-table-wrap">
                <table
                  className={`customers-table proposals-table${showActions ? " proposals-table--actions" : ""}`}
                >
                  <thead>
                    <tr>
                      <th scope="col">Vehicle</th>
                      <th scope="col">Status</th>
                      <th scope="col">Product</th>
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
                      const makeModel = [row.vehicle_make, row.vehicle_model]
                        .filter(Boolean)
                        .join(" · ");
                      const canApproveRow = canApprove && row.status === "SUBMITTED";
                      const canIssueRow = canIssue && row.status === "APPROVED";
                      return (
                        <tr key={row.id}>
                          <td>
                            <div className="customers-table-person">
                              <span
                                className="customers-avatar customers-avatar--empty"
                                aria-hidden="true"
                              >
                                <IconBriefcase />
                              </span>
                              <div className="customers-table-person-text">
                                <span className="customers-table-name">
                                  {row.vehicle_registration}
                                </span>
                                <div className="customers-table-meta">
                                  {row.channel === "GUEST" ? (
                                    <span className="customers-tag customers-tag--kra">Guest</span>
                                  ) : null}
                                  {makeModel ? (
                                    <span className="customers-tag customers-tag--id">
                                      {makeModel}
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
                            <span className="customers-tag customers-tag--id proposals-product-code">
                              {row.product_code}
                            </span>
                          </td>
                          <td>
                            <span
                              className={`proposals-premium-badge${
                                row.gross_premium != null && row.gross_premium !== ""
                                  ? " proposals-premium-badge--value"
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
                            <td className="proposals-actions">
                              {canApproveRow ? (
                                <button
                                  type="button"
                                  className="intermediaries-approve-btn"
                                  disabled={approve.isPending}
                                  onClick={() => setApproveTarget(row)}
                                >
                                  Approve
                                </button>
                              ) : null}
                              {canIssueRow ? (
                                <button
                                  type="button"
                                  className="intermediaries-approve-btn"
                                  disabled={issue.isPending}
                                  onClick={() => setIssueTarget(row)}
                                >
                                  Issue
                                </button>
                              ) : null}
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
                  {q.trim() ? <IconSearch /> : <IconFileText />}
                </span>
                <p className="customers-empty-title">
                  {q.trim() ? "No matches" : "No proposals yet"}
                </p>
                <p className="customers-empty-copy">
                  {q.trim()
                    ? "Try another registration or product."
                    : "Create a proposal to begin."}
                </p>
              </div>
            )
          ) : null}
        </DirectoryCard>
      </div>

      {canCreate ? (
        <Modal
          open={showAdd}
          size="lg"
          title="New proposal"
          subtitle="Vehicle, cover, and customer."
          icon={<IconFileText />}
          onClose={() => {
            setShowAdd(false);
            setError(null);
          }}
          bodyClassName="intermediaries-modal-body"
          footer={
            <>
              <button
                type="button"
                className="secondary"
                onClick={() => {
                  setShowAdd(false);
                  setError(null);
                }}
              >
                Cancel
              </button>
              <button type="submit" form="proposal-create-form" disabled={create.isPending}>
                {create.isPending ? "Running checks…" : "Create"}
              </button>
            </>
          }
        >
          <form
            id="proposal-create-form"
            className="form-grid modal-form-grid intermediaries-modal-form"
            onSubmit={onSubmit}
          >
            <Select
              label="Customer"
              required
              value={form.customer_id}
              onChange={(customer_id) => setForm({ ...form, customer_id })}
              options={customerOptions}
              placeholder="Select customer"
              fieldClassName="config-field"
            />
            <Select
              label="Product"
              required
              value={form.product_code}
              onChange={(product_code) => {
                const product = (products.data ?? []).find((p) => p.code === product_code);
                setForm({
                  ...form,
                  product_code,
                  cover_option: product?.cover_options?.[0] || form.cover_option,
                });
              }}
              options={productOptions}
              placeholder="Select product"
              fieldClassName="config-field"
            />
            <Select
              label="Cover option"
              required
              value={form.cover_option}
              onChange={(cover_option) => setForm({ ...form, cover_option })}
              options={coverOptionItems}
              placeholder="Select cover"
              fieldClassName="config-field"
            />
            <label className="config-field">
              <span>Cover period (months)</span>
              <input
                required
                value={form.cover_period}
                onChange={(e) => setForm({ ...form, cover_period: e.target.value })}
              />
            </label>
            <label className="config-field">
              <span>Registration</span>
              <input
                required
                autoFocus
                value={form.vehicle_registration}
                onChange={(e) => setForm({ ...form, vehicle_registration: e.target.value })}
              />
            </label>
            <Select
              label="Make"
              required
              value={form.vehicle_make}
              onChange={(vehicle_make) => setForm({ ...form, vehicle_make })}
              options={makeOptions}
              placeholder="Select make"
              fieldClassName="config-field"
            />
            <label className="config-field">
              <span>Model</span>
              <input
                value={form.vehicle_model}
                onChange={(e) => setForm({ ...form, vehicle_model: e.target.value })}
              />
            </label>
            <label className="config-field">
              <span>Sum insured</span>
              <input
                type="number"
                min={0}
                placeholder="Optional · e.g. 1500000"
                value={form.sum_insured}
                onChange={(e) => setForm({ ...form, sum_insured: e.target.value })}
              />
            </label>
            <AnimatedFormError error={error} title="Couldn’t create" />
          </form>
        </Modal>
      ) : null}

      <Modal
        open={Boolean(approveTarget)}
        title={
          approveTarget
            ? `Approve ${approveTarget.vehicle_registration}?`
            : "Approve"
        }
        subtitle={approveTarget?.product_code}
        icon={<IconCheckCircle />}
        onClose={() => {
          if (!approve.isPending) setApproveTarget(null);
        }}
        bodyClassName="intermediaries-modal-body"
        footer={
          <>
            <button
              type="button"
              className="secondary"
              disabled={approve.isPending}
              onClick={() => setApproveTarget(null)}
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={!approveTarget || approve.isPending}
              onClick={() => {
                if (approveTarget) approve.mutate(approveTarget.id);
              }}
            >
              {approve.isPending ? "Approving…" : "Approve"}
            </button>
          </>
        }
      >
        {approveTarget ? (
          <div className="intermediaries-confirm">
            <div className="intermediaries-confirm-person">
              <span className="customers-avatar customers-avatar--empty" aria-hidden="true">
                <IconBriefcase />
              </span>
              <div className="customers-table-person-text">
                <span className="customers-table-name">
                  {approveTarget.vehicle_registration}
                </span>
                <div className="customers-table-meta">
                  <span className="customers-tag customers-tag--linked">
                    {approveTarget.product_code}
                  </span>
                  <span className="customers-tag customers-tag--kra">
                    {formatMoney(approveTarget.gross_premium)}
                  </span>
                </div>
              </div>
            </div>
          </div>
        ) : null}
      </Modal>

      <Modal
        open={Boolean(issueTarget)}
        title={
          issueTarget ? `Issue ${issueTarget.vehicle_registration}?` : "Issue"
        }
        subtitle="Creates a policy pending payment."
        icon={<IconShield />}
        onClose={() => {
          if (!issue.isPending) setIssueTarget(null);
        }}
        bodyClassName="intermediaries-modal-body"
        footer={
          <>
            <button
              type="button"
              className="secondary"
              disabled={issue.isPending}
              onClick={() => setIssueTarget(null)}
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={!issueTarget || issue.isPending}
              onClick={() => {
                if (issueTarget) issue.mutate(issueTarget.id);
              }}
            >
              {issue.isPending ? "Issuing…" : "Issue"}
            </button>
          </>
        }
      >
        {issueTarget ? (
          <div className="intermediaries-confirm">
            <div className="intermediaries-confirm-person">
              <span className="customers-avatar customers-avatar--empty" aria-hidden="true">
                <IconShield />
              </span>
              <div className="customers-table-person-text">
                <span className="customers-table-name">
                  {issueTarget.vehicle_registration}
                </span>
                <div className="customers-table-meta">
                  <span className="customers-tag customers-tag--linked">
                    {issueTarget.product_code}
                  </span>
                  <span className="customers-tag customers-tag--kra">
                    {formatMoney(issueTarget.gross_premium)}
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
