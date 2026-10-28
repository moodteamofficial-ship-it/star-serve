export function SessionBootScreen() {
  return (
    <div className="session-boot" aria-busy="true" aria-live="polite">
      <div className="session-boot-card">
        <img
          src={`${import.meta.env.BASE_URL}star-serve-logo.png?v=3`}
          alt="Star Serve Insurance Agency"
          className="session-boot-logo"
        />
        <div className="session-boot-spinner" aria-hidden="true" />
        <p className="session-boot-label">Restoring your session</p>
      </div>
    </div>
  );
}
