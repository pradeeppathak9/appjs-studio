import { Badge, Group } from "@mantine/core";
import { IconLock } from "@tabler/icons-react";
import type { ReactNode } from "react";
import { Outlet, useParams } from "react-router";
import { ApiError, errorMessage } from "../../api/client";
import { useMyApp } from "../../api/queries";
import { AppContext, useCurrentApp } from "../../auth/appContext";
import { canEdit } from "../../auth/roles";
import { Forbidden } from "../../components/Forbidden";
import { AppAvatar, EmptyState, ListSkeleton, PageHeader, PlatformIcon, RoleBadge } from "../../components/ui";

/** `/apps/:appId/...`: loads the app (404 for non-members) and shows its tabs for the user's role. */
export function AppLayout() {
  const { appId } = useParams();
  const app = useMyApp(appId!);

  if (app.error) {
    const missing = app.error instanceof ApiError && app.error.status === 404;
    return (
      <EmptyState
        icon={<IconLock size={28} stroke={1.5} />}
        title={missing ? "App not found" : "Can't load the app"}
        description={missing ? "This app doesn't exist, or you are not a member of it." : errorMessage(app.error)}
      />
    );
  }
  if (!app.data) return <ListSkeleton rows={3} height={64} />;
  const a = app.data;

  return (
    <AppContext.Provider value={a}>
      <PageHeader
        leading={<AppAvatar name={a.name} slug={a.slug} size={44} />}
        title={
          <Group gap="xs" component="span">
            {a.name}
            <RoleBadge role={a.role} testId="my-app-role" />
            {a.status === "disabled" && (
              <Badge color="gray" variant="outline">
                disabled
              </Badge>
            )}
          </Group>
        }
        description={
          <Group gap={6} component="span">
            <PlatformIcon platform={a.platform} size={14} />
            <span>
              {a.slug} · {a.active_template_count ?? 0} of {a.template_count ?? 0} templates active
            </span>
          </Group>
        }
      />
      <Outlet />
    </AppContext.Provider>
  );
}

/** Pages for editors (and admins) of the current app. */
export function RequireEditor({ children }: { children: ReactNode }) {
  const app = useCurrentApp();
  return canEdit(app.role) ? (
    children
  ) : (
    <Forbidden detail={`You are a ${app.role} in ${app.name}; this needs the editor role.`} />
  );
}
