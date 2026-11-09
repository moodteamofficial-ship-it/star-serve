function Skel({ className = "" }: { className?: string }) {
  return <span className={`skeleton-block website-skel ${className}`.trim()} aria-hidden="true" />;
}

export function WebsiteAdminStatsSkeleton() {
  return (
    <div className="website-admin-stats" aria-hidden="true">
      {Array.from({ length: 3 }, (_, i) => (
        <div key={i}>
          <Skel className="website-skel-stat-label" />
          <Skel className="website-skel-stat-value" />
        </div>
      ))}
    </div>
  );
}

export function WebsiteAdminListSkeleton({ rows = 8 }: { rows?: number }) {
  return (
    <ul className="website-admin-list" aria-hidden="true">
      {Array.from({ length: rows }, (_, i) => (
        <li key={i}>
          <div className="website-admin-list-item website-admin-list-item--skel">
            <Skel className="website-skel-index" />
            <div className="website-admin-list-copy">
              <Skel className="website-skel-list-title" />
            </div>
            <Skel className="website-skel-badge" />
          </div>
        </li>
      ))}
    </ul>
  );
}

export function WebsiteAdminEditorSkeleton() {
  return (
    <div className="website-admin-editor-skel" aria-busy="true" aria-live="polite">
      <span className="config-sr-only">Loading section editor</span>
      <div className="website-admin-editor-head">
        <div className="website-admin-editor-title">
          <Skel className="website-skel-kicker" />
          <Skel className="website-skel-editor-title" />
          <Skel className="website-skel-editor-help" />
        </div>
        <Skel className="website-skel-toggle" />
      </div>

      <section className="website-form-section">
        <header className="website-form-section-head">
          <Skel className="website-skel-section-title" />
          <Skel className="website-skel-section-help" />
        </header>
        <div className="website-form-section-body">
          <div className="website-field-grid">
            <div className="website-field">
              <Skel className="website-skel-field-label" />
              <Skel className="website-skel-input" />
            </div>
            <div className="website-field">
              <Skel className="website-skel-field-label" />
              <Skel className="website-skel-input" />
            </div>
            <div className="website-field website-field--span-2">
              <Skel className="website-skel-field-label" />
              <Skel className="website-skel-textarea" />
            </div>
          </div>
        </div>
      </section>

      <section className="website-form-section">
        <header className="website-form-section-head">
          <Skel className="website-skel-section-title" />
        </header>
        <div className="website-form-section-body">
          <div className="website-image-layout">
            <Skel className="website-skel-image" />
            <div className="website-image-controls">
              <Skel className="website-skel-btn" />
              <div className="website-field">
                <Skel className="website-skel-field-label" />
                <Skel className="website-skel-input" />
              </div>
              <div className="website-field">
                <Skel className="website-skel-field-label" />
                <Skel className="website-skel-input" />
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="website-form-section">
        <header className="website-form-section-head">
          <Skel className="website-skel-section-title" />
        </header>
        <div className="website-form-section-body">
          <div className="website-field-grid">
            <div className="website-field">
              <Skel className="website-skel-field-label" />
              <Skel className="website-skel-input" />
            </div>
            <div className="website-field">
              <Skel className="website-skel-field-label" />
              <Skel className="website-skel-input" />
            </div>
            <div className="website-field website-field--span-2">
              <Skel className="website-skel-field-label" />
              <Skel className="website-skel-input" />
            </div>
          </div>
        </div>
      </section>

      <div className="website-admin-editor-footer">
        <Skel className="website-skel-footer-note" />
        <Skel className="website-skel-btn website-skel-btn--primary" />
      </div>
    </div>
  );
}
