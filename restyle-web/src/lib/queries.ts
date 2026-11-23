import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "./api";
import { session, useSession } from "./session";
import { toStyle } from "./styles";

export const keys = {
  config: ["config"] as const,
  me: ["me"] as const,
  templates: ["templates"] as const,
  plans: ["plans"] as const,
  jobs: ["jobs"] as const,
  job: (id: string) => ["job", id] as const,
};

export function useConfig() {
  return useQuery({ queryKey: keys.config, queryFn: api.config, staleTime: 5 * 60_000 });
}

/** The signed-in account (balance, plan); keeps the stored copy fresh. */
export function useMe() {
  const { token } = useSession();
  const q = useQuery({ queryKey: keys.me, queryFn: api.me, enabled: !!token });
  useEffect(() => {
    if (q.data) session.setUser(q.data);
  }, [q.data]);
  return q;
}

export function useStyles(enabled = true) {
  return useQuery({
    queryKey: keys.templates,
    queryFn: async () => (await api.templates()).map(toStyle),
    enabled,
  });
}

export function usePlans() {
  return useQuery({ queryKey: keys.plans, queryFn: api.plans, staleTime: 5 * 60_000 });
}

export function useJobs(enabled = true) {
  return useQuery({ queryKey: keys.jobs, queryFn: api.jobs, enabled });
}

/** One job, polled every 2 s (5 s after 30 s) until it succeeds or fails. */
export function useJob(id: string | undefined) {
  const [started] = useState(() => Date.now());
  return useQuery({
    queryKey: keys.job(id ?? ""),
    queryFn: () => api.job(id!),
    enabled: !!id,
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      if (s === "succeeded" || s === "failed") return false;
      return Date.now() - started < 30_000 ? 2_000 : 5_000;
    },
  });
}

/** An image behind the API (needs the app's headers), as an object URL; revoked when unused. */
export function useAuthedImage(url: string | null | undefined) {
  const q = useQuery({
    queryKey: ["blob", url],
    queryFn: async () => URL.createObjectURL(await api.blob(url!)),
    enabled: !!url,
    staleTime: Infinity,
    gcTime: 10 * 60_000,
  });
  return q.data;
}

export function useSignOut() {
  const qc = useQueryClient();
  return async () => {
    try {
      await api.logout();
    } catch {
      /* the session is dropped here either way */
    }
    session.clear();
    qc.removeQueries({ queryKey: keys.me });
    qc.removeQueries({ queryKey: keys.jobs });
  };
}
