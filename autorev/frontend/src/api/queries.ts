import { useQuery } from "@tanstack/react-query";
import { getToken, request } from "./client";
import type { App, Me, SetupState } from "./types";

export const keys = {
  me: ["me"] as const,
  setup: ["setup"] as const,
  apps: ["apps"] as const,
  app: (id: string) => ["apps", id] as const,
  health: ["health"] as const,
};

export function useMe() {
  return useQuery({
    queryKey: keys.me,
    queryFn: () => request<Me>("/api/auth/me"),
    enabled: !!getToken(),
    staleTime: 60_000,
  });
}

/** Whether first-run setup is open (no admin yet). Public; asked once per page load. */
export function useSetupState() {
  return useQuery({
    queryKey: keys.setup,
    queryFn: () => request<SetupState>("/api/auth/setup"),
    staleTime: Infinity,
    retry: false,
  });
}

export function useApps() {
  return useQuery({ queryKey: keys.apps, queryFn: () => request<App[]>("/api/apps") });
}

export function useApp(appId: string | undefined) {
  return useQuery({
    queryKey: keys.app(appId ?? ""),
    queryFn: () => request<App>(`/api/apps/${appId}`),
    enabled: !!appId,
  });
}

export function useHealth() {
  return useQuery({
    queryKey: keys.health,
    queryFn: () => request<{ status: string }>("/api/health"),
    refetchInterval: 30_000,
    retry: false,
  });
}
