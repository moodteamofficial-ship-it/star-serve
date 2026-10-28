import { useEffect, useRef, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Field } from "@/components/ui/Field";
import { FormError } from "@/components/ui/FormError";
import { Modal } from "@/components/ui/Modal";
import { PhoneField } from "@/components/ui/PhoneField";
import { DateField } from "@/components/ui/DateField";
import { TextField } from "@/components/ui/TextField";
import { DEFAULT_PHONE_COUNTRY, toE164 } from "@/components/ui/phoneCountries";
import { IconCheckCircle, IconClaim, IconFollowUp } from "@/components/ui/icons";
import { ApiError } from "@/services/api/client";
import { guestClaimApi, type GuestClaimPublic } from "@/services/claims/guestClaimApi";
import { insuranceApi } from "@/services/insurance/insuranceApi";
import { GUEST_TENANTS_STALE_MS, readGuestTenantId, writeGuestTenantId } from "@/services/insurance/guestTenant";
import { scrollModalToIssue } from "@/utils/scrollModalToIssue";

type Props = {
  mode: "claim" | "followup" | null;
  onClose: () => void;
};

function fieldError(err: unknown) {
  return err instanceof ApiError ? err.message : "Something went wrong. Please try again.";
}

function guestStatusTone(status: string, needsInfo?: boolean) {
  if (needsInfo || /more information/i.test(status)) return "wait";
  if (/not approved|cancelled|withdrawn/i.test(status)) return "stop";
  if (/completed|closed|approved/i.test(status)) return "done";
  return "progress";
}

function guestStatusCopy(status: string, needsInfo?: boolean) {
  if (needsInfo || /more information/i.test(status)) {
    return "The agency has paused review until they have a little more from you. Send the details below.";
  }
  if (/received/i.test(status)) {
    return "Your report is with the agency. An officer will pick it up and check it against your policy.";
  }
  if (/under review/i.test(status)) {
    return "An officer is reviewing the details. They will contact you if anything is missing.";
  }
  if (/with the insurer/i.test(status)) {
    return "The agency has passed this to the insurer. You do not need to do anything unless they ask.";
  }
  if (/settlement|payment in progress/i.test(status)) {
    return "The claim has been approved and settlement is underway.";
  }
  if (/payment completed/i.test(status)) {
    return "Settlement is complete. Keep this claim number for your records.";
  }
  if (/payment being reviewed/i.test(status)) {
    return "Payment is being checked. The agency will update you when it is resolved.";
  }
  if (/not approved/i.test(status)) {
    return "This claim was not approved. Send a message if you need the agency to explain.";
  }
  if (/cancelled|withdrawn/i.test(status)) {
    return "This claim is no longer open.";
  }
  if (/closed/i.test(status)) {
    return "This claim has been closed. You can still send a message if you have a question.";
  }
  return "The agency has your claim and is working through it.";
}

function formatGuestDate(value: string | null | undefined) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(date);
}

