const STATUS_LABELS: Record<string, string> = {
  CLAIM_DRAFT: "Draft",
  CLAIM_SUBMITTED: "New report",
  VETTING: "Under assessment",
  ADDITIONAL_INFORMATION_REQUIRED: "Awaiting information",
  VETTING_PASSED: "Assessment passed",
  VETTING_FAILED: "Assessment failed",
  SENT_TO_DEFINITE: "Sent to insurer",
  DEFINITE_REVIEW: "With insurer",
  DEFINITE_APPROVED: "Insurer approved",
  DEFINITE_REJECTED: "Insurer declined",
  PAYMENT_PENDING: "Payment pending",
  PAYMENT_AUTHORIZATION: "Payment authorization",
  PAYMENT_AUTHORIZED: "Payment authorized",
  PAYMENT_PROCESSING: "Payment processing",
  PAYMENT_COMPLETED: "Paid",
  PAYMENT_FAILED: "Payment failed",
  PAYMENT_REVIEW: "Payment review",
  CLIENT_NOTIFIED: "Client notified",
  CLOSED: "Closed",
  REJECTED: "Declined",
  CANCELLED: "Cancelled",
  WITHDRAWN: "Withdrawn",
};

export function claimStatusLabel(status: string) {
  return STATUS_LABELS[status.trim().toUpperCase()] || prettyCode(status);
}

export function claimStageCopy(status: string, assigned: boolean, channel?: string | null) {
  const key = status.trim().toUpperCase();
  if (key === "CLAIM_DRAFT") {
    return {
      title: "Draft file",
      body: "This claim is still being prepared. Submit it when the report is ready for assessment.",
    };
  }
  if (key === "CLAIM_SUBMITTED" && !assigned) {
    return {
      title: "Waiting to be taken on",
      body:
        channel === "GUEST"
          ? "Filed from the public welcome screen. Take ownership, then confirm identity, cover, and the accident report."
          : "This report is unassigned. Take it on before starting the assessment.",
    };
  }
  if (key === "CLAIM_SUBMITTED") {
    return {
      title: "Ready for assessment",
      body: "Confirm the claimant, policy, and accident details, then start the assessment.",
    };
  }
  if (key === "VETTING") {
    return {
      title: "Assessment in progress",
      body: "Work through the checklist and record a decision. Ask the client for anything still missing.",
    };
  }
  if (key === "ADDITIONAL_INFORMATION_REQUIRED") {
    return {
      title: "Waiting on the client",
      body: "Resume assessment once the requested information or documents are on file.",
    };
  }
  if (key === "VETTING_PASSED") {
    return {
      title: "Ready for approval",
      body: "Assessment passed. Approve the file, decline it, or send it to the insurer.",
    };
  }
  if (key === "SENT_TO_DEFINITE" || key === "DEFINITE_REVIEW") {
    return {
      title: "With the insurer",
      body: "The insurer works outside Star Serve. Record their decision when they call, email, or write back.",
    };
  }
  if (key === "DEFINITE_APPROVED" || key === "PAYMENT_PENDING") {
    return {
      title: "Ready for payment",
      body: "The insurer has accepted the loss. Confirm who was paid, then record the payout.",
    };
  }
  if (key === "PAYMENT_AUTHORIZATION" || key === "PAYMENT_REVIEW") {
    return {
      title: "Payment needs authorization",
      body: "Review the instruction and authorize payment if the amount and beneficiary are correct.",
    };
  }
  if (key === "PAYMENT_AUTHORIZED" || key === "PAYMENT_PROCESSING") {
    return {
      title: "Payment in flight",
      body: "The instruction has been sent. Complete or retry if the provider reports a failure.",
    };
  }
  if (key === "PAYMENT_COMPLETED" || key === "CLIENT_NOTIFIED") {
    return {
      title: "Settlement complete",
      body: "Payment has gone through. Close the file when the client has been informed.",
    };
  }
  if (["VETTING_FAILED", "REJECTED", "DEFINITE_REJECTED", "CANCELLED", "WITHDRAWN", "CLOSED"].includes(key)) {
    return {
      title: "This file is closed",
      body: "No further desk action is required unless a supervisor reopens it.",
    };
  }
  return {
    title: claimStatusLabel(status),
    body: "Review the file and take the next permitted action.",
  };
}

