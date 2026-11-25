/** What the post-sign-in "Set up your subscription" prompt offers. Same rules and wording as the
 * Android app (SubscriptionPrompt.kt). */
import type { Account, Plan } from "./api";
import { formatPrice } from "./format";

export type Period = Plan["billing_period"];
export const PERIOD_LABEL: Record<Period, string> = { month: "Monthly", year: "Yearly" };

export const PROMPT = {
  title: "Set up your subscription",
  trialLead: "Start with a free trial. Pick monthly or yearly.",
  paidLead: "Subscribe to get fresh credits every month.",
  startTrial: "Start free trial",
  later: "Maybe later",
  close: "Close",
  trialStarted: "Your free trial is on",
  startCreating: "Start creating",
};

export const trialLine = (p: Plan) => `${p.trial_days}-day free trial · ${p.trial_credits} credits`;
export const trialNote = (p: Plan) => `No payment needed. The trial ends after ${p.trial_days} days; your credits stay.`;
export const subscribeLabel = (p: Plan) => `Subscribe · ${formatPrice(p.price_minor, p.currency)}/${p.billing_period}`;
export const comingSoon = (p: Plan) => `Payments are coming soon. Ask support to activate the ${p.name} plan.`;

/** Whether to prompt at all: signed in, no active subscription, and plans on offer. */
export function needsSubscription(me: Account | undefined, plans: Plan[] | undefined): boolean {
  return !!me && !me.subscription && !!plans && plans.length > 0;
}

/** The user can still start a trial (they never had one) and some plan offers one. */
export function trialOffered(me: Account | undefined, plans: Plan[]): boolean {
  return !!me && !me.trial_used && plans.some((p) => p.trial_enabled);
}

/** Monthly / Yearly, in the order the plans come. With a trial on offer, only periods with a trial plan. */
export function periods(plans: Plan[], trial: boolean): Period[] {
  const out: Period[] = [];
  for (const p of plans) if ((!trial || p.trial_enabled) && !out.includes(p.billing_period)) out.push(p.billing_period);
  return out;
}

/** The plan shown for a period: with a trial on offer one that has it; the badged one, else the first. */
export function planFor(plans: Plan[], period: Period | undefined, trial: boolean): Plan | undefined {
  const ofPeriod = plans.filter((p) => p.billing_period === period && (!trial || p.trial_enabled));
  return ofPeriod.find((p) => p.badge) ?? ofPeriod[0];
}

export const shortDate = (iso: string | undefined) =>
  iso ? new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: "Asia/Kolkata" }) : "";

/** The Plan line on the profile: trial, paid (renews / ends), or none. */
export function planLine(a: Account): string {
  const sub = a.subscription;
  if (!sub) return "No plan yet.";
  if (sub.trial) return `You're on a free trial of the ${sub.plan.name} plan.`;
  if (sub.provider === "razorpay")
    return sub.cancel_at_period_end
      ? `You're on the ${sub.plan.name} plan. It ends on ${shortDate(sub.current_period_end)} and won't renew.`
      : `You're on the ${sub.plan.name} plan. It renews automatically.`;
  return `You're on the ${sub.plan.name} plan.`;
}
