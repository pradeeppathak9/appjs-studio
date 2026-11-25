/** Admin sections for an app's end users: plans, and the users themselves (credits,
 * subscriptions, blocking). Sign-in and payments are in AdminAppSettingsPage. */
import {
  Alert,
  Anchor,
  Badge,
  Box,
  Button,
  Divider,
  Drawer,
  Group,
  Modal,
  NumberInput,
  Pagination,
  ScrollArea,
  SegmentedControl,
  Select,
  Skeleton,
  Stack,
  Switch,
  Table,
  Text,
  Textarea,
  TextInput,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { useDebouncedValue } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import {
  IconCoins,
  IconLink,
  IconPlus,
  IconSearch,
  IconUserCircle,
} from "@tabler/icons-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, errorMessage, unwrap } from "../../api/client";
import { keys, useAppUser, useAppUserCredits, useAppUsers, usePlans } from "../../api/queries";
import type { AppDetail, AppUserAdmin, PlanAdmin, SubscriptionAdmin } from "../../api/types";
import { EmptyState, Section } from "../../components/ui";
import { formatPrice, REASONS, signed, toMinor } from "../../lib/billing";
import { age, formatDate } from "../../lib/format";
import { fieldErrors } from "../../lib/formErrors";

function useAdminRefresh() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: keys.admin });
}

// ---- plans ------------------------------------------------------------------------------------------

type PlanValues = {
  slug: string;
  name: string;
  description: string;
  price: number | string;
  currency: string;
  billing_period: "month" | "year";
  credits_per_month: number | string;
  badge: string;
  status: "active" | "archived";
  trial_enabled: boolean;
  trial_days: number | string;
  trial_credits: number | string;
};

const EMPTY_PLAN: PlanValues = {
  slug: "",
  name: "",
  description: "",
  price: "",
  currency: "INR",
  billing_period: "month",
  credits_per_month: 40,
  badge: "",
  status: "active",
  trial_enabled: false,
  trial_days: 7,
  trial_credits: 10,
};

function planValues(p: PlanAdmin): PlanValues {
  return {
    slug: p.slug,
    name: p.name,
    description: p.description,
    price: p.price_minor / 100,
    currency: p.currency,
    billing_period: p.billing_period,
    credits_per_month: p.credits_per_month,
    badge: p.badge ?? "",
    status: p.status,
    trial_enabled: p.trial_enabled,
    trial_days: p.trial_days,
    trial_credits: p.trial_credits,
  };
}

function planBody(v: PlanValues) {
  return {
    name: v.name,
    description: v.description,
    price_minor: toMinor(v.price),
    currency: v.currency,
    billing_period: v.billing_period,
    credits_per_month: Number(v.credits_per_month),
    badge: v.badge || null,
    status: v.status,
    trial_enabled: v.trial_enabled,
    trial_days: Number(v.trial_days),
    trial_credits: Number(v.trial_credits),
  };
}

