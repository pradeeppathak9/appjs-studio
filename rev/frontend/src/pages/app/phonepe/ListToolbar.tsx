import { Button, Group, Text } from "@mantine/core";
import { IconDownload } from "@tabler/icons-react";
import type { ReactNode } from "react";
import { num } from "../../../lib/format";

/** Search on the left; result count, export and extra actions on the right. */
export function ListToolbar({
  search,
  total,
  loading,
  onExport,
  exporting,
  children,
}: {
  search: ReactNode;
  total: number | null;
  loading: boolean;
  onExport?: () => void;
  exporting?: boolean;
  children?: ReactNode;
}) {
  return (
    <Group justify="space-between" wrap="wrap" gap="sm" mb="md">
      {search}
      <Group gap="sm" wrap="wrap">
        <Text size="sm" c="dimmed" className="tabular">
          {loading ? "…" : total !== null ? `${num(total)} results` : ""}
        </Text>
        {onExport && (
          <Button variant="default" size="sm" leftSection={<IconDownload size={14} />} loading={exporting} onClick={onExport}>
            Export CSV
          </Button>
        )}
        {children}
      </Group>
    </Group>
  );
}
