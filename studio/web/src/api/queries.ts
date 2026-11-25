import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "./client";
import type { Job, JobStatus } from "./types";

export type JobFilter = {
  status?: JobStatus;
  template?: string;
  created_by?: string;
  source?: "console" | "app";
  limit?: number;
};

export const keys = {
  setup: ["setup"] as const,
  me: ["me"] as const,
  health: ["health"] as const,
  providers: ["providers"] as const,
  appProviders: (appId: string) => ["providers", "app", appId] as const,
  tokens: ["tokens"] as const,
  myApps: ["myApps"] as const,
  myApp: (appId: string) => ["myApps", appId] as const,
  // everything under one app starts with ["app", appId]
  app: (appId: string) => ["app", appId] as const,
  appTemplates: (appId: string) => ["app", appId, "templates", "active"] as const,
  appTemplate: (appId: string, ref: string) => ["app", appId, "templates", "public", ref] as const,
  manageTemplates: (appId: string) => ["app", appId, "templates", "manage"] as const,
  template: (appId: string, id: string) => ["app", appId, "templates", "manage", id] as const,
  catalog: (appId: string) => ["app", appId, "catalog"] as const,
  jobs: ["jobs"] as const,
  jobList: (appId: string, filter: JobFilter) => ["jobs", "list", appId, filter] as const,
  job: (id: string) => ["jobs", "one", id] as const,
  // admin
  admin: ["admin"] as const,
  users: ["admin", "users"] as const,
  userTokens: (id: string) => ["admin", "users", id, "tokens"] as const,
  userApps: (id: string) => ["admin", "users", id, "apps"] as const,
  adminApps: ["admin", "apps"] as const,
  adminApp: (id: string) => ["admin", "apps", id] as const,
  members: (id: string) => ["admin", "apps", id, "members"] as const,
  appKeys: (id: string) => ["admin", "apps", id, "keys"] as const,
  plans: (id: string) => ["admin", "apps", id, "plans"] as const,
  appUsers: (id: string, q: string, offset = 0, limit = 25) =>
    ["admin", "apps", id, "users", "list", q, offset, limit] as const,
  appUserCredits: (id: string, userId: string, offset: number, limit: number) =>
    ["admin", "apps", id, "users", "credits", userId, offset, limit] as const,
  appUser: (id: string, userId: string) => ["admin", "apps", id, "users", "one", userId] as const,
};

const TERMINAL: JobStatus[] = ["succeeded", "failed"];

export function isTerminal(job: Job | undefined): boolean {
  return job !== undefined && TERMINAL.includes(job.status);
}

/** Poll a job every 1.5 s until it succeeds or fails. */
export function jobRefetchInterval(job: Job | undefined): number | false {
  return isTerminal(job) ? false : 1500;
}

/** Poll the job list every 2 s while anything listed is queued or running, else every 15 s. */
export function jobListRefetchInterval(items: Job[] | undefined): number {
  return items?.some((j) => !isTerminal(j)) ? 2000 : 15000;
}

export function useSetupState() {
  return useQuery({
    queryKey: keys.setup,
    queryFn: () => unwrap(api.GET("/v1/auth/setup")),
    staleTime: Infinity,
  });
}

export function useMe(enabled = true) {
  return useQuery({
    queryKey: keys.me,
    queryFn: () => unwrap(api.GET("/v1/auth/me")),
    enabled,
    retry: false,
    staleTime: 60_000,
  });
}

export function useHealth() {
  return useQuery({
    queryKey: keys.health,
    queryFn: () => unwrap(api.GET("/healthz")),
    refetchInterval: 5000,
    retry: false,
  });
}

/** The providers jobs can run on: the server's, or with `appId`, also those the app has its own key for. */
export function useProviders(appId?: string) {
  return useQuery({
    queryKey: appId ? keys.appProviders(appId) : keys.providers,
    queryFn: () => unwrap(api.GET("/v1/providers", { params: { query: { app_id: appId } } })),
    staleTime: 5 * 60_000,
  });
}

// ---- my apps -------------------------------------------------------------------------------------

export function useMyApps() {
  return useQuery({ queryKey: keys.myApps, queryFn: () => unwrap(api.GET("/v1/apps")) });
}

export function useMyApp(appId: string) {
  return useQuery({
    queryKey: keys.myApp(appId),
    queryFn: () => unwrap(api.GET("/v1/apps/{app_id}", { params: { path: { app_id: appId } } })),
  });
}

const p = (appId: string) => ({ app_id: appId });

export function useAppTemplates(appId: string, enabled = true) {
  return useQuery({
    queryKey: keys.appTemplates(appId),
    queryFn: () => unwrap(api.GET("/v1/apps/{app_id}/templates", { params: { path: p(appId) } })),
    enabled,
  });
}

export function useAppTemplate(appId: string, ref: string | undefined) {
  return useQuery({
    queryKey: keys.appTemplate(appId, ref ?? ""),
    queryFn: () =>
      unwrap(api.GET("/v1/apps/{app_id}/templates/{ref}", { params: { path: { ...p(appId), ref: ref! } } })),
    enabled: !!ref,
  });
}

export function useManageTemplates(appId: string, enabled = true) {
  return useQuery({
    queryKey: keys.manageTemplates(appId),
    queryFn: () => unwrap(api.GET("/v1/apps/{app_id}/manage/templates", { params: { path: p(appId) } })),
    enabled,
  });
}

