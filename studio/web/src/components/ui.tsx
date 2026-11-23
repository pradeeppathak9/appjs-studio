import {
  Avatar,
  Badge,
  Box,
  Center,
  Group,
  HoverCard,
  Paper,
  SegmentedControl,
  Skeleton,
  Stack,
  Text,
  ThemeIcon,
  Title,
  Tooltip,
  useMantineColorScheme,
  type MantineSize,
} from "@mantine/core";
import {
  IconBrandAndroid,
  IconBrandApple,
  IconDeviceDesktop,
  IconDevices,
  IconMoon,
  IconSun,
  IconWorld,
} from "@tabler/icons-react";
import { useId, type ReactNode } from "react";
import { useHealth } from "../api/queries";
import { ROLE_COLOR } from "../auth/roles";
import { colorFor, initials } from "../lib/colors";
import { age } from "../lib/format";

/** The product mark: a gradient tile with a "C". */
export function LogoMark({ size = 28 }: { size?: number }) {
  // Each mark needs its own gradient id: a hidden copy (e.g. the mobile header's) would break a shared one.
  const id = `logo-g-${useId().replace(/:/g, "")}`;
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#5c7cfa" />
          <stop offset="1" stopColor="#9c36b5" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill={`url(#${id})`} />
      <path d="M21.5 11.2a7 7 0 1 0 0 9.6" fill="none" stroke="#fff" strokeWidth="3.2" strokeLinecap="round" />
      <circle cx="22.6" cy="16" r="1.9" fill="#fff" />
    </svg>
  );
}

export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <Group gap={10} wrap="nowrap">
      <LogoMark />
      {!compact && (
        <Text fw={700} size="lg" style={{ letterSpacing: "-0.01em" }}>
          AppJs Studio
        </Text>
      )}
    </Group>
  );
}

export function AppAvatar({ name, slug, size = "md" }: { name: string; slug: string; size?: MantineSize | number }) {
  return (
    <Avatar color={colorFor(slug)} variant="filled" radius="md" size={size} aria-hidden="true">
      {initials(name)}
    </Avatar>
  );
}

export function UserAvatar({ name, email, size = "sm" }: { name: string; email: string; size?: MantineSize | number }) {
  return (
    <Avatar color={colorFor(email)} variant="light" radius="xl" size={size} aria-hidden="true">
      {initials(name)}
    </Avatar>
  );
}

export function RoleBadge({ role, testId }: { role: string; testId?: string }) {
  return (
    <Badge color={ROLE_COLOR[role] ?? "gray"} variant="light" data-testid={testId} tt="capitalize">
      {role}
    </Badge>
  );
}

export function StatusDot({ color, pulse, label }: { color: string; pulse?: boolean; label?: string }) {
  return (
    <span
      className="status-dot"
      data-pulse={pulse || undefined}
      style={{ backgroundColor: `var(--mantine-color-${color}-filled)`, color: `var(--mantine-color-${color}-filled)` }}
      aria-label={label}
      role={label ? "img" : undefined}
    />
  );
}

export function PlatformIcon({ platform, size = 16 }: { platform: string; size?: number }) {
  const Icon =
    platform === "android" ? IconBrandAndroid : platform === "ios" ? IconBrandApple : platform === "web" ? IconWorld : IconDevices;
  return (
    <Tooltip label={platform}>
      <Box component="span" c="dimmed" style={{ display: "inline-flex" }} aria-label={`platform ${platform}`}>
        <Icon size={size} stroke={1.6} />
      </Box>
    </Tooltip>
  );
}

export function PageHeader({
  title,
  description,
  actions,
  leading,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  leading?: ReactNode;
}) {
  return (
    <Group justify="space-between" align="flex-start" wrap="wrap" gap="md" mb="lg">
      <Group gap="md" wrap="nowrap" align="center" style={{ minWidth: 0 }}>
        {leading}
        <div style={{ minWidth: 0 }}>
          <Title order={2} fz={24} lh={1.25}>
            {title}
          </Title>
          {description && (
            <Text c="dimmed" size="sm" mt={4}>
              {description}
            </Text>
          )}
        </div>
      </Group>
      {actions && <Group gap="sm">{actions}</Group>}
    </Group>
  );
}