export type DeskStepId = "assign" | "assess" | "decide" | "settle" | "close";
export type DeskStepState = "done" | "current" | "wait";

export type DeskStep = {
  id: DeskStepId;
  n: number;
  label: string;
  state: DeskStepState;
};

const DESK_ORDER: DeskStepId[] = ["assign", "assess", "decide", "settle", "close"];

export function claimDeskProgress(status: string, assigned: boolean): {
  current: DeskStepId;
  steps: DeskStep[];
} {
  const key = status.trim().toUpperCase();
  let current: DeskStepId = "assign";
  if (["CLOSED", "CLIENT_NOTIFIED", "VETTING_FAILED", "REJECTED", "DEFINITE_REJECTED", "CANCELLED", "WITHDRAWN"].includes(key)) {
    current = "close";
  } else if (
    [
      "SENT_TO_DEFINITE",
      "DEFINITE_REVIEW",
      "DEFINITE_APPROVED",
      "PAYMENT_PENDING",
      "PAYMENT_AUTHORIZATION",
      "PAYMENT_AUTHORIZED",
      "PAYMENT_PROCESSING",
      "PAYMENT_COMPLETED",
      "PAYMENT_FAILED",
      "PAYMENT_REVIEW",
    ].includes(key)
  ) {
    current = "settle";
  } else if (key === "VETTING_PASSED") {
    current = "decide";
  } else if (["VETTING", "ADDITIONAL_INFORMATION_REQUIRED"].includes(key)) {
    current = "assess";
  } else if (key === "CLAIM_SUBMITTED") {
    current = assigned ? "assess" : "assign";
  } else if (key === "CLAIM_DRAFT") {
    current = "assign";
  }

  const idx = DESK_ORDER.indexOf(current);
  const base: Array<Omit<DeskStep, "state">> = [
    { id: "assign", n: 1, label: "Assign" },
    { id: "assess", n: 2, label: "Assess" },
    { id: "decide", n: 3, label: "Decide" },
    { id: "settle", n: 4, label: "Settle" },
    { id: "close", n: 5, label: "Close" },
  ];
  return {
    current,
    steps: base.map((step, index): DeskStep => ({
      ...step,
      state: index < idx ? "done" : index === idx ? "current" : "wait",
    })),
  };
}

export function actorRoleLabel(role?: string | null) {
  const key = (role || "").trim().toLowerCase().replace(/_/g, " ");
  if (key === "guest") return "Client";
  if (key === "platform admin") return "Platform admin";
  if (!key) return "";
  return key.replace(/\b\w/g, (c) => c.toUpperCase());
}

const ACTIVITY_TITLES: Record<string, string> = {
  CLAIM_CREATED: "Opened the file",
  CLAIM_OPENED: "Viewed the file",
  CLAIM_SUBMITTED: "Submitted for assessment",
  CLAIM_ASSIGNED: "Assigned the file",
  VETTING_STARTED: "Started assessment",
  VETTING_PASSED: "Passed assessment",
  VETTING_FAILED: "Failed assessment",
  VETTING_COMPLETED: "Asked for more information",
  FOLLOWUP_CREATED: "Added a task",
  FOLLOWUP_COMPLETED: "Completed a task",
  DOCUMENT_UPLOADED: "Uploaded a document",
  DOCUMENT_DOWNLOADED: "Downloaded a document",
  CLAIM_PDF_OPENED: "Opened the claim PDF",
  CLAIM_PDF_DOWNLOADED: "Downloaded the claim PDF",
  CLAIM_FORWARDED_TO_DEFINITE: "Sent to the insurer",
  DEFINITE_RESPONSE_RECEIVED: "Insurer replied",
  CLAIM_APPROVED: "Approved",
  CLAIM_REJECTED: "Declined",
  PAYMENT_INITIATED: "Started payment",
  PAYMENT_AUTHORIZED: "Authorized payment",
  PAYMENT_COMPLETED: "Paid",
  PAYMENT_FAILED: "Payment failed",
  CLAIM_CLOSED: "Closed the file",
  CLIENT_NOTIFIED: "Notified the client",
};

