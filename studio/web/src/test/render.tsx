import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router";
import type { Me, MyApp } from "../api/types";
import { AppContext } from "../auth/appContext";
import { SessionContext } from "../auth/session";

export function renderWithApp(
  ui: ReactElement,
  { me, app, path = "/" }: { me?: Me; app?: MyApp; path?: string } = {},
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[path]}>
          <SessionContext.Provider value={me ?? null}>
            <AppContext.Provider value={app ?? null}>{ui}</AppContext.Provider>
          </SessionContext.Provider>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

export const user: Me = { id: "u1", email: "t@example.com", name: "Tess", role: "user", must_change_password: false };

export function appAs(role: MyApp["role"]): MyApp {
  return {
    id: "a1",
    slug: "pixel-fun",
    name: "Pixel Fun",
    description: "",
    platform: "android",
    status: "active",
    daily_job_limit: null,
    device_hourly_limit: null,
    auth_google_enabled: false,
    auth_phone_enabled: false,
    google_client_ids: [],
    phone_provider: "msg91",
    msg91_template_id: null,
    msg91_otp_var: null,
    msg91_auth_key_set: false,
    firebase_project_id: null,
    secrets_key_set: false,
    signup_credits: 0,
    require_login: false,
    payment_provider: "none",
    autorev_app_id: null,
    autorev_api_key_set: false,
    autorev_webhook_secret_set: false,
    created_at: "",
    updated_at: "",
    template_count: 0,
    active_template_count: 0,
    active_key_count: 0,
    member_count: 0,
    role,
  };
}
