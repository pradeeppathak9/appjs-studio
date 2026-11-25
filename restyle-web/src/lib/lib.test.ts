import { describe, expect, it } from "vitest";
import { ApiError, type Account, type Plan, type Template } from "./api";
import { creditsLabel, displayPhone, formatPrice, greeting, userMessage } from "./format";
import { cropBox, RATIOS } from "./image";
import { needsSubscription, periods, planFor, planLine, trialOffered } from "./subscription";
import { missingDetails, validEmail, validMobile } from "./checkout";
import { categories, filterStyles, javaHash, toStyle } from "./styles";

const template = (slug: string, extra: Partial<Template> = {}): Template => ({
  id: slug,
  slug,
  title: slug.toUpperCase(),
  description: "",
  media_type: "image",
  inputs: [{ name: "photo", label: "Your photo", required: true }],
  cover_url: null,
  credit_cost: 2,
  version: 1,
  ...extra,
});

describe("format", () => {
  it("formats prices like the Android app", () => {
    expect(formatPrice(19900)).toBe("₹199");
    expect(formatPrice(19950)).toBe("₹199.50");
    expect(formatPrice(14990000)).toBe("₹1,49,900");
    expect(formatPrice(500, "USD")).toBe("$5");
  });

  it("labels credits and phones", () => {
    expect(creditsLabel(1)).toBe("1 credit");
    expect(creditsLabel(0)).toBe("0 credits");
    expect(displayPhone("+919876543210")).toBe("+91 98765 43210");
    expect(displayPhone("+15555550100")).toBe("+15555550100");
  });

  it("greets by time of day", () => {
    expect(greeting(new Date(2026, 0, 1, 9))).toBe("Good morning");
    expect(greeting(new Date(2026, 0, 1, 14))).toBe("Good afternoon");
    expect(greeting(new Date(2026, 0, 1, 20))).toBe("Good evening");
  });

  it("explains API errors in the app's words", () => {
    expect(userMessage(new ApiError(400, "otp_invalid", "x", [{ attempts_left: 1 }]))).toBe("That code didn't work. 1 try left.");
    expect(userMessage(new ApiError(402, "insufficient_credits", "x"))).toBe("You need more credits for this style.");
    expect(userMessage(new ApiError(200, "content_policy", "x"))).toMatch(/refunded/);
    expect(userMessage(new ApiError(401, "unauthenticated", "x"), true)).toBe("Your session ended. Sign in again.");
    expect(userMessage(new ApiError(401, "unauthenticated", "x"), false)).toBe("Sign in to continue.");
    expect(userMessage(new ApiError(0, "network", "x"))).toMatch(/Can't reach the server/);
    expect(userMessage(new Error("boom"))).toBe("Something went wrong. Try again.");
  });
});

describe("styles", () => {
  it("hashes slugs like Java's String.hashCode, so colours match Android", () => {
    expect(javaHash("")).toBe(0);
    expect(javaHash("a")).toBe(97);
    expect(javaHash("hello")).toBe(99162322);
    expect(javaHash("ghibli-gemini")).toBe(javaHash("ghibli-gemini"));
  });

  it("decorates known styles and falls back for others", () => {
    const known = toStyle(template("ghibli-style"), 0);
    expect([known.category, known.meta, known.color, known.trending]).toEqual(["Anime", "Anime · Hand-painted", "#3C5A3A", true]);
    const other = toStyle(template("neon-city-poster", { description: "Game poster" }), 3);
    expect([other.category, other.meta, other.trending, other.slot]).toEqual(["More", "Game poster", false, "photo"]);
    expect(other.color).toMatch(/^#[0-9A-F]{6}$/);
  });

  it("filters by category and search", () => {
    const all = [toStyle(template("ghibli-style"), 0), toStyle(template("80s-retro"), 1), toStyle(template("pixel-art"), 2)];
    expect(categories(all)).toEqual(["All", "Anime", "Retro"]);
    expect(filterStyles(all, "Retro", "").map((s) => s.slug)).toEqual(["80s-retro", "pixel-art"]);
    expect(filterStyles(all, "All", "16-bit").map((s) => s.slug)).toEqual(["pixel-art"]);
  });
});

describe("cropBox", () => {
  const [square, portrait, story] = RATIOS;

  it("centres the crop and keeps the shape", () => {
    expect(cropBox(4000, 3000, square)).toEqual({ sx: 500, sy: 0, sw: 3000, sh: 3000, dw: 2048, dh: 2048 });
    const p = cropBox(1000, 1000, portrait);
    expect([p.sx, p.sy, p.sw, p.sh]).toEqual([100, 0, 800, 1000]);
    const s = cropBox(1080, 1920, story);
    expect([s.sw, s.sh, s.dw, s.dh]).toEqual([1080, 1920, 1080, 1920]); // already 9:16, small enough
  });

  it("never upscales and caps the long side", () => {
    const b = cropBox(6000, 8000, portrait);
    expect(Math.max(b.dw, b.dh)).toBe(2048);
    expect(b.dw / b.dh).toBeCloseTo(4 / 5, 2);
    expect(cropBox(400, 500, portrait)).toMatchObject({ dw: 400, dh: 500 });
  });
});

describe("subscription prompt", () => {
  const plan = (slug: string, period: "month" | "year", extra: Partial<Plan> = {}): Plan => ({
    id: slug,
    slug,
    name: slug,
    description: "",
    price_minor: 49900,
    currency: "INR",
    billing_period: period,
    credits_per_month: 50,
    badge: null,
    trial_enabled: false,
    trial_days: 7,
    trial_credits: 10,
    ...extra,
  });
  const me = (extra: Partial<Account> = {}): Account => ({
    id: "u",
    name: null,
    email: null,
    phone: null,
    photo_url: null,
    sign_in: "phone",
    credits: 0,
    subscription: null,
    trial_used: false,
    ...extra,
  });
  const monthly = plan("monthly", "month", { trial_enabled: true });
  const yearly = plan("yearly", "year", { trial_enabled: true, badge: "Best value" });

  it("prompts only signed-in users without a subscription when plans exist", () => {
    expect(needsSubscription(me(), [monthly])).toBe(true);
    expect(needsSubscription(undefined, [monthly])).toBe(false);
    expect(needsSubscription(me(), [])).toBe(false);
    const sub = { plan: { id: "monthly", name: "Monthly" }, status: "active", trial: true, current_period_end: "" };
    expect(needsSubscription(me({ subscription: sub }), [monthly])).toBe(false);
  });

  it("offers the trial once, monthly or yearly", () => {
    expect(trialOffered(me(), [monthly, yearly])).toBe(true);
    expect(trialOffered(me({ trial_used: true }), [monthly, yearly])).toBe(false);
    expect(trialOffered(me(), [plan("m", "month")])).toBe(false);
    expect(periods([monthly, yearly], true)).toEqual(["month", "year"]);
    expect(periods([plan("m", "month"), yearly], true)).toEqual(["year"]);
    expect(planFor([monthly, yearly], "year", true)?.slug).toBe("yearly");
    expect(planFor([plan("a", "year"), yearly], "year", false)?.slug).toBe("yearly");
  });
});

describe("paying with Razorpay", () => {
  const base = { id: "u", name: null, photo_url: null, credits: 0, trial_used: false } as const;
  const phoneUser: Account = { ...base, email: null, phone: "+919876543210", sign_in: "phone", subscription: null };
  const googleUser: Account = { ...base, email: "a@b.co", phone: null, sign_in: "google", subscription: null };

  it("asks only for what the account lacks", () => {
    expect(missingDetails(phoneUser)).toEqual({ email: true, phone: false });
    expect(missingDetails(googleUser)).toEqual({ email: false, phone: true });
  });

  it("checks the payer's details", () => {
    expect(validEmail("priya@example.com")).toBe(true);
    expect(validEmail("priya@")).toBe(false);
    expect(validMobile("9876543210")).toBe(true);
    expect(validMobile("919876543210")).toBe(true);
    expect(validMobile("1234567890")).toBe(false);
  });

  it("says how a paid plan stands", () => {
    const sub = { plan: { id: "p", name: "Monthly" }, status: "active", trial: false, provider: "razorpay", current_period_end: "2026-12-31T18:30:00Z" };
    expect(planLine({ ...phoneUser, subscription: sub })).toBe("You're on the Monthly plan. It renews automatically.");
    expect(planLine({ ...phoneUser, subscription: { ...sub, cancel_at_period_end: true } })).toMatch(/ends on 1 Jan 2027 and won't renew/);
    expect(planLine(phoneUser)).toBe("No plan yet.");
  });
});
