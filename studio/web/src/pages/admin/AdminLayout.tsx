import { Group, Paper, SimpleGrid, Stack, Tabs, Text, ThemeIcon } from "@mantine/core";
import { IconApps, IconKey, IconUsers, IconUserCheck } from "@tabler/icons-react";
import type { ReactNode } from "react";
import { Outlet, useLocation, useNavigate } from "react-router";
import { useAdminApps, useAdminUsers } from "../../api/queries";
import { PageHeader } from "../../components/ui";

function Stat({ icon, value, label }: { icon: ReactNode; value: number | string; label: string }) {
  return (
    <Paper withBorder p="md" shadow="xs">
      <Group gap="md" wrap="nowrap">
        <ThemeIcon variant="light" size={40} radius="md">
          {icon}
        </ThemeIcon>
        <div>
          <Text fw={700} fz={22} lh={1.1} className="tabular">
            {value}
          </Text>
          <Text size="sm" c="dimmed">
            {label}
          </Text>
        </div>
      </Group>
    </Paper>
  );
}

export function AdminLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const tab = location.pathname.startsWith("/admin/apps") ? "apps" : "users";
  const users = useAdminUsers();
  const apps = useAdminApps();
  const n = (x: number | undefined) => (x === undefined ? "–" : x);
  return (
    <Stack gap="lg">
      <PageHeader title="Admin" description="Users, apps, memberships and app keys." />
      <SimpleGrid cols={{ base: 2, md: 4 }} mt={-8}>
        <Stat icon={<IconUsers size={20} />} value={n(users.data?.length)} label="Users" />
        <Stat
          icon={<IconUserCheck size={20} />}
          value={n(users.data?.filter((u) => u.is_active).length)}
          label="Active users"
        />
        <Stat icon={<IconApps size={20} />} value={n(apps.data?.length)} label="Apps" />
        <Stat
          icon={<IconKey size={20} />}
          value={n(apps.data?.reduce((s, a) => s + (a.active_key_count ?? 0), 0))}
          label="Active app keys"
        />
      </SimpleGrid>
      <Tabs value={tab} onChange={(v) => v && navigate(`/admin/${v}`)}>
        <Tabs.List>
          <Tabs.Tab value="users" leftSection={<IconUsers size={16} />}>
            Users
          </Tabs.Tab>
          <Tabs.Tab value="apps" leftSection={<IconApps size={16} />}>
            Apps
          </Tabs.Tab>
        </Tabs.List>
      </Tabs>
      <Outlet />
    </Stack>
  );
}
