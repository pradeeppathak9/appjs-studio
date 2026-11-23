import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RequireEditor } from "../pages/app/AppLayout";
import { appAs, renderWithApp, user } from "../test/render";
import { RunTemplateForm } from "./RunTemplateForm";

describe("RequireEditor", () => {
  it("tells a tester their role in the app can't open an editor page", () => {
    renderWithApp(
      <RequireEditor>
        <p>secret</p>
      </RequireEditor>,
      { me: user, app: appAs("tester") },
    );
    expect(screen.getByText("Your role can't do this")).toBeInTheDocument();
    expect(screen.getByText(/You are a tester in Pixel Fun/)).toBeInTheDocument();
    expect(screen.queryByText("secret")).not.toBeInTheDocument();
  });

  it("lets editors and admins in", () => {
    for (const role of ["editor", "admin"] as const) {
      const { unmount } = renderWithApp(
        <RequireEditor>
          <p>secret</p>
        </RequireEditor>,
        { me: user, app: appAs(role) },
      );
      expect(screen.getByText("secret")).toBeInTheDocument();
      unmount();
    }
  });
});

describe("RunTemplateForm", () => {
  afterEach(() => vi.unstubAllGlobals());
  const template = {
    ref: "cartoon",
    inputs: [{ name: "photo", label: "Your photo", required: true }],
    variables: [{ name: "mood", label: "Mood", default: "sunny", max_length: 60, choices: ["sunny", "rainy"] }],
    model: "m1",
    allowed_models: ["m1"],
  };

  it("asks for the image before submitting and shows the app-scoped curl command", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderWithApp(<RunTemplateForm template={template} onJob={() => {}} />, { me: user, app: appAs("tester") });
    expect(screen.getByText(/\$CREATIVE_TOKEN/)).toBeInTheDocument();
    expect(screen.getByText(/\/v1\/apps\/a1\/templates\/cartoon\/generations/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Run" }));
    expect(await screen.findByText("Choose an image")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("posts to the app and puts a server 422 for a slot next to that slot", async () => {
    const body = { error: { code: "validation_error", message: "bad", details: [{ field: "photo", message: "not an image" }] } };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 422 }));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: () => "blob:x", revokeObjectURL: () => {} }));
    const { container } = renderWithApp(<RunTemplateForm template={template} version={2} onJob={() => {}} />, {
      me: user,
      app: appAs("editor"),
    });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(input, new File(["x"], "me.png", { type: "image/png" }));
    await waitFor(() => expect(screen.getByText("me.png")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Run" }));
    expect(await screen.findByText("not an image")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/v1/apps/a1/templates/cartoon/generations");
    expect((init.body as FormData).get("version")).toBe("2");
  });
});
