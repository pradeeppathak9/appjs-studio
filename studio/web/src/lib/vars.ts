/** `{{name}}` placeholders, same rule as the server: letters, digits and `_`. */
const VAR_RE = /\{\{\s*([A-Za-z0-9_]+)\s*\}\}/g;

/** Variable names used in the given texts, in order of first appearance, without duplicates. */
export function findVariables(...texts: (string | null | undefined)[]): string[] {
  const seen: string[] = [];
  for (const text of texts) {
    for (const m of (text ?? "").matchAll(VAR_RE)) {
      if (!seen.includes(m[1])) seen.push(m[1]);
    }
  }
  return seen;
}

/** Names used in the prompt but not declared, and declared but not used. */
export function variableProblems(used: string[], declared: string[]) {
  return {
    undeclared: used.filter((n) => !declared.includes(n)),
    unused: declared.filter((n) => n && !used.includes(n)),
  };
}
