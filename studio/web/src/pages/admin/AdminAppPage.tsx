import {
  Alert,
  Badge,
  Button,
  Grid,
  Group,
  Modal,
  Paper,
  Select,
  SimpleGrid,
  Skeleton,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import {
  IconAdjustments,
  IconAlertTriangle,
  IconArrowLeft,
  IconDeviceFloppy,
  IconExternalLink,
  IconKey,
  IconPlus,
  IconSettings,
  IconTrash,
  IconUsers,
} from "@tabler/icons-react";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { api, errorMessage, unwrap } from "../../api/client";
import { keys, patchApp, useAdminApp, useAdminUsers, useAppKeys, useMembers } from "../../api/queries";
import type { AppDetail, AppKeyCreated } from "../../api/types";
import { AppFields } from "../../components/AppForm";
import { CopyBlock } from "../../components/common";
import { TokenTable } from "../../components/TokenTable";
import { AppAvatar, EmptyState, PlatformIcon, Section, StatusDot } from "../../components/ui";
import { appCurl, appValues, generalBody, type AppFormValues } from "../../lib/appForm";
import { fieldErrors } from "../../lib/formErrors";
import { AppUsers } from "./AppEndUsers";

type MemberRole = "editor" | "tester";

function useRefresh(appId: string) {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: keys.admin });
    qc.invalidateQueries({ queryKey: keys.myApps });
    qc.invalidateQueries({ queryKey: keys.app(appId) });
  };
}

function Settings({ app }: { app: AppDetail }) {
  const qc = useQueryClient();
  const refresh = useRefresh(app.id);
  const form = useForm<AppFormValues>({ initialValues: appValues(app) });
  const save = useMutation({
    meta: { quiet: true },
    mutationFn: (v: AppFormValues) =>
      patchApp(app.id, generalBody(v)),
    onSuccess: (a) => {
      qc.setQueryData(keys.adminApp(a.id), a);
      refresh();
      notifications.show({ color: "green", message: "App saved" });
    },
    onError: (e) => form.setErrors(fieldErrors(e, (p) => p in form.values).errors),
  });
  const rest = fieldErrors(save.error, (p) => p in form.values).rest;
  return (
    <Section title="Settings" icon={<IconSettings size={18} />} description="Name, platform, status and rate limits.">
    <form onSubmit={form.onSubmit((v) => save.mutate(v))}>
      <Stack>
        <SimpleGrid cols={2} data-testid="app-usage">
          <Paper withBorder p="sm" bg="var(--app-subtle)">
            <Text fw={700} fz={20} className="tabular">
              {app.usage.jobs_24h ?? 0}
            </Text>
            <Text size="xs" c="dimmed">
              jobs in the last 24 h
            </Text>
          </Paper>
          <Paper withBorder p="sm" bg="var(--app-subtle)">
            <Text fw={700} fz={20} className="tabular">
              {app.usage.devices_24h ?? 0}
            </Text>
            <Text size="xs" c="dimmed">
              devices in the last 24 h
            </Text>
          </Paper>
        </SimpleGrid>
        {save.error && (rest.length > 0 || !Object.keys(form.errors).length) && (
          <Alert color="red">{rest.length ? rest.join("; ") : errorMessage(save.error)}</Alert>
        )}
        <AppFields form={form} creating={false} />
        <Group>
          <Button type="submit" loading={save.isPending} disabled={!form.isDirty()} leftSection={<IconDeviceFloppy size={16} />}>
            Save settings
          </Button>
        </Group>
      </Stack>
    </form>
    </Section>
  );
}

