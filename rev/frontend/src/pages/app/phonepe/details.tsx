import { Alert, Button, Divider, Drawer, Group, Loader, Modal, Stack, Table, Text, TextInput, Title } from "@mantine/core";
import { IconAlertTriangle, IconCircleCheck } from "@tabler/icons-react";
import { useState } from "react";
import { errorMessage } from "../../../api/client";
import { usePhoneStatus, useRevokeSubscription, useScheduledAttempts, useSubscriptionSchedule } from "../../../api/dashboard";
import type { ScheduledTransaction, Subscription } from "../../../api/types";
import { AttemptDots, Fields, Mono, StateBadge, TableCard, Th } from "../../../components/data";
import { fmtDate, fmtDateTime, rupeesExact } from "../../../lib/format";

function trial(sub: { trail_days: number; amount: number }) {
  return sub.trail_days > 0 ? `${rupeesExact(sub.amount)} (${sub.trail_days}d)` : null;
}

function Loading() {
  return (
    <Group justify="center" py="xl">
      <Loader size="sm" />
    </Group>
  );
}

/** A PhonePe subscription: its fields and its scheduled payments. */
export function SubscriptionDrawer({
  appId,
  subscription,
  onClose,
  zIndex,
}: {
  appId: string;
  subscription: Subscription | null;
  onClose: () => void;
  zIndex?: number;
}) {
  const schedule = useSubscriptionSchedule(appId, subscription?.id ?? null);
  return (
    <Drawer
      opened={!!subscription}
      onClose={onClose}
      position="right"
      size="xl"
      zIndex={zIndex}
      title={<Title order={4}>Subscription</Title>}
    >
      {subscription && (
        <Stack gap="lg">
          <Group gap="sm">
            <StateBadge state={subscription.state} size="md" />
            <Text size="sm" c="dimmed">
              Created {fmtDateTime(subscription.created_at)}
            </Text>
          </Group>
          <Fields
            items={[
              ["Subscription ID", <Mono value={subscription.id} />],
              ["Phone number", <Mono value={subscription.phone_number} />],
              ["Trial amount", trial(subscription)],
              ["Max amount", subscription.max_amount ? rupeesExact(subscription.max_amount) : null],
              ["Amount type", subscription.amount_type],
              ["Frequency", subscription.frequency],
              ["Auth workflow", subscription.auth_workflow_type],
              ["Product type", subscription.product_type],
              ["PhonePe subscription ID", <Mono value={subscription.phonepe_subscription_id} />],
              ["PhonePe order ID", <Mono value={subscription.phonepe_order_id} />],
              ["Next payment", fmtDate(subscription.next_payment_date)],
              ["Last payment status", subscription.last_payment_status],
              ["Total payments", subscription.total_payments],
              ["Trial days", subscription.trail_days],
            ]}
          />
          <Divider />
          <div>
            <Text fw={600} mb="sm">
              Scheduled payments
            </Text>
            {schedule.isPending ? (
              <Loading />
            ) : schedule.isError ? (
              <Alert color="red">{errorMessage(schedule.error)}</Alert>
            ) : schedule.data.length === 0 ? (
              <Text size="sm" c="dimmed" ta="center" py="lg">
                No scheduled payments yet.
              </Text>
            ) : (
              <TableCard minWidth={640}>
                <Table.Thead>
                  <Table.Tr>
                    <Th>Payment date</Th>
                    <Th>Transaction ID</Th>
                    <Th>Amount</Th>
                    <Th>State</Th>
                    <Th>Attempts</Th>
                    <Th>Created</Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {schedule.data.map((sc) => (
                    <Table.Tr key={sc.id}>
                      <Table.Td>{fmtDate(sc.payment_date)}</Table.Td>
                      <Table.Td>
                        <TxnId row={sc} />
                      </Table.Td>
                      <Table.Td className="tabular">{rupeesExact(sc.amount)}</Table.Td>
                      <Table.Td>
                        <StateBadge state={sc.state} />
                      </Table.Td>
                      <Table.Td>
                        <AttemptDots attempts={sc.attempts} />
                      </Table.Td>
                      <Table.Td style={{ whiteSpace: "nowrap" }}>{fmtDateTime(sc.created_at)}</Table.Td>
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

/** PhonePe's transaction id, or (dimmed) our merchant order id until PhonePe assigns one. */
export function TxnId({ row }: { row: Pick<ScheduledTransaction, "transaction_id" | "merchant_order_id"> }) {
  if (row.transaction_id) return <Mono value={row.transaction_id} />;
  if (row.merchant_order_id) {
    return (
      <Mono
        value={row.merchant_order_id}
        dimmed
        title={`Merchant order ID (PhonePe transaction ID not yet available): ${row.merchant_order_id}`}
      />
    );
  }
  return <Text c="dimmed">—</Text>;
}

/** Every charge attempt against one scheduled payment. */
export function AttemptsDrawer({
  appId,
  scheduled,
  onClose,
  onOpenSubscription,
}: {
  appId: string;
  scheduled: ScheduledTransaction | null;
  onClose: () => void;
  onOpenSubscription: (id: string) => void;
}) {
  const attempts = useScheduledAttempts(appId, scheduled?.id ?? null);
  return (
    <Drawer opened={!!scheduled} onClose={onClose} position="right" size="xl" title={<Title order={4}>Payment attempts</Title>}>
      {scheduled && (
        <Stack gap="lg">
          <Group gap="sm">
            <StateBadge state={scheduled.state} size="md" />
            <Text size="sm" c="dimmed">
              Scheduled for {fmtDate(scheduled.payment_date)} · {rupeesExact(scheduled.amount)}
            </Text>
          </Group>
          <Fields
            cols={3}
            items={[
              ["Scheduled ID", <Mono value={scheduled.id} />],
              ["Subscription ID", <Mono value={scheduled.subscription_id} onClick={() => onOpenSubscription(scheduled.subscription_id)} />],
              ["Attempts", scheduled.attempts],
            ]}
          />
          <Divider />
          <div>
            <Text fw={600} mb="sm">
              Attempts
            </Text>
            {attempts.isPending ? (
              <Loading />
            ) : attempts.isError ? (
              <Alert color="red">{errorMessage(attempts.error)}</Alert>
            ) : attempts.data.length === 0 ? (
              <Text size="sm" c="dimmed" ta="center" py="lg">
                No attempts yet.
              </Text>
            ) : (
              <TableCard minWidth={720}>
                <Table.Thead>
                  <Table.Tr>
                    <Th>Order ID</Th>
                    <Th>Amount</Th>
                    <Th>State</Th>
                    <Th>PhonePe txn ID</Th>
                    <Th>Payment due</Th>
                    <Th>Created</Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {attempts.data.map((a) => (
                    <Table.Tr key={a.id}>
                      {/* In full: this is the merchantOrderId PhonePe support asks for. */}
                      <Table.Td>
                        <Mono value={a.id} />
                      </Table.Td>
                      <Table.Td className="tabular">{rupeesExact(a.amount)}</Table.Td>
                      <Table.Td>
                        <StateBadge state={a.state} />
                      </Table.Td>
                      <Table.Td>
                        <Mono value={a.transaction_id} />
                      </Table.Td>
                      <Table.Td>{fmtDate(a.payment_due_date)}</Table.Td>
                      <Table.Td style={{ whiteSpace: "nowrap" }}>{fmtDateTime(a.created_at)}</Table.Td>
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

/** What the public status API answers for a phone number right now (called with the app's API key). */
export function PhoneStatusModal({
  appId,
  apiKey,
  phone,
  onClose,
}: {
  appId: string;
  apiKey: string;
  phone: string | null;
  onClose: () => void;
}) {
  const status = usePhoneStatus(appId, apiKey, phone);
  const d = status.data;
  return (
    <Modal opened={!!phone} onClose={onClose} title={<Text fw={600}>Live status · {phone}</Text>} size="lg">
      {status.isPending ? (
        <Group justify="center" py="xl" gap="sm">
          <Loader size="sm" />
          <Text size="sm" c="dimmed">
            Fetching live status…
          </Text>
        </Group>
      ) : status.isError ? (
        <Alert color="red">{errorMessage(status.error)}</Alert>
      ) : (
        d && (
          <Fields
            items={[
              ["State", <StateBadge state={d.state} />],
              ["Subscription ID", <Mono value={d.subscription_id} />],
              ["Start date", d.subscription_start_date],
              ["Subscription end date", d.subscription_validity_end_date],
              ["Frequency", d.subscription_frequency],
              ["Next payment", d.next_payment_date],
              ["Last payment status", d.last_payment_status],
              ["Successful payments", d.number_of_successful_payments],
              ["Payment amount", d.payment_amount ? rupeesExact(d.payment_amount) : null],
              ["Trial amount", d.trail_amount ? rupeesExact(d.trail_amount) : null],
              ["Trial status", d.trail_status],
            ]}
          />
        )
      )}
    </Modal>
  );
}

/** Cancel a mandate at PhonePe by subscription id. */
export function RevokeModal({ appId, opened, onClose }: { appId: string; opened: boolean; onClose: () => void }) {
  const [subId, setSubId] = useState("");
  const revoke = useRevokeSubscription(appId);
  const close = () => {
    setSubId("");
    revoke.reset();
    onClose();
  };
  const submit = () => {
    const id = subId.trim();
    if (id && !revoke.isPending) revoke.mutate(id);
  };
  return (
    <Modal opened={opened} onClose={close} title={<Text fw={600}>Revoke a subscription</Text>}>
      {revoke.data ? (
        <Stack>
          <Alert color="green" icon={<IconCircleCheck size={16} />}>
            Mandate cancelled at PhonePe.
          </Alert>
          <Fields
            items={[
              ["Subscription ID", <Mono value={revoke.data.id} />],
              ["New state", <StateBadge state={revoke.data.state} />],
            ]}
          />
          <Group justify="flex-end">
            <Button onClick={close}>Done</Button>
          </Group>
        </Stack>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <Stack>
            <Alert color="red" variant="light" icon={<IconAlertTriangle size={16} />}>
              Cancels the mandate at PhonePe so no further payments are collected. This can't be undone.
            </Alert>
            <TextInput
              label="Subscription ID"
              value={subId}
              onChange={(e) => setSubId(e.currentTarget.value)}
              data-autofocus
              styles={{ input: { fontFamily: "var(--mantine-font-family-monospace)" } }}
              error={revoke.error ? errorMessage(revoke.error) : undefined}
            />
            <Group justify="flex-end">
              <Button variant="default" onClick={close}>
                Cancel
              </Button>
              <Button type="submit" color="red" loading={revoke.isPending} disabled={!subId.trim()}>
                Revoke subscription
              </Button>
            </Group>
          </Stack>
        </form>
      )}
    </Modal>
  );
}
