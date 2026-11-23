import {
  Alert,
  Autocomplete,
  Button,
  Card,
  Group,
  NumberInput,
  SegmentedControl,
  Select,
  Stack,
  Text,
  Textarea,
  TextInput,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { IconSparkles } from "@tabler/icons-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage, unwrap } from "../../api/client";
import { keys, useProviders } from "../../api/queries";
import type { GenerationCreate } from "../../api/types";
import { useCurrentApp } from "../../auth/appContext";
import { Workspace } from "../../components/Workspace";
import { capabilitiesFor } from "../../lib/capabilities";
import { fieldErrors } from "../../lib/formErrors";
import { useSelectedJob } from "../../lib/useSelectedJob";

const DEFAULT = "__default__";
const FAKE_PROMPTS = ["FAIL_TRANSIENT", "FAIL_TRANSIENT:1", "FAIL_POLICY", "SLEEP:30"];

type Values = {
  provider: string;
  media_type: "image" | "video";
  model: string;
  aspect_ratio: string;
  n: number;
  duration_seconds: string | null;
  negative_prompt: string;
  seed: number | string;
  prompt: string;
  webhook_url: string;
};

/** Free-prompt test generation inside the app (editors): POST /v1/apps/{id}/generations. */
export function FreePromptPage() {
  const app = useCurrentApp();
  const providers = useProviders(app.id);
  const qc = useQueryClient();
  const [, selectJob] = useSelectedJob();
  const form = useForm<Values>({
    initialValues: {
      provider: DEFAULT,
      media_type: "image",
      model: "",
      aspect_ratio: "1:1",
      n: 1,
      duration_seconds: null,
      negative_prompt: "",
      seed: "",
      prompt: "",
      webhook_url: "",
    },
  });
  const list = providers.data ?? [];
  const v = form.values;
  const caps = capabilitiesFor(list, v.provider, v.media_type);
  const isVideo = v.media_type === "video";

  const submit = useMutation({
    meta: { quiet: true },
    mutationFn: (body: GenerationCreate) =>
      unwrap(api.POST("/v1/apps/{app_id}/generations", { params: { path: { app_id: app.id } }, body })),
    onSuccess: (job) => {
      qc.invalidateQueries({ queryKey: keys.jobs });
      qc.setQueryData(keys.job(job.id), job);
      selectJob(job.id);
    },
    onError: (e) => form.setErrors(fieldErrors(e, (p) => p in form.values).errors),
  });
  const rest = fieldErrors(submit.error, (p) => p in form.values).rest;

  const onSubmit = form.onSubmit((x) => {
    submit.mutate({
      prompt: x.prompt,
      media_type: x.media_type,
      provider: x.provider === DEFAULT ? null : x.provider,
      model: x.model.trim() || null,
      aspect_ratio: x.aspect_ratio,
      n: isVideo ? 1 : x.n,
      duration_seconds: isVideo && x.duration_seconds ? Number(x.duration_seconds) : null,
      negative_prompt: caps.negative && x.negative_prompt ? x.negative_prompt : null,
      seed: caps.seed && x.seed !== "" ? Number(x.seed) : null,
      webhook_url: x.webhook_url || null,
    });
  });

  const setChoice = (name: string, media: "image" | "video") => {
    const next = capabilitiesFor(list, name, media);
    const ratio = next.ratios.includes(v.aspect_ratio) ? v.aspect_ratio : (next.ratios[0] ?? "1:1");
    form.setValues({ provider: name, media_type: media, model: "", aspect_ratio: ratio, duration_seconds: null });
  };
  const setProvider = (name: string) => {
    const next = capabilitiesFor(list, name, v.media_type);
    setChoice(name, next.media[v.media_type] ? v.media_type : next.media.image ? "image" : "video");
  };

  return (
    <Workspace>
      <Card padding="lg">
        <form onSubmit={onSubmit}>
          <Stack>
            <Title order={3} fz={18}>
              Free prompt
            </Title>
            <Text size="sm" c="dimmed" mt={-8}>
              Try a prompt without a template. Jobs land in {app.name}'s job list. Fields follow the provider's
              capabilities.
            </Text>
            {providers.error && <Alert color="red">{errorMessage(providers.error)}</Alert>}
            <Group grow align="flex-start">
              <Select
                label="Provider"
                data={[{ value: DEFAULT, label: "Server default" }, ...list.map((p) => ({ value: p.name, label: p.name }))]}
                value={v.provider}
                onChange={(x) => x && setProvider(x)}
                allowDeselect={false}
              />
              <div>
                <Text size="sm" fw={500} mb={4}>
                  Media type
                </Text>
                <SegmentedControl
                  fullWidth
                  data={[
                    { value: "image", label: "Image", disabled: !caps.media.image },
                    { value: "video", label: "Video", disabled: !caps.media.video },
                  ]}
                  value={v.media_type}
                  onChange={(m) => setChoice(v.provider, m as "image" | "video")}
                />
              </div>
            </Group>
            <Group grow align="flex-start">
              <Autocomplete
                label="Model"
                placeholder="provider default"
                description="Pick a known model or type another"
                data={caps.models}
                {...form.getInputProps("model")}
              />
              <Select
                label="Aspect ratio"
                data={caps.ratios.length ? caps.ratios : ["1:1"]}
                allowDeselect={false}
                {...form.getInputProps("aspect_ratio")}
              />
            </Group>
            <Group grow align="flex-start">
              {!isVideo && <NumberInput label="Images (n)" min={1} max={caps.maxImages} {...form.getInputProps("n")} />}
              {isVideo &&
                (caps.durations.length > 0 ? (
                  <Select
                    label="Duration (s)"
                    placeholder="default"
                    data={caps.durations.map(String)}
                    clearable
                    {...form.getInputProps("duration_seconds")}
                  />
                ) : (
                  // No fixed list from the provider: any whole number of seconds.
                  <NumberInput
                    label="Duration (s)"
                    placeholder="default"
                    min={1}
                    max={60}
                    allowDecimal={false}
                    value={v.duration_seconds ?? ""}
                    onChange={(x) => form.setFieldValue("duration_seconds", x === "" ? null : String(x))}
                    error={form.errors.duration_seconds}
                  />
                ))}
              {caps.seed && <NumberInput label="Seed" allowDecimal={false} {...form.getInputProps("seed")} />}
            </Group>
            <Textarea label="Prompt" required autosize minRows={3} maxLength={4000} {...form.getInputProps("prompt")} />
            {v.provider === "fake" && (
              <Group gap="xs">
                <Text size="xs" c="dimmed">
                  Fake provider:
                </Text>
                {FAKE_PROMPTS.map((p) => (
                  <Button
                    key={p}
                    size="compact-xs"
                    variant="light"
                    onClick={() => form.setFieldValue("prompt", `${v.prompt} ${p}`.trim())}
                  >
                    {p}
                  </Button>
                ))}
              </Group>
            )}
            {caps.negative && <TextInput label="Negative prompt" {...form.getInputProps("negative_prompt")} />}
            <TextInput label="Webhook URL" placeholder="https://… (optional)" {...form.getInputProps("webhook_url")} />
            {submit.error && (rest.length > 0 || !Object.keys(form.errors).length) && (
              <Alert color="red">{rest.length ? rest.join("; ") : errorMessage(submit.error)}</Alert>
            )}
            <Button type="submit" loading={submit.isPending} leftSection={<IconSparkles size={16} />}>
              Generate
            </Button>
          </Stack>
        </form>
      </Card>
    </Workspace>
  );
}
