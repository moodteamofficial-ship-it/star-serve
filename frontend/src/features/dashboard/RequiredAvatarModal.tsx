import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useAuth } from "@/app/providers/AuthProvider";
import { Modal } from "@/components/ui/Modal";
import { authApi } from "@/services/auth/authApi";
import { notifySessionUser } from "@/services/auth/sessionBridge";

const MAX_BYTES = 10 * 1024 * 1024;
const ACCEPT = "image/jpeg,image/png,image/webp";

function hasAvatar(url: string | null | undefined): boolean {
  return Boolean(url && url.trim());
}

function initialsFrom(name: string | undefined, email: string | undefined): string {
  const source = (name || email || "SS").trim();
  const parts = source.split(/\s+/);
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  return source.slice(0, 2).toUpperCase();
}

/**
 * Non-dismissible gate on Overview — every staff user must set a profile photo.
 */
export function RequiredAvatarModal() {
  const { user, refreshUser } = useAuth();
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const previewUrlRef = useRef<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const needed = Boolean(user) && !hasAvatar(user?.avatar_url);
  const initials = useMemo(
    () => initialsFrom(user?.full_name, user?.email),
    [user?.full_name, user?.email],
  );
  const firstName = (user?.full_name || "").trim().split(/\s+/)[0] || "there";

  useEffect(() => {
    return () => {
      if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    };
  }, []);

  function clearPreview() {
    if (previewUrlRef.current) {
      URL.revokeObjectURL(previewUrlRef.current);
      previewUrlRef.current = null;
    }
    setPreviewUrl(null);
    setFile(null);
  }

  function takeFile(next: File | null | undefined) {
    setError(null);
    if (!next) return;
    if (!ACCEPT.split(",").includes(next.type) && !/\.(jpe?g|png|webp)$/i.test(next.name)) {
      setError("Use a JPEG, PNG, or WebP image.");
      return;
    }
    if (next.size > MAX_BYTES) {
      setError("Keep the photo under 10 MB.");
      return;
    }
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    const url = URL.createObjectURL(next);
    previewUrlRef.current = url;
    setPreviewUrl(url);
    setFile(next);
  }

  async function save() {
    if (!file || busy) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await authApi.uploadAvatar(file);
      notifySessionUser(updated);
      await refreshUser();
      clearPreview();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save your profile photo.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={needed}
      dismissible={false}
      title="Add a profile photo"
      subtitle={`Hi ${firstName}. Choose a clear photo so your team can recognise you.`}
      onClose={() => undefined}
      size="lg"
      bodyClassName="modal-body--avatar-setup"
      footer={
        <button type="button" disabled={!file || busy} onClick={() => void save()}>
          {busy ? "Saving…" : "Continue"}
        </button>
      }
    >
      <div className="avatar-setup">
        <label htmlFor={inputId} className={`avatar-setup-drop${previewUrl ? " has-preview" : ""}`}>
          <input
            ref={inputRef}
            id={inputId}
            type="file"
            accept={ACCEPT}
            className="avatar-setup-input"
            onChange={(e) => takeFile(e.target.files?.[0])}
          />
          <span className="avatar-setup-ring" aria-hidden="true">
            {previewUrl ? (
              <img src={previewUrl} alt="" className="avatar-setup-preview" />
            ) : (
              <span className="avatar-setup-initials">{initials}</span>
            )}
          </span>
          <span className="avatar-setup-copy">
            <strong>{previewUrl ? "Change photo" : "Choose photo"}</strong>
            <span>JPEG, PNG, or WebP · max 10 MB</span>
          </span>
        </label>
        {error ? (
          <p className="form-error avatar-setup-error" role="alert">
            {error}
          </p>
        ) : (
          <p className="avatar-setup-hint">Required — this step can’t be skipped.</p>
        )}
      </div>
    </Modal>
  );
}
