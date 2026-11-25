/** Shown after sign-in while the user has no subscription: a free trial (Monthly / Yearly) when one is
 * on offer, else the plans. "Maybe later" closes it until the next launch or sign-in. */
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type Account, type Plan } from "../lib/api";
import { creditsLabel, formatPrice, userMessage } from "../lib/format";
import { keys } from "../lib/queries";
import { session } from "../lib/session";
import {
  comingSoon,
  PERIOD_LABEL,
  periods,
  planFor,
  PROMPT,
  subscribeLabel,
  trialLine,
  trialNote,
  trialOffered,
  type Period,
} from "../lib/subscription";
import { IconSparkle } from "./Icons";

export function SubscriptionPrompt({
  me,
  plans,
  onStarted,
  onClose,
}: {
  me: Account;
  plans: Plan[];
  onStarted: () => void;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [started, setStarted] = useState<Account | null>(null);
  const trial = trialOffered(me, plans);
  const options = periods(plans, trial);
  const [period, setPeriod] = useState<Period | undefined>(options[0]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const plan = planFor(plans, period, trial);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const startTrial = async () => {
    if (!plan) return;
    setBusy(true);
    setError(null);
    try {
      const account = await api.startTrial(plan.id);
      onStarted();
      setStarted(account);
      qc.setQueryData(keys.me, account);
      session.setUser(account);
    } catch (e) {
      setError(userMessage(e, true));
      qc.invalidateQueries({ queryKey: keys.me });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="overlay" onClick={onClose}>
      <div
        className="sheet stack"
        role="dialog"
        aria-modal="true"
        aria-labelledby="subscription-title"
        data-testid="subscription-prompt"
        onClick={(e) => e.stopPropagation()}
      >
        {started ? (
          <>
            <div>
              <h2 id="subscription-title">{PROMPT.trialStarted}</h2>
              <p className="muted">
                You have {creditsLabel(started.credits)}. Your trial ends on{" "}
                {new Date(started.subscription?.current_period_end ?? "").toLocaleDateString("en-IN", {
                  day: "numeric",
                  month: "short",
                })}
                .
              </p>
            </div>
            <button className="btn block" onClick={onClose} autoFocus>
              {PROMPT.startCreating}
            </button>
          </>
        ) : (
          <>
            <div>
              <h2 id="subscription-title">{PROMPT.title}</h2>
              <p className="muted">{trial ? PROMPT.trialLead : PROMPT.paidLead}</p>
            </div>
            {options.length > 1 && (
              <div className="segmented" role="radiogroup" aria-label="Billing period">
                {options.map((p) => (
                  <button
                    key={p}
                    role="radio"
                    aria-checked={p === period}
                    className={p === period ? "on" : ""}
                    onClick={() => {
                      setPeriod(p);
                      setNotice(null);
                    }}
                  >
                    {PERIOD_LABEL[p]}
                  </button>
                ))}
              </div>
            )}
            {plan && (
              <div className="plan on">
                {plan.badge && <span className="badge">{plan.badge}</span>}
                <div className="spread">
                  <div>
                    <h3>{plan.name}</h3>
                    <p className="muted small">
                      <IconSparkle size={13} /> {plan.credits_per_month} credits every month
                    </p>
                    {trial && <p className="small trial-line">{trialLine(plan)}</p>}
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <span className="price">{formatPrice(plan.price_minor, plan.currency)}</span>
                    <span className="muted">/{plan.billing_period}</span>
                  </div>
                </div>
              </div>
            )}
            {error && <p className="notice error">{error}</p>}
            {notice && <p className="notice">{notice}</p>}
            {plan && trial && (
              <>
                <button className="btn block" onClick={startTrial} disabled={busy} autoFocus>
                  {PROMPT.startTrial}
                </button>
                <p className="muted small" style={{ textAlign: "center", margin: "-6px 0 0" }}>
                  {trialNote(plan)}
                </p>
              </>
            )}
            {plan && (
              <button className={trial ? "btn outline block" : "btn block"} onClick={() => setNotice(comingSoon(plan))}>
                {subscribeLabel(plan)}
              </button>
            )}
            <button className="btn ghost block" onClick={onClose}>
              {notice ? PROMPT.close : PROMPT.later}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