function PlanForm({ app, plan, onDone }: { app: AppDetail; plan: PlanAdmin | null; onDone: () => void }) {
  const refresh = useAdminRefresh();
  const form = useForm<PlanValues>({
    initialValues: plan ? planValues(plan) : EMPTY_PLAN,
    validate: {
      price: (x) => (x === "" || Number.isNaN(toMinor(x)) || toMinor(x) < 0 ? "Enter a price" : null),
    },
  });
  const save = useMutation({
    meta: { quiet: true },
    mutationFn: (v: PlanValues) =>
      plan
        ? unwrap(
            api.PUT("/v1/admin/apps/{app_id}/plans/{plan_id}", {
              params: { path: { app_id: app.id, plan_id: plan.id } },
              body: planBody(v),
            }),
          )
        : unwrap(
            api.POST("/v1/admin/apps/{app_id}/plans", {
              params: { path: { app_id: app.id } },
              body: { ...planBody(v), slug: v.slug },
            }),
          ),
    onSuccess: () => {
      refresh();
      onDone();
    },
    onError: (e) =>
      form.setErrors(
        fieldErrors(e, (p) => p in form.values || p === "price_minor").errors as Record<string, string>,
      ),
  });
  return (
    <form onSubmit={form.onSubmit((v) => save.mutate(v))}>
      <Stack>
        {save.error && !Object.keys(form.errors).length && <Alert color="red">{errorMessage(save.error)}</Alert>}
        <Group grow align="flex-start">
          <TextInput label="Name" required data-autofocus {...form.getInputProps("name")} />
          {!plan && (
            <TextInput label="Slug" description="e.g. monthly; fixed" required {...form.getInputProps("slug")} />
          )}
        </Group>
        <Textarea label="Description" autosize minRows={1} {...form.getInputProps("description")} />
        <Group grow align="flex-start">
          <NumberInput
            label="Price"
            description="Shown in the app; payments come later"
            min={0}
            decimalScale={2}
            thousandSeparator=","
            required
            {...form.getInputProps("price")}
          />
          <Select
            label="Currency"
            data={["INR", "USD", "EUR"]}
            allowDeselect={false}
            {...form.getInputProps("currency")}
          />
        </Group>
        <Group grow align="flex-start">
          <div>
            <Text size="sm" fw={500} mb={4}>
              Billed every
            </Text>
            <SegmentedControl
              fullWidth
              data={[
                { value: "month", label: "Month" },
                { value: "year", label: "Year" },
              ]}
              {...form.getInputProps("billing_period")}
            />
          </div>
          <NumberInput
            label="Credits per month"
            description="Granted monthly, also on yearly plans"
            min={0}
            allowDecimal={false}
            required
            {...form.getInputProps("credits_per_month")}
          />
        </Group>
        <Group grow align="flex-start">
          <TextInput label="Badge" placeholder="e.g. Best value" {...form.getInputProps("badge")} />
          {plan && (
            <Select
              label="Status"
              data={[
                { value: "active", label: "Active (offered)" },
                { value: "archived", label: "Archived (hidden)" },
              ]}
              allowDeselect={false}
              {...form.getInputProps("status")}
            />
          )}
        </Group>
        <Divider />
        <Switch
          label="Offer a free trial"
          description="Signed-in users can start it once from the app, on this plan or another with a trial"
          {...form.getInputProps("trial_enabled", { type: "checkbox" })}
        />
        {form.values.trial_enabled && (
          <Group grow align="flex-start">
            <NumberInput
              label="Trial days"
              min={1}
              max={365}
              allowDecimal={false}
              required
              {...form.getInputProps("trial_days")}
            />
            <NumberInput
              label="Trial credits"
              description="Granted once when the trial starts; kept after it ends"
              min={0}
              allowDecimal={false}
              required
              {...form.getInputProps("trial_credits")}
            />
          </Group>
        )}
        <Button type="submit" loading={save.isPending}>
          {plan ? "Save plan" : "Create plan"}
        </Button>
      </Stack>
    </form>
  );
}

