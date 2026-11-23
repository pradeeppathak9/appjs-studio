import {
  Alert,
  Autocomplete,
  Badge,
  Box,
  Button,
  Card,
  Checkbox,
  CloseButton,
  Grid,
  Group,
  Image,
  NumberInput,
  Paper,
  SegmentedControl,
  Select,
  Skeleton,
  Stack,
  Table,
  Tabs,
  TagsInput,
  Text,
  Textarea,
  TextInput,
  Timeline,
  Title,
  Tooltip,
  UnstyledButton,
} from "@mantine/core";
import {
  IconAlertTriangle,
  IconArrowLeft,
  IconCpu,
  IconDeviceFloppy,
  IconEye,
  IconEyeOff,
  IconFileDescription,
  IconFlask,
  IconHistory,
  IconPhoto,
  IconRefresh,
  IconRestore,
  IconVariable,
  IconWand,
} from "@tabler/icons-react";
import { Dropzone } from "@mantine/dropzone";
import { useForm, type UseFormReturnType } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";
import { api, ApiError, errorMessage, postForm, unwrap } from "../../api/client";
import { keys, useProviders, useTemplate } from "../../api/queries";
import type { TemplateFull, TemplatePublic, TemplateStatus, TemplateVersion, UploadOut } from "../../api/types";
import { TemplateStatusBadge } from "../../components/common";
import { IMAGE_TYPES, MAX_IMAGE_BYTES } from "../../lib/images";
import { JobDetail } from "../../components/JobDetail";
import { RunTemplateForm } from "../../components/RunTemplateForm";
import { diffVersions } from "../../lib/diff";
import { age } from "../../lib/format";
import { TemplateCard } from "../../components/TemplateCard";
import { Section, StatusDot } from "../../components/ui";
import { fieldErrors } from "../../lib/formErrors";
import {
  EMPTY_TEMPLATE,
  fromVersion,
  isEditorField,
  newVariable,
  resolveField,
  toBody,
  type EditorValues,
} from "../../lib/templateForm";
import { findVariables, variableProblems } from "../../lib/vars";
import { useCurrentApp } from "../../auth/appContext";

type Form = UseFormReturnType<EditorValues>;

// ---- prompt + variables ------------------------------------------------------------------------

function PromptVariables({ form }: { form: Form }) {
  const v = form.values;
  const used = findVariables(v.prompt, v.negative_prompt);
  const declared = v.variables.map((x) => x.name);
  const { undeclared, unused } = variableProblems(used, declared);
  if (!used.length && !unused.length) {
    return (
      <Text size="xs" c="dimmed">
        Use {"{{name}}"} in the prompt for values a caller can fill in.
      </Text>
    );
  }
  return (
    <Stack gap={4} data-testid="prompt-variables">
      <Group gap={4}>
        <Text size="xs" c="dimmed">
          Variables in the prompt:
        </Text>
        {used.map((n) => (
          <Badge key={n} size="sm" variant="light" color={declared.includes(n) ? "green" : "orange"}>
            {n}
          </Badge>
        ))}
      </Group>
      {undeclared.length > 0 && (
        <Group gap={4}>
          <Text size="xs" c="orange">
            Not declared:
          </Text>
          {undeclared.map((n) => (
            <Button
              key={n}
              size="compact-xs"
              variant="light"
              color="orange"
              onClick={() => form.insertListItem("variables", newVariable(n))}
            >
              Add {`{{${n}}}`}
            </Button>
          ))}
        </Group>
      )}
      {unused.length > 0 && (
        <Text size="xs" c="orange">
          Declared but not used in the prompt: {unused.join(", ")}
        </Text>
      )}
    </Stack>
  );
}

