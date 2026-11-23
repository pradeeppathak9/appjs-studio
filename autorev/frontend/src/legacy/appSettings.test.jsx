import React from "react";
import { describe, expect, test, vi } from "vitest";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Routes, Route, Outlet } from "react-router-dom";
import AppSettings from "./pages/AppSettings";

global.IS_REACT_ACT_ENVIRONMENT = true;

const APP = {
  id: "fee3024f5d6c4696a0ca6e9e341122dc",
  name: "LOOKSYHONLINE",
  api_key: "k".repeat(64),
  phonepe_enabled: true,
  razorpay_enabled: false,
  phonepe_environment: "PROD",
  enabled: true,
};

function Shell() {
  return <Outlet context={{ app: APP, setApp: () => {} }} />;
}

async function render(path, element) {
  global.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
  );
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/apps/:appId" element={<Shell />}>
            <Route path="integration-guide" element={element} />
            <Route path="settings" element={element} />
          </Route>
        </Routes>
      </MemoryRouter>
    );
  });
  const html = host.innerHTML;
  act(() => root.unmount());
  host.remove();
  return html;
}

describe("Settings", () => {
  test("Settings no longer carries the endpoint reference", async () => {
    const html = await render(`/apps/${APP.id}/settings`, <AppSettings />);
    // it moved to its own tab; Settings keeps credentials, gateway config, webhooks
    expect(html).not.toContain("Integration URLs");
    expect(html).not.toContain("/phonepay/setup");
    expect(html).toContain("App Credentials");
    expect(html).toContain("Webhooks");
  });
});

// The guide itself is tested in src/pages/app/guide/guide.test.tsx.
