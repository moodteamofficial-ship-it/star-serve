import { useState } from "react";
import { ApiError } from "@/services/api/client";
import { websiteApi } from "@/services/website/websiteApi";

export function EnquiryForm() {
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [coverNeeded, setCoverNeeded] = useState("");
  const [message, setMessage] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "ok" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setStatus("loading");
    setError(null);
    try {
      await websiteApi.submitEnquiry({
        full_name: fullName,
        phone,
        email: email || undefined,
        cover_needed: coverNeeded || undefined,
        message: message || undefined,
      });
      setStatus("ok");
      setFullName("");
      setPhone("");
      setEmail("");
      setCoverNeeded("");
      setMessage("");
    } catch (err) {
      setStatus("error");
      setError(err instanceof ApiError ? err.message : "Could not send enquiry");
    }
  }

  return (
    <form className="mkt-enquiry" onSubmit={onSubmit}>
      <h2 className="mkt-section-title">Request a callback</h2>
      <label>
        Full name
        <input required value={fullName} onChange={(e) => setFullName(e.target.value)} />
      </label>
      <label>
        Phone
        <input required value={phone} onChange={(e) => setPhone(e.target.value)} />
      </label>
      <label>
        Email
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      </label>
      <label>
        Cover needed
        <input value={coverNeeded} onChange={(e) => setCoverNeeded(e.target.value)} />
      </label>
      <label>
        Message
        <textarea rows={4} value={message} onChange={(e) => setMessage(e.target.value)} />
      </label>
      <input type="text" name="website" className="mkt-honeypot" tabIndex={-1} autoComplete="off" />
      <button type="submit" className="mkt-btn mkt-btn-primary" disabled={status === "loading"}>
        {status === "loading" ? "Sending…" : "Send enquiry"}
      </button>
      {status === "ok" ? <p className="mkt-success">Thank you — we will be in touch soon.</p> : null}
      {error ? <p className="mkt-error">{error}</p> : null}
    </form>
  );
}
