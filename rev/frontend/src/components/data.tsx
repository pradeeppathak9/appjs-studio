import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Code,
  CopyButton,
  Group,
  Paper,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
  Tooltip,
  UnstyledButton,
} from "@mantine/core";
import { IconCheck, IconChevronLeft, IconChevronRight, IconCopy, IconSearch, IconX } from "@tabler/icons-react";
import type { ReactNode } from "react";
import { formatWindow, isInvalid, PRESETS, presetOf, rangeForPreset, type DateRange } from "../lib/dateRange";
import { humanize, num } from "../lib/format";
import { stateColor } from "../lib/states";

/** A page's own heading under the app header, with actions on the right. */
export function PageTitle({ title, description, actions }: { title: ReactNode; description?: ReactNode; actions?: ReactNode }) {
  return (
    <Group justify="space-between" align="flex-end" wrap="wrap" gap="sm" mb="md">
      <div>
        <Title order={3}>{title}</Title>
        {description && (
          <Text size="sm" c="dimmed" mt={2}>
            {description}
          </Text>
        )}
      </div>
      {actions && (
        <Group gap="sm" wrap="wrap">
          {actions}
        </Group>
      )}
    </Group>
  );
}

export function StateBadge({ state, size = "sm" }: { state: string | null | undefined; size?: "xs" | "sm" | "md" }) {
  if (!state) return <Text c="dimmed">—</Text>;
  return (
    <Badge
      color={stateColor(state)}
      variant="light"
      size={size}
      title={state}
      // Never shrink to "A…" in a tight table column: badges size to their text.
      styles={{ root: { maxWidth: "none", flexShrink: 0 }, label: { overflow: "visible" } }}
    >
      {humanize(state)}
    </Badge>
  );
}

/** One pill per state, each with its count; "" is All (the sum). Counts are optional. */
export function StatePills({
  states,
  value,
  onChange,
  counts,
}: {
  states: string[];
  value: string;
  onChange: (state: string) => void;
  counts?: Record<string, number>;
}) {
  return (
    <Group gap={6} wrap="wrap" role="radiogroup" aria-label="Filter by state">
      {states.map((st) => {
        const active = value === st;
        const color = st ? stateColor(st) : "indigo";
        const count = !counts ? undefined : st === "" ? Object.values(counts).reduce((a, b) => a + b, 0) : counts[st] ?? 0;
        return (
          <Button
            key={st || "all"}
            size="compact-sm"
            radius="xl"
            variant={active ? "light" : "subtle"}
            color={active ? color : "gray"}
            role="radio"
            aria-checked={active}
            onClick={() => onChange(st)}
            fw={active ? 650 : 500}
            styles={active ? { root: { boxShadow: `inset 0 0 0 1px var(--mantine-color-${color}-light-color)` } } : undefined}
            rightSection={
              count !== undefined ? (
                <Text span size="xs" fw={700} c={active ? undefined : "dimmed"} className="tabular">
                  {num(count)}
                </Text>
              ) : undefined
            }
          >
            {st ? humanize(st) : "All"}
          </Button>
        );
      })}
    </Group>
  );
}

/** Today / 7 days / 30 days / All, plus a custom start and end date (IST calendar dates). */
export function DateRangeFilter({ value, onChange }: { value: DateRange; onChange: (r: DateRange) => void }) {
  const preset = presetOf(value);
  const invalid = isInvalid(value);
  return (
    <Group gap="sm" wrap="wrap" align="center">
      <SegmentedControl
        size="xs"
        value={preset ?? ""}
        onChange={(v) => onChange(rangeForPreset(v))}
        data={PRESETS.map((p) => ({ value: p.value, label: p.label }))}
        aria-label="Date range"
      />
      <Group gap={4} wrap="nowrap">
        <TextInput
          type="date"
          size="xs"
          aria-label="Start date"
          value={value.start}
          max={value.end || undefined}
          onChange={(e) => onChange({ ...value, start: e.currentTarget.value })}
          error={invalid}
        />
        <Text c="dimmed" size="sm">
          –
        </Text>
        <TextInput
          type="date"
          size="xs"
          aria-label="End date"
          value={value.end}
          min={value.start || undefined}
          onChange={(e) => onChange({ ...value, end: e.currentTarget.value })}
          error={invalid}
        />
      </Group>
      <Text size="xs" c={invalid ? "red" : "dimmed"}>
        {invalid ? "Start date must not be after end date." : `${formatWindow(value)}${value.start || value.end ? " · IST" : ""}`}
      </Text>
    </Group>
  );
}

/** Prev / Next, with "Page 2 of 14 · 680 total" when the total is known. */
export function Pager({
  page,
  pageSize,
  total,
  hasMore,
  onChange,
}: {
  page: number;
  pageSize: number;
  total: number | null;
  hasMore: boolean;
  onChange: (page: number) => void;
}) {
  if (page === 0 && !hasMore) return null;
  return (
    <Group justify="center" gap="md" mt="md">
      <Button variant="default" size="xs" leftSection={<IconChevronLeft size={14} />} disabled={page === 0} onClick={() => onChange(page - 1)}>
        Prev
      </Button>
      <Text size="sm" c="dimmed" className="tabular">
        Page {page + 1}
        {total !== null && ` of ${Math.max(1, Math.ceil(total / pageSize))} · ${num(total)} total`}
      </Text>
      <Button variant="default" size="xs" rightSection={<IconChevronRight size={14} />} disabled={!hasMore} onClick={() => onChange(page + 1)}>
        Next
      </Button>
    </Group>
  );
}