const EDITED_TITLES: Record<string, string> = {
  "added an internal note": "Added a note",
  "updated claim details": "Updated the file",
  "withdrew claim": "Withdrew the file",
};

export function activityCopy(event: { action?: string | null; summary?: string | null }) {
  const action = (event.action || "").toUpperCase();
  const summary = (event.summary || "").trim();
  const key = summary.toLowerCase();

  if (action === "CLAIM_EDITED") {
    if (EDITED_TITLES[key]) return { title: EDITED_TITLES[key], detail: "" };
    if (key.startsWith("requested amendment")) {
      return { title: "Requested an amendment", detail: summary.replace(/^Requested amendment to /i, "") };
    }
    return { title: summary || "Updated the file", detail: "" };
  }
  if (action === "DOCUMENT_UPLOADED" && key.startsWith("removed document")) {
    return { title: "Removed a document", detail: summary.replace(/^Removed document /i, "") };
  }
  if (action === "FOLLOWUP_CREATED" && key === "client sent a follow-up") {
    return { title: "Client sent a follow-up", detail: "" };
  }
  if (action === "CLAIM_SUBMITTED" && key.includes("welcome screen")) {
    return { title: "Filed from the welcome screen", detail: "" };
  }

  const title = ACTIVITY_TITLES[action] || prettyCode(action) || summary || "Update";
  let detail = "";
  if (["DOCUMENT_UPLOADED", "DOCUMENT_DOWNLOADED", "FOLLOWUP_CREATED", "FOLLOWUP_COMPLETED"].includes(action)) {
    detail = summary;
  } else if (
    action === "CLAIM_CREATED" ||
    action === "CLAIM_OPENED" ||
    action === "CLAIM_PDF_OPENED" ||
    action === "CLAIM_PDF_DOWNLOADED"
  ) {
    detail = summary.match(/CLM-\S+/)?.[0] || "";
  } else if (action === "CLAIM_ASSIGNED") {
    detail = summary.replace(/^Assigned claim to /i, "");
  } else if (action === "CLIENT_NOTIFIED" || action === "DEFINITE_RESPONSE_RECEIVED") {
    if (key && key !== title.toLowerCase()) detail = summary;
  }
  if (detail && detail.toLowerCase() === title.toLowerCase()) detail = "";
  return { title, detail };
}

const ACTIVITY_TONES: Record<string, StatusBadgeTone> = {
  CLAIM_REJECTED: "danger",
  VETTING_FAILED: "danger",
  PAYMENT_FAILED: "danger",
  CLAIM_APPROVED: "success",
  VETTING_PASSED: "success",
  PAYMENT_COMPLETED: "success",
  PAYMENT_AUTHORIZED: "success",
  FOLLOWUP_COMPLETED: "success",
  CLAIM_CLOSED: "closed",
  CLIENT_NOTIFIED: "closed",
  VETTING_COMPLETED: "warning",
  CLAIM_CREATED: "draft",
  CLAIM_OPENED: "draft",
  CLAIM_SUBMITTED: "pending",
  CLAIM_ASSIGNED: "pending",
  VETTING_STARTED: "pending",
  CLAIM_FORWARDED_TO_DEFINITE: "pending",
  DEFINITE_RESPONSE_RECEIVED: "pending",
  PAYMENT_INITIATED: "pending",
  DOCUMENT_UPLOADED: "draft",
  DOCUMENT_DOWNLOADED: "draft",
  CLAIM_PDF_OPENED: "draft",
  CLAIM_PDF_DOWNLOADED: "draft",
  CLAIM_EDITED: "draft",
};

