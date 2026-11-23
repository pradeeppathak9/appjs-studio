import { ActionIcon, Alert, Badge, Card, Group, SimpleGrid, Skeleton, Stack, Text, Tooltip } from "@mantine/core";
import { IconAlertTriangle, IconApps, IconCircleCheck, IconChevronRight, IconExternalLink } from "@tabler/icons-react";
import { useNavigate } from "react-router";
import { errorMessage } from "../api/client";
import { useApps } from "../api/queries";
import type { App } from "../api/types";
import { useSession } from "../auth/session";
import { AppAvatar, EmptyState, EnvBadge, GatewayBadge, PageHeader, StatusDot } from "../components/ui";
import { gatewaysOf } from "../lib/gateways";

function AppCard({ app }: { app: App }) {
  const navigate = useNavigate();
  const open = () => navigate(`/apps/${app.id}`);
  const gateways = gatewaysOf(app);
  return (
    <Card
      padding="lg"
      className="hover-card"
      style={{ cursor: "pointer" }}
      onClick={open}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && open()}
      tabIndex={0}
      role="link"
      aria-label={`Open ${app.name}`}
      data-testid="app-card"
    >
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <Group gap="md" wrap="nowrap" style={{ minWidth: 0 }}>
          <AppAvatar name={app.name} id={app.id} size={44} />
          <div style={{ minWidth: 0 }}>
            <Text fw={650} truncate>
              {app.name}
            </Text>
            <Text size="xs" c="dimmed" ff="monospace" truncate>
              {app.id}
            </Text>
          </div>
        </Group>
        {/* A real link, so ctrl/cmd-click and "open in new tab" keep working. */}
        <Tooltip label="Open in a new tab">
          <ActionIcon
            component="a"
            href={`/apps/${app.id}`}
            target="_blank"
            rel="noopener noreferrer"
            variant="subtle"
            color="gray"
            aria-label={`Open ${app.name} in a new tab`}
            onClick={(e) => e.stopPropagation()}
          >
            <IconExternalLink size={16} stroke={1.6} />
          </ActionIcon>
        </Tooltip>
      </Group>

      <Stack gap={8} mt="md" mih={64}>
        {gateways.length === 0 && (
          <Text size="sm" c="dimmed">
            No payment gateway enabled.
          </Text>
        )}
        {gateways.map((g) => (
          <Group key={g.gateway} gap="xs" wrap="nowrap">
            <GatewayBadge gateway={g.gateway} />
            <EnvBadge env={g.env} live={g.live} />
            {g.connected ? (
              <Group gap={4} wrap="nowrap">
                <IconCircleCheck size={14} color="var(--mantine-color-green-filled)" />
                <Text size="xs" c="dimmed">
                  Connected
                </Text>
              </Group>
            ) : (
              <Group gap={4} wrap="nowrap">
                <IconAlertTriangle size={14} color="var(--mantine-color-yellow-filled)" />
                <Text size="xs" c="yellow.8">
                  Credentials not set
                </Text>
              </Group>
            )}
          </Group>
        ))}
      </Stack>

      <Group justify="space-between" mt="md" pt="md" style={{ borderTop: "1px solid var(--mantine-color-default-border)" }}>
        <Group gap={6}>
          <StatusDot color={app.enabled ? "green" : "gray"} />
          <Text size="sm" c={app.enabled ? undefined : "dimmed"}>
            {app.enabled ? "Enabled" : "Disabled"}
          </Text>
        </Group>
        <IconChevronRight size={18} stroke={1.6} color="var(--mantine-color-dimmed)" />
      </Group>
    </Card>
  );
}

/** Everyone lands here after signing in: the apps they have access to. */
export function AppsPage() {
  const me = useSession();
  const apps = useApps();
  const count = apps.data?.length;
  return (
    <Stack gap={0}>
      <PageHeader
        title={
          <Group gap="xs" component="span">
            Your apps
            {count !== undefined && (
              <Badge color="gray" variant="light" size="lg" className="tabular">
                {count}
              </Badge>
            )}
          </Group>
        }
        description="Each app has its own gateway credentials, API key and integration URLs."
      />
      {apps.error && <Alert color="red">{errorMessage(apps.error)}</Alert>}
      {apps.isPending && (
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="lg">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} height={200} radius="md" />
          ))}
        </SimpleGrid>
      )}
      {count === 0 && (
        <Card padding="xl">
          <EmptyState
            icon={<IconApps size={30} stroke={1.5} />}
            title="No apps yet"
            description={
              me.is_admin ? "Create the first app under Admin → Apps." : "Ask an admin to create an app for you. It will show up here."
            }
          />
        </Card>
      )}
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="lg">
        {apps.data?.map((a) => (
          <AppCard key={a.id} app={a} />
        ))}
      </SimpleGrid>
    </Stack>
  );
}