/** A bordered card that scrolls a wide table inside itself. */
export function TableCard({ children, minWidth = 900 }: { children: ReactNode; minWidth?: number }) {
  return (
    <Paper withBorder shadow="xs" style={{ overflow: "hidden" }}>
      <Table.ScrollContainer minWidth={minWidth} type="native">
        <Table striped="even" highlightOnHover fz="sm" verticalSpacing="xs" horizontalSpacing="md">
          {children}
        </Table>
      </Table.ScrollContainer>
    </Paper>
  );
}

export function Th({ children }: { children: ReactNode }) {
  return (
    <Table.Th>
      <Text size="xs" fw={600} c="dimmed" tt="uppercase" style={{ letterSpacing: "0.04em", whiteSpace: "nowrap" }}>
        {children}
      </Text>
    </Table.Th>
  );
}

/** An identifier in monospace. With onClick it is a link-styled button; it can be copied on hover. */
export function Mono({
  value,
  onClick,
  dimmed,
  title,
  copy = true,
}: {
  value: string | null | undefined;
  onClick?: () => void;
  dimmed?: boolean;
  title?: string;
  copy?: boolean;
}) {
  if (!value) return <Text c="dimmed">—</Text>;
  const text = (
    <Text span ff="monospace" fz="xs" c={onClick ? "indigo" : dimmed ? "dimmed" : undefined} style={{ whiteSpace: "nowrap" }}>
      {value}
    </Text>
  );
  return (
    <Group gap={2} wrap="nowrap" className="mono-cell" title={title ?? value}>
      {onClick ? (
        <UnstyledButton
          onClick={(e) => {
            e.stopPropagation();
            onClick();
          }}
          style={{ textDecoration: "underline dotted", textUnderlineOffset: 3 }}
        >
          {text}
        </UnstyledButton>
      ) : (
        text
      )}
      {copy && <CopyId value={value} />}
    </Group>
  );
}

export function CopyId({ value }: { value: string }) {
  return (
    <CopyButton value={value} timeout={1500}>
      {({ copied, copy }) => (
        <Tooltip label={copied ? "Copied" : "Copy"} withArrow>
          <ActionIcon
            className="copy-btn"
            variant="subtle"
            color={copied ? "teal" : "gray"}
            size="xs"
            onClick={(e) => {
              e.stopPropagation();
              copy();
            }}
            aria-label="Copy"
          >
            {copied ? <IconCheck size={12} /> : <IconCopy size={12} />}
          </ActionIcon>
        </Tooltip>
      )}
    </CopyButton>
  );
}

/** A grid of label/value pairs for detail panels. */
export function Fields({ items, cols = 2 }: { items: [string, ReactNode][]; cols?: number }) {
  return (
    <SimpleGrid cols={{ base: 1, xs: cols }} spacing="md" verticalSpacing="sm">
      {items.map(([label, value]) => (
        <Stack key={label} gap={2} style={{ minWidth: 0 }}>
          <Text size="xs" fw={600} c="dimmed" tt="uppercase" style={{ letterSpacing: "0.04em" }}>
            {label}
          </Text>
          <Box fz="sm" style={{ wordBreak: "break-all" }}>
            {value === null || value === undefined || value === "" ? <Text c="dimmed">—</Text> : value}
          </Box>
        </Stack>
      ))}
    </SimpleGrid>
  );
}

/** Up to `max` red dots for failed attempts, then the number. */
export function AttemptDots({ attempts, max = 3 }: { attempts: number; max?: number }) {
  const n = Math.min(attempts || 0, max);
  return (
    <Group gap={4} wrap="nowrap" aria-label={`${attempts} attempts`}>
      {Array.from({ length: max }, (_, i) => (
        <Box
          key={i}
          w={8}
          h={8}
          style={{
            borderRadius: "50%",
            background: i < n ? "var(--mantine-color-red-filled)" : "var(--mantine-color-default-border)",
          }}
        />
      ))}
      <Text span size="xs" c="dimmed" ml={4} className="tabular">
        {attempts}
      </Text>
    </Group>
  );
}

/** A monospace id inside running text (no copy button). */
export function InlineId({ children }: { children: ReactNode }) {
  return <Code fz="xs">{children}</Code>;
}

/** A search box that applies on Enter or the button, with a clear button once applied. */
export function SearchBox({
  placeholder,
  applied,
  onApply,
  width = 260,
}: {
  placeholder: string;
  applied: string;
  onApply: (value: string) => void;
  width?: number;
}) {
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        const v = new FormData(e.currentTarget).get("q");
        onApply(String(v ?? "").trim());
      }}
      // Re-mount when the applied value is cleared from outside, so the input empties too.
      key={applied ? "applied" : "empty"}
      style={{ maxWidth: "100%" }}
    >
      <Group gap={6} wrap="nowrap" w={{ base: "100%", xs: "auto" }}>
        <TextInput
          name="q"
          size="sm"
          w={{ base: "auto", xs: width }}
          style={{ flex: "1 1 auto", minWidth: 0 }}
          placeholder={placeholder}
          defaultValue={applied}
          leftSection={<IconSearch size={14} />}
          rightSection={
            applied ? (
              <ActionIcon variant="subtle" color="gray" size="sm" aria-label="Clear search" onClick={() => onApply("")}>
                <IconX size={14} />
              </ActionIcon>
            ) : undefined
          }
        />
        <Button type="submit" size="sm" variant="light">
          Search
        </Button>
      </Group>
    </form>
  );
}
