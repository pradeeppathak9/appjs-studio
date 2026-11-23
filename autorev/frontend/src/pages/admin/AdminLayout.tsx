import { Stack, Tabs } from "@mantine/core";
import { IconApps, IconDatabase, IconUsers } from "@tabler/icons-react";
import { Outlet, useLocation, useNavigate } from "react-router";
import { PageHeader } from "../../components/ui";

const TABS = [
  { value: "apps", label: "Apps", icon: IconApps },
  { value: "users", label: "Users", icon: IconUsers },
  { value: "redis", label: "Redis", icon: IconDatabase },
];

export function AdminLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const tab = TABS.find((t) => location.pathname.startsWith(`/admin/${t.value}`))?.value ?? "apps";
  return (
    <Stack gap="lg">
      <PageHeader title="Admin" description="Users, apps, who can open which app, and the Redis cache." />
      <Tabs value={tab} onChange={(v) => v && navigate(`/admin/${v}`)}>
        <Tabs.List>
          {TABS.map((t) => (
            <Tabs.Tab key={t.value} value={t.value} leftSection={<t.icon size={16} />}>
              {t.label}
            </Tabs.Tab>
          ))}
        </Tabs.List>
      </Tabs>
      <Outlet />
    </Stack>
  );
}
