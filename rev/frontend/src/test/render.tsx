import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import type { ReactElement } from "react";
import { vi } from "vitest";
import { theme } from "../theme";

/** Render with the providers main.tsx sets up, at `path`. */
export function renderAt(path: string, ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider theme={theme}>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

type Route = unknown | ((url: URL, init?: RequestInit) => unknown);

/**
 * Stub fetch: `routes` maps a path (after the API base) to a JSON body, a Response, or a function of
 * the request returning either. The longest matching prefix wins; anything else answers [].
 */
export function stubApi(routes: Record<string, Route>) {
  const fn = vi.fn(async (input: string | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    const key = Object.keys(routes)
      .sort((a, b) => b.length - a.length)
      .find((k) => url.pathname === k || url.pathname.startsWith(`${k}/`));
    const route = key !== undefined ? routes[key] : [];
    const body = typeof route === "function" ? (route as (u: URL, i?: RequestInit) => unknown)(url, init) : route;
    if (body instanceof Response) return body;
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  globalThis.fetch = fn as unknown as typeof fetch;
  return fn;
}

/** A JSON list response with an X-Total-Count header. */
export function page(rows: unknown[], total: number | null) {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (total !== null) headers["X-Total-Count"] = String(total);
  return new Response(JSON.stringify(rows), { status: 200, headers });
}

/** The URLs fetch was called with whose path ends with `suffix`. */
export function calls(fn: ReturnType<typeof stubApi>, suffix: string): URL[] {
  return fn.mock.calls.map(([u]) => new URL(String(u))).filter((u) => u.pathname.endsWith(suffix));
}
