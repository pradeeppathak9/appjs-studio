import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router";
import { setToken, setUnauthorizedHandler } from "./api/client.js";
import { RequireAdmin, RequireSession } from "./auth/session.js";
import { Layout } from "./components/Layout.js";
import { Legacy } from "./components/Legacy.js";
import { AccountPage } from "./pages/AccountPage.js";
import { AdminLayout } from "./pages/admin/AdminLayout.js";
import { AppIndex, AppLayout } from "./pages/app/AppLayout.js";
import { AppsPage } from "./pages/AppsPage.js";
import { SubscriptionsPage } from "./pages/app/phonepe/SubscriptionsPage.js";
import { SummaryPage } from "./pages/app/phonepe/SummaryPage.js";
import { TransactionsPage } from "./pages/app/phonepe/TransactionsPage.js";
import { IntegrationGuidePage } from "./pages/app/guide/IntegrationGuidePage.js";
import { RazorpayPaymentsPage } from "./pages/app/razorpay/PaymentsPage.js";
import { RazorpaySubscriptionsPage } from "./pages/app/razorpay/SubscriptionsPage.js";
import { LoginPage } from "./pages/LoginPage.js";
import { SetupPage } from "./pages/SetupPage.js";

// Pages not yet ported from the old console. Each moves out of src/legacy as it is rewritten.
import AdminAppUsers from "./legacy/pages/AdminAppUsers.jsx";
import AdminApps from "./legacy/pages/AdminApps.jsx";
import AdminRedis from "./legacy/pages/AdminRedis.jsx";
import AdminUsers from "./legacy/pages/AdminUsers.jsx";
import AppSettings from "./legacy/pages/AppSettings.jsx";

/** A 401 from any request (expired token) signs out and returns to the sign-in page. */
function useUnauthorizedRedirect() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setToken(null);
      qc.clear();
      const here = window.location.pathname + window.location.search;
      navigate(here === "/" ? "/" : `/?next=${encodeURIComponent(here)}`, { replace: true });
    });
  }, [navigate, qc]);
}

export function App() {
  useUnauthorizedRedirect();
  return (
    <Routes>
      {/* Sign-in lives at the base URL, as before. */}
      <Route path="/" element={<LoginPage />} />
      <Route path="/login" element={<Navigate to="/" replace />} />
      <Route path="/setup" element={<SetupPage />} />

      <Route
        element={
          <RequireSession>
            <Layout />
          </RequireSession>
        }
      >
        <Route path="/dashboard" element={<AppsPage />} />
        <Route path="/account" element={<AccountPage />} />

        <Route path="/apps/:appId" element={<AppLayout />}>
          <Route index element={<AppIndex summary={<SummaryPage />} />} />
          {/* PhonePe */}
          <Route path="subscriptions" element={<SubscriptionsPage />} />
          <Route path="transactions" element={<TransactionsPage />} />
          {/* Razorpay */}
          <Route path="rz-subscriptions" element={<RazorpaySubscriptionsPage />} />
          <Route path="rz-payments" element={<RazorpayPaymentsPage />} />
          {/* Shared */}
          <Route path="settings" element={<Legacy><AppSettings /></Legacy>} />
          <Route path="integration-guide" element={<IntegrationGuidePage />} />
        </Route>

        <Route
          path="/admin"
          element={
            <RequireAdmin>
              <AdminLayout />
            </RequireAdmin>
          }
        >
          <Route index element={<Navigate to="/admin/apps" replace />} />
          <Route path="apps" element={<Legacy><AdminApps /></Legacy>} />
          <Route path="apps/:appId" element={<Legacy><AdminAppUsers /></Legacy>} />
          <Route path="users" element={<Legacy><AdminUsers /></Legacy>} />
          <Route path="redis" element={<Legacy><AdminRedis /></Legacy>} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