function Members({ app }: { app: AppDetail }) {
  const members = useMembers(app.id);
  const users = useAdminUsers();
  const refresh = useRefresh(app.id);
  const [user, setUser] = useState<string | null>(null);
  const [role, setRole] = useState<MemberRole>("tester");
  const put = useMutation({
    mutationFn: (v: { userId: string; role: MemberRole }) =>
      unwrap(
        api.PUT("/v1/admin/apps/{app_id}/members/{user_id}", {
          params: { path: { app_id: app.id, user_id: v.userId } },
          body: { role: v.role },
        }),
      ),
    onSuccess: () => {
      setUser(null);
      refresh();
    },
  });
  const remove = useMutation({
    mutationFn: (userId: string) =>
      unwrap(
        api.DELETE("/v1/admin/apps/{app_id}/members/{user_id}", { params: { path: { app_id: app.id, user_id: userId } } }),
      ),
    onSuccess: refresh,
  });
  const memberIds = new Set(members.data?.map((m) => m.user_id));
  // Admins act as admin in every app and can't be members.
  const candidates = (users.data ?? []).filter((u) => u.role !== "admin" && !memberIds.has(u.id));

  return (
    <Section
      title="Members"
      icon={<IconUsers size={18} />}
      description="Editors manage templates and see all jobs; testers run active templates and see their own. Admins can open every app."
    >
    <Stack gap="xs">
      <Table data-testid="members-table" highlightOnHover={false}>
        <Table.Tbody>
          {members.data?.map((m) => (
            <Table.Tr key={m.user_id} data-email={m.email}>
              <Table.Td>
                {m.name}
                <Text size="xs" c="dimmed">
                  {m.email}
                  {!m.is_active && " · deactivated"}
                </Text>
              </Table.Td>
              <Table.Td w={130}>
                <Select
                  size="xs"
                  data={["editor", "tester"]}
                  value={m.role}
                  allowDeselect={false}
                  onChange={(v) => v && v !== m.role && put.mutate({ userId: m.user_id, role: v as MemberRole })}
                  aria-label={`Role of ${m.email}`}
                />
              </Table.Td>
              <Table.Td w={90}>
                <Button
                  size="compact-xs"
                  color="red"
                  variant="subtle"
                  loading={remove.isPending && remove.variables === m.user_id}
                  onClick={() => remove.mutate(m.user_id)}
                >
                  Remove
                </Button>
              </Table.Td>
            </Table.Tr>
          ))}
          {members.data?.length === 0 && (
            <Table.Tr>
              <Table.Td>
                <EmptyState
                  compact
                  icon={<IconUsers size={20} stroke={1.5} />}
                  title="No members yet"
                  description="Add users below as editors or testers."
                />
              </Table.Td>
            </Table.Tr>
          )}
        </Table.Tbody>
      </Table>
      <Group align="flex-end">
        <Select
          label="Add member"
          placeholder={candidates.length ? "Pick a user" : "No users to add"}
          data={candidates.map((u) => ({ value: u.id, label: `${u.name} <${u.email}>` }))}
          value={user}
          onChange={setUser}
          searchable
          style={{ flex: 1 }}
        />
        <Select
          label="Role"
          aria-label="New member role"
          data={["editor", "tester"]}
          value={role}
          onChange={(v) => v && setRole(v as MemberRole)}
          allowDeselect={false}
          w={110}
        />
        <Button disabled={!user} loading={put.isPending} onClick={() => put.mutate({ userId: user!, role })}>
          Add
        </Button>
      </Group>
    </Stack>
    </Section>
  );
}

function Keys({ app }: { app: AppDetail }) {
  const list = useAppKeys(app.id);
  const refresh = useRefresh(app.id);
  const [open, setOpen] = useState(false);
  const [created, setCreated] = useState<AppKeyCreated | null>(null);
  const form = useForm({ initialValues: { name: "" } });
  const create = useMutation({
    mutationFn: (name: string) =>
      unwrap(api.POST("/v1/admin/apps/{app_id}/keys", { params: { path: { app_id: app.id } }, body: { name } })),
    onSuccess: (k) => {
      setCreated(k);
      form.reset();
      refresh();
    },
  });
  const revoke = useMutation({
    mutationFn: (key_id: string) =>
      unwrap(api.DELETE("/v1/admin/apps/{app_id}/keys/{key_id}", { params: { path: { app_id: app.id, key_id } } })),
    onSuccess: refresh,
  });
  const close = () => {
    setOpen(false);
    setCreated(null);
  };
  return (
    <Section
      title="Keys"
      icon={<IconKey size={18} />}
      description={
        <>
          The Android build sends its key as <code>X-App-Key</code> and a per-install id as <code>X-Device-Id</code>.
        </>
      }
      actions={
        <Button size="xs" onClick={() => setOpen(true)} leftSection={<IconPlus size={14} />}>
          New key
        </Button>
      }
    >
    <Stack gap="sm">
      <TokenTable
        empty="No keys yet"
        emptyHint="Create a key for each Android build or environment."
        tokens={list.data ?? []}
        revoking={revoke.isPending ? revoke.variables : undefined}
        onRevoke={(k) => window.confirm(`Revoke key "${k.name}"? Builds using it stop working.`) && revoke.mutate(k.id)}
      />
      <Modal opened={open} onClose={close} title={created ? "App key created" : "New app key"} size="xl">
        {created ? (
          <Stack>
            <Text size="sm" c="orange">
              Copy it now: it is shown only once.
            </Text>
            <CopyBlock value={created.key} testId="new-app-key" />
            <CopyBlock label="Example calls for the Android team" value={appCurl(window.location.origin, created.key)} />
            <Button onClick={close}>Done</Button>
          </Stack>
        ) : (
          <form onSubmit={form.onSubmit((v) => create.mutate(v.name))}>
            <Stack>
              <TextInput label="Name" placeholder="e.g. android-prod" required data-autofocus {...form.getInputProps("name")} />
              <Button type="submit" loading={create.isPending}>
                Create key
              </Button>
            </Stack>
          </form>
        )}
      </Modal>
    </Stack>
    </Section>
  );
}

