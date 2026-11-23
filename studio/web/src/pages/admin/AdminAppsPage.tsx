import { Alert, Badge, Button, Group, Modal, Paper, Stack, Table, Text } from "@mantine/core";
import { IconApps, IconPlus } from "@tabler/icons-react";
import { AppAvatar, EmptyState, PlatformIcon, StatusDot } from "../../components/ui";
import { useForm } from "@mantine/form";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router";
import { api, errorMessage, unwrap } from "../../api/client";
import { keys, useAdminApps } from "../../api/queries";
import { AppFields } from "../../components/AppForm";
import { appBody, EMPTY_APP, type AppFormValues } from "../../lib/appForm";
import { age } from "../../lib/format";
import { fieldErrors } from "../../lib/formErrors";

function NewApp() {
  const [open, setOpen] = useState(false);
  const qc = useQueryClient();
  const navigate = useNavigate();
  const form = useForm<AppFormValues>({
    initialValues: EMPTY_APP,
    validate: {
      slug: (s) => (/^[a-z0-9-]{3,64}$/.test(s) ? null : "3-64 characters: a-z, 0-9 and -"),
      name: (s) => (s.trim() ? null : "Required"),
    },
  });
  const create = useMutation({
    meta: { quiet: true },
    mutationFn: (v: AppFormValues) => unwrap(api.POST("/v1/admin/apps", { body: { ...appBody(v), slug: v.slug } })),
    onSuccess: (app) => {
      qc.invalidateQueries({ queryKey: keys.adminApps });
      qc.invalidateQueries({ queryKey: keys.myApps });
      navigate(`/admin/apps/${app.id}`);
    },
    onError: (e) => form.setErrors(fieldErrors(e, (p) => p in form.values).errors),
  });
  const rest = fieldErrors(create.error, (p) => p in form.values).rest;
  return (
    <>
      <Button onClick={() => setOpen(true)} leftSection={<IconPlus size={16} />}>
        New app
      </Button>
      <Modal opened={open} onClose={() => setOpen(false)} title="New app" size="lg">
        <form onSubmit={form.onSubmit((v) => create.mutate(v))}>
          <Stack>
            {create.error && (rest.length > 0 || !Object.keys(form.errors).length) && (
              <Alert color="red">{rest.length ? rest.join("; ") : errorMessage(create.error)}</Alert>
            )}
            <AppFields form={form} creating />
            <Button type="submit" loading={create.isPending}>
              Create app
            </Button>
          </Stack>
        </form>
      </Modal>
    </>
  );
}

export function AdminAppsPage() {
  const apps = useAdminApps();
  const navigate = useNavigate();
  return (
    <Stack>
      <Group justify="space-between">
        <Text size="sm" c="dimmed">
          Each app is a workspace: its templates, its members (editors and testers) and the keys its Android build uses.
        </Text>
        <NewApp />
      </Group>
      {apps.error && <Alert color="red">{errorMessage(apps.error)}</Alert>}
      <Paper withBorder className="table-card">
      <Table.ScrollContainer minWidth={850}>
        <Table data-testid="admin-apps-table">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Name</Table.Th>
              <Table.Th>Slug</Table.Th>
              <Table.Th>Platform</Table.Th>
              <Table.Th>Status</Table.Th>
              <Table.Th>Templates</Table.Th>
              <Table.Th>Members</Table.Th>
              <Table.Th>Keys</Table.Th>
              <Table.Th>Limits</Table.Th>
              <Table.Th>Updated</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {apps.data?.map((a) => (
              <Table.Tr
                key={a.id}
                data-slug={a.slug}
                style={{ cursor: "pointer" }}
                onClick={() => navigate(`/admin/apps/${a.id}`)}
              >
                <Table.Td>
                  <Group gap="sm" wrap="nowrap">
                    <AppAvatar name={a.name} slug={a.slug} size={32} />
                    <Text size="sm" fw={500}>
                      {a.name}
                    </Text>
                  </Group>
                </Table.Td>
                <Table.Td ff="monospace" fz="sm">
                  {a.slug}
                </Table.Td>
                <Table.Td>
                  <Group gap={6} wrap="nowrap">
                    <PlatformIcon platform={a.platform} />
                    <Text size="sm">{a.platform}</Text>
                  </Group>
                </Table.Td>
                <Table.Td>
                  <Badge
                    color={a.status === "active" ? "green" : "gray"}
                    leftSection={<StatusDot color={a.status === "active" ? "green" : "gray"} />}
                  >
                    {a.status}
                  </Badge>
                </Table.Td>
                <Table.Td>
                  {a.active_template_count ?? 0} / {a.template_count ?? 0}
                </Table.Td>
                <Table.Td>{a.member_count ?? 0}</Table.Td>
                <Table.Td>{a.active_key_count ?? 0}</Table.Td>
                <Table.Td>
                  {a.daily_job_limit ?? "∞"}/day · {a.device_hourly_limit ?? "∞"}/device/h
                </Table.Td>
                <Table.Td>{age(a.updated_at)}</Table.Td>
              </Table.Tr>
            ))}
            {apps.data?.length === 0 && (
              <Table.Tr>
                <Table.Td colSpan={9}>
                  <EmptyState
                    icon={<IconApps size={26} stroke={1.5} />}
                    title="No apps yet"
                    description="An app is a workspace: its templates, members and Android keys."
                  />
                </Table.Td>
              </Table.Tr>
            )}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      </Paper>
    </Stack>
  );
}
