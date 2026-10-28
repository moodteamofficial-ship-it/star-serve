import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/app/providers/AuthProvider";
import {
  IconCheckCircle,
  IconChevronLeft,
  IconClaim,
  IconDownload,
  IconFileText,
  IconList,
  IconNote,
  IconSearch,
  IconShield,
  IconTrend,
  IconUser,
  IconWallet,
} from "@/components/ui/icons";
import { Modal } from "@/components/ui/Modal";
import { PdfPreview } from "@/components/ui/PdfPreview";
import { Select } from "@/components/ui/Select";
import { ClaimNotice } from "@/features/claims/ClaimNotice";
import { claimApi, type ClaimDetail } from "@/services/claims/claimApi";
import {
  activityActor,
  activityBadgeTone,
  activityCopy,
  statusBadgeClass,
  claimDeskProgress,
  claimSourceLabel,
  claimStatusLabel,
  claimStatusTone,
  followupStatusLabel,
  followupTypeLabel,
  formatClock,
  formatDay,
  formatWhen,
  money,
  newestFirst,
  payToLabel,
  prettyCode,
  vettingCheckLabel,
  vettingDecisionLabel,
  type DeskStep,
} from "@/features/claims/status";

function MarkDoneButton({
  onConfirm,
  onSaved,
  onError,
}: {
  onConfirm: () => Promise<void>;
  onSaved?: () => Promise<void> | void;
  onError?: (message: string) => void;
}) {
  const [phase, setPhase] = useState<"idle" | "saving" | "saved">("idle");

  return (
    <button
      type="button"
      className={`config-btn config-btn--ghost claims-mark-btn is-${phase}`}
      disabled={phase !== "idle"}
      aria-busy={phase === "saving"}
      aria-live="polite"
      onClick={async () => {
        setPhase("saving");
        try {
          await onConfirm();
          setPhase("saved");
          window.setTimeout(() => {
            void onSaved?.();
          }, 750);
        } catch (err) {
          setPhase("idle");
          onError?.(err instanceof Error ? err.message : "Could not mark that task done");
        }
      }}
    >
      {phase === "saving" ? "Saving…" : phase === "saved" ? "Saved" : "Mark done"}
    </button>
  );
}

function documentKind(doc: Record<string, unknown>) {
  const type = String(doc.content_type || "").toLowerCase();
  const name = String(doc.original_filename || "").toLowerCase();
  if (type.includes("pdf") || name.endsWith(".pdf")) return "pdf" as const;
  if (type.startsWith("image/") || /\.(png|jpe?g|gif|webp|bmp)$/.test(name)) return "image" as const;
  return "file" as const;
}

function fileSizeLabel(bytes?: unknown) {
  const n = Number(bytes);
  if (!Number.isFinite(n) || n <= 0) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

const WORK_ICONS = {
  assign: IconUser,
  assess: IconSearch,
  decide: IconCheckCircle,
  settle: IconWallet,
  close: IconShield,
} as const;

const DESK_ICONS = {
  tasks: IconList,
  documents: IconFileText,
  notes: IconNote,
  activity: IconTrend,
} as const;

let scrollFrame = 0;

function scrollRoot(node: HTMLElement): HTMLElement | Window {
  let current = node.parentElement;
  while (current) {
    const style = getComputedStyle(current);
    const canScroll = /(auto|scroll)/.test(style.overflowY) && current.scrollHeight > current.clientHeight + 1;
    if (canScroll) return current;
    current = current.parentElement;
  }
  return window;
}

function scrollPosition(scroller: HTMLElement | Window) {
  return scroller === window ? window.scrollY : (scroller as HTMLElement).scrollTop;
}

function setScrollPosition(scroller: HTMLElement | Window, top: number) {
  if (scroller === window) window.scrollTo(0, top);
  else (scroller as HTMLElement).scrollTop = top;
}

function pinOffset(scroller: HTMLElement | Window) {
  let cover = scroller === window ? 0 : (scroller as HTMLElement).getBoundingClientRect().top;
  const topbar = document.querySelector(".topbar");
  if (topbar) cover = Math.max(cover, topbar.getBoundingClientRect().bottom);
  if (window.matchMedia("(max-width: 980px)").matches) {
    const rail = document.querySelector(".claims-rail");
    if (rail) cover = Math.max(cover, rail.getBoundingClientRect().bottom);
  }
  return cover + 12;
}

function exactScrollTop(node: HTMLElement, scroller: HTMLElement | Window) {
  const from = scrollPosition(scroller);
  const max =
    scroller === window
      ? Math.max(0, document.documentElement.scrollHeight - window.innerHeight)
      : Math.max(0, (scroller as HTMLElement).scrollHeight - (scroller as HTMLElement).clientHeight);
  return Math.max(0, Math.min(from + node.getBoundingClientRect().top - pinOffset(scroller), max));
}

function smoothScrollTo(node: HTMLElement, duration = 680) {
  cancelAnimationFrame(scrollFrame);
  const scroller = scrollRoot(node);
  const from = scrollPosition(scroller);
  const end = exactScrollTop(node, scroller);
  const delta = end - from;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    setScrollPosition(scroller, end);
    return;
  }
  const started = performance.now();
  const ease = (t: number) => 1 - (1 - t) ** 3;
  const frame = (now: number) => {
    const t = Math.min(1, (now - started) / duration);
    setScrollPosition(scroller, from + delta * ease(t));
    if (t < 1) {
      scrollFrame = requestAnimationFrame(frame);
      return;
    }
    setScrollPosition(scroller, exactScrollTop(node, scroller));
  };
  scrollFrame = requestAnimationFrame(frame);
}

function Fact({
  label,
  value,
  hint,
  mono,
  badge,
}: {
  label: string;
  value?: ReactNode;
  hint?: string;
  mono?: boolean;
  badge?: "id" | "money" | "muted" | "owner";
}) {
  const empty = value == null || value === "";
  let body: ReactNode;
  if (empty) {
    body = <strong>—</strong>;
  } else if (badge === "id") {
    body = <span className="customers-tag customers-tag--id">{value}</span>;
  } else if (badge === "money") {
    body = (
      <span className="claims-amount-badge claims-amount-badge--value">{value}</span>
    );
  } else if (badge === "muted") {
    body = <span className="customers-tag claims-agency-badge">{value}</span>;
  } else if (badge === "owner") {
    const unassigned =
      typeof value === "string" && value.trim().toLowerCase() === "unassigned";
    body = (
      <span className={`claims-owner-badge${unassigned ? " claims-owner-badge--empty" : ""}`}>
        {value}
      </span>
    );
  } else {
    body = <strong>{value}</strong>;
  }
  return (
    <div
      className={`claims-fact${mono || badge === "id" ? " is-mono" : ""}${empty ? " is-empty" : ""}${badge ? " is-badge" : ""}`}
    >
      <dt>{label}</dt>
      <dd>
        {body}
        {hint ? <em>{hint}</em> : null}
      </dd>
    </div>
  );
}

