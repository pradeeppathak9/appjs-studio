import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { IconCheck, IconSparkle } from "../components/Icons";
import { Spinner } from "../components/ui";
import { api, ApiError } from "../lib/api";
import { buy, missingDetails, savedPayer, savePayer, validEmail, validMobile } from "../lib/checkout";
import { creditsLabel, displayPhone, formatPrice, userMessage } from "../lib/format";
import { planLine, shortDate } from "../lib/subscription";
import { keys, useConfig, useMe, usePlans, useSignOut } from "../lib/queries";
import { session } from "../lib/session";

export function Profile() {
  const me = useMe();
  const signOut = useSignOut();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const qc = useQueryClient();
  const a = me.data;
  if (me.isLoading) return <Spinner />;
  if (!a) return <p className="notice error">{userMessage(me.error, true)}</p>;

  const cancel = async () => {
    const end = shortDate(a.subscription?.current_period_end);
    if (!window.confirm(`Cancel your subscription? It won't renew; your plan and credits stay until ${end}.`)) return;
    setCancelling(true);
    setError(null);
    try {
      const account = await api.cancelSubscription();
      qc.setQueryData(keys.me, account);
      session.setUser(account);
    } catch (e) {
      setError(userMessage(e, true));
    } finally {
      setCancelling(false);
    }
  };

  const remove = async () => {
    if (!window.confirm("Delete your account? Your credits and creations are removed, and this can't be undone.")) return;
    try {
      await api.deleteMe();
      session.clear();
      navigate("/login", { replace: true });
    } catch (e) {
      setError(userMessage(e, true));
    }
  };

  return (
    <div className="stack narrow" style={{ gap: 20 }}>
      <h1>Profile</h1>
      <div className="list">
        <div className="spread">
          <div>
            <h3>{a.name || (a.sign_in === "google" ? a.email : displayPhone(a.phone))}</h3>
            <p className="muted small">
              {a.sign_in === "google" ? `Signed in with Google · ${a.email}` : `Mobile number · ${displayPhone(a.phone)}`}
            </p>
          </div>
        </div>
        <div className="spread">
          <div>
            <p className="muted small">Balance</p>
            <h2 className="tabular">{creditsLabel(a.credits)}</h2>
          </div>
          <Link to="/subscribe" className="btn small">
            Get more credits
          </Link>
        </div>
        <div>
          <p className="muted small">Plan</p>
          <p>{planLine(a)}</p>
          {a.subscription?.provider === "razorpay" && !a.subscription.cancel_at_period_end && (
            <button className="btn ghost small" style={{ padding: 0, minHeight: 0 }} onClick={cancel} disabled={cancelling} data-testid="cancel-subscription">
              {cancelling ? "Cancelling…" : "Cancel subscription"}
            </button>
          )}
        </div>
      </div>
      {error && <p className="error">{error}</p>}
      <button
        className="btn outline block"
        onClick={async () => {
          await signOut();
          navigate("/login", { replace: true });
        }}
      >
        Sign out
      </button>
      <button className="btn danger block" onClick={remove}>
        Delete account
      </button>
    </div>
  );
}

