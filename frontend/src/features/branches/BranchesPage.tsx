import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { useAuth } from "@/app/providers/AuthProvider";
import { AnimatedFormError } from "@/components/ui/AnimatedFormError";
import { Modal } from "@/components/ui/Modal";
import { PhoneField } from "@/components/ui/PhoneField";
import { DEFAULT_PHONE_COUNTRY, toE164 } from "@/components/ui/phoneCountries";
import {
  IconAlert,
  IconBuilding,
  IconCheckCircle,
  IconChevronLeft,
  IconChevronRight,
  IconMail,
  IconPhone,
  IconPower,
  IconSearch,
  IconWhatsApp,
} from "@/components/ui/icons";
import { ApiError } from "@/services/api/client";
import { branchApi } from "@/services/branches/branchApi";

const PAGE_SIZE = 10;

function statusLabel(status: string) {
  const key = status.trim().toUpperCase();
  if (key === "ACTIVE") return "Active";
  if (key === "DISABLED") return "Disabled";
  return status
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function statusTone(status: string) {
  const key = status.trim().toUpperCase();
  if (key === "ACTIVE") return "active";
  if (key === "DISABLED") return "inactive";
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

function phoneDigits(phone: string) {
  return phone.replace(/\D/g, "");
}

function ContactIcons({ phone, email }: { phone?: string | null; email?: string | null }) {
  const trimmedPhone = phone?.trim() || "";
  const trimmedEmail = email?.trim() || "";
  const digits = phoneDigits(trimmedPhone);
  return (
    <div className="customers-social" role="group" aria-label="Contact channels">
      {digits ? (
        <a className="customers-social-link" href={`tel:${trimmedPhone}`} aria-label="Call" title="Call">
          <IconPhone />
        </a>
      ) : (
        <span className="customers-social-link is-disabled" aria-disabled="true" title="No phone">
          <IconPhone />
        </span>
      )}
      {digits ? (
        <a
          className="customers-social-link"
          href={`https://wa.me/${digits}`}
          target="_blank"
          rel="noopener noreferrer"
          aria-label="WhatsApp"
          title="WhatsApp"
        >
          <IconWhatsApp />
        </a>
      ) : (
        <span className="customers-social-link is-disabled" aria-disabled="true" title="No WhatsApp">
          <IconWhatsApp />
        </span>
      )}
      {trimmedEmail ? (
        <a className="customers-social-link" href={`mailto:${trimmedEmail}`} aria-label="Email" title="Email">
          <IconMail />
        </a>
      ) : (
        <span className="customers-social-link is-disabled" aria-disabled="true" title="No email">
          <IconMail />
        </span>
      )}
    </div>
  );
}

function DirectoryCard({ children, footer }: { children: ReactNode; footer?: ReactNode }) {
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
      <table className="customers-table branches-table">
        <thead>
          <tr>
            <th scope="col">Branch</th>
            <th scope="col">Status</th>
            <th scope="col">Contact</th>
            <th scope="col">Staff</th>
            <th scope="col">Updated</th>
            <th scope="col">Actions</th>
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: count }, (_, index) => (
            <tr key={`branch-skeleton-${index}`} className="customers-table-row--skeleton">
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
                <div className="customers-social">
                  <span className="skeleton-block customers-social-skeleton" />
                  <span className="skeleton-block customers-social-skeleton" />
                  <span className="skeleton-block customers-social-skeleton" />
                </div>
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

const EMPTY_FORM = {
  name: "",
  code: "",
  city: "",
  phone: "",
  email: "",
  address_line: "",
};

export function BranchesPage() {
  const { hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [phoneCountry, setPhoneCountry] = useState(DEFAULT_PHONE_COUNTRY);
  const [form, setForm] = useState(EMPTY_FORM);

  useEffect(() => {
    setPage(1);
  }, [q]);

  const list = useQuery({
    queryKey: ["branches", q, page],
    queryFn: async () =>
      (await branchApi.list({ q: q || undefined, page, limit: PAGE_SIZE })).data,
    placeholderData: (previous) => previous,
  });

  const canManage = hasPermission("branch:manage");
  const items = list.data?.items ?? [];
  const total = list.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const rangeStart = total === 0 ? 0 : (safePage - 1) * PAGE_SIZE + 1;
  const rangeEnd = total === 0 ? 0 : Math.min(safePage * PAGE_SIZE, total);
  const canPrev = safePage > 1;
  const canNext = safePage < totalPages;
  const activeCount = items.filter((row) => row.status === "ACTIVE").length;
  const disabledCount = items.filter((row) => row.status === "DISABLED").length;
  const staffTotal = items.reduce((sum, row) => sum + (row.users_count ?? 0), 0);

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  function resetForm() {
    setForm(EMPTY_FORM);
    setPhoneCountry(DEFAULT_PHONE_COUNTRY);
    setError(null);
  }

  const create = useMutation({
    mutationFn: async () => {
      const phone = form.phone.trim() ? toE164(phoneCountry, form.phone) : undefined;
      if (form.phone.trim() && !phone) throw new Error("Enter a valid phone number");
      return branchApi.create({
        name: form.name.trim(),
        code: form.code.trim() || undefined,
        city: form.city.trim() || undefined,
        phone,
        email: form.email.trim() || undefined,
        address_line: form.address_line.trim() || undefined,
      });
    },
    onMutate: () => setError(null),
    onSuccess: async () => {
      resetForm();
      setShowAdd(false);
      setPage(1);
      await queryClient.invalidateQueries({ queryKey: ["branches"] });
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : err instanceof Error ? err.message : "Unable to create branch");
    },
  });

  const setStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: "ACTIVE" | "DISABLED" }) =>
      branchApi.update(id, { status }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["branches"] });
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
      <div className="customers-pager" aria-label="Branch pagination">
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
    <section className="config-page customers-page branches-page">
      <h1 className="config-title">Branches</h1>

      <div className="customers-top">
        <div className="customers-stat-grid" aria-live="polite">
          <article className="customers-stat-card">
            <span className="customers-stat-label">All branches</span>
            <strong className="customers-stat-value">{total.toLocaleString()}</strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Active</span>
            <strong className="customers-stat-value">{activeCount.toLocaleString()}</strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Disabled</span>
            <strong className="customers-stat-value">{disabledCount.toLocaleString()}</strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Staff</span>
            <strong className="customers-stat-value">{staffTotal.toLocaleString()}</strong>
          </article>
        </div>

        <div className="customers-search-card">
          <label className="config-field customers-search">
            <span className="config-sr-only">Search branches</span>
            <span className="customers-search-shell">
              <IconSearch className="customers-search-icon" />
              <input
                type="search"
                placeholder="Search name, code, city, contact"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                autoComplete="off"
              />
            </span>
          </label>
          {canManage ? (
            <button type="button" className="config-btn customers-toolbar-add" onClick={() => setShowAdd(true)}>
              + Add branch
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
              <p className="customers-empty-title">Couldn’t load branches</p>
              <p className="customers-empty-copy">Try again in a moment.</p>
            </div>
          ) : null}

          {!(list.isLoading && !list.data) && !list.isError ? (
            items.length > 0 ? (
              <div className="customers-table-wrap">
                <table className="customers-table branches-table">
                  <thead>
                    <tr>
                      <th scope="col">Branch</th>
                      <th scope="col">Status</th>
                      <th scope="col">Contact</th>
                      <th scope="col">Staff</th>
                      <th scope="col">Updated</th>
                      <th scope="col">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((row) => {
                      const tone = statusTone(row.status);
                      const nextStatus = row.status === "DISABLED" ? "ACTIVE" : "DISABLED";
                      return (
                        <tr key={row.id}>
                          <td>
                            <div className="customers-table-person">
                              <span className="customers-avatar customers-avatar--empty" aria-hidden="true" title={row.name}>
                                <IconBuilding />
                              </span>
                              <div className="customers-table-person-text">
                                <span className="customers-table-name">{row.name}</span>
                                <div className="customers-table-meta">
                                  {row.code ? (
                                    <span className="customers-tag customers-tag--id">{row.code}</span>
                                  ) : null}
                                  {row.city ? (
                                    <span className="customers-tag customers-tag--linked">{row.city}</span>
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
                            <ContactIcons phone={row.phone} email={row.email} />
                          </td>
                          <td>
                            <span
                              className={`customers-metric-badge${
                                (row.users_count ?? 0) > 0 ? " is-up" : ""
                              }`}
                            >
                              {(row.users_count ?? 0).toLocaleString()}
                            </span>
                          </td>
                          <td>
                            <span className="customers-date-badge">
                              {formatShortDate(row.updated_at || row.created_at)}
                            </span>
                          </td>
                          <td className="directory-row-actions">
                            {canManage ? (
                              <div className="directory-row-actions-inner" role="group" aria-label="Branch actions">
                                <button
                                  type="button"
                                  className="customers-social-link"
                                  aria-label={nextStatus === "DISABLED" ? "Disable branch" : "Enable branch"}
                                  title={nextStatus === "DISABLED" ? "Disable" : "Enable"}
                                  disabled={setStatus.isPending}
                                  onClick={() => setStatus.mutate({ id: row.id, status: nextStatus })}
                                >
                                  {nextStatus === "DISABLED" ? <IconPower /> : <IconCheckCircle />}
                                </button>
                              </div>
                            ) : (
                              <span className="customers-table-empty">—</span>
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
                  {q.trim() ? <IconSearch /> : <IconBuilding />}
                </span>
                <p className="customers-empty-title">{q.trim() ? "No matches" : "No branches yet"}</p>
                <p className="customers-empty-copy">
                  {q.trim() ? "Try another name, code, city, or contact." : "Add a branch to begin."}
                </p>
              </div>
            )
          ) : null}
        </DirectoryCard>
      </div>

      {canManage ? (
        <Modal
          open={showAdd}
          size="lg"
          title="Add branch"
          subtitle="Location name, code, and contact details."
          icon={<IconBuilding />}
          onClose={() => {
            setShowAdd(false);
            resetForm();
          }}
          bodyClassName="intermediaries-modal-body"
          footer={
            <>
              <button
                type="button"
                className="secondary"
                onClick={() => {
                  setShowAdd(false);
                  resetForm();
                }}
              >
                Cancel
              </button>
              <button type="submit" form="branch-create-form" disabled={create.isPending}>
                {create.isPending ? "Saving…" : "Create"}
              </button>
            </>
          }
        >
          <form
            id="branch-create-form"
            className="form-grid modal-form-grid intermediaries-modal-form"
            onSubmit={onSubmit}
          >
            <label className="config-field">
              <span>Name</span>
              <input
                required
                autoFocus
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </label>
            <label className="config-field">
              <span>Code</span>
              <input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} />
            </label>
            <label className="config-field">
              <span>City</span>
              <input value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} />
            </label>
            <PhoneField
              label="Phone"
              value={form.phone}
              onChange={(phone) => setForm({ ...form, phone })}
              country={phoneCountry}
              onCountryChange={setPhoneCountry}
              fieldClassName="config-field"
            />
            <label className="config-field">
              <span>Email</span>
              <input
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
              />
            </label>
            <label className="config-field">
              <span>Address</span>
              <input
                value={form.address_line}
                onChange={(e) => setForm({ ...form, address_line: e.target.value })}
              />
            </label>
            <AnimatedFormError error={error} title="Couldn’t create branch" />
          </form>
        </Modal>
      ) : null}
    </section>
  );
}
