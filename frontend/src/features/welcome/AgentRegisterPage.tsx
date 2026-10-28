import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { FormError } from "@/components/ui/FormError";
import { PhoneField } from "@/components/ui/PhoneField";
import { DEFAULT_PHONE_COUNTRY, toE164 } from "@/components/ui/phoneCountries";
import { TextField } from "@/components/ui/TextField";
import { IconCheckCircle, IconUsers } from "@/components/ui/icons";
import { WelcomeClaimModals, useGuestAgency } from "@/features/welcome/WelcomeClaimModals";
import { WelcomeTopbar } from "@/features/welcome/WelcomeTopbar";
import { ApiError } from "@/services/api/client";
import { passwordStrengthError } from "@/services/auth/passwordPolicy";
import { guestAgentApplyApi } from "@/services/intermediaries/guestAgentApplyApi";

const EMPTY_FORM = {
  name: "",
  email: "",
  phone: "",
  identification: "",
  agent_code: "",
  kra_pin: "",
  password: "",
  website: "",
};

/** Public agent self-registration. Submissions stay PENDING until an admin approves. */
export function AgentRegisterPage() {
  const navigate = useNavigate();
  const agency = useGuestAgency();
  const [claimMode, setClaimMode] = useState<"claim" | "followup" | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [phoneCountry, setPhoneCountry] = useState(DEFAULT_PHONE_COUNTRY);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);

  function update<K extends keyof typeof EMPTY_FORM>(key: K, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const phone = toE164(phoneCountry, form.phone);
    if (!phone) {
      setError("Enter a valid phone number.");
      return;
    }
    const agentCode = form.agent_code.trim();
    if (agentCode && !/^\d{6}$/.test(agentCode)) {
      setError("Agent code must be exactly 6 digits, or leave it blank to auto-generate.");
      return;
    }
    const passwordError = passwordStrengthError(form.password);
    if (passwordError) {
      setError(passwordError);
      return;
    }
    if (!agency.tenantId) {
      setError("The agency is still loading. Please try again in a moment.");
      return;
    }
    setSaving(true);
    try {
      await guestAgentApplyApi.apply(agency.tenantId, {
        name: form.name.trim(),
        email: form.email.trim(),
        phone,
        identification: form.identification.trim(),
        agent_code: agentCode || undefined,
        kra_pin: form.kra_pin.trim() || undefined,
        password: form.password,
        website: form.website || undefined,
      });
      setSubmitted(true);
      setForm(EMPTY_FORM);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="welcome-shell">
      <WelcomeTopbar
        onReportClaim={() => setClaimMode("claim")}
        onFollowUp={() => setClaimMode("followup")}
      />
      <main className="content welcome-content agent-register">
        <header className="welcome-hero">
          <h1 className="welcome-hero-title welcome-hero-title--compact">
            Become a <span className="welcome-hero-accent">Star Serve</span> agent
          </h1>
          <p className="welcome-hero-subtitle">
            Share your details and our team will review your application.
          </p>
        </header>

        <section className="agent-register-card" aria-live="polite">
          {submitted ? (
            <div className="agent-register-done">
              <span className="agent-register-done-icon" aria-hidden="true">
                <IconCheckCircle />
              </span>
              <h2>Application received</h2>
              <p>
                An admin will review your details. Once you are approved, we will share your agent
                code and QR so customers can quote through you.
              </p>
              <div className="agent-register-actions">
                <Link to="/" className="welcome-action welcome-action--primary">
                  Back to home
                </Link>
              </div>
            </div>
          ) : (
            <>
              <div className="agent-register-head">
                <span className="agent-register-head-icon" aria-hidden="true">
                  <IconUsers />
                </span>
                <div>
                  <h2>Register agent</h2>
                  <p>Your details and a login password.</p>
                </div>
              </div>
              <form className="form-grid modal-form-grid agent-register-form" onSubmit={onSubmit}>
                <TextField
                  label="Name"
                  required
                  autoComplete="name"
                  maxLength={255}
                  value={form.name}
                  onChange={(e) => update("name", e.target.value)}
                />
                <TextField
                  label="Email"
                  type="email"
                  required
                  autoComplete="email"
                  maxLength={255}
                  value={form.email}
                  onChange={(e) => update("email", e.target.value)}
                />
                <PhoneField
                  label="Phone"
                  value={form.phone}
                  onChange={(phone) => update("phone", phone)}
                  country={phoneCountry}
                  onCountryChange={setPhoneCountry}
                  autoComplete="tel"
                  required
                  fieldClassName="agent-register-wide"
                />
                <TextField
                  label="National ID/Passport"
                  required
                  minLength={5}
                  maxLength={64}
                  autoComplete="off"
                  value={form.identification}
                  onChange={(e) => update("identification", e.target.value)}
                />
                <TextField
                  label="Agent code"
                  inputMode="numeric"
                  pattern="[0-9]{6}"
                  maxLength={6}
                  autoComplete="off"
                  placeholder="Blank = auto-generate"
                  value={form.agent_code}
                  onChange={(e) => update("agent_code", e.target.value.replace(/\D/g, "").slice(0, 6))}
                />
                <TextField
                  label="KRA PIN"
                  maxLength={16}
                  autoComplete="off"
                  value={form.kra_pin}
                  onChange={(e) => update("kra_pin", e.target.value.toUpperCase())}
                />
                <TextField
                  label="Login password"
                  type="password"
                  required
                  minLength={6}
                  maxLength={128}
                  autoComplete="new-password"
                  value={form.password}
                  onChange={(e) => update("password", e.target.value)}
                />
                <p className="agent-register-hint agent-register-wide">
                  You sign in with your email and this password once your application is approved.
                </p>
                <div className="agent-register-trap" aria-hidden="true">
                  <label>
                    Website
                    <input
                      tabIndex={-1}
                      autoComplete="off"
                      value={form.website}
                      onChange={(e) => update("website", e.target.value)}
                    />
                  </label>
                </div>
                {error ? (
                  <div className="agent-register-wide">
                    <FormError title="Couldn’t register">{error}</FormError>
                  </div>
                ) : null}
                <div className="agent-register-actions agent-register-wide">
                  <button type="button" className="secondary" onClick={() => navigate("/")}>
                    Cancel
                  </button>
                  <button type="submit" disabled={saving}>
                    {saving ? "Submitting…" : "Create"}
                  </button>
                </div>
              </form>
            </>
          )}
        </section>
      </main>
      <WelcomeClaimModals mode={claimMode} onClose={() => setClaimMode(null)} />
    </div>
  );
}
