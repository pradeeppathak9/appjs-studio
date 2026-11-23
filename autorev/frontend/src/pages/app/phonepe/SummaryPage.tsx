import { Alert, Box, Button, Group, Paper, Progress, SimpleGrid, Skeleton, Stack, Text, Tooltip } from "@mantine/core";
import { IconCalendarDue, IconChecks, IconCoin, IconInbox, IconRefresh, IconRepeat } from "@tabler/icons-react";
import { useState, type ReactNode } from "react";
import { errorMessage } from "../../../api/client";
import { useSummary } from "../../../api/dashboard";
import type { Summary } from "../../../api/types";
import { DateRangeFilter, PageTitle } from "../../../components/data";
import { EmptyState, StatusDot } from "../../../components/ui";
import { isInvalid, presetRange } from "../../../lib/dateRange";
import { humanize, num, rupees, rupeesExact } from "../../../lib/format";
import { useAppContext } from "../../../lib/appContext";
import { stateColor } from "../../../lib/states";

function StatCard({
  label,
  value,
  title,
  lines,
  icon,
  color,
}: {
  label: string;
  value: string;
  title?: string;
  lines: (string | null)[];
  icon: ReactNode;
  color: string;
}) {
  return (
    <Paper withBorder p="lg" shadow="xs">
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <Text size="xs" fw={600} c="dimmed" tt="uppercase" style={{ letterSpacing: "0.05em" }}>
          {label}
        </Text>
        <Box c={`${color}.6`}>{icon}</Box>
      </Group>
      <Tooltip label={title} disabled={!title}>
        <Text fw={700} fz={28} lh={1.2} mt={6} className="tabular" w="fit-content">
          {value}
        </Text>
      </Tooltip>
      {lines.filter(Boolean).map((l) => (
        <Text key={l} size="xs" c="dimmed" mt={4}>
          {l}
        </Text>
      ))}
    </Paper>
  );
}

function Breakdown({
  title,
  byState,
  total,
  valueByState,
  note,
}: {
  title: string;
  byState: Record<string, number>;
  total: number;
  valueByState?: Record<string, number>;
  note?: string;
}) {
  const entries = Object.entries(byState).sort((a, b) => b[1] - a[1]);
  return (
    <Paper withBorder p="lg" shadow="xs">
      <Text fw={600} size="sm" mb="md">
        {title}
      </Text>
      {total === 0 ? (
        <Text size="sm" c="dimmed">
          Nothing in this window.
        </Text>
      ) : (
        <Stack gap={10}>
          {entries.map(([state, count]) => {
            const pct = total > 0 ? (count / total) * 100 : 0;
            const color = stateColor(state);
            return (
              <Group key={state} gap={8} wrap="nowrap">
                <StatusDot color={color} />
                <Text size="xs" w={140} truncate title={state} style={{ flexShrink: 0 }}>
                  {humanize(state)}
                </Text>
                <Progress value={pct} color={color} size="sm" style={{ flex: 1, minWidth: 30 }} aria-label={`${humanize(state)} ${pct.toFixed(0)}%`} />
                <Text size="xs" fw={600} w={56} ta="right" className="tabular" style={{ flexShrink: 0 }}>
                  {num(count)}
                </Text>
                <Text size="xs" c="dimmed" w={36} ta="right" className="tabular" style={{ flexShrink: 0 }}>
                  {pct >= 0.1 ? `${pct.toFixed(0)}%` : "<1%"}
                </Text>
                {valueByState && (
                  <Tooltip label={rupeesExact(valueByState[state])}>
                    <Text size="xs" c="dimmed" w={84} ta="right" className="tabular" style={{ flexShrink: 0 }}>
                      {rupees(valueByState[state])}
                    </Text>
                  </Tooltip>
                )}
              </Group>
            );
          })}
          {note && (
            <Text size="xs" c="dimmed" mt={4} pt="sm" style={{ borderTop: "1px solid var(--mantine-color-default-border)" }}>
              {note}
            </Text>
          )}
        </Stack>
      )}
    </Paper>
  );
}

