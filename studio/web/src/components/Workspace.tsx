import { Box, Grid, Paper, Stack, Text } from "@mantine/core";
import { IconPhotoScan } from "@tabler/icons-react";
import type { ReactNode } from "react";
import { useSelectedJob } from "../lib/useSelectedJob";
import { JobDetail } from "./JobDetail";
import { JobList } from "./JobList";
import { EmptyState } from "./ui";

/** Form on the left, the selected job (result) on the right, recent jobs below. */
export function Workspace({ children }: { children: ReactNode }) {
  const [jobId, selectJob] = useSelectedJob();
  return (
    <Stack gap="xl">
      <Grid gap="lg" align="flex-start">
        <Grid.Col span={{ base: 12, md: 6, lg: 7 }}>{children}</Grid.Col>
        <Grid.Col span={{ base: 12, md: 6, lg: 5 }}>
          <Box pos="sticky" top={72}>
            <Paper withBorder p="lg" shadow="xs">
              <Text fw={600} mb="md">
                Result
              </Text>
              {jobId ? (
                <JobDetail id={jobId} showOpenLink />
              ) : (
                <EmptyState
                  icon={<IconPhotoScan size={28} stroke={1.5} />}
                  title="Nothing run yet"
                  description="Run the form and the result appears here, with the input and output side by side. You can also pick a recent job below."
                />
              )}
            </Paper>
          </Box>
        </Grid.Col>
      </Grid>
      <JobList selectedId={jobId} onSelect={selectJob} title="Recent jobs" />
    </Stack>
  );
}