function SlotsEditor({ form }: { form: Form }) {
  return (
    <Stack gap="xs">
      <Group justify="space-between">
        <Text fw={500} size="sm">
          Input image slots
        </Text>
        <Button
          size="compact-xs"
          variant="light"
          onClick={() => form.insertListItem("inputs", { name: "", label: "", required: true })}
        >
          Add slot
        </Button>
      </Group>
      <Text size="xs" c="dimmed">
        Each slot is a multipart file field named after it, e.g. <code>-F photo=@me.jpg</code>.
      </Text>
      {form.values.inputs.map((_, i) => (
        <Group key={i} align="flex-start" gap="xs" wrap="nowrap">
          <TextInput placeholder="name" aria-label={`Slot ${i + 1} name`} w={140} {...form.getInputProps(`inputs.${i}.name`)} />
          <TextInput placeholder="label" aria-label={`Slot ${i + 1} label`} style={{ flex: 1 }} {...form.getInputProps(`inputs.${i}.label`)} />
          <Checkbox mt={8} label="required" {...form.getInputProps(`inputs.${i}.required`, { type: "checkbox" })} />
          <CloseButton mt={4} aria-label={`Remove slot ${i + 1}`} onClick={() => form.removeListItem("inputs", i)} />
        </Group>
      ))}
      {typeof form.errors.inputs === "string" && (
        <Text size="xs" c="red">
          {form.errors.inputs}
        </Text>
      )}
    </Stack>
  );
}

function VariablesEditor({ form }: { form: Form }) {
  return (
    <Stack gap="xs">
      <Group justify="space-between">
        <Text fw={500} size="sm">
          Variables
        </Text>
        <Button size="compact-xs" variant="light" onClick={() => form.insertListItem("variables", newVariable(""))}>
          Add variable
        </Button>
      </Group>
      {form.values.variables.map((_, i) => (
        <Card key={i} withBorder padding="xs">
          <Group align="flex-start" gap="xs" wrap="wrap">
            <TextInput label="Name" w={130} {...form.getInputProps(`variables.${i}.name`)} />
            <TextInput label="Label" w={150} {...form.getInputProps(`variables.${i}.label`)} />
            <TextInput label="Default" w={170} {...form.getInputProps(`variables.${i}.default`)} />
            <NumberInput label="Max length" w={100} min={1} max={1000} {...form.getInputProps(`variables.${i}.max_length`)} />
            <TagsInput
              label="Choices"
              placeholder="Enter to add"
              style={{ flex: 1, minWidth: 180 }}
              {...form.getInputProps(`variables.${i}.choices`)}
            />
            <CloseButton mt={26} aria-label={`Remove variable ${i + 1}`} onClick={() => form.removeListItem("variables", i)} />
          </Group>
        </Card>
      ))}
      {typeof form.errors.variables === "string" && (
        <Text size="xs" c="red">
          {form.errors.variables}
        </Text>
      )}
    </Stack>
  );
}

function CoverPicker({ form }: { form: Form }) {
  const app = useCurrentApp();
  const upload = useMutation({
    mutationFn: (f: File) => {
      const fd = new FormData();
      fd.append("file", f, f.name);
      return postForm<UploadOut>(`/v1/apps/${app.id}/uploads`, fd);
    },
    onSuccess: (u) => form.setFieldValue("cover_upload", u.id),
  });
  const cover = form.values.cover_upload;
  return (
    <Stack gap="xs" data-testid="cover-picker">
      <Text fw={500} size="sm">
        Cover image
      </Text>
      <Text size="xs" c="dimmed">
        Shown on template cards in the console and in apps. Not sent to the provider.
      </Text>
      {cover ? (
        <Group align="flex-start">
          <Image src={`/v1/apps/${app.id}/uploads/${cover}`} alt="cover" h={120} w="auto" fit="contain" radius="sm" data-testid="cover-preview" />
          <Button size="compact-xs" variant="light" color="red" onClick={() => form.setFieldValue("cover_upload", null)}>
            Remove cover
          </Button>
        </Group>
      ) : (
        <Dropzone
          onDrop={(files) => files[0] && upload.mutate(files[0])}
          onReject={() => notifications.show({ color: "red", message: "Use PNG, JPEG or WebP up to 10 MB" })}
          accept={IMAGE_TYPES}
          maxSize={MAX_IMAGE_BYTES}
          multiple={false}
          loading={upload.isPending}
          p="xs"
        >
          <Text size="xs" c="dimmed" ta="center">
            Drop a cover image or click to choose
          </Text>
        </Dropzone>
      )}
      {typeof form.errors.cover_upload === "string" && (
        <Text size="xs" c="red">
          {form.errors.cover_upload}
        </Text>
      )}
    </Stack>
  );
}

