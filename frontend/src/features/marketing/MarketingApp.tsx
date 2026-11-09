import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { ThemeProvider } from "@/app/providers/ThemeProvider";
import { ScrollToTop } from "@/app/router/ScrollToTop";
import { MarketingHomePage } from "@/features/marketing/MarketingHomePage";
import { MarketingInnerPage } from "@/features/marketing/MarketingInnerPage";
import { MarketingLayout } from "@/features/marketing/MarketingLayout";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
});

export default function MarketingApp() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <BrowserRouter
          future={{
            v7_startTransition: true,
            v7_relativeSplatPath: true,
          }}
        >
          <ScrollToTop />
          <Routes>
            <Route element={<MarketingLayout />}>
              <Route index element={<MarketingHomePage />} />
              <Route path=":pageSlug" element={<MarketingInnerPage />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