export function ClaimDetailPage() {
  const { claimId = "" } = useParams();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [followupSubject, setFollowupSubject] = useState("");
  const [followupMessage, setFollowupMessage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [more, setMore] = useState<"tasks" | "documents" | "notes" | "activity">("tasks");
  const [section, setSection] = useState<"claim" | "work" | "file" | "desk">("claim");
  const [preview, setPreview] = useState<{
    id: string;
    name: string;
    kind: "pdf" | "image";
    url: string;
    blob?: Blob;
    source?: "document" | "claim-file";
  } | null>(null);
  const [pdfBusy, setPdfBusy] = useState(false);
  const scrolling = useRef(false);
  const scrollUnlock = useRef(0);
  const previewUrl = useRef<string | null>(null);

  const detail = useQuery({
    queryKey: ["claim", claimId],
    queryFn: async () => (await claimApi.get(claimId)).data,
    enabled: Boolean(claimId),
    staleTime: 20_000,
  });

  useEffect(() => {
    if (!claimId) return;
    let cancelled = false;
    void claimApi
      .recordView(claimId)
      .then((response) => {
        if (!cancelled && response.data) queryClient.setQueryData(["claim", response.data.id], response.data);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [claimId, queryClient]);

  useEffect(() => {
    if (!detail.data?.id) return;
    const ids = ["claim", "work", "file", "desk"] as const;
    const nodes = ids
      .map((id) => document.getElementById(`claim-sec-${id}`))
      .filter((node): node is HTMLElement => Boolean(node));
    if (!nodes.length) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (scrolling.current) return;
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (!visible?.target.id) return;
        const next = visible.target.id.replace("claim-sec-", "") as typeof section;
        if (ids.includes(next)) setSection(next);
      },
      { rootMargin: "-18% 0px -58% 0px", threshold: [0.2, 0.45, 0.7] },
    );
    nodes.forEach((node) => observer.observe(node));
    return () => observer.disconnect();
  }, [detail.data?.id]);

  function rememberClaim(next: ClaimDetail) {
    queryClient.setQueryData(["claim", next.id], next);
    void queryClient.invalidateQueries({ queryKey: ["claims"] });
    void queryClient.invalidateQueries({ queryKey: ["claims-dashboard"] });
  }

  const act = useMutation({
    mutationFn: async ({ path, body }: { path: string; body?: Record<string, unknown> }) => {
      if (!detail.data) throw new Error("Claim is still loading");
      return claimApi.action(claimId, path, { version: detail.data.version, ...body });
    },
    onSuccess: (response) => {
      setError(null);
      setReason("");
      rememberClaim(response.data);
    },
    onError: (err: Error) => setError(err.message),
  });

  function closePreview() {
    setPreview(null);
    if (previewUrl.current) {
      URL.revokeObjectURL(previewUrl.current);
      previewUrl.current = null;
    }
  }

  async function viewDocument(doc: Record<string, unknown>) {
    const kind = documentKind(doc);
    if (kind === "file") {
      await claimApi.downloadDocument(claimId, String(doc.id), String(doc.original_filename));
      return;
    }
    setError(null);
    try {
      const blob = await claimApi.fetchDocument(claimId, String(doc.id));
      if (previewUrl.current) URL.revokeObjectURL(previewUrl.current);
      previewUrl.current = URL.createObjectURL(blob);
      setPreview({
        id: String(doc.id),
        name: String(doc.original_filename),
        kind,
        url: previewUrl.current,
        blob: kind === "pdf" ? blob : undefined,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not open that document");
    }
  }

  async function openClaimPdf() {
    setError(null);
    setPdfBusy(true);
    try {
      const blob = await claimApi.fetchPdf(claimId, "inline");
      if (previewUrl.current) URL.revokeObjectURL(previewUrl.current);
      previewUrl.current = URL.createObjectURL(blob);
      setPreview({
        id: "claim-file",
        name: `${detail.data?.claim_number || "claim"}.pdf`,
        kind: "pdf",
        url: previewUrl.current,
        blob,
        source: "claim-file",
      });
      void queryClient.invalidateQueries({ queryKey: ["claim", claimId] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not open the claim PDF");
    } finally {
      setPdfBusy(false);
    }
  }

  async function downloadClaimPdf() {
    setError(null);
    try {
      await claimApi.downloadPdf(claimId, `${detail.data?.claim_number || "claim"}.pdf`);
      void queryClient.invalidateQueries({ queryKey: ["claim", claimId] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not download the claim PDF");
    }
  }

  async function upload(file: File) {
    setError(null);
    try {
      const uploaded = await claimApi.uploadDocument(claimId, file, "OTHER");
      rememberClaim(uploaded);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    }
  }

  if (detail.isLoading || (detail.isFetching && !detail.data)) {
    return (
      <section className="config-page customers-page claims-page claims-detail-page">
        <Link to="/app/claims" className="claims-back" aria-label="Back to claims">
          <IconChevronLeft strokeWidth={2.6} />
        </Link>
        <ClaimDetailSkeleton />
      </section>
    );
  }

  if (!claimId || !detail.data) {
    return (
      <section className="config-page customers-page claims-page claims-detail-page">
        <div className="customers-empty">
          <span className="customers-empty-icon" aria-hidden="true">
            <IconClaim />
          </span>
          <p className="customers-empty-title">This claim is not available</p>
          <p className="customers-empty-copy">It may have been moved, or your role cannot open this file.</p>
          <Link to="/app/claims" className="claims-back">
            Back to claims
          </Link>
        </div>
      </section>
    );
  }

  const claim = detail.data;
  const caps = claim.capabilities ?? ({} as ClaimDetail["capabilities"]);
  const assigned = Boolean(claim.assigned_to_user_id);
  const desk = claimDeskProgress(claim.status, assigned);
  const canAssign = Boolean(caps.can_assign && !assigned);
  const canTake = Boolean(canAssign && user?.id);
  const followups = Array.isArray(claim.followups) ? claim.followups : [];
  const openFollowups = newestFirst(followups.filter((row) => String(row.status) !== "COMPLETED"));
  const deskNotes = newestFirst(Array.isArray(claim.notes) ? claim.notes : []);
  const documents = newestFirst(Array.isArray(claim.documents) ? claim.documents : []);
  const timeline = newestFirst(Array.isArray(claim.timeline) ? claim.timeline : []);
  const vetting = Array.isArray(claim.vetting) ? claim.vetting : [];
  const latestVet = vetting.find((row) => row.is_current) ?? vetting[0];
  const busy = act.isPending || detail.isFetching;
  const coverLine = [claim.policy?.product_code, claim.policy?.cover_option].filter(Boolean).join(" · ");
  const vehicleLine = [claim.vehicle?.make, claim.vehicle?.model].filter(Boolean).join(" ");
  const deskTabs = [
    ["tasks", "Tasks", openFollowups.length],
    ["documents", "Documents", documents.length],
    ["notes", "Notes", deskNotes.length],
    ["activity", "Activity", timeline.length],
  ] as const;
  const workNow = desk.steps.find((step) => step.state === "current") ?? desk.steps[0];
  const WorkIcon = WORK_ICONS[workNow.id] ?? IconClaim;

  function jumpTo(id: "claim" | "work" | "file" | "desk" | "tasks" | "documents" | "notes" | "activity") {
    const target =
      id === "tasks" || id === "documents" || id === "notes" || id === "activity" ? "desk" : id;
    if (
      target === "desk" &&
      (id === "tasks" || id === "documents" || id === "notes" || id === "activity")
    ) {
      setMore(id);
    }
    setSection(target);
    scrolling.current = true;
    window.clearTimeout(scrollUnlock.current);
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        const node = document.getElementById(`claim-sec-${target}`);
        if (!node) {
          scrolling.current = false;
          return;
        }
        smoothScrollTo(node);
        const finish = () => {
          scrolling.current = false;
          window.removeEventListener("scrollend", finish);
        };
        window.addEventListener("scrollend", finish, { once: true });
        scrollUnlock.current = window.setTimeout(finish, 900);
      });
    });
  }

  return (
    <section className="config-page customers-page claims-page claims-detail-page">
      <Link to="/app/claims" className="claims-back" aria-label="Back to claims">
        <IconChevronLeft strokeWidth={2.6} />
      </Link>

      <div className="claims-detail-shell">
      <nav className="claims-rail" aria-label="On this file">
        <p className="customers-stat-label">On this file</p>
        <button
          type="button"
          className={`claims-rail-claim${section === "claim" ? " is-active" : ""}`}
          aria-current={section === "claim" ? "location" : undefined}
          onClick={() => jumpTo("claim")}
        >
          <span className="claims-rail-ico" aria-hidden="true">
            <IconClaim />
          </span>
          <span className="claims-rail-copy">
            <strong>Claim</strong>
            <em className="customers-tag customers-tag--id claims-rail-claim-id">{claim.claim_number}</em>
          </span>
        </button>

        <p className="claims-rail-group">Work</p>
        <button
          type="button"
          className={section === "work" ? "is-active" : ""}
          aria-current={section === "work" ? "location" : undefined}
          onClick={() => jumpTo("work")}
        >
          <span className="claims-rail-ico" aria-hidden="true">
            <WorkIcon />
          </span>
          <span className="claims-rail-copy">
            <strong>Work</strong>
            <em>{workNow.label}</em>
          </span>
        </button>
        <ol className="claims-rail-time" aria-label="Claim progress">
          {desk.steps.map((step) => (
            <li key={step.id} className={`is-${step.state}`}>
              <i className="claims-rail-node" aria-hidden="true" />
              {step.label}
            </li>
          ))}
        </ol>

        <p className="claims-rail-group">Record</p>
        <button
          type="button"
          className={section === "file" ? "is-active" : ""}
          aria-current={section === "file" ? "location" : undefined}
          onClick={() => jumpTo("file")}
        >
          <span className="claims-rail-ico" aria-hidden="true">
            <IconFileText />
          </span>
          File
        </button>

        <p className="claims-rail-group">Desk</p>
        {deskTabs.map(([id, label, count]) => {
          const Icon = DESK_ICONS[id];
          return (
            <button
              key={id}
              type="button"
              className={section === "desk" && more === id ? "is-active" : ""}
              aria-current={section === "desk" && more === id ? "location" : undefined}
              onClick={() => jumpTo(id)}
            >
              <span className="claims-rail-ico" aria-hidden="true">
                <Icon />
              </span>
              {label}
              <span className="claims-rail-count">{count}</span>
            </button>
          );
        })}
      </nav>

      <div className="claims-detail-main">
      <header className="claims-hero" id="claim-sec-claim">
        <div className="claims-hero-head">
          <div className="claims-hero-copy">
            <p className="customers-stat-label">Claim</p>
            <h1>{claim.claimant.name || "Unnamed claimant"}</h1>
            <p className="claims-hero-ref">
              <span className="customers-tag customers-tag--id">{claim.claim_number}</span>
            </p>
          </div>
          <div className="claims-hero-side">
            <span
              className={`customers-status-badge customers-status-badge--${claimStatusTone(claim.status)}`}
            >
              <span className="customers-status-dot__mark" aria-hidden="true" />
              {claimStatusLabel(claim.status)}
            </span>
            <strong className="claims-amount-badge claims-amount-badge--value">
              {money(claim.financial.claimed_amount, claim.financial.currency)}
            </strong>
            <em>Claimed</em>
            <button
              type="button"
              className="config-btn config-btn--ghost claims-pdf-btn"
              disabled={pdfBusy}
              onClick={() => void openClaimPdf()}
            >
              <IconDownload />
              {pdfBusy ? "Preparing…" : "Open PDF"}
            </button>
          </div>
        </div>
        <dl className="claims-hero-facts">
          <Fact label="Agency" value={claim.agency_name} badge="muted" />
          <Fact label="Vehicle" value={claim.vehicle?.registration} badge="id" />
          <Fact label="Policy" value={claim.policy?.policy_number} badge="id" />
          <Fact label="Source" value={claimSourceLabel(claim.channel)} badge="muted" />
          <Fact
            label="Officer"
            value={assigned ? claim.assigned_to_name : "Unassigned"}
            badge="owner"
          />
        </dl>
      </header>

      <ol className="claims-steps" aria-label="Claim steps">
        {desk.steps.map((step) => (
          <li key={step.id} className={`claims-step is-${step.state}`}>
            <span className="claims-step-n">{step.state === "done" ? "✓" : step.n}</span>
            <span className="claims-step-label">{step.label}</span>
          </li>
        ))}
      </ol>

      <article className={`claims-work${busy ? " is-busy" : ""}`} id="claim-sec-work" aria-busy={busy}>
        {busy ? <p className="claims-work-busy">Saving…</p> : null}
        <ClaimNotice message={error} />
        <WorkStep
          claim={claim}
          current={desk.current}
          canAssign={canAssign}
          canTake={canTake}
          userId={user?.id}
          reason={reason}
          onReason={setReason}
          busy={busy}
          openFollowups={openFollowups}
          latestVet={latestVet}
          onAct={(path, body) => act.mutate({ path, body })}
          onCompleteTask={async (id) => {
            setError(null);
            rememberClaim((await claimApi.completeFollowup(claim.id, id)).data);
          }}
          onTaskSaved={(next) => {
            if (next) rememberClaim(next);
          }}
          onTaskError={setError}
        />
      </article>

      <article className="claims-panel claims-file" id="claim-sec-file">
        <header className="claims-file-head claims-file-head--actions">
          <div className="claims-file-head-copy">
            <p className="customers-stat-label">The file</p>
            <h2>What is on record</h2>
          </div>
          <button
            type="button"
            className="config-btn claims-pdf-btn"
            disabled={pdfBusy}
            onClick={() => void openClaimPdf()}
          >
            <IconDownload />
            {pdfBusy ? "Preparing PDF…" : "Open PDF"}
          </button>
        </header>
        <div className="claims-file-body">
          <div className="claims-file-row">
            <section className="claims-file-group">
              <h3>Cover</h3>
              <dl className="claims-file-facts">
                <Fact label="Policy" value={claim.policy?.policy_number} badge="id" />
                <Fact
                  label="Cover"
                  value={coverLine || prettyCode(claim.policy?.status)}
                  badge="muted"
                />
                <Fact
                  label="Vehicle"
                  value={
                    [vehicleLine, claim.vehicle?.registration].filter(Boolean).join(" · ") ||
                    undefined
                  }
                  badge="id"
                />
              </dl>
            </section>
            <section className="claims-file-group">
              <h3>Claimant</h3>
              <dl className="claims-file-facts">
                <Fact label="Name" value={claim.claimant.name} />
                <Fact label="Phone" value={claim.claimant.phone} badge="id" />
                <Fact label="National ID" value={claim.claimant.id_number} badge="id" />
              </dl>
            </section>
          </div>
          <div className="claims-file-row">
            <section className="claims-file-group">
              <h3>Incident</h3>
              <dl className="claims-file-facts">
                <Fact label="Date" value={formatDay(claim.accident?.incident_date)} badge="muted" />
                <Fact label="Location" value={claim.accident?.incident_location} />
              </dl>
            </section>
            <section className="claims-file-group">
              <h3>Money</h3>
              <dl className="claims-file-facts">
                <Fact
                  label="Claimed"
                  value={money(claim.financial.claimed_amount, claim.financial.currency)}
                  badge="money"
                />
                <Fact
                  label="Approved"
                  value={
                    claim.financial.approved_amount
                      ? money(claim.financial.approved_amount, claim.financial.currency)
                      : undefined
                  }
                  badge="money"
                />
                <Fact
                  label="Pay to"
                  value={payToLabel(claim.financial.beneficiary_type)}
                  badge="muted"
                  hint={
                    claim.financial.beneficiary_type === "STAR_SERVE"
                      ? "Insurer pays the agency, then the agency pays the client"
                      : claim.financial.beneficiary_type === "CLIENT"
                        ? "Insurer pays the client directly"
                        : undefined
                  }
                />
              </dl>
            </section>
          </div>
          <section className="claims-file-group claims-file-group--wide">
            <h3>What happened</h3>
            <p className="claims-file-note">
              {claim.accident?.incident_description || "No description on file yet."}
            </p>
          </section>
        </div>
      </article>

      <article className="claims-panel claims-desk" id="claim-sec-desk">
        <header className="claims-desk-head">
          <p className="customers-stat-label">Desk</p>
          <h2>
            {more === "tasks"
              ? "Open work"
              : more === "documents"
                ? "Papers on file"
                : more === "notes"
                  ? "Notes"
                  : "Activity"}
          </h2>
          <p>
            {more === "tasks"
              ? "What the officer or client still needs to do."
              : more === "documents"
                ? "Uploads attached to this claim."
                : more === "notes"
                  ? "Internal remarks stay on the desk. Messages from the client are labelled."
                  : "Who did what on this file, in order."}
          </p>
        </header>
        <div className="claims-desk-tabs" role="tablist" aria-label="Desk sections">
          {deskTabs.map(([id, label, count]) => {
            const Icon = DESK_ICONS[id];
            return (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={more === id}
                className={more === id ? "is-active" : ""}
                onClick={() => jumpTo(id)}
              >
                <Icon />
                {label}
                <span>{count}</span>
              </button>
            );
          })}
        </div>

        {more === "tasks" ? (
          <div className="claims-pane">
            <div className="claims-pane-main">
              {openFollowups.length === 0 ? (
                <div className="claims-pane-empty">
                  <span className="claims-rail-ico" aria-hidden="true">
                    <IconList />
                  </span>
                  <strong>No open tasks</strong>
                  <p>Add something the officer or client still needs to do.</p>
                </div>
              ) : (
                <ul className="claims-task-table">
                  {openFollowups.map((row) => {
                    const due = row.due_at ? formatWhen(String(row.due_at)) : "";
                    const message = String(row.message || "").trim();
                    return (
                      <li key={String(row.id)}>
                        <div className="claims-task-copy">
                          <div className="claims-task-meta">
                            <em>{followupTypeLabel(String(row.followup_type))}</em>
                            <span className={statusBadgeClass(String(row.status))}>
                              {followupStatusLabel(String(row.status))}
                            </span>
                            {due ? <time>Due {due}</time> : null}
                          </div>
                          <strong>{String(row.subject)}</strong>
                          {message ? <p>{message}</p> : null}
                        </div>
                        {caps.can_complete_followup ? (
                          <MarkDoneButton
                            onConfirm={async () => {
                              setError(null);
                              rememberClaim(
                                (await claimApi.completeFollowup(claim.id, String(row.id))).data,
                              );
                            }}
                            onSaved={() => undefined}
                            onError={setError}
                          />
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
            {caps.can_create_followup ? (
              <form
                className="claims-pane-foot"
                onSubmit={async (event) => {
                  event.preventDefault();
                  const created = await claimApi.action(claim.id, "followups", {
                    subject: followupSubject,
                    message: followupMessage,
                    followup_type: "CLIENT_INFORMATION",
                  });
                  setFollowupSubject("");
                  setFollowupMessage("");
                  rememberClaim(created.data);
                }}
              >
                <div className="claims-pane-fields">
                  <label className="claims-reason-field">
                    Task
                    <input
                      value={followupSubject}
                      onChange={(event) => setFollowupSubject(event.target.value)}
                      placeholder="What still needs doing"
                      required
                    />
                  </label>
                  <label className="claims-reason-field">
                    Note
                    <input
                      value={followupMessage}
                      onChange={(event) => setFollowupMessage(event.target.value)}
                      placeholder="For the officer or client"
                      required
                    />
                  </label>
                </div>
                <button type="submit" className="config-btn config-btn--ghost">
                  Add task
                </button>
              </form>
            ) : null}
          </div>
        ) : null}

        {more === "documents" ? (
          <div className="claims-pane">
            <div className="claims-pane-main">
              {documents.length === 0 ? (
                <div className="claims-pane-empty">
                  <span className="claims-rail-ico" aria-hidden="true">
                    <IconFileText />
                  </span>
                  <strong>No documents yet</strong>
                  <p>Attach abstracts, photos, or other papers to this file.</p>
                </div>
              ) : (
                <ul className="claims-doc-table">
                  {documents.map((doc) => {
                    const when = doc.created_at ? formatWhen(String(doc.created_at)) : "";
                    const size = fileSizeLabel(doc.file_size_bytes);
                    return (
                      <li key={String(doc.id)}>
                        <span className="claims-rail-ico" aria-hidden="true">
                          <IconFileText />
                        </span>
                        <div>
                          <strong>{String(doc.original_filename)}</strong>
                          <p>{[prettyCode(String(doc.kind || "Document")), size, when].filter(Boolean).join(" · ")}</p>
                        </div>
                        {caps.can_download_document ? (
                          <div className="claims-doc-actions">
                            {documentKind(doc) !== "file" ? (
                              <button
                                type="button"
                                className="config-btn config-btn--ghost"
                                onClick={() => void viewDocument(doc)}
                              >
                                View
                              </button>
                            ) : null}
                            <button
                              type="button"
                              className="config-btn config-btn--ghost"
                              onClick={() =>
                                claimApi.downloadDocument(claim.id, String(doc.id), String(doc.original_filename))
                              }
                            >
                              Download
                            </button>
                          </div>
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
            {caps.can_upload_document ? (
              <label className="claims-pane-foot claims-file-btn">
                Add document
                <input
                  type="file"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) void upload(file);
                    event.target.value = "";
                  }}
                />
              </label>
            ) : null}
          </div>
        ) : null}

        {more === "notes" ? (
          <div className="claims-pane">
            <div className="claims-pane-main">
              {!caps.can_view_notes ? (
                <div className="claims-pane-empty">
                  <span className="claims-rail-ico" aria-hidden="true">
                    <IconNote />
                  </span>
                  <strong>Notes are hidden</strong>
                  <p>Desk notes are not visible on this role.</p>
                </div>
              ) : deskNotes.length === 0 ? (
                <div className="claims-pane-empty">
                  <span className="claims-rail-ico" aria-hidden="true">
                    <IconNote />
                  </span>
                  <strong>No notes yet</strong>
                  <p>Desk remarks stay on the file. Client messages are labelled separately.</p>
                </div>
              ) : (
                <ul className="claims-note-thread">
                  {deskNotes.map((row) => (
                    <li key={String(row.id)}>
                      <div className="claims-note-meta">
                        <em>{row.visibility === "CLIENT" ? "Client" : "Desk"}</em>
                        {row.created_at ? <time>{formatWhen(String(row.created_at))}</time> : null}
                      </div>
                      <p>{String(row.body)}</p>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            {caps.can_add_note ? (
              <form
                className="claims-pane-foot"
                onSubmit={async (event) => {
                  event.preventDefault();
                  const saved = await claimApi.action(claim.id, "notes", { body: note });
                  setNote("");
                  rememberClaim(saved.data);
                }}
              >
                <label className="claims-reason-field">
                  Note
                  <textarea
                    value={note}
                    onChange={(event) => setNote(event.target.value)}
                    placeholder="Internal — never sent to the client"
                    rows={3}
                    required
                  />
                </label>
                <button type="submit" className="config-btn config-btn--ghost">
                  Add note
                </button>
              </form>
            ) : null}
          </div>
        ) : null}

        {more === "activity" ? (
          <div className="claims-pane">
            <div className="claims-pane-main">
              {timeline.length === 0 ? (
                <div className="claims-pane-empty">
                  <span className="claims-rail-ico" aria-hidden="true">
                    <IconTrend />
                  </span>
                  <strong>No activity yet</strong>
                  <p>Actions on this file will appear here in order.</p>
                </div>
              ) : (
                <ol className="claims-activity">
                  {timeline.map((event, index) => {
                    const { title, detail } = activityCopy(event);
                    const day = formatDay(event.created_at);
                    const showDay = index === 0 || day !== formatDay(timeline[index - 1].created_at);
                    const who = activityActor(event);
                    const clock = formatClock(event.created_at);
                    return (
                      <li key={event.id}>
                        {showDay ? <p className="customers-stat-label">{day}</p> : null}
                        <div className="claims-activity-row">
                          <div className="claims-activity-copy">
                            <span className={`ov-status ov-status--${activityBadgeTone(event)}`}>{title}</span>
                            {detail ? <p className="claims-activity-detail">{detail}</p> : null}
                          </div>
                          <div className="claims-note-meta">
                            {clock ? <time dateTime={event.created_at}>{clock}</time> : null}
                            <span>{who}</span>
                          </div>
                        </div>
                      </li>
                    );
                  })}
                </ol>
              )}
            </div>
          </div>
        ) : null}
      </article>
      </div>
      </div>

      <Modal
        open={Boolean(preview)}
        title={preview?.source === "claim-file" ? "Claim file" : preview?.kind === "pdf" ? "Document PDF" : "Document"}
        subtitle={preview?.source === "claim-file" ? claim.claim_number : preview?.name || "Preview"}
        icon={<IconFileText />}
        size="fit"
        bodyClassName="modal-body--pdf"
        onClose={closePreview}
        footer={
          <>
            <button type="button" className="config-btn config-btn--ghost" onClick={closePreview}>
              Close
            </button>
            {preview ? (
              <button
                type="button"
                className="config-btn"
                onClick={() =>
                  void (preview.source === "claim-file"
                    ? downloadClaimPdf()
                    : claimApi.downloadDocument(claim.id, preview.id, preview.name))
                }
              >
                Download PDF
              </button>
            ) : null}
          </>
        }
      >
        {preview?.kind === "pdf" && preview.blob ? <PdfPreview data={preview.blob} /> : null}
        {preview?.kind === "image" ? (
          <div className="cert-pdf-preview-scroll">
            <img className="claims-doc-preview" src={preview.url} alt={preview.name} />
          </div>
        ) : null}
      </Modal>
    </section>
  );
}

function SkelFact({ label, wide = false }: { label: string; wide?: boolean }) {
  return (
    <div className="claims-fact">
      <dt>{label}</dt>
      <dd>
        <span className={`skeleton-block${wide ? " claims-skel-fact--wide" : " claims-skel-fact"}`} />
      </dd>
    </div>
  );
}

function ClaimDetailSkeleton() {
  return (
    <div className="claims-detail-shell" aria-busy="true" aria-label="Loading claim">
      <nav className="claims-rail" aria-label="On this file">
        <p className="customers-stat-label">On this file</p>
        <div className="claims-rail-claim claims-skel-rail-btn">
          <span className="skeleton-block claims-skel-ico" />
          <span className="claims-rail-copy">
            <strong>Claim</strong>
            <span className="skeleton-block claims-skel-rail-sub" />
          </span>
        </div>
        <p className="claims-rail-group">Work</p>
        <div className="claims-skel-rail-btn">
          <span className="skeleton-block claims-skel-ico" />
          <span className="claims-rail-copy">
            <strong>Work</strong>
            <span className="skeleton-block claims-skel-rail-sub" />
          </span>
        </div>
        <ol className="claims-rail-time" aria-label="Claim progress">
          {["Assign", "Assess", "Decide", "Settle", "Close"].map((label) => (
            <li key={label}>
              <i className="claims-rail-node" aria-hidden="true" />
              {label}
            </li>
          ))}
        </ol>
        <p className="claims-rail-group">Record</p>
        <div className="claims-skel-rail-btn">
          <span className="skeleton-block claims-skel-ico" />
          File
        </div>
        <p className="claims-rail-group">Desk</p>
        {["Tasks", "Documents", "Notes", "Activity"].map((label) => (
          <div key={label} className="claims-skel-rail-btn">
            <span className="skeleton-block claims-skel-ico" />
            {label}
            <span className="skeleton-block claims-skel-rail-count" />
          </div>
        ))}
      </nav>

      <div className="claims-detail-main">
        <header className="claims-hero">
          <div className="claims-hero-head">
            <div className="claims-hero-copy">
              <p className="customers-stat-label">Claim</p>
              <span className="skeleton-block claims-skel-hero-name" />
              <span className="skeleton-block claims-skel-hero-ref" />
            </div>
            <div className="claims-hero-side">
              <span className="skeleton-block claims-skel-status" />
              <span className="skeleton-block claims-skel-hero-money" />
              <em>Claimed</em>
            </div>
          </div>
          <dl className="claims-hero-facts">
            <SkelFact label="Agency" />
            <SkelFact label="Vehicle" />
            <SkelFact label="Policy" />
            <SkelFact label="Source" />
            <SkelFact label="Officer" />
          </dl>
        </header>

        <ol className="claims-steps" aria-label="Claim steps">
          {["Assign", "Assess", "Decide", "Settle", "Close"].map((label) => (
            <li key={label} className="claims-step">
              <span className="skeleton-block claims-skel-step-n" />
              <span className="claims-step-label">{label}</span>
            </li>
          ))}
        </ol>

        <article className="claims-work">
          <span className="skeleton-block claims-skel-work-kicker" />
          <span className="skeleton-block claims-skel-work-title" />
          <span className="skeleton-block claims-skel-work-copy" />
          <div className="claims-next-actions">
            <span className="skeleton-block claims-skel-btn" />
            <span className="skeleton-block claims-skel-btn" />
          </div>
        </article>

        <article className="claims-panel claims-file">
          <header className="claims-file-head">
            <p className="customers-stat-label">The file</p>
            <h2>What is on record</h2>
          </header>
          <div className="claims-file-body">
            <div className="claims-file-row">
              <section className="claims-file-group">
                <h3>Cover</h3>
                <dl className="claims-file-facts">
                  <SkelFact label="Policy" />
                  <SkelFact label="Cover" />
                  <SkelFact label="Vehicle" wide />
                </dl>
              </section>
              <section className="claims-file-group">
                <h3>Claimant</h3>
                <dl className="claims-file-facts">
                  <SkelFact label="Name" />
                  <SkelFact label="Phone" />
                  <SkelFact label="National ID" />
                </dl>
              </section>
            </div>
            <div className="claims-file-row">
              <section className="claims-file-group">
                <h3>Incident</h3>
                <dl className="claims-file-facts">
                  <SkelFact label="Date" />
                  <SkelFact label="Location" wide />
                </dl>
              </section>
              <section className="claims-file-group">
                <h3>Money</h3>
                <dl className="claims-file-facts">
                  <SkelFact label="Claimed" />
                  <SkelFact label="Approved" />
                  <SkelFact label="Pay to" />
                </dl>
              </section>
            </div>
            <section className="claims-file-group claims-file-group--wide">
              <h3>What happened</h3>
              <span className="skeleton-block claims-skel-note" />
            </section>
          </div>
        </article>
      </div>
    </div>
  );
}

function WorkStep({
  claim,
  current,
  canAssign,
  canTake,
  userId,
  reason,
  onReason,
  busy,
  openFollowups,
  latestVet,
  onAct,
  onCompleteTask,
  onTaskSaved,
  onTaskError,
}: {
  claim: ClaimDetail;
  current: DeskStep["id"];
  canAssign: boolean;
  canTake: boolean;
  userId?: string;
  reason: string;
  onReason: (value: string) => void;
  busy: boolean;
  openFollowups: Array<Record<string, unknown>>;
  latestVet?: Record<string, unknown>;
  onAct: (path: string, body?: Record<string, unknown>) => void;
  onCompleteTask: (id: string) => Promise<void>;
  onTaskSaved: (next?: ClaimDetail) => void;
  onTaskError: (message: string) => void;
}) {
  const caps = claim.capabilities;
  const status = claim.status;
  const [officerId, setOfficerId] = useState("");
  const [taskSubject, setTaskSubject] = useState("");
  const [taskNote, setTaskNote] = useState("");
  const [taskType, setTaskType] = useState("INTERNAL_REVIEW");
  const [taskError, setTaskError] = useState<string | null>(null);
  const officers = useQuery({
    queryKey: ["claim-assignees", claim.id],
    queryFn: async () => (await claimApi.listAssignees(claim.id)).data,
    enabled: canAssign && current === "assign",
  });

  if (current === "assign") {
    const options = (officers.data?.items ?? []).map((row) => ({
      value: row.id,
      label: row.role ? `${row.name} · ${row.role}` : row.name,
    }));
    const chosen = officerId || (options.some((row) => row.value === userId) ? userId : "");
    const canDraftTask = canAssign || Boolean(caps.can_vet);
    const draftedTask = () => {
      const subject = taskSubject.trim();
      const message = taskNote.trim();
      if (!subject && !message) return undefined;
      if (!subject || !message) {
        setTaskError("Add a task title and a short note, or leave both blank.");
        return null;
      }
      setTaskError(null);
      return { subject, message, followup_type: taskType };
    };
    const actWithTask = (path: string, body: Record<string, unknown> = {}) => {
      const task = draftedTask();
      if (task === null) return;
      onAct(path, task ? { ...body, task } : body);
    };
    return (
      <>
        <p className="customers-stat-label">Step 1 · Assign</p>
        <h2>{status === "CLAIM_DRAFT" ? "Submit this draft" : "This file has no owner"}</h2>
        <p>
          {status === "CLAIM_DRAFT"
            ? "Submit it when the report is ready. An officer can then take it and assess the loss."
            : "Assign an officer so the desk knows who owns the file. Assessment comes next."}
        </p>
        <div className="claims-assign-form">
          {canAssign ? (
            <>
              <Select
                label="Assign to"
                value={chosen ?? ""}
                onChange={setOfficerId}
                options={options}
                placeholder={officers.isPending ? "Loading officers…" : "Choose an officer"}
                searchable
                fieldClassName="claims-reason-field"
              />
              {officers.isSuccess && options.length === 0 ? (
                <p className="claims-quiet">
                  This agency has no claims officers yet. Invite staff on this agency, or start the
                  assessment yourself.
                </p>
              ) : null}
            </>
          ) : null}
          {canDraftTask ? (
            <>
              {openFollowups.length ? (
                <ul className="claims-task-table claims-assign-task-list">
                  {openFollowups.map((row) => (
                    <li key={String(row.id)}>
                      <div className="claims-task-copy">
                        <div className="claims-task-meta">
                          <em>{followupTypeLabel(String(row.followup_type))}</em>
                          <span className={statusBadgeClass(String(row.status))}>
                            {followupStatusLabel(String(row.status))}
                          </span>
                        </div>
                        <strong>{String(row.subject)}</strong>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : null}
              <div className="claims-assign-form-row">
                <Select
                  label="Task type"
                  value={taskType}
                  onChange={setTaskType}
                  fieldClassName="claims-reason-field"
                  options={[
                    { value: "INTERNAL_REVIEW", label: "Internal review" },
                    { value: "CLIENT_INFORMATION", label: "Client follow-up" },
                    { value: "DOCUMENT_REQUIRED", label: "Document required" },
                  ]}
                />
                <label className="claims-reason-field">
                  Task
                  <input
                    value={taskSubject}
                    onChange={(event) => setTaskSubject(event.target.value)}
                    placeholder="What the officer should do"
                  />
                </label>
              </div>
              <label className="claims-reason-field">
                Note
                <input
                  value={taskNote}
                  onChange={(event) => setTaskNote(event.target.value)}
                  placeholder="Optional. Saved when you assign or start assessment."
                />
              </label>
              {taskError ? <p className="claims-quiet">{taskError}</p> : null}
            </>
          ) : null}
        </div>
        <div className="claims-next-actions">
          {canAssign ? (
            <button
              type="button"
              className="config-btn"
              disabled={busy || !chosen}
              onClick={() => actWithTask("assign", { assigned_to_user_id: chosen, reason: "MANUAL" })}
            >
              Assign this claim
            </button>
          ) : null}
          {canTake && userId && chosen !== userId ? (
            <button
              type="button"
              className="config-btn config-btn--ghost"
              disabled={busy}
              onClick={() => actWithTask("assign", { assigned_to_user_id: userId, reason: "MANUAL" })}
            >
              Take it myself
            </button>
          ) : null}
          {caps.can_edit && status === "CLAIM_DRAFT" ? (
            <button type="button" className="config-btn" disabled={busy} onClick={() => onAct("submit")}>
              Submit for assessment
            </button>
          ) : null}
          {caps.can_vet && status === "CLAIM_SUBMITTED" ? (
            <button
              type="button"
              className="config-btn config-btn--ghost"
              disabled={busy}
              onClick={() => actWithTask("start-vetting")}
            >
              Skip and start assessment
            </button>
          ) : null}
        </div>
        {!canAssign && !caps.can_vet && status !== "CLAIM_DRAFT" ? (
          <p className="claims-quiet">An officer at this agency needs to take the file before anyone can assess it.</p>
        ) : null}
      </>
    );
  }

  if (current === "assess") {
    if (status === "VETTING" && caps.can_vet) {
      return (
        <VettingForm
          onSubmit={(body) => onAct("vet", body)}
          busy={busy}
          openTaskCount={openFollowups.length}
          openFollowups={openFollowups}
          onCompleteTask={onCompleteTask}
          onTaskSaved={onTaskSaved}
          onTaskError={onTaskError}
          canComplete={caps.can_complete_followup}
        />
      );
    }
    return (
      <>
        <p className="customers-stat-label">Step 2 · Assess</p>
        <h2>{status === "ADDITIONAL_INFORMATION_REQUIRED" ? "Waiting on the client" : "Assess"}</h2>
        {latestVet ? (
          <p className="claims-vet-result">
            <strong>{vettingDecisionLabel(String(latestVet.decision || ""))}</strong>
            <span>{String(latestVet.decision_reason || "Assessment started")}</span>
          </p>
        ) : null}
        <div className="claims-next-actions">
          {caps.can_vet && status === "CLAIM_SUBMITTED" ? (
            <button type="button" className="config-btn" disabled={busy} onClick={() => onAct("start-vetting")}>
              Start assessment
            </button>
          ) : null}
          {caps.can_vet && status === "ADDITIONAL_INFORMATION_REQUIRED" ? (
            <button type="button" className="config-btn" disabled={busy} onClick={() => onAct("resume-vetting")}>
              Resume assessment
            </button>
          ) : null}
        </div>
      </>
    );
  }

  if (current === "decide") {
    return (
      <>
        <p className="customers-stat-label">Step 3 · Decide</p>
        <h2>Ready to decide</h2>
        <p>Approve, decline, or send this to the insurer.</p>
        {latestVet ? (
          <p className="claims-vet-result">
            <strong>{vettingDecisionLabel(String(latestVet.decision || ""))}</strong>
            <span>{String(latestVet.decision_reason || "")}</span>
          </p>
        ) : null}
        {caps.already_approved ? (
          <ClaimNotice
            title="You already signed this"
            message="Another officer still needs to approve."
            tone="wait"
          />
        ) : null}
        <label className="claims-reason-field">
          Note
          <textarea
            value={reason}
            onChange={(event) => onReason(event.target.value)}
            rows={2}
            placeholder="Required if you decline"
          />
        </label>
        <div className="claims-next-actions">
          {caps.can_approve && !caps.already_approved ? (
            <button type="button" className="config-btn" disabled={busy} onClick={() => onAct("approve", { reason })}>
              Approve
            </button>
          ) : null}
          {caps.can_forward ? (
            <button type="button" className="config-btn" disabled={busy} onClick={() => onAct("forward-to-definite")}>
              Send to insurer
            </button>
          ) : null}
          {caps.can_reject ? (
            <button
              type="button"
              className="config-btn config-btn--danger"
              disabled={busy || !reason.trim()}
              onClick={() => onAct("reject", { reason })}
            >
              Decline claim
            </button>
          ) : null}
        </div>
      </>
    );
  }

  if (current === "settle") {
    return <SettleWork claim={claim} reason={reason} onReason={onReason} busy={busy} onAct={onAct} />;
  }

  return (
    <>
      <p className="customers-stat-label">Step 5 · Close</p>
      <h2>{["CLOSED", "VETTING_FAILED", "REJECTED", "DEFINITE_REJECTED", "CANCELLED", "WITHDRAWN"].includes(status) ? "This file is finished" : "Close the file"}</h2>
      <p>
        {status === "CLIENT_NOTIFIED"
          ? "The client has been informed. Close the file when nothing else is outstanding."
          : "No further desk action is required unless a supervisor reopens it."}
      </p>
      {caps.can_close ? (
        <div className="claims-next-actions">
          <button type="button" className="config-btn" disabled={busy} onClick={() => onAct("close")}>
            Close file
          </button>
        </div>
      ) : null}
    </>
  );
}

function amountValue(value: string | number | null | undefined) {
  if (value == null || value === "") return "";
  return String(value);
}

function SettleWork({
  claim,
  reason,
  onReason,
  busy,
  onAct,
}: {
  claim: ClaimDetail;
  reason: string;
  onReason: (value: string) => void;
  busy: boolean;
  onAct: (path: string, body?: Record<string, unknown>) => void;
}) {
  const caps = claim.capabilities;
  const status = claim.status;
  const withInsurer = ["SENT_TO_DEFINITE", "DEFINITE_REVIEW"].includes(status);
  const [amount, setAmount] = useState(
    amountValue(claim.financial.approved_amount ?? claim.financial.claimed_amount),
  );
  const [payee, setPayee] = useState(claim.financial.beneficiary_type === "STAR_SERVE" ? "STAR_SERVE" : "CLIENT");
  const [reference, setReference] = useState("");

  if (withInsurer) {
    return (
      <>
        <p className="customers-stat-label">Step 4 · Settle</p>
        <h2>With the insurer</h2>
        <p>
          The insurer is not on Star Serve. When they call, email, or send a letter, record what they decided
          and who they will pay.
        </p>
        {caps.can_record_insurer_decision ? (
          <>
            <label className="claims-reason-field">
              Amount they approved
              <input
                type="number"
                min="0"
                step="0.01"
                value={amount}
                onChange={(event) => setAmount(event.target.value)}
              />
            </label>
            <fieldset className="claims-payee">
              <legend>Who they pay</legend>
              <label className="claims-check">
                <input
                  type="radio"
                  name="payee"
                  checked={payee === "CLIENT"}
                  onChange={() => setPayee("CLIENT")}
                />
                <span>Policyholder — insurer pays the client directly</span>
              </label>
              <label className="claims-check">
                <input
                  type="radio"
                  name="payee"
                  checked={payee === "STAR_SERVE"}
                  onChange={() => setPayee("STAR_SERVE")}
                />
                <span>Agency — insurer pays Star Serve, then we pay the client</span>
              </label>
            </fieldset>
            <label className="claims-reason-field">
              Note from the insurer
              <textarea
                value={reason}
                onChange={(event) => onReason(event.target.value)}
                rows={2}
                placeholder="Required if they declined"
              />
            </label>
            <div className="claims-next-actions">
              <button
                type="button"
                className="config-btn"
                disabled={busy || !amount || Number(amount) <= 0}
                onClick={() =>
                  onAct("record-insurer-decision", {
                    decision: "APPROVED",
                    approved_amount: amount,
                    beneficiary_type: payee,
                    reason,
                  })
                }
              >
                Insurer approved
              </button>
              <button
                type="button"
                className="config-btn config-btn--danger"
                disabled={busy || !reason.trim()}
                onClick={() =>
                  onAct("record-insurer-decision", {
                    decision: "REJECTED",
                    beneficiary_type: payee,
                    reason,
                  })
                }
              >
                Insurer declined
              </button>
            </div>
          </>
        ) : (
          <p className="claims-quiet">A claims manager or senior officer records the insurer decision on this file.</p>
        )}
      </>
    );
  }

  const agencyPays = (claim.financial.beneficiary_type || payee) === "STAR_SERVE";

  return (
    <>
      <p className="customers-stat-label">Step 4 · Settle</p>
      <h2>Payment</h2>
      <p>
        {agencyPays
          ? `The insurer is paying the agency ${money(claim.financial.approved_amount, claim.financial.currency)}. Confirm when Star Serve has paid the client.`
          : `The insurer is paying the policyholder ${money(claim.financial.approved_amount, claim.financial.currency)} directly. Confirm when the client has received the money.`}
      </p>
      {caps.can_record_settlement ? (
        <>
          <label className="claims-reason-field">
            Payout reference
            <input
              value={reference}
              onChange={(event) => setReference(event.target.value)}
              placeholder="M-Pesa, cheque, or insurer reference — optional"
            />
          </label>
          <div className="claims-next-actions">
            <button
              type="button"
              className="config-btn"
              disabled={busy}
              onClick={() =>
                onAct("record-settlement", {
                  beneficiary_type: claim.financial.beneficiary_type || payee,
                  reference,
                  note: reason,
                })
              }
            >
              {agencyPays ? "Confirm the agency paid the client" : "Confirm the client has been paid"}
            </button>
          </div>
        </>
      ) : null}
      <div className="claims-next-actions">
        {caps.can_authorize_payment && status === "PAYMENT_PENDING" ? (
          <button type="button" className="config-btn config-btn--ghost" disabled={busy} onClick={() => onAct("request-payment")}>
            Request payment
          </button>
        ) : null}
        {caps.can_authorize_payment && ["PAYMENT_AUTHORIZATION", "PAYMENT_REVIEW"].includes(status) ? (
          <button type="button" className="config-btn config-btn--ghost" disabled={busy} onClick={() => onAct("authorize-payment")}>
            Authorize payment
          </button>
        ) : null}
        {caps.can_execute_payment ? (
          <button
            type="button"
            className="config-btn config-btn--ghost"
            disabled={busy}
            onClick={() =>
              onAct("execute-payment", { idempotency_key: `ui-${claim.id}-${claim.version}-${Date.now()}` })
            }
          >
            Execute payment
          </button>
        ) : null}
      </div>
      {!caps.can_record_settlement && !caps.can_authorize_payment && !caps.can_execute_payment ? (
        <p className="claims-quiet">Finance or a claims manager confirms the payout on this file.</p>
      ) : null}
    </>
  );
}

function VettingForm({
  onSubmit,
  busy,
  openTaskCount,
  openFollowups,
  onCompleteTask,
  onTaskSaved,
  onTaskError,
  canComplete,
}: {
  onSubmit: (body: Record<string, unknown>) => void;
  busy: boolean;
  openTaskCount: number;
  openFollowups: Array<Record<string, unknown>>;
  onCompleteTask: (id: string) => Promise<void>;
  onTaskSaved: (next?: ClaimDetail) => void;
  onTaskError: (message: string) => void;
  canComplete: boolean;
}) {
  const [decision, setDecision] = useState("PASS");
  const [reason, setReason] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const [checks, setChecks] = useState<Record<string, boolean>>({
    claimant_verified: false,
    policy_active_at_incident: false,
    coverage_confirmed: false,
    documents_complete: false,
    accident_details_consistent: false,
    no_unresolved_followups: false,
  });
  const formError = localError;

  return (
    <form
      className="claims-vet-form"
      onSubmit={(event) => {
        event.preventDefault();
        const note = reason.trim();
        if (note.length < 3) {
          setLocalError("Add a reason.");
          return;
        }
        if (decision === "PASS") {
          const missing = Object.entries(checks).filter(([, value]) => !value);
          if (missing.length) {
            setLocalError("Tick every checklist item first.");
            return;
          }
          if (openTaskCount > 0) {
            setLocalError(
              openTaskCount === 1
                ? "Mark the open task done first."
                : `Mark all ${openTaskCount} open tasks done first.`,
            );
            return;
          }
        }
        setLocalError(null);
        onSubmit({ decision, decision_reason: note, checklist: checks, findings: {}, required_documents: [] });
      }}
    >
      <header className="claims-vet-head">
        <p className="customers-stat-label">Step 2 · Assess</p>
        <ClaimNotice message={formError} />
      </header>
      {openFollowups.length ? (
        <section className="claims-vet-block">
          <header className="claims-file-head">
            <h2>Open tasks</h2>
          </header>
          <ul className="claims-task-table claims-vet-tasks">
            {openFollowups.map((row) => (
              <li key={String(row.id)}>
                <div className="claims-task-copy">
                  <div className="claims-task-meta">
                    <em>{followupTypeLabel(String(row.followup_type))}</em>
                    <span className={statusBadgeClass(String(row.status))}>
                      {followupStatusLabel(String(row.status))}
                    </span>
                  </div>
                  <strong>{String(row.subject)}</strong>
                  {String(row.message || "").trim() ? <p>{String(row.message)}</p> : null}
                </div>
                {canComplete ? (
                  <MarkDoneButton
                    onConfirm={() => onCompleteTask(String(row.id))}
                    onSaved={onTaskSaved}
                    onError={onTaskError}
                  />
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <section className="claims-vet-block">
        <header className="claims-file-head">
          <h2>Checklist</h2>
        </header>
        <div className="claims-checks">
          {Object.entries(checks).map(([key, value]) => (
            <label key={key} className="claims-check">
              <input
                type="checkbox"
                checked={value}
                onChange={(event) => setChecks((current) => ({ ...current, [key]: event.target.checked }))}
              />
              <span>{vettingCheckLabel(key)}</span>
            </label>
          ))}
        </div>
      </section>
      <section className="claims-vet-block">
        <header className="claims-file-head">
          <h2>Decision</h2>
        </header>
        <div className="claims-vet-fields">
          <Select
            label="Outcome"
            value={decision}
            onChange={setDecision}
            fieldClassName="claims-reason-field"
            options={[
              { value: "PASS", label: "Pass" },
              { value: "FAIL", label: "Fail" },
              { value: "MORE_INFORMATION_REQUIRED", label: "Need more information" },
            ]}
          />
          <label className="claims-reason-field">
            Reason
            <textarea
              required
              minLength={3}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Short reason"
              rows={3}
            />
          </label>
          <button type="submit" className="config-btn" disabled={busy}>
            Record decision
          </button>
        </div>
      </section>
    </form>
  );
}
