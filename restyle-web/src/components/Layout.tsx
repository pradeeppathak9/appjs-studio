import { Link, NavLink, Outlet } from "react-router";
import { useMe } from "../lib/queries";
import { useSession } from "../lib/session";
import { IconGrid, IconImage, IconSparkle, IconUser } from "./Icons";

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
  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar-inner">
          <Link to="/" className="logo">
            <img src="/favicon.svg" alt="" />
            Restyle
          </Link>
          <div className="topbar-right">
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
