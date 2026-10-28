import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { useAuth } from "@/app/providers/AuthProvider";
import { AnimatedFormError } from "@/components/ui/AnimatedFormError";
import { Modal } from "@/components/ui/Modal";
import { PhoneField } from "@/components/ui/PhoneField";
import { Select } from "@/components/ui/Select";
import { DEFAULT_PHONE_COUNTRY, fromE164, toE164 } from "@/components/ui/phoneCountries";
import {
  IconAlert,
  IconChevronLeft,
  IconChevronRight,
  IconCheckCircle,
  IconMail,
  IconPencil,
  IconPhone,
  IconPower,
  IconSearch,
  IconUser,
  IconUsers,
  IconWhatsApp,
} from "@/components/ui/icons";
import { ApiError } from "@/services/api/client";
import { passwordStrengthError } from "@/services/auth/passwordPolicy";
import { mediaSrc } from "@/services/media/mediaSrc";
import { userApi, type StaffUser } from "@/services/users/userApi";

const PAGE_SIZE = 10;

function apiErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    if (err.message && err.message !== "The request contains invalid information") {
      return err.message;
    }
    const details = Array.isArray(err.details) ? err.details : [];
    for (const item of details) {
      if (!item || typeof item !== "object") continue;
      const msg = String((item as { msg?: unknown }).msg || "").trim();
      if (!msg) continue;
      if (msg.startsWith("Value error, ")) return msg.slice("Value error, ".length).trim();
      return msg;
    }
    return err.message || fallback;
  }
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