export function activityBadgeTone(event: { action?: string | null; summary?: string | null }): StatusBadgeTone {
  const action = (event.action || "").toUpperCase();
  const { title } = activityCopy(event);
  if (action === "CLAIM_EDITED" && /withdrew/i.test(title)) return "danger";
  if (action === "FOLLOWUP_CREATED") {
    return /client sent/i.test(title) ? "warning" : "pending";
  }
  return ACTIVITY_TONES[action] ?? statusBadgeTone(title);
}

export function activityActor(event: { actor_display_name?: string | null; actor_type?: string | null }) {
  const name = (event.actor_display_name || "").trim();
  return name || prettyCode(event.actor_type) || "System";
}

export function vettingDecisionLabel(decision?: string | null) {
  const key = (decision || "").toUpperCase();
  if (key === "PASS") return "Passed";
  if (key === "FAIL") return "Failed";
  if (key === "MORE_INFORMATION_REQUIRED") return "More information needed";
  if (!decision) return "Started";
  return prettyCode(decision);
}

export type StatusBadgeTone = "success" | "pending" | "warning" | "danger" | "closed" | "draft";

export function statusBadgeTone(status: string): StatusBadgeTone {
  const key = status.trim().toUpperCase().replace(/[\s-]+/g, "_");
  if (
    [
      "CLOSED",
      "EXPIRED",
      "REVOKED",
      "COMPLETE",
      "COMPLETED",
      "DONE",
      "CLIENT_NOTIFIED",
    ].includes(key)
  ) {
    return "closed";
  }
  if (
    [
      "REJECTED",
      "DECLINED",
      "FAILED",
      "CANCELLED",
      "CANCELED",
      "WITHDRAWN",
      "VETTING_FAILED",
      "DEFINITE_REJECTED",
      "PAYMENT_FAILED",
      "OVERDUE",
    ].includes(key) ||
    key.includes("REJECT") ||
    key.includes("DECLIN") ||
    key.includes("FAIL")
  ) {
    return "danger";
  }
  if (
    [
      "APPROVED",
      "CONVERTED",
      "SUCCESS",
      "ACTIVE",
      "GENERATED",
      "PAID",
      "PAYMENT_COMPLETED",
      "DEFINITE_APPROVED",
      "VETTING_PASSED",
    ].includes(key)
  ) {
    return "success";
  }
  if (
    [
      "ADDITIONAL_INFORMATION_REQUIRED",
      "PAYMENT_REVIEW",
      "DUE_SOON",
      "WARNING",
    ].includes(key)
  ) {
    return "warning";
  }
  if (["DRAFT", "CLAIM_DRAFT", "OPEN"].includes(key)) return "draft";
  return "pending";
}

export function statusBadgeClass(status: string) {
  return `ov-status ov-status--${statusBadgeTone(status)}`;
}

export function claimStatusTone(status: string) {
  const tone = statusBadgeTone(status);
  if (tone === "success") return "active";
  if (tone === "danger") return "inactive";
  if (tone === "warning" || tone === "pending") return "pending";
  if (tone === "closed") return "closed";
  return "neutral";
}

export function payToLabel(type?: string | null) {
  if (type === "CLIENT") return "Policyholder";
  if (type === "STAR_SERVE") return "Agency";
  return prettyCode(type);
}

export function payToExplain(type?: string | null) {
  if (type === "STAR_SERVE") return "Agency — insurer pays Star Serve, then the agency pays the client";
  if (type === "CLIENT") return "Policyholder — insurer pays the client directly";
  return prettyCode(type);
}

