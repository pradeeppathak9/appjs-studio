/** The app dashboard's Users tab (global admins only): the app's signed-in users with search and pages,
 * and per user their credits (add or remove), subscription with its Razorpay / PhonePe link, and
 * transaction history. Same data as Admin → Apps → the app → Users. */
import { Alert, Paper, Skeleton, Stack, Text, Title } from "@mantine/core";
import { errorMessage } from "../../api/client";
import { useAdminApp } from "../../api/queries";
import { useCurrentApp } from "../../auth/appContext";
import { UsersTable } from "../admin/AppEndUsers";

export function AppUsersPage() {
  const current = useCurrentApp();
  const app = useAdminApp(current.id);
  if (app.error) return <Alert color="red">{errorMessage(app.error)}</Alert>;
  return (
    <Stack gap="sm" data-testid="app-users-page">
      <div>
        <Title order={3} fz={18}>
          Users
        </Title>
        <Text size="sm" c="dimmed">
          People signed in to {current.name}. Open one to add credits, link a Razorpay or PhonePe subscription, or
          see their transactions.
        </Text>
      </div>
      <Paper withBorder p="lg" shadow="xs">
        {app.data ? <UsersTable app={app.data} /> : <Skeleton height={240} />}
      </Paper>
    </Stack>
  );
}
