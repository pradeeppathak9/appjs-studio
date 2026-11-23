import { Alert, Box, Paper, Stack, Table } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconArrowsExchange } from "@tabler/icons-react";
import { useMemo, useState } from "react";
import { errorMessage } from "../../../api/client";
import { fetchAll, paths, usePagedList, useStateCounts, useSubscription } from "../../../api/dashboard";
import type { ScheduledTransaction } from "../../../api/types";
import { AttemptDots, DateRangeFilter, Mono, PageTitle, Pager, SearchBox, StateBadge, StatePills, TableCard, Th } from "../../../components/data";
import { EmptyState, ListSkeleton } from "../../../components/ui";
import { useAppContext } from "../../../lib/appContext";
import { downloadCsv, toCsv } from "../../../lib/csv";
import { presetRange, rangeParams } from "../../../lib/dateRange";
import { fmtDate, fmtDateTime, rupeesExact } from "../../../lib/format";
import { PHONEPE_SCHEDULED_STATES } from "../../../lib/states";
import { AttemptsDrawer, SubscriptionDrawer, TxnId } from "./details";
import { ListToolbar } from "./ListToolbar";

/** PhonePe scheduled payments (one row per billing cycle); a row opens its charge attempts. */
export function TransactionsPage() {
  const { app } = useAppContext();
  const [state, setState] = useState("");
  const [subId, setSubId] = useState("");
  const [range, setRange] = useState(() => presetRange(0));
  const [scheduled, setScheduled] = useState<ScheduledTransaction | null>(null);
  const [openSubId, setOpenSubId] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  const countParams = useMemo(() => ({ subscription_id: subId || null, ...rangeParams(range) }), [subId, range]);
  const filters = useMemo(() => ({ ...countParams, state: state || null }), [countParams, state]);
  const counts = useStateCounts(app.id, "scheduled", countParams);
  const list = usePagedList<ScheduledTransaction>(paths.scheduled(app.id), filters);
  const sub = useSubscription(app.id, openSubId);

  const exportCsv = async () => {
    setExporting(true);
    try {
      const all = await fetchAll<ScheduledTransaction>(paths.scheduled(app.id), filters);
      const csv = toCsv(
        ["Payment Date", "Subscription ID", "Transaction ID", "Amount", "State", "Attempts", "Created"],
        all.map((r) => [
          fmtDate(r.payment_date),
          r.subscription_id,
          r.transaction_id || r.merchant_order_id || "",
          (r.amount / 100).toFixed(2),
          r.state,
          r.attempts,
          fmtDateTime(r.created_at),
        ]),
      );
      downloadCsv(`transactions_${app.id}_${new Date().toISOString().slice(0, 10)}.csv`, csv);
    } catch (e) {
      notifications.show({ color: "red", title: "Export failed", message: errorMessage(e) });
    } finally {
      setExporting(false);
    }
  };

  return (
    <Stack gap={0}>
      <PageTitle title="Transactions" description={`PhonePe · ${app.phonepe_environment} · scheduled payments; open one to see its attempts`} />
      <Stack gap="sm" mb="md">
        <StatePills states={PHONEPE_SCHEDULED_STATES} value={state} onChange={setState} counts={counts.data} />
        <DateRangeFilter value={range} onChange={setRange} />
      </Stack>
      <ListToolbar
        search={<SearchBox placeholder="Filter by subscription ID" applied={subId} onApply={setSubId} width={300} />}
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
          <EmptyState icon={<IconArrowsExchange size={30} stroke={1.5} />} title="No transactions found" description="Try another state, a wider date range or a different search." />
        </Paper>
      ) : (
        <Box style={{ opacity: list.isPlaceholderData ? 0.6 : 1, transition: "opacity 120ms" }}>
          <TableCard minWidth={1000}>
            <Table.Thead>
              <Table.Tr>
                <Th>Payment date</Th>
                <Th>Subscription ID</Th>
                <Th>Transaction ID</Th>
                <Th>Amount</Th>
                <Th>State</Th>
                <Th>Attempts</Th>
                <Th>Created</Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {list.rows.map((r) => (
                <Table.Tr
                  key={r.id}
                  style={{ cursor: "pointer" }}
                  onClick={() => setScheduled(r)}
                  tabIndex={0}
                  onKeyDown={(e) => e.key === "Enter" && setScheduled(r)}
                  aria-label={`Payment attempts for ${fmtDate(r.payment_date)}`}
                >
                  <Table.Td style={{ whiteSpace: "nowrap" }}>{fmtDate(r.payment_date)}</Table.Td>
                  <Table.Td>
                    <Mono value={r.subscription_id} onClick={() => setOpenSubId(r.subscription_id)} />
                  </Table.Td>
                  <Table.Td>
                    <TxnId row={r} />
                  </Table.Td>
                  <Table.Td className="tabular">{rupeesExact(r.amount)}</Table.Td>
                  <Table.Td>
                    <StateBadge state={r.state} />
                  </Table.Td>
                  <Table.Td>
                    <AttemptDots attempts={r.attempts} />
                  </Table.Td>
                  <Table.Td style={{ whiteSpace: "nowrap" }}>{fmtDateTime(r.created_at)}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </TableCard>
        </Box>
      )}
      <Pager page={list.page} pageSize={list.pageSize} total={list.total} hasMore={list.hasMore} onChange={list.setPage} />

      <AttemptsDrawer appId={app.id} scheduled={scheduled} onClose={() => setScheduled(null)} onOpenSubscription={setOpenSubId} />
      {/* Opened from a row or from inside the attempts drawer, so it stacks above it. */}
      <SubscriptionDrawer appId={app.id} subscription={openSubId ? sub.data ?? null : null} onClose={() => setOpenSubId(null)} zIndex={300} />
    </Stack>
  );
}
