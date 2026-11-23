import { Badge, Button, Group, PasswordInput, SimpleGrid, Stack, Text } from "@mantine/core";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { IconKey, IconPalette, IconUser } from "@tabler/icons-react";
import { useMutation } from "@tanstack/react-query";
import { request } from "../api/client";
import { useSession } from "../auth/session";
import { PageHeader, Section, ThemeToggle, UserAvatar } from "../components/ui";

function PasswordSection() {
  const form = useForm({
    initialValues: { current_password: "", new_password: "", confirm_password: "" },
    validate: {
      current_password: (v) => (v ? null : "Enter your current password"),
      new_password: (v) => (v.length >= 8 ? null : "At least 8 characters"),
      confirm_password: (v, all) => (v === all.new_password ? null : "The passwords don't match"),
    },
  });
  const change = useMutation({
    meta: { quiet: true },
    mutationFn: (v: typeof form.values) =>
      request<null>("/api/auth/change-password", {
        method: "POST",
        body: { current_password: v.current_password, new_password: v.new_password },
      }),
    onSuccess: () => {
      form.reset();
      notifications.show({ color: "green", message: "Password changed." });
    },
    onError: (e) => form.setFieldError("current_password", e.message),
  });
  return (
    <Section title="Password" icon={<IconKey size={18} />} description="At least 8 characters.">
      <form onSubmit={form.onSubmit((v) => change.mutate(v))}>
        <Stack gap="sm" maw={420}>
          <PasswordInput label="Current password" autoComplete="current-password" {...form.getInputProps("current_password")} />
          <PasswordInput label="New password" autoComplete="new-password" {...form.getInputProps("new_password")} />
          <PasswordInput label="Confirm new password" autoComplete="new-password" {...form.getInputProps("confirm_password")} />
          <Group>
            <Button type="submit" loading={change.isPending}>
              Change password
            </Button>
          </Group>
        </Stack>
      </form>
    </Section>
  );
}

export function AccountPage() {
  const me = useSession();
  const name = me.full_name || me.email;
  return (
    <Stack gap="lg">
      <PageHeader
        title={name}
        description={me.email}
        leading={<UserAvatar name={name} email={me.email} size={48} />}
        actions={me.is_admin ? <Badge variant="light">Admin</Badge> : undefined}
      />
      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
        <Section title="Profile" icon={<IconUser size={18} />}>
          <Stack gap={6}>
            <Text size="sm">
              <Text span c="dimmed">
                Name:{" "}
              </Text>
              {me.full_name || "—"}
            </Text>
            <Text size="sm">
              <Text span c="dimmed">
                Email:{" "}
              </Text>
              {me.email}
            </Text>
            <Text size="sm">
              <Text span c="dimmed">
                Role:{" "}
              </Text>
              {me.is_admin ? "Admin" : "User"}
            </Text>
          </Stack>
        </Section>
        <Section title="Appearance" icon={<IconPalette size={18} />} description="Light, dark, or follow your system setting.">
          <ThemeToggle />
        </Section>
      </SimpleGrid>
      <PasswordSection />
    </Stack>
  );
}
