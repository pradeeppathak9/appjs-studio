import { Alert, Button, Select, Stack, Text, TextInput } from "@mantine/core";
import { useForm } from "@mantine/form";
import { IconPlayerPlay } from "@tabler/icons-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { errorMessage, runTemplate } from "../api/client";
import { keys } from "../api/queries";
import { useCurrentApp } from "../auth/appContext";
import type { InputSlot, Job, Variable } from "../api/types";
import { templateCurl } from "../lib/curl";
import { fieldErrors } from "../lib/formErrors";
import { CopyBlock } from "./common";
import { ImageDrop } from "./ImageDrop";
import type { Picked } from "../lib/images";

export type Runnable = {
  ref: string;
  inputs: InputSlot[];
  variables: Variable[];
  model: string;
  allowed_models: string[];
};

/**
 * Run a template the way an API client does: one file per input slot, variables, optional model.
 * `version` is for creators test-running a draft or an older version.
 */
export function RunTemplateForm({
  template,
  version,
  onJob,
  showCurl = true,
  submitLabel = "Run",
}: {
  template: Runnable;
  version?: number;
  onJob: (job: Job) => void;
  showCurl?: boolean;
  submitLabel?: string;
}) {
  const qc = useQueryClient();
  const app = useCurrentApp();
  const [files, setFiles] = useState<Record<string, Picked | null>>({});
  const form = useForm({
    initialValues: {
      variables: Object.fromEntries(template.variables.map((v) => [v.name, v.default ?? ""])) as Record<string, string>,
      model: template.model as string | null,
      webhook_url: "",
    },
  });
  const slotNames = template.inputs.map((s) => s.name);
  const known = (p: string) => p.startsWith("files.") || p.startsWith("variables.") || p === "model" || p === "webhook_url";
  const resolve = (f: string) => (slotNames.includes(f) ? `files.${f}` : f);

  const run = useMutation({
    meta: { quiet: true },
    mutationFn: () => {
      const picked: Record<string, File> = {};
      for (const [k, v] of Object.entries(files)) if (v) picked[k] = v.file;
      return runTemplate({
        appId: app.id,
        ref: template.ref,
        files: picked,
        variables: form.values.variables,
        model: template.allowed_models.length > 1 ? form.values.model : null,
        webhookUrl: form.values.webhook_url || null,
        version,
      });
    },
    onSuccess: (job) => {
      qc.invalidateQueries({ queryKey: keys.jobs });
      qc.setQueryData(keys.job(job.id), job);
      onJob(job);
    },
    onError: (e) => form.setErrors(fieldErrors(e, known, resolve).errors),
  });
  const rest = fieldErrors(run.error, known, resolve).rest;

  const submit = form.onSubmit(() => {
    const missing = template.inputs.filter((s) => s.required !== false && !files[s.name]);
    if (missing.length) {
      form.setErrors(Object.fromEntries(missing.map((s) => [`files.${s.name}`, "Choose an image"])));
      return;
    }
    run.mutate();
  });

  const changed = Object.fromEntries(
    template.variables
      .filter((v) => (form.values.variables[v.name] ?? "") !== (v.default ?? ""))
      .map((v) => [v.name, form.values.variables[v.name]]),
  );

  return (
    <form onSubmit={submit}>
      <Stack>
        {template.inputs.map((s) => (
          <ImageDrop
            key={s.name}
            name={s.name}
            label={s.label || s.name}
            required={s.required !== false}
            value={files[s.name] ?? null}
            onChange={(v) => {
              setFiles((f) => ({ ...f, [s.name]: v }));
              form.clearFieldError(`files.${s.name}`);
            }}
            error={form.errors[`files.${s.name}`] as string | undefined}
            onError={(msg) => form.setFieldError(`files.${s.name}`, msg)}
          />
        ))}
        {template.variables.map((v) =>
          v.choices && v.choices.length ? (
            <Select
              key={v.name}
              label={v.label || v.name}
              data={v.choices}
              allowDeselect={false}
              {...form.getInputProps(`variables.${v.name}`)}
            />
          ) : (
            <TextInput
              key={v.name}
              label={v.label || v.name}
              maxLength={v.max_length}
              {...form.getInputProps(`variables.${v.name}`)}
            />
          ),
        )}
        {template.allowed_models.length > 1 && (
          <Select
            label="Model"
            data={template.allowed_models}
            allowDeselect={false}
            {...form.getInputProps("model")}
          />
        )}
        <TextInput
          label="Webhook URL"
          description="Optional: the server POSTs the finished job here"
          placeholder="https://…"
          {...form.getInputProps("webhook_url")}
        />
        {run.error && (rest.length > 0 || !Object.keys(form.errors).length) && (
          <Alert color="red" data-testid="run-error">
            {rest.length ? rest.join("; ") : errorMessage(run.error)}
          </Alert>
        )}
        <Button type="submit" loading={run.isPending} leftSection={<IconPlayerPlay size={16} />}>
          {submitLabel}
        </Button>
        {showCurl && (
          <div>
            <CopyBlock
              label="Same call with curl"
              value={templateCurl({
                origin: window.location.origin,
                appId: app.id,
                ref: template.ref,
                slots: template.inputs.map((s) => ({ name: s.name, fileName: files[s.name]?.file.name })),
                variables: changed,
                model: template.allowed_models.length > 1 && form.values.model !== template.model ? form.values.model : null,
              })}
            />
            <Text size="xs" c="dimmed" mt={4}>
              Create a token under Account and export it as STUDIO_TOKEN.
            </Text>
          </div>
        )}
      </Stack>
    </form>
  );
}
