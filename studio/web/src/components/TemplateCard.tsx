import { AspectRatio, Badge, Card, Center, Group, Image, Text } from "@mantine/core";
import { IconPhoto } from "@tabler/icons-react";
import type { ReactNode } from "react";
import type { TemplatePublic } from "../api/types";

export function CoverImage({ src, alt, muted }: { src?: string | null; alt: string; muted?: boolean }) {
  return (
    <AspectRatio ratio={16 / 10}>
      {src ? (
        <Image src={src} alt={alt} fit="cover" style={muted ? { opacity: 0.6, filter: "grayscale(0.4)" } : undefined} />
      ) : (
        <Center bg="var(--app-subtle)" c="dimmed" aria-label="no cover">
          <IconPhoto size={32} stroke={1.3} />
        </Center>
      )}
    </AspectRatio>
  );
}

/** A template as a caller sees it: cover, title, description, its image slots and variables. */
export function TemplateCard({
  template,
  coverUrl,
  details = false,
  footer,
}: {
  template: TemplatePublic;
  /** Override the cover URL (the app catalog's /v1/app/... URLs need an app key). */
  coverUrl?: string | null;
  details?: boolean;
  footer?: ReactNode;
}) {
  const cover = coverUrl === undefined ? template.cover_url : coverUrl;
  return (
    <Card padding="md" data-testid="template-card" data-slug={template.slug} h="100%">
      <Card.Section>
        <CoverImage src={cover} alt={`${template.title} cover`} />
      </Card.Section>
      <Text fw={600} mt="sm" truncate>
        {template.title}
      </Text>
      <Text size="sm" c="dimmed" lineClamp={2} mih={details ? undefined : 40}>
        {template.description || "No description."}
      </Text>
      {details && (
        <Group gap={4} mt="xs">
          {template.inputs.map((s) => (
            <Badge key={s.name} color="indigo" size="sm" leftSection={<IconPhoto size={11} />}>
              {s.name}
              {s.required === false ? " (optional)" : ""}
            </Badge>
          ))}
          {template.variables.map((v) => (
            <Badge key={v.name} color="gray" variant="outline" size="sm">
              {v.name}
              {v.choices?.length ? `: ${v.choices.join(" | ")}` : ""}
            </Badge>
          ))}
          <Badge color="gray" variant="outline" size="sm">
            v{template.version} · {template.model}
          </Badge>
          <Badge color="yellow" variant="light" size="sm" data-testid="credit-cost">
            {template.credit_cost === 0 ? "free" : `${template.credit_cost} credit${template.credit_cost === 1 ? "" : "s"}`}
          </Badge>
        </Group>
      )}
      {footer && <div style={{ marginTop: "auto", paddingTop: 12 }}>{footer}</div>}
    </Card>
  );
}
