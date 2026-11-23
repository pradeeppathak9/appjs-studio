import { Alert, Button, Card, Code, Collapse, SimpleGrid, Stack, Text, Title } from "@mantine/core";
import { IconBraces, IconDeviceMobile } from "@tabler/icons-react";
import { EmptyState } from "../../components/ui";
import { useState } from "react";
import { errorMessage } from "../../api/client";
import { useCatalog } from "../../api/queries";
import { useCurrentApp } from "../../auth/appContext";
import { TemplateCard } from "../../components/TemplateCard";

/** Exactly what the Android app gets from GET /v1/app/templates. */
export function AndroidPreviewPage() {
  const app = useCurrentApp();
  const catalog = useCatalog(app.id);
  const [raw, setRaw] = useState(false);
  if (catalog.error) return <Alert color="red">{errorMessage(catalog.error)}</Alert>;
  if (!catalog.data) return <Text c="dimmed">Loading…</Text>;
  const c = catalog.data;
  return (
    <Stack gap="sm" data-testid="app-preview">
      <Title order={3} fz={18}>
        Android preview
      </Title>
      <Text size="sm" c="dimmed" mt={-8}>
        What the app receives from GET /v1/app/templates: {c.templates.length} active template
        {c.templates.length === 1 ? "" : "s"}, in this order. Drafts are not included.
      </Text>
      {app.status === "disabled" && (
        <Alert color="orange" p="xs">
          The app is disabled: its calls get 403 app_disabled.
        </Alert>
      )}
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
        {c.templates.map((t) => (
          <TemplateCard
            key={t.id}
            template={t}
            details
            // The catalog's cover_url is /v1/app/... (needs an app key); the console uses the member route.
            coverUrl={t.cover_url ? `/v1/apps/${app.id}/templates/${t.slug}/cover?v=${t.version}` : null}
          />
        ))}
      </SimpleGrid>
      {c.templates.length === 0 && (
        <Card padding="xl">
          <EmptyState
            icon={<IconDeviceMobile size={28} stroke={1.5} />}
            title="The app shows nothing yet"
            description="Activate a template and it appears here, exactly as the Android app will list it."
          />
        </Card>
      )}
      <div>
        <Button size="compact-xs" variant="subtle" color="gray" leftSection={<IconBraces size={14} />} onClick={() => setRaw((r) => !r)}>
          {raw ? "Hide raw JSON" : "Raw JSON"}
        </Button>
        <Collapse expanded={raw}>
          <Code block mt={4}>
            {JSON.stringify(c, null, 2)}
          </Code>
        </Collapse>
      </div>
    </Stack>
  );
}
