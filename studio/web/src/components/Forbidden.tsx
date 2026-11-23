import { IconLock, IconMapOff } from "@tabler/icons-react";
import { EmptyState } from "./ui";

export function Forbidden({ detail }: { detail?: string }) {
  return (
    <EmptyState
      testId="forbidden"
      icon={<IconLock size={28} stroke={1.5} />}
      title="Your role can't do this"
      description={detail ?? "Ask an admin if you need access."}
    />
  );
}

export function NotFound() {
  return (
    <EmptyState icon={<IconMapOff size={28} stroke={1.5} />} title="Not found" description="There is nothing at this address." />
  );
}
