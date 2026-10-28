import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/app/providers/AuthProvider";
import { IdleLockProvider } from "@/app/providers/IdleLockProvider";
import { SessionBootScreen } from "@/components/layout/SessionBootScreen";

export function ProtectedRoute() {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <SessionBootScreen />;
  if (!user) {
    const next = `${location.pathname}${location.search}`;
    const to = next.startsWith("/app")
      ? `/login?next=${encodeURIComponent(next)}`
      : "/login";
    return <Navigate to={to} replace />;
  }
  return (
    <IdleLockProvider>
      <Outlet />
    </IdleLockProvider>
  );
}
