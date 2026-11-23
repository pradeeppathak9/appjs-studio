/** "Continue with Google" through Google Identity Services. The ID token is for the app's OAuth *Web*
 * client id (from GET /v1/app), which the server checks. The site's origin must be listed under that
 * client's "Authorized JavaScript origins" in Google Cloud. */
import { useEffect, useRef, useState } from "react";

type CredentialResponse = { credential: string };
type Gsi = {
  accounts: {
    id: {
      initialize(o: { client_id: string; callback: (r: CredentialResponse) => void; ux_mode?: string }): void;
      renderButton(el: HTMLElement, o: Record<string, unknown>): void;
    };
  };
};

declare global {
  interface Window {
    google?: Gsi;
  }
}

let loading: Promise<Gsi> | null = null;
function loadGsi(): Promise<Gsi> {
  if (window.google?.accounts) return Promise.resolve(window.google);
  loading ??= new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://accounts.google.com/gsi/client";
    s.async = true;
    s.onload = () => (window.google ? resolve(window.google) : reject(new Error("gsi missing")));
    s.onerror = () => {
      loading = null;
      reject(new Error("gsi failed"));
    };
    document.head.appendChild(s);
  });
  return loading;
}

export function GoogleButton({ clientId, onToken }: { clientId: string; onToken: (idToken: string) => void }) {
  const el = useRef<HTMLDivElement>(null);
  const callback = useRef(onToken);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    callback.current = onToken;
  });
  useEffect(() => {
    let alive = true;
    loadGsi()
      .then((g) => {
        if (!alive || !el.current) return;
        g.accounts.id.initialize({ client_id: clientId, callback: (r) => callback.current(r.credential) });
        g.accounts.id.renderButton(el.current, {
          theme: "outline",
          size: "large",
          shape: "pill",
          text: "continue_with",
          width: Math.min(el.current.clientWidth || 360, 400),
        });
      })
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, [clientId]);
  if (failed) return <p className="error">Google sign-in couldn't load. Check your connection or use your phone number.</p>;
  return <div ref={el} style={{ minHeight: 44, display: "flex", justifyContent: "center" }} />;
}
