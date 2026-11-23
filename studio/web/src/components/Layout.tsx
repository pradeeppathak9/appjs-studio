import {
  ActionIcon,
  Anchor,
  AppShell,
  Box,
  Breadcrumbs,
  Burger,
  CloseButton,
  Divider,
  Group,
  Menu,
  NavLink,
  ScrollArea,
  Stack,
  Text,
  Tooltip,
  UnstyledButton,
  useMantineColorScheme,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import {
  IconApps,
  IconChevronRight,
  IconDeviceDesktop,
  IconBook2,
  IconDeviceMobile,
  IconFlask,
  IconLayoutGrid,
  IconLayoutSidebarLeftCollapse,
  IconLayoutSidebarLeftExpand,
  IconListDetails,
  IconLogout,
  IconMoon,
  IconSelector,
  IconSettings,
  IconShieldLock,
  IconSparkles,
  IconSun,
  IconUserCircle,
  IconUsers,
} from "@tabler/icons-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link, NavLink as RouterNavLink, Outlet, useLocation, useMatch, useNavigate } from "react-router";
import { api, unwrap } from "../api/client";
import { useMyApps } from "../api/queries";
import type { MyApp } from "../api/types";
import { appTabsFor, isAdmin } from "../auth/roles";
import { useSession } from "../auth/session";
import { AppAvatar, Logo, RoleBadge, SystemStatus, ThemeToggle, UserAvatar } from "./ui";

const TAB_ICONS: Record<string, typeof IconLayoutGrid> = {
  "": IconLayoutGrid,
  test: IconFlask,
  free: IconSparkles,
  jobs: IconListDetails,
  preview: IconDeviceMobile,
  guide: IconBook2,
  users: IconUsers,
  settings: IconSettings,
};

const COLLAPSE_KEY = "studio-navbar-collapsed";

function readCollapsed(): boolean {
  try {
    return window.localStorage.getItem(COLLAPSE_KEY) === "1";
  } catch {
    return false;
  }
}

/** A navbar entry; icon-only with a tooltip when the navbar is collapsed. */
function NavItem({
  to,
  label,
  icon,
  collapsed,
  end,
  onNavigate,
}: {
  to: string;
  label: string;
  icon: ReactNode;
  collapsed: boolean;
  end?: boolean;
  onNavigate: () => void;
}) {
  const link = (
    <NavLink
      component={RouterNavLink}
      to={to}
      end={end}
      label={collapsed ? undefined : label}
      aria-label={collapsed ? label : undefined}
      leftSection={icon}
      onClick={onNavigate}
      variant="light"
      style={{ borderRadius: "var(--mantine-radius-md)" }}
      styles={collapsed ? { section: { marginInlineEnd: 0 }, root: { justifyContent: "center" } } : undefined}
    />
  );
  return collapsed ? (
    <Tooltip label={label} position="right">
      {link}
    </Tooltip>
  ) : (
    link
  );
}

function AppSwitcher({ current, collapsed }: { current?: MyApp; collapsed: boolean }) {
  const apps = useMyApps();
  const navigate = useNavigate();
  return (
    <Menu position={collapsed ? "right-start" : "bottom-start"} width={260}>
      <Menu.Target>
        <UnstyledButton
          aria-label="Switch app"
          p={collapsed ? 4 : 8}
          style={{
            border: "1px solid var(--mantine-color-default-border)",
            borderRadius: "var(--mantine-radius-md)",
            width: "100%",
          }}
          data-testid="app-switcher"
        >
          <Group gap="sm" wrap="nowrap" justify={collapsed ? "center" : undefined}>
            {current ? (
              <AppAvatar name={current.name} slug={current.slug} size={28} />
            ) : (
              <IconApps size={20} stroke={1.6} />
            )}
            {!collapsed && (
              <>
                <Box style={{ flex: 1, minWidth: 0 }}>
                  <Text size="sm" fw={600} truncate>
                    {current ? current.name : "Select an app"}
                  </Text>
                  <Text size="xs" c="dimmed" truncate>
                    {current ? current.slug : `${apps.data?.length ?? 0} apps`}
                  </Text>
                </Box>
                <IconSelector size={16} stroke={1.6} />
              </>
            )}
          </Group>
        </UnstyledButton>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Label>Your apps</Menu.Label>
        {apps.data?.map((a) => (
          <Menu.Item
            key={a.id}
            leftSection={<AppAvatar name={a.name} slug={a.slug} size={22} />}
            rightSection={<RoleBadge role={a.role} />}
            onClick={() => navigate(`/apps/${a.id}`)}
          >
            <Text size="sm" truncate maw={130}>
              {a.name}
            </Text>
          </Menu.Item>
        ))}
        {apps.data?.length === 0 && (
          <Menu.Item disabled>
            <Text size="sm">No apps yet</Text>
          </Menu.Item>
        )}
        <Menu.Divider />
        <Menu.Item leftSection={<IconLayoutGrid size={16} />} onClick={() => navigate("/")}>
          All apps
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}

function UserMenu({ collapsed }: { collapsed: boolean }) {
  const me = useSession();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const logout = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/auth/logout")),
    onSettled: () => {
      qc.clear();
      navigate("/login");
    },
  });
  return (
    <Menu position={collapsed ? "right-end" : "top-start"} width={240}>
      <Menu.Target>
        <UnstyledButton aria-label="Account menu" p={6} style={{ borderRadius: "var(--mantine-radius-md)", width: "100%" }}>
          <Group gap="sm" wrap="nowrap" justify={collapsed ? "center" : undefined}>
            <UserAvatar name={me.name} email={me.email} size={32} />
            {!collapsed && (
              <Box style={{ flex: 1, minWidth: 0 }}>
                <Text size="sm" fw={600} truncate data-testid="whoami">
                  {me.name}
                </Text>
                <Text size="xs" c="dimmed" truncate>
                  {me.email}
                </Text>
              </Box>
            )}
          </Group>
        </UnstyledButton>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Label>
          {me.email}
          {isAdmin(me) && " · admin"}
        </Menu.Label>
        <Menu.Item component={Link} to="/account" leftSection={<IconUserCircle size={16} />}>
          Account
        </Menu.Item>
        <Menu.Divider />
        <Menu.Item leftSection={<IconLogout size={16} />} onClick={() => logout.mutate()}>
          Log out
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}

/** Cycles light -> dark -> system when the navbar is collapsed. */
function ThemeIconButton() {
  const { colorScheme, setColorScheme } = useMantineColorScheme();
  const next = colorScheme === "light" ? "dark" : colorScheme === "dark" ? "auto" : "light";
  const Icon = colorScheme === "light" ? IconSun : colorScheme === "dark" ? IconMoon : IconDeviceDesktop;
  return (
    <Tooltip label={`Theme: ${colorScheme === "auto" ? "system" : colorScheme}`} position="right">
      <ActionIcon variant="subtle" color="gray" size="lg" aria-label="Change color theme" onClick={() => setColorScheme(next)}>
        <Icon size={18} stroke={1.6} />
      </ActionIcon>
    </Tooltip>
  );
}

function Crumbs({ app }: { app?: MyApp }) {
  const inApp = useMatch("/apps/:appId/*");
  const inAdmin = useMatch("/admin/*");
  const inAccount = useMatch("/account");
  const inJob = useMatch("/jobs/:jobId");
  const items = [
    <Anchor key="apps" component={Link} to="/" size="sm" c="dimmed">
      Apps
    </Anchor>,
  ];
  if (inApp) {
    items.push(
      <Anchor key="app" component={Link} to={`/apps/${inApp.params.appId}`} size="sm" data-testid="crumb-app">
        {app?.name ?? "…"}
      </Anchor>,
    );
  } else if (inAdmin) {
    items.push(
      <Anchor key="admin" component={Link} to="/admin" size="sm">
        Admin
      </Anchor>,
    );
  } else if (inAccount) {
    items.push(
      <Text key="account" size="sm">
        Account
      </Text>,
    );
  } else if (inJob) {
    items.push(
      <Text key="job" size="sm">
        Job
      </Text>,
    );
  }
  return (
    <Breadcrumbs separator={<IconChevronRight size={14} stroke={1.6} />} separatorMargin={6}>
      {items}
    </Breadcrumbs>
  );
}

export function Layout() {
  const me = useSession();
  const [mobileOpen, { toggle, close }] = useDisclosure(false);
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const location = useLocation();
  const inApp = useMatch("/apps/:appId/*");
  const apps = useMyApps();
  const current = inApp ? apps.data?.find((a) => a.id === inApp.params.appId) : undefined;
  // On phones the navbar is a drawer and always shows labels.
  const narrow = collapsed && !mobileOpen;

  const toggleCollapsed = () => {
    setCollapsed((c) => {
      try {
        window.localStorage.setItem(COLLAPSE_KEY, c ? "0" : "1");
      } catch {
        /* storage unavailable */
      }
      return !c;
    });
  };

  return (
    <AppShell
      layout="alt"
      header={{ height: 56 }}
      navbar={{ width: collapsed ? 76 : 260, breakpoint: "sm", collapsed: { mobile: !mobileOpen } }}
      padding={0}
    >
      <AppShell.Header bg="var(--app-surface)">
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap" style={{ minWidth: 0 }}>
            <Burger opened={mobileOpen} onClick={toggle} hiddenFrom="sm" size="sm" aria-label="Toggle navigation" />
            <Box hiddenFrom="sm">
              <Logo compact />
            </Box>
            <Box visibleFrom="xs" style={{ minWidth: 0 }}>
              <Crumbs app={current} />
            </Box>
          </Group>
          <SystemStatus />
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="sm" bg="var(--app-surface)">
        <AppShell.Section>
          <Group justify={narrow ? "center" : "space-between"} mb="sm" px={4} wrap="nowrap">
            <UnstyledButton component={Link} to="/" aria-label="AppJs Studio home" onClick={close}>
              <Logo compact={narrow} />
            </UnstyledButton>
            <CloseButton hiddenFrom="sm" onClick={close} aria-label="Close navigation" />
            {!narrow && (
              <Tooltip label="Collapse sidebar">
                <ActionIcon
                  variant="subtle"
                  color="gray"
                  onClick={toggleCollapsed}
                  aria-label="Collapse sidebar"
                  visibleFrom="sm"
                >
                  <IconLayoutSidebarLeftCollapse size={18} stroke={1.6} />
                </ActionIcon>
              </Tooltip>
            )}
          </Group>
          {narrow && (
            <Group justify="center" mb="sm">
              <Tooltip label="Expand sidebar" position="right">
                <ActionIcon variant="subtle" color="gray" onClick={toggleCollapsed} aria-label="Expand sidebar">
                  <IconLayoutSidebarLeftExpand size={18} stroke={1.6} />
                </ActionIcon>
              </Tooltip>
            </Group>
          )}
          <AppSwitcher current={current} collapsed={narrow} />
        </AppShell.Section>

        <AppShell.Section grow component={ScrollArea} mt="md">
          <Stack gap={2}>
            <NavItem to="/" end label="All apps" icon={<IconApps size={18} stroke={1.6} />} collapsed={narrow} onNavigate={close} />
            {current && (
              <>
                {!narrow && (
                  <Text size="xs" fw={600} c="dimmed" tt="uppercase" mt="md" mb={4} px="sm" truncate>
                    {current.name}
                  </Text>
                )}
                {narrow && <Divider my="xs" />}
                <Stack gap={2} component="nav" aria-label="App sections">
                  {appTabsFor(current.role, isAdmin(me)).map((t) => {
                    const Icon = TAB_ICONS[t.path];
                    const to = t.path ? `/apps/${current.id}/${t.path}` : `/apps/${current.id}`;
                    return (
                      <NavItem
                        key={t.label}
                        to={to}
                        // Templates stays highlighted inside the template editor.
                        end={t.path !== "" ? false : !location.pathname.includes("/templates/")}
                        label={t.label}
                        icon={<Icon size={18} stroke={1.6} />}
                        collapsed={narrow}
                        onNavigate={close}
                      />
                    );
                  })}
                </Stack>
              </>
            )}
          </Stack>
        </AppShell.Section>

        <AppShell.Section>
          <Stack gap={2} mb="sm">
            {isAdmin(me) && (
              <NavItem to="/admin" label="Admin" icon={<IconShieldLock size={18} stroke={1.6} />} collapsed={narrow} onNavigate={close} />
            )}
            <NavItem to="/account" label="Account" icon={<IconUserCircle size={18} stroke={1.6} />} collapsed={narrow} onNavigate={close} />
          </Stack>
          {narrow ? (
            <Group justify="center" mb="xs">
              <ThemeIconButton />
            </Group>
          ) : (
            <Box mb="sm">
              <ThemeToggle fullWidth />
            </Box>
          )}
          <Divider mb="xs" />
          <UserMenu collapsed={narrow} />
        </AppShell.Section>
      </AppShell.Navbar>

      <AppShell.Main bg="var(--app-bg)">
        <Box maw={1240} mx="auto" px={{ base: "md", md: "xl" }} py={{ base: "md", md: "xl" }}>
          <Outlet />
        </Box>
      </AppShell.Main>
    </AppShell>
  );
}
