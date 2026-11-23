import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { IconCheck, IconSparkle } from "../components/Icons";
import { Spinner } from "../components/ui";
import { api } from "../lib/api";
import { creditsLabel, displayPhone, formatPrice, userMessage } from "../lib/format";
import { useMe, usePlans, useSignOut } from "../lib/queries";
import { session } from "../lib/session";

export function Profile() {
  const me = useMe();
  const signOut = useSignOut();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const a = me.data;
  if (me.isLoading) return <Spinner />;
  if (!a) return <p className="notice error">{userMessage(me.error, true)}</p>;

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
          <p>{a.subscription ? `You're on the ${a.subscription.plan.name} plan.` : "No plan yet."}</p>
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
  const [picked, setPicked] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const list = plans.data ?? [];
  const chosen = list.find((p) => p.id === (picked ?? list.find((x) => x.badge)?.id ?? list[0]?.id));
  const current = me.data?.subscription?.plan.id;

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
          {notice && <p className="notice">{notice}</p>}
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
          <p className="muted small" style={{ textAlign: "center" }}>
            Payments are coming soon. Renews automatically; cancel anytime.
          </p>
        </>
      )}
    </div>
  );
}
