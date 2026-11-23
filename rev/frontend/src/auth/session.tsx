import { Center, Loader } from "@mantine/core";
import { createContext, useContext, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router";
import { getToken, setToken } from "../api/client";
import { useMe } from "../api/queries";
import type { Me } from "../api/types";

const SessionContext = createContext<Me | null>(null);

/** The signed-in user. Only valid under <RequireSession>. */
export function useSession(): Me {
  const me = useContext(SessionContext);
  if (!me) throw new Error("useSession outside <RequireSession>");
  return me;
}

/** Renders children for a signed-in user; anyone else goes to the sign-in page at "/". */
export function RequireSession({ children }: { children: ReactNode }) {
  const location = useLocation();
  const me = useMe();
  const next = encodeURIComponent(location.pathname + location.search);
  if (!getToken()) return <Navigate to={`/?next=${next}`} replace />;
  if (me.isPending) {
    return (
      <Center h="100vh">
        <Loader />
      </Center>
    );
  }
  if (me.isError) {
    setToken(null);
    return <Navigate to={`/?next=${next}`} replace />;
  }
  return <SessionContext.Provider value={me.data}>{children}</SessionContext.Provider>;
}

/** The admin area. A non-admin is sent to their own dashboard; the API enforces this too. */
export function RequireAdmin({ children }: { children: ReactNode }) {
  const me = useSession();
  if (!me.is_admin) return <Navigate to="/dashboard" replace />;
  return <>{children}</>;
}