export function money(value: string | number | null | undefined, currency = "KES") {
  if (value == null || value === "") return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(n)) return String(value);
  return `${currency} ${n.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
}

export function formatDay(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function newestFirst<T>(rows: T[], key = "created_at") {
  return [...rows].sort((left, right) => {
    const a = Date.parse(String((left as Record<string, unknown>)[key] ?? "")) || 0;
    const b = Date.parse(String((right as Record<string, unknown>)[key] ?? "")) || 0;
    return b - a;
  });
}

export function prettyCode(value?: string | null) {
  if (!value) return "—";
  return value.replace(/_/g, " ").toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
}

export function followupTypeLabel(type?: string | null) {
  const key = (type || "").toUpperCase();
  if (key === "CLIENT_INFORMATION") return "Client follow-up";
  if (key === "DOCUMENT_REQUIRED") return "Document required";
  if (key === "MEDICAL_INFORMATION") return "Medical information";
  if (key === "POLICE_DOCUMENT") return "Police abstract";
  if (key === "PAYMENT_INFORMATION") return "Payment information";
  if (key === "INTERNAL_REVIEW") return "Internal review";
  return prettyCode(type);
}

export function followupStatusLabel(status?: string | null) {
  const key = (status || "").toUpperCase();
  if (key === "PENDING_INTERNAL") return "Waiting on the desk";
  if (key === "PENDING_CLIENT") return "Waiting on the client";
  if (key === "OPEN") return "Open";
  if (key === "COMPLETED") return "Done";
  return prettyCode(status);
}

export function claimSourceLabel(channel?: string | null) {
  if (channel === "GUEST") return "Guest report";
  if (channel === "CLIENT") return "Client portal";
  return "Staff report";
}

export function vettingCheckLabel(key: string) {
  const labels: Record<string, string> = {
    claimant_verified: "Claimant matches the policy",
    policy_active_at_incident: "Policy was in force on the incident date",
    coverage_confirmed: "This loss is covered",
    documents_complete: "Required documents are on file",
    accident_details_consistent: "Accident details are consistent",
    no_unresolved_followups: "No open tasks left",
  };
  return labels[key] || prettyCode(key);
}

export type ClaimNoticeTone = "wait" | "stop" | "info";

export type ClaimNoticeCopy = {
  title: string;
  body: string;
  tone: ClaimNoticeTone;
};

export function explainClaimError(message: string | null | undefined): ClaimNoticeCopy | null {
  const raw = (message || "").trim();
  if (!raw) return null;
  const text = raw.toLowerCase();

  if (text.includes("second distinct approver") || text.includes("already approved")) {
    return {
      title: "You already signed this",
      body: "Another officer still needs to approve.",
      tone: "wait",
    };
  }
  if (text.includes("must be assigned")) {
    return {
      title: "This file needs an owner",
      body: "Assign the claim to an officer before that action can run.",
      tone: "wait",
    };
  }
  if (text.includes("updated by someone else") || text.includes("reload and try again")) {
    return {
      title: "The file changed",
      body: "Someone else updated this claim. Reload, then try again.",
      tone: "info",
    };
  }
  if (text.includes("closed to further")) {
    return {
      title: "This file is closed",
      body: "No further changes can be made on a finished claim.",
      tone: "stop",
    };
  }
  if (text.includes("segregation of duties")) {
    return {
      title: "A different officer is required",
      body: "You already completed a conflicting step on this file. Another officer needs to continue.",
      tone: "wait",
    };
  }
  if (text.includes("assignee is not a member")) {
    return {
      title: "That officer cannot take this file",
      body: "Pick someone who belongs to the same agency as the claim.",
      tone: "stop",
    };
  }
  if (text.includes("not ready for vetting") || text.includes("only available after vetting")) {
    return {
      title: "This step is not open yet",
      body: "Finish the current desk step first, then try again.",
      tone: "wait",
    };
  }
  if (text.includes("outside your approval authority")) {
    return {
      title: "This amount is outside your authority",
      body: "A supervisor with a higher limit needs to approve this file.",
      tone: "wait",
    };
  }
  if (text.includes("claims can only be opened against an active policy")) {
    return {
      title: "Cover is not active",
      body: "A claim can only be opened on a paid, active policy.",
      tone: "stop",
    };
  }

  return { title: "Couldn't complete that", body: raw, tone: "stop" };
}

export function formatWhen(value?: string | null) {
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

export function formatClock(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}
