import { Box } from "@mantine/core";
import type { ReactNode } from "react";

/**
 * Hosts a page that hasn't been ported from the old console yet. Those pages hard-code light colors
 * in inline styles, so they sit on a light panel in both themes until they move to Mantine.
 */
export function Legacy({ children }: { children: ReactNode }) {
  return (
    <Box
      className="legacy-page"
      p={{ base: "md", sm: "lg" }}
      style={{
        background: "#f8fafc",
        color: "#1e293b",
        colorScheme: "light",
        borderRadius: "var(--mantine-radius-md)",
        border: "1px solid var(--mantine-color-default-border)",
        fontFamily: "var(--mantine-font-family)",
      }}
    >
      {children}
    </Box>
  );
}
