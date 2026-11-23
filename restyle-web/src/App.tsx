import type { ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router";
import { Layout } from "./components/Layout";
import { Spinner } from "./components/ui";
import { userMessage } from "./lib/format";
import { useConfig } from "./lib/queries";
import { useSession } from "./lib/session";
import { Profile, Subscribe } from "./pages/Account";
import { Create } from "./pages/Create";
import { Creations } from "./pages/Creations";
import { Home } from "./pages/Home";
import { Login } from "./pages/Login";
import { Result } from "./pages/Result";

/** Sends people to sign-in when the page needs an account (`always`) or the app requires sign-in. */
function Gate({ children, always = false }: { children: ReactNode; always?: boolean }) {
  const { token } = useSession();
  const config = useConfig();
  const location = useLocation();
  if (token) return children;
  if (!always) {
    if (config.isLoading) return <Spinner />;
    if (config.error) return <p className="notice error">{userMessage(config.error)}</p>;
    if (!config.data?.require_login) return children;
  }
  return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />;
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<Layout />}>
        <Route index element={<Gate><Home /></Gate>} />
        <Route path="create/:slug" element={<Gate><Create /></Gate>} />
        <Route path="result/:jobId" element={<Gate><Result /></Gate>} />
        <Route path="creations" element={<Gate always><Creations /></Gate>} />
        <Route path="profile" element={<Gate always><Profile /></Gate>} />
        <Route path="subscribe" element={<Gate always><Subscribe /></Gate>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
