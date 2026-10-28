import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent, type ReactNode, type SVGProps } from "react";
import { useAuth } from "@/app/providers/AuthProvider";
import { AnimatedFormError } from "@/components/ui/AnimatedFormError";
import { Field } from "@/components/ui/Field";
import { Modal } from "@/components/ui/Modal";
import { PhoneField } from "@/components/ui/PhoneField";
import { Select } from "@/components/ui/Select";
import { TextField } from "@/components/ui/TextField";
import { DEFAULT_PHONE_COUNTRY, toE164 } from "@/components/ui/phoneCountries";
import {
  IconAlert,
  IconBell,
  IconChevronRight,
  IconMail,
  IconPhone,
  IconSearch,
  IconUser,
  IconWhatsApp,
} from "@/components/ui/icons";
import { ApiError } from "@/services/api/client";
import { mediaSrc } from "@/services/media/mediaSrc";
import {
  notificationApi,
  type Notification,
} from "@/services/notifications/notificationApi";

const PAGE_SIZE = 10;

type Channel = "SMS" | "EMAIL" | "WHATSAPP";

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

function newIdempotencyKey() {
  return `ntf-${crypto.randomUUID()}`;
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
  if (key === "SENT") return "active";
  if (key === "QUEUED" || key === "SENDING") return "pending";
  if (key === "FAILED" || key === "CANCELLED") return "inactive";
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

function channelIcon(channel: string) {
  const key = channel.trim().toUpperCase();
  if (key === "EMAIL") return <IconMail />;
  if (key === "SMS") return <IconPhone />;
  if (key === "WHATSAPP") return <IconWhatsApp />;
  return <IconBell />;
}

function recipientTitle(row: Notification) {
  const name = row.recipient_name?.trim();
  if (name) return name;
  return row.recipient;
}

function recipientSubtitle(row: Notification) {
  const name = row.recipient_name?.trim();
  if (name && row.recipient && name.toLowerCase() !== row.recipient.toLowerCase()) {
    return row.recipient;
  }
  if (row.last_error_message) return row.last_error_message;
  if (row.subject?.trim()) return row.subject.trim();
  return null;
}

function RecipientAvatar({ row }: { row: Notification }) {
  const [imgFailed, setImgFailed] = useState(false);
  const title = recipientTitle(row);
  const avatarUrl = mediaSrc(row.recipient_avatar_url) || "";
  const showPhoto = Boolean(avatarUrl) && !imgFailed;

  useEffect(() => {
    setImgFailed(false);
  }, [avatarUrl]);

  if (showPhoto) {
    return (
      <img
        src={avatarUrl}
        alt=""
        className="customers-avatar customers-avatar--photo"
        onError={() => setImgFailed(true)}
      />
    );
  }

  return (
    <span className="customers-avatar customers-avatar--empty" aria-hidden="true" title={title}>
      {row.recipient_name?.trim() ? <IconUser /> : channelIcon(row.channel)}
    </span>
  );
}

function canRetryRow(row: Notification, canSend: boolean) {
  return canSend && ["QUEUED", "FAILED"].includes(row.status);
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
      <table className="customers-table notifications-table notifications-table--actions">
        <thead>
          <tr>
            <th scope="col">Recipient</th>
            <th scope="col">Status</th>
            <th scope="col">Channel</th>
            <th scope="col">Template</th>
            <th scope="col">When</th>
            <th scope="col">
              <span className="config-sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: count }, (_, index) => (
            <tr key={`notification-skeleton-${index}`} className="customers-table-row--skeleton">
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

export function NotificationsPage() {
  const { hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [showSend, setShowSend] = useState(false);
  const [retryTarget, setRetryTarget] = useState<Notification | null>(null);
  const [channel, setChannel] = useState<Channel>("EMAIL");
  const [template, setTemplate] = useState("GENERIC_ALERT");
  const [recipient, setRecipient] = useState("");
  const [phoneCountry, setPhoneCountry] = useState(DEFAULT_PHONE_COUNTRY);
  const [message, setMessage] = useState("Hello from Star Serve");
  const [sendError, setSendError] = useState<string | null>(null);

  useEffect(() => {
    setPage(1);
  }, [q]);

  const canSend = hasPermission("notification:send");
  const canRead = hasPermission("notification:read");

  const list = useQuery({
    queryKey: ["notifications", q, page],
    queryFn: async () =>
      (await notificationApi.list({ q: q || undefined, page, limit: PAGE_SIZE })).data,
    placeholderData: (previous) => previous,
  });
  const templates = useQuery({
    queryKey: ["notification-templates"],
    queryFn: async () => (await notificationApi.templates()).data.items,
    enabled: canRead && showSend,
  });

  const items = list.data?.items ?? [];
  const total = list.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const rangeStart = total === 0 ? 0 : (safePage - 1) * PAGE_SIZE + 1;
  const rangeEnd = total === 0 ? 0 : Math.min(safePage * PAGE_SIZE, total);
  const canPrev = safePage > 1;
  const canNext = safePage < totalPages;
  const sentCount = items.filter((row) => row.status === "SENT").length;
  const failedCount = items.filter((row) => row.status === "FAILED").length;
  const queuedCount = items.filter((row) =>
    ["QUEUED", "SENDING"].includes(row.status),
  ).length;
  const showActions = items.some((row) => canRetryRow(row, canSend));
  const templateOptions = templates.data?.length ? templates.data : ["GENERIC_ALERT"];

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  useEffect(() => {
    if (!templateOptions.includes(template) && templateOptions[0]) {
      setTemplate(templateOptions[0]);
    }
  }, [template, templateOptions]);

  function resetSendForm() {
    setChannel("EMAIL");
    setTemplate(templateOptions[0] || "GENERIC_ALERT");
    setRecipient("");
    setPhoneCountry(DEFAULT_PHONE_COUNTRY);
    setMessage("Hello from Star Serve");
    setSendError(null);
  }

  function resolvedRecipient() {
    if (channel === "EMAIL") return recipient.trim();
    return toE164(phoneCountry, recipient) || "";
  }

  const send = useMutation({
    mutationFn: () =>
      notificationApi.send(
        {
          channel,
          template_code: template,
          recipient: resolvedRecipient(),
          context: {
            message,
            reference: "DEMO",
            amount: "0",
            currency: "KES",
            policy_number: "DEMO",
            receipt: "",
            vehicle_registration: "",
            cover_start_date: "",
            cover_end_date: "",
            certificate_number: "",
            external_certificate_ref: "",
            product_code: "",
            gross_premium: "",
          },
          deliver_now: true,
        },
        newIdempotencyKey(),
      ),
    onMutate: () => {
      setSendError(null);
    },
    onSuccess: async () => {
      resetSendForm();
      setShowSend(false);
      setPage(1);
      await queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
    onError: (err) => {
      setSendError(err instanceof ApiError ? err.message : "Unable to send notification");
    },
  });

  const retry = useMutation({
    mutationFn: (id: string) => notificationApi.retry(id),
    onMutate: () => {
      setSendError(null);
    },
    onSuccess: async () => {
      setRetryTarget(null);
      await queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });

  function onSendSubmit(e: FormEvent) {
    e.preventDefault();
    setSendError(null);
    send.mutate();
  }

  const footer = (
    <div className="customers-footer">
      <div className="customers-pager-meta customers-footer-range">
        {total === 0 ? "0 of 0" : `${rangeStart}–${rangeEnd} of ${total}`}
      </div>
      <div className="customers-pager" aria-label="Notification pagination">
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
    <section className="config-page customers-page notifications-page">
      <h1 className="config-title">Notifications</h1>

      <div className="customers-top">
        <div className="customers-stat-grid" aria-live="polite">
          <article className="customers-stat-card">
            <span className="customers-stat-label">All messages</span>
            <strong className="customers-stat-value">{total.toLocaleString()}</strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Sent</span>
            <strong className="customers-stat-value">{sentCount.toLocaleString()}</strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Queued</span>
            <strong className="customers-stat-value">{queuedCount.toLocaleString()}</strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Failed</span>
            <strong className="customers-stat-value">{failedCount.toLocaleString()}</strong>
          </article>
        </div>

        <div className="customers-search-card">
          <label className="config-field customers-search">
            <span className="config-sr-only">Search notifications</span>
            <span className="customers-search-shell">
              <IconSearch className="customers-search-icon" />
              <input
                type="search"
                placeholder="Search recipient or template"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                autoComplete="off"
              />
            </span>
          </label>
          {canSend ? (
            <button
              type="button"
              className="config-btn customers-toolbar-add"
              onClick={() => {
                resetSendForm();
                setShowSend(true);
              }}
            >
              + Send
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
              <p className="customers-empty-title">Couldn’t load notifications</p>
              <p className="customers-empty-copy">Try again in a moment.</p>
            </div>
          ) : null}

          {!(list.isLoading && !list.data) && !list.isError ? (
            items.length > 0 ? (
              <div className="customers-table-wrap">
                <table
                  className={`customers-table notifications-table${
                    showActions ? " notifications-table--actions" : ""
                  }`}
                >
                  <thead>
                    <tr>
                      <th scope="col">Recipient</th>
                      <th scope="col">Status</th>
                      <th scope="col">Channel</th>
                      <th scope="col">Template</th>
                      <th scope="col">When</th>
                      {showActions ? (
                        <th scope="col">
                          <span className="config-sr-only">Actions</span>
                        </th>
                      ) : null}
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((row) => {
                      const retryable = canRetryRow(row, canSend);
                      return (
                        <tr key={row.id}>
                          <td>
                            <div className="customers-table-person">
                              <RecipientAvatar row={row} />
                              <div className="customers-table-person-text">
                                <span className="customers-table-name">{recipientTitle(row)}</span>
                                <div className="customers-table-meta">
                                  {recipientSubtitle(row) ? (
                                    <span
                                      className={`customers-tag${
                                        row.last_error_message && !row.recipient_name?.trim()
                                          ? " customers-tag--kra"
                                          : " customers-tag--id"
                                      }`}
                                      title={recipientSubtitle(row) ?? undefined}
                                    >
                                      {recipientSubtitle(row)}
                                    </span>
                                  ) : (
                                    <span className="customers-tag customers-tag--linked">
                                      {ucwords(row.channel)}
                                    </span>
                                  )}
                                </div>
                              </div>
                            </div>
                          </td>
                          <td>
                            <span
                              className={`customers-status-badge customers-status-badge--${statusTone(row.status)}`}
                            >
                              <span className="customers-status-dot__mark" aria-hidden="true" />
                              {ucwords(row.status)}
                            </span>
                          </td>
                          <td>
                            <span className="customers-tag notifications-channel-badge">
                              {ucwords(row.channel)}
                            </span>
                          </td>
                          <td>
                            <span className="customers-tag customers-tag--kra">
                              {ucwords(row.template_code)}
                            </span>
                          </td>
                          <td>
                            <span className="customers-date-badge">
                              {formatShortDate(row.sent_at || row.updated_at || row.created_at)}
                            </span>
                          </td>
                          {showActions ? (
                            <td className="notifications-actions">
                              {retryable ? (
                                <button
                                  type="button"
                                  className="intermediaries-approve-btn"
                                  disabled={retry.isPending}
                                  onClick={() => setRetryTarget(row)}
                                >
                                  Retry
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
                  {q.trim() ? <IconSearch /> : <IconBell />}
                </span>
                <p className="customers-empty-title">
                  {q.trim() ? "No matches" : "No notifications yet"}
                </p>
                <p className="customers-empty-copy">
                  {q.trim()
                    ? "Try another recipient or template."
                    : "Send a message to begin the delivery log."}
                </p>
              </div>
            )
          ) : null}
        </DirectoryCard>
      </div>

      {canSend ? (
        <Modal
          open={showSend}
          size="lg"
          title="Send notification"
          subtitle="Delivery status comes from the provider job."
          icon={<IconBell />}
          onClose={() => {
            if (!send.isPending) {
              setShowSend(false);
              setSendError(null);
            }
          }}
          bodyClassName="intermediaries-modal-body"
          footer={
            <>
              <button
                type="button"
                className="secondary"
                disabled={send.isPending}
                onClick={() => {
                  setShowSend(false);
                  setSendError(null);
                }}
              >
                Cancel
              </button>
              <button
                type="submit"
                form="notification-send-form"
                disabled={send.isPending || !resolvedRecipient()}
              >
                {send.isPending ? "Sending…" : "Send"}
              </button>
            </>
          }
        >
          <form
            id="notification-send-form"
            className="form-grid modal-form-grid intermediaries-modal-form notifications-modal-form"
            onSubmit={onSendSubmit}
          >
            <Select
              label="Channel"
              value={channel}
              searchable={false}
              onChange={(next) => {
                setChannel(next as Channel);
                setRecipient("");
              }}
              options={[
                { value: "EMAIL", label: "Email" },
                { value: "SMS", label: "SMS" },
                { value: "WHATSAPP", label: "WhatsApp" },
              ]}
            />
            <Select
              label="Template"
              value={template}
              searchable={templateOptions.length >= 8}
              onChange={setTemplate}
              options={templateOptions.map((code) => ({
                value: code,
                label: ucwords(code),
              }))}
            />
            {channel === "EMAIL" ? (
              <TextField
                label="Recipient"
                type="email"
                required
                autoFocus
                placeholder="user@example.com"
                value={recipient}
                onChange={(e) => setRecipient(e.target.value)}
                fieldClassName="notifications-field-span"
              />
            ) : (
              <PhoneField
                label={channel === "SMS" ? "SMS phone" : "WhatsApp phone"}
                value={recipient}
                onChange={setRecipient}
                country={phoneCountry}
                onCountryChange={setPhoneCountry}
                required
                fieldClassName="notifications-field-span"
              />
            )}
            <Field
              label="Message"
              htmlFor="notification-message"
              className="notifications-field-span"
            >
              <textarea
                id="notification-message"
                className="ui-input"
                rows={3}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
              />
            </Field>
            <AnimatedFormError
              error={sendError}
              title="Couldn’t send"
              className="notifications-field-span"
            />
          </form>
        </Modal>
      ) : null}

      <Modal
        open={Boolean(retryTarget)}
        title={retryTarget ? `Retry ${ucwords(retryTarget.channel)}?` : "Retry"}
        subtitle={retryTarget?.recipient}
        icon={<IconBell />}
        onClose={() => {
          if (!retry.isPending) setRetryTarget(null);
        }}
        bodyClassName="intermediaries-modal-body"
        footer={
          <>
            <button
              type="button"
              className="secondary"
              disabled={retry.isPending}
              onClick={() => setRetryTarget(null)}
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={!retryTarget || retry.isPending}
              onClick={() => {
                if (retryTarget) retry.mutate(retryTarget.id);
              }}
            >
              {retry.isPending ? "Retrying…" : "Retry"}
            </button>
          </>
        }
      >
        {retryTarget ? (
          <div className="intermediaries-confirm">
            <div className="intermediaries-confirm-person">
              <RecipientAvatar row={retryTarget} />
              <div className="customers-table-person-text">
                <span className="customers-table-name">{recipientTitle(retryTarget)}</span>
                <div className="customers-table-meta">
                  {recipientSubtitle(retryTarget) ? (
                    <span className="customers-tag customers-tag--id">
                      {recipientSubtitle(retryTarget)}
                    </span>
                  ) : null}
                  <span className="customers-tag customers-tag--linked">
                    {ucwords(retryTarget.template_code)}
                  </span>
                  <span className="customers-tag customers-tag--kra">
                    {ucwords(retryTarget.status)}
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
