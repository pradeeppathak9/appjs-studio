/** The curl command an API client would run for a template; the token stays a shell variable. */
export function templateCurl(opts: {
  origin: string;
  appId: string;
  ref: string;
  slots: { name: string; fileName?: string }[];
  variables?: Record<string, string>;
  model?: string | null;
}): string {
  const lines = [`curl -H "Authorization: Bearer $STUDIO_TOKEN"`];
  for (const s of opts.slots) lines.push(`-F ${s.name}=@${s.fileName || `${s.name}.jpg`}`);
  if (opts.variables && Object.keys(opts.variables).length) {
    lines.push(`-F 'variables=${JSON.stringify(opts.variables).replace(/'/g, "'\\''")}'`);
  }
  if (opts.model) lines.push(`-F model=${opts.model}`);
  lines.push(`${opts.origin}/v1/apps/${opts.appId}/templates/${opts.ref}/generations`);
  return lines.join(" \\\n  ");
}
