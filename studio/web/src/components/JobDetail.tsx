import {
  Accordion,
  Alert,
  Anchor,
  Badge,
  Button,
  Code,
  Collapse,
  Group,
  Loader,
  Paper,
  Progress,
  SimpleGrid,
  Skeleton,
  Stack,
  Table,
  Text,
  Timeline,
  Tooltip,
} from "@mantine/core";
import {
  IconAlertTriangle,
  IconArrowRight,
  IconBraces,
  IconCheck,
  IconClock,
  IconDownload,
  IconExternalLink,
  IconPlayerPlay,
  IconX,
} from "@tabler/icons-react";
import { useState } from "react";
import { Link } from "react-router";
import { errorMessage } from "../api/client";
import { isTerminal, useJob, useMyApps } from "../api/queries";
import type { Asset, Job, JobInput } from "../api/types";
import { canEdit } from "../auth/roles";
import { age, formatBytes, formatDate, shortId } from "../lib/format";
import { jobOrigin } from "../lib/jobs";
import { JobStatusBadge, MediaView } from "./common";

function AssetCard({ asset, index }: { asset: Asset; index: number }) {
  const ext = asset.mime_type.split("/")[1] ?? "bin";
  return (
    <Paper withBorder p={6} data-testid="asset">
      <MediaView url={asset.url} mime={asset.mime_type} alt={`output ${index + 1}`} />
      <Group justify="space-between" mt={6} gap={4} wrap="nowrap" px={2}>
        <Text size="xs" c="dimmed" truncate>
          {asset.mime_type} · {formatBytes(asset.size_bytes)}
          {asset.width ? ` · ${asset.width}×${asset.height}` : ""}
          {asset.duration_seconds ? ` · ${asset.duration_seconds}s` : ""}
        </Text>
        <Tooltip label="Download">
          <Anchor href={asset.url} download={`${asset.id}.${ext}`} size="xs" aria-label="Download" style={{ display: "inline-flex" }}>
            <IconDownload size={16} />
          </Anchor>
        </Tooltip>
      </Group>
    </Paper>
  );
}

function InputCard({ input }: { input: JobInput }) {
  return (
    <Paper withBorder p={6} data-testid="input">
      <MediaView url={input.url} mime={input.mime_type} alt={`input ${input.slot}`} />
      <Text size="xs" c="dimmed" mt={6} px={2} truncate>
        {input.slot}
        {input.role !== "input" ? ` (${input.role})` : ""} · {input.width}×{input.height}
      </Text>
    </Paper>
  );
}