export function Subscribe() {
  const me = useMe();
  const plans = usePlans();
  const config = useConfig();
  const qc = useQueryClient();
  const [params] = useSearchParams();
  const [picked, setPicked] = useState<string | null>(params.get("plan"));
  const [method, setMethod] = useState<"upi" | "card">("upi");
  const [payer, setPayer] = useState(savedPayer);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const list = plans.data ?? [];
  const chosen = list.find((p) => p.id === (picked ?? list.find((x) => x.badge)?.id ?? list[0]?.id));
  const sub = me.data?.subscription;
  const current = sub?.plan.id;
  const payable = config.data?.payments?.provider === "razorpay";
  const subscribed = !!sub && !sub.trial && !sub.cancel_at_period_end;
  const need = missingDetails(me.data);

  const pay = async () => {
    if (!chosen) return;
    setError(null);
    setNotice(null);
    if (need.email && !validEmail(payer.email)) return setError("Enter your email address. Razorpay sends the receipt there.");
    if (need.phone && !validMobile(payer.phone)) return setError("Enter your 10-digit mobile number.");
    setBusy(true);
    try {
      if (need.email || need.phone) savePayer(payer);
      const result = await buy(
        {
          plan_id: chosen.id,
          method,
          ...(need.email ? { email: payer.email.trim() } : {}),
          ...(need.phone ? { phone: payer.phone.replace(/\D/g, "") } : {}),
        },
        chosen.name,
      );
      if (result.kind === "active") {
        const account = await api.me();
        qc.setQueryData(keys.me, account);
        session.setUser(account);
        setNotice(`You're on the ${chosen.name} plan. You have ${creditsLabel(account.credits)}.`);
      } else if (result.kind === "pending") {
        setNotice("We're confirming your payment. Your plan and credits appear here in a minute.");
        qc.invalidateQueries({ queryKey: keys.me });
      } else if (result.kind === "failed") {
        setError(result.message);
      } else {
        setNotice("Payment cancelled. Nothing was charged.");
      }
    } catch (e) {
      setError(e instanceof Error && !(e instanceof ApiError) ? e.message : userMessage(e, true));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack narrow" style={{ gap: 20 }}>
      <div>
        <h1>Subscribe for credits</h1>
        <p className="muted">
          {me.data ? `You have ${creditsLabel(me.data.credits)}.` : ""} Subscribe to get fresh credits every month.
        </p>
      </div>
      {plans.isLoading && <Spinner />}
      {plans.isSuccess && list.length === 0 && <p className="muted">No plans are on offer right now.</p>}
      <div className="stack" role="radiogroup" aria-label="Plans">
        {list.map((p) => (
          <button key={p.id} role="radio" aria-checked={p.id === chosen?.id} className={p.id === chosen?.id ? "plan on" : "plan"} onClick={() => setPicked(p.id)}>
            {p.badge && <span className="badge">{p.badge}</span>}
            <div className="spread">
              <div>
                <h3>
                  {p.name} {p.id === current && <span className="muted small">· current plan</span>}
                </h3>
                <p className="muted small">
                  <IconSparkle size={13} /> {p.credits_per_month} credits every month
                </p>
                {p.description && <p className="muted small">{p.description}</p>}
              </div>
              <div style={{ textAlign: "right" }}>
                <span className="price">{formatPrice(p.price_minor, p.currency)}</span>
                <span className="muted">/{p.billing_period}</span>
              </div>
            </div>
          </button>
        ))}
      </div>
      {chosen && (
        <>
          <ul className="muted small" style={{ margin: 0, paddingLeft: 0, listStyle: "none" }}>
            {[`${chosen.credits_per_month} credits every month`, "All styles, plus new ones as they're added", "Cancel anytime"].map((t) => (
              <li key={t} className="row" style={{ gap: 8 }}>
                <IconCheck size={16} /> {t}
              </li>
            ))}
          </ul>
          {payable && !subscribed && (
            <div className="stack" style={{ gap: 10 }} data-testid="pay-details">
              <div className="segmented" role="radiogroup" aria-label="Pay with">
                {(["upi", "card"] as const).map((m) => (
                  <button key={m} type="button" role="radio" aria-checked={m === method} className={m === method ? "on" : ""} onClick={() => setMethod(m)}>
                    {m === "upi" ? "UPI Autopay" : "Card"}
                  </button>
                ))}
              </div>
              {need.email && (
                <label className="field">
                  <input
                    type="email"
                    autoComplete="email"
                    placeholder="Email for the receipt"
                    aria-label="Email"
                    value={payer.email}
                    onChange={(e) => setPayer({ ...payer, email: e.target.value })}
                  />
                </label>
              )}
              {need.phone && (
                <label className="field">
                  <span className="prefix">+91</span>
                  <input
                    inputMode="numeric"
                    autoComplete="tel-national"
                    placeholder="10-digit mobile number"
                    aria-label="Mobile number"
                    maxLength={10}
                    value={payer.phone}
                    onChange={(e) => setPayer({ ...payer, phone: e.target.value.replace(/\D/g, "") })}
                  />
                </label>
              )}
            </div>
          )}
          {error && <p className="notice error">{error}</p>}
          {notice && <p className="notice">{notice}</p>}
          {payable ? (
            subscribed ? (
              <p className="muted" style={{ textAlign: "center" }}>
                You're on the {sub!.plan.name} plan. Manage it from your profile.
              </p>
            ) : (
              <button className="btn block" onClick={pay} disabled={busy} data-testid="subscribe">
                {busy ? <Spinner /> : `Subscribe · ${formatPrice(chosen.price_minor, chosen.currency)}/${chosen.billing_period}`}
              </button>
            )
          ) : (
            <button
              className="btn block"
              onClick={() =>
                setNotice(
                  `Payments aren't available yet. Ask support to activate the ${chosen.name} plan; your credits appear here as soon as it's on.`,
                )
              }
            >
              Subscribe · {formatPrice(chosen.price_minor, chosen.currency)}/{chosen.billing_period}
            </button>
          )}
          <p className="muted small" style={{ textAlign: "center" }}>
            {payable
              ? "Paid securely with Razorpay. Renews automatically; cancel anytime from your profile."
              : "Payments are coming soon. Renews automatically; cancel anytime."}
          </p>
        </>
      )}
    </div>
  );
}
