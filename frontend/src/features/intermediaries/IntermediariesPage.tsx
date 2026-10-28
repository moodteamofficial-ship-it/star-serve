import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  useEffect,
  useState,
  type FormEvent,
  type ReactNode,
  type SVGProps,
} from "react";
import { buildWelcomeAgentQrUrl } from "@/services/insurance/guestAgent";
import { buildBrandedAgentQrDataUrl } from "@/features/intermediaries/brandedAgentQr";
import { useAuth } from "@/app/providers/AuthProvider";
import { AnimatedFormError } from "@/components/ui/AnimatedFormError";
import { Modal } from "@/components/ui/Modal";
import { PhoneField } from "@/components/ui/PhoneField";
import {
  DEFAULT_PHONE_COUNTRY,
  fromE164,
  toE164,
} from "@/components/ui/phoneCountries";
import {
  IconAlert,
  IconCheckCircle,
  IconChevronRight,
  IconDownload,
  IconMail,
  IconPencil,
  IconPhone,
  IconSearch,
  IconUser,
  IconUsers,
  IconWhatsApp,
} from "@/components/ui/icons";
import { ApiError } from "@/services/api/client";
import { passwordStrengthError } from "@/services/auth/passwordPolicy";
import {
  intermediaryApi,
  type AgentKitChannel,
  type Intermediary,
} from "@/services/intermediaries/intermediaryApi";

const KIT_CHANNEL_META: Record<
  AgentKitChannel,
  { label: string; icon: typeof IconMail }
> = {
  EMAIL: { label: "Email", icon: IconMail },
  SMS: { label: "SMS", icon: IconPhone },
  WHATSAPP: { label: "WhatsApp", icon: IconWhatsApp },
};

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

function phoneDigits(phone: string) {
  return phone.replace(/\D/g, "");
}

