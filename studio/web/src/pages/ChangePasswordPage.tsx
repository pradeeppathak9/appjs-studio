import { Button, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { api } from "../api/client";
import { keys } from "../api/queries";
import { useSession } from "../auth/session";
import { AuthCard } from "../components/AuthCard";
import { PasswordForm } from "../components/PasswordForm";

/** Forced after sign-in while must_change_password is set (e.g. a temporary password). */
export function ChangePasswordPage() {
  const me = useSession();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const done = async () => {
    notifications.show({ color: "green", message: "Password changed" });
    await qc.invalidateQueries({ queryKey: keys.me });
    navigate("/", { replace: true });
  };
  const logout = async () => {
    await api.POST("/v1/auth/logout");
    qc.clear();
    navigate("/login", { replace: true });
  };
  return (
    <AuthCard
      title="Change your password"
      subtitle={
        me.must_change_password
          ? "You signed in with a temporary password. Choose your own to continue."
          : `Signed in as ${me.email}`
      }
    >
      <PasswordForm onDone={done} submitLabel="Set password" />
      <Text size="sm" ta="center">
        <Button variant="subtle" size="xs" onClick={logout}>
          Log out
        </Button>
      </Text>
    </AuthCard>
  );
}
