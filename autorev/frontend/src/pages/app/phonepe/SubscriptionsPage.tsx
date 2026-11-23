import { Alert, Box, Button, Paper, Stack, Table, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconBan, IconRepeat } from "@tabler/icons-react";
import { useMemo, useState } from "react";
import { errorMessage } from "../../../api/client";
import { fetchAll, paths, usePagedList, useStateCounts } from "../../../api/dashboard";
import type { Subscription } from "../../../api/types";
import { DateRangeFilter, Mono, PageTitle, Pager, SearchBox, StateBadge, StatePills, TableCard, Th } from "../../../components/data";
import { EmptyState, ListSkeleton } from "../../../components/ui";
import { useAppContext } from "../../../lib/appContext";
import { downloadCsv, toCsv } from "../../../lib/csv";
import { presetRange, rangeParams } from "../../../lib/dateRange";
import { fmtDate, fmtDateTime, rupeesExact } from "../../../lib/format";
import { searchParams } from "../../../lib/search";
import { PHONEPE_SUBSCRIPTION_STATES } from "../../../lib/states";
import { PhoneStatusModal, RevokeModal, SubscriptionDrawer } from "./details";
import { ListToolbar } from "./ListToolbar";

export function SubscriptionsPage() {
  const { app } = useAppContext();
  const [state, setState] = useState("");
  const [search, setSearch] = useState("");
  const [range, setRange] = useState(() => presetRange(0));
  const [selected, setSelected] = useState<Subscription | null>(null);
  const [phone, setPhone] = useState<string | null>(null);
  const [revoking, setRevoking] = useState(false);
  const [exporting, setExporting] = useState(false);

  // The pill counts leave out the state filter, so choosing a pill doesn't zero the others.
  const countParams = useMemo(() => ({ ...searchParams(search), ...rangeParams(range) }), [search, range]);
  const filters = useMemo(() => ({ ...countParams, state: state || null }), [countParams, state]);
  const counts = useStateCounts(app.id, "subscriptions", countParams);
  const list = usePagedList<Subscription>(paths.subscriptions(app.id), filters);

  const exportCsv = async () => {
    setExporting(true);
    try {
      const all = await fetchAll<Subscription>(paths.subscriptions(app.id), filters);
      const csv = toCsv(
        ["Subscription ID", "Phone", "Trial Amount", "Trial Days", "Max Amount", "Frequency", "State", "Next Payment", "Last Payment Status", "Total Paid", "Created"],
        all.map((r) => [
          r.id,
          r.phone_number,
          r.trail_days > 0 ? (r.amount / 100).toFixed(2) : "",
          r.trail_days || 0,
          r.max_amount ? (r.max_amount / 100).toFixed(2) : "",
          r.frequency,
          r.state,
          r.next_payment_date ? new Date(r.next_payment_date).toLocaleDateString("en-IN") : "",
          r.last_payment_status || "",
          r.total_payments || 0,
          fmtDateTime(r.created_at),
        ]),
      );
      downloadCsv(`subscriptions_${app.id}_${new Date().toISOString().slice(0, 10)}.csv`, csv);
    } catch (e) {
      notifications.show({ color: "red", title: "Export failed", message: errorMessage(e) });
    } finally {
      setExporting(false);
    }
  };

  return (
    <Stack gap={0}>
      <PageTitle
        title="Subscriptions"
        description={`PhonePe · ${app.phonepe_environment}`}
        actions={
          <Button variant="light" color="red" size="sm" leftSection={<IconBan size={14} />} onClick={() => setRevoking(true)}>
            Revoke a subscription
          </Button>
        }
      />
      <Stack gap="sm" mb="md">
        <StatePills states={PHONEPE_SUBSCRIPTION_STATES} value={state} onChange={setState} counts={counts.data} />
        <DateRangeFilter value={range} onChange={setRange} />
      </Stack>
      <ListToolbar
        search={<SearchBox placeholder="Phone or subscription ID" applied={search} onApply={setSearch} />}
        total={list.total}
        loading={list.isPending}
        onExport={list.rows.length > 0 ? exportCsv : undefined}
        exporting={exporting}
      />

      {list.isError ? (
        <Alert color="red">{errorMessage(list.error)}</Alert>
      ) : list.isPending ? (
        <ListSkeleton rows={8} />
      ) : list.rows.length === 0 ? (
        <Paper withBorder>
          <EmptyState icon={<IconRepeat size={30} stroke={1.5} />} title="No subscriptions found" description="Try another state, a wider date range or a different search." />
        </Paper>
      ) : (
        <Box style={{ opacity: list.isPlaceholderData ? 0.6 : 1, transition: "opacity 120ms" }}>
          <TableCard minWidth={1100}>
            <Table.Thead>
              <Table.Tr>
                <Th>Subscription ID</Th>
                <Th>Phone</Th>
                <Th>Trial amt</Th>
                <Th>Max amt</Th>
                <Th>Frequency</Th>
                <Th>State</Th>
                <Th>Next payment</Th>
                <Th>Total paid</Th>
                <Th>Created</Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {list.rows.map((r) => (
                <Table.Tr key={r.id}>
                  <Table.Td>
                    <Mono value={r.id} onClick={() => setSelected(r)} />
                  </Table.Td>
                  <Table.Td>
                    <Mono value={r.phone_number} onClick={() => setPhone(r.phone_number)} title="Show the live status for this number" />
                  </Table.Td>
                  <Table.Td className="tabular" style={{ whiteSpace: "nowrap" }}>
                    {r.trail_days > 0 ? `${rupeesExact(r.amount)} (${r.trail_days}d)` : "—"}
                  </Table.Td>
                  <Table.Td className="tabular">{r.max_amount ? rupeesExact(r.max_amount) : "—"}</Table.Td>
                  <Table.Td>{r.frequency}</Table.Td>
                  <Table.Td>
                    <StateBadge state={r.state} />
                  </Table.Td>
                  <Table.Td style={{ whiteSpace: "nowrap" }}>{fmtDate(r.next_payment_date)}</Table.Td>
                  <Table.Td className="tabular">{r.total_payments}</Table.Td>
                  <Table.Td style={{ whiteSpace: "nowrap" }}>
                    <Text size="sm">{fmtDateTime(r.created_at)}</Text>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </TableCard>
        </Box>
      )}
      <Pager page={list.page} pageSize={list.pageSize} total={list.total} hasMore={list.hasMore} onChange={list.setPage} />

      <SubscriptionDrawer appId={app.id} subscription={selected} onClose={() => setSelected(null)} />
      <PhoneStatusModal appId={app.id} apiKey={app.api_key} phone={phone} onClose={() => setPhone(null)} />
      <RevokeModal appId={app.id} opened={revoking} onClose={() => setRevoking(false)} />
    </Stack>
  );
}
