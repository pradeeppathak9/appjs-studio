import { ActionIcon, Badge, Code, CopyButton, Group, Loader, Stack, Text, Tooltip } from "@mantine/core";
import { IconCheck, IconCopy } from "@tabler/icons-react";
import type { JobStatus, TemplateStatus } from "../api/types";
import { StatusDot } from "./ui";

const JOB_COLOR: Record<JobStatus, string> = {
  queued: "gray",
  running: "blue",
  succeeded: "green",
  failed: "red",
};

export function JobStatusBadge({ status }: { status: JobStatus }) {
  return (
    <Badge
      color={JOB_COLOR[status]}
      variant="light"
      tt="capitalize"
      leftSection={status === "running" ? <Loader size={8} color="blue" type="oval" /> : <StatusDot color={JOB_COLOR[status]} />}
      data-testid="job-status"
    >
      {status}
    </Badge>
  );
}

const TEMPLATE_COLOR: Record<TemplateStatus, string> = { draft: "gray", active: "green" };

export function TemplateStatusBadge({ status }: { status: TemplateStatus }) {
  return (
    <Badge
      color={TEMPLATE_COLOR[status]}
      variant={status === "active" ? "light" : "outline"}
      tt="capitalize"
      leftSection={<StatusDot color={TEMPLATE_COLOR[status]} />}
      data-testid="template-status"
    >
      {status}
    </Badge>
  );
}

/** A value with a copy button: tokens, temporary passwords, curl commands. */
export function CopyBlock({ value, label, testId }: { value: string; label?: string; testId?: string }) {
  return (
    <Stack gap={4}>
      {label && (
        <Text size="sm" fw={500}>
          {label}
        </Text>
      )}
      <Group gap="xs" wrap="nowrap" align="flex-start">
        <Code
          block
          style={{ flex: 1, whiteSpace: "pre-wrap", wordBreak: "break-all", fontSize: 12.5, lineHeight: 1.55 }}
          data-testid={testId}
        >
          {value}
        </Code>
        <CopyButton value={value}>
          {({ copied, copy }) => (
            <Tooltip label={copied ? "Copied" : "Copy"}>
              <ActionIcon variant="default" size="lg" onClick={copy} aria-label={label ? `Copy ${label}` : "Copy"}>
                {copied ? <IconCheck size={16} color="var(--mantine-color-teal-6)" /> : <IconCopy size={16} />}
              </ActionIcon>
            </Tooltip>
          )}
        </CopyButton>
      </Group>
    </Stack>
  );
}

/** Render an image or a video by mime type (the fake provider returns "video" as image/gif). */
export function MediaView({ url, mime, alt }: { url: string; mime: string; alt?: string }) {
  if (mime.startsWith("video/")) {
    return <video src={url} controls style={{ maxWidth: "100%", borderRadius: 8, display: "block" }} />;
  }
  return <img src={url} alt={alt ?? ""} style={{ maxWidth: "100%", borderRadius: 8, display: "block" }} />;
}
