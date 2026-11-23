import { Alert, Button, PasswordInput, Stack, TextInput } from "@mantine/core";
import { useForm } from "@mantine/form";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Navigate, useNavigate, useSearchParams } from "react-router";
import { api, errorMessage, unwrap } from "../api/client";
import { keys, useSetupState } from "../api/queries";
import { AuthCard } from "../components/AuthCard";
import { safeNext } from "../lib/safeNext";

export function LoginPage() {
  const setup = useSetupState();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const form = useForm({ initialValues: { email: "", password: "" } });
  const login = useMutation({
    meta: { quiet: true },
    mutationFn: (body: typeof form.values) => unwrap(api.POST("/v1/auth/login", { body })),
    onSuccess: (me) => {
      qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "setup" });
      qc.setQueryData(keys.me, me);
      const to = me.must_change_password ? "/change-password" : safeNext(params.get("next")) ?? "/";
      navigate(to, { replace: true });
    },
  });

  if (setup.data?.needed) return <Navigate to="/setup" replace />;

  return (
    <AuthCard title="Sign in" subtitle="Use the email and password your admin gave you.">
      <form onSubmit={form.onSubmit((v) => login.mutate(v))}>
        <Stack>
          {login.error && (
            <Alert color="red" data-testid="login-error">
              {errorMessage(login.error)}
            </Alert>
          )}
          <TextInput label="Email" type="email" required autoComplete="username" {...form.getInputProps("email")} />
          <PasswordInput label="Password" required autoComplete="current-password" {...form.getInputProps("password")} />
          <Button type="submit" loading={login.isPending}>
            Sign in
          </Button>
        </Stack>
      </form>
    </AuthCard>
  );
}