function ReferenceImages({ form }: { form: Form }) {
  const app = useCurrentApp();
  const upload = useMutation({
    mutationFn: async (files: File[]) => {
      const out: UploadOut[] = [];
      for (const f of files) {
        const fd = new FormData();
        fd.append("file", f, f.name);
        out.push(await postForm<UploadOut>(`/v1/apps/${app.id}/uploads`, fd));
      }
      return out;
    },
    onSuccess: (ups) => ups.forEach((u) => form.insertListItem("reference_uploads", u.id)),
  });
  return (
    <Stack gap="xs">
      <Text fw={500} size="sm">
        Reference images
      </Text>
      <Text size="xs" c="dimmed">
        Sent to the provider with every call, after the caller's images. Callers never see them.
      </Text>
      <Group gap="xs">
        {form.values.reference_uploads.map((id, i) => (
          <div key={id} style={{ position: "relative" }}>
            <Image src={`/v1/apps/${app.id}/uploads/${id}`} alt="reference" h={80} w={80} fit="cover" radius="sm" />
            <CloseButton
              size="sm"
              style={{ position: "absolute", top: 2, right: 2 }}
              variant="filled"
              aria-label="Remove reference"
              onClick={() => form.removeListItem("reference_uploads", i)}
            />
          </div>
        ))}
        <Dropzone
          onDrop={(files) => upload.mutate(files)}
          onReject={() => notifications.show({ color: "red", message: "Use PNG, JPEG or WebP up to 10 MB" })}
          accept={IMAGE_TYPES}
          maxSize={MAX_IMAGE_BYTES}
          loading={upload.isPending}
          w={80}
          h={80}
          p={4}
        >
          <Text size="xs" c="dimmed" ta="center" mt={18}>
            + add
          </Text>
        </Dropzone>
      </Group>
      {typeof form.errors.reference_uploads === "string" && (
        <Text size="xs" c="red">
          {form.errors.reference_uploads}
        </Text>
      )}
    </Stack>
  );
}

// ---- the editor form ---------------------------------------------------------------------------

