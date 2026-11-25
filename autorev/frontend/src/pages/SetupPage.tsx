import { Alert, Button, Center, Loader, PasswordInput, Stack, TextInput } from "@mantine/core";
import { useForm } from "@mantine/form";
import { IconAlertCircle } from "@tabler/icons-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Navigate, useNavigate } from "react-router";
import { errorMessage, request, setToken } from "../api/client";
import { keys, useSetupState } from "../api/queries";
import type { SetupResponse } from "../api/types";
import { AuthCard } from "../components/AuthCard";

type Values = { setup_token: string; email: string; full_name: string; password: string; confirm: string };

/** First run: create the first admin with the setup token from AUTOREV_SETUP_TOKEN or the backend log. */
export function SetupPage() {
  const setup = useSetupState();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const form = useForm<Values>({
    initialValues: { setup_token: "", email: "", full_name: "", password: "", confirm: "" },
    validate: {
      email: (v) => (/^\S+@\S+$/.test(v) ? null : "Enter your email address"),
      password: (v) => (v.length >= 12 ? null : "At least 12 characters"),
      confirm: (v, values) => (v !== values.password ? "Passwords don't match" : null),
    },
  });
  const submit = useMutation({
    meta: { quiet: true },
    mutationFn: (v: Values) =>
      request<SetupResponse>("/api/auth/setup", {
        method: "POST",
        body: { setup_token: v.setup_token.trim(), email: v.email.trim(), full_name: v.full_name.trim(), password: v.password },
      }),
    onSuccess: (res) => {
      setToken(res.access_token);
      qc.setQueryData(keys.setup, { needed: false });
      qc.setQueryData(keys.me, res.user);
      navigate("/dashboard", { replace: true });
    },
  });

  if (setup.isPending) {
    return (
      <Center h="100vh">
        <Loader />
      </Center>
    );
  }
  if (!setup.data?.needed && !submit.isSuccess) return <Navigate to="/" replace />;

  return (
    <AuthCard
      title="First-run setup"
      subtitle="Create the admin account. The setup token is AUTOREV_SETUP_TOKEN, or printed in the backend log."
    >
      <form onSubmit={form.onSubmit((v) => submit.mutate(v))}>
        <Stack gap="sm">
          {submit.error && (
            <Alert color="red" icon={<IconAlertCircle size={16} />}>
              {errorMessage(submit.error)}
            </Alert>
          )}
          <TextInput label="Setup token" required autoFocus autoComplete="off" {...form.getInputProps("setup_token")} />
          <TextInput label="Email" type="email" required autoComplete="username" {...form.getInputProps("email")} />
          <TextInput label="Name" required autoComplete="name" {...form.getInputProps("full_name")} />
          <PasswordInput
            label="Password"
            description="At least 12 characters"
            required
            autoComplete="new-password"
            {...form.getInputProps("password")}
          />
          <PasswordInput label="Repeat password" required autoComplete="new-password" {...form.getInputProps("confirm")} />
          <Button type="submit" fullWidth mt="xs" loading={submit.isPending}>
            Create admin
          </Button>
        </Stack>
      </form>
    </AuthCard>
  );
}
