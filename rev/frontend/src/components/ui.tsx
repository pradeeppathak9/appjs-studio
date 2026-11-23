import {
  Avatar,
  Badge,
  Box,
  Center,
  Group,
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
import { IconDeviceDesktop, IconMoon, IconSun } from "@tabler/icons-react";
import { useId, type ReactNode } from "react";
import { useHealth } from "../api/queries";
import { colorFor, initials } from "../lib/colors";
import { GATEWAY_COLOR, GATEWAY_LABEL, type Gateway } from "../lib/gateways";

/** The product mark: a gradient tile with a recurring-payment arrow. */
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
      <path d="M22.4 12.6A7 7 0 1 0 23 17" fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round" />
      <path
        d="M23.6 8.4v4.8h-4.8"
        fill="none"
        stroke="#fff"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <Group gap={10} wrap="nowrap">
      <LogoMark />
      {!compact && (
        <Text fw={700} size="lg" style={{ letterSpacing: "-0.01em" }}>
          AutoRev
        </Text>
      )}
    </Group>
  );
}

export function AppAvatar({ name, id, size = "md" }: { name: string; id: string; size?: MantineSize | number }) {
  return (
    <Avatar color={colorFor(id)} variant="filled" radius="md" size={size} aria-hidden="true">
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

export function GatewayBadge({ gateway }: { gateway: Gateway }) {
  return (
    <Badge color={GATEWAY_COLOR[gateway]} variant="light">
      {GATEWAY_LABEL[gateway]}
    </Badge>
  );
}

/** UAT / TEST in yellow, PROD / LIVE in green. */
export function EnvBadge({ env, live }: { env: string; live: boolean }) {
  return (
    <Badge color={live ? "green" : "yellow"} variant="light">
      {env}
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
}: {
  title: ReactNode;
  icon?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  danger?: boolean;
}) {
  return (
    <Paper withBorder p="lg" shadow="xs" style={danger ? { borderColor: "var(--mantine-color-red-outline)" } : undefined}>
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
}: {
  icon: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <Center py={48}>
      <Stack align="center" gap={6} maw={420} ta="center">
        <ThemeIcon variant="light" color="gray" size={56} radius="xl">
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

/** A status dot: is the API answering /api/health? */
export function ApiStatus() {
  const { data, error } = useHealth();
  const state = error ? "down" : !data ? "loading" : data.status === "ok" ? "ok" : "degraded";
  const color = { ok: "green", degraded: "yellow", down: "red", loading: "gray" }[state];
  const label = { ok: "API online", degraded: "Degraded", down: "API unreachable", loading: "Checking…" }[state];
  return (
    <Tooltip label={error ? "The API did not answer /api/health." : "Checked every 30 seconds"}>
      <Group gap={8} tabIndex={0} style={{ cursor: "default" }} wrap="nowrap" data-testid="health">
        <StatusDot color={color} pulse={state === "degraded"} />
        <Text size="sm" c="dimmed" visibleFrom="xs">
          {label}
        </Text>
      </Group>
    </Tooltip>
  );
}