function Request({ request }: { request: Job["request"] }) {
  const rows = Object.entries(request).filter(([, v]) => v !== null && v !== undefined && v !== "");
  return (
    <Table fz="sm" verticalSpacing={4} withRowBorders={false} highlightOnHover={false}>
      <Table.Tbody>
        {rows.map(([k, v]) => (
          <Table.Tr key={k}>
            <Table.Td c="dimmed" w={150} style={{ verticalAlign: "top" }}>
              {k}
            </Table.Td>
            <Table.Td style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
              {typeof v === "string" ? v : JSON.stringify(v)}
            </Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  );
}

/** Queued / running: what's happening and a moving bar. */
function Progressing({ job }: { job: Job }) {
  const running = job.status === "running";
  return (
    <Paper withBorder p="md" bg="var(--app-subtle)" data-testid="job-progress">
      <Group gap="sm" wrap="nowrap">
        <Loader size="sm" type={running ? "oval" : "dots"} />
        <div style={{ flex: 1 }}>
          <Text size="sm" fw={600}>
            {running ? "Generating…" : "Queued — waiting for a worker"}
          </Text>
          <Text size="xs" c="dimmed">
            {running
              ? `Started ${age(job.started_at)}${job.attempt > 1 ? `, attempt ${job.attempt} of ${job.max_attempts}` : ""}`
              : `Created ${age(job.created_at)}`}
          </Text>
        </div>
      </Group>
      <Progress value={running ? 66 : 20} animated striped mt="sm" size="sm" />
    </Paper>
  );
}

function Outputs({ job }: { job: Job }) {
  const done = isTerminal(job);
  if (job.assets.length) {
    return (
      <Stack gap="sm">
        {job.assets.map((a, n) => (
          <AssetCard key={a.id} asset={a} index={n} />
        ))}
      </Stack>
    );
  }
  if (!done) return <Skeleton height={180} radius="md" animate />;
  return (
    <Paper withBorder p="md" ta="center" c="dimmed">
      <Text size="sm">No output</Text>
    </Paper>
  );
}

export function JobView({ job, showOpenLink }: { job: Job; showOpenLink?: boolean }) {
  const myApps = useMyApps();
  const role = myApps.data?.find((a) => a.id === job.app?.id)?.role;
  const [raw, setRaw] = useState(false);
  const done = isTerminal(job);

  return (
    <Stack gap="md" data-testid="job-detail">
      <Group justify="space-between" wrap="nowrap" align="flex-start">
        <div style={{ minWidth: 0 }}>
          <Group gap="xs">
            <JobStatusBadge status={job.status} />
            <Badge variant="outline" color="gray" tt="capitalize">
              {job.media_type}
            </Badge>
            <Text ff="monospace" size="sm" c="dimmed">
              {shortId(job.id)}
            </Text>
          </Group>
          <Text size="sm" mt={6} truncate>
            {job.template ? job.template.title : "Free prompt"}
            <Text span c="dimmed">
              {" "}
              · {job.provider}/{job.model} · by {jobOrigin(job)}
            </Text>
          </Text>
        </div>
        {showOpenLink && (
          <Button
            component={Link}
            to={`/jobs/${job.id}`}
            size="xs"
            variant="subtle"
            style={{ flexShrink: 0 }}
            rightSection={<IconExternalLink size={14} />}
          >
            Open
          </Button>
        )}
      </Group>

      {!done && <Progressing job={job} />}

      {job.error && (
        <Alert color="red" variant="light" title={job.error.code} icon={<IconAlertTriangle size={18} />} data-testid="job-error">
          {job.error.message ?? "The job failed."}
        </Alert>
      )}

      {job.inputs.length > 0 ? (
        <SimpleGrid cols={2} spacing="sm" data-testid="before-after">
          <Stack gap={6}>
            <Text size="xs" fw={600} c="dimmed" tt="uppercase">
              Before
            </Text>
            {job.inputs.map((i) => (
              <InputCard key={i.id} input={i} />
            ))}
          </Stack>
          <Stack gap={6}>
            <Group gap={4}>
              <Text size="xs" fw={600} c="dimmed" tt="uppercase">
                After
              </Text>
              <IconArrowRight size={12} color="var(--mantine-color-dimmed)" />
            </Group>
            <Outputs job={job} />
          </Stack>
        </SimpleGrid>
      ) : (
        <SimpleGrid cols={{ base: 1, sm: job.assets.length > 1 ? 2 : 1 }} spacing="sm">
          {job.assets.map((a, n) => (
            <AssetCard key={a.id} asset={a} index={n} />
          ))}
          {job.assets.length === 0 && done && (
            <Paper withBorder p="md" ta="center" c="dimmed">
              <Text size="sm">No output</Text>
            </Paper>
          )}
        </SimpleGrid>
      )}

      <Accordion variant="contained" radius="md" multiple defaultValue={[]} chevronPosition="right">
        <Accordion.Item value="details">
          <Accordion.Control icon={<IconClock size={16} />}>
            <Text size="sm">Timeline and request</Text>
          </Accordion.Control>
          <Accordion.Panel>
            <Timeline active={job.finished_at ? 2 : job.started_at ? 1 : 0} bulletSize={20} lineWidth={2} mb="md">
              <Timeline.Item title="Created" bullet={<IconClock size={12} />}>
                <Text size="xs" c="dimmed">
                  {formatDate(job.created_at)}
                </Text>
              </Timeline.Item>
              <Timeline.Item title="Started" bullet={<IconPlayerPlay size={12} />}>
                <Text size="xs" c="dimmed">
                  {formatDate(job.started_at)} · attempt {job.attempt} of {job.max_attempts}
                </Text>
              </Timeline.Item>
              <Timeline.Item
                title={job.status === "failed" ? "Failed" : "Finished"}
                color={job.status === "failed" ? "red" : undefined}
                bullet={job.status === "failed" ? <IconX size={12} /> : <IconCheck size={12} />}
              >
                <Text size="xs" c="dimmed">
                  {done ? formatDate(job.finished_at) : "waiting…"}
                </Text>
              </Timeline.Item>
            </Timeline>
            <Stack gap={4}>
              {job.app && (
                <Text size="sm">
                  App:{" "}
                  <Anchor component={Link} to={`/apps/${job.app.id}`} data-testid="job-app-link">
                    {job.app.name}
                  </Anchor>
                  {job.app.device_id && (
                    <Text span c="dimmed">
                      {" "}
                      (device {job.app.device_id})
                    </Text>
                  )}
                </Text>
              )}
              {job.template && (
                <Text size="sm">
                  Template:{" "}
                  {canEdit(role) && job.app ? (
                    <Anchor component={Link} to={`/apps/${job.app.id}/templates/${job.template.id}`}>
                      {job.template.title}
                    </Anchor>
                  ) : (
                    job.template.title
                  )}{" "}
                  <Text span c="dimmed">
                    ({job.template.slug}, version {job.template.version ?? "?"})
                  </Text>
                </Text>
              )}
              {job.webhook && (
                <Text size="sm">
                  Webhook: {job.webhook.url} — {job.webhook.status ?? "pending"} ({job.webhook.attempts} attempts)
                </Text>
              )}
            </Stack>
            <Text size="xs" fw={600} c="dimmed" tt="uppercase" mt="md" mb={4}>
              Request
            </Text>
            <Request request={job.request} />
          </Accordion.Panel>
        </Accordion.Item>
      </Accordion>

      <div>
        <Button size="compact-xs" variant="subtle" color="gray" leftSection={<IconBraces size={14} />} onClick={() => setRaw((r) => !r)}>
          {raw ? "Hide raw JSON" : "Raw JSON"}
        </Button>
        <Collapse expanded={raw}>
          <Code block mt={4} style={{ maxHeight: 360, overflow: "auto" }}>
            {JSON.stringify(job, null, 2)}
          </Code>
        </Collapse>
      </div>
    </Stack>
  );
}

/** Loads and polls a job (every 1.5 s until it is terminal). */
export function JobDetail({ id, showOpenLink }: { id: string; showOpenLink?: boolean }) {
  const job = useJob(id);
  if (job.error) return <Alert color="red">{errorMessage(job.error)}</Alert>;
  if (!job.data)
    return (
      <Stack>
        <Skeleton height={24} width="60%" />
        <Skeleton height={200} />
      </Stack>
    );
  return <JobView job={job.data} showOpenLink={showOpenLink} />;
}
