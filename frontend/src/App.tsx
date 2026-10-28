import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "@/app/providers/AuthProvider";
import { ThemeProvider } from "@/app/providers/ThemeProvider";
import { ProtectedRoute } from "@/app/router/ProtectedRoute";
import { ScrollToTop } from "@/app/router/ScrollToTop";
import { AppShell } from "@/components/layout/AppShell";
import { TopLoader } from "@/components/layout/TopLoader";
import { LoginPage } from "@/features/auth/LoginPage";
import { AuditPage } from "@/features/audit/AuditPage";
import { BranchesPage } from "@/features/branches/BranchesPage";
import { CertificatesPage } from "@/features/certificates/CertificatesPage";
import { ClaimDetailPage } from "@/features/claims/ClaimDetailPage";
import { ClaimsPage } from "@/features/claims/ClaimsPage";
import { NewClaimPage } from "@/features/claims/NewClaimPage";
import { CommissionLedgerPage } from "@/features/commissions/CommissionLedgerPage";
import { CustomersPage } from "@/features/customers/CustomersPage";
import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { IntermediariesPage } from "@/features/intermediaries/IntermediariesPage";
import { NotificationsPage } from "@/features/notifications/NotificationsPage";
import { PaymentsPage } from "@/features/payments/PaymentsPage";
import { PlatformPage } from "@/features/platform/PlatformPage";
import { PoliciesPage } from "@/features/policies/PoliciesPage";
import { ProductsPage } from "@/features/products/ProductsPage";
import { ProposalsPage } from "@/features/proposals/ProposalsPage";
import { QuoteWizardPage } from "@/features/quote/QuoteWizardPage";
import { ReportsPage } from "@/features/reports/ReportsPage";
import { SettingsPage } from "@/features/settings/SettingsPage";
import { UsersPage } from "@/features/users/UsersPage";
import { UssdPage } from "@/features/ussd/UssdPage";
import { WelcomePage } from "@/features/welcome/WelcomePage";
import { AgentRegisterPage } from "@/features/welcome/AgentRegisterPage";
import { appBasename } from "@/app/router/basePath";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false, refetchOnWindowFocus: false },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AuthProvider>
          <BrowserRouter
            basename={appBasename()}
            future={{
              v7_startTransition: true,
              v7_relativeSplatPath: true,
            }}
          >
            <TopLoader />
            <ScrollToTop />
            <Routes>
              <Route path="/" element={<WelcomePage />} />
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register-agent" element={<AgentRegisterPage />} />
              <Route element={<ProtectedRoute />}>
                <Route path="/app" element={<AppShell />}>
                  <Route index element={<DashboardPage />} />
                  <Route path="quote" element={<QuoteWizardPage />} />
                  <Route path="customers" element={<CustomersPage />} />
                  <Route path="intermediaries" element={<IntermediariesPage />} />
                  <Route path="products" element={<ProductsPage />} />
                  <Route path="proposals" element={<ProposalsPage />} />
                  <Route path="policies" element={<PoliciesPage />} />
                  <Route path="certificates" element={<CertificatesPage />} />
                  <Route path="claims" element={<ClaimsPage />} />
                  <Route path="claims/new" element={<NewClaimPage />} />
                  <Route path="claims/:claimId" element={<ClaimDetailPage />} />
                  <Route path="payments" element={<PaymentsPage />} />
                  <Route path="commission-ledger" element={<CommissionLedgerPage />} />
                  <Route path="notifications" element={<NotificationsPage />} />
                  <Route path="reports" element={<ReportsPage />} />
                  <Route path="audit" element={<AuditPage />} />
                  <Route path="users" element={<UsersPage />} />
                  <Route path="branches" element={<BranchesPage />} />
                  <Route path="settings" element={<SettingsPage />} />
                  <Route path="ussd" element={<UssdPage />} />
                  <Route path="platform" element={<PlatformPage />} />
                </Route>
              </Route>
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </BrowserRouter>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
