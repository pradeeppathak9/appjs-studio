import { Alert, Anchor, Badge, Box, Button, Code, CopyButton, Group, Paper, Stack, Table, Text, Title } from "@mantine/core";
import { IconAlertTriangle, IconCheck, IconCopy, IconInfoCircle } from "@tabler/icons-react";
import type { ReactNode } from "react";

/** Running text in a guide section. */
export function P({ children, muted }: { children: ReactNode; muted?: boolean }) {
  return (
    <Text size="sm" c={muted ? "dimmed" : undefined} lh={1.65}>
      {children}
    </Text>
  );
}

/** Inline code. */
export function C({ children }: { children: ReactNode }) {
  return <Code fz="xs">{children}</Code>;
}

/** A labelled, copyable code sample. */
export function CodeBlock({ children, label = "curl" }: { children: string; label?: string }) {
  return (
    <Box style={{ border: "1px solid var(--mantine-color-default-border)", borderRadius: "var(--mantine-radius-md)", overflow: "hidden" }}>
      <Group justify="space-between" px="sm" py={4} bg="var(--app-subtle)">
        <Text size="xs" fw={600} c="dimmed" tt="uppercase" style={{ letterSpacing: "0.05em" }}>
          {label}
        </Text>
        <CopyButton value={children} timeout={1500}>
          {({ copied, copy }) => (
            <Button
              size="compact-xs"
              variant="subtle"
              color={copied ? "teal" : "gray"}
              leftSection={copied ? <IconCheck size={12} /> : <IconCopy size={12} />}
              onClick={copy}
            >
              {copied ? "Copied" : "Copy"}
            </Button>
          )}
        </CopyButton>
      </Group>
      <Code block fz="xs" style={{ borderRadius: 0, whiteSpace: "pre", overflowX: "auto" }}>
        {children}
      </Code>
    </Box>
  );
}

/** Something that is easy to get wrong. */
export function Note({ children, tone = "info", title }: { children: ReactNode; tone?: "info" | "warn" | "danger"; title?: string }) {
  const color = tone === "danger" ? "red" : tone === "warn" ? "yellow" : "indigo";
  return (
    <Alert
      color={color}
      variant="light"
      title={title}
      icon={tone === "info" ? <IconInfoCircle size={16} /> : <IconAlertTriangle size={16} />}
      styles={{ message: { fontSize: "var(--mantine-font-size-sm)", lineHeight: 1.6 } }}
    >
      {children}
    </Alert>
  );
}

export function Endpoint({ method, path }: { method: "GET" | "POST"; path: string }) {
  return (
    <Group gap="xs" wrap="nowrap" style={{ minWidth: 0 }}>
      <Badge color={method === "POST" ? "green" : "blue"} variant="light" radius="sm" style={{ flexShrink: 0 }}>
        {method}
      </Badge>
      <Text ff="monospace" fz="xs" style={{ wordBreak: "break-all" }}>
        {path}
      </Text>
    </Group>
  );
}

/** A guide section: an anchor target with a heading, optional endpoint, and its content. */
export function GuideSection({
  id,
  title,
  method,
  path,
  children,
}: {
  id: string;
  title: string;
  method?: "GET" | "POST";
  path?: string;
  children: ReactNode;
}) {
  return (
    <Paper id={id} withBorder p={{ base: "md", sm: "lg" }} shadow="xs" style={{ scrollMarginTop: 72 }}>
      <Stack gap="sm">
        <Title order={4}>{title}</Title>
        {method && path && <Endpoint method={method} path={path} />}
        {children}
      </Stack>
    </Paper>
  );
}

/** Jump links to every section. */
export function Toc({ items }: { items: [string, string][] }) {
  return (
    <Paper withBorder p="sm" bg="var(--app-subtle)">
      <Group gap="xs" wrap="wrap">
        {items.map(([id, label]) => (
          <Anchor key={id} href={`#${id}`} size="sm" px={6}>
            {label}
          </Anchor>
        ))}
      </Group>
    </Paper>
  );
}

export type Param = { name: string; type: string; required: boolean; def?: string; notes: ReactNode };

/** Request parameters. Required is its own column: it is the first thing anyone writing a request needs. */
export function Params({ rows }: { rows: Param[] }) {
  return (
    <Paper withBorder style={{ overflow: "hidden" }}>
      <Table.ScrollContainer minWidth={720} type="native">
        <Table fz="sm" verticalSpacing="xs" striped="even">
          <Table.Thead>
            <Table.Tr>
              {["Parameter", "Type", "Required", "Default", "Notes"].map((h) => (
                <Table.Th key={h}>
                  <Text size="xs" fw={600} c="dimmed" tt="uppercase">
                    {h}
                  </Text>
                </Table.Th>
              ))}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((r) => (
              <Table.Tr key={r.name}>
                <Table.Td>
                  <C>{r.name}</C>
                </Table.Td>
                <Table.Td c="dimmed" style={{ whiteSpace: "nowrap" }}>
                  {r.type}
                </Table.Td>
                <Table.Td>
                  {r.required ? (
                    <Badge color="red" variant="light" size="sm">
                      Required
                    </Badge>
                  ) : (
                    <Badge color="gray" variant="light" size="sm">
                      Optional
                    </Badge>
                  )}
                </Table.Td>
                <Table.Td c="dimmed">{r.def || "—"}</Table.Td>
                <Table.Td>{r.notes}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Paper>
  );
}

/** A two- or three-column reference table (fields, states, status codes). */
export function RefTable({ head, rows }: { head: string[]; rows: ReactNode[][] }) {
  return (
    <Paper withBorder style={{ overflow: "hidden" }}>
      <Table.ScrollContainer minWidth={520} type="native">
        <Table fz="sm" verticalSpacing="xs" striped="even">
          <Table.Thead>
            <Table.Tr>
              {head.map((h) => (
                <Table.Th key={h}>
                  <Text size="xs" fw={600} c="dimmed" tt="uppercase">
                    {h}
                  </Text>
                </Table.Th>
              ))}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((r, i) => (
              <Table.Tr key={i}>
                {r.map((cell, j) => (
                  <Table.Td key={j}>{j === 0 && typeof cell === "string" ? <C>{cell}</C> : cell || "—"}</Table.Td>
                ))}
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Paper>
  );
}
