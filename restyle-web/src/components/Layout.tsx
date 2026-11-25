import { useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router";
import { useMe, usePlans } from "../lib/queries";
import { needsSubscription } from "../lib/subscription";
import { readView, saveView, useSession, type View } from "../lib/session";
import { IconGrid, IconImage, IconMonitor, IconPhone, IconSparkle, IconUser } from "./Icons";
import { SubscriptionPrompt } from "./SubscriptionPrompt";

const TABS = [
  { to: "/", label: "Templates", icon: IconGrid, end: true },
  { to: "/creations", label: "My creations", icon: IconImage, end: false },
  { to: "/profile", label: "Profile", icon: IconUser, end: false },
];

/** Up to two letters from a name or email; none for a phone number (the avatar shows an icon). */
function initials(name: string | null | undefined): string {
  return (name ?? "").replace(/@.*/, "").split(/[\s._-]+/).filter((w) => /^[a-z]/i.test(w)).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
}

export function Layout() {
  const { token, user } = useSession();
  const me = useMe();
  const account = me.data ?? user;
  const plans = usePlans();
  const location = useLocation();
  // "Maybe later" holds for this session token only: the prompt is back after a reload or a new sign-in.
  const [dismissedFor, setDismissedFor] = useState<string | null>(null);
  // Stays open after a trial starts (the account then has a subscription) to show the confirmation.
  const [keepOpen, setKeepOpen] = useState(false);
  const prompt =
    keepOpen ||
    (!!token &&
    dismissedFor !== token &&
    location.pathname !== "/subscribe" &&
    needsSubscription(me.data, plans.data));
  const [view, setView] = useState<View>(readView);
  const toggleView = () => {
    const next = view === "wide" ? "phone" : "wide";
    saveView(next);
    setView(next);
  };
  return (
    <div className={view === "wide" ? "shell wide" : "shell"}>
      <header className="topbar">
        <div className="topbar-inner">
          <Link to="/" className="logo">
            <img src="/favicon.svg" alt="" />
            Restyle AI
          </Link>
          <nav className="topnav" aria-label="Main">
            {TABS.map((t) => (
              <NavLink key={t.to} to={t.to} end={t.end}>
                {t.label}
              </NavLink>
            ))}
          </nav>
          <div className="topbar-right">
            <button
              type="button"
              className="view-toggle"
              onClick={toggleView}
              aria-label={view === "wide" ? "Switch to phone view" : "Switch to wide view"}
              title={view === "wide" ? "Phone view" : "Wide view"}
            >
              {view === "wide" ? <IconPhone size={20} /> : <IconMonitor size={20} />}
            </button>
            {token ? (
              <>
                <Link to="/subscribe" className="chip tabular" data-testid="credits-chip">
                  <IconSparkle size={16} />
                  {account?.credits ?? "…"} credits
                </Link>
                <Link to="/profile" className="avatar" aria-label="Profile">
                  {account?.photo_url ? (
                    <img src={account.photo_url} alt="" referrerPolicy="no-referrer" />
                  ) : (
                    initials(account?.name ?? account?.email) || <IconUser size={20} />
                  )}
                </Link>
              </>
            ) : (
              <Link to="/login" className="btn small">
                Sign in
              </Link>
            )}
          </div>
        </div>
      </header>
      <main className="page">
        <Outlet />
      </main>
      {prompt && me.data && plans.data && (
        <SubscriptionPrompt
          me={me.data}
          plans={plans.data}
          onStarted={() => setKeepOpen(true)}
          onClose={() => {
            setKeepOpen(false);
            setDismissedFor(token);
          }}
        />
      )}
      <nav className="tabbar" aria-label="Main">
        {TABS.map((t) => (
          <NavLink key={t.to} to={t.to} end={t.end}>
            <span className="pill">
              <t.icon size={22} />
            </span>
            {t.label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
