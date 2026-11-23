import { Alert, Box, Divider, Drawer, Group, Loader, Paper, Stack, Table, Text, Title } from "@mantine/core";
import { IconRepeat } from "@tabler/icons-react";
import { useMemo, useState } from "react";
import { errorMessage } from "../../../api/client";
import { paths, usePagedList, useRazorpaySubscriptionTransactions } from "../../../api/dashboard";
import type { RazorpaySubscription } from "../../../api/types";
import { Fields, Mono, PageTitle, Pager, SearchBox, StateBadge, StatePills, TableCard, Th } from "../../../components/data";
import { EmptyState, ListSkeleton } from "../../../components/ui";
import { useAppContext } from "../../../lib/appContext";
import { fmtDate, fmtDateTime, rupeesExact } from "../../../lib/format";
import { RAZORPAY_SUBSCRIPTION_STATES } from "../../../lib/states";

function RazorpaySubscriptionDrawer({
  appId,
  subscription: sub,
  onClose,
}: {
  appId: string;
  subscription: RazorpaySubscription | null;
  onClose: () => void;
}) {
  const txns = useRazorpaySubscriptionTransactions(appId, sub?.id ?? null);
  return (
    <Drawer opened={!!sub} onClose={onClose} position="right" size="xl" title={<Title order={4}>Subscription</Title>}>
      {sub && (
        <Stack gap="lg">
          <Group gap="sm">
            <StateBadge state={sub.state} size="md" />
            <Text size="sm" c="dimmed">
              Created {fmtDateTime(sub.created_at)}
            </Text>
          </Group>
          <Fields
            items={[
              ["Subscription ID", <Mono value={sub.id} />],
              ["Name", sub.name],
              ["Email", sub.email],
              ["Phone number", <Mono value={sub.phone_number} />],
              ["Amount", rupeesExact(sub.amount)],
              ["Max amount", sub.max_amount ? rupeesExact(sub.max_amount) : null],
              ["Amount type", sub.amount_type],
              ["Frequency", sub.frequency],
              ["Method", sub.method],
              ["Razorpay customer ID", <Mono value={sub.razorpay_customer_id} />],
              ["Razorpay order ID", <Mono value={sub.razorpay_order_id} />],
              ["Razorpay token ID", <Mono value={sub.razorpay_token_id} />],
              ["Next payment", fmtDate(sub.next_payment_date)],
              ["Last payment status", sub.last_payment_status],
              ["Total payments", sub.total_payments],
            ]}
          />
          <Divider />
          <div>
            <Text fw={600} mb="sm">
              Payments
            </Text>
            {txns.isPending ? (
              <Group justify="center" py="xl">
                <Loader size="sm" />
              </Group>
            ) : txns.isError ? (
              <Alert color="red">{errorMessage(txns.error)}</Alert>
            ) : txns.data.length === 0 ? (
              <Text size="sm" c="dimmed" ta="center" py="lg">
                No payments yet.
              </Text>
            ) : (
              <TableCard minWidth={760}>
                <Table.Thead>
                  <Table.Tr>
                    <Th>ID</Th>
                    <Th>Amount</Th>
                    <Th>State</Th>
                    <Th>Razorpay order ID</Th>
                    <Th>Razorpay payment ID</Th>
                    <Th>Created</Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {txns.data.map((tx) => (
                    <Table.Tr key={tx.id}>
                      <Table.Td>
                        <Mono value={tx.id} />
                      </Table.Td>
                      <Table.Td className="tabular">{rupeesExact(tx.amount)}</Table.Td>
                      <Table.Td>
                        <StateBadge state={tx.state} />
                      </Table.Td>
                      <Table.Td>
                        <Mono value={tx.razorpay_order_id} />
                      </Table.Td>
                      <Table.Td>
                        <Mono value={tx.razorpay_payment_id} />
                      </Table.Td>
                      <Table.Td style={{ whiteSpace: "nowrap" }}>{fmtDateTime(tx.created_at)}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </TableCard>
            )}
          </div>
        </Stack>
      )}
    </Drawer>
  );
}

export function RazorpaySubscriptionsPage() {
  const { app } = useAppContext();
  const [state, setState] = useState("");
  const [phone, setPhone] = useState("");
  const [selected, setSelected] = useState<RazorpaySubscription | null>(null);
  const filters = useMemo(() => ({ state: state || null, phone_number: phone || null }), [state, phone]);
  const list = usePagedList<RazorpaySubscription>(paths.razorpaySubscriptions(app.id), filters);

  return (
    <Stack gap={0}>
      <PageTitle title="Subscriptions" description={`Razorpay · ${app.razorpay_environment}`} />
      <Box mb="md">
        <StatePills states={RAZORPAY_SUBSCRIPTION_STATES} value={state} onChange={setState} />
      </Box>
      <Group mb="md">
        <SearchBox placeholder="Search by phone" applied={phone} onApply={setPhone} />
      </Group>

      {list.isError ? (
        <Alert color="red">{errorMessage(list.error)}</Alert>
      ) : list.isPending ? (
        <ListSkeleton rows={8} />
      ) : list.rows.length === 0 ? (
        <Paper withBorder>
          <EmptyState icon={<IconRepeat size={30} stroke={1.5} />} title="No subscriptions found" description="Try another state or a different phone number." />
        </Paper>
      ) : (
        <Box style={{ opacity: list.isPlaceholderData ? 0.6 : 1, transition: "opacity 120ms" }}>
          <TableCard minWidth={1200}>
            <Table.Thead>
              <Table.Tr>
                <Th>Subscription ID</Th>
                <Th>Customer ID</Th>
                <Th>Name</Th>
                <Th>Phone</Th>
                <Th>Amount</Th>
                <Th>Method</Th>
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
                    <Mono value={r.razorpay_customer_id} />
                  </Table.Td>
                  <Table.Td>{r.name}</Table.Td>
                  <Table.Td>
                    <Mono value={r.phone_number} />
                  </Table.Td>
                  <Table.Td className="tabular">{rupeesExact(r.amount)}</Table.Td>
                  <Table.Td>{r.method}</Table.Td>
                  <Table.Td>{r.frequency}</Table.Td>
                  <Table.Td>
                    <StateBadge state={r.state} />
                  </Table.Td>
                  <Table.Td style={{ whiteSpace: "nowrap" }}>{fmtDate(r.next_payment_date)}</Table.Td>
                  <Table.Td className="tabular">{r.total_payments}</Table.Td>
                  <Table.Td style={{ whiteSpace: "nowrap" }}>{fmtDate(r.created_at)}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </TableCard>
        </Box>
      )}
      <Pager page={list.page} pageSize={list.pageSize} total={null} hasMore={list.hasMore} onChange={list.setPage} />
      <RazorpaySubscriptionDrawer appId={app.id} subscription={selected} onClose={() => setSelected(null)} />
    </Stack>
  );
}
