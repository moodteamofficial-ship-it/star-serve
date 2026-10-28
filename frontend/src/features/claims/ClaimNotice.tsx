import { useEffect, useState } from "react";
import { IconAlert, IconCheckCircle, IconWarning } from "@/components/ui/icons";
import {
  explainClaimError,
  type ClaimNoticeCopy,
  type ClaimNoticeTone,
} from "@/features/claims/status";

type Props = {
  message?: string | null;
  title?: string;
  tone?: ClaimNoticeTone;
};

export function ClaimNotice({ message, title, tone }: Props) {
  const explained: ClaimNoticeCopy | null = title
    ? { title, body: (message || "").trim(), tone: tone ?? "wait" }
    : explainClaimError(message);
  const [shown, setShown] = useState<ClaimNoticeCopy | null>(explained);

  useEffect(() => {
    if (explained) setShown(explained);
  }, [explained?.title, explained?.body, explained?.tone]);

  const open = Boolean(explained);
  const copy = shown;
  const kind = copy?.tone ?? "info";
  const Icon = kind === "wait" ? IconCheckCircle : kind === "info" ? IconWarning : IconAlert;

  return (
    <div className={`claims-notice-slot${open ? " is-open" : ""}`} aria-live="polite">
      <div className="claims-notice-slot-inner">
        {copy ? (
          <div className={`claims-notice is-${copy.tone}`} role="status">
            <span className="claims-notice-icon" aria-hidden="true">
              <Icon />
            </span>
            <div className="claims-notice-copy">
              <strong>{copy.title}</strong>
              {copy.body ? <span>{copy.body}</span> : null}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
