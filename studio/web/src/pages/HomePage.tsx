import { Alert, Badge, Card, Group, SimpleGrid, Skeleton, Stack, Text } from "@mantine/core";
import { IconApps, IconChevronRight } from "@tabler/icons-react";
import { useNavigate } from "react-router";
import { errorMessage } from "../api/client";
import { useMyApps } from "../api/queries";
import type { MyApp } from "../api/types";
import { useSession } from "../auth/session";
import { isAdmin } from "../auth/roles";
import { AppAvatar, EmptyState, PageHeader, PlatformIcon, RoleBadge, StatusDot } from "../components/ui";

function Stat({ value, label }: { value: string | number; label: string }) {
  return (
    <div>
      <Text fw={650} size="lg" className="tabular" lh={1.2}>
        {value}
      </Text>
      <Text size="xs" c="dimmed">
        {label}
      </Text>
    </div>
  );
}

function AppCard({ app }: { app: MyApp }) {
  const navigate = useNavigate();
  const open = () => navigate(`/apps/${app.id}`);
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
      data-slug={app.slug}
    >
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <Group gap="md" wrap="nowrap" style={{ minWidth: 0 }}>
          <AppAvatar name={app.name} slug={app.slug} size={44} />
          <div style={{ minWidth: 0 }}>
            <Text fw={650} truncate>
              {app.name}
            </Text>
            <Group gap={6} wrap="nowrap">
              <PlatformIcon platform={app.platform} size={14} />
              <Text size="xs" c="dimmed" truncate>
                {app.slug}
              </Text>
            </Group>
          </div>
        </Group>
        <RoleBadge role={app.role} testId="app-role" />
      </Group>
      <Text size="sm" c="dimmed" lineClamp={2} mt="md" mih={42}>
        {app.description || "No description yet."}
      </Text>
      <Group justify="space-between" mt="md" pt="md" style={{ borderTop: "1px solid var(--mantine-color-default-border)" }}>
        <Group gap="xl">
          <Stat value={`${app.active_template_count ?? 0}/${app.template_count ?? 0}`} label="active templates" />
          <Group gap={6}>
            <StatusDot color={app.status === "active" ? "green" : "gray"} />
            <Text size="sm" c={app.status === "active" ? undefined : "dimmed"}>
              {app.status === "active" ? "Live" : "Disabled"}
            </Text>
          </Group>
        </Group>
        <IconChevronRight size={18} stroke={1.6} color="var(--mantine-color-dimmed)" />
      </Group>
    </Card>
  );
}

/** Everyone lands here: the apps they belong to (all apps for admins). */
export function HomePage() {
  const me = useSession();
  const apps = useMyApps();
  const count = apps.data?.length;
  return (
    <Stack gap={0}>
      <PageHeader
        title={
          <Group gap="xs" component="span">
            My apps
            {count !== undefined && (
              <Badge color="gray" variant="light" size="lg" className="tabular">
                {count}
              </Badge>
            )}
          </Group>
        }
        description={
          isAdmin(me) ? "As an admin you can open every app." : "Apps you are a member of. Your role is shown on each card."
        }
      />
      {apps.error && <Alert color="red">{errorMessage(apps.error)}</Alert>}
      {apps.isPending && (
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="lg">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} height={196} radius="md" />
          ))}
        </SimpleGrid>
      )}
      {count === 0 && (
        <Card padding="xl">
          <EmptyState
            testId="no-apps"
            icon={<IconApps size={30} stroke={1.5} />}
            title="No apps yet"
            description={
              isAdmin(me)
                ? "Create the first app under Admin → Apps."
                : "Ask an admin to add you to an app. It will show up here."
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
