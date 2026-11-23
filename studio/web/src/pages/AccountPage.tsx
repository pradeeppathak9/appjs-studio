import { Button, Group, Modal, SimpleGrid, Stack, Text, TextInput } from "@mantine/core";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import { keys } from "../api/queries";
import type { TokenCreated } from "../api/types";
import { useSession } from "../auth/session";
import { CopyBlock } from "../components/common";
import { PageHeader, Section, ThemeToggle, UserAvatar } from "../components/ui";
import { IconKey, IconLock, IconPalette, IconPlus, IconUser } from "@tabler/icons-react";
import { PasswordForm } from "../components/PasswordForm";
import { TokenTable } from "../components/TokenTable";

function NameForm() {
  const me = useSession();
  const qc = useQueryClient();
  const form = useForm({ initialValues: { name: me.name } });
  const save = useMutation({
    mutationFn: (name: string) => unwrap(api.PATCH("/v1/auth/me", { body: { name } })),
    onSuccess: (updated) => {
      qc.setQueryData(keys.me, updated);
      notifications.show({ color: "green", message: "Name saved" });
    },
  });
  return (
    <form onSubmit={form.onSubmit((v) => save.mutate(v.name))}>
      <Stack>
        <TextInput label="Email" value={me.email} disabled />
        <TextInput label="Name" required {...form.getInputProps("name")} />
        <Group>
          <Button type="submit" loading={save.isPending} disabled={!form.isDirty()}>
            Save name
          </Button>
        </Group>
      </Stack>
    </form>
  );
}

function Tokens() {
  const qc = useQueryClient();
  const tokens = useQuery({ queryKey: keys.tokens, queryFn: () => unwrap(api.GET("/v1/auth/tokens")) });
  const [open, setOpen] = useState(false);
  const [created, setCreated] = useState<TokenCreated | null>(null);
  const form = useForm({ initialValues: { name: "" } });
  const create = useMutation({
    mutationFn: (name: string) => unwrap(api.POST("/v1/auth/tokens", { body: { name } })),
    onSuccess: (t) => {
      setCreated(t);
      form.reset();
      qc.invalidateQueries({ queryKey: keys.tokens });
    },
  });
  const revoke = useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/v1/auth/tokens/{token_id}", { params: { path: { token_id: id } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.tokens }),
  });
  const close = () => {
    setOpen(false);
    setCreated(null);
  };

  return (
    <Section
      title="API tokens"
      icon={<IconKey size={18} />}
      description="A token acts as you, with your role. Send it as Authorization: Bearer …."
      actions={
        <Button size="xs" onClick={() => setOpen(true)} leftSection={<IconPlus size={14} />}>
          New token
        </Button>
      }
    >
    <Stack>
      <TokenTable
        tokens={tokens.data ?? []}
        revoking={revoke.isPending ? revoke.variables : undefined}
        onRevoke={(t) => {
          if (window.confirm(`Revoke token "${t.name}"? Scripts using it will stop working.`)) revoke.mutate(t.id);
        }}
      />
      <Modal opened={open} onClose={close} title={created ? "Token created" : "New API token"} size="lg">
        {created ? (
          <Stack>
            <Text size="sm" c="orange">
              Copy it now: it is shown only once.
            </Text>
            <CopyBlock value={created.token} testId="new-token" />
            <CopyBlock
              label="Example"
              value={`export STUDIO_TOKEN=${created.token}\ncurl -H "Authorization: Bearer $STUDIO_TOKEN" ${window.location.origin}/v1/apps`}
            />
            <Button onClick={close}>Done</Button>
          </Stack>
        ) : (
          <form onSubmit={form.onSubmit((v) => create.mutate(v.name))}>
            <Stack>
              <TextInput label="Name" placeholder="e.g. ci-script" required data-autofocus {...form.getInputProps("name")} />
              <Button type="submit" loading={create.isPending}>
                Create token
              </Button>
            </Stack>
          </form>
        )}
      </Modal>
    </Stack>
    </Section>
  );
}

export function AccountPage() {
  const me = useSession();
  return (
    <Stack gap="lg">
      <PageHeader
        leading={<UserAvatar name={me.name} email={me.email} size={48} />}
        title={me.name}
        description={me.email}
      />
      <Section title="Appearance" icon={<IconPalette size={18} />} description="Light, dark, or follow your system setting.">
        <ThemeToggle size="sm" />
      </Section>
      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
        <Section title="Profile" icon={<IconUser size={18} />}>
          <NameForm />
        </Section>
        <Section title="Password" icon={<IconLock size={18} />}>
          <PasswordForm onDone={() => notifications.show({ color: "green", message: "Password changed" })} />
        </Section>
      </SimpleGrid>
      <Tokens />
    </Stack>
  );
}
