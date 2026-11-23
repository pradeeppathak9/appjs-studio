import { Alert, Button, Group, Stack } from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Link, Navigate, Outlet, useParams } from "react-router";
import { errorMessage } from "../../api/client";
import { keys, useApp } from "../../api/queries";
import type { App } from "../../api/types";
import { AppAvatar, EnvBadge, GatewayBadge, ListSkeleton, PageHeader } from "../../components/ui";
import { useAppContext, type AppContext } from "../../lib/appContext";
import { appLanding, gatewaysOf } from "../../lib/gateways";

export function AppLayout() {
  const { appId } = useParams();
  const qc = useQueryClient();
  const app = useApp(appId);

  if (app.isPending) return <ListSkeleton rows={6} />;
  if (app.isError) {
    return (
      <Stack>
        <Alert color="red" title="This app can't be opened">
          {errorMessage(app.error)}
        </Alert>
        <Group>
          <Button component={Link} to="/dashboard" variant="default">
            Back to apps
          </Button>
        </Group>
      </Stack>
    );
  }

  const setApp = (updated: App) => {
    qc.setQueryData(keys.app(updated.id), updated);
    qc.invalidateQueries({ queryKey: keys.apps, exact: true });
  };
  const a = app.data;
  return (
    <Stack gap={0}>
      <PageHeader
        leading={<AppAvatar name={a.name} id={a.id} size={44} />}
        title={a.name}
        description={
          <Group gap={6} component="span">
            <span style={{ fontFamily: "var(--mantine-font-family-monospace)" }}>{a.id}</span>
            {gatewaysOf(a).map((g) => (
              <Group key={g.gateway} gap={4} component="span">
                <GatewayBadge gateway={g.gateway} />
                <EnvBadge env={g.env} live={g.live} />
              </Group>
            ))}
          </Group>
        }
      />
      <Outlet context={{ app: a, setApp } satisfies AppContext} />
    </Stack>
  );
}

/** /apps/:appId with no tab: send to the app's landing page; PhonePe apps show the summary here. */
export function AppIndex({ summary }: { summary: ReactNode }) {
  const { app } = useAppContext();
  const landing = appLanding(app);
  if (landing === "") return <>{summary}</>;
  return <Navigate to={`/apps/${app.id}/${landing}`} replace />;
}
