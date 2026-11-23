import { Alert, Box, Center, Group, Image, Paper, SegmentedControl, Select, Stack, Table, Text, Title, Tooltip } from "@mantine/core";
import { IconBrandAndroid, IconDeviceDesktop, IconInbox, IconPhoto } from "@tabler/icons-react";
import { useState } from "react";
import { errorMessage } from "../api/client";
import { useAppJobs, useAppTemplates, useManageTemplates, type JobFilter } from "../api/queries";
import type { Job, JobStatus } from "../api/types";
import { useCurrentApp } from "../auth/appContext";
import { canEdit } from "../auth/roles";
import { useSession } from "../auth/session";
import { age, shortId } from "../lib/format";
import { jobOrigin } from "../lib/jobs";
import { JobStatusBadge } from "./common";
import { EmptyState, ListSkeleton } from "./ui";

function TemplateFilter({ value, onChange }: { value?: string; onChange: (v?: string) => void }) {
  const app = useCurrentApp();
  const editor = canEdit(app.role);
  const manage = useManageTemplates(app.id, editor);
  const active = useAppTemplates(app.id, !editor);
  const options = (editor ? manage.data : active.data)?.map((t) => ({ value: t.id, label: t.title })) ?? [];
  return (
    <Select
      size="xs"
      placeholder="Any template"
      data={options}
      value={value ?? null}
      onChange={(v) => onChange(v ?? undefined)}
      clearable
      searchable
      w={170}
      aria-label="Template filter"
    />
  );
}

function what(job: Job, editor: boolean): string {
  if (job.template) return job.template.title;
  const prompt = typeof job.request.prompt === "string" ? job.request.prompt : "";
  return editor && prompt ? prompt : "Free prompt";
}

function Thumb({ job }: { job: Job }) {
  const asset = job.assets.find((a) => a.mime_type.startsWith("image/"));
  return asset ? (
    <Image src={asset.url} alt="" h={36} w={36} fit="cover" radius="sm" />
  ) : (
    <Center h={36} w={36} bg="var(--app-subtle)" c="dimmed" style={{ borderRadius: 6 }}>
      <IconPhoto size={16} stroke={1.4} />
    </Center>
  );
}

function Source({ job }: { job: Job }) {
  const fromApp = !job.created_by && !!job.app;
  const Icon = fromApp ? IconBrandAndroid : IconDeviceDesktop;
  return (
    <Tooltip label={fromApp ? "Android app" : "Console"}>
      <Box c="dimmed" style={{ display: "inline-flex" }} aria-label={fromApp ? "from the Android app" : "from the console"}>
        <Icon size={16} stroke={1.6} />
      </Box>
    </Tooltip>
  );
}

/** The current app's jobs, with filters. Testers only ever get their own (the server enforces it). */
export function JobList({
  selectedId,
  onSelect,
  title = "Jobs",
}: {
  selectedId?: string;
  onSelect: (id: string) => void;
  title?: string;
}) {
  const me = useSession();
  const app = useCurrentApp();
  const editor = canEdit(app.role);
  const [status, setStatus] = useState<JobStatus | undefined>();
  const [template, setTemplate] = useState<string | undefined>();
  const [scope, setScope] = useState<"mine" | "everyone">("mine");
  const [source, setSource] = useState<"any" | "console" | "app">("any");

  const filter: JobFilter = { status, template };
  if (editor && scope === "mine" && source !== "app") filter.created_by = me.id;
  if (editor && source !== "any") filter.source = source;
  const jobs = useAppJobs(app.id, filter);

  return (
    <Stack gap="sm">
      <Group justify="space-between" wrap="wrap">
        <Title order={3} fz={18}>
          {title}
        </Title>
        <Group gap="xs" wrap="wrap">
          {editor && (
            <>
              <SegmentedControl
                size="xs"
                value={scope}
                onChange={(v) => setScope(v as "mine" | "everyone")}
                data={[
                  { value: "mine", label: "Mine" },
                  { value: "everyone", label: "Everyone" },
                ]}
              />
              <Select
                size="xs"
                w={140}
                aria-label="Source filter"
                data={[
                  { value: "any", label: "Any source" },
                  { value: "console", label: "Console" },
                  { value: "app", label: "Android app" },
                ]}
                value={source}
                onChange={(v) => setSource((v as "any" | "console" | "app") ?? "any")}
                allowDeselect={false}
              />
            </>
          )}
          <Select
            size="xs"
            placeholder="Any status"
            data={["queued", "running", "succeeded", "failed"]}
            value={status ?? null}
            onChange={(v) => setStatus((v as JobStatus) ?? undefined)}
            clearable
            w={130}
            aria-label="Status filter"
          />
          <TemplateFilter value={template} onChange={setTemplate} />
        </Group>
      </Group>
      {jobs.error && <Alert color="red">{errorMessage(jobs.error)}</Alert>}
      <Paper withBorder className="table-card">
        {jobs.isPending ? (
          <Box p="md">
            <ListSkeleton rows={4} />
          </Box>
        ) : jobs.data?.items.length === 0 ? (
          <EmptyState
            icon={<IconInbox size={26} stroke={1.5} />}
            title="No jobs yet"
            description={editor ? "Jobs from tests, free prompts and the Android app appear here." : "Run a template to see your jobs here."}
          />
        ) : (
          <Table.ScrollContainer minWidth={720}>
            <Table data-testid="job-list" verticalSpacing="xs">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th w={52} />
                  <Table.Th>Status</Table.Th>
                  <Table.Th>Template / prompt</Table.Th>
                  <Table.Th w={40}>Src</Table.Th>
                  <Table.Th>By</Table.Th>
                  <Table.Th>Model</Table.Th>
                  <Table.Th>When</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {jobs.data?.items.map((j) => (
                  <Table.Tr
                    key={j.id}
                    data-job={j.id}
                    onClick={() => onSelect(j.id)}
                    onKeyDown={(e) => e.key === "Enter" && onSelect(j.id)}
                    tabIndex={0}
                    style={{ cursor: "pointer" }}
                    bg={j.id === selectedId ? "var(--mantine-primary-color-light)" : undefined}
                  >
                    <Table.Td>
                      <Thumb job={j} />
                    </Table.Td>
                    <Table.Td>
                      <Group gap={4} wrap="nowrap">
                        <JobStatusBadge status={j.status} />
                        {j.attempt > 1 && (
                          <Text size="xs" c="dimmed">
                            try {j.attempt}
                          </Text>
                        )}
                      </Group>
                    </Table.Td>
                    <Table.Td maw={260}>
                      <Text size="sm" fw={500} truncate>
                        {what(j, editor)}
                      </Text>
                      <Text size="xs" c="dimmed" ff="monospace">
                        {shortId(j.id)}
                        {j.template?.version ? ` · v${j.template.version}` : ""}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Source job={j} />
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" truncate maw={220}>
                        {jobOrigin(j)}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="xs" c="dimmed">
                        {j.provider}/{j.model}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" c="dimmed" className="tabular">
                        {age(j.created_at)}
                      </Text>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        )}
      </Paper>
    </Stack>
  );
}
