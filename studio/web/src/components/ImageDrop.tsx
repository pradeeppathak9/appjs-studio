import { CloseButton, Group, Image, Input, Stack, Text } from "@mantine/core";
import { Dropzone, type FileRejection } from "@mantine/dropzone";
import { IconCloudUpload } from "@tabler/icons-react";
import { formatBytes } from "../lib/format";
import { IMAGE_TYPES, MAX_IMAGE_BYTES, pick, type Picked } from "../lib/images";

function rejectionMessage(rejections: FileRejection[]): string {
  const code = rejections[0]?.errors[0]?.code;
  if (code === "file-too-large") return "The file is larger than 10 MB";
  if (code === "file-invalid-type") return "Use a PNG, JPEG or WebP image";
  return rejections[0]?.errors[0]?.message ?? "This file can't be used";
}

/** One image slot: a drop zone, or the chosen file's preview and size. Checks here are only hints. */
export function ImageDrop({
  name,
  label,
  required,
  value,
  onChange,
  error,
  onError,
}: {
  name: string;
  label: string;
  required?: boolean;
  value: Picked | null;
  onChange: (v: Picked | null) => void;
  error?: string;
  onError: (msg: string) => void;
}) {
  const set = (v: Picked | null) => {
    if (value) URL.revokeObjectURL(value.url);
    onChange(v);
  };
  return (
    <Input.Wrapper label={label} required={required} error={error} description={`form field "${name}"`}>
      {value ? (
        <Group align="flex-start" mt={4} data-testid={`preview-${name}`}>
          <Image src={value.url} alt={`${name} preview`} h={120} w="auto" fit="contain" radius="sm" />
          <Stack gap={2}>
            <Text size="sm">{value.file.name}</Text>
            <Text size="xs" c="dimmed">
              {value.file.type || "unknown type"} · {formatBytes(value.file.size)}
            </Text>
          </Stack>
          <CloseButton aria-label={`Remove ${name}`} onClick={() => set(null)} />
        </Group>
      ) : (
        <Dropzone
          mt={4}
          onDrop={(files) => files[0] && set(pick(files[0]))}
          onReject={(r) => onError(rejectionMessage(r))}
          accept={IMAGE_TYPES}
          maxSize={MAX_IMAGE_BYTES}
          multiple={false}
          data-testid={`drop-${name}`}
          name={name}
        >
          <Stack align="center" gap={4} py="md" style={{ pointerEvents: "none" }}>
            <IconCloudUpload size={28} stroke={1.4} color="var(--mantine-color-dimmed)" />
            <Text size="sm" fw={500}>
              Drop an image or click to choose
            </Text>
            <Text size="xs" c="dimmed">
              PNG, JPEG or WebP, up to 10 MB
            </Text>
          </Stack>
        </Dropzone>
      )}
    </Input.Wrapper>
  );
}
