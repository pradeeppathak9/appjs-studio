import { Group, NumberInput, SegmentedControl, Select, Stack, Text, Textarea, TextInput } from "@mantine/core";
import type { UseFormReturnType } from "@mantine/form";
import { PLATFORMS, type AppFormValues } from "../lib/appForm";

/** The app's fields; `slug` only when creating. */
export function AppFields({ form, creating }: { form: UseFormReturnType<AppFormValues>; creating: boolean }) {
  return (
    <Stack>
      <Group grow align="flex-start">
        <TextInput label="Name" required {...form.getInputProps("name")} />
        {creating && (
          <TextInput label="Slug" description="a-z, 0-9 and -, fixed after creation" required {...form.getInputProps("slug")} />
        )}
      </Group>
      <Textarea label="Description" autosize minRows={1} {...form.getInputProps("description")} />
      <Group grow align="flex-start">
        <Select label="Platform" data={PLATFORMS} allowDeselect={false} {...form.getInputProps("platform")} />
        <div>
          <Text size="sm" fw={500} mb={4}>
            Status
          </Text>
          <SegmentedControl
            fullWidth
            data={[
              { value: "active", label: "Active" },
              { value: "disabled", label: "Disabled" },
            ]}
            {...form.getInputProps("status")}
          />
        </div>
      </Group>
      <Group grow align="flex-start">
        <NumberInput
          label="Jobs per day (whole app)"
          placeholder="no limit"
          min={1}
          allowDecimal={false}
          {...form.getInputProps("daily_job_limit")}
        />
        <NumberInput
          label="Jobs per device per hour"
          placeholder="no limit"
          min={1}
          allowDecimal={false}
          {...form.getInputProps("device_hourly_limit")}
        />
      </Group>
      <Text size="xs" c="dimmed">
        Disabled apps get 403 app_disabled. Over a limit, calls get 429 rate_limited. Leave a limit blank for none.
      </Text>
    </Stack>
  );
}
