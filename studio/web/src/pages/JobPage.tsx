import { Button, Paper, Stack } from "@mantine/core";
import { IconArrowLeft } from "@tabler/icons-react";
import { useNavigate, useParams } from "react-router";
import { JobDetail } from "../components/JobDetail";

export function JobPage() {
  const { jobId } = useParams();
  const navigate = useNavigate();
  return (
    <Stack maw={1100}>
      <Button
        variant="subtle"
        size="compact-sm"
        leftSection={<IconArrowLeft size={14} />}
        onClick={() => (window.history.length > 1 ? navigate(-1) : navigate("/"))}
        style={{ alignSelf: "flex-start" }}
      >
        Back
      </Button>
      <Paper withBorder p="lg" shadow="xs">
        {jobId && <JobDetail id={jobId} />}
      </Paper>
    </Stack>
  );
}
