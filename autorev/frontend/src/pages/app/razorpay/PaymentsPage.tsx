import { Alert, Box, Paper, Stack, Table } from "@mantine/core";
import { IconReceipt } from "@tabler/icons-react";
import { useMemo, useState } from "react";
import { errorMessage } from "../../../api/client";
import { paths, usePagedList } from "../../../api/dashboard";
import type { RazorpayTransaction } from "../../../api/types";
import { Mono, PageTitle, Pager, StateBadge, StatePills, TableCard, Th } from "../../../components/data";
import { EmptyState, ListSkeleton } from "../../../components/ui";
import { useAppContext } from "../../../lib/appContext";
import { fmtDate, rupeesExact } from "../../../lib/format";
import { RAZORPAY_PAYMENT_STATES } from "../../../lib/states";

export function RazorpayPaymentsPage() {
  const { app } = useAppContext();
  const [state, setState] = useState("");
  const filters = useMemo(() => ({ state: state || null }), [state]);
  const list = usePagedList<RazorpayTransaction>(paths.razorpayTransactions(app.id), filters);

  return (
    <Stack gap={0}>
      <PageTitle title="Payments" description={`Razorpay · ${app.razorpay_environment}`} />
      <Box mb="md">
        <StatePills states={RAZORPAY_PAYMENT_STATES} value={state} onChange={setState} />
      </Box>

      {list.isError ? (
        <Alert color="red">{errorMessage(list.error)}</Alert>
      ) : list.isPending ? (
        <ListSkeleton rows={8} />
      ) : list.rows.length === 0 ? (
        <Paper withBorder>
          <EmptyState icon={<IconReceipt size={30} stroke={1.5} />} title="No payments found" description="Try another state." />
        </Paper>
      ) : (
        <Box style={{ opacity: list.isPlaceholderData ? 0.6 : 1, transition: "opacity 120ms" }}>
          <TableCard minWidth={900}>
            <Table.Thead>
              <Table.Tr>
                <Th>Order ref</Th>
                <Th>Subscription</Th>
                <Th>Amount</Th>
                <Th>State</Th>
                <Th>Razorpay payment ID</Th>
                <Th>Created</Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {list.rows.map((r) => (
                <Table.Tr key={r.id}>
                  <Table.Td>
                    <Mono value={r.id} />
                  </Table.Td>
                  <Table.Td>
                    <Mono value={r.subscription_id} />
                  </Table.Td>
                  <Table.Td className="tabular">{rupeesExact(r.amount)}</Table.Td>
                  <Table.Td>
                    <StateBadge state={r.state} />
                  </Table.Td>
                  <Table.Td>
                    <Mono value={r.razorpay_payment_id} />
                  </Table.Td>
                  <Table.Td style={{ whiteSpace: "nowrap" }}>{fmtDate(r.created_at)}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </TableCard>
        </Box>
      )}
      <Pager page={list.page} pageSize={list.pageSize} total={null} hasMore={list.hasMore} onChange={list.setPage} />
    </Stack>
  );
}
