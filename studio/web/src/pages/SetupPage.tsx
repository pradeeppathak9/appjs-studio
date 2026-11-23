import { Alert, Button, PasswordInput, Stack, TextInput } from "@mantine/core";
import { useForm } from "@mantine/form";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Navigate, useNavigate } from "react-router";
import { api, errorMessage, unwrap } from "../api/client";
import { keys, useSetupState } from "../api/queries";
import { FullPageLoader } from "../auth/Gate";
import { AuthCard } from "../components/AuthCard";
import { fieldErrors } from "../lib/formErrors";

/** First run: create the admin with the setup token from the API log / .env. */
export function SetupPage() {
  const setup = useSetupState();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const form = useForm({
    initialValues: { setup_token: "", email: "", name: "", password: "", confirm: "" },
    validate: {
      confirm: (v, values) => (v !== values.password ? "Passwords don't match" : null),
    },
  });
  const submit = useMutation({
    meta: { quiet: true },
    mutationFn: (v: typeof form.values) =>
      unwrap(
        api.POST("/v1/auth/setup", {
          body: { setup_token: v.setup_token, email: v.email, name: v.name, password: v.password },
        }),
      ),
    onSuccess: (me) => {
      qc.setQueryData(keys.setup, { needed: false });
      qc.setQueryData(keys.me, me);
      navigate("/", { replace: true });
    },
    onError: (e) => form.setErrors(fieldErrors(e, (p) => p in form.values).errors),
  });

  if (setup.isPending) return <FullPageLoader />;
  if (setup.data && !setup.data.needed && !submit.isSuccess) return <Navigate to="/login" replace />;

  const { rest } = fieldErrors(submit.error, (p) => p in form.values);
  return (
    <AuthCard
      title="First-run setup"
      subtitle="Create the admin account. The setup token is SETUP_TOKEN, or printed in the API log."
    >
      <form onSubmit={form.onSubmit((v) => submit.mutate(v))}>
        <Stack>
          {submit.error && (
            <Alert color="red">{rest.length ? rest.join("; ") : errorMessage(submit.error)}</Alert>
          )}
          <TextInput label="Setup token" required {...form.getInputProps("setup_token")} />
          <TextInput label="Email" type="email" required autoComplete="username" {...form.getInputProps("email")} />
          <TextInput label="Name" required {...form.getInputProps("name")} />
          <PasswordInput
            label="Password"
            description="At least 12 characters"
            required
            autoComplete="new-password"
            {...form.getInputProps("password")}
          />
          <PasswordInput label="Repeat password" required autoComplete="new-password" {...form.getInputProps("confirm")} />
          <Button type="submit" loading={submit.isPending}>
            Create admin
          </Button>
        </Stack>
      </form>
    </AuthCard>
  );
}
