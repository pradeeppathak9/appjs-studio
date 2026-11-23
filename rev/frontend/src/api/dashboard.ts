import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { DateRange } from "../lib/dateRange";
import { rangeParams } from "../lib/dateRange";
import { request, requestPage, type Query } from "./client";
import type {
  PhoneStatus,
  RazorpayTransaction,
  ScheduledTransaction,
  Subscription,
  SubscriptionTransaction,
  Summary,
} from "./types";

const base = (appId: string) => `/api/apps/${appId}`;

export function useSummary(appId: string, range: DateRange, enabled = true) {
  return useQuery({
    queryKey: ["summary", appId, range],
    queryFn: () => request<Summary>(`${base(appId)}/summary`, { query: rangeParams(range) }),
    enabled,
    placeholderData: keepPreviousData,
  });
}

/** Per-state counts for the filter pills. They leave out the state filter, so picking one pill keeps the others. */
export function useStateCounts(appId: string, kind: "subscriptions" | "scheduled", params: Query) {
  return useQuery({
    queryKey: ["state-counts", appId, kind, params],
    queryFn: () => request<Record<string, number>>(`${base(appId)}/${kind}/state-counts`, { query: params }),
    placeholderData: keepPreviousData,
  });
}

type Page<T> = { rows: T[]; total: number | null };

/**
 * One page of a list, with paging state. The page resets to 0 whenever `filters` change. The total
 * (X-Total-Count) is asked for on page 0 only and reused while paging, which saves a count(*) per
 * page; endpoints without a count report hasMore from a full page instead.
 */
export function usePagedList<T>(path: string, filters: Query, pageSize = 50) {
  const qc = useQueryClient();
  const filterKey = JSON.stringify(filters);
  const [state, setState] = useState({ filterKey, page: 0 });
  const page = state.filterKey === filterKey ? state.page : 0;
  const listKey = ["list", path, filters] as const;
  const knownTotal = qc.getQueryData<Page<T>>([...listKey, 0])?.total ?? null;
  const withCount = page === 0 || knownTotal === null;

  const q = useQuery({
    queryKey: [...listKey, page],
    queryFn: () =>
      requestPage<T>(path, { query: { ...filters, limit: pageSize, offset: page * pageSize, with_count: withCount } }),
    placeholderData: keepPreviousData,
  });
  const rows = q.data?.rows ?? [];
  const total = q.data?.total ?? (page === 0 ? null : knownTotal);
  return {
    ...q,
    rows,
    page,
    pageSize,
    total,
    hasMore: total !== null ? (page + 1) * pageSize < total : rows.length === pageSize,
    setPage: (p: number) => setState({ filterKey, page: p }),
  };
}

/** Every row matching `filters`, fetched in batches of 1000 (for CSV export). */
export async function fetchAll<T>(path: string, filters: Query): Promise<T[]> {
  const BATCH = 1000;
  let all: T[] = [];
  for (let offset = 0; ; offset += BATCH) {
    const { rows } = await requestPage<T>(path, { query: { ...filters, limit: BATCH, offset, with_count: false } });
    all = all.concat(rows);
    if (rows.length < BATCH) return all;
  }
}

export const paths = {
  subscriptions: (appId: string) => `${base(appId)}/subscriptions`,
  scheduled: (appId: string) => `${base(appId)}/scheduled`,
  razorpaySubscriptions: (appId: string) => `${base(appId)}/razorpay-subscriptions`,
  razorpayTransactions: (appId: string) => `${base(appId)}/razorpay-transactions`,
};

export function useSubscription(appId: string, subscriptionId: string | null) {
  return useQuery({
    queryKey: ["subscription", appId, subscriptionId],
    queryFn: () => request<Subscription>(`${base(appId)}/subscriptions/${subscriptionId}`),
    enabled: !!subscriptionId,
  });
}

/** The scheduled payments of one subscription (the details drawer). */
export function useSubscriptionSchedule(appId: string, subscriptionId: string | null) {
  return useQuery({
    queryKey: ["subscription-schedule", appId, subscriptionId],
    queryFn: () =>
      request<ScheduledTransaction[]>(`${base(appId)}/scheduled`, {
        query: { subscription_id: subscriptionId, limit: 200 },
      }),
    enabled: !!subscriptionId,
  });
}

/** Every charge attempt against one scheduled payment. */
export function useScheduledAttempts(appId: string, scheduledId: string | null) {
  return useQuery({
    queryKey: ["scheduled-attempts", appId, scheduledId],
    queryFn: () => request<SubscriptionTransaction[]>(`${base(appId)}/scheduled/${scheduledId}/attempts`),
    enabled: !!scheduledId,
  });
}

export function useRevokeSubscription(appId: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { quiet: true },
    mutationFn: (subscriptionId: string) =>
      request<Subscription>(`${base(appId)}/subscriptions/${subscriptionId}/revoke`, { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["list"] });
      qc.invalidateQueries({ queryKey: ["state-counts", appId] });
      qc.invalidateQueries({ queryKey: ["subscription", appId] });
    },
  });
}

/** The live status an integration sees for a phone number: the public API, called with the app's key. */
export function usePhoneStatus(appId: string, apiKey: string, phone: string | null) {
  return useQuery({
    queryKey: ["phone-status", appId, phone],
    queryFn: () => request<PhoneStatus>(`/api/v1/${appId}/phonepay/${phone}/status`, { auth: apiKey }),
    enabled: !!phone,
    staleTime: 0,
  });
}

export function useRazorpaySubscriptionTransactions(appId: string, subscriptionId: string | null) {
  return useQuery({
    queryKey: ["rz-subscription-transactions", appId, subscriptionId],
    queryFn: () => request<RazorpayTransaction[]>(`${base(appId)}/razorpay-subscriptions/${subscriptionId}/transactions`),
    enabled: !!subscriptionId,
  });
}

