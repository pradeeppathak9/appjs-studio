import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Card,
  Center,
  Group,
  Image,
  Menu,
  Modal,
  Paper,
  SegmentedControl,
  Select,
  SimpleGrid,
  Skeleton,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
  Tooltip,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import {
  IconArrowDown,
  IconArrowUp,
  IconCopy,
  IconDots,
  IconEye,
  IconEyeOff,
  IconFlask,
  IconGripVertical,
  IconLayoutGrid,
  IconPencil,
  IconPhoto,
  IconPlus,
  IconTable,
  IconTemplate,
  IconTrash,
} from "@tabler/icons-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type DragEvent } from "react";
import { Link, useNavigate } from "react-router";
import { api, errorWithDetails, errorMessage, unwrap } from "../../api/client";
import { keys, useAppTemplates, useManageTemplates, useMyApps } from "../../api/queries";
import type { TemplateFull } from "../../api/types";
import { useCurrentApp } from "../../auth/appContext";
import { canEdit } from "../../auth/roles";
import { TemplateStatusBadge } from "../../components/common";
import { CoverImage, TemplateCard } from "../../components/TemplateCard";
import { AppAvatar, EmptyState } from "../../components/ui";
import { age } from "../../lib/format";
import { moveItem } from "../../lib/reorder";

const VIEW_KEY = "studio-templates-view";
type View = "grid" | "table";

function readView(): View {
  try {
    return window.localStorage.getItem(VIEW_KEY) === "table" ? "table" : "grid";
  } catch {
    return "grid";
  }
}

function useRefreshApp() {
  const qc = useQueryClient();
  const app = useCurrentApp();
  return () => {
    qc.invalidateQueries({ queryKey: keys.app(app.id) });
    qc.invalidateQueries({ queryKey: keys.myApps });
  };
}

function CopyDialog({ template, onClose }: { template: TemplateFull; onClose: () => void }) {
  const app = useCurrentApp();
  const myApps = useMyApps();
  const qc = useQueryClient();
  const targets = (myApps.data ?? []).filter((a) => a.id !== app.id && canEdit(a.role));
  const [target, setTarget] = useState<string | null>(null);
  const [slug, setSlug] = useState("");
  const copy = useMutation({
    meta: { quiet: true },
    mutationFn: () =>
      unwrap(
        api.POST("/v1/apps/{app_id}/manage/templates/{template_id}/copy", {
          params: { path: { app_id: app.id, template_id: template.id } },
          body: { target_app_id: target!, slug: slug.trim() || null },
        }),
      ),
    onSuccess: (saved) => {
      const to = targets.find((a) => a.id === target);
      qc.invalidateQueries({ queryKey: keys.app(target!) });
      qc.invalidateQueries({ queryKey: keys.myApps });
      notifications.show({
        color: "green",
        title: "Template copied",
        message: `Copied to ${to?.name ?? "the app"} as draft "${saved.template.slug}"`,
      });
      onClose();
    },
  });
  return (
    <Modal opened onClose={onClose} title={`Copy "${template.title}" to another app`}>
      <Stack>
        <Text size="sm" c="dimmed">
          The copy starts as a draft (version 1) in the target app. Only apps where you can edit are listed.
        </Text>
        {copy.error && <Alert color="red">{errorWithDetails(copy.error)}</Alert>}
        <Select
          label="Target app"
          data={targets.map((a) => ({ value: a.id, label: a.name }))}
          value={target}
          onChange={setTarget}
          placeholder={targets.length ? "Pick an app" : "No other app where you are an editor"}
          allowDeselect={false}
          renderOption={({ option }) => {
            const a = targets.find((x) => x.id === option.value)!;
            return (
              <Group gap="sm">
                <AppAvatar name={a.name} slug={a.slug} size={22} />
                <Text size="sm">{a.name}</Text>
              </Group>
            );
          }}
        />
        <TextInput
          label="New slug"
          description={`Optional; defaults to "${template.slug}"`}
          value={slug}
          onChange={(e) => setSlug(e.currentTarget.value)}
        />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!target} loading={copy.isPending} onClick={() => copy.mutate()} leftSection={<IconCopy size={16} />}>
            Copy
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}