function EditorForm({
  template,
  base,
  onSaved,
  onReload,
  aside,
}: {
  template: TemplateFull | null;
  base: TemplateVersion | null;
  onSaved: (t: TemplateFull, warnings: string[]) => void;
  onReload?: () => void;
  aside?: (dirty: boolean) => ReactNode;
}) {
  const app = useCurrentApp();
  const providers = useProviders(app.id);
  const location = useLocation();
  const [warnings, setWarnings] = useState<string[]>((location.state as { warnings?: string[] } | null)?.warnings ?? []);
  const [conflict, setConflict] = useState<ApiError | null>(null);
  const [problems, setProblems] = useState<string[]>([]);
  const qc = useQueryClient();
  const form = useForm<EditorValues>({
    initialValues: base && template ? fromVersion(base, template.slug, template.credit_cost) : EMPTY_TEMPLATE,
    validate: {
      slug: (s) => (/^[a-z0-9-]{3,64}$/.test(s) ? null : "3-64 characters: a-z, 0-9 and -"),
      title: (s) => (s.trim() ? null : "Required"),
      provider: (s) => (s ? null : "Pick a provider"),
      model: (s) => (s.trim() ? null : "Required"),
      prompt: (s) => (s.trim() ? null : "Required"),
    },
  });
  const v = form.values;
  const list = providers.data ?? [];
  const usesImages = v.inputs.length + v.reference_uploads.length > 0;
  const provider = list.find((p) => p.name === v.provider);
  const providerOptions = list.filter((p) => !usesImages || p.image_input).map((p) => p.name);
  if (v.provider && !providerOptions.includes(v.provider)) providerOptions.push(v.provider);
  const models = provider
    ? usesImages
      ? provider.image_input_models
      : v.media_type === "image"
        ? provider.known_image_models
        : provider.known_video_models
    : [];
  const ratios = provider ? (v.media_type === "image" ? provider.image_aspect_ratios : provider.video_aspect_ratios) : [];

  const save = useMutation({
    meta: { quiet: true },
    mutationFn: async (values: EditorValues) => {
      const body = toBody(values);
      if (!template) {
        return unwrap(
          api.POST("/v1/apps/{app_id}/manage/templates", {
            params: { path: { app_id: app.id } },
            body: { ...body, slug: values.slug },
          }),
        );
      }
      return unwrap(
        api.PUT("/v1/apps/{app_id}/manage/templates/{template_id}", {
          params: { path: { app_id: app.id, template_id: template.id } },
          body: { ...body, base_version: base!.version },
        }),
      );
    },
    onMutate: () => {
      setConflict(null);
      setProblems([]);
    },
    onSuccess: (saved) => {
      setWarnings(saved.warnings);
      qc.invalidateQueries({ queryKey: keys.app(app.id) });
      notifications.show({ color: "green", message: `Saved version ${saved.template.current_version}` });
      onSaved(saved.template, saved.warnings);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.code === "conflict" && e.status === 409 && template) {
        setConflict(e);
        return;
      }
      const { errors, rest } = fieldErrors(e, isEditorField, (f) => resolveField(f, form.values));
      form.setErrors(errors);
      setProblems(rest.length || Object.keys(errors).length ? rest : [errorMessage(e)]);
    },
  });

  const dirty = form.isDirty();
  const preview: TemplatePublic = {
    id: template?.id ?? "new",
    slug: v.slug || "new-template",
    title: v.title || "Untitled template",
    description: v.description,
    media_type: v.media_type,
    version: base?.version ?? 1,
    inputs: v.inputs.filter((x) => x.name),
    variables: v.variables
      .filter((x) => x.name)
      .map((x) => ({ ...x, choices: x.choices.length ? x.choices : null })),
    model: v.model || "—",
    allowed_models: v.allowed_models,
    has_reference_images: v.reference_uploads.length > 0,
    cover_url: v.cover_upload ? `/v1/apps/${app.id}/uploads/${v.cover_upload}` : null,
    credit_cost: Number(v.credit_cost) || 0,
  };

  return (
    <Grid gap="lg" align="flex-start">
      <Grid.Col span={{ base: 12, lg: 7 }}>
        <form id="template-form" onSubmit={form.onSubmit((x) => save.mutate(x))}>
          <Stack gap="lg">
            <Paper
              withBorder
              shadow="sm"
              p="sm"
              pos="sticky"
              top={64}
              style={{ zIndex: 5 }}
              data-testid="save-bar"
            >
              <Group gap="sm" wrap="wrap" align="center">
                <Group gap={8} wrap="nowrap" miw={150}>
                  <StatusDot color={!template ? "indigo" : dirty ? "yellow" : "green"} />
                  <Text size="sm" fw={500}>
                    {!template ? "New template" : dirty ? "Unsaved changes" : "All changes saved"}
                  </Text>
                </Group>
                <TextInput
                  aria-label="Change note"
                  placeholder="Change note: what changed and why"
                  size="sm"
                  style={{ flex: 1, minWidth: 180 }}
                  {...form.getInputProps("note")}
                />
                <Button type="submit" loading={save.isPending} leftSection={<IconDeviceFloppy size={16} />}>
                  {template ? `Save as version ${template.current_version + 1}` : "Create template"}
                </Button>
              </Group>
            </Paper>

            {warnings.length > 0 && (
              <Alert color="yellow" title="Saved with warnings" withCloseButton onClose={() => setWarnings([])} data-testid="save-warnings">
                {warnings.map((w) => (
                  <div key={w}>{w}</div>
                ))}
              </Alert>
            )}
            {conflict && (
              <Alert color="red" title="Someone else saved first" data-testid="save-conflict" icon={<IconAlertTriangle size={18} />}>
                <Stack gap="xs">
                  <Text size="sm">{conflict.message}</Text>
                  <Text size="sm">Reloading shows their version; your unsaved edits here are discarded.</Text>
                  <Group>
                    <Button size="xs" color="red" variant="light" onClick={onReload} leftSection={<IconRefresh size={14} />}>
                      Reload their version
                    </Button>
                  </Group>
                </Stack>
              </Alert>
            )}
            {problems.length > 0 && (
              <Alert color="red" title="Not saved" data-testid="save-errors" icon={<IconAlertTriangle size={18} />}>
                {problems.map((p) => (
                  <div key={p}>{p}</div>
                ))}
              </Alert>
            )}

            <Section title="Basics" icon={<IconFileDescription size={18} />} description="How the template is listed.">
              <Stack>
                <Group grow align="flex-start">
                  <TextInput label="Title" required {...form.getInputProps("title")} />
                  <TextInput
                    label="Slug"
                    description={template ? "Fixed after creation" : "Used in URLs: …/templates/<slug>"}
                    required
                    disabled={!!template}
                    {...form.getInputProps("slug")}
                  />
                </Group>
                <Textarea label="Description" autosize minRows={2} {...form.getInputProps("description")} />
                <NumberInput
                  label="Credits per run"
                  description="What a signed-in app user pays each time they run it (refunded if the job fails). 0 = free."
                  min={0}
                  max={10000}
                  allowDecimal={false}
                  w={260}
                  {...form.getInputProps("credit_cost")}
                />
              </Stack>
            </Section>

            <Section title="Model" icon={<IconCpu size={18} />} description="Provider, model and output settings.">
              <Stack>
                <Group grow align="flex-start">
                  <div>
                    <Text size="sm" fw={500} mb={4}>
                      Media type
                    </Text>
                    <SegmentedControl fullWidth data={["image", "video"]} {...form.getInputProps("media_type")} />
                  </div>
                  <Select
                    label="Provider"
                    description={usesImages ? "Only providers that take input images" : undefined}
                    data={providerOptions}
                    required
                    allowDeselect={false}
                    {...form.getInputProps("provider")}
                  />
                </Group>
                <Group grow align="flex-start">
                  <Autocomplete
                    label="Model"
                    description="Known models, or type another"
                    data={models}
                    required
                    {...form.getInputProps("model")}
                  />
                  <TagsInput
                    label="Allowed models"
                    description="Callers may pick one of these per request"
                    data={models}
                    {...form.getInputProps("allowed_models")}
                  />
                </Group>
                <Group grow align="flex-start">
                  <Select
                    label="Aspect ratio"
                    data={["auto", ...ratios.filter((r) => r !== "auto")]}
                    allowDeselect={false}
                    {...form.getInputProps("aspect_ratio")}
                  />
                  {v.media_type === "image" ? (
                    <NumberInput label="Images (n)" min={1} max={provider?.max_images ?? 8} {...form.getInputProps("n")} />
                  ) : (provider?.video_durations ?? []).length > 0 ? (
                    <Select
                      label="Duration (s)"
                      data={(provider?.video_durations ?? []).map(String)}
                      placeholder="default"
                      clearable
                      {...form.getInputProps("duration_seconds")}
                    />
                  ) : (
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
                  )}
                  {(provider?.supports_seed || v.seed !== "") && (
                    <NumberInput label="Seed" allowDecimal={false} {...form.getInputProps("seed")} />
                  )}
                </Group>
              </Stack>
            </Section>

            <Section title="Prompt" icon={<IconWand size={18} />} description="Callers never see it; they fill the {{variables}}.">
              <Stack>
                <Textarea label="Prompt" required autosize minRows={4} {...form.getInputProps("prompt")} />
                <PromptVariables form={form} />
                {(provider?.supports_negative_prompt || v.negative_prompt) && (
                  <Textarea label="Negative prompt" autosize minRows={1} {...form.getInputProps("negative_prompt")} />
                )}
              </Stack>
            </Section>

            <Section title="Inputs & variables" icon={<IconVariable size={18} />} description="What a caller sends with each run.">
              <Stack gap="lg">
                <SlotsEditor form={form} />
                <VariablesEditor form={form} />
              </Stack>
            </Section>

            <Section title="Images" icon={<IconPhoto size={18} />} description="Cover for the catalog, and reference images for the provider.">
              <Stack gap="lg">
                <CoverPicker form={form} />
                <ReferenceImages form={form} />
              </Stack>
            </Section>
          </Stack>
        </form>
      </Grid.Col>
      <Grid.Col span={{ base: 12, lg: 5 }}>
        <Stack gap="lg">
          <Paper withBorder p="lg" shadow="xs">
            <Group justify="space-between" mb="sm">
              <Text fw={600}>Catalog preview</Text>
              <Text size="xs" c="dimmed">
                as the Android app lists it
              </Text>
            </Group>
            <Box maw={320} mx="auto">
              <TemplateCard template={preview} details />
            </Box>
          </Paper>
          {aside?.(dirty)}
        </Stack>
      </Grid.Col>
    </Grid>
  );
}

