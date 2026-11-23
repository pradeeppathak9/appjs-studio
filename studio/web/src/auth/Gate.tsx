import { Alert, Center, Loader } from "@mantine/core";
import { Navigate, Outlet, useLocation } from "react-router";
import { errorMessage } from "../api/client";
import { useMe, useSetupState } from "../api/queries";
import { SessionContext } from "./session";

export function FullPageLoader() {
  return (
    <Center h="60vh">
      <Loader />
    </Center>
  );
}

/**
 * Everything behind sign-in: setup needed -> /setup; signed out -> /login?next=...;
 * must change password -> /change-password only.
 */
export function Gate() {
  const location = useLocation();
  const setup = useSetupState();
  const me = useMe(setup.data?.needed === false);

  if (setup.isPending) return <FullPageLoader />;
  if (setup.error) {
    return (
      <Alert color="red" m="xl" title="Can't reach the API">
        {errorMessage(setup.error)}
      </Alert>
    );
  }
  if (setup.data.needed) return <Navigate to="/setup" replace />;
  if (me.isPending) return <FullPageLoader />;
  if (me.error || !me.data) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  if (me.data.must_change_password && location.pathname !== "/change-password") {
    return <Navigate to="/change-password" replace />;
  }
  return (
    <SessionContext.Provider value={me.data}>
      <Outlet />
    </SessionContext.Provider>
  );
}