export function Plans({ app }: { app: AppDetail }) {
  const plans = usePlans(app.id);
  const refresh = useAdminRefresh();
  const [editing, setEditing] = useState<PlanAdmin | "new" | null>(null);
  const remove = useMutation({
    mutationFn: (planId: string) =>
      unwrap(
        api.DELETE("/v1/admin/apps/{app_id}/plans/{plan_id}", {
          params: { path: { app_id: app.id, plan_id: planId } },
        }),
      ),
    onSuccess: refresh,
  });
  return (
    <Section
      title="Plans"
      icon={<IconCoins size={18} />}
      description="Subscriptions the app offers. Until payments are connected, give a plan to a user under Users."
      testId="plans"
      actions={
        <Button size="xs" onClick={() => setEditing("new")} leftSection={<IconPlus size={14} />}>
          New plan
        </Button>
      }
    >
      {plans.isLoading ? (
        <Skeleton height={80} />
      ) : plans.data?.length ? (
        <Table highlightOnHover={false} data-testid="plans-table">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Plan</Table.Th>
              <Table.Th>Price</Table.Th>
              <Table.Th>Credits / month</Table.Th>
              <Table.Th>Free trial</Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {plans.data.map((p) => (
              <Table.Tr key={p.id} data-slug={p.slug} style={{ opacity: p.status === "archived" ? 0.55 : 1 }}>
                <Table.Td>
                  <Group gap={6}>
                    <Text size="sm" fw={500}>
                      {p.name}
                    </Text>
                    {p.badge && (
                      <Badge size="xs" variant="light">
                        {p.badge}
                      </Badge>
                    )}
                    {p.status === "archived" && (
                      <Badge size="xs" color="gray">
                        archived
                      </Badge>
                    )}
                  </Group>
                  <Text size="xs" c="dimmed">
                    {p.slug}
                  </Text>
                </Table.Td>
                <Table.Td className="tabular">
                  {formatPrice(p.price_minor, p.currency)} / {p.billing_period}
                </Table.Td>
                <Table.Td className="tabular">{p.credits_per_month}</Table.Td>
                <Table.Td className="tabular" data-testid="plan-trial">
                  {p.trial_enabled ? (
                    `${p.trial_days} days · ${p.trial_credits} credits`
                  ) : (
                    <Text size="sm" c="dimmed">
                      Off
                    </Text>
                  )}
                </Table.Td>
                <Table.Td w={150}>
                  <Group gap={4} justify="flex-end" wrap="nowrap">
                    <Button size="compact-xs" variant="subtle" onClick={() => setEditing(p)}>
                      Edit
                    </Button>
                    <Button
                      size="compact-xs"
                      variant="subtle"
                      color="red"
                      loading={remove.isPending && remove.variables === p.id}
                      onClick={() =>
                        window.confirm(
                          `Remove plan "${p.name}"? A plan anyone ever subscribed to is archived instead.`,
                        ) && remove.mutate(p.id)
                      }
                    >
                      Remove
                    </Button>
                  </Group>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      ) : (
        <EmptyState
          compact
          icon={<IconCoins size={20} stroke={1.5} />}
          title="No plans yet"
          description="Create the plans the app's Subscribe screen shows."
        />
      )}
      <Modal
        opened={editing !== null}
        onClose={() => setEditing(null)}
        title={editing === "new" ? "New plan" : `Edit ${editing?.name ?? "plan"}`}
        size="lg"
      >
        {editing !== null && (
          <PlanForm app={app} plan={editing === "new" ? null : editing} onDone={() => setEditing(null)} />
        )}
      </Modal>
    </Section>
  );
}

// ---- users ---------------------------------------------------------------------------------------------

function who(u: AppUserAdmin): string {
  return u.name || u.email || u.phone || "Unnamed user";
}

const PROVIDERS: Record<string, string> = { manual: "Given by an admin", trial: "Free trial", razorpay: "Razorpay", phonepe: "PhonePe" };

/** Which payment-gateway subscription pays for this one: shown, and editable by admins. */
function GatewayLink({ app, userId, sub }: { app: AppDetail; userId: string; sub: SubscriptionAdmin }) {
  const refresh = useAdminRefresh();
  const [editing, setEditing] = useState(false);
  const form = useForm({
    initialValues: { provider: sub.provider, provider_ref: sub.provider_ref ?? "" },
  });
  const link = useMutation({
    meta: { quiet: true },
    mutationFn: (v: { provider: string; provider_ref: string }) =>
      unwrap(
        api.PUT("/v1/admin/apps/{app_id}/users/{user_id}/subscriptions/{subscription_id}/link", {
          params: { path: { app_id: app.id, user_id: userId, subscription_id: sub.id } },
          body: {
            provider: v.provider as "manual" | "razorpay" | "phonepe",
            provider_ref: v.provider === "manual" ? null : v.provider_ref.trim(),
          },
        }),
      ),
    onSuccess: () => {
      setEditing(false);
      refresh();
      notifications.show({ color: "green", message: "Payment link saved" });
    },
    onError: (e) => form.setErrors(fieldErrors(e, (f) => f in form.values).errors),
  });
  if (!editing)
    return (
      <Group gap="xs" wrap="nowrap" data-testid="gateway-link">
        <Badge variant="light" color={sub.provider === "manual" ? "gray" : "violet"}>
          {PROVIDERS[sub.provider] ?? sub.provider}
        </Badge>
        {sub.provider_ref && (
          <Text size="xs" ff="monospace" data-testid="gateway-ref">
            {sub.provider_ref}
          </Text>
        )}
        <Anchor component="button" type="button" size="xs" onClick={() => setEditing(true)}>
          {sub.provider === "manual" ? "Link Razorpay / PhonePe" : "Change"}
        </Anchor>
      </Group>
    );
  return (
    <form onSubmit={form.onSubmit((v) => link.mutate(v))} data-testid="gateway-link-form">
      <Stack gap="xs">
        <SegmentedControl
          size="xs"
          data={[
            { value: "manual", label: "None" },
            { value: "razorpay", label: "Razorpay" },
            { value: "phonepe", label: "PhonePe" },
          ]}
          {...form.getInputProps("provider")}
        />
        {form.values.provider !== "manual" && (
          <TextInput
            size="xs"
            label={`${PROVIDERS[form.values.provider]} subscription id`}
            placeholder={form.values.provider === "razorpay" ? "sub_…" : "merchant subscription id"}
            leftSection={<IconLink size={14} />}
            required
            {...form.getInputProps("provider_ref")}
          />
        )}
        {link.error && !Object.keys(form.errors).length && (
          <Text size="xs" c="red">
            {errorMessage(link.error)}
          </Text>
        )}
        <Group gap="xs">
          <Button size="xs" type="submit" loading={link.isPending}>
            Save
          </Button>
          <Button size="xs" variant="subtle" color="gray" onClick={() => setEditing(false)}>
            Cancel
          </Button>
        </Group>
      </Stack>
    </form>
  );
}

const HISTORY_PAGE = 20;

/** Every credit transaction of the user, a page at a time. */
function CreditHistory({ appId, userId }: { appId: string; userId: string }) {
  const [page, setPage] = useState(1);
  const history = useAppUserCredits(appId, userId, (page - 1) * HISTORY_PAGE, HISTORY_PAGE);
  if (history.error) return <Alert color="red">{errorMessage(history.error)}</Alert>;
  if (!history.data) return <Skeleton height={120} />;
  const { items, total } = history.data;
  const pages = Math.max(1, Math.ceil(total / HISTORY_PAGE));
  return (
    <Stack gap="xs">
      <Table data-testid="ledger" highlightOnHover={false}>
        <Table.Tbody>
          {items.map((e) => (
            <Table.Tr key={e.id}>
              <Table.Td w={70} className="tabular" c={e.delta > 0 ? "green" : undefined} fw={600}>
                {signed(e.delta)}
              </Table.Td>
              <Table.Td>
                <Text size="sm">{REASONS[e.reason] ?? e.reason}</Text>
                {(e.note || e.job_id) && (
                  <Text size="xs" c="dimmed">
                    {e.note}
                    {e.note && e.job_id && " · "}
                    {e.job_id && (
                      <Anchor component={Link} to={`/jobs/${e.job_id}`} size="xs">
                        job
                      </Anchor>
                    )}
                  </Text>
                )}
              </Table.Td>
              <Table.Td w={110}>
                <Text size="xs" c="dimmed" title={formatDate(e.created_at)}>
                  {age(e.created_at)}
                </Text>
              </Table.Td>
            </Table.Tr>
          ))}
          {items.length === 0 && (
            <Table.Tr>
              <Table.Td>
                <Text size="sm" c="dimmed">
                  No credit changes yet.
                </Text>
              </Table.Td>
            </Table.Tr>
          )}
        </Table.Tbody>
      </Table>
      {total > HISTORY_PAGE && (
        <Group justify="space-between">
          <Text size="xs" c="dimmed">
            {total} transactions
          </Text>
          <Pagination size="sm" total={pages} value={page} onChange={setPage} />
        </Group>
      )}
    </Stack>
  );
}

function UserDetail({ app, userId }: { app: AppDetail; userId: string }) {
  const detail = useAppUser(app.id, userId);
  const plans = usePlans(app.id);
  const refresh = useAdminRefresh();
  const [planId, setPlanId] = useState<string | null>(null);
  const adjustForm = useForm({ initialValues: { delta: "" as number | string, note: "" } });
  const path = { app_id: app.id, user_id: userId };

  const adjust = useMutation({
    meta: { quiet: true },
    mutationFn: (v: { delta: number; note: string }) =>
      unwrap(api.POST("/v1/admin/apps/{app_id}/users/{user_id}/credits", { params: { path }, body: v })),
    onSuccess: (r) => {
      adjustForm.reset();
      refresh();
      notifications.show({ color: "green", message: `Balance is now ${r.credits}` });
    },
  });
  const grant = useMutation({
    meta: { quiet: true },
    mutationFn: (plan_id: string) =>
      unwrap(api.POST("/v1/admin/apps/{app_id}/users/{user_id}/subscriptions", { params: { path }, body: { plan_id } })),
    onSuccess: () => {
      setPlanId(null);
      refresh();
    },
  });
  const cancel = useMutation({
    mutationFn: (subscription_id: string) =>
      unwrap(
        api.DELETE("/v1/admin/apps/{app_id}/users/{user_id}/subscriptions/{subscription_id}", {
          params: { path: { ...path, subscription_id } },
        }),
      ),
    onSuccess: refresh,
  });
  const setStatus = useMutation({
    mutationFn: (status: "active" | "blocked") =>
      unwrap(api.PUT("/v1/admin/apps/{app_id}/users/{user_id}/status", { params: { path }, body: { status } })),
    onSuccess: refresh,
  });

  if (detail.error) return <Alert color="red">{errorMessage(detail.error)}</Alert>;
  const u = detail.data;
  if (!u) return <Skeleton height={300} />;
  const active = u.subscription;
  const activeAdmin = u.subscriptions.find((x) => x.status === "active");
  const past = u.subscriptions.filter((x) => x.status !== "active");
  const offered = (plans.data ?? []).filter((p) => p.status === "active");

  return (
    <Stack data-testid="app-user-detail">
      <Group justify="space-between" align="flex-start">
        <div>
          <Text fw={600}>{who(u)}</Text>
          <Text size="sm" c="dimmed">
            {[u.email, u.phone].filter(Boolean).join(" · ")} · signed in with {u.sign_in}
          </Text>
          <Text size="xs" c="dimmed">
            Joined {formatDate(u.created_at)} · last seen {age(u.last_seen_at)}
          </Text>
        </div>
        <Badge color={u.status === "active" ? "green" : "red"}>{u.status}</Badge>
      </Group>

      <Group gap="xs" align="baseline">
        <Text fz={28} fw={700} className="tabular" data-testid="user-credits">
          {u.credits}
        </Text>
        <Text c="dimmed">credits</Text>
      </Group>

      <form
        onSubmit={adjustForm.onSubmit((v) => adjust.mutate({ delta: Number(v.delta), note: v.note }))}
        data-testid="adjust-credits"
      >
        <Group align="flex-end" wrap="nowrap">
          <NumberInput
            label="Add or remove"
            placeholder="e.g. 10 or -5"
            allowDecimal={false}
            w={130}
            required
            {...adjustForm.getInputProps("delta")}
          />
          <TextInput label="Note" placeholder="why" required style={{ flex: 1 }} {...adjustForm.getInputProps("note")} />
          <Button type="submit" loading={adjust.isPending} variant="light">
            Apply
          </Button>
        </Group>
        {adjust.error && (
          <Text size="xs" c="red" mt={4}>
            {errorMessage(adjust.error)}
          </Text>
        )}
      </form>

      <Divider label="Subscription" labelPosition="left" />
      {active ? (
        <Group justify="space-between">
          <div>
            <Text size="sm" fw={500}>
              {active.plan.name}
              {active.trial && " · free trial"}
            </Text>
            <Text size="xs" c="dimmed">
              until {formatDate(active.current_period_end)}
              {active.next_credit_grant_at && ` · next credits ${formatDate(active.next_credit_grant_at)}`}
            </Text>
            {activeAdmin && !activeAdmin.trial && (
              <Box mt={6}>
                <GatewayLink key={activeAdmin.provider + (activeAdmin.provider_ref ?? "")} app={app} userId={userId} sub={activeAdmin} />
              </Box>
            )}
          </div>
          <Button
            size="xs"
            color="red"
            variant="subtle"
            loading={cancel.isPending}
            onClick={() => window.confirm("Cancel now? No more monthly credits.") && cancel.mutate(active.id)}
          >
            Cancel
          </Button>
        </Group>
      ) : (
        <Group align="flex-end" wrap="nowrap">
          <Select
            label="Give a plan"
            placeholder={offered.length ? "Pick a plan" : "Create a plan first"}
            data={offered.map((p) => ({
              value: p.id,
              label: `${p.name} · ${formatPrice(p.price_minor, p.currency)}/${p.billing_period} · ${p.credits_per_month} credits/month`,
            }))}
            value={planId}
            onChange={setPlanId}
            style={{ flex: 1 }}
          />
          <Button disabled={!planId} loading={grant.isPending} onClick={() => grant.mutate(planId!)}>
            Give
          </Button>
        </Group>
      )}
      {grant.error && (
        <Text size="xs" c="red">
          {errorMessage(grant.error)}
        </Text>
      )}

      {past.length > 0 && (
        <Stack gap={4}>
          {past.map((x) => (
            <Group key={x.id} gap="xs" wrap="nowrap">
              <Text size="xs" c="dimmed">
                {x.plan.name} · {x.status} · {formatDate(x.created_at)}
              </Text>
              <Badge size="xs" variant="light" color="gray">
                {PROVIDERS[x.provider] ?? x.provider}
              </Badge>
              {x.provider_ref && (
                <Text size="xs" ff="monospace" c="dimmed">
                  {x.provider_ref}
                </Text>
              )}
            </Group>
          ))}
        </Stack>
      )}

      <Divider label="Transaction history" labelPosition="left" />
      <CreditHistory appId={app.id} userId={userId} />

      <Divider />
      <Group>
        {u.status === "active" ? (
          <Button
            color="red"
            variant="outline"
            size="xs"
            loading={setStatus.isPending}
            onClick={() =>
              window.confirm("Block this user? They are signed out and can't sign in again.") &&
              setStatus.mutate("blocked")
            }
          >
            Block user
          </Button>
        ) : (
          <Button variant="outline" size="xs" loading={setStatus.isPending} onClick={() => setStatus.mutate("active")}>
            Unblock user
          </Button>
        )}
      </Group>
    </Stack>
  );
}

const USERS_PAGE = 25;

/** The app's users with search and pages; a row opens the user (credits, subscription, history). */
export function UsersTable({ app }: { app: AppDetail }) {
  const [q, setQ] = useState("");
  const [debounced] = useDebouncedValue(q.trim(), 300);
  const [page, setPage] = useState(1);
  const users = useAppUsers(app.id, debounced, (page - 1) * USERS_PAGE, USERS_PAGE);
  const [open, setOpen] = useState<string | null>(null);
  const total = users.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / USERS_PAGE));
  const first = (page - 1) * USERS_PAGE + 1;
  return (
    <>
      <Stack gap="sm">
        <TextInput
          placeholder="Search name, email, phone or user id"
          leftSection={<IconSearch size={16} />}
          value={q}
          onChange={(e) => {
            setQ(e.currentTarget.value);
            setPage(1);
          }}
          aria-label="Search users"
        />
        {users.error ? (
          <Alert color="red">{errorMessage(users.error)}</Alert>
        ) : users.isLoading ? (
          <Skeleton height={120} />
        ) : users.data?.items.length ? (
          <>
            <ScrollArea>
              <Table highlightOnHover data-testid="app-users-table" style={{ opacity: users.isPlaceholderData ? 0.6 : 1 }}>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>User</Table.Th>
                    <Table.Th>Credits</Table.Th>
                    <Table.Th>Plan</Table.Th>
                    <Table.Th>Joined</Table.Th>
                    <Table.Th>Last seen</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {users.data.items.map((u) => (
                    <Table.Tr key={u.id} style={{ cursor: "pointer" }} onClick={() => setOpen(u.id)} data-user={u.id}>
                      <Table.Td>
                        <Group gap={6}>
                          <Text size="sm" fw={500}>
                            {who(u)}
                          </Text>
                          {u.status === "blocked" && (
                            <Badge size="xs" color="red">
                              blocked
                            </Badge>
                          )}
                        </Group>
                        <Text size="xs" c="dimmed">
                          {u.sign_in === "google" ? u.email : u.phone}
                        </Text>
                      </Table.Td>
                      <Table.Td className="tabular">{u.credits}</Table.Td>
                      <Table.Td>
                        <Text size="sm">{u.subscription?.plan.name ?? "—"}</Text>
                        {u.subscription && u.subscription.provider !== "manual" && (
                          <Text size="xs" c="dimmed">
                            {PROVIDERS[u.subscription.provider] ?? u.subscription.provider}
                          </Text>
                        )}
                      </Table.Td>
                      <Table.Td>
                        <Text size="xs" c="dimmed">
                          {formatDate(u.created_at)}
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        <Text size="xs" c="dimmed">
                          {age(u.last_seen_at)}
                        </Text>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </ScrollArea>
            <Group justify="space-between">
              <Text size="xs" c="dimmed" data-testid="users-count">
                {first}–{first + users.data.items.length - 1} of {total} user{total === 1 ? "" : "s"}
              </Text>
              {pages > 1 && <Pagination size="sm" total={pages} value={page} onChange={setPage} />}
            </Group>
          </>
        ) : (
          <EmptyState
            compact
            icon={<IconUserCircle size={20} stroke={1.5} />}
            title={debounced ? "No matching users" : "No users yet"}
            description={debounced ? undefined : "Users appear here after they sign in to the app."}
          />
        )}
      </Stack>
      <Drawer opened={open !== null} onClose={() => setOpen(null)} position="right" size="lg" title="App user">
        {open && <UserDetail app={app} userId={open} />}
      </Drawer>
    </>
  );
}

export function AppUsers({ app }: { app: AppDetail }) {
  return (
    <Section
      title="Users"
      icon={<IconUserCircle size={18} />}
      description="People signed in to the app: their credits, plan and history."
      testId="app-users"
    >
      <UsersTable app={app} />
    </Section>
  );
}
