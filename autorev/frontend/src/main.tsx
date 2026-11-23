import "@mantine/core/styles.css";
import "@mantine/notifications/styles.css";
import "@fontsource-variable/inter";
import "./styles.css";

import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { App } from "./App";
import { makeQueryClient } from "./queryClient";
import { cssVariablesResolver, theme } from "./theme";

const queryClient = makeQueryClient();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <MantineProvider theme={theme} defaultColorScheme="auto" cssVariablesResolver={cssVariablesResolver}>
      <Notifications position="top-right" />
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </MantineProvider>
  </StrictMode>,
);
