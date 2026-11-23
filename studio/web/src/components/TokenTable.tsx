import { Button, Table, Text } from "@mantine/core";
import { IconKey } from "@tabler/icons-react";
import type { TokenOut } from "../api/types";
import { EmptyState } from "./ui";
import { formatDate } from "../lib/format";

export function TokenTable({
  tokens,
  onRevoke,
  revoking,
  empty = "No API tokens yet",
  emptyHint,
}: {
  tokens: TokenOut[];
  onRevoke: (t: TokenOut) => void;
  revoking?: string;
  empty?: string;
  emptyHint?: string;
}) {
  if (tokens.length === 0)
    return <EmptyState compact icon={<IconKey size={20} stroke={1.5} />} title={empty} description={emptyHint} />;
  return (
    <Table.ScrollContainer minWidth={520}>
      <Table fz="sm" data-testid="token-table">
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Name</Table.Th>
            <Table.Th>Prefix</Table.Th>
            <Table.Th>Created</Table.Th>
            <Table.Th>Last used</Table.Th>
            <Table.Th />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {tokens.map((t) => (
            <Table.Tr key={t.id}>
              <Table.Td>{t.name}</Table.Td>
              <Table.Td ff="monospace">{t.prefix}…</Table.Td>
              <Table.Td>{formatDate(t.created_at)}</Table.Td>
              <Table.Td>{formatDate(t.last_used_at)}</Table.Td>
              <Table.Td>
                {t.revoked_at ? (
                  <Text size="xs" c="dimmed">
                    revoked
                  </Text>
                ) : (
                  <Button
                    size="compact-xs"
                    color="red"
                    variant="subtle"
                    loading={revoking === t.id}
                    onClick={() => onRevoke(t)}
                  >
                    Revoke
                  </Button>
                )}
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}
