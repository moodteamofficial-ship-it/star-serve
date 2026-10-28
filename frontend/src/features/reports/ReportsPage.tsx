import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type FormEvent, type ReactNode, type SVGProps } from "react";
import { useAuth } from "@/app/providers/AuthProvider";
import { AnimatedFormError } from "@/components/ui/AnimatedFormError";
import { Modal } from "@/components/ui/Modal";
import { IconAlert, IconChart, IconChevronRight, IconFileText, IconSearch } from "@/components/ui/icons";
import { ApiError } from "@/services/api/client";
import { reportApi, type ReportRun } from "@/services/reports/reportApi";

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
  if (key === "COMPLETED") return "active";
  if (key === "QUEUED" || key === "RUNNING") return "pending";
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

function formatShortDateTime(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function summaryPreview(summary: Record<string, unknown> | null | undefined) {
  if (!summary || Object.keys(summary).length === 0) return "—";
  const parts: string[] = [];
  for (const [key, value] of Object.entries(summary)) {
    if (value == null) continue;
    if (typeof value === "object") {
      const nested = value as Record<string, unknown>;
      const nestedCount = Object.keys(nested).length;
      parts.push(`${ucwords(key)} (${nestedCount})`);
    } else {
      parts.push(`${ucwords(key)} ${String(value)}`);
    }
    if (parts.length >= 3) break;
  }
  return parts.length ? parts.join(" · ") : "—";
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
      <table className="customers-table reports-table">
        <thead>
          <tr>
            <th scope="col">Report</th>
            <th scope="col">Status</th>
            <th scope="col">Summary</th>
            <th scope="col">When</th>
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: count }, (_, index) => (
            <tr key={`report-skeleton-${index}`} className="customers-table-row--skeleton">
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
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SummaryDetails({ summary }: { summary: Record<string, unknown> }) {
  const entries = Object.entries(summary);
  if (!entries.length) {
    return <p className="config-muted">No summary data.</p>;
  }

  return (
    <div className="reports-summary">
      {entries.map(([key, value]) => {
        if (value != null && typeof value === "object" && !Array.isArray(value)) {
          const nested = Object.entries(value as Record<string, unknown>);
          return (
            <div key={key} className="reports-summary-block">
              <span className="reports-summary-label">{ucwords(key)}</span>
              {nested.length ? (
                <div className="reports-summary-tags">
                  {nested.map(([nestedKey, nestedValue]) => (
                    <span key={`${key}-${nestedKey}`} className="customers-tag customers-tag--kra">
                      {ucwords(nestedKey)} · {String(nestedValue)}
                    </span>
                  ))}
                </div>
              ) : (
                <span className="customers-date">—</span>
              )}
            </div>
          );
        }

        return (
          <div key={key} className="reports-summary-block">
            <span className="reports-summary-label">{ucwords(key)}</span>
            <strong className="reports-summary-value">{String(value ?? "—")}</strong>
          </div>
        );
      })}
    </div>
  );
}

export function ReportsPage() {
  const { hasPermission } = useAuth();
  const canRunReports = hasPermission("reports:run");
  const queryClient = useQueryClient();
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [showGenerate, setShowGenerate] = useState(false);
  const [reportType, setReportType] = useState("POLICIES_SUMMARY");
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [viewTarget, setViewTarget] = useState<ReportRun | null>(null);

  useEffect(() => {
    setPage(1);
  }, [q]);

  const types = useQuery({
    queryKey: ["report-types"],
    queryFn: async () => (await reportApi.types()).data.items,
  });
  const list = useQuery({
    queryKey: ["reports", page],
    queryFn: async () => (await reportApi.list({ page, limit: PAGE_SIZE })).data,
    placeholderData: (previous) => previous,
  });

  const typeOptions = types.data?.length ? types.data : ["POLICIES_SUMMARY"];

  useEffect(() => {
    if (!typeOptions.includes(reportType) && typeOptions[0]) {
      setReportType(typeOptions[0]);
    }
  }, [reportType, typeOptions]);

  const allItems = list.data?.items ?? [];
  const filteredItems = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return allItems;
    return allItems.filter((row) => {
      const type = row.report_type.toLowerCase();
      const status = row.status.toLowerCase();
      const summary = JSON.stringify(row.result_summary ?? {}).toLowerCase();
      return type.includes(needle) || status.includes(needle) || summary.includes(needle);
    });
  }, [allItems, q]);

  const items = filteredItems;
  const total = q.trim() ? filteredItems.length : (list.data?.total ?? 0);
  const totalPages = Math.max(1, Math.ceil((list.data?.total ?? 0) / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const rangeStart = total === 0 ? 0 : q.trim() ? 1 : (safePage - 1) * PAGE_SIZE + 1;
  const rangeEnd = total === 0 ? 0 : q.trim() ? items.length : Math.min(safePage * PAGE_SIZE, total);
  const canPrev = !q.trim() && safePage > 1;
  const canNext = !q.trim() && safePage < totalPages;
  const completedCount = allItems.filter((row) => row.status === "COMPLETED").length;
  const failedCount = allItems.filter((row) => row.status === "FAILED").length;
  const runningCount = allItems.filter((row) =>
    ["QUEUED", "RUNNING"].includes(row.status),
  ).length;

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  const run = useMutation({
    mutationFn: async () => (await reportApi.run(reportType)).data,
    onMutate: () => {
      setGenerateError(null);
    },
    onSuccess: async (data) => {
      setGenerateError(null);
      setShowGenerate(false);
      setPage(1);
      await queryClient.invalidateQueries({ queryKey: ["reports"] });
      setViewTarget(data);
    },
    onError: (err) => {
      setGenerateError(err instanceof ApiError ? err.message : "Unable to generate report");
    },
  });

  function onGenerate(e: FormEvent) {
    e.preventDefault();
    setGenerateError(null);
    run.mutate();
  }

  const footer = (
    <div className="customers-footer">
      <div className="customers-pager-meta customers-footer-range">
        {total === 0 ? "0 of 0" : `${rangeStart}–${rangeEnd} of ${total}`}
      </div>
      <div className="customers-pager" aria-label="Report pagination">
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
    <section className="config-page customers-page reports-page">
      <h1 className="config-title">Reports</h1>

      <div className="customers-top">
        <div className="customers-stat-grid" aria-live="polite">
          <article className="customers-stat-card">
            <span className="customers-stat-label">All runs</span>
            <strong className="customers-stat-value">
              {(list.data?.total ?? 0).toLocaleString()}
            </strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Completed</span>
            <strong className="customers-stat-value">{completedCount.toLocaleString()}</strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Running</span>
            <strong className="customers-stat-value">{runningCount.toLocaleString()}</strong>
          </article>
          <article className="customers-stat-card">
            <span className="customers-stat-label">Failed</span>
            <strong className="customers-stat-value">{failedCount.toLocaleString()}</strong>
          </article>
        </div>

        <div className="customers-search-card">
          <label className="config-field customers-search">
            <span className="config-sr-only">Search reports</span>
            <span className="customers-search-shell">
              <IconSearch className="customers-search-icon" />
              <input
                type="search"
                placeholder="Search type, status, or summary"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                autoComplete="off"
              />
            </span>
          </label>
          {canRunReports ? (
            <button
              type="button"
              className="config-btn customers-toolbar-add"
              onClick={() => {
                setGenerateError(null);
                setShowGenerate(true);
              }}
            >
              + Generate
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
              <p className="customers-empty-title">Couldn’t load reports</p>
              <p className="customers-empty-copy">Try again in a moment.</p>
            </div>
          ) : null}

          {!(list.isLoading && !list.data) && !list.isError ? (
            items.length > 0 ? (
              <div className="customers-table-wrap">
                <table className="customers-table reports-table">
                  <thead>
                    <tr>
                      <th scope="col">Report</th>
                      <th scope="col">Status</th>
                      <th scope="col">Summary</th>
                      <th scope="col">When</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((row) => (
                      <tr key={row.id}>
                        <td>
                          <button
                            type="button"
                            className="reports-row-btn"
                            onClick={() => setViewTarget(row)}
                          >
                            <span className="customers-table-person">
                              <span
                                className="customers-avatar customers-avatar--empty"
                                aria-hidden="true"
                              >
                                <IconChart />
                              </span>
                              <span className="customers-table-person-text">
                                <span className="customers-table-name">
                                  {ucwords(row.report_type)}
                                </span>
                              </span>
                            </span>
                          </button>
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
                          <span className="reports-summary-preview">
                            {row.status === "FAILED" && row.failure_message
                              ? row.failure_message
                              : summaryPreview(row.result_summary)}
                          </span>
                        </td>
                        <td>
                          <span className="customers-date">
                            {formatShortDate(row.completed_at || row.created_at)}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="customers-empty" role="status">
                <span className="customers-empty-icon" aria-hidden="true">
                  {q.trim() ? <IconSearch /> : <IconFileText />}
                </span>
                <p className="customers-empty-title">
                  {q.trim() ? "No matches" : "No reports yet"}
                </p>
                <p className="customers-empty-copy">
                  {q.trim()
                    ? "Try another type, status, or keyword."
                    : "Generate a tenant-scoped summary to begin."}
                </p>
              </div>
            )
          ) : null}
        </DirectoryCard>
      </div>

      <Modal
        open={showGenerate}
        title="Generate report"
        subtitle="Tenant-scoped aggregates only."
        icon={<IconChart />}
        onClose={() => {
          if (!run.isPending) {
            setShowGenerate(false);
            setGenerateError(null);
          }
        }}
        bodyClassName="intermediaries-modal-body"
        footer={
          <>
            <button
              type="button"
              className="secondary"
              disabled={run.isPending}
              onClick={() => {
                setShowGenerate(false);
                setGenerateError(null);
              }}
            >
              Cancel
            </button>
            <button type="submit" form="report-generate-form" disabled={run.isPending}>
              {run.isPending ? "Generating…" : "Generate"}
            </button>
          </>
        }
      >
        <form
          id="report-generate-form"
          className="form-grid modal-form-grid intermediaries-modal-form reports-modal-form"
          onSubmit={onGenerate}
        >
          <label className="config-field reports-field-span">
            <span>Report type</span>
            <select
              required
              value={reportType}
              onChange={(e) => setReportType(e.target.value)}
            >
              {typeOptions.map((type) => (
                <option key={type} value={type}>
                  {ucwords(type)}
                </option>
              ))}
            </select>
          </label>
          <AnimatedFormError error={generateError} title="Couldn’t generate" />
        </form>
      </Modal>

      <Modal
        open={Boolean(viewTarget)}
        size="lg"
        title={viewTarget ? ucwords(viewTarget.report_type) : "Report"}
        subtitle={
          viewTarget
            ? `${ucwords(viewTarget.status)} · ${formatShortDateTime(
                viewTarget.completed_at || viewTarget.created_at,
              )}`
            : undefined
        }
        icon={<IconFileText />}
        onClose={() => setViewTarget(null)}
        bodyClassName="intermediaries-modal-body"
        footer={
          <button type="button" className="secondary" onClick={() => setViewTarget(null)}>
            Close
          </button>
        }
      >
        {viewTarget ? (
          viewTarget.status === "FAILED" ? (
            <p className="config-muted customers-feedback is-error" role="alert">
              {viewTarget.failure_message || "Report generation failed."}
            </p>
          ) : (
            <SummaryDetails summary={viewTarget.result_summary ?? {}} />
          )
        ) : null}
      </Modal>
    </section>
  );
}
