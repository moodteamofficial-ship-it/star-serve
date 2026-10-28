import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { IconChevronLeft, IconSearch } from "@/components/ui/icons";
import { DateField } from "@/components/ui/DateField";
import { claimApi } from "@/services/claims/claimApi";
import { policyApi, type Policy } from "@/services/policies/policyApi";
import { ClaimNotice } from "@/features/claims/ClaimNotice";
import { prettyCode } from "@/features/claims/status";

function Fact({ label, value }: { label: string; value?: ReactNode }) {
  const empty = value == null || value === "";
  return (
    <div className={`claims-fact${empty ? " is-empty" : ""}`}>
      <dt>{label}</dt>
      <dd>
        <strong>{empty ? "—" : value}</strong>
      </dd>
    </div>
  );
}

function policyLine(policy: Policy) {
  const vehicle = [policy.vehicle_make, policy.vehicle_model].filter(Boolean).join(" ");
  return [policy.vehicle_registration, vehicle || null, policyStatusLabel(policy.status)]
    .filter(Boolean)
    .join(" · ");
}

function policyStatusLabel(status: string) {
  if (status === "ACTIVE") return "Active";
  if (status === "PENDING_PAYMENT") return "Unpaid";
  if (status === "PENDING_CERTIFICATE") return "Awaiting certificate";
  if (status === "CANCELLED") return "Cancelled";
  if (status === "EXPIRED") return "Expired";
  return prettyCode(status);
}

export function NewClaimPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [policyId, setPolicyId] = useState("");
  const [selected, setSelected] = useState<Policy | null>(null);
  const [draft, setDraft] = useState("");
  const [q, setQ] = useState("");
  const [incidentDate, setIncidentDate] = useState("");
  const [location, setLocation] = useState("");
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setQ(draft.trim()), 280);
    return () => window.clearTimeout(timer);
  }, [draft]);

  const ready = q.length >= 4;
  const policies = useQuery({
    queryKey: ["policies-claim-search", q],
    queryFn: async () => (await policyApi.list({ q, limit: 20 })).data,
    enabled: ready,
  });

  const items = ready ? (policies.data?.items ?? []) : [];
  const cover = selected ? [selected.product_code, selected.cover_option].filter(Boolean).join(" · ") : "";
  const vehicle = selected ? [selected.vehicle_make, selected.vehicle_model].filter(Boolean).join(" ") : "";

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!policyId) {
      setError("Pick the active policy this loss sits on.");
      return;
    }
    setSaving(true);
    try {
      const created = await claimApi.create({
        policy_id: policyId,
        incident_date: incidentDate || null,
        incident_location: location || null,
        incident_description: description || null,
        claimed_amount: amount || "0",
      });
      queryClient.setQueryData(["claim", created.data.id], created.data);
      void queryClient.invalidateQueries({ queryKey: ["claims"] });
      void queryClient.invalidateQueries({ queryKey: ["claims-dashboard"] });
      navigate(`/app/claims/${created.data.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not open the claim");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="config-page customers-page claims-page claims-detail-page claims-new-page">
      <Link to="/app/claims" className="claims-back" aria-label="Back to claims">
        <IconChevronLeft strokeWidth={2.6} />
      </Link>

      <header className="claims-hero">
        <div className="claims-hero-head">
          <div className="claims-hero-copy">
            <p className="customers-stat-label">Claim</p>
            <h1>Open a claim</h1>
            <p className="claims-hero-ref">Starts as a draft</p>
          </div>
          <div className="claims-hero-side">
            <span className="customers-status-dot customers-status-dot--pending">
              <span className="customers-status-dot__mark" aria-hidden="true" />
              Draft
            </span>
          </div>
        </div>
      </header>

      <form className={`claims-panel claims-new${saving ? " is-busy" : ""}`} onSubmit={onSubmit} aria-busy={saving}>
        {saving ? <p className="claims-work-busy">Saving…</p> : null}

        <section className="claims-new-block">
          <header className="claims-file-head">
            <p className="customers-stat-label">Policy</p>
            <h2>Find the cover</h2>
            <p>Search plate, policy number, certificate, or name. Then pick an active policy.</p>
          </header>
          <div className="claims-new-body">
            <label className="claims-reason-field">
              Find policy
              <span className="claims-new-search">
                <IconSearch />
                <input
                  type="search"
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") event.preventDefault();
                  }}
                  placeholder="KDV345L, POL-…, certificate, or name"
                  autoComplete="off"
                />
              </span>
            </label>

            {!ready ? null : policies.isError ? (
              <p className="claims-quiet">Could not search policies. Try again.</p>
            ) : policies.isFetching && !policies.data ? (
              <p className="claims-quiet">Looking up policies…</p>
            ) : items.length === 0 ? (
              <p className="claims-quiet">Nothing matches that search.</p>
            ) : (
              <ul className="claims-work-list claims-policy-list">
                {items.map((policy) => {
                  const active = policy.status === "ACTIVE";
                  return (
                    <li key={policy.id}>
                      <button
                        type="button"
                        className={`${policy.id === policyId ? "is-selected" : ""}${active ? "" : " is-inactive"}`}
                        disabled={!active}
                        onClick={() => {
                          setPolicyId(policy.id);
                          setSelected(policy);
                        }}
                      >
                        <strong>{policy.policy_number}</strong>
                        <p>{policyLine(policy)}</p>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}

            {selected ? (
              <dl className="claims-new-pick">
                <Fact label="Policy" value={selected.policy_number} />
                <Fact label="Cover" value={cover || prettyCode(selected.status)} />
                <Fact
                  label="Vehicle"
                  value={[vehicle, selected.vehicle_registration].filter(Boolean).join(" · ")}
                />
              </dl>
            ) : null}
          </div>
        </section>

        <section className="claims-new-block">
          <header className="claims-file-head">
            <p className="customers-stat-label">Incident</p>
            <h2>What happened</h2>
            <p>Add what you know now. You can finish the rest on the file.</p>
          </header>
          <div className="claims-new-body">
            <div className="claims-new-grid">
              <DateField
                label="Incident date"
                value={incidentDate}
                onChange={setIncidentDate}
                fieldClassName="claims-reason-field"
                max={new Date().toISOString().slice(0, 10)}
              />
              <label className="claims-reason-field">
                Location
                <input
                  value={location}
                  onChange={(event) => setLocation(event.target.value)}
                  placeholder="Where it happened"
                />
              </label>
              <label className="claims-reason-field">
                Claimed amount
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={amount}
                  onChange={(event) => setAmount(event.target.value)}
                  placeholder="KES"
                />
              </label>
              <label className="claims-reason-field claims-reason-field--wide">
                Description
                <textarea
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  rows={4}
                  placeholder="Short account of the accident"
                />
              </label>
            </div>
          </div>
        </section>

        <div className="claims-new-foot">
          <ClaimNotice message={error} />
          <div className="claims-next-actions">
            <button type="button" className="config-btn config-btn--ghost" onClick={() => navigate("/app/claims")}>
              Cancel
            </button>
            <button type="submit" className="config-btn" disabled={saving || !policyId}>
              {saving ? "Saving…" : "Create draft"}
            </button>
          </div>
        </div>
      </form>
    </section>
  );
}
