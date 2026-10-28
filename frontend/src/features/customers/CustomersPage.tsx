import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent, type ReactNode, type SVGProps } from "react";
import { useSearchParams } from "react-router-dom";
import { useAuth } from "@/app/providers/AuthProvider";
import { AnimatedFormError } from "@/components/ui/AnimatedFormError";
import { PhoneField } from "@/components/ui/PhoneField";
import { DEFAULT_PHONE_COUNTRY, toE164 } from "@/components/ui/phoneCountries";
import { Modal } from "@/components/ui/Modal";
import { buildBrandedAgentQrDataUrl } from "@/features/intermediaries/brandedAgentQr";
import { buildWelcomeReferralQrUrl } from "@/services/insurance/guestAgent";
import {
  referralApi,
  type ReferralKitChannel,
} from "@/services/commissions/referralApi";
import {
  IconAlert,
  IconChevronRight,
  IconDownload,
  IconMail,
  IconPhone,
  IconSearch,
  IconUser,
  IconUsers,
  IconWhatsApp,
} from "@/components/ui/icons";
import { ApiError } from "@/services/api/client";
import { customerApi, type Customer } from "@/services/customers/customerApi";
import { mediaSrc } from "@/services/media/mediaSrc";

const PAGE_SIZE = 10;

const KIT_CHANNEL_META: Record<
  ReferralKitChannel,
  { label: string; icon: typeof IconMail }
