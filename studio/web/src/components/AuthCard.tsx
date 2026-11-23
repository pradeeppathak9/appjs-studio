import { Box, Center, Group, Paper, Stack, Text, Title } from "@mantine/core";
import type { ReactNode } from "react";
import { LogoMark, ThemeToggle } from "./ui";

/** Centered card on a soft gradient, with the logo and tagline above it. */
export function AuthCard({ title, subtitle, children }: { title: string; subtitle?: ReactNode; children: ReactNode }) {
  return (
    <Box className="auth-bg" mih="100vh">
      <Center mih="100vh" p="md">
        <Stack w="100%" maw={420} gap="lg">
          <Stack align="center" gap={6}>
            <LogoMark size={44} />
            <Text fw={700} size="xl" style={{ letterSpacing: "-0.01em" }}>
              AppJs Studio
            </Text>
            <Text size="sm" c="dimmed" ta="center">
              Templates that turn photos into images, for your apps.
            </Text>
          </Stack>
          <Paper withBorder shadow="md" p={{ base: "lg", xs: "xl" }} radius="lg">
            <Stack>
              <div>
                <Title order={3}>{title}</Title>
                {subtitle && (
                  <Text size="sm" c="dimmed" mt={4}>
                    {subtitle}
                  </Text>
                )}
              </div>
              {children}
            </Stack>
          </Paper>
          <Group justify="center">
            <ThemeToggle />
          </Group>
        </Stack>
      </Center>
    </Box>
  );
}
