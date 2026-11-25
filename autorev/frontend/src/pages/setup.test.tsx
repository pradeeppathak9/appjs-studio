import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, test } from "vitest";
import { App } from "../App";
import { renderAt, stubApi } from "../test/render";

const ADMIN = { id: 1, email: "owner@example.com", full_name: "Owner", is_admin: true };

beforeEach(() => localStorage.clear());

describe("first-run setup", () => {
  test("the sign-in page sends you to setup while there is no admin", async () => {
    stubApi({ "/api/auth/setup": { needed: true } });
    renderAt("/", <App />);
    expect(await screen.findByText("First-run setup")).toBeInTheDocument();
  });

  test("/setup goes back to sign-in once an admin exists", async () => {
    stubApi({ "/api/auth/setup": { needed: false } });
    renderAt("/setup", <App />);
    expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  test("creating the admin stores the session and opens the dashboard", async () => {
    let sent: unknown = null;
    stubApi({
      "/api/auth/setup": (_url: URL, init?: RequestInit) => {
        if (init?.method !== "POST") return { needed: true };
        sent = JSON.parse(String(init.body));
        return { access_token: "jwt", token_type: "bearer", user: ADMIN };
      },
      "/api/auth/me": ADMIN,
      "/api/apps": [],
    });
    renderAt("/setup", <App />);
    fireEvent.change(await screen.findByLabelText(/Setup token/), { target: { value: " tok-123 " } });
    fireEvent.change(screen.getByLabelText(/Email/), { target: { value: "owner@example.com" } });
    fireEvent.change(screen.getByLabelText(/^Name/), { target: { value: "Owner" } });
    fireEvent.change(screen.getByLabelText(/^Password/), { target: { value: "a-long-password" } });
    fireEvent.change(screen.getByLabelText(/Repeat password/), { target: { value: "a-long-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Create admin" }));

    expect(await screen.findByText("Your apps")).toBeInTheDocument();
    expect(localStorage.getItem("token")).toBe("jwt");
    expect(sent).toEqual({
      setup_token: "tok-123",
      email: "owner@example.com",
      full_name: "Owner",
      password: "a-long-password",
    });
  });

  test("a wrong token shows the API's message", async () => {
    stubApi({
      "/api/auth/setup": (_url: URL, init?: RequestInit) =>
        init?.method === "POST"
          ? new Response(JSON.stringify({ detail: "The setup token is wrong" }), { status: 403 })
          : { needed: true },
    });
    renderAt("/setup", <App />);
    fireEvent.change(await screen.findByLabelText(/Setup token/), { target: { value: "nope" } });
    fireEvent.change(screen.getByLabelText(/Email/), { target: { value: "owner@example.com" } });
    fireEvent.change(screen.getByLabelText(/^Name/), { target: { value: "Owner" } });
    fireEvent.change(screen.getByLabelText(/^Password/), { target: { value: "a-long-password" } });
    fireEvent.change(screen.getByLabelText(/Repeat password/), { target: { value: "a-long-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Create admin" }));
    await waitFor(() => expect(screen.getByText("The setup token is wrong")).toBeInTheDocument());
    expect(localStorage.getItem("token")).toBeNull();
  });
});
