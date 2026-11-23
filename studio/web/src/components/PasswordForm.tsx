import { Alert, Button, PasswordInput, Stack } from "@mantine/core";
import { useForm } from "@mantine/form";
import { useMutation } from "@tanstack/react-query";
import { api, errorMessage, unwrap } from "../api/client";
import { fieldErrors } from "../lib/formErrors";

/** Change own password (POST /v1/auth/password). Ends the user's other sessions. */
export function PasswordForm({ onDone, submitLabel = "Change password" }: { onDone: () => void; submitLabel?: string }) {
  const form = useForm({
    initialValues: { current_password: "", new_password: "", confirm: "" },
    validate: { confirm: (v, values) => (v !== values.new_password ? "Passwords don't match" : null) },
  });
  const change = useMutation({
    meta: { quiet: true },
    mutationFn: (v: typeof form.values) =>
      unwrap(
        api.POST("/v1/auth/password", {
          body: { current_password: v.current_password, new_password: v.new_password },
        }),
      ),
    onSuccess: () => {
      form.reset();
      onDone();
    },
    onError: (e) => form.setErrors(fieldErrors(e, (p) => p in form.values).errors),
  });
  const { errors, rest } = fieldErrors(change.error, (p) => p in form.values);
  return (
    <form onSubmit={form.onSubmit((v) => change.mutate(v))}>
      <Stack>
        {change.error && (rest.length > 0 || Object.keys(errors).length === 0) && (
          <Alert color="red">{rest.length ? rest.join("; ") : errorMessage(change.error)}</Alert>
        )}
        <PasswordInput
          label="Current password"
          required
          autoComplete="current-password"
          {...form.getInputProps("current_password")}
        />
        <PasswordInput
          label="New password"
          description="At least 12 characters, not your email"
          required
          autoComplete="new-password"
          {...form.getInputProps("new_password")}
        />
        <PasswordInput label="Repeat new password" required autoComplete="new-password" {...form.getInputProps("confirm")} />
        <Button type="submit" loading={change.isPending}>
          {submitLabel}
        </Button>
      </Stack>
    </form>
  );
}
