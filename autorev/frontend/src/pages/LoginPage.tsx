import { Alert, Button, PasswordInput, TextInput } from "@mantine/core";
import { useForm } from "@mantine/form";
import { IconAlertCircle } from "@tabler/icons-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Navigate, useNavigate, useSearchParams } from "react-router";
import { errorMessage, getToken, request, setToken } from "../api/client";
import { keys, useSetupState } from "../api/queries";
import type { Me } from "../api/types";
import { AuthCard } from "../components/AuthCard";
import { safeNext } from "../lib/safeNext";

export function LoginPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const next = safeNext(params.get("next"));
  const setup = useSetupState();
  const form = useForm({
    initialValues: { email: "", password: "" },
    validate: { email: (v) => (/^\S+@\S+$/.test(v) ? null : "Enter your email address") },
  });
  const login = useMutation({
    meta: { quiet: true },
    mutationFn: async (v: { email: string; password: string }) => {
      const { access_token } = await request<{ access_token: string }>("/api/auth/login", {
        method: "POST",
        body: { email: v.email.trim(), password: v.password },
      });
      setToken(access_token);
      return request<Me>("/api/auth/me");
    },
    onSuccess: (me) => {
      qc.setQueryData(keys.me, me);
      navigate(next, { replace: true });
    },
    onError: () => setToken(null),
  });

  // First run: there is no admin to sign in as yet.
  if (setup.data?.needed) return <Navigate to="/setup" replace />;
  // Already signed in: RequireSession re-checks the token on the way in.
  if (getToken() && !login.isPending) return <Navigate to={next} replace />;

  return (
    <AuthCard title="Sign in" subtitle="Manage your apps' subscription payments.">
      <form onSubmit={form.onSubmit((v) => login.mutate(v))}>
        {login.error && (
          <Alert color="red" icon={<IconAlertCircle size={16} />} mb="md">
            {errorMessage(login.error)}
          </Alert>
        )}
        <TextInput
          label="Email"
          placeholder="you@company.com"
          type="email"
          autoComplete="email"
          autoFocus
          required
          {...form.getInputProps("email")}
        />
        <PasswordInput
          label="Password"
          autoComplete="current-password"
          required
          mt="sm"
          {...form.getInputProps("password")}
        />
        <Button type="submit" fullWidth mt="lg" loading={login.isPending}>
          Sign in
        </Button>
      </form>
    </AuthCard>
  );
}
