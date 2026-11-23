import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, buildRunForm, errorMessage, errorWithDetails, runTemplate, setAuthHandlers, toApiError, unwrap } from "./client";

function fail(status: number, body: unknown) {
  return Promise.resolve({ data: undefined, error: body, response: new Response(null, { status }) });
}
const err = (code: string, extra: object = {}) => ({ error: { code, message: `msg ${code}`, ...extra } });

describe("error parsing", () => {
  it("reads the uniform error body", () => {
    const e = toApiError(422, err("validation_error", { details: [{ field: "prompt", message: "required" }] }));
    expect(e).toBeInstanceOf(ApiError);
    expect(e.code).toBe("validation_error");
    expect(e.message).toBe("msg validation_error");
    expect(e.details).toEqual([{ field: "prompt", message: "required" }]);
  });

  it("survives a body that isn't the error shape", () => {
    const e = toApiError(502, "<html>bad gateway</html>", "Bad Gateway");
    expect(e.code).toBe("http_502");
    expect(e.message).toBe("Bad Gateway");
  });

  it("can spell out the details", () => {
    const e = toApiError(422, err("validation_error", { details: [{ field: "cover_upload", message: "not found" }] }));
    expect(errorWithDetails(e)).toBe("msg validation_error: cover_upload: not found");
  });

  it("explains a 403 forbidden as a role problem", () => {
    expect(errorMessage(toApiError(403, err("forbidden")))).toBe("Your role can't do this.");
  });
});

describe("auth redirects", () => {
  const navigate = vi.fn();
  const onSignedOut = vi.fn();
  beforeEach(() => {
    navigate.mockReset();
    onSignedOut.mockReset();
    setAuthHandlers({ navigate, onSignedOut });
    window.history.pushState({}, "", "/jobs/abc?x=1");
  });

  it("401 unauthenticated -> login with the return path", async () => {
    await expect(unwrap(fail(401, err("unauthenticated")))).rejects.toMatchObject({ status: 401 });
    expect(onSignedOut).toHaveBeenCalled();
    expect(navigate).toHaveBeenCalledWith("/login?next=%2Fjobs%2Fabc%3Fx%3D1");
  });

  it("401 invalid_credentials (wrong password on the login form) doesn't redirect", async () => {
    window.history.pushState({}, "", "/login");
    await expect(unwrap(fail(401, err("invalid_credentials")))).rejects.toMatchObject({ code: "invalid_credentials" });
    expect(navigate).not.toHaveBeenCalled();
  });

  it("403 password_change_required -> change-password page", async () => {
    await expect(unwrap(fail(403, err("password_change_required")))).rejects.toBeInstanceOf(ApiError);
    expect(navigate).toHaveBeenCalledWith("/change-password");
  });

  it("403 forbidden stays on the page", async () => {
    await expect(unwrap(fail(403, err("forbidden")))).rejects.toMatchObject({ code: "forbidden" });
    expect(navigate).not.toHaveBeenCalled();
  });

  it("returns data on success", async () => {
    const ok = Promise.resolve({ data: { id: 1 }, response: new Response(null, { status: 200 }) });
    await expect(unwrap(ok)).resolves.toEqual({ id: 1 });
  });
});

describe("running a template (multipart)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("builds one file field per slot plus variables/model/version", () => {
    const photo = new File(["x"], "me.png", { type: "image/png" });
    const form = buildRunForm({ appId: "a1", ref: "t", files: { photo }, variables: { mood: "rainy" }, model: "m2", version: 3 });
    expect((form.get("photo") as File).name).toBe("me.png");
    expect(form.get("variables")).toBe('{"mood":"rainy"}');
    expect(form.get("model")).toBe("m2");
    expect(form.get("version")).toBe("3");
    expect(form.has("webhook_url")).toBe(false);
  });

  it("posts FormData without setting Content-Type, so the browser adds the boundary", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: "job1" }), { status: 202 }));
    vi.stubGlobal("fetch", fetchMock);
    const job = await runTemplate({ appId: "a1", ref: "ghibli gemini", files: { photo: new File(["x"], "a.jpg") } });
    expect(job).toEqual({ id: "job1" });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/v1/apps/a1/templates/ghibli%20gemini/generations");
    expect(init.method).toBe("POST");
    expect(init.body).toBeInstanceOf(FormData);
    expect(init.credentials).toBe("same-origin");
    expect(init.headers).toBeUndefined();
  });

  it("turns a 422 into an ApiError with details", async () => {
    const body = err("validation_error", { details: [{ field: "photo", message: "not an image" }] });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 422 })));
    await expect(runTemplate({ appId: "a1", ref: "t", files: {} })).rejects.toMatchObject({
      status: 422,
      details: [{ field: "photo", message: "not an image" }],
    });
  });
});
