import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router";
import { GoogleButton } from "../components/GoogleButton";
import { IconBack } from "../components/Icons";
import { Spinner } from "../components/ui";
import { api, type SignedIn } from "../lib/api";
import { userMessage } from "../lib/format";
import { keys, useConfig } from "../lib/queries";
import { session, useSession } from "../lib/session";

const COUNTRY = "+91";

/** Only same-site paths, so ?next= can't send people elsewhere. */
function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

export function Login() {
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const { token } = useSession();
  const config = useConfig();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [usePhone, setUsePhone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (token) return <Navigate to={next} replace />;

  const done = (r: SignedIn) => {
    session.signIn(r.token, r.user);
    qc.setQueryData(keys.me, r.user);
    qc.invalidateQueries();
    navigate(next, { replace: true });
  };

  const c = config.data;
  const google = !!(c?.sign_in.google && c.sign_in.google_client_id);
  const phone = !!(c?.sign_in.phone && c.sign_in.phone_provider === "msg91");
  const showPhone = phone && (usePhone || !google);

  return (
    <div className="auth">
      <div className="auth-card">
        <div className="stack" style={{ gap: 8, alignItems: "center", textAlign: "center" }}>
          <img src="/favicon.svg" alt="" width={56} height={56} />
          <h1>Restyle</h1>
          <p className="muted">Turn any photo into a styled post</p>
        </div>
        <div className="card stack">
          {config.isLoading && <Spinner />}
          {config.error && <p className="error">{userMessage(config.error)}</p>}
          {c && !google && !phone && <p className="muted">Sign-in isn't available right now. Try again later.</p>}
          {google && !showPhone && (
            <>
              <h2>Sign in</h2>
              <p className="muted">Sign in to keep your credits and creations.</p>
              <GoogleButton
                clientId={c!.sign_in.google_client_id!}
                onToken={(t) =>
                  api.google(t).then(done, (e) => setError(userMessage(e)))
                }
              />
              {phone && (
                <>
                  <div className="divider">or</div>
                  <button className="btn outline block" onClick={() => setUsePhone(true)}>
                    Use phone number instead
                  </button>
                </>
              )}
            </>
          )}
          {showPhone && <PhoneSignIn onSignedIn={done} onBack={google ? () => setUsePhone(false) : undefined} />}
          {error && <p className="error">{error}</p>}
        </div>
        <p className="muted small" style={{ textAlign: "center" }}>
          By continuing you agree to Restyle's terms and privacy policy.
        </p>
      </div>
    </div>
  );
}

function PhoneSignIn({ onSignedIn, onBack }: { onSignedIn: (r: SignedIn) => void; onBack?: () => void }) {
  const [number, setNumber] = useState("");
  const [challenge, setChallenge] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resendAt, setResendAt] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  const codeInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!challenge) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [challenge]);

  const send = async (e?: FormEvent) => {
    e?.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api.sendOtp(number);
      setChallenge(r.challenge_id);
      setResendAt(Date.now() + r.resend_after_s * 1000);
      setNow(Date.now());
      setCode("");
      setTimeout(() => codeInput.current?.focus(), 0);
    } catch (err) {
      setError(userMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const verify = async (e?: FormEvent, value = code) => {
    e?.preventDefault();
    if (!challenge || value.length !== 6) return;
    setBusy(true);
    setError(null);
    try {
      onSignedIn(await api.verifyOtp(challenge, value));
    } catch (err) {
      setError(userMessage(err));
      setBusy(false);
    }
  };

  if (!challenge)
    return (
      <form className="stack" onSubmit={send}>
        <div className="row">
          {onBack && (
            <button type="button" className="btn ghost" onClick={onBack} aria-label="Back">
              <IconBack />
            </button>
          )}
          <h2>Log in with your mobile number.</h2>
        </div>
        <p className="muted">We'll send a 6-digit code by SMS.</p>
        <label className="field">
          <span className="prefix" aria-label={`Country code, India ${COUNTRY}`}>
            {COUNTRY}
          </span>
          <input
            inputMode="numeric"
            autoComplete="tel-national"
            placeholder="10-digit number"
            aria-label="Mobile number"
            value={number}
            maxLength={10}
            onChange={(e) => setNumber(e.target.value.replace(/\D/g, ""))}
            autoFocus
          />
        </label>
        {error && <p className="error">{error}</p>}
        <button className="btn block" disabled={number.length !== 10 || busy}>
          {busy ? <Spinner /> : "Get OTP"}
        </button>
      </form>
    );

  const wait = Math.max(0, Math.ceil((resendAt - now) / 1000));
  return (
    <form className="stack" onSubmit={verify}>
      <div className="row">
        <button type="button" className="btn ghost" onClick={() => setChallenge(null)} aria-label="Change number">
          <IconBack />
        </button>
        <h2>Enter the code</h2>
      </div>
      <p className="muted">
        Sent to {COUNTRY} {number.slice(0, 5)} {number.slice(5)} ·{" "}
        <button type="button" className="btn ghost" style={{ minHeight: 0, padding: 0 }} onClick={() => setChallenge(null)}>
          Change
        </button>
      </p>
      <label className="field">
        <input
          ref={codeInput}
          inputMode="numeric"
          autoComplete="one-time-code"
          placeholder="6-digit code"
          aria-label="Code"
          value={code}
          maxLength={6}
          style={{ letterSpacing: 6, fontSize: 20, fontWeight: 600 }}
          onChange={(e) => {
            const v = e.target.value.replace(/\D/g, "").slice(0, 6);
            setCode(v);
            if (v.length === 6) void verify(undefined, v);
          }}
        />
      </label>
      {error && <p className="error">{error}</p>}
      <button className="btn block" disabled={code.length !== 6 || busy}>
        {busy ? <Spinner /> : "Verify & continue"}
      </button>
      <p className="muted small" style={{ textAlign: "center" }}>
        Didn't get it?{" "}
        {wait > 0 ? (
          `Resend in 0:${String(wait).padStart(2, "0")}`
        ) : (
          <button type="button" className="btn ghost" style={{ minHeight: 0, padding: 0 }} onClick={() => void send()} disabled={busy}>
            Resend code
          </button>
        )}
      </p>
    </form>
  );
}
