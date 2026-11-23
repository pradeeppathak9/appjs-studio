/** App settings: how the app's users sign in, which payment gateway it uses, and its plans.
 * Each section saves on its own (PATCH), so saving one never overwrites another. */
import {
  Alert,
  Badge,
  Button,
  Grid,
  Group,
  List,
  NumberInput,
  PasswordInput,
  SegmentedControl,
  Skeleton,
  Stack,
  Switch,
  Text,
  Textarea,
  TextInput,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import {
  IconArrowLeft,
  IconCreditCard,
  IconDeviceFloppy,
  IconLogin,
  IconUsers,
} from "@tabler/icons-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import { errorMessage } from "../../api/client";
import { keys, patchApp, useAdminApp } from "../../api/queries";
import type { AppDetail } from "../../api/types";
import { AppAvatar, Section } from "../../components/ui";
import {
  appValues,
  paymentBody,
  signInBody,
  type AppFormValues,
} from "../../lib/appForm";
import { fieldErrors } from "../../lib/formErrors";
import { Plans } from "./AppEndUsers";

/** A form over the app's settings that saves `body(values)` with PATCH. */
function useSectionForm(
  app: AppDetail,
  body: (v: AppFormValues) => object,
  saved: string,
) {
  const qc = useQueryClient();
  const form = useForm<AppFormValues>({ initialValues: appValues(app) });
  const save = useMutation({
    meta: { quiet: true },
    mutationFn: (v: AppFormValues) => patchApp(app.id, body(v)),
    onSuccess: (a) => {
      qc.setQueryData(keys.adminApp(a.id), a);
      qc.invalidateQueries({ queryKey: keys.admin });
      form.resetDirty(appValues(a));
      notifications.show({ color: "green", message: saved });
    },
    onError: (e) =>
      form.setErrors(fieldErrors(e, (p) => p in form.values).errors),
  });
  const rest = fieldErrors(save.error, (p) => p in form.values).rest;
  const problem =
    save.error && (rest.length || !Object.keys(form.errors).length)
      ? rest.join("; ") || errorMessage(save.error)
      : null;
  return { form, save, problem };
}

function SaveRow({
  dirty,
  loading,
  problem,
}: {
  dirty: boolean;
  loading: boolean;
  problem: string | null;
}) {
  return (
    <Stack gap="xs">
      {problem && <Alert color="red">{problem}</Alert>}
      <Group>
        <Button
          type="submit"
          loading={loading}
          disabled={!dirty}
          leftSection={<IconDeviceFloppy size={16} />}
        >
          Save
        </Button>
      </Group>
    </Stack>
  );
}

type SectionForm = ReturnType<typeof useSectionForm>["form"];

/** Which service sends and checks the phone codes, and its credentials. */
function PhoneProvider({ app, form }: { app: AppDetail; form: SectionForm }) {
  const qc = useQueryClient();
  const v = form.values;
  const removeKey = useMutation({
    mutationFn: () => patchApp(app.id, { msg91_auth_key: null }),
    onSuccess: (a) => {
      qc.setQueryData(keys.adminApp(a.id), a);
      notifications.show({ color: "green", message: "MSG91 auth key removed" });
    },
  });
  const hasKey = app.msg91_auth_key_set || !!v.msg91_auth_key.trim();
  const hasTemplate = !!v.msg91_template_id.trim();
  return (
    <Stack gap="sm" pl="xl" data-testid="phone-provider">
      <div>
        <Text size="sm" fw={500} mb={4}>
          Codes sent by
        </Text>
        <SegmentedControl
          data={[
            { value: "msg91", label: "MSG91" },
            { value: "firebase", label: "Firebase" },
          ]}
          {...form.getInputProps("phone_provider")}
        />
        <Text size="xs" c="dimmed" mt={4}>
          {v.phone_provider === "msg91"
            ? "Our server texts the code through MSG91 and checks it."
            : "The app verifies the number with Firebase Authentication; our server checks Firebase's sign-in token."}
        </Text>
      </div>

      {v.phone_provider === "msg91" && (
        <>
          {!app.secrets_key_set && (
            <Alert color="yellow">
              The server can't store credentials yet: set{" "}
              <code>SECRETS_KEY</code> (any long random string) in its
              environment and restart it.
            </Alert>
          )}
          <PasswordInput
            label={
              <Group gap={6} component="span">
                MSG91 auth key
                {app.msg91_auth_key_set && (
                  <Badge size="xs" color="green" variant="light">
                    saved
                  </Badge>
                )}
              </Group>
            }
            description="MSG91 → API → Auth Key. Stored encrypted; it can be replaced, never shown again."
            placeholder={
              app.msg91_auth_key_set
                ? "Saved · type a new key to replace it"
                : "Not set"
            }
            disabled={!app.secrets_key_set}
            autoComplete="new-password"
            {...form.getInputProps("msg91_auth_key")}
          />
          {app.msg91_auth_key_set && (
            <Group>
              <Button
                variant="subtle"
                color="red"
                size="compact-sm"
                loading={removeKey.isPending}
                onClick={() => removeKey.mutate()}
              >
                Remove saved key
              </Button>
            </Group>
          )}
          <Group grow align="flex-start">
            <TextInput
              label="Template ID"
              description="A DLT-approved OTP template (MSG91 → OTP / Flow)."
              placeholder="6650ab12cd34ef56"
              {...form.getInputProps("msg91_template_id")}
            />
            <TextInput
              label="Code variable"
              description="Where the code goes in the template, without the ##."
              placeholder="otp"
              {...form.getInputProps("msg91_otp_var")}
            />
          </Group>
          {hasKey !== hasTemplate ? (
            <Alert color="yellow">
              Add both the auth key and the template ID. Until then, codes go
              through the server's own SMS settings.
            </Alert>
          ) : (
            !hasKey && (
              <Alert color="gray" variant="light">
                No MSG91 account of this app's own: codes go through the
                server's SMS settings (<code>SMS_PROVIDER</code>), which in
                development only writes them to the API log.
              </Alert>
            )
          )}
        </>
      )}

      {v.phone_provider === "firebase" && (
        <>
          <TextInput
            label="Firebase project ID"
            description="Firebase console → Project settings → General → Project ID."
            placeholder="my-app-1a2b3"
            {...form.getInputProps("firebase_project_id")}
          />
          {!v.firebase_project_id.trim() && (
            <Alert color="yellow">
              Add the project ID: without it every phone sign-in is refused.
            </Alert>
          )}
          <Alert color="gray" variant="light" title="In the Firebase console">
            <List size="sm" spacing={2}>
              <List.Item>
                Authentication → Sign-in method → turn on Phone (needs the Blaze
                plan).
              </List.Item>
              <List.Item>
                Add the Android app with its package name and the SHA-1 and
                SHA-256 of the debug and release signing keys; put its{" "}
                <code>google-services.json</code> in the app.
              </List.Item>
              <List.Item>
                Test numbers for store review go under Phone → Phone numbers for
                testing.
              </List.Item>
            </List>
            <Text size="xs" c="dimmed" mt={6}>
              No secret is needed here: sign-in tokens are checked against
              Firebase's public keys.
            </Text>
          </Alert>
        </>
      )}
    </Stack>
  );
}

function SignInSettings({ app }: { app: AppDetail }) {
  const { form, save, problem } = useSectionForm(
    app,
    signInBody,
    "Sign-in settings saved",
  );
  const v = form.values;
  return (
    <Section
      title="Sign-in"
      icon={<IconLogin size={18} />}
      description="How the app's users sign in. Turn on one method or both."
      testId="sign-in-settings"
    >
      <form onSubmit={form.onSubmit((x) => save.mutate(x))}>
        <Stack>
          <Switch
            label="Mobile number"
            description="A 6-digit code by SMS."
            {...form.getInputProps("auth_phone_enabled", { type: "checkbox" })}
          />
          {v.auth_phone_enabled && <PhoneProvider app={app} form={form} />}
          <Switch
            label="Google"
            description="Sign in with the Google account on the phone."
            {...form.getInputProps("auth_google_enabled", { type: "checkbox" })}
          />
          {v.auth_google_enabled && (
            <Textarea
              label="Google OAuth Web client ids"
              description="One per line, from Google Cloud Console (type: Web application). The app requests ID tokens for the first one."
              placeholder="1234-abc.apps.googleusercontent.com"
              autosize
              minRows={1}
              {...form.getInputProps("google_client_ids")}
            />
          )}
          {v.auth_google_enabled && !v.google_client_ids.trim() && (
            <Alert color="yellow">
              Add a Web client id: without one the app can't offer Google
              sign-in.
            </Alert>
          )}
          <Switch
            label="Require sign-in"
            description="Styles, runs and results need a signed-in user; each run costs the style's credits."
            {...form.getInputProps("require_login", { type: "checkbox" })}
          />
          {v.require_login &&
            !v.auth_google_enabled &&
            !v.auth_phone_enabled && (
              <Alert color="yellow">
                Sign-in is required but no method is on: nobody can use the app.
              </Alert>
            )}
          <NumberInput
            label="Credits on sign-up"
            description="Given once, when an account is created."
            min={0}
            allowDecimal={false}
            w={220}
            {...form.getInputProps("signup_credits")}
          />
          <SaveRow
            dirty={form.isDirty()}
            loading={save.isPending}
            problem={problem}
          />
        </Stack>
      </form>
    </Section>
  );
}

const PROVIDERS: { value: AppFormValues["payment_provider"]; label: string }[] =
  [
    { value: "none", label: "None" },
    { value: "razorpay", label: "Razorpay" },
    { value: "phonepe", label: "PhonePe" },
  ];

function PaymentSettings({ app }: { app: AppDetail }) {
  const { form, save, problem } = useSectionForm(
    app,
    paymentBody,
    "Payment settings saved",
  );
  const v = form.values;
  return (
    <Section
      title="Payments"
      icon={<IconCreditCard size={18} />}
      description="The gateway the app's subscriptions are paid through."
      testId="payment-settings"
      actions={
        app.payment_provider !== "none" && (
          <Badge
            color={app.payment_mode === "live" ? "green" : "yellow"}
            variant="light"
          >
            {app.payment_mode}
          </Badge>
        )
      }
    >
      <form onSubmit={form.onSubmit((x) => save.mutate(x))}>
        <Stack>
          <div>
            <Text size="sm" fw={500} mb={4}>
              Gateway
            </Text>
            <SegmentedControl
              fullWidth
              data={PROVIDERS}
              {...form.getInputProps("payment_provider")}
            />
          </div>
          {v.payment_provider !== "none" && (
            <div>
              <Text size="sm" fw={500} mb={4}>
                Mode
              </Text>
              <SegmentedControl
                data={[
                  { value: "test", label: "Test" },
                  { value: "live", label: "Live" },
                ]}
                {...form.getInputProps("payment_mode")}
              />
              <Text size="xs" c="dimmed" mt={4}>
                Test mode uses the gateway's sandbox: no real money moves.
              </Text>
            </div>
          )}
          {v.payment_provider === "razorpay" && (
            <TextInput
              label="Razorpay Key ID"
              description={`Razorpay Dashboard → Account & Settings → API Keys (rzp_${v.payment_mode}_…). Sent to the app for Checkout.`}
              placeholder={`rzp_${v.payment_mode}_XXXXXXXXXXXXXX`}
              {...form.getInputProps("razorpay_key_id")}
            />
          )}
          {v.payment_provider === "phonepe" && (
            <TextInput
              label="PhonePe Merchant ID"
              description="PhonePe Business dashboard → Developer settings. Stays on the server."
              placeholder="M22XXXXXXXXXX"
              {...form.getInputProps("phonepe_merchant_id")}
            />
          )}
          <Alert color="gray" variant="light">
            {v.payment_provider === "none"
              ? "No gateway: the app shows plans but can't take payments. Give plans to users by hand under Users."
              : "Checkout isn't connected yet. The key secret (Razorpay) or salt key (PhonePe) is added with that step; until then, give plans to users by hand."}
          </Alert>
          <SaveRow
            dirty={form.isDirty()}
            loading={save.isPending}
            problem={problem}
          />
        </Stack>
      </form>
    </Section>
  );
}

/** Admin → Apps → the app → App settings, and the app dashboard's Settings tab (`inApp`, admins only). */
export function AdminAppSettingsPage({ inApp = false }: { inApp?: boolean }) {
  const { appId } = useParams();
  const app = useAdminApp(appId!);
  if (app.error) return <Alert color="red">{errorMessage(app.error)}</Alert>;
  if (!app.data)
    return (
      <Stack>
        <Skeleton height={40} width={320} />
        <Skeleton height={300} />
      </Stack>
    );
  const a = app.data;
  return (
    <Stack>
      {!inApp && (
        <Button
          component={Link}
          to={`/admin/apps/${a.id}`}
          variant="subtle"
          size="compact-sm"
          leftSection={<IconArrowLeft size={14} />}
          w="fit-content"
        >
          {a.name}
        </Button>
      )}
      <Group justify="space-between" wrap="wrap">
        <Group gap="md" wrap="nowrap">
          <AppAvatar name={a.name} slug={a.slug} size={44} />
          <div>
            <Title order={3} fz={20}>
              App settings
            </Title>
            <Text c="dimmed" size="sm">
              {a.name} · {a.slug}
            </Text>
          </div>
        </Group>
        {inApp && (
          <Button
            component={Link}
            to={`/admin/apps/${a.id}`}
            variant="default"
            leftSection={<IconUsers size={16} />}
            data-testid="app-admin-link"
          >
            Members, keys and users
          </Button>
        )}
      </Group>
      <Grid gap="lg">
        <Grid.Col span={{ base: 12, lg: 6 }}>
          <Stack gap="lg">
            <SignInSettings app={a} />
            <PaymentSettings app={a} />
          </Stack>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 6 }}>
          <Plans app={a} />
        </Grid.Col>
      </Grid>
    </Stack>
  );
}
