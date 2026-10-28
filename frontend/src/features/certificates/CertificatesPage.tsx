import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactNode, type SVGProps } from "react";
import { useAuth } from "@/app/providers/AuthProvider";
import { Modal } from "@/components/ui/Modal";
import { PdfPreview } from "@/components/ui/PdfPreview";
import { Select } from "@/components/ui/Select";
import {
  IconAlert,
  IconCertificate,
  IconChevronRight,
  IconSearch,
  IconSliders,
  IconUser,
} from "@/components/ui/icons";
import {
  certificateApi,
  type Certificate,
} from "@/services/certificates/certificateApi";

const PAGE_SIZE = 10;

const CERTIFICATE_STATUS_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: "GENERATED", label: "Ready" },
  { value: "PENDING", label: "Pending" },
  { value: "FAILED", label: "Failed" },
  { value: "REVOKED", label: "Revoked" },
];

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
    GENERATED: "Ready",
    PENDING: "Pending",
    FAILED: "Failed",
    REVOKED: "Revoked",
  };
  if (map[key]) return map[key];
  return status
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function statusTone(status: string) {
  const key = status.trim().toUpperCase();
  if (key === "GENERATED") return "active";
  if (key === "PENDING") return "pending";
  if (key === "FAILED" || key === "REVOKED") return "inactive";
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

function canOpenPdf(row: Certificate) {
  return (
    row.status === "GENERATED" &&
    (row.file_available || row.local_copy_available)
  );
}

function opensLabel(count: number) {
  if (count === 1) return "1 open";
  return `${count} opens`;
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
      <table className="customers-table certificates-table certificates-table--actions">
        <thead>
          <tr>
            <th scope="col">Certificate</th>
            <th scope="col">Customer</th>
            <th scope="col" title="Times the certificate PDF was viewed or downloaded">
              Opens
            </th>
            <th scope="col">Status</th>
            <th scope="col">Generated</th>
            <th scope="col">
              <span className="config-sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: count }, (_, index) => (
            <tr key={`cert-skeleton-${index}`} className="customers-table-row--skeleton">
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

export function CertificatesPage() {
  const { hasPermission } = useAuth();
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pdfPreviewOpen, setPdfPreviewOpen] = useState(false);
  const [pdfPreviewBlob, setPdfPreviewBlob] = useState<Blob | null>(null);
  const [previewCert, setPreviewCert] = useState<Certificate | null>(null);
  const pdfObjectUrlRef = useRef<string | null>(null);

  const canRead = hasPermission("certificate:read");

  useEffect(() => {
    setPage(1);
  }, [q, statusFilter]);

  useEffect(() => {
    return () => {
      if (pdfObjectUrlRef.current) {
        URL.revokeObjectURL(pdfObjectUrlRef.current);
        pdfObjectUrlRef.current = null;
      }
    };
  }, []);

  const list = useQuery({
    queryKey: ["certificates", statusFilter, page],
    queryFn: async () =>
      (
        await certificateApi.list({
          status: statusFilter || undefined,
          page,
          limit: PAGE_SIZE,
        })
      ).data,
    enabled: canRead,
    placeholderData: (previous) => previous,
  });

  const rawItems = list.data?.items ?? [];
  const query = q.trim().toLowerCase();
  const items = query
    ? rawItems.filter((row) => {
        const haystack = [
          row.certificate_number,
          row.external_certificate_ref,
          row.customer_name,
          row.vehicle_registration,
          row.policy_id,
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        return haystack.includes(query);
      })
    : rawItems;
  const total = list.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const rangeStart = total === 0 ? 0 : (safePage - 1) * PAGE_SIZE + 1;
  const rangeEnd = total === 0 ? 0 : Math.min(safePage * PAGE_SIZE, total);
  const canPrev = safePage > 1;
  const canNext = safePage < totalPages;
  const readyCount = items.filter((row) => row.status === "GENERATED").length;
  const pendingCount = items.filter((row) => row.status === "PENDING").length;
  const failedCount = items.filter((row) =>
    ["FAILED", "REVOKED"].includes(row.status),
  ).length;

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  function clearPreview() {
    setPdfPreviewOpen(false);
    setPdfPreviewBlob(null);
    setPreviewCert(null);
    if (pdfObjectUrlRef.current) {
      URL.revokeObjectURL(pdfObjectUrlRef.current);
      pdfObjectUrlRef.current = null;
    }
  }

  async function viewCertificate(row: Certificate) {
    setActionError(null);
    setBusyId(row.id);
    try {
      const blob = await certificateApi.downloadPdf(row.id, "inline");
      if (pdfObjectUrlRef.current) URL.revokeObjectURL(pdfObjectUrlRef.current);
      pdfObjectUrlRef.current = URL.createObjectURL(blob);
      setPreviewCert(row);
      setPdfPreviewBlob(blob);
      setPdfPreviewOpen(true);
      await list.refetch();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not open certificate.");
    } finally {
      setBusyId(null);
    }
  }

  async function downloadCertificate(row: Certificate) {
    setActionError(null);
    setBusyId(row.id);
    try {
      const blob = await certificateApi.downloadPdf(row.id, "attachment");
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${row.certificate_number || "certificate"}.pdf`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      await list.refetch();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not download certificate.");
    } finally {
      setBusyId(null);
    }
  }

  const footer = (
    <div className="customers-footer">
      <div className="customers-pager-meta customers-footer-range">
        {total === 0 ? "0 of 0" : `${rangeStart}–${rangeEnd} of ${total}`}
      </div>
      <div className="customers-pager" aria-label="Certificate pagination">
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

  if (!canRead) {
    return (
      <section className="config-page customers-page">
        <h1 className="config-title">Certificates</h1>
        <div className="customers-empty" role="alert">
          <span className="customers-empty-icon is-error" aria-hidden="true">
            <IconAlert />
          </span>
          <p className="customers-empty-title">No access</p>
          <p className="customers-empty-copy">
            You need certificate read permission to view this page.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="config-page customers-page certificates-page">
      <h1 className="config-title">Certificates</h1>

      <div className="customers-top">
        <div className="customers-stat-grid" aria-live="polite">
          <article className="customers-stat-card">
            <span className="customers-stat-label">All certificates</span>
            <strong className="customers-stat-value">{total.toLocaleString()}</strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Ready</span>
            <strong className="customers-stat-value">{readyCount.toLocaleString()}</strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Pending</span>
            <strong className="customers-stat-value">{pendingCount.toLocaleString()}</strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Failed</span>
            <strong className="customers-stat-value">{failedCount.toLocaleString()}</strong>
          </article>
        </div>

        <div className="customers-search-card certificates-toolbar">
          <label className="config-field customers-search">
            <span className="config-sr-only">Search certificates</span>
            <span className="customers-search-shell">
              <IconSearch className="customers-search-icon" />
              <input
                type="search"
                placeholder="Search certificate, customer, plate, or ref"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                autoComplete="off"
              />
            </span>
          </label>
          <div className="customers-search-shell certificates-status-shell">
            <IconSliders className="customers-search-icon" aria-hidden="true" />
            <Select
              label="Filter by status"
              fieldClassName="customers-toolbar-select"
              value={statusFilter}
              searchable={false}
              onChange={setStatusFilter}
              options={CERTIFICATE_STATUS_OPTIONS}
            />
          </div>
        </div>
      </div>

      {actionError ? (
        <p className="customers-feedback is-error" role="alert">
          {actionError}
        </p>
      ) : null}

      <div className="config-stage config-stage--fill">
        <DirectoryCard footer={footer}>
          {list.isLoading && !list.data ? <DirectorySkeleton /> : null}

          {list.isError ? (
            <div className="customers-empty" role="alert">
              <span className="customers-empty-icon is-error" aria-hidden="true">
                <IconAlert />
              </span>
              <p className="customers-empty-title">Couldn’t load certificates</p>
              <p className="customers-empty-copy">Try again in a moment.</p>
            </div>
          ) : null}

          {!(list.isLoading && !list.data) && !list.isError ? (
            items.length > 0 ? (
              <div className="customers-table-wrap">
                <table className="customers-table certificates-table certificates-table--actions">
                  <thead>
                    <tr>
                      <th scope="col">Certificate</th>
                      <th scope="col">Customer</th>
                      <th scope="col" title="Times the certificate PDF was viewed or downloaded">
                        Opens
                      </th>
                      <th scope="col">Status</th>
                      <th scope="col">Generated</th>
                      <th scope="col">
                        <span className="config-sr-only">Actions</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((row) => {
                      const tone = statusTone(row.status);
                      const openable = canOpenPdf(row);
                      const busy = busyId === row.id;
                      return (
                        <tr key={row.id}>
                          <td>
                            <div className="customers-table-person">
                              <span
                                className="customers-avatar customers-avatar--empty"
                                aria-hidden="true"
                              >
                                <IconCertificate />
                              </span>
                              <div className="customers-table-person-text">
                                <span className="customers-tag customers-tag--id certificates-number">
                                  {row.certificate_number}
                                </span>
                                <div className="customers-table-meta">
                                  {row.external_certificate_ref ? (
                                    <span className="customers-tag customers-tag--id">
                                      {row.external_certificate_ref}
                                    </span>
                                  ) : null}
                                </div>
                              </div>
                            </div>
                          </td>
                          <td>
                            <div className="customers-table-person certificates-customer">
                              <span
                                className="customers-avatar customers-avatar--empty"
                                aria-hidden="true"
                              >
                                <IconUser />
                              </span>
                              <div className="customers-table-person-text">
                                <span className="customers-table-name">
                                  {row.customer_name?.trim() || "—"}
                                </span>
                                {row.vehicle_registration ? (
                                  <div className="customers-table-meta">
                                    <span className="customers-tag customers-tag--id">
                                      {row.vehicle_registration}
                                    </span>
                                  </div>
                                ) : null}
                              </div>
                            </div>
                          </td>
                          <td>
                            <div className="certificates-opens-cell">
                              {row.access_count > 0 ? (
                                <div className="customers-table-meta certificates-opens-meta">
                                  <span
                                    className="customers-tag customers-tag--linked certificates-opens-badge"
                                    title="Times viewed or downloaded"
                                  >
                                    {opensLabel(row.access_count)}
                                  </span>
                                  <span className="customers-tag customers-tag--kra certificates-opens-badge">
                                    Last {formatShortDate(row.last_accessed_at)}
                                  </span>
                                </div>
                              ) : (
                                <span className="customers-tag certificates-opens-badge certificates-opens-badge--empty">
                                  Not opened
                                </span>
                              )}
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
                            <span className="customers-date-badge">
                              {formatShortDate(row.generated_at || row.created_at)}
                            </span>
                          </td>
                          <td className="certificates-actions">
                            {openable ? (
                              <div className="certificates-action-row">
                                <button
                                  type="button"
                                  className="intermediaries-approve-btn"
                                  disabled={busy}
                                  onClick={() => void viewCertificate(row)}
                                >
                                  {busy ? "Opening…" : "View"}
                                </button>
                                <button
                                  type="button"
                                  className="certificates-download-btn"
                                  disabled={busy}
                                  onClick={() => void downloadCertificate(row)}
                                >
                                  Download
                                </button>
                              </div>
                            ) : row.status === "FAILED" && row.failure_message ? (
                              <span
                                className="customers-tag customers-tag--kra certificates-failure"
                                title={row.failure_message}
                              >
                                {row.failure_message}
                              </span>
                            ) : (
                              <span className="customers-date">—</span>
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
                  {q.trim() || statusFilter ? <IconSearch /> : <IconCertificate />}
                </span>
                <p className="customers-empty-title">
                  {q.trim() || statusFilter ? "No matches" : "No certificates yet"}
                </p>
                <p className="customers-empty-copy">
                  {q.trim() || statusFilter
                    ? "Try another certificate, customer, plate, or status."
                    : "Certificates appear here after a policy is paid and issued."}
                </p>
              </div>
            )
          ) : null}
        </DirectoryCard>
      </div>

      <Modal
        open={pdfPreviewOpen && Boolean(pdfPreviewBlob)}
        title="Certificate PDF"
        subtitle={
          previewCert?.certificate_number ||
          previewCert?.external_certificate_ref ||
          "Preview"
        }
        icon={<IconCertificate />}
        size="fit"
        bodyClassName="modal-body--pdf"
        onClose={clearPreview}
        footer={
          <>
            <button type="button" className="secondary" onClick={clearPreview}>
              Close
            </button>
            {previewCert ? (
              <button
                type="button"
                disabled={busyId === previewCert.id}
                onClick={() => void downloadCertificate(previewCert)}
              >
                Download PDF
              </button>
            ) : null}
          </>
        }
      >
        {pdfPreviewBlob ? <PdfPreview data={pdfPreviewBlob} /> : null}
      </Modal>
    </section>
  );
}