function statusLabel(status: string) {
  const key = status.trim().toUpperCase();
  if (key === "ACTIVE") return "Active";
  if (key === "PENDING") return "Pending";
  if (key === "DISABLED") return "Disabled";
  if (key === "LOCKED") return "Locked";
  return status
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function statusTone(status: string) {
  const key = status.trim().toUpperCase();
  if (key === "ACTIVE") return "active";
  if (key === "PENDING") return "pending";
  if (key === "DISABLED" || key === "LOCKED") return "inactive";
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

function UserAvatar({ name, avatarUrl }: { name: string; avatarUrl?: string | null }) {
  const [imgFailed, setImgFailed] = useState(false);
  const src = mediaSrc(avatarUrl);
  const showPhoto = Boolean(src) && !imgFailed;

  useEffect(() => {
    setImgFailed(false);
  }, [src]);

  if (showPhoto) {
    return (
      <img
        src={src!}
        alt=""
        className="customers-avatar customers-avatar--photo"
        onError={() => setImgFailed(true)}
      />
    );
  }

  return (
    <span className="customers-avatar customers-avatar--empty" aria-hidden="true" title={name}>
      <IconUser />
    </span>
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
      <table className="customers-table users-table">
        <thead>
          <tr>
            <th scope="col">User</th>
            <th scope="col">Role</th>
            <th scope="col">Branch</th>
            <th scope="col">Status</th>
            <th scope="col">Contact</th>
            <th scope="col">Last login</th>
            <th scope="col">Actions</th>
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: count }, (_, index) => (
            <tr key={`user-skeleton-${index}`} className="customers-table-row--skeleton">
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
                <span className="skeleton-block skeleton-block--meta" />
              </td>
              <td>
                <span className="skeleton-block skeleton-block--meta" />
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
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const EMPTY_FORM = {
  full_name: "",
  email: "",
  phone: "",
  role_id: "",
  branch_id: "",
  password: "",
};

export function UsersPage() {
  const { user: currentUser, hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [editing, setEditing] = useState<StaffUser | null>(null);
  const [phoneCountry, setPhoneCountry] = useState(DEFAULT_PHONE_COUNTRY);
  const [form, setForm] = useState(EMPTY_FORM);
  const modalOpen = showAdd || Boolean(editing);

  useEffect(() => {
    setPage(1);
  }, [q]);

  const list = useQuery({
    queryKey: ["users", q, page],
    queryFn: async () => (await userApi.list({ q: q || undefined, page, limit: PAGE_SIZE })).data,
    placeholderData: (previous) => previous,
  });

  const options = useQuery({
    queryKey: ["users-options"],
    queryFn: async () => (await userApi.options()).data,
    enabled: modalOpen,
  });

  const canCreate = hasPermission("user:create");
  const canUpdate = hasPermission("user:update");
  const canDisable = hasPermission("user:disable");
  const roleOptions = [
    ...(options.data?.roles ?? []),
    ...(editing?.role_id && !(options.data?.roles ?? []).some((role) => role.id === editing.role_id)
      ? [{ id: editing.role_id, name: editing.role_name || "Current role", code: editing.role_code }]
      : []),
  ];
  const branchOptions = [
    ...(options.data?.branches ?? []),
    ...(editing?.branch_id &&
    !(options.data?.branches ?? []).some((branch) => branch.id === editing.branch_id)
      ? [
          {
            id: editing.branch_id,
            name: editing.branch_name || "Current branch",
            code: editing.branch_code,
          },
        ]
      : []),
  ];
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
  const pendingCount = items.filter((row) => row.status === "PENDING").length;

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  function resetForm() {
    setForm(EMPTY_FORM);
    setPhoneCountry(DEFAULT_PHONE_COUNTRY);
    setEditing(null);
    setError(null);
  }

  function openEdit(row: StaffUser) {
    const parsed = fromE164(row.phone);
    setEditing(row);
    setShowAdd(false);
    setError(null);
    setPhoneCountry(parsed.iso);
    setForm({
      full_name: row.full_name,
      email: row.email,
      phone: parsed.national,
      role_id: row.role_id || "",
      branch_id: row.branch_id || "",
      password: "",
    });
  }

  const create = useMutation({
    mutationFn: async () => {
      if (!form.role_id) throw new Error("Select a role");
      const passwordError = passwordStrengthError(form.password);
      if (passwordError) throw new Error(passwordError);
      const phone = form.phone.trim() ? toE164(phoneCountry, form.phone) : undefined;
      if (form.phone.trim() && !phone) throw new Error("Enter a valid phone number");
      return userApi.create({
        full_name: form.full_name.trim(),
        email: form.email.trim(),
        password: form.password,
        phone,
        role_id: form.role_id,
        branch_id: form.branch_id || undefined,
      });
    },
    onMutate: () => setError(null),
    onSuccess: async () => {
      resetForm();
      setShowAdd(false);
      setPage(1);
      await queryClient.invalidateQueries({ queryKey: ["users"] });
    },
    onError: (err) => {
      setError(apiErrorMessage(err, "Unable to create user"));
    },
  });

  const update = useMutation({
    mutationFn: async () => {
      if (!editing) throw new Error("Select a user to edit");
      if (!form.role_id) throw new Error("Select a role");
      if (form.password.trim()) {
        const passwordError = passwordStrengthError(form.password);
        if (passwordError) throw new Error(passwordError);
      }
      const phone = form.phone.trim() ? toE164(phoneCountry, form.phone) : "";
      if (form.phone.trim() && !phone) throw new Error("Enter a valid phone number");
      return userApi.update(editing.id, {
        full_name: form.full_name.trim(),
        email: form.email.trim(),
        phone: phone || null,
        role_id: form.role_id,
        branch_id: form.branch_id || undefined,
        password: form.password.trim() || undefined,
      });
    },
    onMutate: () => setError(null),
    onSuccess: async () => {
      resetForm();
      await queryClient.invalidateQueries({ queryKey: ["users"] });
    },
    onError: (err) => {
      setError(apiErrorMessage(err, "Unable to update user"));
    },
  });

  const setStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: "ACTIVE" | "DISABLED" }) =>
      userApi.setStatus(id, status),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (editing) update.mutate();
    else create.mutate();
  }

  function closeModal() {
    setShowAdd(false);
    resetForm();
  }

  const footer = (
    <div className="customers-footer">
      <div className="customers-pager-meta customers-footer-range">
        {total === 0 ? "0 of 0" : `${rangeStart}–${rangeEnd} of ${total}`}
      </div>
      <div className="customers-pager" aria-label="User pagination">
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
    <section className="config-page customers-page users-page">
      <h1 className="config-title">Users</h1>

      <div className="customers-top">
        <div className="customers-stat-grid" aria-live="polite">
          <article className="customers-stat-card">
            <span className="customers-stat-label">All users</span>
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
            <span className="customers-stat-label">Disabled</span>
            <strong className="customers-stat-value">{disabledCount.toLocaleString()}</strong>
          </article>
        </div>

        <div className="customers-search-card">
          <label className="config-field customers-search">
            <span className="config-sr-only">Search users</span>
            <span className="customers-search-shell">
              <IconSearch className="customers-search-icon" />
              <input
                type="search"
                placeholder="Search name, email, role, branch"
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
              + Add user
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
              <p className="customers-empty-title">Couldn’t load users</p>
              <p className="customers-empty-copy">Try again in a moment.</p>
            </div>
          ) : null}

          {!(list.isLoading && !list.data) && !list.isError ? (
            items.length > 0 ? (
              <div className="customers-table-wrap">
                <table className="customers-table users-table">
                  <thead>
                    <tr>
                      <th scope="col">User</th>
                      <th scope="col">Role</th>
                      <th scope="col">Branch</th>
                      <th scope="col">Status</th>
                      <th scope="col">Contact</th>
                      <th scope="col">Last login</th>
                      <th scope="col">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((row) => {
                      const tone = statusTone(row.status);
                      const isSelf = row.id === currentUser?.id;
                      const nextStatus = row.status === "DISABLED" ? "ACTIVE" : "DISABLED";
                      return (
                        <tr key={row.id}>
                          <td>
                            <div className="customers-table-person">
                              <UserAvatar name={row.full_name} avatarUrl={row.avatar_url} />
                              <div className="customers-table-person-text">
                                <span className="customers-table-name">{row.full_name}</span>
                                <div className="customers-table-meta">
                                  <span className="customers-tag customers-tag--id">{row.email}</span>
                                </div>
                              </div>
                            </div>
                          </td>
                          <td>
                            <span className="customers-tag users-role-badge">
                              {row.role_name || "—"}
                            </span>
                          </td>
                          <td>
                            {row.branch_name ? (
                              <span className="customers-tag claims-agency-badge">
                                {row.branch_name}
                              </span>
                            ) : (
                              <span className="customers-table-empty">—</span>
                            )}
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
                            {row.last_login_at ? (
                              <span className="customers-date-badge">
                                {formatShortDate(row.last_login_at)}
                              </span>
                            ) : (
                              <span className="customers-date-badge customers-date-badge--empty">
                                —
                              </span>
                            )}
                          </td>
                          <td className="directory-row-actions">
                            {canUpdate ||
                            (canDisable && !isSelf && (row.status === "ACTIVE" || row.status === "DISABLED")) ? (
                              <div className="directory-row-actions-inner" role="group" aria-label="User actions">
                                {canUpdate ? (
                                  <button
                                    type="button"
                                    className="customers-social-link"
                                    aria-label="Edit user"
                                    title="Edit"
                                    onClick={() => openEdit(row)}
                                  >
                                    <IconPencil />
                                  </button>
                                ) : null}
                                {canDisable && !isSelf && (row.status === "ACTIVE" || row.status === "DISABLED") ? (
                                  <button
                                    type="button"
                                    className="customers-social-link"
                                    aria-label={nextStatus === "DISABLED" ? "Disable user" : "Enable user"}
                                    title={nextStatus === "DISABLED" ? "Disable" : "Enable"}
                                    disabled={setStatus.isPending}
                                    onClick={() => setStatus.mutate({ id: row.id, status: nextStatus })}
                                  >
                                    {nextStatus === "DISABLED" ? <IconPower /> : <IconCheckCircle />}
                                  </button>
                                ) : null}
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
                  {q.trim() ? <IconSearch /> : <IconUsers />}
                </span>
                <p className="customers-empty-title">{q.trim() ? "No matches" : "No users yet"}</p>
                <p className="customers-empty-copy">
                  {q.trim() ? "Try another name, email, role, or branch." : "Add a staff user to begin."}
                </p>
              </div>
            )
          ) : null}
        </DirectoryCard>
      </div>

      {canCreate || canUpdate ? (
        <Modal
          open={modalOpen}
          size="lg"
          title={editing ? "Edit user" : "Add user"}
          subtitle={
            editing
              ? "Update name, contact, role, or home branch."
              : "Name, sign-in, role, and home branch."
          }
          icon={<IconUsers />}
          onClose={closeModal}
          bodyClassName="intermediaries-modal-body"
          footer={
            <>
              <button type="button" className="secondary" onClick={closeModal}>
                Cancel
              </button>
              <button
                type="submit"
                form="user-create-form"
                disabled={create.isPending || update.isPending}
              >
                {create.isPending || update.isPending ? "Saving…" : editing ? "Save" : "Create"}
              </button>
            </>
          }
        >
          <form id="user-create-form" className="form-grid modal-form-grid intermediaries-modal-form" onSubmit={onSubmit}>
            <label className="config-field">
              <span>Full name</span>
              <input
                required
                autoFocus
                value={form.full_name}
                onChange={(e) => setForm({ ...form, full_name: e.target.value })}
              />
            </label>
            <label className="config-field">
              <span>Email</span>
              <input
                required
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
              />
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
              <span>{editing ? "New password" : "Password"}</span>
              <input
                required={!editing}
                type="password"
                autoComplete="new-password"
                minLength={editing ? undefined : 6}
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                placeholder={editing ? "Leave blank to keep current" : undefined}
              />
              {/* <span className="ui-field-hint">At least 6 characters.</span> */}
            </label>
            <Select
              label="Role"
              required
              value={form.role_id}
              onChange={(role_id) => setForm({ ...form, role_id })}
              options={roleOptions.map((role) => ({
                value: role.id,
                label: role.name,
              }))}
              placeholder={options.isLoading ? "Loading roles…" : "Select a role"}
              fieldClassName="config-field"
            />
            <Select
              label="Branch"
              value={form.branch_id}
              onChange={(branch_id) => setForm({ ...form, branch_id })}
              options={branchOptions.map((branch) => ({
                value: branch.id,
                label: branch.code ? `${branch.name} (${branch.code})` : branch.name,
              }))}
              placeholder={options.isLoading ? "Loading branches…" : "Home branch"}
              fieldClassName="config-field"
            />
            <AnimatedFormError
              error={error}
              title={editing ? "Couldn’t update user" : "Couldn’t create user"}
            />
          </form>
        </Modal>
      ) : null}
    </section>
  );
}
