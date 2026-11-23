/** How a client app (e.g. Restyle on Android) integrates with this app's API, filled in with this app's
 * values. A summary of docs/APPS_API.md, which stays the full contract: change both together. */
import {
  ActionIcon,
  Alert,
  Anchor,
  Badge,
  Box,
  Code,
  CopyButton,
  Group,
  List,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Title,
  Tooltip,
} from "@mantine/core";
import {
  IconCheck,
  IconCopy,
  IconKey,
  IconLogin,
  IconPhoto,
  IconRoute,
  IconShieldCheck,
} from "@tabler/icons-react";
import type { ReactNode } from "react";
import { Link } from "react-router";
import { useCatalog } from "../../api/queries";
import { useCurrentApp } from "../../auth/appContext";
import { isAdmin } from "../../auth/roles";
import { useSession } from "../../auth/session";
import { Section } from "../../components/ui";

function CopyIcon({ value }: { value: string }) {
  return (
    <CopyButton value={value} timeout={1500}>
      {({ copied, copy }) => (
        <Tooltip label={copied ? "Copied" : "Copy"} withArrow>
          <ActionIcon
            variant="subtle"
            color={copied ? "teal" : "gray"}
            onClick={copy}
            aria-label="Copy"
          >
            {copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
          </ActionIcon>
        </Tooltip>
      )}
    </CopyButton>
  );
}

function Snippet({ code }: { code: string }) {
  return (
    <Box pos="relative">
      <Code block fz="xs" style={{ whiteSpace: "pre", overflowX: "auto" }}>
        {code}
      </Code>
      <Box pos="absolute" top={6} right={6}>
        <CopyIcon value={code} />
      </Box>
    </Box>
  );
}

function Fact({
  label,
  value,
  copy,
}: {
  label: string;
  value: ReactNode;
  copy?: string;
}) {
  return (
    <div>
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
        {label}
      </Text>
      <Group gap={4} wrap="nowrap">
        <Text size="sm" ff="monospace" truncate>
          {value}
        </Text>
        {copy && <CopyIcon value={copy} />}
      </Group>
    </div>
  );
}

const ERRORS: [string, string, string][] = [
  [
    "401",
    "unauthenticated",
    "Wrong or revoked app key, session ended, or a paid template run without signing in: show sign-in",
  ],
  [
    "402",
    "insufficient_credits",
    "Not enough credits for this template: show plans",
  ],
  [
    "403",
    "app_disabled",
    "The app is switched off in the console: show a maintenance message",
  ],
  [
    "404",
    "not_found",
    "Template no longer active, or job not visible: refresh the list",
  ],
  [
    "413",
    "payload_too_large",
    "Photo over 10 MB: downscale on the device first",
  ],
  [
    "422",
    "validation_error",
    "details[] has {field, message}, e.g. photo or variables.mood",
  ],
  [
    "429",
    "rate_limited",
    "Daily app limit or hourly device limit reached: try later",
  ],
  [
    "503",
    "provider_unavailable",
    "The model behind the template is down right now",
  ],
];

export function IntegrationGuidePage() {
  const app = useCurrentApp();
  const me = useSession();
  const catalog = useCatalog(app.id);
  const base = window.location.origin;

  // A real template from this app makes the examples copy-pasteable.
  const sample = catalog.data?.templates[0];
  const slug = sample?.slug ?? "<template-slug>";
  const slot = sample?.inputs[0]?.name ?? "photo";
  const vars = Object.fromEntries(
    (sample?.variables ?? []).map((v) => [v.name, v.default]),
  );
  const varsJson = JSON.stringify(vars);
  const hasVars = Object.keys(vars).length > 0;

  const curl = `KEY=cak_...            # the app key (see step 1)
DEV=test-device-1      # one random id per install
B=${base}

curl -H "X-App-Key: $KEY" -H "X-Device-Id: $DEV" $B/v1/app            # config: sign-in methods, payments
curl -H "X-App-Key: $KEY" -H "X-Device-Id: $DEV" $B/v1/app/templates  # active templates, in order
curl -H "X-App-Key: $KEY" -H "X-Device-Id: $DEV" \\
     -F ${slot}=@me.jpg${hasVars ? ` -F 'variables=${varsJson}'` : ""} \\
     $B/v1/app/templates/${slug}/generations                         # -> 202 {"id": ..., "status": "queued"}
curl -H "X-App-Key: $KEY" -H "X-Device-Id: $DEV" $B/v1/app/generations/<job id>
curl -H "X-App-Key: $KEY" -H "X-Device-Id: $DEV" -o out.png $B<assets[0].url>
# When sign-in is required, add: -H "Authorization: Bearer cas_..."`;

  const kotlin = `val client = OkHttpClient.Builder()
    .addInterceptor { chain ->
        val req = chain.request().newBuilder()
            .header("X-App-Key", BuildConfig.APP_KEY)
            .header("X-Device-Id", installId)                 // UUID made once, kept in prefs
        session.token?.let { req.header("Authorization", "Bearer $it") }
        val res = chain.proceed(req.build())
        if (res.code == 401 && session.token != null) session.clear()   // ended: show sign-in
        res
    }.build()

val base = "${base}"

// run "${slug}"
val body = MultipartBody.Builder().setType(MultipartBody.FORM)
    .addFormDataPart("${slot}", "photo.jpg", jpegBytes.toRequestBody("image/jpeg".toMediaType()))${
      hasVars ? `\n    .addFormDataPart("variables", """${varsJson}""")` : ""
    }
    .build()
val job = client.newCall(Request.Builder()
    .url("$base/v1/app/templates/${slug}/generations").post(body).build()).execute()

// poll GET $base/v1/app/generations/{id} every 2 s until succeeded / failed,
// then load base + assets[0].url through the same client (Coil/Glide too, so headers are sent).`;

  return (
    <Stack gap="lg" data-testid="integration-guide">
      <div>
        <Title order={3} fz={18}>
          Integration guide
        </Title>
        <Text size="sm" c="dimmed">
          How the {app.platform} app talks to {app.name}. The full contract is{" "}
          <Code>docs/APPS_API.md</Code> in the appjs-studio repo.
        </Text>
      </div>

      {app.status === "disabled" && (
        <Alert color="orange" p="xs">
          This app is disabled: every call gets 403 app_disabled.
        </Alert>
      )}

      <Section title="This app" icon={<IconRoute size={18} />}>
        <SimpleGrid cols={{ base: 1, sm: 3 }}>
          <Fact label="API base URL" value={base} copy={base} />
          <Fact label="App slug" value={app.slug} copy={app.slug} />
          <Fact
            label="Active templates"
            value={catalog.data ? String(catalog.data.templates.length) : "…"}
          />
        </SimpleGrid>
        <Text size="xs" c="dimmed" mt="sm">
          From an Android emulator, the host is{" "}
          <Code>http://10.0.2.2:8010</Code>. Serve the API over HTTPS before
          release: Android blocks plain HTTP by default.
        </Text>
      </Section>

      <Section
        title="1. App key and headers"
        icon={<IconKey size={18} />}
        description="Every call carries the app key; a device id keeps each install's jobs private."
        actions={
          isAdmin(me) ? (
            <Anchor component={Link} to={`/admin/apps/${app.id}`} size="sm">
              Manage keys
            </Anchor>
          ) : undefined
        }
      >
        <Table withTableBorder fz="sm" mb="sm">
          <Table.Tbody>
            <Table.Tr>
              <Table.Td>
                <Code>X-App-Key</Code>
              </Table.Td>
              <Table.Td>
                Required. <Code>cak_…</Code>, created by an admin (Admin → Apps
                → {app.name} → Keys) and shown once. Keep it in the build config
                (e.g. <Code>local.properties</Code> → <Code>BuildConfig</Code>),
                not in git.
              </Table.Td>
            </Table.Tr>
            <Table.Tr>
              <Table.Td>
                <Code>X-Device-Id</Code>
              </Table.Td>
              <Table.Td>
                Strongly recommended. A random id generated once per install
                (1–128 chars).
              </Table.Td>
            </Table.Tr>
            <Table.Tr>
              <Table.Td>
                <Code>Authorization</Code>
              </Table.Td>
              <Table.Td>
                After sign-in: <Code>Bearer cas_…</Code>. Required for templates
                and runs when the app has Require sign-in on.
              </Table.Td>
            </Table.Tr>
          </Table.Tbody>
        </Table>
        <Text size="xs" c="dimmed">
          A key inside an APK can be extracted: treat it as an identifier. Daily
          and per-device limits, key rotation and disabling the app limit the
          damage.
        </Text>
      </Section>

      <Section
        title="2. Sign-in"
        icon={<IconLogin size={18} />}
        description="Users sign in per app. Call GET /v1/app on start to see which methods are on."
        actions={
          isAdmin(me) ? (
            <Anchor component={Link} to={`/apps/${app.id}/settings`} size="sm">
              Sign-in settings
            </Anchor>
          ) : undefined
        }
      >
        <List size="sm" spacing={6}>
          <List.Item>
            <b>Google</b>: get an ID token with Credential Manager for{" "}
            <Code>sign_in.google_client_id</Code> (the Web client id), then{" "}
            <Code>
              POST /v1/app/auth/google {"{"}"id_token"{"}"}
            </Code>
            .
          </List.Item>
          <List.Item>
            <b>Phone, msg91</b>: <Code>POST /v1/app/auth/otp/send</Code>, then{" "}
            <Code>/otp/verify</Code> with the code.
          </List.Item>
          <List.Item>
            <b>Phone, Firebase</b>: verify with Firebase Auth, then{" "}
            <Code>POST /v1/app/auth/firebase</Code> with its ID token.
          </List.Item>
          <List.Item>
            Each returns{" "}
            <Code>
              {"{"}"token": "cas_…"{"}"}
            </Code>
            : keep it in encrypted storage. It lasts 90 days and is extended on
            use; a 401 with a token means sign in again.
          </List.Item>
        </List>
      </Section>

      <Section
        title="3. List, run, poll, download"
        icon={<IconPhoto size={18} />}
        description={
          sample ? (
            <>
              Examples use this app's first active template,{" "}
              <Badge variant="light">{sample.title}</Badge>
            </>
          ) : (
            "No active templates yet: activate one to run these examples."
          )
        }
      >
        <List size="sm" spacing={6} mb="md" type="ordered">
          <List.Item>
            <Code>GET /v1/app/templates</Code>: one card per template (title,
            cover, credit cost, inputs, variables). Fetch on start and on
            refresh; don't hard-code slugs.
          </List.Item>
          <List.Item>
            <Code>POST /v1/app/templates/{"{slug}"}/generations</Code>,
            multipart: one file per input slot (field name = slot name,
            PNG/JPEG/WebP, max 10 MB), optional <Code>variables</Code> as a JSON
            string. The server checks and charges the template's credits, then
            returns 202 with <Code>credits</Code>, the user's new balance: show it
            at once. Not enough: 402 <Code>insufficient_credits</Code>. Templates
            that cost credits always need a signed-in user (401 otherwise).
          </List.Item>
          <List.Item>
            <Code>GET /v1/app/generations/{"{id}"}</Code> every 2 s (5 s after
            30 s) until <Code>succeeded</Code> or <Code>failed</Code>. Images
            take 5–30 s; video can take minutes.
          </List.Item>
          <List.Item>
            Download <Code>assets[].url</Code> with the same headers. Failed
            jobs refund their credits automatically: refresh{" "}
            <Code>GET /v1/app/me</Code> to show the balance.
          </List.Item>
        </List>
        <Stack gap="sm">
          <Text size="sm" fw={600}>
            Try it with curl
          </Text>
          <Snippet code={curl} />
          <Text size="sm" fw={600}>
            Kotlin (OkHttp)
          </Text>
          <Snippet code={kotlin} />
        </Stack>
      </Section>

      <Section
        title="Errors"
        icon={<IconShieldCheck size={18} />}
        description={
          <>
            Every error is{" "}
            <Code>{'{"error": {"code", "message", "field", "details"}}'}</Code>.
            Handle these:
          </>
        }
      >
        <Table withTableBorder striped fz="sm">
          <Table.Tbody>
            {ERRORS.map(([status, code, what]) => (
              <Table.Tr key={code}>
                <Table.Td w={60}>{status}</Table.Td>
                <Table.Td w={200}>
                  <Code>{code}</Code>
                </Table.Td>
                <Table.Td>{what}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Section>
    </Stack>
  );
}
