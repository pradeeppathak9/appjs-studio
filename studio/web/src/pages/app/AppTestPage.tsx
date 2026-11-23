import { Alert, Card, Group, Image, Select, Stack, Text, Title } from "@mantine/core";
import { useState } from "react";
import { useSearchParams } from "react-router";
import { errorMessage } from "../../api/client";
import { useAppTemplate, useAppTemplates, useManageTemplates, useTemplate } from "../../api/queries";
import { useCurrentApp } from "../../auth/appContext";
import { canEdit } from "../../auth/roles";
import { RunTemplateForm } from "../../components/RunTemplateForm";
import { Workspace } from "../../components/Workspace";
import { useSelectedJob } from "../../lib/useSelectedJob";

function Header({ title, description, cover, meta }: { title: string; description: string; cover?: string | null; meta: string }) {
  return (
    <Group align="flex-start" wrap="nowrap">
      {cover && <Image src={cover} alt={`${title} cover`} h={80} w={80} fit="cover" radius="sm" />}
      <div>
        <Title order={4}>{title}</Title>
        {description && (
          <Text size="sm" c="dimmed">
            {description}
          </Text>
        )}
        <Text size="xs" c="dimmed">
          {meta}
        </Text>
      </div>
    </Group>
  );
}

/** Testers: the current version of an active template. */
function TesterRunner({ slug }: { slug: string }) {
  const app = useCurrentApp();
  const t = useAppTemplate(app.id, slug);
  const [, selectJob] = useSelectedJob();
  if (t.error) return <Alert color="red">{errorMessage(t.error)}</Alert>;
  if (!t.data) return <Text c="dimmed">Loading…</Text>;
  const tpl = t.data;
  return (
    <Stack>
      <Header
        title={tpl.title}
        description={tpl.description}
        cover={tpl.cover_url}
        meta={`${tpl.slug} · version ${tpl.version} · ${tpl.media_type} · model ${tpl.model}`}
      />
      <RunTemplateForm key={`${tpl.id}:${tpl.version}`} template={{ ...tpl, ref: tpl.slug }} onJob={(j) => selectJob(j.id)} />
    </Stack>
  );
}

/** Editors: any template (drafts too) and any saved version; sends `version`. */
function EditorRunner({ templateId }: { templateId: string }) {
  const app = useCurrentApp();
  const t = useTemplate(app.id, templateId);
  const [version, setVersion] = useState<number | null>(null);
  const [, selectJob] = useSelectedJob();
  if (t.error) return <Alert color="red">{errorMessage(t.error)}</Alert>;
  if (!t.data) return <Text c="dimmed">Loading…</Text>;
  const tpl = t.data;
  const versions = [...(tpl.versions ?? [])].sort((a, b) => b.version - a.version);
  const chosen = version ?? tpl.current_version;
  const v = versions.find((x) => x.version === chosen) ?? tpl.current;
  return (
    <Stack>
      <Header
        title={tpl.title}
        description={tpl.description}
        cover={tpl.cover_url}
        meta={`${tpl.slug} · ${tpl.status} · ${v.provider}/${v.model}`}
      />
      <Select
        label="Version"
        data={versions.map((x) => ({
          value: String(x.version),
          label: `v${x.version}${x.version === tpl.current_version ? " (current)" : ""}${x.note ? ` — ${x.note}` : ""}`,
        }))}
        value={String(chosen)}
        onChange={(x) => x && setVersion(Number(x))}
        allowDeselect={false}
      />
      <RunTemplateForm
        key={`${tpl.id}:${chosen}`}
        template={{ ref: tpl.slug, inputs: v.inputs, variables: v.variables, model: v.model, allowed_models: v.allowed_models }}
        version={chosen}
        onJob={(j) => selectJob(j.id)}
      />
    </Stack>
  );
}

export function AppTestPage() {
  const app = useCurrentApp();
  const editor = canEdit(app.role);
  const [params, setParams] = useSearchParams();
  const slug = params.get("t") ?? undefined;
  const manage = useManageTemplates(app.id, editor);
  const active = useAppTemplates(app.id, !editor);
  const options = editor
    ? [...(manage.data ?? [])]
        .sort((a, b) => a.position - b.position)
        .map((t) => ({ value: t.slug, label: t.status === "active" ? t.title : `${t.title} (draft)` }))
    : (active.data ?? []).map((t) => ({ value: t.slug, label: t.title }));
  const managed = manage.data?.find((t) => t.slug === slug);

  return (
    <Workspace>
      <Card padding="lg">
        <Stack>
          <div>
            <Title order={3} fz={18}>
              Test a template
            </Title>
            <Text size="sm" c="dimmed">
              Upload a photo and run a template the way the Android app does.
            </Text>
          </div>
          <Select
            label="Template"
            placeholder={options.length ? "Pick a template" : "No templates to test yet"}
            data={options}
            value={slug ?? null}
            onChange={(v) => v && setParams({ t: v })}
            searchable
            allowDeselect={false}
            data-testid="template-select"
          />
          {slug && editor && managed && <EditorRunner key={managed.id} templateId={managed.id} />}
          {slug && !editor && <TesterRunner key={slug} slug={slug} />}
        </Stack>
      </Card>
    </Workspace>
  );
}
