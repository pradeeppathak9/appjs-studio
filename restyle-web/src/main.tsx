import "@fontsource-variable/inter";
import "./styles.css";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { App } from "./App";
import { ApiError } from "./lib/api";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: true,
      // 4xx answers won't change on retry; network errors and 5xx get two more tries
      retry: (n, e) => n < 2 && !(e instanceof ApiError && e.status >= 400 && e.status < 500),
    },
  },
});

// Images fetched with the app's headers live as object URLs: free them when they leave the cache.
queryClient.getQueryCache().subscribe((event) => {
  if (event.type === "removed" && event.query.queryKey[0] === "blob" && typeof event.query.state.data === "string") {
    URL.revokeObjectURL(event.query.state.data);
  }
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