/** A titled card section with an optional icon and right-hand actions. */
export function Section({
  title,
  icon,
  description,
  actions,
  children,
  danger,
  testId,
}: {
  title: ReactNode;
  icon?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  danger?: boolean;
  testId?: string;
}) {
  return (
    <Paper
      withBorder
      p="lg"
      shadow="xs"
      data-testid={testId}
      style={danger ? { borderColor: "var(--mantine-color-red-outline)" } : undefined}
    >
      <Group justify="space-between" align="flex-start" mb="md" wrap="nowrap">
        <Group gap="sm" wrap="nowrap" align="flex-start">
          {icon && (
            <ThemeIcon variant="light" color={danger ? "red" : "indigo"} size={32} radius="md">
              {icon}
            </ThemeIcon>
          )}
          <div>
            <Text fw={600} c={danger ? "red" : undefined}>
              {title}
            </Text>
            {description && (
              <Text size="sm" c="dimmed">
                {description}
              </Text>
            )}
          </div>
        </Group>
        {actions && <Box style={{ flexShrink: 0 }}>{actions}</Box>}
      </Group>
      {children}
    </Paper>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  testId,
  compact,
}: {
  icon: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  testId?: string;
  compact?: boolean;
}) {
  return (
    <Center py={compact ? "md" : 48} data-testid={testId}>
      <Stack align="center" gap={6} maw={420} ta="center">
        <ThemeIcon variant="light" color="gray" size={compact ? 40 : 56} radius="xl">
          {icon}
        </ThemeIcon>
        <Text fw={600} mt={4}>
          {title}
        </Text>
        {description && (
          <Text size="sm" c="dimmed">
            {description}
          </Text>
        )}
        {action && <Box mt="xs">{action}</Box>}
      </Stack>
    </Center>
  );
}

export function ListSkeleton({ rows = 4, height = 44 }: { rows?: number; height?: number }) {
  return (
    <Stack gap="xs" data-testid="skeleton">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} height={height} radius="md" />
      ))}
    </Stack>
  );
}

/** Light / Dark / System, persisted by Mantine's localStorage color-scheme manager. */
export function ThemeToggle({ fullWidth, size = "xs" }: { fullWidth?: boolean; size?: MantineSize }) {
  const { colorScheme, setColorScheme } = useMantineColorScheme();
  const item = (value: string, label: string, Icon: typeof IconSun) => ({
    value,
    label: (
      <Center style={{ gap: 6 }}>
        <Icon size={14} stroke={1.8} />
        <span>{label}</span>
      </Center>
    ),
  });
  return (
    <SegmentedControl
      size={size}
      fullWidth={fullWidth}
      value={colorScheme}
      onChange={(v) => setColorScheme(v as "light" | "dark" | "auto")}
      aria-label="Color theme"
      data={[item("light", "Light", IconSun), item("dark", "Dark", IconMoon), item("auto", "System", IconDeviceDesktop)]}
    />
  );
}

/** A status dot with "All systems normal" / "Degraded"; details on hover. */
export function SystemStatus() {
  const { data, error } = useHealth();
  const state = error ? "down" : !data ? "loading" : data.status === "ok" ? "ok" : "degraded";
  const color = { ok: "green", degraded: "yellow", down: "red", loading: "gray" }[state];
  const label = { ok: "All systems normal", degraded: "Degraded", down: "API unreachable", loading: "Checking…" }[state];
  const live = data?.workers.filter((w) => w.fresh).length ?? 0;
  return (
    <HoverCard width={260} shadow="md" position="bottom-end" withArrow openDelay={100}>
      <HoverCard.Target>
        <Group gap={8} data-testid="health" tabIndex={0} style={{ cursor: "default" }} wrap="nowrap">
          <StatusDot color={color} pulse={state === "degraded"} />
          <Text size="sm" c="dimmed" visibleFrom="xs">
            {label}
          </Text>
        </Group>
      </HoverCard.Target>
      <HoverCard.Dropdown>
        <Stack gap={6}>
          <Group justify="space-between">
            <Text size="sm" fw={600}>
              {label}
            </Text>
            <StatusDot color={color} />
          </Group>
          {data ? (
            <>
              <Row label="Database" value={data.db} />
              <Row label="Live workers" value={`${live} of ${data.workers.length}`} />
              <Row label="Jobs queued" value={String(data.jobs.queued ?? 0)} />
              <Row label="Jobs running" value={String(data.jobs.running ?? 0)} />
              {data.workers[0] && <Row label="Last heartbeat" value={age(data.workers[0].heartbeat_at)} />}
            </>
          ) : (
            <Text size="sm" c="dimmed">
              {error ? "The API did not answer /healthz." : "Loading…"}
            </Text>
          )}
        </Stack>
      </HoverCard.Dropdown>
    </HoverCard>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <Group justify="space-between" gap="xs">
      <Text size="sm" c="dimmed">
        {label}
      </Text>
      <Text size="sm" className="tabular">
        {value}
      </Text>
    </Group>
  );
}
