import { MutationCache, QueryClient } from "@tanstack/react-query";
import { notifications } from "@mantine/notifications";
import { ApiError, errorMessage } from "./api/client";

/** Don't retry client errors (4xx); retry other failures twice. */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status < 500) return false;
  return failureCount < 2;
}

export function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: shouldRetry, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
    mutationCache: new MutationCache({
      // A mutation can opt out (it shows the error itself) with meta: {quiet: true}.
      onError: (error, _v, _c, mutation) => {
        if (mutation.meta?.quiet) return;
        if (error instanceof ApiError && (error.status === 401 || error.code === "password_change_required")) {
          return;
        }
        notifications.show({ color: "red", title: "Request failed", message: errorMessage(error) });
      },
    }),
  });
}
