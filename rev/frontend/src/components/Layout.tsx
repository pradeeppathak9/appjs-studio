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
  IconArrowsExchange,
  IconBook,
  IconChartBar,
  IconChevronRight,
  IconCreditCard,
  IconDeviceDesktop,
  IconLayoutGrid,
  IconLayoutSidebarLeftCollapse,
  IconLayoutSidebarLeftExpand,
  IconLogout,
  IconMoon,
  IconReceipt,
  IconRepeat,
  IconSelector,
  IconSettings,
  IconShieldLock,
  IconSun,
  IconUserCircle,
} from "@tabler/icons-react";
import { useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link, NavLink as RouterNavLink, Outlet, useMatch, useNavigate } from "react-router";
import { setToken } from "../api/client";
import { useApps } from "../api/queries";
import type { App } from "../api/types";
import { useSession } from "../auth/session";
import { appTabsFor, GATEWAY_LABEL, type AppTab } from "../lib/gateways";
import { ApiStatus, AppAvatar, Logo, ThemeToggle, UserAvatar } from "./ui";

const COLLAPSE_KEY = "autorev-navbar-collapsed";

function readCollapsed(): boolean {
  try {
    return window.localStorage.getItem(COLLAPSE_KEY) === "1";
  } catch {
    return false;
  }
}

function tabIcon(t: AppTab) {
  const props = { size: 18, stroke: 1.6 };
  switch (t.path) {
    case "":
      return <IconChartBar {...props} />;
    case "subscriptions":
    case "rz-subscriptions":
      return <IconRepeat {...props} />;
    case "transactions":
      return <IconArrowsExchange {...props} />;
    case "rz-payments":
      return <IconReceipt {...props} />;
    case "integration-guide":
      return <IconBook {...props} />;
    case "settings":
      return <IconSettings {...props} />;
    default:
      return <IconCreditCard {...props} />;
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

function AppSwitcher({ current, collapsed }: { current?: App; collapsed: boolean }) {
  const apps = useApps();
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
        >
          <Group gap="sm" wrap="nowrap" justify={collapsed ? "center" : undefined}>
            {current ? <AppAvatar name={current.name} id={current.id} size={28} /> : <IconApps size={20} stroke={1.6} />}
            {!collapsed && (
              <>
                <Box style={{ flex: 1, minWidth: 0 }}>
                  <Text size="sm" fw={600} truncate>
                    {current ? current.name : "Select an app"}
                  </Text>
                  <Text size="xs" c="dimmed" truncate ff="monospace">
                    {current ? current.id : `${apps.data?.length ?? 0} apps`}
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
            leftSection={<AppAvatar name={a.name} id={a.id} size={22} />}
            onClick={() => navigate(`/apps/${a.id}`)}
          >
            <Text size="sm" truncate maw={180}>
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
        <Menu.Item leftSection={<IconLayoutGrid size={16} />} onClick={() => navigate("/dashboard")}>
          All apps
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}

function useLogout() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  return () => {
    setToken(null);
    qc.clear();
    navigate("/", { replace: true });
  };
}

function UserMenu({ collapsed }: { collapsed: boolean }) {
  const me = useSession();
  const logout = useLogout();
  const name = me.full_name || me.email;
  return (
    <Menu position={collapsed ? "right-end" : "top-start"} width={240}>
      <Menu.Target>
        <UnstyledButton aria-label="Account menu" p={6} style={{ borderRadius: "var(--mantine-radius-md)", width: "100%" }}>
          <Group gap="sm" wrap="nowrap" justify={collapsed ? "center" : undefined}>
            <UserAvatar name={name} email={me.email} size={32} />
            {!collapsed && (
              <Box style={{ flex: 1, minWidth: 0 }}>
                <Text size="sm" fw={600} truncate data-testid="whoami">
                  {name}
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
          {me.is_admin && " · admin"}
        </Menu.Label>
        <Menu.Item component={Link} to="/account" leftSection={<IconUserCircle size={16} />}>
          Account
        </Menu.Item>
        <Menu.Divider />
        <Menu.Item leftSection={<IconLogout size={16} />} onClick={logout}>
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

function Crumbs({ app }: { app?: App }) {
  const inApp = useMatch("/apps/:appId/*");
  const inAdmin = useMatch("/admin/*");
  const inAccount = useMatch("/account");
  const items = [
    <Anchor key="apps" component={Link} to="/dashboard" size="sm" c="dimmed">
      Apps
    </Anchor>,
  ];
  if (inApp) {
    items.push(
      <Anchor key="app" component={Link} to={`/apps/${inApp.params.appId}`} size="sm">
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
  }
  return (
    <Breadcrumbs separator={<IconChevronRight size={14} stroke={1.6} />} separatorMargin={6}>
      {items}
    </Breadcrumbs>
  );
}

function AppNav({ app, collapsed, onNavigate }: { app: App; collapsed: boolean; onNavigate: () => void }) {
  const tabs = appTabsFor(app);
  return (
    <Stack gap={2} component="nav" aria-label="App sections">
      {tabs.map((t, i) => {
        // A heading (or a divider when collapsed) wherever the gateway section changes.
        const heading = i === 0 || t.group !== tabs[i - 1].group;
        const to = t.path ? `/apps/${app.id}/${t.path}` : `/apps/${app.id}`;
        return (
          <Box key={`${t.group ?? "app"}-${t.path}`}>
            {heading &&
              (collapsed ? (
                <Divider my="xs" />
              ) : (
                <Text size="xs" fw={600} c="dimmed" tt="uppercase" mt="md" mb={4} px="sm" truncate>
                  {t.group ? GATEWAY_LABEL[t.group] : "App"}
                </Text>
              ))}
            <NavItem
              to={to}
              end={t.path === ""}
              label={t.label}
              icon={tabIcon(t)}
              collapsed={collapsed}
              onNavigate={onNavigate}
            />
          </Box>
        );
      })}
    </Stack>
  );
}

export function Layout() {
  const me = useSession();
  const [mobileOpen, { toggle, close }] = useDisclosure(false);
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const inApp = useMatch("/apps/:appId/*");
  const apps = useApps();
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
          <ApiStatus />
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="sm" bg="var(--app-surface)">
        <AppShell.Section>
          <Group justify={narrow ? "center" : "space-between"} mb="sm" px={4} wrap="nowrap">
            <UnstyledButton component={Link} to="/dashboard" aria-label="AutoRev home" onClick={close}>
              <Logo compact={narrow} />
            </UnstyledButton>
            <CloseButton hiddenFrom="sm" onClick={close} aria-label="Close navigation" />
            {!narrow && (
              <Tooltip label="Collapse sidebar">
                <ActionIcon variant="subtle" color="gray" onClick={toggleCollapsed} aria-label="Collapse sidebar" visibleFrom="sm">
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
            <NavItem to="/dashboard" end label="All apps" icon={<IconApps size={18} stroke={1.6} />} collapsed={narrow} onNavigate={close} />
            {current && <AppNav app={current} collapsed={narrow} onNavigate={close} />}
          </Stack>
        </AppShell.Section>

        <AppShell.Section>
          <Stack gap={2} mb="sm">
            {me.is_admin && (
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
        <Box p={{ base: "md", sm: "xl" }} maw={1400} mx="auto">
          <Outlet />
        </Box>
      </AppShell.Main>
    </AppShell>
  );
}