// ---- side panels -------------------------------------------------------------------------------

function StatusButtons({ template, onChanged }: { template: TemplateFull; onChanged: (t: TemplateFull) => void }) {
  const app = useCurrentApp();
  const qc = useQueryClient();
  const set = useMutation({
    mutationFn: (status: TemplateStatus) =>
      unwrap(
        api.POST("/v1/apps/{app_id}/manage/templates/{template_id}/status", {
          params: { path: { app_id: app.id, template_id: template.id } },
          body: { status },
        }),
      ),
    onSuccess: (t) => {
      qc.invalidateQueries({ queryKey: keys.app(app.id) });
      onChanged(t);
    },
  });
  return template.status === "active" ? (
    <Tooltip label="Hide it from the app; it becomes a draft">
      <Button
        variant="default"
        leftSection={<IconEyeOff size={16} />}
        loading={set.isPending}
        onClick={() => set.mutate("draft")}
      >
        Deactivate
      </Button>
    </Tooltip>
  ) : (
    <Tooltip label="Show it in the app (current version)">
      <Button color="green" leftSection={<IconEye size={16} />} loading={set.isPending} onClick={() => set.mutate("active")}>
        Activate
      </Button>
    </Tooltip>
  );
}

function History({ template, onRestored }: { template: TemplateFull; onRestored: (t: TemplateFull) => void }) {
  const app = useCurrentApp();
  const versions = [...(template.versions ?? [])].sort((a, b) => b.version - a.version);
  const [selected, setSelected] = useState<number>(template.current_version);
  const qc = useQueryClient();
  const restore = useMutation({
    mutationFn: (version: number) =>
      unwrap(
        api.POST("/v1/apps/{app_id}/manage/templates/{template_id}/versions/{version}/restore", {
          params: { path: { app_id: app.id, template_id: template.id, version } },
        }),
      ),
    onSuccess: (saved) => {
      qc.invalidateQueries({ queryKey: keys.app(app.id) });
      notifications.show({ color: "green", message: `Restored as version ${saved.template.current_version}` });
      onRestored(saved.template);
    },
  });
  const sel = versions.find((x) => x.version === selected);
  const prev = versions.find((x) => x.version === selected - 1);
  const changes = sel ? diffVersions(prev, sel) : [];

  return (
    <Stack gap="md" data-testid="history">
      <Timeline active={-1} bulletSize={22} lineWidth={2}>
        {versions.map((x) => (
          <Timeline.Item
            key={x.version}
            color={x.version === template.current_version ? "indigo" : "gray"}
            bullet={<Text size="10px" fw={700}>{x.version}</Text>}
            title={
              <UnstyledButton
                onClick={() => setSelected(x.version)}
                px={8}
                py={4}
                style={{
                  borderRadius: 6,
                  width: "100%",
                  background: x.version === selected ? "var(--mantine-primary-color-light)" : undefined,
                }}
                aria-pressed={x.version === selected}
              >
                <Group gap="xs" justify="space-between" wrap="nowrap">
                  <Text size="sm" fw={600}>
                    Version {x.version}
                    {x.version === template.current_version && (
                      <Badge size="xs" ml={6} color="indigo">
                        current
                      </Badge>
                    )}
                  </Text>
                  <Text size="xs" c="dimmed">
                    {age(x.created_at)}
                  </Text>
                </Group>
                <Text size="xs" c="dimmed">
                  {x.created_by.name}
                  {x.note ? ` — ${x.note}` : ""}
                </Text>
              </UnstyledButton>
            }
          />
        ))}
      </Timeline>
      {sel && (
        <Paper withBorder p="sm" bg="var(--app-subtle)">
          <Group justify="space-between" mb={6}>
            <Text size="sm" fw={600}>
              {prev ? `Changes in v${sel.version} since v${prev.version}` : `Version ${sel.version}`}
            </Text>
            {sel.version !== template.current_version && (
              <Button
                size="compact-xs"
                variant="light"
                loading={restore.isPending}
                onClick={() => restore.mutate(sel.version)}
                leftSection={<IconRestore size={12} />}
              >
                Restore as new version
              </Button>
            )}
          </Group>
          {changes.length === 0 ? (
            <Text size="xs" c="dimmed">
              No field changes.
            </Text>
          ) : (
            <Table fz="xs" verticalSpacing={4} data-testid="version-diff" highlightOnHover={false}>
              <Table.Tbody>
                {changes.map((c) => (
                  <Table.Tr key={c.field}>
                    <Table.Td fw={600} style={{ verticalAlign: "top" }} w={110}>
                      {c.field}
                    </Table.Td>
                    <Table.Td style={{ wordBreak: "break-word" }}>
                      {prev && (
                        <Text size="xs" c="red" td="line-through">
                          {c.before}
                        </Text>
                      )}
                      <Text size="xs" c="green">
                        {c.after}
                      </Text>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
        </Paper>
      )}
    </Stack>
  );
}

function TestRun({ template, dirty }: { template: TemplateFull; dirty: boolean }) {
  const versions = [...(template.versions ?? [])].sort((a, b) => b.version - a.version);
  const [version, setVersion] = useState(template.current_version);
  const [jobId, setJobId] = useState<string | null>(null);
  const v = versions.find((x) => x.version === version) ?? template.current;
  return (
    <Stack gap="sm" data-testid="test-run">
      <Text size="sm" c="dimmed">
        Runs a saved version (drafts too) with your image. Unsaved edits are not included.
      </Text>
      {dirty && (
        <Alert color="yellow" p="xs">
          The editor has unsaved changes; save first to test them.
        </Alert>
      )}
      <Select
        label="Version"
        data={versions.map((x) => ({ value: String(x.version), label: `v${x.version}${x.note ? ` — ${x.note}` : ""}` }))}
        value={String(version)}
        onChange={(x) => x && setVersion(Number(x))}
        allowDeselect={false}
      />
      <RunTemplateForm
        key={version}
        template={{ ref: template.id, inputs: v.inputs, variables: v.variables, model: v.model, allowed_models: v.allowed_models }}
        version={version}
        onJob={(job) => setJobId(job.id)}
        showCurl={false}
        submitLabel="Test run"
      />
      {jobId && (
        <Paper withBorder p="md">
          <JobDetail id={jobId} showOpenLink />
        </Paper>
      )}
    </Stack>
  );
}

// ---- page --------------------------------------------------------------------------------------

export function TemplateEditorPage() {
  const { templateId: id } = useParams();
  const app = useCurrentApp();
  const isNew = id === "new";
  const navigate = useNavigate();
  const qc = useQueryClient();
  const q = useTemplate(app.id, isNew ? undefined : id);
  // The version the form was loaded from (= base_version of the next save). Pinned so a background
  // refetch that sees someone else's save doesn't wipe the form; we show a notice instead.
  const [pinned, setPinned] = useState<number | null>(null);
  if (q.data && pinned === null) setPinned(q.data.current_version);

  const accept = (t: TemplateFull) => {
    qc.setQueryData(keys.template(app.id, t.id), t);
    setPinned(t.current_version);
  };
  const back = (
    <Button
      component={Link}
      to={`/apps/${app.id}`}
      variant="subtle"
      size="compact-sm"
      leftSection={<IconArrowLeft size={14} />}
      mb="sm"
      style={{ alignSelf: "flex-start" }}
    >
      Templates
    </Button>
  );

  if (isNew) {
    return (
      <Stack gap={0}>
        {back}
        <Title order={3} fz={20} mb="lg">
          New template
        </Title>
        <EditorForm
          template={null}
          base={null}
          onSaved={(t, warnings) => {
            qc.setQueryData(keys.template(app.id, t.id), t);
            navigate(`/apps/${app.id}/templates/${t.id}`, { replace: true, state: { warnings } });
          }}
        />
      </Stack>
    );
  }
  if (q.error) return <Alert color="red">{errorMessage(q.error)}</Alert>;
  if (!q.data || pinned === null)
    return (
      <Stack>
        <Skeleton height={28} width={300} />
        <Skeleton height={400} />
      </Stack>
    );

  const t = q.data;
  const base = t.versions?.find((x) => x.version === pinned) ?? t.current;

  return (
    <Stack gap={0}>
      {back}
      <Group justify="space-between" mb="lg" wrap="wrap">
        <Group gap="sm" wrap="nowrap" style={{ minWidth: 0 }}>
          <Title order={3} fz={20} lineClamp={1}>
            {t.title}
          </Title>
          <TemplateStatusBadge status={t.status} />
          <Text c="dimmed" size="sm" ff="monospace">
            {t.slug} · v{t.current_version}
          </Text>
        </Group>
        <StatusButtons template={t} onChanged={(x) => qc.setQueryData(keys.template(app.id, x.id), x)} />
      </Group>
      {t.current_version !== pinned && (
        <Alert color="orange" data-testid="newer-version" mb="lg">
          <Group justify="space-between">
            <Text size="sm">
              Version {t.current_version} was saved by {t.current.created_by.name}; the form shows version {pinned}.
            </Text>
            <Button size="xs" onClick={() => accept(t)}>
              Load version {t.current_version}
            </Button>
          </Group>
        </Alert>
      )}
      <EditorForm
        key={pinned}
        template={t}
        base={base}
        onSaved={accept}
        onReload={async () => {
          const fresh = await q.refetch();
          if (fresh.data) accept(fresh.data);
        }}
        aside={(dirty) => (
          <Paper withBorder p="lg" shadow="xs">
            <Tabs defaultValue="test">
              <Tabs.List>
                <Tabs.Tab value="test" leftSection={<IconFlask size={14} />}>
                  Test run
                </Tabs.Tab>
                <Tabs.Tab value="history" leftSection={<IconHistory size={14} />}>
                  History ({t.versions?.length ?? 0})
                </Tabs.Tab>
              </Tabs.List>
              <Tabs.Panel value="test" pt="md">
                <TestRun key={t.current_version} template={t} dirty={dirty} />
              </Tabs.Panel>
              <Tabs.Panel value="history" pt="md">
                <History key={t.current_version} template={t} onRestored={accept} />
              </Tabs.Panel>
            </Tabs>
          </Paper>
        )}
      />
    </Stack>
  );
}
