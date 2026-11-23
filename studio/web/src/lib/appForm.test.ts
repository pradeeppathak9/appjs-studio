import { describe, expect, it } from "vitest";
import { appBody, appCurl, EMPTY_APP, signInBody } from "./appForm";

describe("app form", () => {
  it("sends blank limits as null (no limit)", () => {
    expect(appBody({ ...EMPTY_APP, name: "A", daily_job_limit: "", device_hourly_limit: 5 })).toMatchObject({
      daily_job_limit: null,
      device_hourly_limit: 5,
    });
  });

  it("shows app-key curl calls for listing, running and polling", () => {
    const c = appCurl("http://h:8010", "cak_x", "cartoon");
    expect(c).toContain('-H "X-App-Key: cak_x" -H "X-Device-Id: <install id>"');
    expect(c).toContain("http://h:8010/v1/app/templates\n");
    expect(c).toContain("-F photo=@me.jpg");
    expect(c).toContain("/v1/app/templates/cartoon/generations");
    expect(c).toContain("/v1/app/generations/<job id>");
  });

  it("sends the MSG91 auth key only when one is typed, so saving keeps the saved key", () => {
    const base = { ...EMPTY_APP, auth_phone_enabled: true, msg91_template_id: " 6650ab12 " };
    expect(signInBody(base)).not.toHaveProperty("msg91_auth_key");
    expect(signInBody(base)).toMatchObject({ phone_provider: "msg91", msg91_template_id: "6650ab12", msg91_otp_var: null });
    expect(signInBody({ ...base, msg91_auth_key: " 412345AbCd " })).toMatchObject({ msg91_auth_key: "412345AbCd" });
  });

  it("sends a blank Firebase project id as null", () => {
    expect(signInBody({ ...EMPTY_APP, phone_provider: "firebase", firebase_project_id: "  " })).toMatchObject({
      phone_provider: "firebase",
      firebase_project_id: null,
    });
  });
});