export function useTemplate(appId: string, id: string | undefined) {
  return useQuery({
    queryKey: keys.template(appId, id ?? ""),
    queryFn: () =>
      unwrap(
        api.GET("/v1/apps/{app_id}/manage/templates/{template_id}", {
          params: { path: { ...p(appId), template_id: id! } },
        }),
      ),
    enabled: !!id,
  });
}

export function useCatalog(appId: string) {
  return useQuery({
    queryKey: keys.catalog(appId),
    queryFn: () => unwrap(api.GET("/v1/apps/{app_id}/catalog", { params: { path: p(appId) } })),
  });
}

export function useAppJobs(appId: string, filter: JobFilter) {
  return useQuery({
    queryKey: keys.jobList(appId, filter),
    queryFn: () =>
      unwrap(
        api.GET("/v1/apps/{app_id}/generations", { params: { path: p(appId), query: { limit: 50, ...filter } } }),
      ),
    refetchInterval: (q) => jobListRefetchInterval(q.state.data?.items),
    refetchIntervalInBackground: false,
  });
}

export function useJob(id: string | undefined) {
  return useQuery({
    queryKey: keys.job(id ?? ""),
    queryFn: () => unwrap(api.GET("/v1/generations/{job_id}", { params: { path: { job_id: id! } } })),
    enabled: !!id,
    refetchInterval: (q) => jobRefetchInterval(q.state.data),
    refetchIntervalInBackground: false,
  });
}

// ---- admin ---------------------------------------------------------------------------------------

export function useAdminUsers() {
  return useQuery({ queryKey: keys.users, queryFn: () => unwrap(api.GET("/v1/admin/users")) });
}

export function useUserApps(userId: string) {
  return useQuery({
    queryKey: keys.userApps(userId),
    queryFn: () => unwrap(api.GET("/v1/admin/users/{user_id}/apps", { params: { path: { user_id: userId } } })),
  });
}

export function useAdminApps() {
  return useQuery({ queryKey: keys.adminApps, queryFn: () => unwrap(api.GET("/v1/admin/apps")) });
}

export function useAdminApp(appId: string) {
  return useQuery({
    queryKey: keys.adminApp(appId),
    queryFn: () => unwrap(api.GET("/v1/admin/apps/{app_id}", { params: { path: p(appId) } })),
  });
}

export function useMembers(appId: string) {
  return useQuery({
    queryKey: keys.members(appId),
    queryFn: () => unwrap(api.GET("/v1/admin/apps/{app_id}/members", { params: { path: p(appId) } })),
  });
}

export function useAppKeys(appId: string) {
  return useQuery({
    queryKey: keys.appKeys(appId),
    queryFn: () => unwrap(api.GET("/v1/admin/apps/{app_id}/keys", { params: { path: p(appId) } })),
  });
}

// ---- admin: an app's end users, plans --------------------------------------------------------------

export function usePlans(appId: string) {
  return useQuery({
    queryKey: keys.plans(appId),
    queryFn: () => unwrap(api.GET("/v1/admin/apps/{app_id}/plans", { params: { path: p(appId) } })),
  });
}

/** One page of the app's users (`items`, `total`), newest first. */
export function useAppUsers(appId: string, q: string, offset = 0, limit = 25) {
  return useQuery({
    queryKey: keys.appUsers(appId, q, offset, limit),
    queryFn: () =>
      unwrap(
        api.GET("/v1/admin/apps/{app_id}/users", {
          params: { path: p(appId), query: { q: q || undefined, offset, limit } },
        }),
      ),
    placeholderData: (prev) => prev,
  });
}

/** One page of a user's credit transactions, newest first. */
export function useAppUserCredits(appId: string, userId: string, offset = 0, limit = 20) {
  return useQuery({
    queryKey: keys.appUserCredits(appId, userId, offset, limit),
    queryFn: () =>
      unwrap(
        api.GET("/v1/admin/apps/{app_id}/users/{user_id}/credits", {
          params: { path: { ...p(appId), user_id: userId }, query: { offset, limit } },
        }),
      ),
    placeholderData: (prev) => prev,
  });
}

export function useAppUser(appId: string, userId: string | null) {
  return useQuery({
    queryKey: keys.appUser(appId, userId ?? ""),
    queryFn: () =>
      unwrap(
        api.GET("/v1/admin/apps/{app_id}/users/{user_id}", { params: { path: { ...p(appId), user_id: userId! } } }),
      ),
    enabled: !!userId,
  });
}

// ---- admin: change some of an app's settings ------------------------------------------------------

type AppPatchBody = import("./schema").components["schemas"]["AppPatch"];

/** PATCH /v1/admin/apps/{id}: only the fields given change. (openapi-typescript marks fields that
 * have a server default as required; the server treats every field of this body as optional.) */
/** Check an app's autorev connection: its key works, the gateway is on there and has keys. */
export function testPayments(appId: string) {
  return unwrap(api.POST("/v1/admin/apps/{app_id}/payments/test", { params: { path: { app_id: appId } } }));
}

export function patchApp(appId: string, changes: Partial<AppPatchBody>) {
  return unwrap(
    api.PATCH("/v1/admin/apps/{app_id}", { params: { path: { app_id: appId } }, body: changes as AppPatchBody }),
  );
}