function DeleteDialog({ template, onClose }: { template: TemplateFull; onClose: () => void }) {
  const app = useCurrentApp();
  const refresh = useRefreshApp();
  const del = useMutation({
    mutationFn: () =>
      unwrap(
        api.DELETE("/v1/apps/{app_id}/manage/templates/{template_id}", {
          params: { path: { app_id: app.id, template_id: template.id } },
        }),
      ),
    onSuccess: () => {
      refresh();
      notifications.show({ color: "green", title: "Template deleted", message: template.title });
      onClose();
    },
  });
  return (
    <Modal opened onClose={onClose} title={`Delete "${template.title}"?`}>
      <Stack>
        <Text size="sm">
          It disappears from {app.name} and from the Android app right away. Past jobs keep its name.
        </Text>
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button color="red" loading={del.isPending} onClick={() => del.mutate()} leftSection={<IconTrash size={16} />}>
            Delete template
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}

type Actions = {
  edit: (t: TemplateFull) => void;
  test: (t: TemplateFull) => void;
  toggle: (t: TemplateFull) => void;
  move: (i: number, d: -1 | 1) => void;
  copy: (t: TemplateFull) => void;
  remove: (t: TemplateFull) => void;
  busy: boolean;
};

function ActionsMenu({ t, i, count, a }: { t: TemplateFull; i: number; count: number; a: Actions }) {
  return (
    <Menu position="bottom-end" width={200}>
      <Menu.Target>
        <ActionIcon variant="subtle" color="gray" aria-label={`Actions for ${t.slug}`} onClick={(e) => e.stopPropagation()}>
          <IconDots size={18} />
        </ActionIcon>
      </Menu.Target>
      <Menu.Dropdown onClick={(e) => e.stopPropagation()}>
        <Menu.Item leftSection={<IconFlask size={16} />} onClick={() => a.test(t)}>
          Test
        </Menu.Item>
        <Menu.Item
          leftSection={t.status === "active" ? <IconEyeOff size={16} /> : <IconEye size={16} />}
          onClick={() => a.toggle(t)}
        >
          {t.status === "active" ? "Deactivate" : "Activate"}
        </Menu.Item>
        <Menu.Item leftSection={<IconArrowUp size={16} />} disabled={i === 0 || a.busy} onClick={() => a.move(i, -1)}>
          Move up
        </Menu.Item>
        <Menu.Item leftSection={<IconArrowDown size={16} />} disabled={i === count - 1 || a.busy} onClick={() => a.move(i, 1)}>
          Move down
        </Menu.Item>
        <Menu.Item leftSection={<IconCopy size={16} />} onClick={() => a.copy(t)}>
          Copy to app…
        </Menu.Item>
        <Menu.Divider />
        <Menu.Item color="red" leftSection={<IconTrash size={16} />} onClick={() => a.remove(t)}>
          Delete
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}

/** HTML5 drag-and-drop between items; drop sends the full new order. */
function useDragOrder(count: number, onDrop: (from: number, to: number) => void) {
  const [from, setFrom] = useState<number | null>(null);
  const [over, setOver] = useState<number | null>(null);
  const reset = () => {
    setFrom(null);
    setOver(null);
  };
  return (i: number) => ({
    draggable: count > 1,
    onDragStart: (e: DragEvent) => {
      setFrom(i);
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", String(i));
    },
    onDragOver: (e: DragEvent) => {
      e.preventDefault();
      if (over !== i) setOver(i);
    },
    onDrop: (e: DragEvent) => {
      e.preventDefault();
      if (from !== null && from !== i) onDrop(from, i);
      reset();
    },
    onDragEnd: reset,
    "data-dragging": from === i || undefined,
    "data-drop-target": (over === i && from !== null && from !== i) || undefined,
  });
}

function DragHandle({ title }: { title: string }) {
  return (
    <Tooltip label="Drag to reorder">
      <span className="drag-handle" aria-label={`Drag ${title} to reorder`} role="img" style={{ display: "inline-flex" }}>
        <IconGripVertical size={16} />
      </span>
    </Tooltip>
  );
}

function GridView({ list, a, drag }: { list: TemplateFull[]; a: Actions; drag: ReturnType<typeof useDragOrder> }) {
  return (
    <SimpleGrid cols={{ base: 1, xs: 2, md: 3, lg: 4 }} spacing="lg">
      {list.map((t, i) => {
        const draft = t.status !== "active";
        return (
          <Card
            key={t.id}
            padding="md"
            className="hover-card"
            data-testid="template-item"
            data-slug={t.slug}
            {...drag(i)}
            style={{ cursor: "pointer", ...(draft ? { borderStyle: "dashed" } : {}) }}
            onClick={() => a.edit(t)}
          >
            <Card.Section pos="relative">
              <CoverImage src={t.cover_url} alt={`${t.title} cover`} muted={draft} />
              <Badge pos="absolute" top={8} left={8} color="dark" variant="filled" size="sm" className="tabular">
                #{i + 1}
              </Badge>
            </Card.Section>
            <Group justify="space-between" mt="sm" wrap="nowrap" gap="xs">
              <Text fw={600} truncate c={draft ? "dimmed" : undefined}>
                {t.title}
              </Text>
              <TemplateStatusBadge status={t.status} />
            </Group>
            <Text size="xs" c="dimmed" ff="monospace" truncate>
              {t.slug}
            </Text>
            <Text size="xs" c="dimmed" mt={6}>
              v{t.current_version} · {t.current.created_by.name}, {age(t.updated_at)}
            </Text>
            <Group justify="space-between" mt="md" wrap="nowrap">
              <Group gap={6} wrap="nowrap">
                <DragHandle title={t.title} />
                <Button
                  size="xs"
                  variant="light"
                  leftSection={<IconPencil size={14} />}
                  onClick={(e) => {
                    e.stopPropagation();
                    a.edit(t);
                  }}
                >
                  Edit
                </Button>
              </Group>
              <ActionsMenu t={t} i={i} count={list.length} a={a} />
            </Group>
          </Card>
        );
      })}
    </SimpleGrid>
  );
}

function TableView({ list, a, drag }: { list: TemplateFull[]; a: Actions; drag: ReturnType<typeof useDragOrder> }) {
  return (
    <Paper withBorder className="table-card">
      <Table.ScrollContainer minWidth={760}>
        <Table data-testid="templates-table">
          <Table.Thead>
            <Table.Tr>
              <Table.Th w={36} />
              <Table.Th w={40}>#</Table.Th>
              <Table.Th w={72} />
              <Table.Th>Title</Table.Th>
              <Table.Th>Status</Table.Th>
              <Table.Th>Version</Table.Th>
              <Table.Th>Last edited</Table.Th>
              <Table.Th w={120} />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {list.map((t, i) => (
              <Table.Tr key={t.id} data-testid="template-item" data-slug={t.slug} {...drag(i)}>
                <Table.Td>
                  <DragHandle title={t.title} />
                </Table.Td>
                <Table.Td c="dimmed" className="tabular">
                  {i + 1}
                </Table.Td>
                <Table.Td>
                  {t.cover_url ? (
                    <Image src={t.cover_url} alt="" h={40} w={64} fit="cover" radius="sm" />
                  ) : (
                    <Center h={40} w={64} bg="var(--app-subtle)" c="dimmed" style={{ borderRadius: 6 }}>
                      <IconPhoto size={18} stroke={1.4} />
                    </Center>
                  )}
                </Table.Td>
                <Table.Td>
                  <Text component={Link} to={`/apps/${t.app_id}/templates/${t.id}`} fw={600} size="sm" c={t.status === "active" ? "inherit" : "dimmed"} style={{ textDecoration: "none" }}>
                    {t.title}
                  </Text>
                  <Text size="xs" c="dimmed" ff="monospace">
                    {t.slug} · {t.current.provider}/{t.current.model}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <TemplateStatusBadge status={t.status} />
                </Table.Td>
                <Table.Td className="tabular">v{t.current_version}</Table.Td>
                <Table.Td>
                  <Text size="sm">{t.current.created_by.name}</Text>
                  <Text size="xs" c="dimmed">
                    {age(t.updated_at)}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Group gap={4} wrap="nowrap" justify="flex-end">
                    <Button size="xs" variant="default" leftSection={<IconPencil size={14} />} onClick={() => a.edit(t)}>
                      Edit
                    </Button>
                    <ActionsMenu t={t} i={i} count={list.length} a={a} />
                  </Group>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Paper>
  );
}

function EditorList() {
  const app = useCurrentApp();
  const navigate = useNavigate();
  const templates = useManageTemplates(app.id);
  const refresh = useRefreshApp();
  const [view, setView] = useState<View>(readView);
  const [copying, setCopying] = useState<TemplateFull | null>(null);
  const [deleting, setDeleting] = useState<TemplateFull | null>(null);
  const list = [...(templates.data ?? [])].sort((a, b) => a.position - b.position);

  const order = useMutation({
    mutationFn: (template_ids: string[]) =>
      unwrap(
        api.PUT("/v1/apps/{app_id}/manage/templates/order", { params: { path: { app_id: app.id } }, body: { template_ids } }),
      ),
    onSettled: refresh,
  });
  const status = useMutation({
    mutationFn: (v: { t: TemplateFull; status: "draft" | "active" }) =>
      unwrap(
        api.POST("/v1/apps/{app_id}/manage/templates/{template_id}/status", {
          params: { path: { app_id: app.id, template_id: v.t.id } },
          body: { status: v.status },
        }),
      ),
    onSuccess: (_r, v) => {
      refresh();
      notifications.show({
        color: "green",
        message: v.status === "active" ? `${v.t.title} is live in the app` : `${v.t.title} is now a draft (hidden from the app)`,
      });
    },
  });
  const reorder = (from: number, to: number) => order.mutate(moveItem(list.map((t) => t.id), from, to));
  const drag = useDragOrder(list.length, reorder);
  const actions: Actions = {
    edit: (t) => navigate(`/apps/${app.id}/templates/${t.id}`),
    test: (t) => navigate(`/apps/${app.id}/test?t=${t.slug}`),
    toggle: (t) => status.mutate({ t, status: t.status === "active" ? "draft" : "active" }),
    move: (i, d) => reorder(i, i + d),
    copy: setCopying,
    remove: setDeleting,
    busy: order.isPending,
  };
  const changeView = (v: string) => {
    setView(v as View);
    try {
      window.localStorage.setItem(VIEW_KEY, v);
    } catch {
      /* storage unavailable */
    }
  };

  return (
    <Stack>
      <Group justify="space-between" wrap="wrap">
        <div>
          <Title order={3} fz={18}>
            Templates
          </Title>
          <Text size="sm" c="dimmed">
            The Android app shows active templates in this order. Drag to reorder.
          </Text>
        </div>
        <Group gap="sm">
          <SegmentedControl
            value={view}
            onChange={changeView}
            aria-label="View"
            data={[
              { value: "grid", label: <Center aria-label="Grid view"><IconLayoutGrid size={16} /></Center> },
              { value: "table", label: <Center aria-label="Table view"><IconTable size={16} /></Center> },
            ]}
          />
          <Button component={Link} to={`/apps/${app.id}/templates/new`} leftSection={<IconPlus size={16} />}>
            New template
          </Button>
        </Group>
      </Group>
      {templates.error && <Alert color="red">{errorMessage(templates.error)}</Alert>}
      {templates.isPending && (
        <SimpleGrid cols={{ base: 1, xs: 2, md: 3, lg: 4 }} spacing="lg">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} height={260} radius="md" />
          ))}
        </SimpleGrid>
      )}
      {templates.data && list.length === 0 && (
        <Card padding="xl">
          <EmptyState
            icon={<IconTemplate size={30} stroke={1.5} />}
            title="No templates yet"
            description="A template is a prompt, image slots and a model. Create one, test it, then activate it for the app."
            action={
              <Button component={Link} to={`/apps/${app.id}/templates/new`} leftSection={<IconPlus size={16} />}>
                New template
              </Button>
            }
          />
        </Card>
      )}
      {list.length > 0 &&
        (view === "grid" ? <GridView list={list} a={actions} drag={drag} /> : <TableView list={list} a={actions} drag={drag} />)}
      {copying && <CopyDialog template={copying} onClose={() => setCopying(null)} />}
      {deleting && <DeleteDialog template={deleting} onClose={() => setDeleting(null)} />}
    </Stack>
  );
}

function TesterList() {
  const app = useCurrentApp();
  const navigate = useNavigate();
  const templates = useAppTemplates(app.id);
  return (
    <Stack>
      <div>
        <Title order={3} fz={18}>
          Templates
        </Title>
        <Text size="sm" c="dimmed">
          Active templates in {app.name}. Pick one to try it with your own photo.
        </Text>
      </div>
      {templates.error && <Alert color="red">{errorMessage(templates.error)}</Alert>}
      {templates.isPending && (
        <SimpleGrid cols={{ base: 1, xs: 2, md: 3, lg: 4 }} spacing="lg">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} height={260} radius="md" />
          ))}
        </SimpleGrid>
      )}
      {templates.data?.length === 0 && (
        <Card padding="xl">
          <EmptyState
            icon={<IconTemplate size={30} stroke={1.5} />}
            title="No active templates yet"
            description="Editors of this app haven't activated any templates."
          />
        </Card>
      )}
      <SimpleGrid cols={{ base: 1, xs: 2, md: 3, lg: 4 }} spacing="lg">
        {templates.data?.map((t) => (
          <TemplateCard
            key={t.id}
            template={t}
            footer={
              <Button
                fullWidth
                variant="light"
                leftSection={<IconFlask size={16} />}
                onClick={() => navigate(`/apps/${app.id}/test?t=${t.slug}`)}
              >
                Test
              </Button>
            }
          />
        ))}
      </SimpleGrid>
    </Stack>
  );
}

export function AppTemplatesPage() {
  const app = useCurrentApp();
  return canEdit(app.role) ? <EditorList /> : <TesterList />;
}