function statusLabel(status: string) {
  const key = status.trim().toUpperCase();
  if (key === "APPROVED") return "Approved";
  if (key === "PENDING") return "Pending";
  if (key === "SUSPENDED") return "Suspended";
  if (key === "REJECTED") return "Rejected";
  return status
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function statusTone(status: string) {
  const key = status.trim().toUpperCase();
  if (key === "APPROVED") return "active";
  if (key === "PENDING") return "pending";
  if (key === "SUSPENDED") return "suspended";
  if (key === "REJECTED") return "inactive";
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

function ContactIcons({
  phone,
  email,
}: {
  phone?: string | null;
  email?: string | null;
}) {
  const trimmedPhone = phone?.trim() || "";
  const trimmedEmail = email?.trim() || "";
  const digits = phoneDigits(trimmedPhone);
  const canCall = Boolean(digits);
  const canWhatsApp = Boolean(digits);
  const canEmail = Boolean(trimmedEmail);

  return (
    <div className="customers-social" role="group" aria-label="Contact channels">
      {canCall ? (
        <a className="customers-social-link" href={`tel:${trimmedPhone}`} aria-label="Call" title="Call">
          <IconPhone />
        </a>
      ) : (
        <span className="customers-social-link is-disabled" aria-disabled="true" title="No phone">
          <IconPhone />
        </span>
      )}
      {canWhatsApp ? (
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
      {canEmail ? (
        <a
          className="customers-social-link"
          href={`mailto:${trimmedEmail}`}
          aria-label="Email"
          title="Email"
        >
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

function AgentAvatar({ name }: { name: string }) {
  return (
    <span className="customers-avatar customers-avatar--empty" aria-hidden="true" title={name}>
      <IconUser />
    </span>
  );
}

function loginLabel(agent: Intermediary): { text: string; tone: string } {
  if (!agent.has_login) return { text: "No login yet", tone: "neutral" };
  switch (agent.login_status) {
    case "ACTIVE":
      return { text: "Can sign in", tone: "active" };
    case "PENDING":
      return { text: "Awaiting approval", tone: "pending" };
    case "LOCKED":
      return { text: "Locked", tone: "suspended" };
    default:
      return { text: "Disabled", tone: "suspended" };
  }
}

function AgentLoginSection({
  agent,
  canEdit,
  onUpdated,
}: {
  agent: Intermediary;
  canEdit: boolean;
  onUpdated: (agent: Intermediary) => void;
}) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setOpen(false);
    setPassword("");
    setError(null);
    setSaved(false);
  }, [agent.id]);

  const save = useMutation({
    mutationFn: async () => {
      const problem = passwordStrengthError(password);
      if (problem) throw new Error(problem);
      return intermediaryApi.setLogin(agent.id, password);
    },
    onMutate: () => setError(null),
    onSuccess: async (res) => {
      setOpen(false);
      setPassword("");
      setSaved(true);
      onUpdated(res.data);
      await queryClient.invalidateQueries({ queryKey: ["intermediaries"] });
    },
    onError: (err) => {
      if (err instanceof ApiError && err.status === 404) {
        setError("Agent logins are available after the next backend deploy.");
        return;
      }
      setError(err instanceof Error && err.message ? err.message : "Unable to save login");
    },
  });

  const label = loginLabel(agent);

  return (
    <div className="intermediaries-login">
      <div className="intermediaries-login-head">
        <div className="intermediaries-login-copy">
          <p className="customers-stat-label">Sales Agent login</p>
          <span className={`customers-status-dot customers-status-dot--${label.tone}`}>
            <span className="customers-status-dot__mark" aria-hidden="true" />
            {label.text}
          </span>
          <span className="intermediaries-login-sub">
            {saved ? "Password saved." : `Signs in as ${agent.email}`}
          </span>
        </div>
        {canEdit && !open ? (
          <button
            type="button"
            className="secondary intermediaries-login-btn"
            onClick={() => {
              setSaved(false);
              setOpen(true);
            }}
          >
            {agent.has_login ? "Reset password" : "Create login"}
          </button>
        ) : null}
      </div>
      {open ? (
        <form
          className="intermediaries-login-form"
          onSubmit={(event) => {
            event.preventDefault();
            if (!save.isPending) save.mutate();
          }}
        >
          <label className="config-field">
            <span className="config-sr-only">New password</span>
            <input
              type="password"
              autoFocus
              autoComplete="new-password"
              minLength={6}
              placeholder="New password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <button
            type="button"
            className="secondary"
            disabled={save.isPending}
            onClick={() => {
              setOpen(false);
              setPassword("");
              setError(null);
            }}
          >
            Cancel
          </button>
          <button type="submit" disabled={save.isPending || !password}>
            {save.isPending ? "Saving…" : "Save"}
          </button>
          <AnimatedFormError error={error} title="Couldn’t save login" />
        </form>
      ) : null}
    </div>
  );
}

function AgentDetailModal({
  agent,
  open,
  canEdit,
  onClose,
  onUpdated,
}: {
  agent: Intermediary | null;
  open: boolean;
  canEdit: boolean;
  onClose: () => void;
  onUpdated: (agent: Intermediary) => void;
}) {
  const queryClient = useQueryClient();
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null);
  const [qrError, setQrError] = useState<string | null>(null);
  const [resendNote, setResendNote] = useState<string | null>(null);
  const [resendError, setResendError] = useState<string | null>(null);
  const [resendingChannel, setResendingChannel] = useState<AgentKitChannel | null>(null);
  const [editing, setEditing] = useState(false);
  const [editArmed, setEditArmed] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [phoneCountry, setPhoneCountry] = useState(DEFAULT_PHONE_COUNTRY);
  const [editForm, setEditForm] = useState({
    name: "",
    email: "",
    phone: "",
    kra_pin: "",
  });

  useEffect(() => {
    if (!open) {
      setEditing(false);
      setEditArmed(false);
      setEditError(null);
      setResendNote(null);
      setResendError(null);
      setResendingChannel(null);
    }
  }, [open]);

  useEffect(() => {
    setEditing(false);
    setEditArmed(false);
    setEditError(null);
    setResendNote(null);
    setResendError(null);
    setResendingChannel(null);
  }, [agent?.id]);

  const kitChannels = useQuery({
    queryKey: ["intermediaries", "kit-channels", agent?.id],
    queryFn: async () => {
      if (!agent) return [] as AgentKitChannel[];
      return (await intermediaryApi.kitChannels(agent.id)).data.channels;
    },
    enabled: open && Boolean(agent?.id) && !editing && canEdit,
  });

  const resendKit = useMutation({
    mutationFn: async (channel: AgentKitChannel) => {
      if (!agent) throw new Error("No agent selected");
      return intermediaryApi.resendKit(agent.id, channel);
    },
    onMutate: (channel) => {
      setResendingChannel(channel);
      setResendNote(null);
      setResendError(null);
    },
    onSuccess: async (_res, channel) => {
      const label = KIT_CHANNEL_META[channel].label;
      setResendNote(`Agent kit queued via ${label}.`);
      await queryClient.invalidateQueries({
        queryKey: ["intermediaries", "kit-channels", agent?.id],
      });
    },
    onError: (err) => {
      setResendError(err instanceof ApiError ? err.message : "Couldn’t resend the agent kit");
    },
    onSettled: () => setResendingChannel(null),
  });

  useEffect(() => {
    if (!editing) {
      setEditArmed(false);
      return;
    }
    // Prevent the Edit click from landing on Save in the same footer slot.
    const timer = window.setTimeout(() => setEditArmed(true), 350);
    return () => window.clearTimeout(timer);
  }, [editing]);

  useEffect(() => {
    if (!open || !agent || editing) return;
    const parsed = fromE164(agent.phone);
    setEditForm({
      name: agent.name,
      email: agent.email,
      phone: parsed.national,
      kra_pin: agent.kra_pin ?? "",
    });
    setPhoneCountry(parsed.iso);
    setEditError(null);
  }, [open, agent, editing]);

  useEffect(() => {
    if (!open || !agent?.agent_code) {
      setQrDataUrl(null);
      setQrError(null);
      return;
    }
    let cancelled = false;
    setQrDataUrl(null);
    setQrError(null);
    void buildBrandedAgentQrDataUrl({
      payloadUrl: buildWelcomeAgentQrUrl(agent.agent_code),
      agentName: agent.name,
      agentCode: agent.agent_code,
    })
      .then((url) => {
        if (!cancelled) setQrDataUrl(url);
      })
      .catch(() => {
        if (!cancelled) setQrError("Couldn’t generate QR code");
      });
    return () => {
      cancelled = true;
    };
  }, [open, agent?.agent_code, agent?.id, agent?.name]);

  const update = useMutation({
    mutationFn: async () => {
      if (!agent) throw new Error("No agent selected");
      const phone = toE164(phoneCountry, editForm.phone);
      if (!phone) throw new Error("Enter a valid phone number");
      const name = editForm.name.trim();
      const email = editForm.email.trim();
      if (name.length < 2) throw new Error("Name must be at least 2 characters");
      if (!email) throw new Error("Email is required");
      return intermediaryApi.update(agent.id, {
        name,
        email,
        phone,
        kra_pin: editForm.kra_pin.trim() || null,
      });
    },
    onMutate: () => setEditError(null),
    onSuccess: async (res) => {
      setEditing(false);
      onUpdated(res.data);
      await queryClient.invalidateQueries({ queryKey: ["intermediaries"] });
    },
    onError: (err) => {
      setEditError(err instanceof ApiError ? err.message : "Unable to update agent");
    },
  });

  function downloadQr() {
    if (!qrDataUrl || !agent) return;
    const safeName =
      agent.name
        .trim()
        .replace(/[^\w\s-]+/g, "")
        .replace(/\s+/g, "-")
        .replace(/-+/g, "-")
        .replace(/^-|-$/g, "")
        .toLowerCase() || "agent";
    const link = document.createElement("a");
    link.href = qrDataUrl;
    link.download = `${safeName}-${agent.agent_code}-qr.png`;
    link.click();
  }

  function cancelEdit() {
    if (!agent || update.isPending) return;
    const parsed = fromE164(agent.phone);
    setEditForm({
      name: agent.name,
      email: agent.email,
      phone: parsed.national,
      kra_pin: agent.kra_pin ?? "",
    });
    setPhoneCountry(parsed.iso);
    setEditError(null);
    setEditing(false);
  }

  function onEditSubmit(e?: FormEvent) {
    e?.preventDefault();
    if (!editArmed || update.isPending) return;
    update.mutate();
  }

  const tone = agent ? statusTone(agent.status) : "neutral";
  const kra = agent?.kra_pin?.trim() || "";
  const linked = Boolean(agent?.external_intermediary_ref?.trim());

  return (
    <Modal
      open={open && Boolean(agent)}
      size="xl"
      title={editing ? "Edit agent" : (agent?.name ?? "Agent")}
      subtitle={
        agent
          ? editing
            ? `Agent code ${agent.agent_code} · ID ${agent.identification}`
            : `Agent code ${agent.agent_code}`
          : undefined
      }
      icon={<IconUsers />}
      onClose={() => {
        if (update.isPending) return;
        if (editing) {
          cancelEdit();
          return;
        }
        onClose();
      }}
      panelClassName="intermediaries-detail-modal"
      bodyClassName="intermediaries-modal-body"
      footer={
        editing ? (
          <>
            <button
              type="button"
              className="secondary"
              disabled={update.isPending}
              onClick={cancelEdit}
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={!editArmed || update.isPending}
              onClick={() => onEditSubmit()}
            >
              {update.isPending ? "Saving…" : "Save changes"}
            </button>
          </>
        ) : (
          <>
            <button type="button" className="secondary" onClick={onClose}>
              Close
            </button>
            {canEdit ? (
              <button
                type="button"
                className="secondary"
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  setEditing(true);
                }}
              >
                <IconPencil />
                Edit details
              </button>
            ) : null}
            <button type="button" disabled={!qrDataUrl} onClick={downloadQr}>
              <IconDownload />
              Download QR
            </button>
          </>
        )
      }
    >
      {agent ? (
        <div className="intermediaries-detail">
          {editing ? (
            <form
              id="intermediary-edit-form"
              className="form-grid modal-form-grid intermediaries-modal-form"
              onSubmit={onEditSubmit}
            >
              <label className="config-field">
                <span>Name</span>
                <input
                  required
                  autoFocus
                  value={editForm.name}
                  onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                />
              </label>
              <label className="config-field">
                <span>Email</span>
                <input
                  required
                  type="email"
                  value={editForm.email}
                  onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
                />
              </label>
              <PhoneField
                label="Phone"
                value={editForm.phone}
                onChange={(phone) => setEditForm({ ...editForm, phone })}
                country={phoneCountry}
                onCountryChange={setPhoneCountry}
                required
                fieldClassName="config-field config-field--wide"
              />
              <label className="config-field">
                <span>KRA PIN</span>
                <input
                  value={editForm.kra_pin}
                  onChange={(e) => setEditForm({ ...editForm, kra_pin: e.target.value })}
                />
              </label>
              <label className="config-field">
                <span>Agent code</span>
                <input value={agent.agent_code} disabled readOnly />
              </label>
              <label className="config-field">
                <span>Identification</span>
                <input value={agent.identification} disabled readOnly />
              </label>
              <AnimatedFormError error={editError} title="Couldn’t update" />
            </form>
          ) : (
            <>
              <div className="intermediaries-detail-top">
                <div className="intermediaries-detail-identity">
                  <AgentAvatar name={agent.name} />
                  <div className="intermediaries-detail-copy">
                    <strong>{agent.name}</strong>
                    <span className={`customers-status-dot customers-status-dot--${tone}`}>
                      <span className="customers-status-dot__mark" aria-hidden="true" />
                      {statusLabel(agent.status)}
                    </span>
                  </div>
                </div>
                <div className="intermediaries-detail-contacts">
                  <ContactIcons phone={agent.phone} email={agent.email} />
                </div>
              </div>

              <dl className="intermediaries-detail-facts">
                <div>
                  <dt>Agent code</dt>
                  <dd className="mono">{agent.agent_code}</dd>
                </div>
                <div>
                  <dt>Identification</dt>
                  <dd>{agent.identification}</dd>
                </div>
                <div>
                  <dt>Phone</dt>
                  <dd>{agent.phone || "—"}</dd>
                </div>
                <div>
                  <dt>Email</dt>
                  <dd>{agent.email || "—"}</dd>
                </div>
                <div>
                  <dt>KRA PIN</dt>
                  <dd>{kra || "—"}</dd>
                </div>
                <div>
                  <dt>Provider link</dt>
                  <dd>{linked ? agent.external_intermediary_ref : "Not linked"}</dd>
                </div>
                <div>
                  <dt>Registered</dt>
                  <dd>{formatShortDate(agent.created_at)}</dd>
                </div>
                <div>
                  <dt>Updated</dt>
                  <dd>{formatShortDate(agent.updated_at || agent.created_at)}</dd>
                </div>
              </dl>

              <AgentLoginSection agent={agent} canEdit={canEdit} onUpdated={onUpdated} />

              <div className="intermediaries-detail-qr">
                <div className="intermediaries-detail-qr-copy">
                  <p className="customers-stat-label">Agent QR</p>
                  <strong>How to share</strong>
                  <ol className="customers-referral-steps">
                    <li>Download the QR and share it (print, WhatsApp, or show on screen).</li>
                    <li>A customer scans it on their phone.</li>
                    <li>The welcome quote opens with this agent already selected.</li>
                    <li>When they pay for cover, this agent is credited on the sale.</li>
                  </ol>
                  {canEdit ? (
                    <div className="intermediaries-kit-resend">
                      <p className="intermediaries-kit-resend-label">Resend kit</p>
                      {kitChannels.isLoading ? (
                        <div className="intermediaries-kit-resend-actions" aria-busy="true">
                          <span className="skeleton-block intermediaries-kit-resend-skel" />
                          <span className="skeleton-block intermediaries-kit-resend-skel" />
                        </div>
                      ) : (kitChannels.data?.length ?? 0) > 0 ? (
                        <div className="intermediaries-kit-resend-actions">
                          {(kitChannels.data ?? []).map((channel) => {
                            const meta = KIT_CHANNEL_META[channel];
                            const Icon = meta.icon;
                            const busy = resendingChannel === channel;
                            return (
                              <button
                                key={channel}
                                type="button"
                                className="secondary intermediaries-kit-resend-btn"
                                disabled={resendKit.isPending}
                                onClick={() => resendKit.mutate(channel)}
                              >
                                <Icon />
                                {busy ? "Sending…" : meta.label}
                              </button>
                            );
                          })}
                        </div>
                      ) : (
                        <p className="intermediaries-kit-resend-empty">
                          No enabled notification channels are available for this agent.
                        </p>
                      )}
                      {resendNote ? (
                        <p className="intermediaries-kit-resend-note" role="status">
                          {resendNote}
                        </p>
                      ) : null}
                      <AnimatedFormError error={resendError} title="Couldn’t resend" />
                    </div>
                  ) : null}
                </div>
                <div className="intermediaries-detail-qr-frame" aria-live="polite">
                  {qrDataUrl ? (
                    <img src={qrDataUrl} alt={`QR code for agent ${agent.agent_code}`} />
                  ) : qrError ? (
                    <p className="intermediaries-detail-qr-fallback">{qrError}</p>
                  ) : (
                    <span className="skeleton-block intermediaries-detail-qr-skel" aria-hidden="true" />
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      ) : null}
    </Modal>
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
      <table className="customers-table intermediaries-table">
        <thead>
          <tr>
            <th scope="col">Agent</th>
            <th scope="col">Status</th>
            <th scope="col">Contact</th>
            <th scope="col">Updated</th>
            <th scope="col">
              <span className="config-sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: count }, (_, index) => (
            <tr key={`intermediary-skeleton-${index}`} className="customers-table-row--skeleton">
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
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function IntermediariesPage() {
  const { hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [approveTarget, setApproveTarget] = useState<Intermediary | null>(null);
  const [detailTarget, setDetailTarget] = useState<Intermediary | null>(null);
  const [phoneCountry, setPhoneCountry] = useState(DEFAULT_PHONE_COUNTRY);
  const [form, setForm] = useState({
    name: "",
    email: "",
    phone: "",
    identification: "",
    agent_code: "",
    kra_pin: "",
    password: "",
  });

  useEffect(() => {
    setPage(1);
  }, [q]);

  const list = useQuery({
    queryKey: ["intermediaries", q, page],
    queryFn: async () =>
      (await intermediaryApi.list({ q: q || undefined, page, limit: PAGE_SIZE })).data,
    placeholderData: (previous) => previous,
  });

  const canCreate = hasPermission("agent:create");
  const canApprove = hasPermission("agent:approve");
  const items = list.data?.items ?? [];
  const total = list.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const rangeStart = total === 0 ? 0 : (safePage - 1) * PAGE_SIZE + 1;
  const rangeEnd = total === 0 ? 0 : Math.min(safePage * PAGE_SIZE, total);
  const canPrev = safePage > 1;
  const canNext = safePage < totalPages;
  const approvedCount = items.filter((row) => row.status === "APPROVED").length;
  const pendingCount = items.filter((row) => row.status === "PENDING").length;
  const suspendedCount = items.filter((row) => row.status === "SUSPENDED").length;

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  function resetForm() {
    setForm({
      name: "",
      email: "",
      phone: "",
      identification: "",
      agent_code: "",
      kra_pin: "",
      password: "",
    });
    setPhoneCountry(DEFAULT_PHONE_COUNTRY);
    setError(null);
  }

  const create = useMutation({
    mutationFn: async () => {
      const phone = toE164(phoneCountry, form.phone);
      if (!phone) throw new Error("Enter a valid phone number");
      const agentCode = form.agent_code.trim();
      if (agentCode && !/^\d{6}$/.test(agentCode)) {
        throw new Error("Agent code must be exactly 6 digits, or leave blank to auto-generate");
      }
      const passwordError = passwordStrengthError(form.password);
      if (passwordError) throw new Error(passwordError);
      return intermediaryApi.create({
        name: form.name.trim(),
        email: form.email.trim(),
        phone,
        identification: form.identification.trim(),
        agent_code: agentCode || undefined,
        kra_pin: form.kra_pin.trim() || undefined,
        password: form.password,
      });
    },
    onMutate: () => {
      setError(null);
    },
    onSuccess: async () => {
      resetForm();
      setShowAdd(false);
      setPage(1);
      await queryClient.invalidateQueries({ queryKey: ["intermediaries"] });
    },
    onError: (err) => {
      setError(err instanceof Error && err.message ? err.message : "Unable to create intermediary");
    },
  });

  const approve = useMutation({
    mutationFn: (id: string) => intermediaryApi.approve(id),
    onSuccess: async () => {
      setApproveTarget(null);
      await queryClient.invalidateQueries({ queryKey: ["intermediaries"] });
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
      <div className="customers-pager" aria-label="Intermediary pagination">
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
    <section className="config-page customers-page intermediaries-page">
      <h1 className="config-title">Intermediaries</h1>

      <div className="customers-top">
        <div className="customers-stat-grid" aria-live="polite">
          <article className="customers-stat-card">
            <span className="customers-stat-label">All agents</span>
            <strong className="customers-stat-value">{total.toLocaleString()}</strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Approved</span>
            <strong className="customers-stat-value">{approvedCount.toLocaleString()}</strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Pending</span>
            <strong className="customers-stat-value">{pendingCount.toLocaleString()}</strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Suspended</span>
            <strong className="customers-stat-value">{suspendedCount.toLocaleString()}</strong>
          </article>
        </div>

        <div className="customers-search-card">
          <label className="config-field customers-search">
            <span className="config-sr-only">Search intermediaries</span>
            <span className="customers-search-shell">
              <IconSearch className="customers-search-icon" />
              <input
                type="search"
                placeholder="Search name, code, ID, phone, email"
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
              onClick={() => setShowAdd(true)}
            >
              + Register
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
              <p className="customers-empty-title">Couldn’t load intermediaries</p>
              <p className="customers-empty-copy">Try again in a moment.</p>
            </div>
          ) : null}

          {!(list.isLoading && !list.data) && !list.isError ? (
            items.length > 0 ? (
              <div className="customers-table-wrap">
                <table className="customers-table intermediaries-table">
                  <thead>
                    <tr>
                      <th scope="col">Agent</th>
                      <th scope="col">Status</th>
                      <th scope="col">Contact</th>
                      <th scope="col">Updated</th>
                      <th scope="col">
                        <span className="config-sr-only">Actions</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((row) => {
                      const kra = row.kra_pin?.trim() || "";
                      const linked = Boolean(row.external_intermediary_ref?.trim());
                      const tone = statusTone(row.status);
                      const pending = row.status === "PENDING";
                      return (
                        <tr
                          key={row.id}
                          className="intermediaries-row is-clickable"
                          tabIndex={0}
                          aria-label={`View ${row.name}`}
                          onClick={() => setDetailTarget(row)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter" || event.key === " ") {
                              event.preventDefault();
                              setDetailTarget(row);
                            }
                          }}
                        >
                          <td>
                            <div className="customers-table-person">
                              <AgentAvatar name={row.name} />
                              <div className="customers-table-person-text">
                                <span className="customers-table-name">{row.name}</span>
                                <div className="customers-table-meta">
                                  <span className="customers-tag customers-tag--id">
                                    {row.agent_code}
                                  </span>
                                  <span className="customers-tag customers-tag--id">
                                    {row.identification}
                                  </span>
                                  {kra ? (
                                    <span className="customers-tag customers-tag--kra">KRA</span>
                                  ) : null}
                                  {linked ? (
                                    <span className="customers-tag customers-tag--linked">Linked</span>
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
                          <td onClick={(event) => event.stopPropagation()}>
                            <ContactIcons phone={row.phone} email={row.email} />
                          </td>
                          <td>
                            <span className="customers-date-badge">
                              {formatShortDate(row.updated_at || row.created_at)}
                            </span>
                          </td>
                          <td
                            className="intermediaries-actions"
                            onClick={(event) => event.stopPropagation()}
                          >
                            {canApprove && pending ? (
                              <button
                                type="button"
                                className="intermediaries-approve-btn"
                                disabled={approve.isPending}
                                onClick={() => setApproveTarget(row)}
                              >
                                Approve
                              </button>
                            ) : (
                              <button
                                type="button"
                                className="intermediaries-view-btn"
                                aria-label={`View ${row.name}`}
                                onClick={() => setDetailTarget(row)}
                              >
                                View
                                <IconChevronRight />
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
                  {q.trim() ? <IconSearch /> : <IconUsers />}
                </span>
                <p className="customers-empty-title">
                  {q.trim() ? "No matches" : "No agents yet"}
                </p>
                <p className="customers-empty-copy">
                  {q.trim()
                    ? "Try another name, ID, phone, or email."
                    : "Register an agent or broker to begin."}
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
          title="Register agent"
          subtitle="Agent details and login password."
          icon={<IconUsers />}
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
              <button type="submit" form="intermediary-register-form" disabled={create.isPending}>
                {create.isPending ? "Saving…" : "Create"}
              </button>
            </>
          }
        >
          <form
            id="intermediary-register-form"
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
              required
              fieldClassName="config-field config-field--wide"
            />
            <label className="config-field">
              <span>Identification</span>
              <input
                required
                value={form.identification}
                onChange={(e) => setForm({ ...form, identification: e.target.value })}
              />
            </label>
            <label className="config-field">
              <span>Agent code</span>
              <input
                inputMode="numeric"
                pattern="[0-9]{6}"
                maxLength={6}
                autoComplete="off"
                placeholder="Blank = auto-generate"
                value={form.agent_code}
                onChange={(e) =>
                  setForm({
                    ...form,
                    agent_code: e.target.value.replace(/\D/g, "").slice(0, 6),
                  })
                }
              />
            </label>
            <label className="config-field">
              <span>KRA PIN</span>
              <input
                value={form.kra_pin}
                onChange={(e) => setForm({ ...form, kra_pin: e.target.value })}
              />
            </label>
            <label className="config-field">
              <span>Login password</span>
              <input
                required
                type="password"
                autoComplete="new-password"
                minLength={6}
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
              />
            </label>
            <p className="intermediaries-login-hint config-field--wide">
              The agent signs in with their email and this password once approved.
            </p>
            <AnimatedFormError error={error} title="Couldn’t register" />
          </form>
        </Modal>
      ) : null}

      <AgentDetailModal
        agent={detailTarget}
        open={Boolean(detailTarget)}
        canEdit={canCreate}
        onClose={() => setDetailTarget(null)}
        onUpdated={(updated) => setDetailTarget(updated)}
      />

      <Modal
        open={Boolean(approveTarget)}
        title={approveTarget ? `Approve ${approveTarget.name}?` : "Approve"}
        subtitle={
          approveTarget?.identification
            ? `ID ${approveTarget.identification}`
            : undefined
        }
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
                <IconUser />
              </span>
              <div className="customers-table-person-text">
                <span className="customers-table-name">{approveTarget.name}</span>
                <div className="customers-table-meta">
                  <span className="customers-tag customers-tag--id">
                    {approveTarget.identification}
                  </span>
                  {approveTarget.kra_pin?.trim() ? (
                    <span className="customers-tag customers-tag--kra">KRA</span>
                  ) : null}
                </div>
              </div>
            </div>
            {approveTarget.email?.trim() ? (
              <p className="intermediaries-confirm-copy">
                We&apos;ll email <strong>{approveTarget.email}</strong> their approval and
                personal QR code.
              </p>
            ) : null}
          </div>
        ) : null}
      </Modal>
    </section>
  );
}
