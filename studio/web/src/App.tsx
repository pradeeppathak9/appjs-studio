import { useQueryClient } from "@tanstack/react-query";
import { useEffect, type ReactNode } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router";
import { setAuthHandlers } from "./api/client";
import { Gate } from "./auth/Gate";
import { isAdmin } from "./auth/roles";
import { useSession } from "./auth/session";
import { Forbidden, NotFound } from "./components/Forbidden";
import { Layout } from "./components/Layout";
import { AccountPage } from "./pages/AccountPage";
import { AdminAppPage } from "./pages/admin/AdminAppPage";
import { AdminAppSettingsPage } from "./pages/admin/AdminAppSettingsPage";
import { AdminAppsPage } from "./pages/admin/AdminAppsPage";
import { AdminLayout } from "./pages/admin/AdminLayout";
import { AdminUsersPage } from "./pages/admin/AdminUsersPage";
import { AndroidPreviewPage } from "./pages/app/AndroidPreviewPage";
import { AppJobsPage } from "./pages/app/AppJobsPage";
import { AppLayout, RequireEditor } from "./pages/app/AppLayout";
import { AppTemplatesPage } from "./pages/app/AppTemplatesPage";
import { AppTestPage } from "./pages/app/AppTestPage";
import { AppUsersPage } from "./pages/app/AppUsersPage";
import { FreePromptPage } from "./pages/app/FreePromptPage";
import { IntegrationGuidePage } from "./pages/app/IntegrationGuidePage";
import { TemplateEditorPage } from "./pages/app/TemplateEditorPage";
import { ChangePasswordPage } from "./pages/ChangePasswordPage";
import { HomePage } from "./pages/HomePage";
import { JobPage } from "./pages/JobPage";
import { LoginPage } from "./pages/LoginPage";
import { SetupPage } from "./pages/SetupPage";

/** Lets the API client send the user to /login or /change-password from outside React. */
function AuthBridge() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  useEffect(() => {
    setAuthHandlers({
      navigate: (to) => navigate(to),
      onSignedOut: () => qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "setup" }),
    });
  }, [navigate, qc]);
  return null;
}

function RequireAdmin({ children }: { children: ReactNode }) {
  const me = useSession();
  return isAdmin(me) ? children : <Forbidden detail="The admin dashboard is for admins." />;
}

/** Paths from the old global-tab layout. */
const OLD_PATHS = ["/use/*", "/generate", "/templates/*", "/users", "/apps", "/jobs"];

export function App() {
  return (
    <>
      <AuthBridge />
      <Routes>
        <Route path="/setup" element={<SetupPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route element={<Gate />}>
          <Route path="/change-password" element={<ChangePasswordPage />} />
          <Route element={<Layout />}>
            <Route index element={<HomePage />} />
            <Route path="/account" element={<AccountPage />} />
            <Route path="/jobs/:jobId" element={<JobPage />} />
            <Route path="/apps/:appId" element={<AppLayout />}>
              <Route index element={<AppTemplatesPage />} />
              <Route path="test" element={<AppTestPage />} />
              <Route path="jobs" element={<AppJobsPage />} />
              <Route path="guide" element={<IntegrationGuidePage />} />
              <Route
                path="free"
                element={
                  <RequireEditor>
                    <FreePromptPage />
                  </RequireEditor>
                }
              />
              <Route
                path="preview"
                element={
                  <RequireEditor>
                    <AndroidPreviewPage />
                  </RequireEditor>
                }
              />
              <Route
                path="users"
                element={
                  <RequireAdmin>
                    <AppUsersPage />
                  </RequireAdmin>
                }
              />
              <Route
                path="settings"
                element={
                  <RequireAdmin>
                    <AdminAppSettingsPage inApp />
                  </RequireAdmin>
                }
              />
              <Route
                path="templates/:templateId"
                element={
                  <RequireEditor>
                    <TemplateEditorPage />
                  </RequireEditor>
                }
              />
            </Route>
            <Route
              path="/admin"
              element={
                <RequireAdmin>
                  <AdminLayout />
                </RequireAdmin>
              }
            >
              <Route index element={<Navigate to="users" replace />} />
              <Route path="users" element={<AdminUsersPage />} />
              <Route path="apps" element={<AdminAppsPage />} />
              <Route path="apps/:appId" element={<AdminAppPage />} />
              <Route path="apps/:appId/settings" element={<AdminAppSettingsPage />} />
            </Route>
            {OLD_PATHS.map((p) => (
              <Route key={p} path={p} element={<Navigate to="/" replace />} />
            ))}
            <Route path="*" element={<NotFound />} />
          </Route>
        </Route>
      </Routes>
    </>
  );
}
