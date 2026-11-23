import React, { useCallback, useEffect, useState } from "react";
import {
  getWebhookConfig,
  updateWebhookConfig,
  rotateWebhookSecret,
  sendWebhookTest,
  listWebhookDeliveries,
  retryWebhookDelivery,
} from "../api";

function copyToClipboard(text) {
  if (navigator.clipboard) return navigator.clipboard.writeText(text);
  const el = document.createElement("textarea");
  el.value = text;
  el.style.position = "fixed";
  el.style.opacity = "0";
  document.body.appendChild(el);
  el.select();
  document.execCommand("copy");
  document.body.removeChild(el);
  return Promise.resolve();
}

function CopyButton({ value, label = "Copy", style }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      style={style || w.smallBtn}
      onClick={() => {
        copyToClipboard(value);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
    >
      {copied ? "✓" : label}
    </button>
  );
}

const STATUS_STYLE = {
  DELIVERED: { bg: "#f0fdf4", border: "#bbf7d0", color: "#166534" },
  PENDING: { bg: "#fffbeb", border: "#fde68a", color: "#92400e" },
  FAILED: { bg: "#fef2f2", border: "#fecaca", color: "#991b1b" },
};

function StatusPill({ status }) {
  const c = STATUS_STYLE[status] || STATUS_STYLE.PENDING;
  return (
    <span style={{ ...w.pill, backgroundColor: c.bg, border: `1px solid ${c.border}`, color: c.color }}>
      {status}
    </span>
  );
}

function relativeTime(iso) {
  if (!iso) return "—";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function DeliveryRow({ delivery, appId, onRetried }) {
  const [open, setOpen] = useState(false);
  const [retrying, setRetrying] = useState(false);

  async function handleRetry(e) {
    e.stopPropagation();
    setRetrying(true);
    try {
      await retryWebhookDelivery(appId, delivery.id);
      onRetried();
    } finally {
      setRetrying(false);
    }
  }

  return (
    <div style={w.delivery}>
      <div style={w.deliveryTop} onClick={() => setOpen((o) => !o)}>
        <StatusPill status={delivery.status} />
        <code style={w.deliveryEvent}>{delivery.event}</code>
        <span style={w.deliveryMeta}>
          {delivery.response_code ? `HTTP ${delivery.response_code}` : "no response"}
          {delivery.attempts > 1 ? ` · ${delivery.attempts} attempts` : ""}
        </span>
        <span style={w.deliveryTime}>{relativeTime(delivery.created_at)}</span>
        <span style={w.caret}>{open ? "▾" : "▸"}</span>
      </div>
      {open && (
        <div style={w.deliveryBody}>
          <div style={w.kv}>
            <span style={w.kvKey}>Delivery ID</span>
            <code style={w.kvVal}>{delivery.id}</code>
          </div>
          <div style={w.kv}>
            <span style={w.kvKey}>Object</span>
            <code style={w.kvVal}>{delivery.object_id}</code>
          </div>
          <div style={w.kv}>
            <span style={w.kvKey}>URL</span>
            <code style={w.kvVal}>{delivery.url}</code>
          </div>
          {delivery.error && (
            <div style={w.errBox}>{delivery.error}</div>
          )}
          <div style={w.codeWrap}>
            <div style={w.codeHeader}>
              <span style={w.codeLabel}>payload</span>
              <CopyButton value={JSON.stringify(delivery.payload, null, 2)} style={w.codeCopy} />
            </div>
            <pre style={w.pre}>{JSON.stringify(delivery.payload, null, 2)}</pre>
          </div>
          {delivery.status !== "DELIVERED" && (
            <button type="button" onClick={handleRetry} disabled={retrying} style={w.retryBtn}>
              {retrying ? "Retrying…" : "Retry delivery"}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function EventRow({ event, checked, onToggle }) {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState("body");

  const body = JSON.stringify(event.sample, null, 2);
  const headers = Object.entries(event.sample_headers || {})
    .map(([k, v]) => `${k}: ${v}`)
    .join("\n");
  const shown = tab === "body" ? body : headers;

  return (
    <div style={w.event}>
      <div style={w.eventTop}>
        {/* The label wraps only the checkbox and its text. Putting the sample
            toggle inside it would make every click on "Sample" also subscribe
            or unsubscribe from the event. */}
        <label style={w.eventLabel}>
          <input type="checkbox" checked={checked} onChange={onToggle} style={{ marginTop: 3 }} />
          <span>
            <code style={w.eventName}>{event.name}</code>
            <span style={w.eventDesc}>{event.description}</span>
          </span>
        </label>
        {event.sample && (
          <button type="button" onClick={() => setOpen((o) => !o)} style={w.sampleBtn}>
            {open ? "▾ Hide" : "▸ Sample"}
          </button>
        )}
      </div>

      {open && event.sample && (
        <div style={w.codeWrap}>
          <div style={w.codeHeader}>
            <span style={w.tabs}>
              <button
                type="button"
                onClick={() => setTab("body")}
                style={tab === "body" ? w.tabOn : w.tabOff}
              >
                body
              </button>
              <button
                type="button"
                onClick={() => setTab("headers")}
                style={tab === "headers" ? w.tabOn : w.tabOff}
              >
                headers
              </button>
            </span>
            <CopyButton value={shown} style={w.codeCopy} />
          </div>
          <pre style={w.pre}>{shown}</pre>
        </div>
      )}
    </div>
  );
}


export default function WebhooksSection({ app, styles: s }) {
  const [config, setConfig] = useState(null);
  const [deliveries, setDeliveries] = useState([]);
  const [url, setUrl] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [events, setEvents] = useState([]);
  const [authEnabled, setAuthEnabled] = useState(false);
  // Always starts empty, even when a credential is stored: the API only ever
  // returns a mask, so an empty box means "leave what is saved alone".
  const [authHeader, setAuthHeader] = useState("");
  const [showAuth, setShowAuth] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  const [testResult, setTestResult] = useState(null);
  const [testing, setTesting] = useState(false);
  const [freshSecret, setFreshSecret] = useState(null);
  const [confirmRotate, setConfirmRotate] = useState(false);
  const [showHelp, setShowHelp] = useState(false);

  const applyConfig = useCallback((c) => {
    setConfig(c);
    setUrl(c.url || "");
    setEnabled(c.enabled);
    setEvents(c.events || []);
    setAuthEnabled(c.auth_enabled);
    setAuthHeader("");
    // The API returns the full secret only on the response that minted it.
    if (c.secret && !c.secret.includes("•")) setFreshSecret(c.secret);
  }, []);

  const loadDeliveries = useCallback(async () => {
    try {
      const res = await listWebhookDeliveries(app.id, { limit: 10 });
      setDeliveries(res.deliveries || []);
    } catch {
      /* the config is the important half; a failed log fetch stays silent */
    }
  }, [app.id]);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const c = await getWebhookConfig(app.id);
        if (alive) applyConfig(c);
      } catch (e) {
        if (alive) setError(e.message);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    loadDeliveries();
    return () => {
      alive = false;
    };
  }, [app.id, applyConfig, loadDeliveries]);

  async function handleSave() {
    setSaving(true);
    setError("");
    setSaved(false);
    try {
      const payload = { url, enabled, events, auth_enabled: authEnabled };
      // Only send the credential when something was typed. Sending "" would
      // clear a stored one, and sending the mask would overwrite it with dots.
      if (authHeader.trim()) payload.auth_header = authHeader.trim();
      applyConfig(await updateWebhookConfig(app.id, payload));
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleRotate() {
    if (!confirmRotate) {
      setConfirmRotate(true);
      return;
    }
    setConfirmRotate(false);
    setError("");
    try {
      applyConfig(await rotateWebhookSecret(app.id));
    } catch (e) {
      setError(e.message);
    }
  }

  async function handleTest() {
    setTesting(true);
    setTestResult(null);
    setError("");
    try {
      await sendWebhookTest(app.id);
      setTestResult("queued");
      // Delivery is asynchronous; give the worker a moment, then show the row.
      setTimeout(loadDeliveries, 1500);
      setTimeout(loadDeliveries, 4000);
    } catch (e) {
      setError(e.message);
    } finally {
      setTesting(false);
    }
  }

  function toggleEvent(name) {
    setEvents((prev) => (prev.includes(name) ? prev.filter((e) => e !== name) : [...prev, name]));
  }

  if (loading) {
    return (
      <section style={s.section}>
        <h2 style={s.sectionTitle}>Webhooks</h2>
        <p style={s.sectionDesc}>Loading…</p>
      </section>
    );
  }

  const dirty =
    config &&
    (url !== (config.url || "") ||
      enabled !== config.enabled ||
      authEnabled !== config.auth_enabled ||
      authHeader.trim() !== "" ||
      events.length !== (config.events || []).length ||
      events.some((e) => !(config.events || []).includes(e)));

  return (
    <section style={s.section}>
      <div style={s.sectionHeader}>
        <div>
          <h2 style={s.sectionTitle}>Webhooks</h2>
          <p style={s.sectionDesc}>
            We POST a signed JSON payload to your endpoint when a subscription event happens,
            so you don't have to poll for it.
          </p>
        </div>
        <button
          type="button"
          onClick={handleTest}
          disabled={testing || !config.url}
          style={testing ? s.testingBtn : s.testBtn}
          title={!config.url ? "Save an endpoint URL first" : "Send a webhook.test event"}
        >
          {testing ? "Sending…" : "Send Test"}
        </button>
      </div>

      {error && <div style={s.testError}>✗ {error}</div>}
      {testResult === "queued" && (
        <div style={s.testSuccess}>
          ✓ Test event queued — watch for it under Recent deliveries below.
        </div>
      )}

      <div style={s.field}>
        <label style={s.label}>Endpoint URL</label>
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://yourapp.com/hooks/autorev"
          style={s.input}
        />
        <p style={w.hint}>
          Must be publicly reachable over HTTPS. Reply 2xx within 10 seconds — do the work
          afterwards, not before you respond.
        </p>
      </div>

      <label style={s.checkboxRow}>
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
        Deliver events to this endpoint
      </label>

      <div style={s.divider}>Events</div>
      <p style={w.hint}>
        Tick the events you want delivered. Open <strong>Sample</strong> on any of them to see the
        exact body and headers we send.
      </p>
      {(config.available_events || []).map((ev) => (
        <EventRow
          key={ev.name}
          event={ev}
          checked={events.includes(ev.name)}
          onToggle={() => toggleEvent(ev.name)}
        />
      ))}

      <div style={s.divider}>Authorization header (optional)</div>
      <label style={s.checkboxRow}>
        <input
          type="checkbox"
          checked={authEnabled}
          onChange={(e) => setAuthEnabled(e.target.checked)}
        />
        Send an Authorization header with every delivery
      </label>

      {authEnabled && (
        <div style={s.field}>
          {config.has_auth_header && (
            <div style={w.authStored}>
              Stored: <code>{config.auth_header}</code> — leave the box empty to keep it.
            </div>
          )}
          <div style={s.secretRow}>
            <input
              value={authHeader}
              onChange={(e) => setAuthHeader(e.target.value)}
              type={showAuth ? "text" : "password"}
              placeholder={config.has_auth_header ? "Enter a new value to replace it" : "Bearer eyJhbGciOi…"}
              style={{ ...s.input, flex: 1 }}
            />
            <button type="button" onClick={() => setShowAuth((v) => !v)} style={s.toggleBtn}>
              {showAuth ? "Hide" : "Show"}
            </button>
          </div>
          <p style={w.hint}>
            Sent verbatim as <code style={s.inlineCode}>Authorization</code>, so include the
            scheme — <code style={s.inlineCode}>Bearer &lt;token&gt;</code> or{" "}
            <code style={s.inlineCode}>Basic &lt;base64&gt;</code>. Write-only: we never show it
            again. This does not replace the signature — verify that too, since anyone who
            learns this value could call your endpoint.
          </p>
        </div>
      )}

      <div style={w.saveRow}>
        {saved && <span style={w.savedMsg}>✓ Webhook saved</span>}
        <button
          type="button"
          onClick={handleSave}
          disabled={saving || !dirty}
          style={dirty && !saving ? w.saveBtn : w.saveBtnDisabled}
        >
          {saving ? "Saving…" : "Save Webhook"}
        </button>
      </div>

      {config.has_secret && (
        <>
          <div style={s.divider}>Signing secret</div>
          {freshSecret ? (
            <div style={w.freshSecret}>
              <div style={w.freshSecretNote}>
                Copy this now — it is only shown once.
              </div>
              <div style={w.secretBox}>
                <code style={w.secretValue}>{freshSecret}</code>
                <CopyButton value={freshSecret} />
              </div>
            </div>
          ) : (
            <div style={w.secretBox}>
              <code style={w.secretValue}>{config.secret}</code>
            </div>
          )}

          <div style={w.rotateRow}>
            {confirmRotate && (
              <span style={w.warn}>
                The old secret stops verifying immediately. Deploy the new one first.
              </span>
            )}
            {confirmRotate && (
              <button type="button" onClick={() => setConfirmRotate(false)} style={w.cancelBtn}>
                Cancel
              </button>
            )}
            <button
              type="button"
              onClick={handleRotate}
              style={confirmRotate ? w.confirmBtn : w.smallBtn}
            >
              {confirmRotate ? "Yes, rotate" : "Rotate secret"}
            </button>
          </div>

          <button type="button" onClick={() => setShowHelp((h) => !h)} style={w.helpToggle}>
            {showHelp ? "▾ Hide verification example" : "▸ How to verify the signature"}
          </button>
          {showHelp && (
            <div style={w.codeWrap}>
              <div style={w.codeHeader}>
                <span style={w.codeLabel}>node</span>
                <CopyButton value={VERIFY_SNIPPET} style={w.codeCopy} />
              </div>
              <pre style={w.pre}>{VERIFY_SNIPPET}</pre>
            </div>
          )}
        </>
      )}

      <div style={{ ...s.divider, display: "flex", alignItems: "center", gap: 10 }}>
        Recent deliveries
        <button type="button" onClick={loadDeliveries} style={w.refreshBtn}>
          Refresh
        </button>
      </div>
      {deliveries.length === 0 ? (
        <p style={w.empty}>
          Nothing delivered yet. Use <strong>Send Test</strong> above to check your endpoint.
        </p>
      ) : (
        <div style={w.deliveryList}>
          {deliveries.map((d) => (
            <DeliveryRow key={d.id} delivery={d} appId={app.id} onRetried={loadDeliveries} />
          ))}
        </div>
      )}
    </section>
  );
}

const VERIFY_SNIPPET = `// Verify on the RAW body — JSON.parse then re-stringify will not match.
const crypto = require("crypto");

app.post("/hooks/autorev",
  express.raw({ type: "application/json" }),
  (req, res) => {
    const expected = "sha256=" + crypto
      .createHmac("sha256", process.env.AUTOREV_WEBHOOK_SECRET)
      .update(req.body)
      .digest("hex");

    const got = req.headers["x-autorev-signature"] || "";
    if (got.length !== expected.length ||
        !crypto.timingSafeEqual(Buffer.from(got), Buffer.from(expected))) {
      return res.sendStatus(401);
    }

    // Respond first, then process: we time out after 10s and retry.
    res.sendStatus(200);

    const event = JSON.parse(req.body);
    // X-Autorev-Delivery is stable across retries — use it to stay idempotent.
    handle(req.headers["x-autorev-delivery"], event);
  });`;

const w = {
  hint: { margin: "6px 0 0", fontSize: 12, color: "#64748b", lineHeight: 1.5 },
  authStored: { padding: "7px 10px", backgroundColor: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 6, fontSize: 12, color: "#475569", marginBottom: 8 },
  event: { padding: "8px 0", borderBottom: "1px solid #f8fafc" },
  eventTop: { display: "flex", gap: 10, alignItems: "flex-start" },
  eventLabel: { display: "flex", gap: 10, alignItems: "flex-start", flex: 1, fontSize: 13, color: "#1e293b", cursor: "pointer" },
  sampleBtn: { flexShrink: 0, padding: "3px 10px", backgroundColor: "#f1f5f9", border: "1px solid #e2e8f0", borderRadius: 6, cursor: "pointer", fontSize: 11, color: "#475569", whiteSpace: "nowrap" },
  tabs: { display: "flex", gap: 4 },
  tabOn: { padding: "2px 9px", backgroundColor: "#1e293b", color: "#fff", border: "none", borderRadius: 5, cursor: "pointer", fontSize: 10, letterSpacing: 0.3 },
  tabOff: { padding: "2px 9px", backgroundColor: "transparent", color: "#64748b", border: "1px solid #e2e8f0", borderRadius: 5, cursor: "pointer", fontSize: 10, letterSpacing: 0.3 },
  eventName: { display: "block", backgroundColor: "#e2e8f0", padding: "1px 5px", borderRadius: 4, fontSize: 12, width: "fit-content" },
  eventDesc: { display: "block", marginTop: 4, color: "#64748b", fontSize: 12, lineHeight: 1.5 },
  saveRow: { display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 12, marginTop: 16 },
  savedMsg: { color: "#166534", fontSize: 13 },
  saveBtn: { padding: "9px 20px", backgroundColor: "#4f46e5", color: "#fff", border: "none", borderRadius: 8, cursor: "pointer", fontSize: 13, fontWeight: 500 },
  saveBtnDisabled: { padding: "9px 20px", backgroundColor: "#e2e8f0", color: "#94a3b8", border: "none", borderRadius: 8, cursor: "not-allowed", fontSize: 13, fontWeight: 500 },
  secretBox: { display: "flex", alignItems: "center", gap: 8, backgroundColor: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: "8px 10px" },
  secretValue: { flex: 1, fontSize: 12, color: "#1e293b", wordBreak: "break-all", fontFamily: "monospace" },
  freshSecret: { border: "1px solid #bbf7d0", backgroundColor: "#f0fdf4", borderRadius: 8, padding: 10 },
  freshSecretNote: { fontSize: 12, color: "#166534", marginBottom: 8, fontWeight: 500 },
  rotateRow: { display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 10, marginTop: 10, flexWrap: "wrap" },
  warn: { fontSize: 12, color: "#92400e", flex: 1, minWidth: 180 },
  smallBtn: { padding: "6px 12px", backgroundColor: "#f1f5f9", border: "1px solid #e2e8f0", borderRadius: 6, cursor: "pointer", fontSize: 12, color: "#1e293b", whiteSpace: "nowrap" },
  cancelBtn: { padding: "6px 12px", backgroundColor: "#fff", border: "1px solid #e2e8f0", borderRadius: 6, cursor: "pointer", fontSize: 12, color: "#64748b" },
  confirmBtn: { padding: "6px 12px", backgroundColor: "#dc2626", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 12, fontWeight: 500 },
  helpToggle: { marginTop: 12, padding: 0, background: "none", border: "none", color: "#2563eb", cursor: "pointer", fontSize: 12 },
  refreshBtn: { marginLeft: "auto", padding: "4px 10px", backgroundColor: "#f1f5f9", border: "1px solid #e2e8f0", borderRadius: 6, cursor: "pointer", fontSize: 11, color: "#475569", textTransform: "none", letterSpacing: 0, fontWeight: 400 },
  empty: { margin: 0, fontSize: 13, color: "#64748b" },
  deliveryList: { display: "flex", flexDirection: "column", gap: 6 },
  delivery: { border: "1px solid #e2e8f0", borderRadius: 8, overflow: "hidden" },
  deliveryTop: { display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", cursor: "pointer", flexWrap: "wrap" },
  deliveryEvent: { fontSize: 12, color: "#1e293b", fontFamily: "monospace" },
  deliveryMeta: { fontSize: 11, color: "#64748b" },
  deliveryTime: { fontSize: 11, color: "#94a3b8", marginLeft: "auto" },
  caret: { fontSize: 10, color: "#94a3b8" },
  deliveryBody: { borderTop: "1px solid #e2e8f0", padding: 10, backgroundColor: "#f8fafc" },
  kv: { display: "flex", gap: 8, fontSize: 11, marginBottom: 6 },
  kvKey: { color: "#64748b", flex: "0 0 86px" },
  kvVal: { color: "#1e293b", wordBreak: "break-all", fontFamily: "monospace" },
  errBox: { padding: "8px 10px", backgroundColor: "#fef2f2", border: "1px solid #fecaca", borderRadius: 6, fontSize: 11, color: "#991b1b", margin: "8px 0", wordBreak: "break-word", maxHeight: 120, overflow: "auto" },
  pill: { padding: "2px 7px", borderRadius: 999, fontSize: 10, fontWeight: 600, letterSpacing: 0.3 },
  codeWrap: { marginTop: 8, border: "1px solid #e2e8f0", borderRadius: 8, overflow: "hidden" },
  codeHeader: { display: "flex", justifyContent: "space-between", alignItems: "center", padding: "5px 10px", backgroundColor: "#f1f5f9", borderBottom: "1px solid #e2e8f0" },
  codeLabel: { fontSize: 10, color: "#64748b", textTransform: "uppercase", letterSpacing: 0.5 },
  codeCopy: { padding: "3px 8px", backgroundColor: "#fff", border: "1px solid #e2e8f0", borderRadius: 5, cursor: "pointer", fontSize: 10, color: "#475569" },
  pre: { margin: 0, padding: 10, fontSize: 11, lineHeight: 1.55, color: "#1e293b", backgroundColor: "#fff", overflowX: "auto", maxHeight: 320, whiteSpace: "pre" },
  retryBtn: { marginTop: 10, padding: "6px 12px", backgroundColor: "#4f46e5", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 12 },
};