function SummaryView({ data }: { data: Summary }) {
  const active = data.subscriptions_by_state["ACTIVE"] || 0;
  const share = data.subscriptions_total > 0 ? ((active / data.subscriptions_total) * 100).toFixed(0) : null;
  const scheduledValue = data.scheduled_value_by_state_paise["SCHEDULED"];
  return (
    <Stack gap="lg">
      <SimpleGrid cols={{ base: 1, xs: 2, lg: 4 }} spacing="md">
        <StatCard
          label="Total subscriptions"
          value={num(data.subscriptions_total)}
          lines={["includes archived"]}
          icon={<IconRepeat size={20} />}
          color="indigo"
        />
        <StatCard
          label="Active"
          value={num(active)}
          lines={[share !== null ? `${share}% of subscriptions created` : null]}
          icon={<IconChecks size={20} />}
          color="green"
        />
        <StatCard
          label="Revenue collected"
          value={rupees(data.revenue_collected_paise)}
          title={rupeesExact(data.revenue_collected_paise)}
          lines={[
            `${num(data.transactions_by_state["COMPLETED"])} payments · ${rupees(data.payment_revenue_collected_paise)}`,
            `${num(data.trial_setups_count)} setups · ${rupees(data.trial_revenue_collected_paise)}`,
          ]}
          icon={<IconCoin size={20} />}
          color="cyan"
        />
        <StatCard
          label="Upcoming payments"
          value={rupees(scheduledValue)}
          title={rupeesExact(scheduledValue)}
          lines={[
            `${num(data.scheduled_by_state["SCHEDULED"])} scheduled`,
            `${rupees(data.scheduled_value_paise)} across ${num(data.scheduled_total)} total`,
          ]}
          icon={<IconCalendarDue size={20} />}
          color="orange"
        />
      </SimpleGrid>
      <SimpleGrid cols={{ base: 1, md: 2, xl: 3 }} spacing="md">
        <Breakdown
          title="Subscriptions by state"
          byState={data.subscriptions_by_state}
          total={data.subscriptions_total}
          note="Failed includes archived subscriptions."
        />
        <Breakdown title="Transactions by state" byState={data.transactions_by_state} total={data.transactions_total} />
        <Breakdown
          title="Scheduled payments by state"
          byState={data.scheduled_by_state}
          total={data.scheduled_total}
          valueByState={data.scheduled_value_by_state_paise}
        />
      </SimpleGrid>
    </Stack>
  );
}

function SummarySkeleton() {
  return (
    <Stack gap="lg">
      <SimpleGrid cols={{ base: 1, xs: 2, lg: 4 }} spacing="md">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} height={124} radius="md" />
        ))}
      </SimpleGrid>
      <SimpleGrid cols={{ base: 1, md: 2, xl: 3 }} spacing="md">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} height={220} radius="md" />
        ))}
      </SimpleGrid>
    </Stack>
  );
}

/** PhonePe summary: totals and state breakdowns for a date window (default today). */
export function SummaryPage() {
  const { app } = useAppContext();
  const [range, setRange] = useState(() => presetRange(0));
  const invalid = isInvalid(range);
  const summary = useSummary(app.id, range, !invalid);
  const d = summary.data;
  const empty = d && d.subscriptions_total === 0 && d.transactions_total === 0 && d.scheduled_total === 0;

  return (
    <Stack gap={0}>
      <PageTitle
        title="Summary"
        description={`PhonePe · ${app.phonepe_environment}`}
        actions={
          <>
            {summary.dataUpdatedAt > 0 && !summary.isFetching && (
              <Text size="xs" c="dimmed">
                Updated {new Date(summary.dataUpdatedAt).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}
              </Text>
            )}
            <Button
              variant="default"
              size="xs"
              leftSection={<IconRefresh size={14} />}
              loading={summary.isFetching}
              disabled={invalid}
              onClick={() => summary.refetch()}
            >
              Refresh
            </Button>
          </>
        }
      />
      <Box mb="lg">
        <DateRangeFilter value={range} onChange={setRange} />
      </Box>
      {summary.isError && (
        <Alert color="red" mb="lg" title="Could not load the summary">
          <Group justify="space-between">
            <Text size="sm">{errorMessage(summary.error)}</Text>
            <Button size="xs" variant="white" color="red" onClick={() => summary.refetch()}>
              Try again
            </Button>
          </Group>
        </Alert>
      )}
      {!d ? (
        summary.isPending && !invalid ? <SummarySkeleton /> : null
      ) : empty ? (
        <Paper withBorder>
          <EmptyState
            icon={<IconInbox size={30} stroke={1.5} />}
            title="No activity in this window"
            description="Try a wider date range, or integrate using the URLs in the Integration guide."
          />
        </Paper>
      ) : (
        <Box style={{ opacity: summary.isPlaceholderData ? 0.6 : 1, transition: "opacity 120ms" }}>
          <SummaryView data={d} />
        </Box>
      )}
    </Stack>
  );
}