function GuestClaimReceipt({ claim }: { claim: GuestClaimPublic }) {
  const [copied, setCopied] = useState(false);
  const copiedTimer = useRef<number>(0);
  const tone = guestStatusTone(claim.public_status, claim.needs_information);
  const facts = [
    { label: "Vehicle", value: claim.vehicle_registration },
    { label: "Incident", value: formatGuestDate(claim.incident_date) },
    { label: "Filed", value: formatGuestDate(claim.submitted_at) },
  ].filter((row): row is { label: string; value: string } => Boolean(row.value));

  useEffect(() => () => window.clearTimeout(copiedTimer.current), []);

  async function copyNumber() {
    try {
      await navigator.clipboard.writeText(claim.claim_number);
      setCopied(true);
      window.clearTimeout(copiedTimer.current);
      copiedTimer.current = window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="modal-cover welcome-claim-result" role="status">
      <section className="welcome-claim-result-panel">
        <div className="welcome-claim-result-ref">
          <div className="welcome-claim-result-ref-main">
            <p className="welcome-claim-agency-kicker">Claim number</p>
            <p className="welcome-claim-result-number">{claim.claim_number}</p>
          </div>
          <div className="welcome-claim-result-ref-side">
            <span className={`welcome-claim-pill welcome-claim-pill--${tone}`}>
              {claim.public_status}
            </span>
            <button
              type="button"
              className={`welcome-claim-copy${copied ? " is-copied" : ""}`}
              onClick={copyNumber}
              aria-label={copied ? "Claim number copied" : "Copy claim number"}
            >
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
        </div>
        {facts.length ? (
          <dl className="welcome-claim-result-facts">
            {facts.map((row) => (
              <div key={row.label}>
                <dt>{row.label}</dt>
                <dd>{row.value}</dd>
              </div>
            ))}
          </dl>
        ) : null}
      </section>

      <section className="welcome-claim-result-next">
        <h3>What happens next</h3>
        <ol>
          <li>An officer reviews your report against the policy on file.</li>
          <li>You will be contacted only if more information is needed.</li>
          <li>Use Follow up on this page with the claim number above.</li>
        </ol>
      </section>
    </div>
  );
}

function GuestClaimSummary({ claim }: { claim: GuestClaimPublic }) {
  const tone = guestStatusTone(claim.public_status, claim.needs_information);
  const journey = claim.journey;
  const facts = [
    claim.vehicle_registration,
    formatGuestDate(claim.incident_date) ? `Incident ${formatGuestDate(claim.incident_date)}` : null,
    formatGuestDate(claim.submitted_at) ? `Filed ${formatGuestDate(claim.submitted_at)}` : null,
  ].filter(Boolean);

  return (
    <article className="welcome-claim-file">
      <header className="welcome-claim-file-head">
        <p className="welcome-claim-status-kicker">Your claim</p>
        <div className="welcome-claim-status-title">
          <strong>{claim.claim_number}</strong>
          <span className={`welcome-claim-pill welcome-claim-pill--${tone}`}>
            {claim.public_status}
          </span>
        </div>
        {facts.length ? (
          <p className="welcome-claim-status-meta">{facts.join(" · ")}</p>
        ) : null}
      </header>

      {journey?.steps?.length ? (
        <section className="welcome-claim-section">
          <h3>Progress</h3>
          <ol className="welcome-claim-steps" aria-label="Claim progress">
            {journey.steps.map((step, index) => (
              <li key={step.id} className={`welcome-claim-step is-${step.state}`}>
                <span>{step.state === "done" ? "✓" : step.state === "skip" ? "—" : index + 1}</span>
                <em>{step.label}</em>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      <section className="welcome-claim-section welcome-claim-now">
        <h3>Where things stand</h3>
        <p>{journey?.now || guestStatusCopy(claim.public_status, claim.needs_information)}</p>
        {journey?.waiting_label ? <p className="welcome-claim-waiting">{journey.waiting_label}</p> : null}
      </section>

      {journey?.done?.length || journey?.pending?.length ? (
        <div className="welcome-claim-split">
          {journey?.done?.length ? (
            <section className="welcome-claim-section welcome-claim-list">
              <h3>Done</h3>
              <ul>
                {journey.done.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </section>
          ) : null}
          {journey?.pending?.length ? (
            <section className="welcome-claim-section welcome-claim-list welcome-claim-list--pending">
              <h3>Still to come</h3>
              <ul>
                {journey.pending.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </section>
          ) : (
            <section className="welcome-claim-section welcome-claim-list welcome-claim-list--pending">
              <h3>Still to come</h3>
              <p className="welcome-claim-empty">Nothing further is waiting.</p>
            </section>
          )}
        </div>
      ) : null}

      <section className="welcome-claim-section welcome-claim-thread" aria-label="Notices">
        <h3>Notices</h3>
        {claim.messages?.length ? (
          <ol>
            {claim.messages.map((row) => (
              <li
                key={`${row.created_at}-${row.body}`}
                className={row.from === "agency" ? "is-agency" : "is-you"}
              >
                <div className="welcome-claim-thread-meta">
                  <span>{row.from === "agency" ? "Agency" : "You"}</span>
                  <time dateTime={row.created_at}>{formatGuestDate(row.created_at) ?? ""}</time>
                </div>
                <p>{row.body}</p>
              </li>
            ))}
          </ol>
        ) : (
          <p className="welcome-claim-empty">The agency has not sent a notice yet. Your updates will show here.</p>
        )}
      </section>
    </article>
  );
}

function SmoothError({ title, message }: { title: string; message: string | null }) {
  const [shown, setShown] = useState(message);

  useEffect(() => {
    if (message) setShown(message);
  }, [message]);

  return (
    <div className={`welcome-claim-error${message ? " is-open" : ""}`} aria-live="polite">
      <div className="welcome-claim-error-inner">
        {shown ? <FormError title={title}>{shown}</FormError> : null}
      </div>
    </div>
  );
}

export function useGuestAgency() {
  const [tenantId, setTenantId] = useState(readGuestTenantId);
  const tenants = useQuery({
    queryKey: ["guest-tenants"],
    queryFn: async () => (await insuranceApi.listGuestTenants()).data,
    staleTime: GUEST_TENANTS_STALE_MS,
  });

  useEffect(() => {
    const items = tenants.data?.items ?? [];
    if (!items.length) return;
    // Same default as the welcome quote flow: earliest agency in the DB.
    const first = items[0].id;
    if (tenantId === first) return;
    setTenantId(first);
    writeGuestTenantId(first);
  }, [tenants.data, tenantId]);

  return { tenantId, tenants };
}

export function WelcomeClaimModals({ mode, onClose }: Props) {
  return (
    <>
      <ReportClaimModal open={mode === "claim"} onClose={onClose} />
      <FollowUpModal open={mode === "followup"} onClose={onClose} />
    </>
  );
}

function ReportClaimModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const agency = useGuestAgency();
  const [policyNumber, setPolicyNumber] = useState("");
  const [registration, setRegistration] = useState("");
  const [idNumber, setIdNumber] = useState("");
  const [phone, setPhone] = useState("");
  const [phoneCountry, setPhoneCountry] = useState(DEFAULT_PHONE_COUNTRY);
  const [incidentDate, setIncidentDate] = useState("");
  const [location, setLocation] = useState("");
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GuestClaimPublic | null>(null);

  useEffect(() => {
    if (open) return;
    setResult(null);
    setError(null);
    setSaving(false);
  }, [open]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.checkValidity()) {
      scrollModalToIssue(form.closest(".modal-panel"));
      form.reportValidity();
      return;
    }
    if (!agency.tenantId) {
      setError("Choose the agency that issued the policy.");
      return;
    }
    setError(null);
    setSaving(true);
    try {
      const res = await guestClaimApi.file(agency.tenantId, {
        policy_number: policyNumber,
        vehicle_registration: registration,
        id_number: idNumber,
        phone: toE164(phoneCountry, phone) || phone,
        incident_date: incidentDate,
        incident_location: location,
        incident_description: description,
        claimed_amount: amount || "0",
      });
      setResult(res.data);
    } catch (err) {
      setError(fieldError(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={result ? "We've received your claim" : "Report a claim"}
      subtitle={
        result
          ? "An officer will review it against your policy and contact you if anything else is needed."
          : "Pick your agency and enter a policy or certificate number."
      }
      icon={result ? <IconCheckCircle /> : <IconClaim />}
      size="xl"
      panelClassName="welcome-type-scale"
      footer={
        result ? (
          <button type="button" onClick={onClose}>
            Done
          </button>
        ) : (
          <>
            <button type="button" className="secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" form="welcome-report-claim" disabled={saving || !agency.tenantId}>
              {saving ? "Submitting…" : "Submit claim"}
            </button>
          </>
        )
      }
    >
      {result ? (
        <GuestClaimReceipt claim={result} />
      ) : (
        <form id="welcome-report-claim" className="modal-cover" onSubmit={onSubmit}>
          <div className="form-grid modal-form-grid">
            <TextField
              label="Policy or certificate number"
              value={policyNumber}
              onChange={(e) => setPolicyNumber(e.target.value)}
              required
              autoComplete="off"
              placeholder="POL-…, NW…, or certificate number"
            />
            <TextField
              label="Vehicle registration"
              value={registration}
              onChange={(e) => setRegistration(e.target.value)}
              required
              autoComplete="off"
              placeholder="e.g. KDA 123A"
            />
            <TextField
              label="National ID"
              value={idNumber}
              onChange={(e) => setIdNumber(e.target.value)}
              required
              autoComplete="off"
            />
            <PhoneField
              label="Phone on the policy"
              value={phone}
              onChange={setPhone}
              country={phoneCountry}
              onCountryChange={setPhoneCountry}
              required
            />
            <DateField
              label="Incident date"
              value={incidentDate}
              onChange={setIncidentDate}
              required
              max={new Date().toISOString().slice(0, 10)}
            />
            <TextField
              label="Location"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              required
              placeholder="Where it happened"
            />
            <Field label="What happened" required className="welcome-claim-span">
              <textarea
                className="ui-input"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                required
                minLength={10}
                rows={4}
                placeholder="A short description of the incident"
              />
            </Field>
            <TextField
              label="Estimated amount (KES)"
              type="number"
              min="0"
              step="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="Optional"
              fieldClassName="welcome-claim-span"
            />
          </div>
          <SmoothError title="Could not submit claim" message={error} />
        </form>
      )}
    </Modal>
  );
}

function FollowUpModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const agency = useGuestAgency();
  const [claimNumber, setClaimNumber] = useState("");
  const [idNumber, setIdNumber] = useState("");
  const [phone, setPhone] = useState("");
  const [phoneCountry, setPhoneCountry] = useState(DEFAULT_PHONE_COUNTRY);
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [claim, setClaim] = useState<GuestClaimPublic | null>(null);

  useEffect(() => {
    if (open) return;
    setClaim(null);
    setError(null);
    setMessage("");
    setSaving(false);
  }, [open]);

  async function lookup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.checkValidity()) {
      scrollModalToIssue(form.closest(".modal-panel"));
      form.reportValidity();
      return;
    }
    if (!agency.tenantId) {
      setError("Choose the agency that issued the policy.");
      return;
    }
    setError(null);
    setSaving(true);
    try {
      const res = await guestClaimApi.lookup(agency.tenantId, {
        claim_number: claimNumber,
        id_number: idNumber,
        phone: toE164(phoneCountry, phone) || phone,
      });
      setClaim(res.data);
    } catch (err) {
      setError(fieldError(err));
    } finally {
      setSaving(false);
    }
  }

  async function sendFollowUp(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.checkValidity()) {
      scrollModalToIssue(form.closest(".modal-panel"));
      form.reportValidity();
      return;
    }
    if (!claim || !agency.tenantId) return;
    setError(null);
    setSaving(true);
    try {
      const res = await guestClaimApi.followUp(agency.tenantId, claim.id, message);
      setClaim(res.data);
      setMessage("");
    } catch (err) {
      setError(fieldError(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={claim ? "Your claim" : "Follow up a claim"}
      subtitle={
        claim
          ? "See where things stand, then send a note if you have an update."
          : "Pick your agency and enter your claim number."
      }
      icon={<IconFollowUp />}
      size="xl"
      panelClassName="welcome-type-scale"
      footer={
        !claim ? (
          <>
            <button type="button" className="secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" form="welcome-followup-lookup" disabled={saving || !agency.tenantId}>
              {saving ? "Checking…" : "Find claim"}
            </button>
          </>
        ) : (
          <>
            <button type="button" className="secondary" onClick={onClose}>
              Close
            </button>
            <button type="submit" form="welcome-followup-send" disabled={saving}>
              {saving ? "Sending…" : "Send follow-up"}
            </button>
          </>
        )
      }
    >
      {!claim ? (
        <form id="welcome-followup-lookup" className="modal-cover" onSubmit={lookup}>
          <div className="form-grid modal-form-grid">
            <TextField
              label="Claim number"
              value={claimNumber}
              onChange={(e) => setClaimNumber(e.target.value)}
              required
              autoComplete="off"
              placeholder="e.g. CLM-2026-AB12CD"
              fieldClassName="welcome-claim-span"
            />
          </div>
          <div className="form-grid modal-form-grid">
            <TextField
              label="National ID"
              value={idNumber}
              onChange={(e) => setIdNumber(e.target.value)}
              required
              autoComplete="off"
            />
            <PhoneField
              label="Phone on the policy"
              value={phone}
              onChange={setPhone}
              country={phoneCountry}
              onCountryChange={setPhoneCountry}
              required
            />
          </div>
          <SmoothError title="Could not find claim" message={error} />
        </form>
      ) : (
        <form id="welcome-followup-send" className="modal-cover welcome-claim-follow" onSubmit={sendFollowUp}>
          <GuestClaimSummary claim={claim} />
          <div className="form-grid modal-form-grid welcome-claim-compose">
            <Field
              label="Write to the agency"
              required
              className="welcome-claim-span"
              hint="A short update, question, or document reference."
            >
              <textarea
                className="ui-input"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                required
                minLength={3}
                rows={4}
                placeholder="Type your update…"
              />
            </Field>
          </div>
          <SmoothError title="Could not send follow-up" message={error} />
        </form>
      )}
    </Modal>
  );
}