> = {
  EMAIL: { label: "Email", icon: IconMail },
  SMS: { label: "SMS", icon: IconPhone },
  WHATSAPP: { label: "WhatsApp", icon: IconWhatsApp },
};

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
  if (key === "ACTIVE") return "Active";
  if (key === "INACTIVE") return "Inactive";
  if (key === "SUSPENDED") return "Suspended";
  return status
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function statusTone(status: string) {
  const key = status.trim().toUpperCase();
  if (key === "ACTIVE") return "active";
  if (key === "INACTIVE") return "inactive";
  if (key === "SUSPENDED") return "suspended";
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

function CustomerContactIcons({
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

function CustomerAvatar({
  name,
  avatarUrl,
}: {
  name: string;
  avatarUrl?: string | null;
}) {
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

function CustomerCard({
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

function ReferredBy({ customer }: { customer: Customer }) {
  if (customer.referred_by_intermediary_id || customer.referred_by_agent_code) {
    return (
      <div className="customers-referred">
        <span className="customers-referred-name">
          {customer.referred_by_agent_name || "Agent"}
        </span>
        {customer.referred_by_agent_code ? (
          <span className="customers-tag customers-tag--id">
            Agent {customer.referred_by_agent_code}
          </span>
        ) : null}
      </div>
    );
  }
  if (customer.referred_by_referral_code) {
    return (
      <div className="customers-referred">
        <span className="customers-referred-name">Customer</span>
        <span className="customers-tag customers-tag--id">{customer.referred_by_referral_code}</span>
      </div>
    );
  }
  return <span className="customers-referred-none">Direct</span>;
}

function CustomerReferralQrModal({
  customer,
  onClose,
}: {
  customer: Customer | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const { hasPermission } = useAuth();
  const canResend = hasPermission("customer:update") || hasPermission("customer:create");
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null);
  const [qrError, setQrError] = useState<string | null>(null);
  const [resendNote, setResendNote] = useState<string | null>(null);
  const [resendError, setResendError] = useState<string | null>(null);
  const [resendingChannel, setResendingChannel] = useState<ReferralKitChannel | null>(null);
  const name = customer ? `${customer.first_name} ${customer.last_name}`.trim() : "";

  // Also issues a code for customers created before referrals existed.
  const referral = useQuery({
    queryKey: ["customer-referral", customer?.id],
    queryFn: async () => (await referralApi.forCustomer(customer!.id)).data,
    enabled: Boolean(customer?.id),
    retry: (count, err) => !(err instanceof ApiError && err.status === 404) && count < 2,
  });
  const code = referral.data?.referral_code ?? customer?.referral_code ?? null;
  const shareLink = code ? buildWelcomeReferralQrUrl(code) : null;
  const [copied, setCopied] = useState(false);
  const referralUnavailable =
    referral.isError && referral.error instanceof ApiError && referral.error.status === 404;
  const referralErrorText = referralUnavailable
    ? "Referral codes are available after the next deploy."
    : referral.error instanceof ApiError
      ? referral.error.message
      : "Couldn’t load the referral code.";

  const kitChannels = useQuery({
    queryKey: ["customer-referral-kit-channels", customer?.id],
    queryFn: async () => (await referralApi.kitChannels(customer!.id)).data.channels,
    enabled: Boolean(customer?.id) && canResend,
  });

  const resendKit = useMutation({
    mutationFn: async (channel: ReferralKitChannel) => {
      if (!customer) throw new Error("No customer selected");
      return referralApi.resendKit(customer.id, channel);
    },
    onMutate: (channel) => {
      setResendingChannel(channel);
      setResendNote(null);
      setResendError(null);
    },
    onSuccess: async (_res, channel) => {
      setResendNote(`Referral kit queued via ${KIT_CHANNEL_META[channel].label}.`);
      await queryClient.invalidateQueries({
        queryKey: ["customer-referral-kit-channels", customer?.id],
      });
    },
    onError: (err) => {
      setResendError(
        err instanceof ApiError ? err.message : "Couldn’t resend the referral kit",
      );
    },
    onSettled: () => setResendingChannel(null),
  });

  useEffect(() => {
    setCopied(false);
    setResendNote(null);
    setResendError(null);
    setResendingChannel(null);
  }, [customer?.id]);

  async function copyLink() {
    if (!shareLink) return;
    try {
      await navigator.clipboard.writeText(shareLink);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  }

  useEffect(() => {
    if (referral.data?.referral_code && !customer?.referral_code) {
      void queryClient.invalidateQueries({ queryKey: ["customers"] });
    }
  }, [referral.data?.referral_code, customer?.referral_code, queryClient]);

  useEffect(() => {
    if (!customer || !code) {
      setQrDataUrl(null);
      setQrError(null);
      return;
    }
    let cancelled = false;
    setQrDataUrl(null);
    setQrError(null);
    void buildBrandedAgentQrDataUrl({
      payloadUrl: buildWelcomeReferralQrUrl(code),
      agentName: name || customer.id_number,
      agentCode: code,
      caption: `Referral ${code}`,
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
  }, [customer, code, name]);

  function downloadQr() {
    if (!qrDataUrl || !code) return;
    const safeName =
      name
        .replace(/[^\w\s-]+/g, "")
        .replace(/\s+/g, "-")
        .replace(/-+/g, "-")
        .replace(/^-|-$/g, "")
        .toLowerCase() || "customer";
    const link = document.createElement("a");
    link.href = qrDataUrl;
    link.download = `${safeName}-${code}-referral-qr.png`;
    link.click();
  }

  const balance = Number(referral.data?.balance ?? 0);

  return (
    <Modal
      open={Boolean(customer)}
      size="xl"
      title={name || "Customer"}
      subtitle={
        customer
          ? [customer.id_number, customer.phone].filter(Boolean).join(" · ") || "Customer referral"
          : undefined
      }
      icon={<IconUser />}
      onClose={onClose}
      panelClassName="customers-referral-modal"
      bodyClassName="customers-referral-modal-body"
      footer={
        <>
          <button type="button" className="secondary" onClick={onClose}>
            Close
          </button>
          <button type="button" disabled={!qrDataUrl} onClick={downloadQr}>
            <IconDownload />
            Download QR
          </button>
        </>
      }
    >
      {customer ? (
        <div className="intermediaries-detail">
          {referral.isError && !code ? (
            <p className="customers-referral-notice" role="status">
              {referralErrorText}
            </p>
          ) : null}

          <dl className="intermediaries-detail-facts">
            <div>
              <dt>Referral code</dt>
              <dd className="mono">{code || (referral.isLoading ? "…" : "—")}</dd>
            </div>
            <div>
              <dt>Referral credit</dt>
              <dd className="mono">
                {referral.isLoading
                  ? "…"
                  : referral.data
                    ? `KES ${balance.toLocaleString("en-KE", {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}`
                    : "—"}
              </dd>
            </div>
            <div>
              <dt>Referred by</dt>
              <dd>
                <ReferredBy customer={customer} />
              </dd>
            </div>
            <div className="customers-referral-link-row">
              <dt>Share link</dt>
              <dd>
                {shareLink ? (
                  <span className="customers-referral-link-wrap">
                    <span className="customers-referral-link">{shareLink}</span>
                    <button type="button" className="secondary customers-referral-copy" onClick={copyLink}>
                      {copied ? "Copied" : "Copy"}
                    </button>
                  </span>
                ) : (
                  "—"
                )}
              </dd>
            </div>
          </dl>

          <div className="intermediaries-detail-qr">
            <div className="intermediaries-detail-qr-copy">
              <p className="customers-stat-label">Referral QR</p>
              <strong>How to share</strong>
              <ol className="customers-referral-steps">
                <li>
                  Download the QR or copy the share link above.
                </li>
                <li>
                  Send it to a friend (WhatsApp, SMS, print, or show the code).
                </li>
                <li>
                  They scan or open it, get a quote, and pay for cover.
                </li>
                <li>
                  {name.split(" ")[0] || "The customer"} earns credit off their next cover.
                </li>
              </ol>
              {canResend ? (
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
                            disabled={resendKit.isPending || !code}
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
                      No enabled notification channels are available for this customer.
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
                <img src={qrDataUrl} alt={`Referral QR code ${code}`} />
              ) : qrError || (referral.isError && !code) ? (
                <p className="intermediaries-detail-qr-fallback">
                  {qrError || (referralUnavailable ? "QR available after deploy" : referralErrorText)}
                </p>
              ) : (
                <span className="skeleton-block intermediaries-detail-qr-skel" aria-hidden="true" />
              )}
            </div>
          </div>
        </div>
      ) : null}
    </Modal>
  );
}

function DirectorySkeleton({ count = 5 }: { count?: number }) {
  return (
    <div className="customers-table-wrap" aria-busy="true">
      <table className="customers-table">
        <thead>
          <tr>
            <th scope="col">Customer</th>
            <th scope="col">Status</th>
            <th scope="col">Contact</th>
            <th scope="col">Referral code</th>
            <th scope="col">Referred by</th>
            <th scope="col">Policies</th>
            <th scope="col">Quotes</th>
            <th scope="col">Updated</th>
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: count }, (_, index) => (
            <tr key={`customer-skeleton-${index}`} className="customers-table-row--skeleton">
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

export function CustomersPage() {
  const { hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const [q, setQ] = useState(searchParams.get("q") ?? "");
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [phoneCountry, setPhoneCountry] = useState(DEFAULT_PHONE_COUNTRY);
  const [form, setForm] = useState({
    first_name: "",
    last_name: "",
    id_number: "",
    phone: "",
    email: "",
    kra_pin: "",
  });

  useEffect(() => {
    setQ(searchParams.get("q") ?? "");
  }, [searchParams]);

  useEffect(() => {
    setPage(1);
  }, [q]);

  const list = useQuery({
    queryKey: ["customers", q, page],
    queryFn: async () =>
      (await customerApi.list({ q: q || undefined, page, limit: PAGE_SIZE })).data,
    placeholderData: (previous) => previous,
  });

  const canCreate = hasPermission("customer:create");
  const [qrCustomer, setQrCustomer] = useState<Customer | null>(null);
  const items = list.data?.items ?? [];
  const total = list.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const rangeStart = total === 0 ? 0 : (safePage - 1) * PAGE_SIZE + 1;
  const rangeEnd = total === 0 ? 0 : Math.min(safePage * PAGE_SIZE, total);
  const canPrev = safePage > 1;
  const canNext = safePage < totalPages;
  const activeCount = items.filter((c) => c.status === "ACTIVE").length;
  const policiesTotal = items.reduce((sum, c) => sum + (c.policies_count ?? 0), 0);
  const quotesTotal = items.reduce((sum, c) => sum + (c.proposals_count ?? 0), 0);

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  function resetForm() {
    setForm({
      first_name: "",
      last_name: "",
      id_number: "",
      phone: "",
      email: "",
      kra_pin: "",
    });
    setPhoneCountry(DEFAULT_PHONE_COUNTRY);
    setError(null);
  }

  const create = useMutation({
    mutationFn: async () => {
      const phone = toE164(phoneCountry, form.phone);
      if (!phone) throw new Error("Enter a valid phone number");
      return customerApi.create({
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        id_number: form.id_number.trim(),
        phone,
        email: form.email.trim() || undefined,
        kra_pin: form.kra_pin.trim() || undefined,
      });
    },
    onMutate: () => {
      setError(null);
    },
    onSuccess: async () => {
      resetForm();
      setShowAdd(false);
      setPage(1);
      await queryClient.invalidateQueries({ queryKey: ["customers"] });
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "Unable to create customer");
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
      <div className="customers-pager" aria-label="Customer pagination">
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
    <section className="config-page customers-page customers-directory-page">
      <h1 className="config-title">Customers</h1>

      <div className="customers-top">
        <div className="customers-stat-grid" aria-live="polite">
          <article className="customers-stat-card">
            <span className="customers-stat-label">All customers</span>
            <strong className="customers-stat-value">{total.toLocaleString()}</strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Active</span>
            <strong className="customers-stat-value">{activeCount.toLocaleString()}</strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Policies</span>
            <strong className="customers-stat-value">{policiesTotal.toLocaleString()}</strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Quotes</span>
            <strong className="customers-stat-value">{quotesTotal.toLocaleString()}</strong>
          </article>
        </div>

        <div className="customers-search-card">
          <label className="config-field customers-search">
            <span className="config-sr-only">Search customers</span>
            <span className="customers-search-shell">
              <IconSearch className="customers-search-icon" />
              <input
                type="search"
                placeholder="Search name, ID, phone, email"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                autoComplete="off"
              />
            </span>
          </label>
          {canCreate && !showAdd ? (
            <button
              type="button"
              className="config-btn customers-toolbar-add"
              onClick={() => setShowAdd(true)}
            >
              + Add customer
            </button>
          ) : null}
        </div>
      </div>

      <div className="config-stage config-stage--fill">
        <CustomerCard footer={footer}>
          {list.isLoading && !list.data ? <DirectorySkeleton /> : null}

          {list.isError ? (
            <div className="customers-empty" role="alert">
              <span className="customers-empty-icon is-error" aria-hidden="true">
                <IconAlert />
              </span>
              <p className="customers-empty-title">Couldn’t load customers</p>
              <p className="customers-empty-copy">Try again in a moment.</p>
            </div>
          ) : null}

          {!(list.isLoading && !list.data) && !list.isError ? (
            items.length > 0 ? (
              <div className="customers-table-wrap">
                <table className="customers-table">
                  <thead>
                    <tr>
                      <th scope="col">Customer</th>
                      <th scope="col">Status</th>
                      <th scope="col">Contact</th>
                      <th scope="col">Referral code</th>
                      <th scope="col">Referred by</th>
                      <th scope="col">Policies</th>
                      <th scope="col">Quotes</th>
                      <th scope="col">Updated</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((c) => {
                      const name = `${c.first_name} ${c.last_name}`.trim();
                      const kra = c.kra_pin?.trim() || "";
                      const linked = Boolean(c.external_client_ref?.trim());
                      const tone = statusTone(c.status);
                      const policies = c.policies_count ?? 0;
                      const quotes = c.proposals_count ?? 0;
                      return (
                        <tr key={c.id}>
                          <td>
                            <div className="customers-table-person">
                              <CustomerAvatar name={name} avatarUrl={c.avatar_url} />
                              <div className="customers-table-person-text">
                                <span className="customers-table-name">{name}</span>
                                <div className="customers-table-meta">
                                  <span className="customers-tag customers-tag--id">{c.id_number}</span>
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
                              {statusLabel(c.status)}
                            </span>
                          </td>
                          <td>
                            <CustomerContactIcons phone={c.phone} email={c.email} />
                          </td>
                          <td>
                            <button
                              type="button"
                              className="customers-referral-btn"
                              onClick={() => setQrCustomer(c)}
                              title="Show and download referral QR"
                            >
                              <span className="mono">{c.referral_code || "Get code"}</span>
                              <IconDownload aria-hidden="true" />
                            </button>
                          </td>
                          <td>
                            <ReferredBy customer={c} />
                          </td>
                          <td>
                            <span
                              className={`customers-metric-badge${policies > 0 ? " is-up" : ""}`}
                            >
                              {policies}
                            </span>
                          </td>
                          <td>
                            <span
                              className={`customers-metric-badge${quotes > 0 ? " is-up" : ""}`}
                            >
                              {quotes}
                            </span>
                          </td>
                          <td>
                            <span className="customers-date-badge">
                              {formatShortDate(c.updated_at || c.created_at)}
                            </span>
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
                  {q.trim() ? "No matches found" : "No customers yet"}
                </p>
                <p className="customers-empty-copy">
                  {q.trim()
                    ? "No customers match that search. Try a different name, ID, phone, or email."
                    : "Add your first client to get started."}
                </p>
              </div>
            )
          ) : null}

          {canCreate && showAdd ? (
            <form className="config-form" onSubmit={onSubmit}>
              <label className="config-field">
                <span>First name</span>
                <input
                  required
                  value={form.first_name}
                  onChange={(e) => setForm({ ...form, first_name: e.target.value })}
                />
              </label>
              <label className="config-field">
                <span>Last name</span>
                <input
                  required
                  value={form.last_name}
                  onChange={(e) => setForm({ ...form, last_name: e.target.value })}
                />
              </label>
              <label className="config-field">
                <span>ID number</span>
                <input
                  required
                  value={form.id_number}
                  onChange={(e) => setForm({ ...form, id_number: e.target.value })}
                />
              </label>
              <PhoneField
                label="Phone"
                value={form.phone}
                onChange={(phone) => setForm({ ...form, phone })}
                country={phoneCountry}
                onCountryChange={setPhoneCountry}
                required
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
                <span>KRA PIN</span>
                <input
                  value={form.kra_pin}
                  onChange={(e) => setForm({ ...form, kra_pin: e.target.value })}
                />
              </label>
              <AnimatedFormError error={error} title="Couldn’t create" />
              <div className="config-form-actions">
                <button
                  type="button"
                  className="config-btn config-btn--ghost config-btn--flex"
                  onClick={() => {
                    setShowAdd(false);
                    resetForm();
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="config-btn config-btn--flex"
                  disabled={create.isPending}
                >
                  {create.isPending ? "Saving…" : "Create"}
                </button>
              </div>
            </form>
          ) : null}
        </CustomerCard>
      </div>
      <CustomerReferralQrModal customer={qrCustomer} onClose={() => setQrCustomer(null)} />
    </section>
  );
}