function DeleteApp({ app }: { app: AppDetail }) {
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const qc = useQueryClient();
  const navigate = useNavigate();
  const del = useMutation({
    mutationFn: () => unwrap(api.DELETE("/v1/admin/apps/{app_id}", { params: { path: { app_id: app.id } } })),
    onSuccess: () => {
      qc.removeQueries({ queryKey: keys.adminApp(app.id) });
      qc.removeQueries({ queryKey: keys.app(app.id) });
      qc.invalidateQueries({ queryKey: keys.admin });
      qc.invalidateQueries({ queryKey: keys.myApps });
      notifications.show({ color: "green", message: `Deleted ${app.name}` });
      navigate("/admin/apps");
    },
  });
  return (
    <Section
      danger
      title="Danger zone"
      icon={<IconAlertTriangle size={18} />}
      description="Deleting the app stops its keys, removes its templates and members. Old jobs keep its name."
      actions={
        <Button color="red" variant="outline" onClick={() => setOpen(true)} leftSection={<IconTrash size={16} />}>
          Delete app
        </Button>
      }
    >
      <Text size="sm" c="dimmed">
        This can't be undone.
      </Text>
      <Modal opened={open} onClose={() => setOpen(false)} title={`Delete ${app.name}?`}>
        <Stack>
          <Text size="sm" component="ul" m={0} pl="md">
            <li>its app keys stop working right away;</li>
            <li>its templates and members are removed;</li>
            <li>old jobs keep the app's name.</li>
          </Text>
          <TextInput
            label={`Type the app slug "${app.slug}" to confirm`}
            value={typed}
            onChange={(e) => setTyped(e.currentTarget.value)}
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button color="red" disabled={typed !== app.slug} loading={del.isPending} onClick={() => del.mutate()}>
              Delete app
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Section>
  );
}

export function AdminAppPage() {
  const { appId } = useParams();
  const app = useAdminApp(appId!);
  if (app.error) return <Alert color="red">{errorMessage(app.error)}</Alert>;
  if (!app.data)
    return (
      <Stack>
        <Skeleton height={40} width={320} />
        <Skeleton height={300} />
      </Stack>
    );
  const a = app.data;
  return (
    <Stack>
      <Button component={Link} to="/admin/apps" variant="subtle" size="compact-sm" leftSection={<IconArrowLeft size={14} />} w="fit-content">
        Apps
      </Button>
      <Group justify="space-between" wrap="wrap">
        <Group gap="md" wrap="nowrap">
          <AppAvatar name={a.name} slug={a.slug} size={44} />
          <div>
            <Group gap="xs">
              <Title order={3} fz={20}>
                {a.name}
              </Title>
              <Badge
                color={a.status === "active" ? "green" : "gray"}
                leftSection={<StatusDot color={a.status === "active" ? "green" : "gray"} />}
                data-testid="app-status"
              >
                {a.status}
              </Badge>
            </Group>
            <Group gap={6}>
              <PlatformIcon platform={a.platform} size={14} />
              <Text c="dimmed" size="sm">
                {a.slug} · {a.active_template_count ?? 0}/{a.template_count ?? 0} templates active · {a.member_count ?? 0}{" "}
                members
              </Text>
            </Group>
          </div>
        </Group>
        <Group gap="xs">
          <Button
            component={Link}
            to={`/admin/apps/${a.id}/settings`}
            variant="default"
            leftSection={<IconAdjustments size={16} />}
            data-testid="app-settings-link"
          >
            App settings
          </Button>
          <Button component={Link} to={`/apps/${a.id}`} variant="light" rightSection={<IconExternalLink size={16} />}>
            Open dashboard
          </Button>
        </Group>
      </Group>
      <Grid gap="lg">
        <Grid.Col span={{ base: 12, lg: 6 }}>
          <Stack gap="lg">
            <Members app={a} />
            <Keys app={a} />
          </Stack>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 6 }}>
          <Stack gap="lg">
            <Settings key={a.updated_at} app={a} />
            <DeleteApp app={a} />
          </Stack>
        </Grid.Col>
        <Grid.Col span={12}>
          <AppUsers app={a} />
        </Grid.Col>
      </Grid>
    </Stack>
  );
}
